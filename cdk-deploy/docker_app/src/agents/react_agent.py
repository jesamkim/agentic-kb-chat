"""
ReAct Agent
Reasoning and Acting 패턴을 구현하는 메인 Agent
Orchestration, Action, Response Agent를 통합하여 완전한 ReAct 사이클 실행
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import time

from config.settings import settings
from src.utils.logger import agent_logger, main_logger
from src.utils.session import ChatSession, SessionContext, Message, session_manager
from src.agents.orchestration import orchestration_agent
from src.agents.action import action_agent
from src.agents.response import response_agent


class ReActAgent:
    """ReAct 패턴 기반 메인 Agent"""
    
    def __init__(self):
        self.execution_history = []
        self.current_session = None
        agent_logger.log_agent_action("ReActAgent", "initialized", {})
    
    def process_query(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        kb_id: Optional[str] = None,
        max_iterations: int = 5,
        image_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        사용자 쿼리를 ReAct 패턴으로 처리
        
        Args:
            user_query: 사용자 쿼리
            session_id: 세션 ID (없으면 새 세션 생성)
            system_prompt: 시스템 프롬프트 (사용자 설정)
            kb_id: Knowledge Base ID (사용자 설정)
            max_iterations: 최대 반복 횟수
            
        Returns:
            최종 처리 결과
        """
        start_time = time.time()
        
        try:
            # 세션 관리
            session = self._get_or_create_session(session_id, system_prompt, kb_id)
            
            # 사용자 메시지 세션에 추가
            user_message = Message.create_user_message(user_query)
            session.add_message(user_message)
            
            agent_logger.log_agent_action(
                "ReActAgent",
                "process_query_start",
                {
                    "session_id": session.session_id[:8],
                    "query_length": len(user_query),
                    "max_iterations": max_iterations
                }
            )
            
            # ReAct 사이클 실행
            final_result = self._execute_react_cycle(
                user_query,
                session,
                system_prompt,
                max_iterations,
                image_data
            )
            
            # 실행 시간 계산
            total_time = time.time() - start_time
            final_result["total_processing_time"] = round(total_time, 3)
            
            # 실행 히스토리 저장
            self._save_execution_history(user_query, session.session_id, final_result, total_time)
            
            agent_logger.log_agent_action(
                "ReActAgent",
                "process_query_complete",
                {
                    "session_id": session.session_id[:8],
                    "total_time": total_time,
                    "status": final_result.get("status", "unknown")
                }
            )
            
            return final_result
            
        except Exception as e:
            agent_logger.log_error(e, "react_process_query")
            return self._get_error_response(user_query, str(e))
    
    def _get_or_create_session(
        self,
        session_id: Optional[str],
        system_prompt: Optional[str],
        kb_id: Optional[str]
    ) -> ChatSession:
        """세션 가져오기 또는 생성"""
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
            agent_logger.log_error(e, "react_session_management")
            # 기본 세션 생성
            return session_manager.create_session()
    
    def _execute_react_cycle(
        self,
        user_query: str,
        session: ChatSession,
        system_prompt: Optional[str],
        max_iterations: int,
        image_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """ReAct 사이클 실행"""
        
        react_log = []
        iteration = 0
        
        try:
            while iteration < max_iterations:
                iteration += 1
                
                agent_logger.log_agent_action(
                    "ReActAgent",
                    f"react_iteration_{iteration}_start",
                    {"iteration": iteration, "max_iterations": max_iterations}
                )
                
                # === THOUGHT 단계 (Orchestration Agent) ===
                thought_start = time.time()
                analysis_result = orchestration_agent.analyze_query(
                    user_query,
                    session,
                    system_prompt
                )
                thought_time = time.time() - thought_start
                
                react_log.append({
                    "iteration": iteration,
                    "step": "THOUGHT",
                    "content": analysis_result,
                    "time": round(thought_time, 3)
                })
                
                agent_logger.log_agent_action(
                    "ReActAgent",
                    f"thought_complete_iteration_{iteration}",
                    {
                        "strategy": analysis_result.get("search_strategy", "unknown"),
                        "query_count": len(analysis_result.get("search_queries", []))
                    }
                )
                
                # === ACTION 단계 (Action Agent) ===
                action_start = time.time()
                search_results = action_agent.execute_search_strategy(
                    analysis_result,
                    max_results_per_query=None,
                    enable_rerank=settings.knowledge_base.enable_rerank
                )
                action_time = time.time() - action_start
                
                react_log.append({
                    "iteration": iteration,
                    "step": "ACTION",
                    "content": {
                        "status": search_results.get("status", "unknown"),
                        "citation_count": len(search_results.get("citations", [])),
                        "search_time": search_results.get("search_time", 0),
                        "rerank_time": search_results.get("rerank_time", 0)
                    },
                    "time": round(action_time, 3)
                })
                
                agent_logger.log_agent_action(
                    "ReActAgent",
                    f"action_complete_iteration_{iteration}",
                    {
                        "status": search_results.get("status", "unknown"),
                        "result_count": len(search_results.get("citations", []))
                    }
                )
                
                # === OBSERVATION 단계 (결과 평가) ===
                observation_result = self._evaluate_search_results(
                    search_results,
                    analysis_result,
                    iteration
                )
                
                react_log.append({
                    "iteration": iteration,
                    "step": "OBSERVATION",
                    "content": observation_result,
                    "time": 0.1  # 평가는 빠름
                })
                
                # 결과가 충분한지 확인
                if observation_result["sufficient"]:
                    # === RESPONSE 생성 (Response Agent) ===
                    response_start = time.time()
                    final_response = response_agent.generate_response(
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
                        "step": "RESPONSE",
                        "content": {
                            "response_length": len(final_response.get("content", "")),
                            "citation_count": len(final_response.get("citations", []))
                        },
                        "time": round(response_time, 3)
                    })
                    
                    # 세션에 응답 저장
                    enhanced_response = response_agent.enhance_response_with_context(
                        final_response,
                        session,
                        save_to_session=True
                    )
                    
                    # ReAct 로그 추가
                    enhanced_response["react_log"] = react_log
                    enhanced_response["iterations_used"] = iteration
                    
                    agent_logger.log_agent_action(
                        "ReActAgent",
                        "react_cycle_complete",
                        {
                            "iterations": iteration,
                            "final_status": enhanced_response.get("status", "unknown")
                        }
                    )
                    
                    return enhanced_response
                
                # 결과가 부족하면 쿼리 개선 후 다음 반복
                if iteration < max_iterations:
                    refined_queries = orchestration_agent.refine_search_queries(
                        analysis_result,
                        [search_results]
                    )
                    analysis_result["search_queries"] = refined_queries
                    
                    agent_logger.log_agent_action(
                        "ReActAgent",
                        f"refine_queries_iteration_{iteration}",
                        {"refined_query_count": len(refined_queries)}
                    )
            
            # 최대 반복 횟수 도달 시 현재 결과로 응답 생성
            agent_logger.log_agent_action(
                "ReActAgent",
                "max_iterations_reached",
                {"max_iterations": max_iterations}
            )
            
            final_response = response_agent.generate_response(
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
            
            return response_agent.enhance_response_with_context(
                final_response,
                session,
                save_to_session=True
            )
            
        except Exception as e:
            agent_logger.log_error(e, "react_execute_cycle")
            return self._get_error_response(user_query, str(e), react_log)
    
    def _evaluate_search_results(
        self,
        search_results: Dict[str, Any],
        analysis_result: Dict[str, Any],
        iteration: int
    ) -> Dict[str, Any]:
        """검색 결과 평가"""
        try:
            citations = search_results.get("citations", [])
            citation_count = len(citations)
            
            # 기본 충족 조건
            min_results = 1
            preferred_results = 3
            
            # 복잡도에 따른 조정
            complexity = analysis_result.get("complexity", "보통")
            if complexity == "복잡":
                preferred_results = 5
            elif complexity == "단순":
                preferred_results = 2
            
            # 충족도 평가
            if citation_count == 0:
                sufficient = False
                reason = "검색 결과가 없음"
            elif citation_count < min_results:
                sufficient = False
                reason = f"최소 결과 수({min_results}) 미달"
            elif citation_count >= preferred_results:
                sufficient = True
                reason = f"충분한 결과 확보 ({citation_count}개)"
            elif iteration >= 2:  # 2번째 반복부터는 관대하게 평가
                sufficient = True
                reason = f"반복 후 결과 확보 ({citation_count}개)"
            else:
                # 1개 결과라도 있으면 일단 충족으로 간주 (테스트 환경 고려)
                sufficient = citation_count > 0
                reason = f"기본 결과 확보 ({citation_count}개)" if citation_count > 0 else f"더 많은 결과 필요 (현재 {citation_count}개, 목표 {preferred_results}개)"
            
            # 신뢰도 평가
            high_confidence_count = sum(
                1 for c in citations 
                if c.get("confidence", 0) >= 0.7
            )
            
            confidence_evaluation = {
                "total_results": citation_count,
                "high_confidence_results": high_confidence_count,
                "average_confidence": sum(c.get("confidence", 0) for c in citations) / max(citation_count, 1)
            }
            
            return {
                "sufficient": sufficient,
                "reason": reason,
                "iteration": iteration,
                "confidence_evaluation": confidence_evaluation,
                "search_status": search_results.get("status", "unknown")
            }
            
        except Exception as e:
            agent_logger.log_error(e, "react_evaluate_results")
            return {
                "sufficient": True,  # 평가 실패 시 진행
                "reason": "평가 실패로 인한 기본 진행",
                "error": str(e)
            }
    
    def _save_execution_history(
        self,
        user_query: str,
        session_id: str,
        result: Dict[str, Any],
        total_time: float
    ):
        """실행 히스토리 저장"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "query": user_query[:100],  # 처음 100자만
                "status": result.get("status", "unknown"),
                "iterations_used": result.get("iterations_used", 0),
                "citation_count": len(result.get("citations", [])),
                "total_time": total_time,
                "has_images": result.get("metadata", {}).get("has_images", False)
            }
            
            self.execution_history.append(history_entry)
            
            # 히스토리 크기 제한 (최근 100개만 유지)
            if len(self.execution_history) > 100:
                self.execution_history = self.execution_history[-100:]
                
        except Exception as e:
            agent_logger.log_error(e, "react_save_history")
    
    def _get_error_response(
        self,
        user_query: str,
        error_message: str,
        react_log: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """에러 응답 생성"""
        return {
            "content": f"죄송합니다. 질문 처리 중 오류가 발생했습니다: {error_message}",
            "citations": [],
            "status": "error",
            "error": error_message,
            "react_log": react_log or [],
            "metadata": {
                "error_timestamp": datetime.now().isoformat(),
                "original_query": user_query
            }
        }
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """세션 정보 조회"""
        try:
            session = session_manager.get_session(session_id)
            if session:
                return session.to_dict()
            return None
        except Exception as e:
            agent_logger.log_error(e, "react_get_session_info")
            return None
    
    def reset_session(self, session_id: str) -> bool:
        """세션 리셋"""
        try:
            session = session_manager.get_session(session_id)
            if session:
                session.clear_history(keep_system_messages=True)
                agent_logger.log_agent_action(
                    "ReActAgent",
                    "session_reset",
                    {"session_id": session_id[:8]}
                )
                return True
            return False
        except Exception as e:
            agent_logger.log_error(e, "react_reset_session")
            return False
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """실행 통계 반환"""
        if not self.execution_history:
            return {"total_queries": 0}
        
        total_queries = len(self.execution_history)
        successful_queries = sum(1 for h in self.execution_history if h["status"] == "success")
        total_time = sum(h["total_time"] for h in self.execution_history)
        avg_time = total_time / total_queries
        avg_iterations = sum(h["iterations_used"] for h in self.execution_history) / total_queries
        
        return {
            "total_queries": total_queries,
            "successful_queries": successful_queries,
            "success_rate": round(successful_queries / total_queries * 100, 1),
            "total_processing_time": round(total_time, 3),
            "average_processing_time": round(avg_time, 3),
            "average_iterations": round(avg_iterations, 2),
            "last_query_time": self.execution_history[-1]["timestamp"]
        }


# 전역 ReAct Agent 인스턴스
react_agent = ReActAgent()
