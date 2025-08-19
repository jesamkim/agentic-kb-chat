"""
Improved ReAct Agent
개선된 데이터 흐름을 구현하는 ReAct Agent
- 의도 기반 다단계 검색
- MCP Tool 호출 추적
- 3000 토큰 제한 응답 생성
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import time

from config.settings import settings
from src.utils.logger import agent_logger, main_logger
from src.utils.session import ChatSession, SessionContext, Message, session_manager
from src.agents.orchestration_improved import improved_orchestration_agent
from src.agents.action_improved import improved_action_agent
from src.agents.response_improved import ImprovedResponseAgent
from src.mcp.tool_call_tracker import tool_call_tracker


class ImprovedReActAgent:
    """개선된 ReAct 패턴 기반 메인 Agent"""
    
    def __init__(self):
        self.orchestration_agent = improved_orchestration_agent
        self.action_agent = improved_action_agent
        self.response_agent = ImprovedResponseAgent()
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
        max_iterations: int = 3,  # 개선된 시스템에서는 반복 횟수 감소
        image_data: Optional[str] = None,
        ui_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        개선된 ReAct 패턴으로 사용자 쿼리 처리
        
        Args:
            user_query: 사용자 쿼리
            session_id: 세션 ID (없으면 새 세션 생성)
            system_prompt: 시스템 프롬프트 (사용자 설정)
            kb_id: Knowledge Base ID (사용자 설정)
            max_iterations: 최대 반복 횟수 (기본 3회)
            image_data: 이미지 데이터 (base64)
            ui_callback: UI 업데이트 콜백 함수
            
        Returns:
            최종 처리 결과
        """
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
                
                # === ENHANCED THOUGHT 단계 (Improved Orchestration Agent) ===
                thought_start = time.time()
                
                # UI 업데이트: 의도 분석 시작
                if ui_callback:
                    ui_callback("stage_update", {
                        "stage": "intent_analysis",
                        "message": "🧠 사용자 쿼리 의도 분석 중...",
                        "iteration": iteration
                    })
                
                analysis_result = self.orchestration_agent.analyze_query_with_intent(
                    user_query,
                    session,
                    system_prompt
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
                
                # UI 업데이트: 의도 분석 완료
                if ui_callback:
                    ui_callback("stage_update", {
                        "stage": "intent_analysis_complete",
                        "message": f"✅ 의도 분석 완료: {analysis_result.get('primary_intent', 'unknown')}",
                        "analysis_result": analysis_result
                    })
                
                agent_logger.log_agent_action(
                    "ImprovedReActAgent",
                    f"enhanced_thought_complete_iteration_{iteration}",
                    {
                        "primary_intent": analysis_result.get("primary_intent", "unknown"),
                        "requires_additional_search": analysis_result.get("requires_additional_search", False),
                        "additional_queries_count": len(analysis_result.get("additional_search_queries", []))
                    }
                )
                
                # === ENHANCED ACTION 단계 (Improved Action Agent) ===
                action_start = time.time()
                
                # UI 업데이트: 검색 시작
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
                
                # UI 업데이트: 검색 완료
                if ui_callback:
                    ui_callback("stage_update", {
                        "stage": "search_complete",
                        "message": f"✅ 검색 완료: {len(search_results.get('citations', []))}개 결과",
                        "search_results": search_results
                    })
                
                agent_logger.log_agent_action(
                    "ImprovedReActAgent",
                    f"enhanced_action_complete_iteration_{iteration}",
                    {
                        "status": search_results.get("status", "unknown"),
                        "result_count": len(search_results.get("citations", [])),
                        "quality_score": search_results.get("quality_metrics", {}).get("overall_quality", 0)
                    }
                )
                
                # === ENHANCED OBSERVATION 단계 (결과 평가) ===
                observation_result = self._evaluate_enhanced_search_results(
                    search_results,
                    analysis_result,
                    iteration
                )
                
                react_log.append({
                    "iteration": iteration,
                    "step": "ENHANCED_OBSERVATION",
                    "content": observation_result,
                    "time": 0.1
                })
                
                # 결과가 충분한지 확인
                if observation_result["sufficient"]:
                    # === ENHANCED RESPONSE 생성 (Improved Response Agent) ===
                    response_start = time.time()
                    
                    # UI 업데이트: 응답 생성 시작
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
                    
                    # UI 업데이트: 응답 생성 완료
                    if ui_callback:
                        ui_callback("stage_update", {
                            "stage": "response_complete",
                            "message": "✅ 응답 생성 완료",
                            "response_metadata": final_response.get("response_metadata", {})
                        })
                    
                    # 세션에 응답 저장
                    enhanced_response = self.response_agent.enhance_response_with_context(
                        final_response,
                        session,
                        save_to_session=True
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
                    
                    agent_logger.log_agent_action(
                        "ImprovedReActAgent",
                        "enhanced_react_cycle_complete",
                        {
                            "iterations": iteration,
                            "final_status": enhanced_response.get("status", "unknown"),
                            "final_quality": enhanced_response.get("metadata", {}).get("response_quality", {}).get("overall_quality", 0)
                        }
                    )
                    
                    return enhanced_response
                
                # 결과가 부족하면 다음 반복 (개선된 시스템에서는 대부분 1회에 완료)
                if iteration < max_iterations:
                    # 검색 전략 개선
                    refined_analysis = self._refine_analysis_for_next_iteration(
                        analysis_result,
                        search_results,
                        observation_result
                    )
                    analysis_result = refined_analysis
                    
                    agent_logger.log_agent_action(
                        "ImprovedReActAgent",
                        f"refine_analysis_iteration_{iteration}",
                        {"refined_queries_count": len(refined_analysis.get("additional_search_queries", []))}
                    )
            
            # 최대 반복 횟수 도달 시 현재 결과로 응답 생성
            agent_logger.log_agent_action(
                "ImprovedReActAgent",
                "max_iterations_reached_enhanced",
                {"max_iterations": max_iterations}
            )
            
            final_response = self.response_agent.generate_comprehensive_response(
                user_query,
                search_results,
                analysis_result,
                session,
                system_prompt,
                image_data
            )
            
            final_response["react_log"] = react_log
            final_response["iterations_used"] = max_iterations
            final_response["max_iterations_reached"] = True
            
            return self.response_agent.enhance_response_with_context(
                final_response,
                session,
                save_to_session=True
            )
            
        except Exception as e:
            agent_logger.log_error(e, "enhanced_react_execute_cycle")
            return self._get_enhanced_error_response(user_query, str(e), react_log)
    
    def _evaluate_enhanced_search_results(
        self,
        search_results: Dict[str, Any],
        analysis_result: Dict[str, Any],
        iteration: int
    ) -> Dict[str, Any]:
        """개선된 검색 결과 평가"""
        
        try:
            # 기본 평가는 Orchestration Agent에 위임
            basic_evaluation = self.orchestration_agent.evaluate_search_completeness(
                analysis_result,
                search_results
            )
            
            # 품질 메트릭 추가 고려
            quality_metrics = search_results.get("quality_metrics", {})
            overall_quality = quality_metrics.get("overall_quality", 0)
            
            # 품질 기반 충족도 조정
            if basic_evaluation["sufficient"] and overall_quality < 0.3:
                basic_evaluation["sufficient"] = False
                basic_evaluation["reason"] += f" (품질 점수 낮음: {overall_quality:.2f})"
            
            # 개선된 평가 정보 추가
            enhanced_evaluation = basic_evaluation.copy()
            enhanced_evaluation.update({
                "quality_metrics": quality_metrics,
                "search_stages_completed": len(search_results.get("search_stages", [])),
                "additional_searches_performed": len(search_results.get("additional_results", [])),
                "tool_calls_made": len(search_results.get("tool_call_statistics", {}).get("tool_statistics", {})),
                "evaluation_version": "enhanced_v1.0"
            })
            
            return enhanced_evaluation
            
        except Exception as e:
            agent_logger.log_error(e, "enhanced_search_evaluation")
            return {
                "sufficient": True,  # 평가 실패 시 진행
                "reason": "평가 실패로 인한 기본 진행",
                "error": str(e),
                "evaluation_version": "enhanced_v1.0_fallback"
            }
    
    def _refine_analysis_for_next_iteration(
        self,
        analysis_result: Dict[str, Any],
        search_results: Dict[str, Any],
        observation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """다음 반복을 위한 분석 결과 개선"""
        
        refined_analysis = analysis_result.copy()
        
        # 검색 결과가 부족한 경우 추가 쿼리 생성
        if observation_result.get("citation_count", 0) < 3:
            # 기존 추가 쿼리에 더 구체적인 쿼리 추가
            existing_queries = refined_analysis.get("additional_search_queries", [])
            key_entities = refined_analysis.get("search_priorities", {}).get("key_entities", [])
            
            new_queries = []
            for entity in key_entities[:2]:
                new_queries.extend([
                    f"{entity} 상세 정보",
                    f"{entity} 관련 규정",
                    f"{entity} 실무 가이드"
                ])
            
            # 중복 제거하고 기존 쿼리와 합치기
            all_queries = existing_queries + [q for q in new_queries if q not in existing_queries]
            refined_analysis["additional_search_queries"] = all_queries[:5]  # 최대 5개
            refined_analysis["max_additional_searches"] = min(len(all_queries), 5)
        
        return refined_analysis
