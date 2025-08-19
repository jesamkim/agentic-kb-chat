"""
Improved Response Agent - Safe Version
tiktoken 의존성을 안전하게 처리하는 완전한 Response Agent
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
        """통합된 검색 결과를 바탕으로 포괄적 응답 생성 (3000 토큰 이내)"""
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
            
            # Citation 우선순위 정렬 및 선별
            prioritized_citations = self._prioritize_and_filter_citations(
                search_results.get("citations", []),
                analysis_result,
                user_query
            )
            
            # 응답 구조 설계
            response_structure = self._design_response_structure(
                analysis_result,
                prioritized_citations
            )
            
            # 토큰 예산 계산
            token_budget = self._calculate_token_budget(
                user_query,
                prioritized_citations,
                system_prompt
            )
            
            # 응답 생성 프롬프트 구성
            response_prompt = self._build_comprehensive_response_prompt(
                user_query,
                prioritized_citations,
                analysis_result,
                response_structure,
                token_budget,
                system_prompt,
                session
            )
            
            # Claude 호출 및 응답 생성
            generated_response = self._call_claude_for_comprehensive_response(
                response_prompt,
                token_budget["max_output_tokens"],
                image_data
            )
            
            # 응답 후처리 및 검증
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
        
        primary_intent = analysis_result.get("primary_intent", "")
        key_entities = analysis_result.get("search_priorities", {}).get("key_entities", [])
        
        # 각 Citation에 최종 점수 계산
        for citation in citations:
            base_score = citation.get("intent_adjusted_score", citation.get("confidence", 0.5))
            bonus_score = 0.0
            
            # 검색 단계별 가중치
            source_stage = citation.get("source_stage", "primary")
            if source_stage == "primary":
                bonus_score += 0.1
            
            # 문서 신뢰도
            filename = citation.get("document_title", "")
            if any(keyword in filename.lower() for keyword in ["공식", "지침", "규정", "법령"]):
                bonus_score += 0.15
            
            # 내용 길이
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
        
        # 상위 Citation 선별
        intent_min_citations = {
            "절차_문의": 8, "규정_확인": 6, "기술_질문": 5,
            "일반_정보": 4, "비교_분석": 10, "문제_해결": 7
        }
        
        min_required = intent_min_citations.get(primary_intent, 5)
        final_count = max(min_required, min(20, len(sorted_citations)))
        
        return sorted_citations[:final_count]
    
    def _design_response_structure(
        self,
        analysis_result: Dict[str, Any],
        citations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """응답 구조 설계"""
        
        primary_intent = analysis_result.get("primary_intent", "일반_정보")
        complexity = analysis_result.get("complexity", "보통")
        
        structure_templates = {
            "절차_문의": {
                "sections": ["직접_답변", "상세_절차", "주의사항", "관련_규정"],
                "emphasis": "step_by_step"
            },
            "규정_확인": {
                "sections": ["직접_답변", "관련_규정", "적용_범위", "예외사항"],
                "emphasis": "accuracy"
            },
            "기술_질문": {
                "sections": ["직접_답변", "기술_방법", "구현_예시", "참고사항"],
                "emphasis": "practical"
            },
            "일반_정보": {
                "sections": ["직접_답변", "상세_설명", "참고사항"],
                "emphasis": "comprehensive"
            }
        }
        
        base_structure = structure_templates.get(primary_intent, structure_templates["일반_정보"])
        
        # 복잡도에 따른 조정
        if complexity == "단순":
            base_structure["sections"] = base_structure["sections"][:2]
        elif complexity == "복잡":
            if "추가_고려사항" not in base_structure["sections"]:
                base_structure["sections"].append("추가_고려사항")
        
        return base_structure
    
    def _calculate_token_budget(
        self,
        user_query: str,
        citations: List[Dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> Dict[str, int]:
        """토큰 예산 계산"""
        
        input_tokens = 0
        input_tokens += self._estimate_tokens(user_query)
        
        if system_prompt:
            input_tokens += self._estimate_tokens(system_prompt)
        
        # Citation 토큰
        citation_text = ""
        for citation in citations:
            preview = citation.get("preview", "")[:300]
            citation_text += f"[{citation.get('index', 0)}] {preview}\n"
        
        citation_tokens = self._estimate_tokens(citation_text)
        input_tokens += citation_tokens + 500  # 템플릿 토큰
        
        # 출력 토큰 예산
        max_total_tokens = 4000
        available_output_tokens = min(
            self.max_output_tokens,
            max_total_tokens - input_tokens
        )
        
        safe_output_tokens = int(available_output_tokens * 0.9)
        
        return {
            "input_tokens": input_tokens,
            "citation_tokens": citation_tokens,
            "max_output_tokens": max(safe_output_tokens, 1000),
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
        session: Optional[Any] = None
    ) -> str:
        """포괄적 응답 생성용 프롬프트 구성"""
        
        primary_intent = analysis_result.get("primary_intent", "일반_정보")
        complexity = analysis_result.get("complexity", "보통")
        max_tokens = token_budget["max_output_tokens"]
        
        # Citation 텍스트 구성
        citation_lines = []
        for i, citation in enumerate(citations, 1):
            filename = citation.get("document_title", f"문서_{i}")
            preview = citation.get("preview", "")[:250]
            confidence = citation.get("confidence", 0)
            citation_lines.append(f"[{i}] {filename} (신뢰도: {confidence:.1%})\n{preview}\n")
        
        citation_text = "\n".join(citation_lines)
        
        # 응답 구조 지침
        sections = response_structure.get("sections", ["직접_답변", "상세_설명"])
        structure_guide = "\n".join([f"{i}. {section.replace('_', ' ')}" for i, section in enumerate(sections, 1)])
        
        prompt = f"""
다음 정보를 바탕으로 사용자 질문에 대한 포괄적이고 정확한 답변을 생성하세요.

사용자 질문: "{user_query}"

질문 분석:
- 주요 의도: {primary_intent}
- 복잡도: {complexity}

참고 문서 정보:
{citation_text}

응답 구조:
{structure_guide}

중요한 제약사항:
1. 응답은 반드시 {max_tokens} 토큰 이내로 작성하세요
2. 모든 정보는 제공된 참고 문서에 기반해야 합니다
3. Citation 번호 [1], [2] 등을 사용하여 출처를 명시하세요
4. 한국어로 작성하되, 전문 용어는 정확히 사용하세요

응답을 시작하세요:
"""
        
        return prompt
    
    def _call_claude_for_comprehensive_response(
        self,
        prompt: str,
        max_tokens: int,
        image_data: Optional[str] = None
    ) -> str:
        """Claude를 호출하여 포괄적 응답 생성"""
        try:
            messages = []
            
            if image_data:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data
                            }
                        }
                    ]
                })
            else:
                messages.append({"role": "user", "content": prompt})
            
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": settings.model.temperature,
                "messages": messages
            }
            
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body)
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
            
        except Exception as e:
            agent_logger.log_error(e, "claude_comprehensive_response_call")
            raise
    
    def _post_process_response(
        self,
        generated_response: str,
        citations: List[Dict[str, Any]],
        analysis_result: Dict[str, Any],
        search_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """응답 후처리 및 검증"""
        
        try:
            # 토큰 수 검증
            token_count = self._estimate_tokens(generated_response)
            if token_count > self.max_output_tokens:
                generated_response = self._truncate_response(generated_response, self.max_output_tokens)
            
            # Citation 참조 검증
            validated_response, used_citations = self._validate_and_clean_citations(
                generated_response, citations
            )
            
            # 응답 품질 메트릭 계산
            quality_metrics = self._calculate_response_quality(
                validated_response, used_citations, analysis_result
            )
            
            return {
                "content": validated_response,
                "citations": used_citations,
                "status": "success",
                "metadata": {
                    "primary_intent": analysis_result.get("primary_intent", "unknown"),
                    "complexity_level": analysis_result.get("complexity", "보통"),
                    "total_citations_available": len(citations),
                    "citations_used": len(used_citations),
                    "search_quality": search_results.get("quality_metrics", {}),
                    "response_quality": quality_metrics,
                    "token_usage": self._calculate_token_usage(validated_response),
                    "has_images": self._detect_image_references(validated_response),
                    "response_sections": self._detect_response_sections(validated_response)
                }
            }
            
        except Exception as e:
            agent_logger.log_error(e, "response_post_processing")
            return {
                "content": generated_response,
                "citations": citations,
                "status": "partial_success",
                "error": f"후처리 중 오류: {str(e)}"
            }
    
    def _truncate_response(self, response: str, max_tokens: int) -> str:
        """응답을 토큰 제한에 맞게 축약"""
        sentences = re.split(r'(?<=[.!?])\s+', response)
        truncated_sentences = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)
            if current_tokens + sentence_tokens <= max_tokens * 0.95:
                truncated_sentences.append(sentence)
                current_tokens += sentence_tokens
            else:
                break
        
        truncated_response = ' '.join(truncated_sentences)
        if len(truncated_sentences) < len(sentences):
            truncated_response += "\n\n*[응답이 토큰 제한으로 인해 축약되었습니다]*"
        
        return truncated_response
    
    def _validate_and_clean_citations(self, response: str, citations: List[Dict[str, Any]]) -> tuple:
        """Citation 참조 검증 및 정리"""
        citation_pattern = r'\[(\d+)\]'
        used_citation_numbers = set(re.findall(citation_pattern, response))
        
        used_citations = []
        citation_mapping = {}
        
        new_index = 1
        for i, citation in enumerate(citations, 1):
            if str(i) in used_citation_numbers:
                citation_copy = citation.copy()
                citation_copy["index"] = new_index
                used_citations.append(citation_copy)
                citation_mapping[str(i)] = str(new_index)
                new_index += 1
        
        # Citation 번호 재매핑
        cleaned_response = response
        for original_num, new_num in citation_mapping.items():
            cleaned_response = cleaned_response.replace(f'[{original_num}]', f'[{new_num}]')
        
        return cleaned_response, used_citations
    
    def _calculate_response_quality(
        self, response: str, citations: List[Dict[str, Any]], analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """응답 품질 메트릭 계산"""
        
        response_length = len(response)
        length_score = 1.0 if 200 <= response_length <= 2500 else 0.7
        
        citation_count = len(citations)
        citation_score = min(citation_count / 5.0, 1.0)
        
        # 구조화 점수
        structure_indicators = [r'##?\s*[가-힣\w\s]+:', r'^\d+\.', r'^[-*]\s']
        structure_score = min(sum(0.3 for pattern in structure_indicators 
                                if re.search(pattern, response, re.MULTILINE)), 1.0)
        
        # 의도 충족도
        primary_intent = analysis_result.get("primary_intent", "")
        intent_keywords = {
            "절차_문의": ["단계", "절차", "순서", "방법"],
            "규정_확인": ["규정", "기준", "법령", "조항"],
            "기술_질문": ["방법", "기술", "해결", "구현"]
        }
        
        intent_score = 0.0
        if primary_intent in intent_keywords:
            keywords = intent_keywords[primary_intent]
            matched_keywords = sum(1 for keyword in keywords if keyword in response)
            intent_score = matched_keywords / len(keywords)
        
        overall_quality = (length_score * 0.2 + citation_score * 0.3 + 
                          structure_score * 0.2 + intent_score * 0.3)
        
        return {
            "overall_quality": round(overall_quality, 3),
            "length_score": round(length_score, 3),
            "citation_score": round(citation_score, 3),
            "structure_score": round(structure_score, 3),
            "intent_score": round(intent_score, 3),
            "response_length": response_length,
            "citations_used": citation_count
        }
    
    def _calculate_token_usage(self, text: str) -> Dict[str, int]:
        """토큰 사용량 계산"""
        tokens = self._estimate_tokens(text)
        return {
            "total_tokens": tokens,
            "character_count": len(text),
            "word_count": len(text.split()),
            "tokens_per_word": round(tokens / max(len(text.split()), 1), 2),
            "utilization_rate": round(tokens / self.max_output_tokens * 100, 1)
        }
    
    def _detect_image_references(self, response: str) -> bool:
        """응답에 이미지 참조가 있는지 감지"""
        image_indicators = ["이미지", "그림", "도표", "차트", "사진", "첨부", "시각", "도식", "그래프"]
        return any(indicator in response for indicator in image_indicators)
    
    def _detect_response_sections(self, response: str) -> List[str]:
        """응답의 섹션 구조 감지"""
        sections = []
        
        # 헤더 패턴 감지
        header_patterns = [
            r'##?\s*([가-힣\w\s]+):',
            r'^\*\*([가-힣\w\s]+)\*\*',
            r'^([가-힣\w\s]+):\s*$'
        ]
        
        for pattern in header_patterns:
            matches = re.findall(pattern, response, re.MULTILINE)
            sections.extend(matches)
        
        # 기본 섹션들 감지
        if "절차" in response or "단계" in response:
            sections.append("절차_설명")
        if "주의" in response or "유의" in response:
            sections.append("주의사항")
        if "참고" in response or "추가" in response:
            sections.append("참고사항")
        
        return list(set(sections))
    
    def _get_fallback_response(self, user_query: str, error_message: str) -> Dict[str, Any]:
        """응답 생성 실패 시 기본 응답"""
        fallback_content = f"""
죄송합니다. 질문에 대한 답변을 생성하는 중 오류가 발생했습니다.

**질문**: {user_query}
**오류 내용**: {error_message}

다시 질문해 주시거나, 질문을 더 구체적으로 작성해 주시면 도움을 드릴 수 있습니다.
"""
        
        return {
            "content": fallback_content,
            "citations": [],
            "status": "error",
            "error": error_message,
            "metadata": {
                "primary_intent": "unknown",
                "complexity_level": "unknown",
                "total_citations_available": 0,
                "citations_used": 0,
                "response_quality": {"overall_quality": 0.0},
                "token_usage": self._calculate_token_usage(fallback_content),
                "error_timestamp": datetime.now().isoformat()
            }
        }
    
    def enhance_response_with_context(
        self, response: Dict[str, Any], session: Optional[Any] = None, save_to_session: bool = True
    ) -> Dict[str, Any]:
        """응답에 컨텍스트 정보 추가 및 세션 저장"""
        try:
            if save_to_session and session:
                assistant_message = {
                    "role": "assistant",
                    "content": response.get("content", ""),
                    "timestamp": datetime.now(),
                    "metadata": response.get("metadata", {})
                }
                
                if hasattr(session, 'add_message'):
                    session.add_message(assistant_message)
            
            enhanced_response = response.copy()
            enhanced_response["context_metadata"] = {
                "session_saved": save_to_session and session is not None,
                "enhancement_timestamp": datetime.now().isoformat(),
                "agent_version": "improved_v1.0"
            }
            
            return enhanced_response
            
        except Exception as e:
            agent_logger.log_error(e, "response_context_enhancement")
            return response
