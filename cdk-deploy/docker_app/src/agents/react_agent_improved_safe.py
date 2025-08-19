"""
Improved ReAct Agent - Safe Version
안전한 Response Agent를 사용하는 개선된 ReAct Agent
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import time

from config.settings import settings
from src.utils.logger import agent_logger, main_logger
from src.utils.session import ChatSession, SessionContext, Message, session_manager
from src.agents.orchestration_improved import improved_orchestration_agent
from src.agents.action_improved import improved_action_agent
from src.agents.response_improved_safe import ImprovedResponseAgent  # 안전한 버전 사용
from src.mcp.tool_call_tracker import tool_call_tracker


class ImprovedReActAgent:
    """개선된 ReAct 패턴 기반 메인 Agent - 안전 버전"""
    
    def __init__(self):
        self.orchestration_agent = improved_orchestration_agent
        self.action_agent = improved_action_agent
        self.response_agent = ImprovedResponseAgent()  # 안전한 Response Agent 사용
        self.tool_tracker = tool_call_tracker
        self.execution_history = []
        self.current_session = None
        
        agent_logger.log_agent_action("ImprovedReActAgent", "initialized", {})
    
    def process_query_enhanced(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        kb_id: Optional[str] = None,
        max_iterations: int = 3,
        image_data: Optional[str] = None,
        ui_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """개선된 ReAct 패턴으로 사용자 쿼리 처리"""
        start_time = time.time()
        
        try:
            # UI 콜백 설정
            if ui_callback:
                self.tool_tracker.set_ui_callback(ui_callback)
            
            # 세션 관리
            session = self._get_or_create_session(session_id, system_prompt, kb_id)
            
            # 사용자 메시지 세션에 추가
            user_message = Message.create_user_message(user_query)
            session.add_message(user_message)
            
            agent_logger.log_agent_action(
                "ImprovedReActAgent",
                "enhanced_process_start",
                {
                    "session_id": session.session_id[:8],
                    "query_length": len(user_query),
                    "max_iterations": max_iterations,
                    "has_image": image_data is not None
                }
            )
            
            # 개선된 ReAct 사이클 실행
            final_result = self._execute_enhanced_react_cycle(
                user_query,
                session,
                system_prompt,
                max_iterations,
                image_data,
                ui_callback
            )
            
            # 실행 시간 계산
            total_time = time.time() - start_time
            final_result["total_processing_time"] = round(total_time, 3)
            
            # 실행 히스토리 저장
            self._save_enhanced_execution_history(user_query, session.session_id, final_result, total_time)
            
            agent_logger.log_agent_action(
                "ImprovedReActAgent",
                "enhanced_process_complete",
                {
                    "session_id": session.session_id[:8],
                    "total_time": total_time,
                    "status": final_result.get("status", "unknown"),
                    "final_citation_count": len(final_result.get("citations", []))
                }
            )
            
            return final_result
            
        except Exception as e:
            agent_logger.log_error(e, "enhanced_react_process_query")
            return self._get_enhanced_error_response(user_query, str(e))
    
    def _execute_enhanced_react_cycle(
        self,
        user_query: str,
        session: ChatSession,
        system_prompt: Optional[str],
        max_iterations: int,
        image_data: Optional[str] = None,
        ui_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """개선된 ReAct 사이클 실행"""
        
        react_log = []
        iteration = 0
        
        try:
            while iteration < max_iterations:
                iteration += 1
                
                agent_logger.log_agent_action(
                    "ImprovedReActAgent",
                    f"enhanced_react_iteration_{iteration}_start",
                    {"iteration": iteration, "max_iterations": max_iterations}
                )
                
                # === ENHANCED THOUGHT 단계 ===
                thought_start = time.time()
                
                if ui_callback:
                    ui_callback("stage_update", {
                        "stage": "intent_analysis",
                        "message": "🧠 사용자 쿼리 의도 분석 중...",
                        "iteration": iteration
                    })
                
                analysis_result = self.orchestration_agent.analyze_query_with_intent(
                    user_query, session, system_prompt
                )
                
                thought_time = time.time() - thought_start
                
                react_log.append({
                    "iteration": iteration,
                    "step": "ENHANCED_THOUGHT",
                    "content": {
                        "primary_intent": analysis_result.get("primary_intent", "unknown"),
                        "complexity": analysis_result.get("complexity", "보통"),
                        "requires_additional_search": analysis_result.get("requires_additional_search", False),
                        "additional_queries_count": len(analysis_result.get("additional_search_queries", []))
                    },
                    "time": round(thought_time, 3)
                })
                
                if ui_callback:
                    ui_callback("stage_update", {
                        "stage": "intent_analysis_complete",
                        "message": f"✅ 의도 분석 완료: {analysis_result.get('primary_intent', 'unknown')}",
                        "analysis_result": analysis_result
                    })
                
                # === ENHANCED ACTION 단계 ===
                action_start = time.time()
                
                if ui_callback:
                    ui_callback("stage_update", {
                        "stage": "multi_stage_search",
                        "message": "🔍 다단계 KB 검색 시작...",
                        "search_plan": {
                            "primary_search": True,
                            "additional_searches": analysis_result.get("requires_additional_search", False),
                            "additional_queries": analysis_result.get("additional_search_queries", [])
                        }
                    })
                
                search_results = self.action_agent.execute_enhanced_search_strategy(
                    analysis_result,
                    max_results_per_query=None,
                    enable_rerank=settings.knowledge_base.enable_rerank,
                    ui_callback=ui_callback
                )
                
                action_time = time.time() - action_start
                
                react_log.append({
                    "iteration": iteration,
                    "step": "ENHANCED_ACTION",
                    "content": {
                        "status": search_results.get("status", "unknown"),
                        "citation_count": len(search_results.get("citations", [])),
                        "search_stages": len(search_results.get("search_stages", [])),
                        "quality_score": search_results.get("quality_metrics", {}).get("overall_quality", 0),
                        "additional_searches_performed": len(search_results.get("additional_results", []))
                    },
                    "time": round(action_time, 3)
                })
                
                if ui_callback:
                    ui_callback("stage_update", {
                        "stage": "search_complete",
                        "message": f"✅ 검색 완료: {len(search_results.get('citations', []))}개 결과",
                        "search_results": search_results
                    })
                
                # === ENHANCED OBSERVATION 단계 ===
                observation_result = self._evaluate_enhanced_search_results(
                    search_results, analysis_result, iteration
                )
                
                react_log.append({
                    "iteration": iteration,
                    "step": "ENHANCED_OBSERVATION",
                    "content": observation_result,
                    "time": 0.1
                })
                
                # 결과가 충분한지 확인
                if observation_result["sufficient"]:
                    # === ENHANCED RESPONSE 생성 ===
                    response_start = time.time()
                    
                    if ui_callback:
                        ui_callback("stage_update", {
                            "stage": "response_generation",
                            "message": "📝 포괄적 응답 생성 중... (3000 토큰 이내)",
                            "citation_count": len(search_results.get("citations", []))
                        })
                    
                    final_response = self.response_agent.generate_comprehensive_response(
                        user_query,
                        search_results,
                        analysis_result,
                        session,
                        system_prompt,
                        image_data
                    )
                    
                    response_time = time.time() - response_start
                    
                    react_log.append({
                        "iteration": iteration,
                        "step": "ENHANCED_RESPONSE",
                        "content": {
                            "response_length": len(final_response.get("content", "")),
                            "citation_count": len(final_response.get("citations", [])),
                            "token_usage": final_response.get("response_metadata", {}).get("token_usage", {}),
                            "quality_score": final_response.get("metadata", {}).get("response_quality", {}).get("overall_quality", 0)
                        },
                        "time": round(response_time, 3)
                    })
                    
                    if ui_callback:
                        ui_callback("stage_update", {
                            "stage": "response_complete",
                            "message": "✅ 응답 생성 완료",
                            "response_metadata": final_response.get("response_metadata", {})
                        })
                    
                    # 세션에 응답 저장
                    enhanced_response = self.response_agent.enhance_response_with_context(
                        final_response, session, save_to_session=True
                    )
                    
                    # ReAct 로그 및 메타데이터 추가
                    enhanced_response["react_log"] = react_log
                    enhanced_response["iterations_used"] = iteration
                    enhanced_response["enhanced_features"] = {
                        "intent_analysis": True,
                        "multi_stage_search": True,
                        "token_limited_response": True,
                        "tool_call_tracking": True
                    }
                    
                    return enhanced_response
                
                # 결과가 부족하면 다음 반복
                if iteration < max_iterations:
                    refined_analysis = self._refine_analysis_for_next_iteration(
                        analysis_result, search_results, observation_result
                    )
                    analysis_result = refined_analysis
            
            # 최대 반복 횟수 도달 시 현재 결과로 응답 생성
            final_response = self.response_agent.generate_comprehensive_response(
                user_query, search_results, analysis_result, session, system_prompt, image_data
            )
            
            final_response["react_log"] = react_log
            final_response["iterations_used"] = max_iterations
            final_response["max_iterations_reached"] = True
            
            return self.response_agent.enhance_response_with_context(
                final_response, session, save_to_session=True
            )
            
        except Exception as e:
            agent_logger.log_error(e, "enhanced_react_execute_cycle")
            return self._get_enhanced_error_response(user_query, str(e), react_log)
    
    def _evaluate_enhanced_search_results(
        self, search_results: Dict[str, Any], analysis_result: Dict[str, Any], iteration: int
    ) -> Dict[str, Any]:
        """개선된 검색 결과 평가"""
        try:
            basic_evaluation = self.orchestration_agent.evaluate_search_completeness(
                analysis_result, search_results
            )
            
            quality_metrics = search_results.get("quality_metrics", {})
            overall_quality = quality_metrics.get("overall_quality", 0)
            
            if basic_evaluation["sufficient"] and overall_quality < 0.3:
                basic_evaluation["sufficient"] = False
                # reason 키가 없을 경우 기본값 설정
                if "reason" not in basic_evaluation:
                    basic_evaluation["reason"] = "품질 점수 낮음"
                else:
                    basic_evaluation["reason"] += f" (품질 점수 낮음: {overall_quality:.2f})"
            
            enhanced_evaluation = basic_evaluation.copy()
            enhanced_evaluation.update({
                "quality_metrics": quality_metrics,
                "search_stages_completed": len(search_results.get("search_stages", [])),
                "additional_searches_performed": len(search_results.get("additional_results", [])),
                "evaluation_version": "enhanced_v1.0"
            })
            
            return enhanced_evaluation
            
        except Exception as e:
            agent_logger.log_error(e, "enhanced_search_evaluation")
            return {
                "sufficient": True,
                "reason": "평가 실패로 인한 기본 진행",
                "error": str(e)
            }
    
    def _refine_analysis_for_next_iteration(
        self, analysis_result: Dict[str, Any], search_results: Dict[str, Any], observation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """다음 반복을 위한 분석 결과 개선"""
        refined_analysis = analysis_result.copy()
        
        if observation_result.get("citation_count", 0) < 3:
            existing_queries = refined_analysis.get("additional_search_queries", [])
            key_entities = refined_analysis.get("search_priorities", {}).get("key_entities", [])
            
            new_queries = []
            for entity in key_entities[:2]:
                new_queries.extend([
                    f"{entity} 상세 정보",
                    f"{entity} 관련 규정",
                    f"{entity} 실무 가이드"
                ])
            
            all_queries = existing_queries + [q for q in new_queries if q not in existing_queries]
            refined_analysis["additional_search_queries"] = all_queries[:5]
            refined_analysis["max_additional_searches"] = min(len(all_queries), 5)
        
        return refined_analysis
    
    def _get_or_create_session(
        self, session_id: Optional[str], system_prompt: Optional[str], kb_id: Optional[str]
    ) -> ChatSession:
        """세션 가져오기 또는 생성"""
        try:
            context = SessionContext(
                system_prompt=system_prompt or "",
                kb_id=kb_id or settings.knowledge_base.kb_id
            )
            
            if session_id:
                session = session_manager.get_session(session_id)
                if session:
                    if system_prompt:
                        session.update_context(system_prompt=system_prompt)
                    if kb_id:
                        session.update_context(kb_id=kb_id)
                    return session
            
            session = session_manager.create_session(context)
            
            if system_prompt:
                system_message = Message.create_system_message(system_prompt)
                session.add_message(system_message)
            
            self.current_session = session
            return session
            
        except Exception as e:
            agent_logger.log_error(e, "enhanced_react_session_management")
            return session_manager.create_session()
    
    def _save_enhanced_execution_history(
        self, user_query: str, session_id: str, result: Dict[str, Any], total_time: float
    ):
        """개선된 실행 히스토리 저장"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "query": user_query[:100],
                "status": result.get("status", "unknown"),
                "iterations_used": result.get("iterations_used", 0),
                "total_time": total_time,
                "enhanced_features": result.get("enhanced_features", {}),
                "primary_intent": result.get("metadata", {}).get("primary_intent", "unknown"),
                "complexity_level": result.get("metadata", {}).get("complexity_level", "보통"),
                "citation_count": len(result.get("citations", [])),
                "search_stages": result.get("metadata", {}).get("total_search_stages", 0),
                "additional_searches": result.get("metadata", {}).get("additional_searches_performed", 0),
                "search_quality": result.get("metadata", {}).get("search_quality", {}).get("overall_quality", 0),
                "response_quality": result.get("metadata", {}).get("response_quality", {}).get("overall_quality", 0),
                "token_usage": result.get("response_metadata", {}).get("token_usage", {}),
                "has_images": result.get("metadata", {}).get("has_images", False)
            }
            
            self.execution_history.append(history_entry)
            
            if len(self.execution_history) > 100:
                self.execution_history = self.execution_history[-100:]
                
        except Exception as e:
            agent_logger.log_error(e, "enhanced_execution_history_save")
    
    def _get_enhanced_error_response(
        self, user_query: str, error_message: str, react_log: Optional[List[Dict[str, Any]]] = None
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
    
    def validate_enhanced_system(self) -> Dict[str, Any]:
        """개선된 시스템 유효성 검증"""
        validation_results = {
            "system_status": "healthy",
            "components": {},
            "validation_timestamp": datetime.now().isoformat()
        }
        
        try:
            validation_results["components"]["orchestration_agent"] = {
                "status": "available" if self.orchestration_agent else "unavailable",
                "features": ["intent_analysis", "search_strategy", "result_evaluation"]
            }
            
            validation_results["components"]["action_agent"] = {
                "status": "available" if self.action_agent else "unavailable",
                "features": ["multi_stage_search", "tool_call_tracking", "result_integration"]
            }
            
            validation_results["components"]["response_agent"] = {
                "status": "available" if self.response_agent else "unavailable",
                "features": ["comprehensive_response", "token_limitation", "quality_metrics"]
            }
            
            validation_results["components"]["tool_tracker"] = {
                "status": "available" if self.tool_tracker else "unavailable",
                "features": ["call_tracking", "ui_updates", "statistics"]
            }
            
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
