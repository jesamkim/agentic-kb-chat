"""
Response Agent 나머지 메서드들 - 안전 처리 버전
"""

import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from config.settings import settings
from src.utils.logger import agent_logger


class ResponseAgentMethods:
    """Response Agent의 나머지 메서드들"""
    
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
    
    def _call_claude_for_comprehensive_response(
        self,
        prompt: str,
        max_tokens: int,
        image_data: Optional[str] = None
    ) -> str:
        """Claude를 호출하여 포괄적 응답 생성"""
        try:
            # 메시지 구성
            messages = []
            
            if image_data:
                # 이미지가 있는 경우
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
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
                # 텍스트만 있는 경우
                messages.append({
                    "role": "user",
                    "content": prompt
                })
            
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
            # 1. 토큰 수 검증
            token_count = self._estimate_tokens(generated_response)
            if token_count > self.max_output_tokens:
                # 토큰 수 초과 시 응답 축약
                generated_response = self._truncate_response(generated_response, self.max_output_tokens)
            
            # 2. Citation 참조 검증 및 정리
            validated_response, used_citations = self._validate_and_clean_citations(
                generated_response, 
                citations
            )
            
            # 3. 응답 품질 메트릭 계산
            quality_metrics = self._calculate_response_quality(
                validated_response,
                used_citations,
                analysis_result
            )
            
            # 4. 최종 응답 구성
            final_response = {
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
            
            return final_response
            
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
        
        # 문장 단위로 분할
        sentences = re.split(r'(?<=[.!?])\s+', response)
        
        truncated_sentences = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)
            
            if current_tokens + sentence_tokens <= max_tokens * 0.95:  # 5% 마진
                truncated_sentences.append(sentence)
                current_tokens += sentence_tokens
            else:
                break
        
        truncated_response = ' '.join(truncated_sentences)
        
        # 축약 표시 추가
        if len(truncated_sentences) < len(sentences):
            truncated_response += "\n\n*[응답이 토큰 제한으로 인해 축약되었습니다]*"
        
        return truncated_response
    
    def _validate_and_clean_citations(
        self, 
        response: str, 
        citations: List[Dict[str, Any]]
    ) -> tuple:
        """Citation 참조 검증 및 정리"""
        
        # 응답에서 사용된 Citation 번호 추출
        citation_pattern = r'\[(\d+)\]'
        used_citation_numbers = set(re.findall(citation_pattern, response))
        
        # 사용된 Citation만 필터링
        used_citations = []
        citation_mapping = {}  # 원본 번호 -> 새 번호 매핑
        
        new_index = 1
        for i, citation in enumerate(citations, 1):
            if str(i) in used_citation_numbers:
                citation_copy = citation.copy()
                citation_copy["index"] = new_index
                citation_copy["original_index"] = i
                used_citations.append(citation_copy)
                citation_mapping[str(i)] = str(new_index)
                new_index += 1
        
        # 응답에서 Citation 번호 재매핑
        cleaned_response = response
        for original_num, new_num in citation_mapping.items():
            cleaned_response = cleaned_response.replace(f'[{original_num}]', f'[{new_num}]')
        
        # 사용되지 않은 Citation 참조 제거
        for num in used_citation_numbers:
            if num not in citation_mapping:
                cleaned_response = cleaned_response.replace(f'[{num}]', '')
        
        return cleaned_response, used_citations
    
    def _calculate_response_quality(
        self,
        response: str,
        citations: List[Dict[str, Any]],
        analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """응답 품질 메트릭 계산"""
        
        # 1. 길이 적절성
        response_length = len(response)
        length_score = 1.0
        if response_length < 200:
            length_score = 0.5  # 너무 짧음
        elif response_length > 2500:
            length_score = 0.8  # 너무 길 수 있음
        
        # 2. Citation 활용도
        citation_count = len(citations)
        citation_score = min(citation_count / 5.0, 1.0)  # 5개 이상이면 만점
        
        # 3. 구조화 점수
        structure_indicators = [
            r'##?\s*[가-힣\w\s]+:',  # 섹션 헤더
            r'^\d+\.',  # 번호 목록
            r'^[-*]\s',  # 불릿 목록
            r'```',  # 코드 블록
            r'\|.*\|'  # 테이블
        ]
        
        structure_score = 0.0
        for pattern in structure_indicators:
            if re.search(pattern, response, re.MULTILINE):
                structure_score += 0.2
        structure_score = min(structure_score, 1.0)
        
        # 4. 의도 충족도
        primary_intent = analysis_result.get("primary_intent", "")
        intent_keywords = {
            "절차_문의": ["단계", "절차", "순서", "방법"],
            "규정_확인": ["규정", "기준", "법령", "조항"],
            "기술_질문": ["방법", "기술", "해결", "구현"],
            "일반_정보": ["정보", "설명", "개념"],
            "비교_분석": ["비교", "차이", "장단점"],
            "문제_해결": ["해결", "방안", "조치"]
        }
        
        intent_score = 0.0
        if primary_intent in intent_keywords:
            keywords = intent_keywords[primary_intent]
            matched_keywords = sum(1 for keyword in keywords if keyword in response)
            intent_score = matched_keywords / len(keywords)
        
        # 5. 전체 품질 점수
        overall_quality = (
            length_score * 0.2 +
            citation_score * 0.3 +
            structure_score * 0.2 +
            intent_score * 0.3
        )
        
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
        
        image_indicators = [
            "이미지", "그림", "도표", "차트", "사진",
            "첨부", "시각", "도식", "그래프"
        ]
        
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
        
        return list(set(sections))  # 중복 제거
    
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
                "response_quality": {
                    "overall_quality": 0.0,
                    "length_score": 0.0,
                    "citation_score": 0.0,
                    "structure_score": 0.0,
                    "intent_score": 0.0
                },
                "token_usage": self._calculate_token_usage(fallback_content),
                "error_timestamp": datetime.now().isoformat()
            }
        }
    
    def enhance_response_with_context(
        self,
        response: Dict[str, Any],
        session: Optional[Any] = None,
        save_to_session: bool = True
    ) -> Dict[str, Any]:
        """응답에 컨텍스트 정보 추가 및 세션 저장"""
        
        try:
            # 세션에 응답 저장
            if save_to_session and session:
                assistant_message = {
                    "role": "assistant",
                    "content": response.get("content", ""),
                    "timestamp": datetime.now(),
                    "metadata": response.get("metadata", {})
                }
                
                if hasattr(session, 'add_message'):
                    session.add_message(assistant_message)
            
            # 컨텍스트 메타데이터 추가
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
