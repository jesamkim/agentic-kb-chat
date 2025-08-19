"""
Improved Action Agent
다단계 검색과 MCP Tool 호출 추적이 통합된 개선된 Action Agent
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time

from config.settings import settings
from src.utils.logger import agent_logger
from src.mcp.server import execute_mcp_tool_sync
from src.utils.citation import CitationCollection, CitationProcessor
from src.agents.multi_stage_search import multi_stage_search_executor
from src.mcp.tool_call_tracker import tool_call_tracker


class ImprovedActionAgent:
    """개선된 Action Agent - 다단계 검색 및 Tool 호출 추적"""
    
    def __init__(self):
        self.multi_stage_executor = multi_stage_search_executor
        self.tool_tracker = tool_call_tracker
        self.execution_history = []
        agent_logger.log_agent_action("ImprovedActionAgent", "initialized", {})
    
    def execute_enhanced_search_strategy(
        self,
        analysis_result: Dict[str, Any],
        max_results_per_query: Optional[int] = None,
        enable_rerank: Optional[bool] = None,
        ui_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        개선된 검색 전략 실행 - 다단계 검색 및 실시간 UI 업데이트
        
        Args:
            analysis_result: 개선된 Orchestration Agent의 분석 결과
            max_results_per_query: 쿼리당 최대 결과 수
            enable_rerank: ReRank 사용 여부
            ui_callback: UI 업데이트 콜백 함수
            
        Returns:
            통합된 검색 실행 결과
        """
        try:
            start_time = time.time()
            
            # UI 콜백 설정
            if ui_callback:
                self.tool_tracker.set_ui_callback(ui_callback)
                self.multi_stage_executor.set_ui_callback(ui_callback)  # 추가
            
            # ReRank 설정 결정
            if enable_rerank is None:
                enable_rerank = settings.knowledge_base.enable_rerank
            
            agent_logger.log_agent_action(
                "ImprovedActionAgent",
                "enhanced_search_start",
                {
                    "requires_additional_search": analysis_result.get("requires_additional_search", False),
                    "additional_queries_count": len(analysis_result.get("additional_search_queries", [])),
                    "enable_rerank": enable_rerank
                }
            )
            
            # 1단계: 다단계 검색 실행
            search_results = self._execute_multi_stage_search_with_tracking(
                analysis_result,
                max_results_per_query or analysis_result.get("max_results", 50)
            )
            
            # 2단계: ReRank 적용 (활성화된 경우)
            if enable_rerank and search_results.get("status") == "success":
                search_results = self._apply_rerank_with_tracking(
                    search_results,
                    analysis_result
                )
            
            # 3단계: 최종 결과 후처리
            final_results = self._post_process_search_results(
                search_results,
                analysis_result
            )
            
            # 실행 시간 계산
            total_time = time.time() - start_time
            final_results["total_execution_time"] = round(total_time, 3)
            
            # 실행 히스토리 저장
            self._save_enhanced_execution_history(analysis_result, final_results)
            
            agent_logger.log_agent_action(
                "ImprovedActionAgent",
                "enhanced_search_complete",
                {
                    "total_time": total_time,
                    "final_citation_count": len(final_results.get("citations", [])),
                    "search_stages": len(final_results.get("search_stages", []))
                }
            )
            
            return final_results
            
        except Exception as e:
            agent_logger.log_error(e, "enhanced_search_execution")
            return self._get_enhanced_error_response(str(e))
    
    def _execute_multi_stage_search_with_tracking(
        self,
        analysis_result: Dict[str, Any],
        primary_search_limit: int
    ) -> Dict[str, Any]:
        """Tool 호출 추적과 함께 다단계 검색 실행"""
        
        try:
            # 1차 검색 Tool 호출 추적 시작
            primary_call_id = self.tool_tracker.start_tool_call(
                tool_name="kb_search",
                parameters={
                    "query": analysis_result.get("primary_query", ""),
                    "max_results": primary_search_limit,
                    "search_type": analysis_result.get("search_type", "HYBRID")
                },
                stage="primary_search"
            )
            
            # 다단계 검색 실행
            search_results = self.multi_stage_executor.execute_multi_stage_search(
                analysis_result=analysis_result,
                max_additional_searches=analysis_result.get("max_additional_searches", 5),
                primary_search_limit=primary_search_limit
            )
            
            # 1차 검색 완료 처리
            primary_result = search_results.get("primary_results", {})
            self.tool_tracker.complete_tool_call(primary_call_id, primary_result)
            
            # 추가 검색들의 Tool 호출 추적
            additional_results = search_results.get("additional_results", [])
            for i, additional_result in enumerate(additional_results, 1):
                if additional_result.get("status") == "success":
                    # 추가 검색 Tool 호출 추적 (이미 완료된 것들을 기록)
                    additional_call_id = self.tool_tracker.start_tool_call(
                        tool_name="kb_search",
                        parameters={
                            "query": additional_result.get("query", ""),
                            "max_results": 20,
                            "search_type": "HYBRID"
                        },
                        stage=f"additional_search_{i}"
                    )
                    self.tool_tracker.complete_tool_call(additional_call_id, additional_result)
            
            return search_results
            
        except Exception as e:
            # 실패한 Tool 호출 처리
            if 'primary_call_id' in locals():
                self.tool_tracker.fail_tool_call(primary_call_id, str(e))
            raise
    
    def _apply_rerank_with_tracking(
        self,
        search_results: Dict[str, Any],
        analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ReRank 적용 및 Tool 호출 추적"""
        
        citations = search_results.get("citations", [])
        if len(citations) < 2:  # ReRank할 결과가 부족한 경우
            return search_results
        
        # ReRank Tool 호출 추적 시작
        rerank_call_id = self.tool_tracker.start_tool_call(
            tool_name="rerank",
            parameters={
                "query": analysis_result.get("primary_query", ""),
                "documents_count": len(citations),
                "top_k": settings.model.rerank_top_k
            },
            stage="rerank"
        )
        
        try:
            # ReRank 실행 (MCP 도구 호출)
            rerank_params = {
                "query": analysis_result.get("primary_query", ""),
                "citations": citations,
                "top_k": min(settings.model.rerank_top_k, len(citations))
            }
            
            rerank_result = execute_mcp_tool_sync("rerank_citations", rerank_params)
            
            if rerank_result.get("status") == "success":
                # ReRank된 결과로 업데이트
                reranked_citations = rerank_result.get("reranked_citations", citations)
                search_results["citations"] = reranked_citations
                search_results["rerank_applied"] = True
                search_results["rerank_time"] = rerank_result.get("rerank_time", 0)
                
                # Tool 호출 완료 처리
                self.tool_tracker.complete_tool_call(rerank_call_id, {
                    "reranked_count": len(reranked_citations),
                    "rerank_time": rerank_result.get("rerank_time", 0)
                })
            else:
                # ReRank 실패 시 원본 결과 유지
                self.tool_tracker.fail_tool_call(rerank_call_id, rerank_result.get("error", "Unknown error"))
            
            return search_results
            
        except Exception as e:
            # ReRank 실패 처리
            self.tool_tracker.fail_tool_call(rerank_call_id, str(e))
            agent_logger.log_error(e, "rerank_application")
            return search_results  # 원본 결과 반환
    
    def _post_process_search_results(
        self,
        search_results: Dict[str, Any],
        analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """검색 결과 후처리 및 메타데이터 추가"""
        
        try:
            citations = search_results.get("citations", [])
            
            # 의도 기반 Citation 점수 조정
            self._adjust_citation_scores_by_intent(citations, analysis_result)
            
            # 검색 품질 메트릭 계산
            quality_metrics = self._calculate_search_quality_metrics(
                citations, 
                analysis_result
            )
            
            # Tool 호출 통계 추가
            tool_statistics = self.tool_tracker.get_call_statistics()
            
            # 최종 결과 구성
            final_results = search_results.copy()
            final_results.update({
                "quality_metrics": quality_metrics,
                "tool_call_statistics": tool_statistics,
                "search_metadata": {
                    "primary_intent": analysis_result.get("primary_intent", "unknown"),
                    "complexity_level": analysis_result.get("complexity", "보통"),
                    "additional_searches_performed": len(search_results.get("additional_results", [])),
                    "rerank_applied": search_results.get("rerank_applied", False),
                    "total_search_stages": len(search_results.get("search_stages", []))
                }
            })
            
            return final_results
            
        except Exception as e:
            agent_logger.log_error(e, "search_result_post_processing")
            return search_results
    
    def _adjust_citation_scores_by_intent(
        self,
        citations: List[Dict[str, Any]],
        analysis_result: Dict[str, Any]
    ):
        """의도 기반 Citation 점수 조정"""
        
        primary_intent = analysis_result.get("primary_intent", "")
        key_entities = analysis_result.get("search_priorities", {}).get("key_entities", [])
        intent_keywords = analysis_result.get("search_priorities", {}).get("intent_keywords", [])
        
        for citation in citations:
            preview_text = citation.get("preview", "").lower()
            original_score = citation.get("final_score", citation.get("confidence", 0.5))
            
            # 의도별 가중치 적용
            intent_boost = 0.0
            
            # 키워드 매칭 보너스
            for keyword in intent_keywords:
                if keyword in preview_text:
                    intent_boost += 0.1
            
            # 핵심 엔티티 매칭 보너스
            for entity in key_entities:
                if entity.lower() in preview_text:
                    intent_boost += 0.15
            
            # 의도별 특별 보너스
            if primary_intent == "절차_문의" and any(word in preview_text for word in ["단계", "순서", "절차"]):
                intent_boost += 0.2
            elif primary_intent == "규정_확인" and any(word in preview_text for word in ["규정", "기준", "법령"]):
                intent_boost += 0.2
            
            # 최종 점수 업데이트 (최대 1.0으로 제한)
            citation["intent_adjusted_score"] = min(original_score + intent_boost, 1.0)
    
    def _calculate_search_quality_metrics(
        self,
        citations: List[Dict[str, Any]],
        analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """검색 품질 메트릭 계산"""
        
        if not citations:
            return {
                "overall_quality": 0.0,
                "coverage_score": 0.0,
                "relevance_score": 0.0,
                "diversity_score": 0.0
            }
        
        # 1. 관련성 점수 (평균 신뢰도)
        relevance_scores = [c.get("confidence", 0) for c in citations]
        relevance_score = sum(relevance_scores) / len(relevance_scores)
        
        # 2. 커버리지 점수 (키워드 커버리지)
        key_entities = analysis_result.get("search_priorities", {}).get("key_entities", [])
        covered_entities = 0
        
        for entity in key_entities:
            entity_covered = any(
                entity.lower() in citation.get("preview", "").lower() 
                for citation in citations
            )
            if entity_covered:
                covered_entities += 1
        
        coverage_score = covered_entities / max(len(key_entities), 1)
        
        # 3. 다양성 점수 (서로 다른 문서 수)
        unique_documents = set()
        for citation in citations:
            doc_id = citation.get("document_uri", citation.get("uri", citation.get("id", "")))
            if doc_id:
                unique_documents.add(doc_id)
        
        diversity_score = len(unique_documents) / len(citations)
        
        # 4. 전체 품질 점수
        overall_quality = (relevance_score * 0.4 + coverage_score * 0.4 + diversity_score * 0.2)
        
        return {
            "overall_quality": round(overall_quality, 3),
            "relevance_score": round(relevance_score, 3),
            "coverage_score": round(coverage_score, 3),
            "diversity_score": round(diversity_score, 3),
            "total_citations": len(citations),
            "unique_documents": len(unique_documents),
            "high_confidence_citations": sum(1 for c in citations if c.get("confidence", 0) >= 0.7)
        }
    
    def _save_enhanced_execution_history(
        self,
        analysis_result: Dict[str, Any],
        final_results: Dict[str, Any]
    ):
        """개선된 실행 히스토리 저장"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "primary_intent": analysis_result.get("primary_intent", "unknown"),
                "complexity_level": analysis_result.get("complexity", "보통"),
                "requires_additional_search": analysis_result.get("requires_additional_search", False),
                "additional_searches_performed": len(final_results.get("search_stages", [])) - 1,
                "final_citation_count": len(final_results.get("citations", [])),
                "total_execution_time": final_results.get("total_execution_time", 0),
                "quality_metrics": final_results.get("quality_metrics", {}),
                "rerank_applied": final_results.get("rerank_applied", False),
                "tool_calls_made": len(final_results.get("tool_call_statistics", {}).get("tool_statistics", {}))
            }
            
            self.execution_history.append(history_entry)
            
            # 히스토리 크기 제한 (최근 100개만 유지)
            if len(self.execution_history) > 100:
                self.execution_history = self.execution_history[-100:]
                
        except Exception as e:
            agent_logger.log_error(e, "enhanced_execution_history_save")
    
    def _get_enhanced_error_response(self, error_message: str) -> Dict[str, Any]:
        """개선된 에러 응답 생성"""
        return {
            "status": "error",
            "error": error_message,
            "citations": [],
            "search_stages": [],
            "quality_metrics": {
                "overall_quality": 0.0,
                "relevance_score": 0.0,
                "coverage_score": 0.0,
                "diversity_score": 0.0
            },
            "tool_call_statistics": self.tool_tracker.get_call_statistics(),
            "search_metadata": {
                "primary_intent": "unknown",
                "complexity_level": "unknown",
                "additional_searches_performed": 0,
                "rerank_applied": False,
                "total_search_stages": 0
            },
            "total_execution_time": 0,
            "error_timestamp": datetime.now().isoformat()
        }
    
    def get_enhanced_execution_stats(self) -> Dict[str, Any]:
        """개선된 실행 통계 반환"""
        if not self.execution_history:
            return {"total_executions": 0}
        
        total_executions = len(self.execution_history)
        
        # 기본 통계
        avg_execution_time = sum(h.get("total_execution_time", 0) for h in self.execution_history) / total_executions
        avg_citation_count = sum(h.get("final_citation_count", 0) for h in self.execution_history) / total_executions
        
        # 의도별 통계
        intent_stats = {}
        for history in self.execution_history:
            intent = history.get("primary_intent", "unknown")
            if intent not in intent_stats:
                intent_stats[intent] = {"count": 0, "avg_quality": 0, "total_quality": 0}
            
            intent_stats[intent]["count"] += 1
            quality = history.get("quality_metrics", {}).get("overall_quality", 0)
            intent_stats[intent]["total_quality"] += quality
        
        # 평균 품질 계산
        for intent, stats in intent_stats.items():
            stats["avg_quality"] = round(stats["total_quality"] / stats["count"], 3)
            del stats["total_quality"]
        
        # 추가 검색 통계
        additional_search_rate = sum(
            1 for h in self.execution_history 
            if h.get("requires_additional_search", False)
        ) / total_executions * 100
        
        avg_additional_searches = sum(
            h.get("additional_searches_performed", 0) 
            for h in self.execution_history
        ) / total_executions
        
        # 품질 통계
        quality_scores = [
            h.get("quality_metrics", {}).get("overall_quality", 0) 
            for h in self.execution_history
        ]
        avg_quality = sum(quality_scores) / len(quality_scores)
        
        return {
            "total_executions": total_executions,
            "average_execution_time": round(avg_execution_time, 3),
            "average_citation_count": round(avg_citation_count, 1),
            "average_quality_score": round(avg_quality, 3),
            "additional_search_rate": round(additional_search_rate, 1),
            "average_additional_searches": round(avg_additional_searches, 1),
            "intent_statistics": intent_stats,
            "tool_call_statistics": self.tool_tracker.get_call_statistics(),
            "last_execution_time": self.execution_history[-1]["timestamp"]
        }


# 전역 인스턴스
improved_action_agent = ImprovedActionAgent()
