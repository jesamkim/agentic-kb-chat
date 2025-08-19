"""
Improved Response Agent
3000 토큰 제한과 통합 응답 생성 기능이 포함된 개선된 Response Agent
"""

import boto3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import tiktoken

from config.settings import settings
from src.utils.logger import agent_logger
from src.utils.session import ChatSession, Message
from src.utils.citation import CitationCollection, CitationProcessor
from src.utils.s3_utils import batch_enhance_citations_with_s3_info


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
            # 토큰 계산용 인코더 초기화
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
            agent_logger.log_agent_action("ImprovedResponseAgent", "initialized", {"model_id": self.model_id})
        except Exception as e:
            agent_logger.log_error(e, "improved_response_agent_init")
            raise
    
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
        
        Args:
            user_query: 원본 사용자 쿼리
            search_results: 개선된 Action Agent의 검색 결과
            analysis_result: 개선된 Orchestration Agent의 분석 결과
            session: 채팅 세션
            system_prompt: 시스템 프롬프트
            image_data: 이미지 데이터 (base64)
            
        Returns:
            최종 응답 결과
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
        
        # 의도 기반 점수 조정 (이미 Action Agent에서 수행되었지만 재확인)
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
            # 단순한 경우 섹션 축소
            base_structure["sections"] = base_structure["sections"][:2]
        elif complexity == "복잡":
            # 복잡한 경우 추가 섹션
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
        input_tokens += len(self.tokenizer.encode(user_query))
        
        # 시스템 프롬프트 토큰
        if system_prompt:
            input_tokens += len(self.tokenizer.encode(system_prompt))
        
        # Citation 토큰 (예상)
        citation_text = ""
        for citation in citations:
            preview = citation.get("preview", "")[:300]  # 300자로 제한
            citation_text += f"[{citation.get('index', 0)}] {preview}\n"
        
        citation_tokens = len(self.tokenizer.encode(citation_text))
        input_tokens += citation_tokens
        
        # 프롬프트 템플릿 토큰 (예상 500토큰)
        template_tokens = 500
        input_tokens += template_tokens
        
        # 출력 토큰 예산 계산 (최대 3000토큰에서 입력 토큰 제외)
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
            "max_output_tokens": safe_output_tokens,
            "total_budget": max_total_tokens
        }
    
    def _build_comprehensive_response_prompt(
        self,
        user_query: str,
        citations: List[Dict[str, Any]],
        analysis_result: Dict[str, Any],
        response_structure: Dict[str, Any],
        token_budget: Dict[str, int],
        system_prompt: Optional[str] = None,
        session: Optional[ChatSession] = None
    ) -> str:
        """포괄적 응답 생성용 프롬프트 구성"""
        
        # 기본 정보
        primary_intent = analysis_result.get("primary_intent", "일반_정보")
        complexity = analysis_result.get("complexity", "보통")
        max_tokens = token_budget["max_output_tokens"]
        
        # Citation 텍스트 구성
        citation_text = self._format_citations_for_prompt(citations)
        
        # 대화 컨텍스트
        conversation_context = ""
        if session and hasattr(session, 'messages') and session.messages:
            recent_messages = session.messages[-4:]  # 최근 4개 메시지
            context_parts = []
            for msg in recent_messages:
                if hasattr(msg, 'role') and hasattr(msg, 'content'):
                    content = msg.content[:150]  # 150자로 제한
                    context_parts.append(f"{msg.role}: {content}")
            if context_parts:
                conversation_context = f"\n\n이전 대화 맥락:\n" + "\n".join(context_parts)
        
        # 시스템 프롬프트 섹션
        system_section = ""
        if system_prompt:
            system_section = f"\n\n사용자 지정 지침:\n{system_prompt[:200]}"
        
        # 응답 구조 지침
        sections = response_structure.get("sections", ["직접_답변", "상세_설명"])
        structure_guide = self._generate_structure_guide(sections, primary_intent)
        
        prompt = f"""
다음 정보를 바탕으로 사용자 질문에 대한 포괄적이고 정확한 답변을 생성하세요.

사용자 질문: "{user_query}"

질문 분석:
- 주요 의도: {primary_intent}
- 복잡도: {complexity}
- 추가 검색 수행됨: {analysis_result.get('requires_additional_search', False)}

참고 문서 정보:
{citation_text}

{conversation_context}{system_section}

응답 작성 지침:
{structure_guide}

중요한 제약사항:
1. 응답은 반드시 {max_tokens} 토큰 이내로 작성하세요
2. 모든 정보는 제공된 참고 문서에 기반해야 합니다
3. Citation 번호 [1], [2] 등을 사용하여 출처를 명시하세요
4. 불확실한 정보는 추측하지 말고 "문서에서 확인되지 않음"으로 표시하세요
5. 한국어로 작성하되, 전문 용어는 정확히 사용하세요

응답을 시작하세요:
"""
        
        return prompt
    
    def _format_citations_for_prompt(self, citations: List[Dict[str, Any]]) -> str:
        """프롬프트용 Citation 텍스트 포맷팅"""
        
        citation_lines = []
        for i, citation in enumerate(citations, 1):
            filename = citation.get("document_title", f"문서_{i}")
            preview = citation.get("preview", "")[:250]  # 250자로 제한
            confidence = citation.get("confidence", 0)
            
            citation_line = f"[{i}] {filename} (신뢰도: {confidence:.1%})\n{preview}\n"
            citation_lines.append(citation_line)
        
        return "\n".join(citation_lines)
    
    def _generate_structure_guide(self, sections: List[str], primary_intent: str) -> str:
        """응답 구조 가이드 생성"""
        
        section_descriptions = {
            "직접_답변": "질문에 대한 핵심적이고 직접적인 답변 (2-3문장)",
            "상세_절차": "단계별 절차나 프로세스 설명 (번호나 순서 포함)",
            "상세_설명": "개념이나 내용에 대한 자세한 설명",
            "주의사항": "중요한 주의점이나 제한사항",
            "관련_규정": "관련된 규정이나 기준 사항",
            "적용_범위": "규정이나 기준의 적용 범위",
            "예외사항": "일반 원칙의 예외 상황들",
            "기술_방법": "구체적인 기술적 방법이나 해결책",
            "구현_예시": "실제 구현이나 적용 예시",
            "참고사항": "추가로 알아두면 좋은 정보",
            "비교_분석": "여러 옵션이나 방법의 비교",
            "권장사항": "추천하는 방법이나 접근법",
            "고려사항": "결정 시 고려해야 할 요소들",
            "해결_방안": "문제에 대한 구체적 해결 방안",
            "단계별_조치": "문제 해결을 위한 단계별 조치",
            "예방책": "문제 예방을 위한 방법들",
            "추가_고려사항": "기타 중요한 고려사항들"
        }
        
        guide_lines = []
        for i, section in enumerate(sections, 1):
            description = section_descriptions.get(section, "관련 정보")
            guide_lines.append(f"{i}. {section.replace('_', ' ')}: {description}")
        
        # 의도별 특별 지침
        special_instructions = {
            "절차_문의": "절차는 명확한 순서와 단계로 구성하세요.",
            "규정_확인": "규정 내용은 정확하고 구체적으로 인용하세요.",
            "기술_질문": "기술적 내용은 실용적이고 구현 가능하도록 설명하세요.",
            "비교_분석": "비교 항목들을 표나 목록으로 정리하세요.",
            "문제_해결": "해결 방안은 우선순위와 함께 제시하세요."
        }
        
        guide = "\n".join(guide_lines)
        if primary_intent in special_instructions:
            guide += f"\n\n특별 지침: {special_instructions[primary_intent]}"
        
        return guide
