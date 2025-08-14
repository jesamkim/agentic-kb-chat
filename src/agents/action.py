"""
Action Agent
MCP 도구를 호출하여 실제 KB 검색과 ReRank를 수행하는 Agent
ReAct 패턴의 Action 단계를 담당
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time

from config.settings import settings
from src.utils.logger import agent_logger
from src.mcp.server import execute_mcp_tool_sync
from src.utils.citation import CitationCollection, CitationProcessor


class ActionAgent:
    """MCP 도구 호출 및 실행 Agent"""
    
    def __init__(self):
        self.execution_history = []
        agent_logger.log_agent_action("ActionAgent", "initialized", {})
    
    def execute_search_strategy(
        self,
        analysis_result: Dict[str, Any],
        max_results_per_query: Optional[int] = None,
        enable_rerank: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        분석 결과를 바탕으로 검색 전략 실행
        
        Args:
            analysis_result: Orchestration Agent의 분석 결과
            max_results_per_query: 쿼리당 최대 결과 수
            enable_rerank: ReRank 사용 여부
            
        Returns:
            검색 실행 결과
        """
        try:
            start_time = time.time()
            
            search_strategy = analysis_result.get("search_strategy", "직접검색")
            search_queries = analysis_result.get("search_queries", [])
            
            # ReRank 설정 결정 (설정값 우선, 파라미터로 오버라이드 가능)
            if enable_rerank is None:
                enable_rerank = settings.knowledge_base.enable_rerank
            
            agent_logger.log_agent_action(
                "ActionAgent",
                "execute_search_strategy_start",
                {
                    "strategy": search_strategy,
                    "query_count": len(search_queries),
                    "enable_rerank": enable_rerank
                }
            )
            
            # 검색 전략에 따른 실행
            if search_strategy == "직접검색" and len(search_queries) == 1:
                result = self._execute_single_search(
                    search_queries[0],
                    max_results_per_query,
                    enable_rerank
                )
            elif search_strategy in ["분할검색", "단계적검색"] or len(search_queries) > 1:
                result = self._execute_multi_search(
                    search_queries,
                    max_results_per_query,
                    enable_rerank
                )
            else:
                # 기본값: 단일 검색
                query = search_queries[0] if search_queries else analysis_result.get("original_query", "")
                result = self._execute_single_search(
                    query,
                    max_results_per_query,
                    enable_rerank
                )
            
            # 실행 결과 보강
            execution_time = time.time() - start_time
            result.update({
                "analysis_result": analysis_result,
                "execution_time": round(execution_time, 3),
                "execution_timestamp": datetime.now().isoformat(),
                "search_strategy_used": search_strategy
            })
            
            # 실행 히스토리 저장
            self.execution_history.append({
                "timestamp": datetime.now().isoformat(),
                "strategy": search_strategy,
                "queries": search_queries,
                "result_count": len(result.get("citations", [])),
                "execution_time": execution_time
            })
            
            agent_logger.log_agent_action(
                "ActionAgent",
                "execute_search_strategy_complete",
                {
                    "strategy": search_strategy,
                    "total_results": len(result.get("citations", [])),
                    "execution_time": execution_time
                }
            )
            
            return result
            
        except Exception as e:
            agent_logger.log_error(e, "action_execute_search_strategy")
            return {
                "status": "error",
                "error": str(e),
                "citations": [],
                "analysis_result": analysis_result,
                "execution_timestamp": datetime.now().isoformat()
            }
    
    def _execute_single_search(
        self,
        query: str,
        max_results: Optional[int] = None,
        enable_rerank: Optional[bool] = None
    ) -> Dict[str, Any]:
        """단일 쿼리 검색 실행"""
        try:
            # ReRank 설정 결정
            if enable_rerank is None:
                enable_rerank = settings.knowledge_base.enable_rerank
                
            agent_logger.log_agent_action(
                "ActionAgent",
                "single_search_start",
                {"query": query[:50], "enable_rerank": enable_rerank}
            )
            
            # 통합 검색+ReRank 도구 사용 (권장)
            if enable_rerank:
                result = execute_mcp_tool_sync(
                    "search_and_rerank",
                    query=query,
                    max_results=max_results or settings.knowledge_base.max_results,
                    rerank_top_k=settings.model.rerank_top_k,
                    threshold=settings.knowledge_base.rerank_threshold
                )
            else:
                # ReRank 없이 KB 검색만
                result = execute_mcp_tool_sync(
                    "search_knowledge_base",
                    query=query,
                    max_results=max_results or settings.knowledge_base.max_results
                )
            
            agent_logger.log_agent_action(
                "ActionAgent",
                "single_search_complete",
                {
                    "status": result.get("status", "unknown"),
                    "result_count": len(result.get("citations", []))
                }
            )
            
            return result
            
        except Exception as e:
            agent_logger.log_error(e, "action_single_search")
            return {
                "status": "error",
                "error": str(e),
                "query": query,
                "citations": []
            }
    
    def _execute_multi_search(
        self,
        queries: List[str],
        max_results_per_query: Optional[int] = None,
        enable_rerank: Optional[bool] = None
    ) -> Dict[str, Any]:
        """다중 쿼리 검색 실행"""
        try:
            # ReRank 설정 결정
            if enable_rerank is None:
                enable_rerank = settings.knowledge_base.enable_rerank
                
            agent_logger.log_agent_action(
                "ActionAgent",
                "multi_search_start",
                {"query_count": len(queries), "enable_rerank": enable_rerank}
            )
            
            # 다중 검색 도구 사용
            result = execute_mcp_tool_sync(
                "multi_search_knowledge_base",
                queries=queries,
                max_results_per_query=max_results_per_query or (settings.knowledge_base.max_results // len(queries))
            )
            
            # ReRank 적용 (다중 검색 결과에 대해)
            if enable_rerank and result.get("status") == "success" and result.get("citations"):
                rerank_result = execute_mcp_tool_sync(
                    "rerank_search_results",
                    query=" ".join(queries),  # 모든 쿼리 결합
                    citations_data=result["citations"],
                    top_k=settings.model.rerank_top_k,
                    threshold=settings.knowledge_base.rerank_threshold
                )
                
                if rerank_result.get("status") == "success":
                    # ReRank 결과로 업데이트
                    result["citations"] = rerank_result["citations"]
                    result["rerank_applied"] = True
                    result["rerank_time"] = rerank_result.get("rerank_time", 0)
                    
                    # 메타데이터 업데이트
                    if "metadata" not in result:
                        result["metadata"] = {}
                    result["metadata"]["rerank_model"] = settings.model.rerank_model_id
            
            agent_logger.log_agent_action(
                "ActionAgent",
                "multi_search_complete",
                {
                    "status": result.get("status", "unknown"),
                    "result_count": len(result.get("citations", [])),
                    "rerank_applied": result.get("rerank_applied", False)
                }
            )
            
            return result
            
        except Exception as e:
            agent_logger.log_error(e, "action_multi_search")
            return {
                "status": "error",
                "error": str(e),
                "queries": queries,
                "citations": []
            }
    
    def execute_followup_search(
        self,
        original_result: Dict[str, Any],
        followup_queries: List[str],
        max_results: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        후속 검색 실행 (결과가 부족한 경우)
        
        Args:
            original_result: 원본 검색 결과
            followup_queries: 후속 검색 쿼리들
            max_results: 최대 결과 수
            
        Returns:
            통합된 검색 결과
        """
        try:
            agent_logger.log_agent_action(
                "ActionAgent",
                "followup_search_start",
                {"followup_query_count": len(followup_queries)}
            )
            
            # 후속 검색 실행
            followup_result = self._execute_multi_search(
                followup_queries,
                max_results,
                enable_rerank=True
            )
            
            # 원본 결과와 후속 결과 통합
            combined_result = self._combine_search_results(
                original_result,
                followup_result
            )
            
            agent_logger.log_agent_action(
                "ActionAgent",
                "followup_search_complete",
                {
                    "original_count": len(original_result.get("citations", [])),
                    "followup_count": len(followup_result.get("citations", [])),
                    "combined_count": len(combined_result.get("citations", []))
                }
            )
            
            return combined_result
            
        except Exception as e:
            agent_logger.log_error(e, "action_followup_search")
            return original_result  # 실패 시 원본 결과 반환
    
    def _combine_search_results(
        self,
        result1: Dict[str, Any],
        result2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """두 검색 결과를 통합"""
        try:
            # Citation 통합
            citations1 = result1.get("citations", [])
            citations2 = result2.get("citations", [])
            
            # CitationCollection을 사용하여 중복 제거
            combined_collection = CitationCollection()
            
            # 첫 번째 결과의 Citation들 추가
            for citation_data in citations1:
                try:
                    # Citation 객체 재구성 (간단한 방식)
                    from src.utils.citation import Citation
                    citation = Citation(
                        id=citation_data.get("id", ""),
                        document_uri=citation_data.get("uri", ""),
                        document_title=citation_data.get("title", ""),
                        chunk_text=citation_data.get("preview", ""),
                        confidence_score=citation_data.get("confidence", 0.0),
                        relevance_score=citation_data.get("relevance", 0.0)
                    )
                    combined_collection.add_citation(citation)
                except Exception:
                    continue
            
            # 두 번째 결과의 Citation들 추가
            for citation_data in citations2:
                try:
                    from src.utils.citation import Citation
                    citation = Citation(
                        id=citation_data.get("id", ""),
                        document_uri=citation_data.get("uri", ""),
                        document_title=citation_data.get("title", ""),
                        chunk_text=citation_data.get("preview", ""),
                        confidence_score=citation_data.get("confidence", 0.0),
                        relevance_score=citation_data.get("relevance", 0.0)
                    )
                    combined_collection.add_citation(citation)
                except Exception:
                    continue
            
            # 중복 제거 및 정리
            combined_collection.remove_duplicates()
            
            # 응답용 포맷팅
            formatted_citations = CitationProcessor.format_citations_for_response(
                list(combined_collection.get_top_citations(
                    n=settings.citation.max_citations_per_response,
                    min_confidence=settings.citation.min_confidence_score
                )),
                include_images=True
            )
            
            # 통합 결과 구성
            combined_result = {
                "status": "success",
                "citations": formatted_citations,
                "total_results": len(combined_collection),
                "search_time": result1.get("search_time", 0) + result2.get("search_time", 0),
                "rerank_time": result1.get("rerank_time", 0) + result2.get("rerank_time", 0),
                "combined": True,
                "metadata": {
                    "original_count": len(citations1),
                    "followup_count": len(citations2),
                    "combined_count": len(formatted_citations)
                }
            }
            
            return combined_result
            
        except Exception as e:
            agent_logger.log_error(e, "action_combine_results")
            # 통합 실패 시 첫 번째 결과 반환
            return result1
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """실행 통계 반환"""
        if not self.execution_history:
            return {"total_executions": 0}
        
        total_executions = len(self.execution_history)
        total_time = sum(h["execution_time"] for h in self.execution_history)
        avg_time = total_time / total_executions
        
        strategy_counts = {}
        for h in self.execution_history:
            strategy = h["strategy"]
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        return {
            "total_executions": total_executions,
            "total_execution_time": round(total_time, 3),
            "average_execution_time": round(avg_time, 3),
            "strategy_distribution": strategy_counts,
            "last_execution": self.execution_history[-1]["timestamp"]
        }


# 전역 Action Agent 인스턴스
action_agent = ActionAgent()
