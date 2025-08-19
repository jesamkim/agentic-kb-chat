"""
Improved Response Agent - Fixed Version
tiktoken 의존성을 안전하게 처리하는 개선된 Response Agent
"""

import boto3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

from config.settings import settings
from src.utils.logger import agent_logger
from src.utils.session import ChatSession, Message
from src.utils.citation import CitationCollection, CitationProcessor
from src.utils.s3_utils import batch_enhance_citations_with_s3_info

# tiktoken 안전 import
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("Warning: tiktoken not available. Using fallback token counting.")


class ImprovedResponseAgent:
    """개선된 Response Agent - 3000 토큰 제한 및 통합 응답 생성"""
    
    def __init__(self, model_id: Optional[str] = None, region: Optional[str] = None):
        self.model_id = model_id or settings.model.primary_model_id
        self.region = region or settings.model.region
        self.max_output_tokens = 3000  # 출력 토큰 제한
        
        try:
            self.bedrock_runtime = boto3.client(
                'bedrock-runtime',
                region_name=self.region
            )
            
            # 토큰 계산용 인코더 초기화 (안전 처리)
            if TIKTOKEN_AVAILABLE:
                try:
                    self.tokenizer = tiktoken.get_encoding("cl100k_base")
                    self.use_tiktoken = True
                except Exception as e:
                    print(f"tiktoken 초기화 실패: {e}. 대체 방법 사용.")
                    self.use_tiktoken = False
            else:
                self.use_tiktoken = False
            
            agent_logger.log_agent_action("ImprovedResponseAgent", "initialized", {"model_id": self.model_id})
        except Exception as e:
            agent_logger.log_error(e, "improved_response_agent_init")
            raise
    
    def _estimate_tokens(self, text: str) -> int:
        """토큰 수 추정 (tiktoken 사용 가능시 정확한 계산, 아니면 추정)"""
        if self.use_tiktoken:
            try:
                return len(self.tokenizer.encode(text))
            except Exception:
                pass
        
        # 대체 방법: 대략적인 토큰 수 추정
        # 영어: 평균 4자당 1토큰, 한국어: 평균 2자당 1토큰
        korean_chars = len(re.findall(r'[가-힣]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        other_chars = len(text) - korean_chars - english_chars
        
        estimated_tokens = (korean_chars // 2) + (english_chars // 4) + (other_chars // 3)
        return max(estimated_tokens, len(text.split()) // 2)  # 최소값 보장
    
    def generate_comprehensive_response(
        self,
        user_query: str,
        search_results: Dict[str, Any],
        analysis_result: Dict[str, Any],
        session: Optional[ChatSession] = None,
        system_prompt: Optional[str] = None,
        image_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        통합된 검색 결과를 바탕으로 포괄적 응답 생성 (3000 토큰 이내)
        """
        try:
            start_time = datetime.now()
            
            agent_logger.log_agent_action(
                "ImprovedResponseAgent",
                "comprehensive_response_start",
                {
                    "query_length": len(user_query),
                    "citation_count": len(search_results.get("citations", [])),
                    "primary_intent": analysis_result.get("primary_intent", "unknown")
                }
            )
            
            # 1단계: Citation 우선순위 정렬 및 선별
            prioritized_citations = self._prioritize_and_filter_citations(
                search_results.get("citations", []),
                analysis_result,
                user_query
            )
            
            # 2단계: 응답 구조 설계
            response_structure = self._design_response_structure(
                analysis_result,
                prioritized_citations
            )
            
            # 3단계: 토큰 예산 계산 및 할당
            token_budget = self._calculate_token_budget(
                user_query,
                prioritized_citations,
                system_prompt
            )
            
            # 4단계: 응답 생성 프롬프트 구성
            response_prompt = self._build_comprehensive_response_prompt(
                user_query,
                prioritized_citations,
                analysis_result,
                response_structure,
                token_budget,
                system_prompt,
                session
            )
            
            # 5단계: Claude 호출 및 응답 생성
            generated_response = self._call_claude_for_comprehensive_response(
                response_prompt,
                token_budget["max_output_tokens"],
                image_data
            )
            
            # 6단계: 응답 후처리 및 검증
            final_response = self._post_process_response(
                generated_response,
                prioritized_citations,
                analysis_result,
                search_results
            )
            
            # 처리 시간 계산
            processing_time = (datetime.now() - start_time).total_seconds()
            final_response["response_metadata"] = {
                "processing_time": processing_time,
                "token_usage": self._calculate_token_usage(final_response.get("content", "")),
                "citations_used": len(prioritized_citations),
                "response_structure": response_structure,
                "timestamp": start_time.isoformat()
            }
            
            agent_logger.log_agent_action(
                "ImprovedResponseAgent",
                "comprehensive_response_complete",
                {
                    "processing_time": processing_time,
                    "response_length": len(final_response.get("content", "")),
                    "token_count": final_response["response_metadata"]["token_usage"]["total_tokens"]
                }
            )
            
            return final_response
            
        except Exception as e:
            agent_logger.log_error(e, "comprehensive_response_generation")
            return self._get_fallback_response(user_query, str(e))
    
    def _prioritize_and_filter_citations(
        self,
        citations: List[Dict[str, Any]],
        analysis_result: Dict[str, Any],
        user_query: str
    ) -> List[Dict[str, Any]]:
        """Citation 우선순위 정렬 및 선별"""
        
        if not citations:
            return []
        
        # 의도 기반 점수 조정
        primary_intent = analysis_result.get("primary_intent", "")
        key_entities = analysis_result.get("search_priorities", {}).get("key_entities", [])
        
        # 각 Citation에 최종 점수 계산
        for citation in citations:
            base_score = citation.get("intent_adjusted_score", citation.get("confidence", 0.5))
            
            # 추가 점수 조정 요소들
            bonus_score = 0.0
            
            # 1. 검색 단계별 가중치
            source_stage = citation.get("source_stage", "primary")
            if source_stage == "primary":
                bonus_score += 0.1  # 1차 검색 결과 우대
            
            # 2. 문서 신뢰도 (파일명 기반)
            filename = citation.get("document_title", "")
            if any(keyword in filename.lower() for keyword in ["공식", "지침", "규정", "법령"]):
                bonus_score += 0.15
            
            # 3. 내용 길이 (적절한 길이의 내용 우대)
            preview_length = len(citation.get("preview", ""))
            if 100 <= preview_length <= 500:
                bonus_score += 0.05
            
            citation["final_priority_score"] = min(base_score + bonus_score, 1.0)
        
        # 점수 기준으로 정렬
        sorted_citations = sorted(
            citations,
            key=lambda x: (
                x.get("final_priority_score", 0),
                x.get("confidence", 0),
                -x.get("index", 999)
            ),
            reverse=True
        )
        
        # 상위 Citation 선별 (최대 20개)
        max_citations = min(20, len(sorted_citations))
        
        # 의도별 최소 Citation 수 보장
        intent_min_citations = {
            "절차_문의": 8,
            "규정_확인": 6,
            "기술_질문": 5,
            "일반_정보": 4,
            "비교_분석": 10,
            "문제_해결": 7
        }
        
        min_required = intent_min_citations.get(primary_intent, 5)
        final_count = max(min_required, min(max_citations, len(sorted_citations)))
        
        return sorted_citations[:final_count]
    
    def _design_response_structure(
        self,
        analysis_result: Dict[str, Any],
        citations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """응답 구조 설계"""
        
        primary_intent = analysis_result.get("primary_intent", "일반_정보")
        complexity = analysis_result.get("complexity", "보통")
        
        # 의도별 응답 구조 템플릿
        structure_templates = {
            "절차_문의": {
                "sections": ["직접_답변", "상세_절차", "주의사항", "관련_규정"],
                "emphasis": "step_by_step",
                "include_examples": True
            },
            "규정_확인": {
                "sections": ["직접_답변", "관련_규정", "적용_범위", "예외사항"],
                "emphasis": "accuracy",
                "include_examples": False
            },
            "기술_질문": {
                "sections": ["직접_답변", "기술_방법", "구현_예시", "참고사항"],
                "emphasis": "practical",
                "include_examples": True
            },
            "일반_정보": {
                "sections": ["직접_답변", "상세_설명", "참고사항"],
                "emphasis": "comprehensive",
                "include_examples": False
            },
            "비교_분석": {
                "sections": ["직접_답변", "비교_분석", "권장사항", "고려사항"],
                "emphasis": "comparison",
                "include_examples": True
            },
            "문제_해결": {
                "sections": ["직접_답변", "해결_방안", "단계별_조치", "예방책"],
                "emphasis": "solution",
                "include_examples": True
            }
        }
        
        base_structure = structure_templates.get(primary_intent, structure_templates["일반_정보"])
        
        # 복잡도에 따른 구조 조정
        if complexity == "단순":
            base_structure["sections"] = base_structure["sections"][:2]
        elif complexity == "복잡":
            if "추가_고려사항" not in base_structure["sections"]:
                base_structure["sections"].append("추가_고려사항")
        
        # Citation 수에 따른 조정
        citation_count = len(citations)
        if citation_count >= 10:
            base_structure["detailed_citations"] = True
        else:
            base_structure["detailed_citations"] = False
        
        return base_structure
    
    def _calculate_token_budget(
        self,
        user_query: str,
        citations: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> Dict[str, int]:
        """토큰 예산 계산 및 할당"""
        
        # 입력 토큰 계산
        input_tokens = 0
        
        # 사용자 쿼리 토큰
        input_tokens += self._estimate_tokens(user_query)
        
        # 시스템 프롬프트 토큰
        if system_prompt:
            input_tokens += self._estimate_tokens(system_prompt)
        
        # Citation 토큰 (예상)
        citation_text = ""
        for citation in citations:
            preview = citation.get("preview", "")[:300]  # 300자로 제한
            citation_text += f"[{citation.get('index', 0)}] {preview}\n"
        
        citation_tokens = self._estimate_tokens(citation_text)
        input_tokens += citation_tokens
        
        # 프롬프트 템플릿 토큰 (예상 500토큰)
        template_tokens = 500
        input_tokens += template_tokens
        
        # 출력 토큰 예산 계산
        max_total_tokens = 4000  # Claude의 컨텍스트 윈도우 고려
        available_output_tokens = min(
            self.max_output_tokens,
            max_total_tokens - input_tokens
        )
        
        # 안전 마진 (10%)
        safe_output_tokens = int(available_output_tokens * 0.9)
        
        return {
            "input_tokens": input_tokens,
            "citation_tokens": citation_tokens,
            "max_output_tokens": max(safe_output_tokens, 1000),  # 최소 1000토큰 보장
            "total_budget": max_total_tokens
        }
