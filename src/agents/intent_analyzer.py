"""
Intent Analyzer
사용자 쿼리의 의도를 상세 분석하고 추가 검색 키워드를 생성하는 모듈
"""

import boto3
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re

from config.settings import settings
from src.utils.logger import agent_logger


class IntentAnalyzer:
    """사용자 쿼리 의도 분석기"""
    
    def __init__(self, model_id: Optional[str] = None, region: Optional[str] = None):
        self.model_id = model_id or settings.model.primary_model_id
        self.region = region or settings.model.region
        
        try:
            self.bedrock_runtime = boto3.client(
                'bedrock-runtime',
                region_name=self.region
            )
            agent_logger.log_agent_action("IntentAnalyzer", "initialized", {"model_id": self.model_id})
        except Exception as e:
            agent_logger.log_error(e, "intent_analyzer_init")
            raise
    
    def analyze_user_intent(
        self, 
        query: str, 
        context: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        사용자 쿼리의 의도를 상세 분석
        
        Args:
            query: 사용자 쿼리
            context: 추가 컨텍스트 정보
            conversation_history: 대화 히스토리
            
        Returns:
            의도 분석 결과
        """
        try:
            start_time = datetime.now()
            
            # 프롬프트 구성
            analysis_prompt = self._build_intent_analysis_prompt(query, context, conversation_history)
            
            # Claude 호출
            response = self._call_claude_for_intent_analysis(analysis_prompt)
            
            # 응답 파싱
            intent_result = self._parse_intent_response(response)
            
            # 추가 검색 키워드 생성
            intent_result["additional_search_queries"] = self._generate_additional_search_queries(
                intent_result, query
            )
            
            # 메타데이터 추가
            intent_result["analysis_metadata"] = {
                "timestamp": start_time.isoformat(),
                "processing_time": (datetime.now() - start_time).total_seconds(),
                "model_used": self.model_id,
                "original_query": query
            }
            
            agent_logger.log_agent_action(
                "IntentAnalyzer",
                "intent_analysis_complete",
                {
                    "primary_intent": intent_result.get("primary_intent", "unknown"),
                    "requires_additional_search": intent_result.get("requires_additional_search", False),
                    "additional_queries_count": len(intent_result.get("additional_search_queries", []))
                }
            )
            
            return intent_result
            
        except Exception as e:
            agent_logger.log_error(e, "intent_analysis")
            return self._get_fallback_intent_analysis(query)
    
    def _build_intent_analysis_prompt(
        self, 
        query: str, 
        context: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """의도 분석용 프롬프트 구성"""
        
        # 대화 히스토리 컨텍스트 구성
        history_context = ""
        if conversation_history:
            recent_history = conversation_history[-3:]  # 최근 3개 대화만
            history_items = []
            for item in recent_history:
                role = item.get("role", "unknown")
                content = item.get("content", "")[:200]  # 200자로 제한
                history_items.append(f"{role}: {content}")
            history_context = f"\n\n이전 대화 맥락:\n" + "\n".join(history_items)
        
        # 추가 컨텍스트
        context_section = f"\n\n추가 컨텍스트:\n{context}" if context else ""
        
        prompt = f"""
사용자 쿼리를 분석하여 의도를 파악하고 추가 검색이 필요한지 판단하세요.

사용자 쿼리: "{query}"{history_context}{context_section}

다음 JSON 형태로 분석 결과를 제공하세요:

{{
    "primary_intent": "절차_문의|규정_확인|기술_질문|일반_정보|비교_분석|문제_해결",
    "secondary_intents": ["관련_절차", "예외_사항", "참고_자료"],
    "key_entities": ["핵심 개체명들"],
    "complexity_level": "단순|보통|복잡",
    "requires_additional_search": true/false,
    "search_focus_areas": ["검색해야 할 주요 영역들"],
    "confidence_score": 0.0-1.0
}}

분석 기준:
1. primary_intent 분류:
   - 절차_문의: 특정 절차나 프로세스에 대한 질문
   - 규정_확인: 규정, 기준, 법령 등에 대한 확인
   - 기술_질문: 기술적 방법이나 해결책 문의
   - 일반_정보: 일반적인 정보나 개념 설명 요청
   - 비교_분석: 여러 옵션이나 방법의 비교
   - 문제_해결: 특정 문제 상황의 해결 방안 문의

2. requires_additional_search 판단 기준:
   - 복잡한 절차나 다단계 프로세스 관련: true
   - 여러 규정이나 기준이 관련된 경우: true
   - 예외사항이나 특수 상황 포함: true
   - 단순한 정의나 개념 질문: false

3. search_focus_areas: 추가 검색이 필요한 구체적 영역들

JSON 형태로만 응답하세요.
"""
        return prompt
    
    def _call_claude_for_intent_analysis(self, prompt: str) -> str:
        """Claude를 호출하여 의도 분석 수행"""
        try:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "temperature": 0.1,  # 일관성 있는 분석을 위해 낮은 temperature
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body)
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
            
        except Exception as e:
            agent_logger.log_error(e, "claude_intent_analysis_call")
            raise
    
    def _parse_intent_response(self, response: str) -> Dict[str, Any]:
        """Claude 응답을 파싱하여 구조화된 데이터로 변환"""
        try:
            # JSON 추출 (```json 블록이 있는 경우 처리)
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # JSON 블록이 없으면 전체 응답에서 JSON 찾기
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise ValueError("JSON 형태의 응답을 찾을 수 없습니다")
            
            # JSON 파싱
            intent_data = json.loads(json_str)
            
            # 필수 필드 검증 및 기본값 설정
            validated_data = {
                "primary_intent": intent_data.get("primary_intent", "일반_정보"),
                "secondary_intents": intent_data.get("secondary_intents", []),
                "key_entities": intent_data.get("key_entities", []),
                "complexity_level": intent_data.get("complexity_level", "보통"),
                "requires_additional_search": intent_data.get("requires_additional_search", False),
                "search_focus_areas": intent_data.get("search_focus_areas", []),
                "confidence_score": intent_data.get("confidence_score", 0.7)
            }
            
            return validated_data
            
        except Exception as e:
            agent_logger.log_error(e, "intent_response_parsing")
            # 파싱 실패 시 기본값 반환
            return self._get_fallback_intent_analysis("")
    
    def _generate_additional_search_queries(
        self, 
        intent_result: Dict[str, Any], 
        original_query: str
    ) -> List[str]:
        """의도 분석 결과를 바탕으로 추가 검색 쿼리 생성"""
        
        if not intent_result.get("requires_additional_search", False):
            return []
        
        additional_queries = []
        key_entities = intent_result.get("key_entities", [])
        primary_intent = intent_result.get("primary_intent", "")
        search_focus_areas = intent_result.get("search_focus_areas", [])
        
        # 의도별 키워드 패턴 정의
        intent_patterns = {
            "절차_문의": ["절차", "단계", "프로세스", "방법", "순서"],
            "규정_확인": ["규정", "기준", "법령", "조항", "요구사항"],
            "기술_질문": ["기술", "방법", "해결책", "구현", "적용"],
            "비교_분석": ["비교", "차이점", "장단점", "선택", "기준"],
            "문제_해결": ["해결", "대응", "조치", "방안", "처리"]
        }
        
        # 1. 의도 기반 키워드 조합
        if primary_intent in intent_patterns:
            patterns = intent_patterns[primary_intent]
            for entity in key_entities[:3]:  # 상위 3개 엔티티만
                for pattern in patterns[:2]:  # 상위 2개 패턴만
                    query = f"{entity} {pattern}"
                    if query not in additional_queries:
                        additional_queries.append(query)
        
        # 2. 검색 포커스 영역 기반 쿼리
        for focus_area in search_focus_areas[:3]:
            if focus_area not in additional_queries:
                additional_queries.append(focus_area)
        
        # 3. 특수 패턴 추가
        for entity in key_entities[:2]:
            # 예외사항 관련
            exception_query = f"{entity} 예외사항"
            if exception_query not in additional_queries:
                additional_queries.append(exception_query)
            
            # 주의사항 관련
            caution_query = f"{entity} 주의사항"
            if caution_query not in additional_queries:
                additional_queries.append(caution_query)
        
        # 최대 5개로 제한
        return additional_queries[:5]
    
    def _get_fallback_intent_analysis(self, query: str) -> Dict[str, Any]:
        """분석 실패 시 기본 의도 분석 결과 반환"""
        return {
            "primary_intent": "일반_정보",
            "secondary_intents": [],
            "key_entities": self._extract_simple_entities(query),
            "complexity_level": "보통",
            "requires_additional_search": len(query) > 50,  # 긴 쿼리는 추가 검색 필요로 판단
            "search_focus_areas": [],
            "confidence_score": 0.3,
            "additional_search_queries": [],
            "analysis_metadata": {
                "timestamp": datetime.now().isoformat(),
                "processing_time": 0.1,
                "model_used": "fallback",
                "original_query": query,
                "fallback_reason": "intent_analysis_failed"
            }
        }
    
    def _extract_simple_entities(self, query: str) -> List[str]:
        """간단한 엔티티 추출 (fallback용)"""
        # 한글 명사 패턴 추출
        import re
        
        # 2-10글자 한글 단어 추출
        korean_words = re.findall(r'[가-힣]{2,10}', query)
        
        # 빈도 기반 필터링 (중복 제거)
        unique_words = list(set(korean_words))
        
        # 길이 기준 정렬 (긴 단어 우선)
        unique_words.sort(key=len, reverse=True)
        
        return unique_words[:5]
    
    def validate_intent_analysis(self, intent_result: Dict[str, Any]) -> bool:
        """의도 분석 결과 유효성 검증"""
        required_fields = [
            "primary_intent", "secondary_intents", "key_entities",
            "complexity_level", "requires_additional_search", "search_focus_areas"
        ]
        
        for field in required_fields:
            if field not in intent_result:
                return False
        
        # 값 유효성 검증
        valid_intents = ["절차_문의", "규정_확인", "기술_질문", "일반_정보", "비교_분석", "문제_해결"]
        if intent_result["primary_intent"] not in valid_intents:
            return False
        
        valid_complexity = ["단순", "보통", "복잡"]
        if intent_result["complexity_level"] not in valid_complexity:
            return False
        
        return True


# 전역 인스턴스
intent_analyzer = IntentAnalyzer()
