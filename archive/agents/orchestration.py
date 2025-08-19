"""
Orchestration Agent
사용자 쿼리를 분석하고 검색 전략을 수립하는 Agent
ReAct 패턴의 Thought 단계를 담당
"""

import boto3
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from config.settings import settings
from src.utils.logger import agent_logger
from src.utils.session import ChatSession, Message


class OrchestrationAgent:
    """사용자 쿼리 분석 및 검색 전략 수립 Agent"""
    
    def __init__(self, model_id: Optional[str] = None, region: Optional[str] = None):
        self.model_id = model_id or settings.model.primary_model_id
        self.region = region or settings.model.region
        
        try:
            self.bedrock_runtime = boto3.client(
                'bedrock-runtime',
                region_name=self.region
            )
            agent_logger.log_agent_action("OrchestrationAgent", "initialized", {"model_id": self.model_id})
        except Exception as e:
            agent_logger.log_error(e, "orchestration_agent_init")
            raise
    
    def analyze_query(
        self,
        user_query: str,
        session: Optional[ChatSession] = None,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        사용자 쿼리를 분석하고 검색 전략을 수립
        
        Args:
            user_query: 사용자 쿼리
            session: 채팅 세션 (컨텍스트 참조용)
            system_prompt: 시스템 프롬프트 (사용자 설정)
            
        Returns:
            분석 결과 및 검색 전략
        """
        try:
            agent_logger.log_agent_action(
                "OrchestrationAgent", 
                "analyze_query_start", 
                {"query_length": len(user_query)}
            )
            
            # 프롬프트 구성
            analysis_prompt = self._build_analysis_prompt(user_query, session, system_prompt)
            
            # Claude 모델 호출
            response = self._call_claude_model(analysis_prompt)
            
            # 응답 파싱
            analysis_result = self._parse_analysis_response(response, user_query)
            
            agent_logger.log_agent_action(
                "OrchestrationAgent",
                "analyze_query_complete",
                {
                    "search_strategy": analysis_result.get("search_strategy", "unknown"),
                    "query_count": len(analysis_result.get("search_queries", []))
                }
            )
            
            return analysis_result
            
        except Exception as e:
            agent_logger.log_error(e, "orchestration_analyze_query")
            # 실패 시 기본 전략 반환
            return self._get_fallback_strategy(user_query)
    
    def _build_analysis_prompt(
        self,
        user_query: str,
        session: Optional[ChatSession] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """분석용 프롬프트 구성 (sample.md 패턴 반영)"""
        
        # 기본 시스템 프롬프트
        default_system = """당신은 건설/건축 분야 전문 AI 어시스턴트입니다. 
사용자의 질문을 분석하여 Knowledge Base 검색에 최적화된 검색어를 생성하는 것이 주요 역할입니다.
실제 현장 상황을 법적 근거와 기술 기준에 연결하여 정확한 정보를 찾을 수 있도록 도와주세요."""
        
        system_content = system_prompt or default_system
        
        # 대화 컨텍스트 구성
        context_info = ""
        if session:
            recent_messages = session.get_recent_context(max_messages=5)
            if recent_messages:
                context_info = "\n\n=== 최근 대화 컨텍스트 ===\n"
                for msg in recent_messages[-3:]:  # 최근 3개 메시지만
                    if msg.role != "system":
                        context_info += f"{msg.role}: {msg.content[:100]}...\n"
        
        prompt = f"""{system_content}

{context_info}

=== 사용자 쿼리 분석 및 KB 검색 최적화 ===

사용자 질문: "{user_query}"

위 질문을 분석하여 Knowledge Base에서 정확한 정보를 찾을 수 있도록 최적화된 검색 전략을 수립해주세요.

다음 JSON 형태로 응답해주세요:

{{
    "query_analysis": {{
        "user_intent": "사용자가 알고 싶어하는 핵심 내용",
        "context_type": "현장상황|법규문의|기술질문|절차문의",
        "complexity": "단순|보통|복잡",
        "requires_legal_basis": true/false
    }},
    "search_strategy": {{
        "approach": "단일검색|다중검색|단계적검색",
        "primary_query": "가장 중요한 검색어 (KB 검색에 최적화)",
        "secondary_queries": [
            "보조 검색어 1",
            "보조 검색어 2"
        ],
        "reasoning": "검색 전략 선택 이유"
    }},
    "domain_context": {{
        "construction_category": "구조|시공|품질|안전|관리|설계|기타",
        "legal_framework": "건설기술진흥법|건축법|산업안전보건법|기타|해당없음",
        "technical_area": "콘크리트|철근|거푸집|품질관리|안전관리|기타",
        "priority_keywords": ["핵심키워드1", "핵심키워드2", "핵심키워드3"]
    }}
}}

=== 검색어 최적화 가이드라인 ===

**현장 상황 → 법적/기술적 근거 연결**
- 사용자의 현장 상황을 이해하고, 관련 법규나 기술 기준으로 연결
- 예시: "철거공사 품질관리" → "건설 현장 철거 공사 품질관리 계획 품질시험 계획 수립 의무"

**구체적이고 포괄적인 검색어 생성**
- 너무 구체적이면 결과가 없고, 너무 일반적이면 부정확
- 법조문, 시행령, 기술기준 등 다양한 관점에서 검색
- 동의어와 관련 용어를 포함하여 검색 범위 확장

**단계적 검색 전략**
- 복잡한 질문은 여러 단계로 나누어 검색
- 1단계: 기본 개념 및 법적 근거
- 2단계: 구체적 적용 기준
- 3단계: 실무 적용 방법

검색어는 Knowledge Base의 문서에서 실제로 사용될 가능성이 높은 용어로 구성해주세요."""
        
        return prompt
    
    def _call_claude_model(self, prompt: str) -> str:
        """Claude 모델 호출"""
        try:
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": settings.model.max_tokens,
                "temperature": settings.model.temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
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
            agent_logger.log_error(e, "orchestration_claude_call")
            raise
    
    def _parse_analysis_response(self, response: str, original_query: str) -> Dict[str, Any]:
        """분석 응답 파싱"""
        try:
            # JSON 추출 시도
            response_clean = response.strip()
            
            # JSON 블록 찾기
            if "```json" in response_clean:
                start = response_clean.find("```json") + 7
                end = response_clean.find("```", start)
                json_str = response_clean[start:end].strip()
            elif response_clean.startswith("{") and response_clean.endswith("}"):
                json_str = response_clean
            else:
                # JSON 형태 찾기 시도
                start = response_clean.find("{")
                end = response_clean.rfind("}") + 1
                if start >= 0 and end > start:
                    json_str = response_clean[start:end]
                else:
                    raise ValueError("JSON format not found")
            
            parsed_result = json.loads(json_str)
            
            # 필수 필드 검증 및 기본값 설정
            result = {
                "query_type": parsed_result.get("query_type", "단일검색"),
                "complexity": parsed_result.get("complexity", "보통"),
                "search_strategy": parsed_result.get("search_strategy", "직접검색"),
                "search_queries": parsed_result.get("search_queries", [original_query]),
                "reasoning": parsed_result.get("reasoning", "기본 검색 전략 적용"),
                "expected_content_types": parsed_result.get("expected_content_types", ["텍스트"]),
                "priority_keywords": parsed_result.get("priority_keywords", []),
                "original_query": original_query,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
            # 검색 쿼리가 비어있으면 원본 쿼리 사용
            if not result["search_queries"]:
                result["search_queries"] = [original_query]
            
            return result
            
        except Exception as e:
            agent_logger.log_error(e, "orchestration_parse_response")
            return self._get_fallback_strategy(original_query)
    
    def _get_fallback_strategy(self, user_query: str) -> Dict[str, Any]:
        """분석 실패 시 기본 전략 반환"""
        return {
            "query_type": "단일검색",
            "complexity": "보통",
            "search_strategy": "직접검색",
            "search_queries": [user_query],
            "reasoning": "쿼리 분석 실패로 기본 전략 적용",
            "expected_content_types": ["텍스트"],
            "priority_keywords": [],
            "original_query": user_query,
            "analysis_timestamp": datetime.now().isoformat(),
            "fallback": True
        }
    
    def refine_search_queries(
        self,
        analysis_result: Dict[str, Any],
        previous_results: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """
        이전 검색 결과를 바탕으로 검색 쿼리 개선
        
        Args:
            analysis_result: 초기 분석 결과
            previous_results: 이전 검색 결과들
            
        Returns:
            개선된 검색 쿼리 리스트
        """
        try:
            if not previous_results:
                return analysis_result["search_queries"]
            
            # 이전 결과 분석
            total_results = sum(len(result.get("citations", [])) for result in previous_results)
            
            if total_results == 0:
                # 결과가 없으면 더 일반적인 쿼리로 변경
                original_queries = analysis_result["search_queries"]
                refined_queries = []
                
                for query in original_queries:
                    # 키워드 추출 및 단순화
                    keywords = self._extract_keywords(query)
                    if len(keywords) > 2:
                        refined_queries.append(" ".join(keywords[:2]))
                    else:
                        refined_queries.append(query)
                
                agent_logger.log_agent_action(
                    "OrchestrationAgent",
                    "refine_queries_no_results",
                    {"original": len(original_queries), "refined": len(refined_queries)}
                )
                
                return refined_queries
            
            elif total_results < 3:
                # 결과가 적으면 관련 키워드 추가
                refined_queries = analysis_result["search_queries"].copy()
                
                # 우선순위 키워드 기반 추가 쿼리 생성
                priority_keywords = analysis_result.get("priority_keywords", [])
                if priority_keywords:
                    for keyword in priority_keywords[:2]:
                        refined_queries.append(f"{keyword} 관련 기준")
                
                agent_logger.log_agent_action(
                    "OrchestrationAgent",
                    "refine_queries_few_results",
                    {"total_results": total_results, "added_queries": len(refined_queries) - len(analysis_result["search_queries"])}
                )
                
                return refined_queries
            
            else:
                # 충분한 결과가 있으면 원본 쿼리 유지
                return analysis_result["search_queries"]
                
        except Exception as e:
            agent_logger.log_error(e, "orchestration_refine_queries")
            return analysis_result["search_queries"]
    
    def _extract_keywords(self, query: str) -> List[str]:
        """쿼리에서 핵심 키워드 추출 (간단한 구현)"""
        # 불용어 제거 및 키워드 추출
        stop_words = {"을", "를", "이", "가", "은", "는", "에", "에서", "으로", "로", "와", "과", "의", "도", "만", "까지", "부터", "하고", "하는", "해서", "해줘", "알려줘", "설명해줘", "하려고", "하는데"}
        
        words = query.split()
        keywords = []
        
        for word in words:
            # 조사 제거 처리
            clean_word = word
            if word.endswith("을") or word.endswith("를"):
                clean_word = word[:-1]
            elif word.endswith("이") or word.endswith("가"):
                clean_word = word[:-1]
            elif word.endswith("에서"):
                clean_word = word[:-2]
            elif word.endswith("으로") or word.endswith("에게"):
                clean_word = word[:-2]
            
            # 길이가 2 이상이고 불용어가 아닌 경우
            if len(clean_word) >= 2 and clean_word not in stop_words and word not in stop_words:
                keywords.append(clean_word)
        
        return keywords[:5]  # 최대 5개 키워드
    
    def get_search_priority(self, analysis_result: Dict[str, Any]) -> str:
        """검색 우선순위 결정"""
        complexity = analysis_result.get("complexity", "보통")
        query_type = analysis_result.get("query_type", "단일검색")
        
        if complexity == "복잡" or query_type == "복합검색":
            return "comprehensive"  # 포괄적 검색
        elif complexity == "단순" and query_type == "단일검색":
            return "focused"  # 집중 검색
        else:
            return "balanced"  # 균형 검색


# 전역 Orchestration Agent 인스턴스
orchestration_agent = OrchestrationAgent()
