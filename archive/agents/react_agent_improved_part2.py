"""
Improved ReAct Agent - Part 2
개선된 ReAct Agent의 나머지 메서드들
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import time

from config.settings import settings
from src.utils.logger import agent_logger
from src.utils.session import ChatSession, SessionContext, Message, session_manager


class ImprovedReActAgentPart2:
    """개선된 ReAct Agent의 나머지 메서드들"""
    
    def _get_or_create_session(
        self,
        session_id: Optional[str],
        system_prompt: Optional[str],
        kb_id: Optional[str]
    ) -> ChatSession:
        """세션 가져오기 또는 생성 (개선된 버전)"""
        try:
            # 세션 컨텍스트 구성
            context = SessionContext(
                system_prompt=system_prompt or "",
                kb_id=kb_id or settings.knowledge_base.kb_id
            )
            
            if session_id:
                session = session_manager.get_session(session_id)
                if session:
                    # 기존 세션의 컨텍스트 업데이트
                    if system_prompt:
                        session.update_context(system_prompt=system_prompt)
                    if kb_id:
                        session.update_context(kb_id=kb_id)
                    return session
            
            # 새 세션 생성
            session = session_manager.create_session(context)
            
            # 시스템 메시지 추가 (시스템 프롬프트가 있는 경우)
            if system_prompt:
                system_message = Message.create_system_message(system_prompt)
                session.add_message(system_message)
            
            self.current_session = session
            return session
            
        except Exception as e:
            agent_logger.log_error(e, "enhanced_react_session_management")
            # 기본 세션 생성
            return session_manager.create_session()
    
    def _save_enhanced_execution_history(
        self,
        user_query: str,
        session_id: str,
        result: Dict[str, Any],
        total_time: float
    ):
        """개선된 실행 히스토리 저장"""
        try:
            # 기본 정보
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "query": user_query[:100],  # 처음 100자만
                "status": result.get("status", "unknown"),
                "iterations_used": result.get("iterations_used", 0),
                "total_time": total_time,
                
                # 개선된 메트릭들
                "enhanced_features": result.get("enhanced_features", {}),
                "primary_intent": result.get("metadata", {}).get("primary_intent", "unknown"),
                "complexity_level": result.get("metadata", {}).get("complexity_level", "보통"),
                "citation_count": len(result.get("citations", [])),
                "search_stages": result.get("metadata", {}).get("total_search_stages", 0),
                "additional_searches": result.get("metadata", {}).get("additional_searches_performed", 0),
                
                # 품질 메트릭
                "search_quality": result.get("metadata", {}).get("search_quality", {}).get("overall_quality", 0),
                "response_quality": result.get("metadata", {}).get("response_quality", {}).get("overall_quality", 0),
                
                # 토큰 사용량
                "token_usage": result.get("response_metadata", {}).get("token_usage", {}),
                
                # 이미지 관련
                "has_images": result.get("metadata", {}).get("has_images", False),
                
                # Tool 호출 통계
                "tool_calls": len(result.get("metadata", {}).get("tool_call_statistics", {}).get("tool_statistics", {}))
            }
            
            self.execution_history.append(history_entry)
            
            # 히스토리 크기 제한 (최근 100개만 유지)
            if len(self.execution_history) > 100:
                self.execution_history = self.execution_history[-100:]
                
        except Exception as e:
            agent_logger.log_error(e, "enhanced_execution_history_save")
    
    def _get_enhanced_error_response(
        self,
        user_query: str,
        error_message: str,
        react_log: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """개선된 에러 응답 생성"""
        return {
            "content": f"""
죄송합니다. 질문 처리 중 오류가 발생했습니다.

**오류 내용**: {error_message}

**질문**: {user_query}

개선된 시스템에서 다음 기능들을 시도했습니다:
- 🧠 사용자 의도 분석
- 🔍 다단계 KB 검색
- 📝 3000 토큰 이내 응답 생성
- 🔧 MCP Tool 호출 추적

다시 질문해 주시거나, 질문을 더 구체적으로 작성해 주시면 도움을 드릴 수 있습니다.
""",
            "citations": [],
            "status": "error",
            "error": error_message,
            "react_log": react_log or [],
            "enhanced_features": {
                "intent_analysis": False,
                "multi_stage_search": False,
                "token_limited_response": False,
                "tool_call_tracking": False
            },
            "metadata": {
                "error_timestamp": datetime.now().isoformat(),
                "original_query": user_query,
                "agent_version": "enhanced_v1.0_error"
            }
        }
    
    def get_enhanced_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """개선된 세션 정보 조회"""
        try:
            session = session_manager.get_session(session_id)
            if session:
                basic_info = session.to_dict()
                
                # 개선된 정보 추가
                enhanced_info = basic_info.copy()
                enhanced_info["enhanced_features"] = {
                    "intent_analysis_enabled": True,
                    "multi_stage_search_enabled": True,
                    "token_limited_responses": True,
                    "tool_call_tracking_enabled": True
                }
                
                # 세션 통계
                if hasattr(session, 'messages') and session.messages:
                    enhanced_info["session_statistics"] = {
                        "total_messages": len(session.messages),
                        "user_messages": sum(1 for msg in session.messages if getattr(msg, 'role', '') == 'user'),
                        "assistant_messages": sum(1 for msg in session.messages if getattr(msg, 'role', '') == 'assistant'),
                        "last_activity": session.messages[-1].timestamp.isoformat() if hasattr(session.messages[-1], 'timestamp') else None
                    }
                
                return enhanced_info
            return None
        except Exception as e:
            agent_logger.log_error(e, "enhanced_get_session_info")
            return None
    
    def reset_enhanced_session(self, session_id: str) -> bool:
        """개선된 세션 리셋"""
        try:
            session = session_manager.get_session(session_id)
            if session:
                session.clear_history(keep_system_messages=True)
                
                # Tool 호출 추적기 정리
                self.tool_tracker.clear_completed_calls()
                
                agent_logger.log_agent_action(
                    "ImprovedReActAgent",
                    "enhanced_session_reset",
                    {"session_id": session_id[:8]}
                )
                return True
            return False
        except Exception as e:
            agent_logger.log_error(e, "enhanced_reset_session")
            return False
    
    def get_enhanced_execution_stats(self) -> Dict[str, Any]:
        """개선된 실행 통계 반환"""
        if not self.execution_history:
            return {"total_queries": 0, "enhanced_features_enabled": True}
        
        total_queries = len(self.execution_history)
        successful_queries = sum(1 for h in self.execution_history if h["status"] == "success")
        
        # 기본 통계
        total_time = sum(h["total_time"] for h in self.execution_history)
        avg_time = total_time / total_queries
        avg_iterations = sum(h["iterations_used"] for h in self.execution_history) / total_queries
        
        # 개선된 메트릭들
        avg_citation_count = sum(h["citation_count"] for h in self.execution_history) / total_queries
        avg_search_stages = sum(h["search_stages"] for h in self.execution_history) / total_queries
        avg_additional_searches = sum(h["additional_searches"] for h in self.execution_history) / total_queries
        
        # 품질 통계
        search_quality_scores = [h.get("search_quality", 0) for h in self.execution_history if h.get("search_quality", 0) > 0]
        response_quality_scores = [h.get("response_quality", 0) for h in self.execution_history if h.get("response_quality", 0) > 0]
        
        avg_search_quality = sum(search_quality_scores) / len(search_quality_scores) if search_quality_scores else 0
        avg_response_quality = sum(response_quality_scores) / len(response_quality_scores) if response_quality_scores else 0
        
        # 의도별 통계
        intent_stats = {}
        for history in self.execution_history:
            intent = history.get("primary_intent", "unknown")
            if intent not in intent_stats:
                intent_stats[intent] = {"count": 0, "avg_time": 0, "success_rate": 0}
            
            intent_stats[intent]["count"] += 1
            intent_stats[intent]["avg_time"] += history["total_time"]
            if history["status"] == "success":
                intent_stats[intent]["success_rate"] += 1
        
        # 평균 계산
        for intent, stats in intent_stats.items():
            stats["avg_time"] = round(stats["avg_time"] / stats["count"], 3)
            stats["success_rate"] = round(stats["success_rate"] / stats["count"] * 100, 1)
        
        # 토큰 사용 통계
        token_usages = [h.get("token_usage", {}).get("total_tokens", 0) for h in self.execution_history if h.get("token_usage")]
        avg_token_usage = sum(token_usages) / len(token_usages) if token_usages else 0
        
        # Tool 호출 통계
        total_tool_calls = sum(h.get("tool_calls", 0) for h in self.execution_history)
        avg_tool_calls = total_tool_calls / total_queries
        
        return {
            # 기본 통계
            "total_queries": total_queries,
            "successful_queries": successful_queries,
            "success_rate": round(successful_queries / total_queries * 100, 1),
            "total_processing_time": round(total_time, 3),
            "average_processing_time": round(avg_time, 3),
            "average_iterations": round(avg_iterations, 2),
            
            # 개선된 메트릭
            "enhanced_features_enabled": True,
            "average_citation_count": round(avg_citation_count, 1),
            "average_search_stages": round(avg_search_stages, 1),
            "average_additional_searches": round(avg_additional_searches, 1),
            "average_search_quality": round(avg_search_quality, 3),
            "average_response_quality": round(avg_response_quality, 3),
            "average_token_usage": round(avg_token_usage, 0),
            "average_tool_calls": round(avg_tool_calls, 1),
            
            # 의도별 통계
            "intent_statistics": intent_stats,
            
            # 기능 사용률
            "feature_usage": {
                "multi_stage_search_rate": round(
                    sum(1 for h in self.execution_history if h.get("additional_searches", 0) > 0) / total_queries * 100, 1
                ),
                "image_usage_rate": round(
                    sum(1 for h in self.execution_history if h.get("has_images", False)) / total_queries * 100, 1
                ),
                "high_quality_response_rate": round(
                    sum(1 for h in self.execution_history if h.get("response_quality", 0) >= 0.7) / total_queries * 100, 1
                )
            },
            
            # Tool 호출 통계 (전체)
            "tool_call_statistics": self.tool_tracker.get_call_statistics(),
            
            # 최근 실행 정보
            "last_query_time": self.execution_history[-1]["timestamp"]
        }
    
    def get_tool_call_progress(self) -> Dict[str, Any]:
        """현재 Tool 호출 진행 상황 반환"""
        return self.tool_tracker.generate_progress_summary()
    
    def clear_execution_history(self):
        """실행 히스토리 정리"""
        # 최근 50개만 유지
        if len(self.execution_history) > 50:
            self.execution_history = self.execution_history[-50:]
        
        # Tool 호출 기록 정리
        self.tool_tracker.clear_completed_calls()
    
    def validate_enhanced_system(self) -> Dict[str, Any]:
        """개선된 시스템 유효성 검증"""
        validation_results = {
            "system_status": "healthy",
            "components": {},
            "validation_timestamp": datetime.now().isoformat()
        }
        
        try:
            # Orchestration Agent 검증
            validation_results["components"]["orchestration_agent"] = {
                "status": "available" if self.orchestration_agent else "unavailable",
                "features": ["intent_analysis", "search_strategy", "result_evaluation"]
            }
            
            # Action Agent 검증
            validation_results["components"]["action_agent"] = {
                "status": "available" if self.action_agent else "unavailable",
                "features": ["multi_stage_search", "tool_call_tracking", "result_integration"]
            }
            
            # Response Agent 검증
            validation_results["components"]["response_agent"] = {
                "status": "available" if self.response_agent else "unavailable",
                "features": ["comprehensive_response", "token_limitation", "quality_metrics"]
            }
            
            # Tool Tracker 검증
            validation_results["components"]["tool_tracker"] = {
                "status": "available" if self.tool_tracker else "unavailable",
                "features": ["call_tracking", "ui_updates", "statistics"]
            }
            
            # 전체 시스템 상태 결정
            unavailable_components = [
                name for name, info in validation_results["components"].items() 
                if info["status"] == "unavailable"
            ]
            
            if unavailable_components:
                validation_results["system_status"] = "degraded"
                validation_results["issues"] = f"Unavailable components: {', '.join(unavailable_components)}"
            
        except Exception as e:
            validation_results["system_status"] = "error"
            validation_results["error"] = str(e)
        
        return validation_results


# 전역 개선된 ReAct Agent 인스턴스
improved_react_agent = ImprovedReActAgent()
