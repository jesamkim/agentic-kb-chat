"""
Improved Orchestration Agent
의도 분석 기능이 통합된 개선된 오케스트레이션 Agent
"""

import boto3
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from config.settings import settings
from src.utils.logger import agent_logger
from src.utils.session import ChatSession, Message
from src.agents.intent_analyzer import intent_analyzer


class ImprovedOrchestrationAgent:
    """개선된 오케스트레이션 Agent - 의도 분석 통합"""
    
    def __init__(self, model_id: Optional[str] = None, region: Optional[str] = None):
        self.model_id = model_id or settings.model.primary_model_id
        self.region = region or settings.model.region
        self.intent_analyzer = intent_analyzer
        
        try:
            self.bedrock_runtime = boto3.client(
                'bedrock-runtime',
                region_name=self.region
            )
            agent_logger.log_agent_action("ImprovedOrchestrationAgent", "initialized", {"model_id": self.model_id})
        except Exception as e:
            agent_logger.log_error(e, "improved_orchestration_agent_init")
            raise
    
    def analyze_query_with_intent(
        self,
        user_query: str,
        session: Optional[ChatSession] = None,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        사용자 쿼리를 분석하고 의도 기반 검색 전략을 수립
        
        Args:
            user_query: 사용자 쿼리
            session: 채팅 세션 (컨텍스트 참조용)
            system_prompt: 시스템 프롬프트 (사용자 설정)
            
        Returns:
            의도 분석 결과 및 검색 전략
        """
        try:
            start_time = datetime.now()
            
            agent_logger.log_agent_action(
                "ImprovedOrchestrationAgent",
                "analyze_query_start",
                {"query_length": len(user_query)}
            )
            
            # 1단계: 의도 분석
            conversation_history = self._extract_conversation_history(session)
            context = self._build_context(session, system_prompt)
            
            intent_result = self.intent_analyzer.analyze_user_intent(
                query=user_query,
                context=context,
                conversation_history=conversation_history
            )
            
            # 2단계: 기본 검색 전략 수립
            basic_strategy = self._develop_basic_search_strategy(user_query, intent_result)
            
            # 3단계: 의도 기반 검색 전략 강화
            enhanced_strategy = self._enhance_strategy_with_intent(basic_strategy, intent_result)
            
            # 4단계: 최종 분석 결과 통합
            final_result = self._integrate_analysis_results(
                user_query,
                intent_result,
                basic_strategy,
                enhanced_strategy
            )
            
            # 처리 시간 계산
            processing_time = (datetime.now() - start_time).total_seconds()
            final_result["processing_metadata"] = {
                "processing_time": processing_time,
                "timestamp": start_time.isoformat(),
                "model_used": self.model_id
            }
            
            agent_logger.log_agent_action(
                "ImprovedOrchestrationAgent",
                "analyze_query_complete",
                {
                    "primary_intent": intent_result.get("primary_intent", "unknown"),
                    "requires_additional_search": intent_result.get("requires_additional_search", False),
                    "search_strategy": enhanced_strategy.get("strategy_type", "unknown"),
                    "processing_time": processing_time
                }
            )
            
            return final_result
            
        except Exception as e:
            agent_logger.log_error(e, "improved_orchestration_analyze_query")
            return self._get_fallback_analysis(user_query)
    
    def _extract_conversation_history(self, session: Optional[ChatSession]) -> Optional[List[Dict[str, str]]]:
        """세션에서 대화 히스토리 추출"""
        if not session or not hasattr(session, 'messages'):
            return None
        
        history = []
        for message in session.messages[-6:]:  # 최근 6개 메시지만
            if hasattr(message, 'role') and hasattr(message, 'content'):
                history.append({
                    "role": message.role,
                    "content": message.content[:300]  # 300자로 제한
                })
        
        return history if history else None
    
    def _build_context(self, session: Optional[ChatSession], system_prompt: Optional[str]) -> Optional[str]:
        """컨텍스트 정보 구성"""
        context_parts = []
        
        if system_prompt:
            context_parts.append(f"시스템 프롬프트: {system_prompt[:200]}")
        
        if session and hasattr(session, 'context'):
            kb_id = getattr(session.context, 'kb_id', None)
            if kb_id:
                context_parts.append(f"Knowledge Base ID: {kb_id}")
        
        return " | ".join(context_parts) if context_parts else None
    
    def _develop_basic_search_strategy(
        self, 
        user_query: str, 
        intent_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """기본 검색 전략 수립"""
        
        complexity = intent_result.get("complexity_level", "보통")
        primary_intent = intent_result.get("primary_intent", "일반_정보")
        
        # 복잡도별 기본 전략
        if complexity == "단순":
            strategy_type = "단일검색"
            max_results = 30
        elif complexity == "복잡":
            strategy_type = "다단계검색"
            max_results = 50
        else:
            strategy_type = "하이브리드검색"
            max_results = 40
        
        # 의도별 검색 타입 조정
        search_type_mapping = {
            "절차_문의": "HYBRID",
            "규정_확인": "HYBRID", 
            "기술_질문": "SEMANTIC",
            "일반_정보": "HYBRID",
            "비교_분석": "HYBRID",
            "문제_해결": "SEMANTIC"
        }
        
        search_type = search_type_mapping.get(primary_intent, "HYBRID")
        
        return {
            "strategy_type": strategy_type,
            "search_type": search_type,
            "max_results": max_results,
            "primary_query": user_query,
            "confidence": intent_result.get("confidence_score", 0.7)
        }
    
    def _enhance_strategy_with_intent(
        self, 
        basic_strategy: Dict[str, Any], 
        intent_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """의도 분석 결과로 검색 전략 강화"""
        
        enhanced_strategy = basic_strategy.copy()
        
        # 추가 검색 필요성 판단
        requires_additional = intent_result.get("requires_additional_search", False)
        additional_queries = intent_result.get("additional_search_queries", [])
        
        if requires_additional and additional_queries:
            enhanced_strategy["requires_additional_search"] = True
            enhanced_strategy["additional_search_queries"] = additional_queries
            enhanced_strategy["max_additional_searches"] = min(len(additional_queries), 5)
        else:
            enhanced_strategy["requires_additional_search"] = False
            enhanced_strategy["additional_search_queries"] = []
            enhanced_strategy["max_additional_searches"] = 0
        
        # 검색 우선순위 설정
        key_entities = intent_result.get("key_entities", [])
        search_focus_areas = intent_result.get("search_focus_areas", [])
        
        enhanced_strategy["search_priorities"] = {
            "key_entities": key_entities[:3],  # 상위 3개 엔티티
            "focus_areas": search_focus_areas[:3],  # 상위 3개 포커스 영역
            "intent_keywords": self._get_intent_keywords(intent_result.get("primary_intent", ""))
        }
        
        # 결과 필터링 기준 설정
        enhanced_strategy["result_filtering"] = {
            "min_confidence": 0.3,
            "prefer_recent": intent_result.get("primary_intent") in ["규정_확인", "절차_문의"],
            "prefer_comprehensive": intent_result.get("complexity_level") == "복잡"
        }
        
        return enhanced_strategy
    
    def _get_intent_keywords(self, primary_intent: str) -> List[str]:
        """의도별 키워드 반환"""
        intent_keywords = {
            "절차_문의": ["절차", "단계", "프로세스", "방법"],
            "규정_확인": ["규정", "기준", "법령", "조항"],
            "기술_질문": ["기술", "방법", "해결책", "구현"],
            "일반_정보": ["정보", "개념", "정의", "설명"],
            "비교_분석": ["비교", "차이점", "장단점", "선택"],
            "문제_해결": ["해결", "대응", "조치", "방안"]
        }
        
        return intent_keywords.get(primary_intent, [])
    
    def _integrate_analysis_results(
        self,
        user_query: str,
        intent_result: Dict[str, Any],
        basic_strategy: Dict[str, Any],
        enhanced_strategy: Dict[str, Any]
    ) -> Dict[str, Any]:
        """분석 결과들을 통합하여 최종 결과 생성"""
        
        return {
            # 원본 정보
            "original_query": user_query,
            
            # 의도 분석 결과
            "intent_analysis": intent_result,
            
            # 검색 전략
            "search_strategy": enhanced_strategy["strategy_type"],
            "search_type": enhanced_strategy["search_type"],
            "max_results": enhanced_strategy["max_results"],
            
            # 검색 쿼리들
            "primary_query": user_query,
            "search_queries": [user_query],  # 기본 쿼리
            
            # 추가 검색 정보
            "requires_additional_search": enhanced_strategy.get("requires_additional_search", False),
            "additional_search_queries": enhanced_strategy.get("additional_search_queries", []),
            "max_additional_searches": enhanced_strategy.get("max_additional_searches", 0),
            
            # 우선순위 및 필터링
            "search_priorities": enhanced_strategy.get("search_priorities", {}),
            "result_filtering": enhanced_strategy.get("result_filtering", {}),
            
            # 메타데이터
            "complexity": intent_result.get("complexity_level", "보통"),
            "primary_intent": intent_result.get("primary_intent", "일반_정보"),
            "confidence": enhanced_strategy.get("confidence", 0.7),
            
            # 처리 정보
            "analysis_timestamp": datetime.now().isoformat(),
            "agent_version": "improved_v1.0"
        }
    
    def _get_fallback_analysis(self, user_query: str) -> Dict[str, Any]:
        """분석 실패 시 기본 분석 결과 반환"""
        return {
            "original_query": user_query,
            "intent_analysis": {
                "primary_intent": "일반_정보",
                "complexity_level": "보통",
                "requires_additional_search": False,
                "confidence_score": 0.3
            },
            "search_strategy": "하이브리드검색",
            "search_type": "HYBRID",
            "max_results": 30,
            "primary_query": user_query,
            "search_queries": [user_query],
            "requires_additional_search": False,
            "additional_search_queries": [],
            "max_additional_searches": 0,
            "search_priorities": {"key_entities": [], "focus_areas": [], "intent_keywords": []},
            "result_filtering": {"min_confidence": 0.3, "prefer_recent": False, "prefer_comprehensive": False},
            "complexity": "보통",
            "primary_intent": "일반_정보",
            "confidence": 0.3,
            "analysis_timestamp": datetime.now().isoformat(),
            "agent_version": "improved_v1.0_fallback"
        }
    
    def refine_search_queries(
        self,
        analysis_result: Dict[str, Any],
        search_results: List[Dict[str, Any]]
    ) -> List[str]:
        """검색 결과를 바탕으로 쿼리 개선"""
        
        original_queries = analysis_result.get("additional_search_queries", [])
        if not original_queries:
            return []
        
        # 검색 결과 분석
        total_results = sum(len(result.get("citations", [])) for result in search_results)
        
        # 결과가 부족한 경우 쿼리 확장
        if total_results < 10:
            key_entities = analysis_result.get("search_priorities", {}).get("key_entities", [])
            intent_keywords = analysis_result.get("search_priorities", {}).get("intent_keywords", [])
            
            refined_queries = []
            for entity in key_entities[:2]:
                for keyword in intent_keywords[:2]:
                    refined_query = f"{entity} {keyword}"
                    if refined_query not in original_queries:
                        refined_queries.append(refined_query)
            
            return refined_queries[:3]  # 최대 3개 추가
        
        return original_queries
    
    def evaluate_search_completeness(
        self,
        analysis_result: Dict[str, Any],
        search_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """검색 완성도 평가"""
        
        citations = search_results.get("citations", [])
        citation_count = len(citations)
        
        # 의도별 최소 요구사항
        intent_requirements = {
            "절차_문의": {"min_results": 3, "preferred_results": 8},
            "규정_확인": {"min_results": 2, "preferred_results": 6},
            "기술_질문": {"min_results": 2, "preferred_results": 5},
            "일반_정보": {"min_results": 1, "preferred_results": 4},
            "비교_분석": {"min_results": 4, "preferred_results": 10},
            "문제_해결": {"min_results": 3, "preferred_results": 7}
        }
        
        primary_intent = analysis_result.get("primary_intent", "일반_정보")
        requirements = intent_requirements.get(primary_intent, {"min_results": 2, "preferred_results": 5})
        
        min_results = requirements["min_results"]
        preferred_results = requirements["preferred_results"]
        
        # 완성도 평가
        if citation_count >= preferred_results:
            completeness = "excellent"
            sufficient = True
        elif citation_count >= min_results:
            completeness = "good"
            sufficient = True
        elif citation_count > 0:
            completeness = "minimal"
            sufficient = citation_count >= 1  # 최소 1개는 있어야 함
        else:
            completeness = "insufficient"
            sufficient = False
        
        # 품질 평가
        high_confidence_count = sum(1 for c in citations if c.get("confidence", 0) >= 0.7)
        quality_score = high_confidence_count / max(citation_count, 1)
        
        return {
            "sufficient": sufficient,
            "completeness": completeness,
            "citation_count": citation_count,
            "min_required": min_results,
            "preferred_count": preferred_results,
            "quality_score": round(quality_score, 2),
            "high_confidence_count": high_confidence_count,
            "recommendation": self._get_search_recommendation(
                completeness, citation_count, preferred_results
            )
        }
    
    def _get_search_recommendation(
        self, 
        completeness: str, 
        current_count: int, 
        preferred_count: int
    ) -> str:
        """검색 권장사항 생성"""
        
        if completeness == "insufficient":
            return "추가 검색이 필요합니다. 다른 키워드로 검색을 시도하세요."
        elif completeness == "minimal":
            return f"기본 정보는 확보했으나, 더 포괄적인 답변을 위해 추가 검색을 권장합니다. (현재 {current_count}개, 권장 {preferred_count}개)"
        elif completeness == "good":
            return "충분한 정보가 확보되었습니다. 답변 생성을 진행합니다."
        else:  # excellent
            return "우수한 품질의 정보가 충분히 확보되었습니다."


# 전역 인스턴스
improved_orchestration_agent = ImprovedOrchestrationAgent()
