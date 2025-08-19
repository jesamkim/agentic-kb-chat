"""
Response Agent
수집된 정보를 통합하여 최종 응답을 생성하는 Agent
ReAct 패턴의 Observation 및 최종 응답 생성을 담당
"""

import boto3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from config.settings import settings
from src.utils.logger import agent_logger
from src.utils.session import ChatSession, Message
from src.utils.citation import CitationCollection, CitationProcessor
from src.utils.s3_utils import batch_enhance_citations_with_s3_info


class ResponseAgent:
    """정보 통합 및 최종 응답 생성 Agent"""
    
    def __init__(self, model_id: Optional[str] = None, region: Optional[str] = None):
        self.model_id = model_id or settings.model.primary_model_id
        self.region = region or settings.model.region
        
        try:
            self.bedrock_runtime = boto3.client(
                'bedrock-runtime',
                region_name=self.region
            )
            agent_logger.log_agent_action("ResponseAgent", "initialized", {"model_id": self.model_id})
        except Exception as e:
            agent_logger.log_error(e, "response_agent_init")
            raise
    
    def generate_response(
        self,
        user_query: str,
        search_results: Dict[str, Any],
        analysis_result: Dict[str, Any],
        session: Optional[ChatSession] = None,
        system_prompt: Optional[str] = None,
        image_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        검색 결과를 바탕으로 최종 응답 생성
        
        Args:
            user_query: 원본 사용자 쿼리
            search_results: Action Agent의 검색 결과
            analysis_result: Orchestration Agent의 분석 결과
            session: 채팅 세션
            system_prompt: 시스템 프롬프트
            
        Returns:
            최종 응답 및 Citation 정보
        """
        try:
            agent_logger.log_agent_action(
                "ResponseAgent",
                "generate_response_start",
                {
                    "query_length": len(user_query),
                    "citation_count": len(search_results.get("citations", []))
                }
            )
            
            # Citation 정보 처리
            citations = search_results.get("citations", [])
            
            # S3 이미지 정보 향상 (presigned URL 등)
            enhanced_citations = batch_enhance_citations_with_s3_info(citations)
            
            # 응답 생성 프롬프트 구성
            response_prompt = self._build_response_prompt(
                user_query,
                enhanced_citations,
                analysis_result,
                session,
                system_prompt
            )
            
            # Claude 모델 호출하여 응답 생성 (이미지 포함)
            generated_response = self._call_claude_model(response_prompt, image_data)
            
            # Citation과 응답 통합
            final_response = self._integrate_response_with_citations(
                generated_response,
                enhanced_citations,
                search_results
            )
            
            agent_logger.log_agent_action(
                "ResponseAgent",
                "generate_response_complete",
                {
                    "response_length": len(final_response.get("content", "")),
                    "citation_count": len(final_response.get("citations", []))
                }
            )
            
            return final_response
            
        except Exception as e:
            agent_logger.log_error(e, "response_generate_response")
            return self._get_fallback_response(user_query, search_results)
    
    def _build_response_prompt(
        self,
        user_query: str,
        citations: List[Dict[str, Any]],
        analysis_result: Dict[str, Any],
        session: Optional[ChatSession] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """응답 생성용 프롬프트 구성 (sample.md 패턴 반영)"""
        
        # 기본 시스템 프롬프트
        default_system = """당신은 건설/건축 분야 전문 AI 어시스턴트입니다. 
제공된 Knowledge Base 문서를 바탕으로 법적 근거와 기술적 기준을 포함한 정확하고 실무적인 답변을 제공합니다.
현장 상황에 대한 질문을 관련 법규와 기준에 연결하여 체계적으로 답변하는 것이 주요 역할입니다."""
        
        system_content = system_prompt or default_system
        
        # 대화 컨텍스트 구성
        context_info = ""
        if session:
            recent_messages = session.get_recent_context(max_messages=3)
            if recent_messages:
                context_info = "\n\n=== 대화 컨텍스트 ===\n"
                for msg in recent_messages:
                    if msg.role != "system":
                        context_info += f"{msg.role}: {msg.content[:150]}...\n"
        
        # Citation 정보 구성 (더 상세하게)
        citation_content = ""
        if citations:
            citation_content = "\n\n=== Knowledge Base 검색 결과 ===\n"
            for i, citation in enumerate(citations[:10], 1):  # 최대 10개
                citation_content += f"\n[참고문서 {i}]\n"
                citation_content += f"제목: {citation.get('title', 'Unknown')}\n"
                citation_content += f"내용: {citation.get('preview', '')[:400]}...\n"
                
                # 이미지 정보 포함
                if citation.get('has_images') and citation.get('images'):
                    citation_content += f"관련 이미지: {len(citation['images'])}개\n"
                    for img in citation['images'][:2]:  # 최대 2개 이미지 정보
                        if img.get('alt_text'):
                            citation_content += f"  - {img['alt_text']}\n"
                
                citation_content += f"신뢰도: {citation.get('confidence', 0):.2f}\n"
                citation_content += "---\n"
        
        # 분석 결과 정보
        analysis_info = ""
        if analysis_result:
            query_analysis = analysis_result.get("query_analysis", {})
            domain_context = analysis_result.get("domain_context", {})
            
            analysis_info = f"""
=== 질문 분석 결과 ===
사용자 의도: {query_analysis.get('user_intent', '정보 요청')}
질문 유형: {query_analysis.get('context_type', '일반')}
건설 분야: {domain_context.get('construction_category', '일반')}
법적 근거 필요: {query_analysis.get('requires_legal_basis', False)}
핵심 키워드: {', '.join(domain_context.get('priority_keywords', []))}
"""
        
        prompt = f"""{system_content}

{context_info}

{citation_content}

{analysis_info}

=== 사용자 질문 ===
{user_query}

=== 답변 작성 지침 (sample.md 패턴 적용) ===

**답변 작성 시 필수 요구사항:**
- 제공된 참고문서의 정보를 사용할 때는 반드시 [1], [2], [3] 형태로 Citation 번호를 표시하세요
- 법령, 기준, 수치, 절차를 언급할 때마다 해당하는 Citation 번호를 포함하세요
- Citation 없는 일반적인 설명은 최소화하고, 문서 기반 정보를 우선하세요

답변 예시:
"건설기술 진흥법 제55조에 따르면 품질관리계획을 수립해야 합니다[1]. 구체적으로는 다음과 같은 기준을 적용합니다[2]:"

1. **질문 확인 및 개요**
   - 사용자의 현장 상황을 이해했음을 보여주는 도입부
   - 예시: "제공해주신 질문에 대해 [현장상황]에서의 [핵심주제]에 관한 정보를 알려드리겠습니다."

2. **법적 근거 및 기본 원칙** (해당하는 경우)
   - 관련 법령과 조항을 명시하고 반드시 Citation 번호 포함
   - 예시: "건설기술 진흥법 제55조(건설공사의 품질관리)에 따르면...[1]"
   - **중요**: 모든 법령, 기준, 수치 언급 시 반드시 [숫자] 형태로 Citation 표시

3. **구체적 적용 기준**
   - 사용자 상황에 적용되는 구체적 기준 제시하고 Citation 포함
   - 수치, 조건, 절차 등을 명확히 기술하며 출처 표시
   - 예시: "다음과 같은 공사가 품질관리계획 수립 대상입니다[2]:"

4. **현장 적용 방법**
   - 사용자의 구체적 상황(철거공사 등)에 대한 적용 방법
   - 예외 사항이나 특별 고려사항 포함

5. **결론 및 권고사항**
   - 명확한 결론 제시
   - 추가 확인이 필요한 사항 안내
   - 실무적 조언 포함

**작성 원칙:**
- Knowledge Base 문서의 내용을 적극 활용하되, 자연스럽게 통합
- 법조문이나 기준을 인용할 때는 정확한 출처 표시
- 사용자의 현장 상황을 고려한 실무적 답변
제공된 참고문서를 바탕으로 위 구조에 따라 체계적이고 실무적인 답변을 작성해주세요."""
        
        return prompt
    
    def _call_claude_model(self, prompt: str, image_data: Optional[str] = None) -> str:
        """Claude 모델 호출하여 응답 생성 (이미지 지원)"""
        try:
            # 메시지 내용 구성
            if image_data:
                # 이미지가 있는 경우 멀티모달 메시지 구성
                content = [
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
            else:
                # 텍스트만 있는 경우
                content = prompt
            
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": settings.model.max_tokens,
                "temperature": settings.model.temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ]
            }
            
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
            
        except Exception as e:
            agent_logger.log_error(e, "response_claude_call")
            raise
    
    def _integrate_response_with_citations(
        self,
        generated_response: str,
        citations: List[Dict[str, Any]],
        search_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """생성된 응답과 Citation 정보 통합"""
        try:
            # Citation 번호 처리 (다양한 패턴 지원)
            enhanced_response = generated_response
            
            # 1. [문서 N] 형태를 [N]으로 변경
            for i, citation in enumerate(citations[:30], 1):
                enhanced_response = enhanced_response.replace(f"[문서 {i}]", f"[{i}]")
                enhanced_response = enhanced_response.replace(f"[참고문서 {i}]", f"[{i}]")
                enhanced_response = enhanced_response.replace(f"[참고 {i}]", f"[{i}]")
            
            # 2. Citation이 없는 경우 자동으로 추가 (첫 번째 Citation만)
            if citations and "[1]" not in enhanced_response and "[문서" not in enhanced_response:
                # 첫 번째 문장 끝에 Citation 추가
                sentences = enhanced_response.split('.')
                if len(sentences) > 1:
                    sentences[0] = sentences[0] + "[1]"
                    enhanced_response = '.'.join(sentences)
            
            # 3. 강제로 Citation 번호 추가 (개발용 - 나중에 제거 가능)
            if citations and not any(f"[{i}]" in enhanced_response for i in range(1, min(len(citations)+1, 6))):
                # 응답 끝에 참고 문서 정보 추가
                enhanced_response += f"\n\n*참고: 위 내용은 제공된 문서 자료를 바탕으로 작성되었습니다.[1]*"
            
            # 최종 응답 구성
            final_response = {
                "content": enhanced_response,
                "citations": citations,
                "metadata": {
                    "response_length": len(enhanced_response),
                    "citation_count": len(citations),
                    "has_images": any(c.get("has_images", False) for c in citations),
                    "search_time": search_results.get("search_time", 0),
                    "rerank_time": search_results.get("rerank_time", 0),
                    "total_time": search_results.get("execution_time", 0),
                    "generation_timestamp": datetime.now().isoformat()
                },
                "search_metadata": search_results.get("metadata", {}),
                "status": "success"
            }
            
            return final_response
            
        except Exception as e:
            agent_logger.log_error(e, "response_integrate_citations")
            return {
                "content": generated_response,
                "citations": citations,
                "status": "partial_success",
                "error": str(e)
            }
    
    def _get_fallback_response(
        self,
        user_query: str,
        search_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """응답 생성 실패 시 기본 응답 반환 (KB 검색 결과 기반)"""
        citations = search_results.get("citations", [])
        
        if citations:
            fallback_content = f"""제공된 문서 정보를 바탕으로 답변드리겠습니다.

다음 관련 문서들을 참고하시기 바랍니다:

"""
            for i, citation in enumerate(citations[:5], 1):
                fallback_content += f"[{i}] {citation.get('title', 'Unknown Document')}\n"
                preview = citation.get('preview', '')
                if preview:
                    fallback_content += f"   {preview[:200]}...\n\n"
                else:
                    fallback_content += f"   (문서 내용 미리보기 없음)\n\n"
            
            fallback_content += "더 구체적인 정보를 위해서는 위 문서들을 직접 확인하시거나, 관련 전문가에게 문의하시기 바랍니다."
        else:
            fallback_content = f"""죄송합니다. 현재 Knowledge Base에서 '{user_query}'와 관련된 구체적인 문서를 찾을 수 없습니다.

다음과 같은 방법을 시도해보시기 바랍니다:

1. 더 구체적인 키워드로 다시 질문해주세요
2. 질문을 세분화해서 나누어 질문해주세요
3. 관련 기관이나 전문가에게 직접 문의하시기 바랍니다

정확한 정보 제공을 위해 문서 기반 답변만을 제공하고 있어 이런 제한이 있는 점 양해 부탁드립니다."""
        
        return {
            "content": fallback_content,
            "citations": citations,
            "status": "no_relevant_documents" if not citations else "fallback",
            "metadata": {
                "fallback_reason": "no_kb_results" if not citations else "response_generation_failed",
                "generation_timestamp": datetime.now().isoformat(),
                "search_attempted": True
            }
        }
    
    def enhance_response_with_context(
        self,
        response: Dict[str, Any],
        session: ChatSession,
        save_to_session: bool = True
    ) -> Dict[str, Any]:
        """
        세션 컨텍스트를 고려하여 응답 향상
        
        Args:
            response: 기본 응답
            session: 채팅 세션
            save_to_session: 세션에 저장할지 여부
            
        Returns:
            향상된 응답
        """
        try:
            # 세션에 메시지 저장
            if save_to_session:
                # 어시스턴트 응답 메시지 생성
                from src.utils.citation import CitationCollection
                citations_collection = CitationCollection()
                
                # Citation 정보를 CitationCollection으로 변환
                for citation_data in response.get("citations", []):
                    try:
                        from src.utils.citation import Citation
                        citation = Citation(
                            id=citation_data.get("id", ""),
                            document_uri=citation_data.get("uri", ""),
                            document_title=citation_data.get("title", ""),
                            chunk_text=citation_data.get("preview", ""),
                            confidence_score=citation_data.get("confidence", 0.0)
                        )
                        citations_collection.add_citation(citation)
                    except Exception:
                        continue
                
                assistant_message = Message.create_assistant_message(
                    response["content"],
                    citations=citations_collection
                )
                
                session.add_message(assistant_message)
                
                agent_logger.log_agent_action(
                    "ResponseAgent",
                    "response_saved_to_session",
                    {"session_id": session.session_id[:8]}
                )
            
            # 응답에 세션 정보 추가
            enhanced_response = response.copy()
            enhanced_response["session_info"] = {
                "session_id": session.session_id,
                "message_count": len(session.messages),
                "last_activity": session.last_activity.isoformat()
            }
            
            return enhanced_response
            
        except Exception as e:
            agent_logger.log_error(e, "response_enhance_with_context")
            return response


# 전역 Response Agent 인스턴스
response_agent = ResponseAgent()
