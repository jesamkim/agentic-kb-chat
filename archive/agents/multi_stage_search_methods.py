"""
Multi-Stage Search Executor - 나머지 메서드들
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import time

from src.utils.logger import agent_logger


class MultiStageSearchMethods:
    """다단계 검색의 나머지 메서드들"""
    
    def _integrate_search_results(
        self,
        primary_results: Dict[str, Any],
        additional_results: List[Dict[str, Any]],
        analysis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """검색 결과 통합 및 중복 제거"""
        
        try:
            # 모든 Citation 수집
            all_citations = []
            
            # 1차 검색 결과 추가 (우선순위 높음)
            primary_citations = primary_results.get("citations", [])
            for citation in primary_citations:
                citation["source_stage"] = "primary"
                citation["priority_score"] = 1.0
                all_citations.append(citation)
            
            # 추가 검색 결과 추가
            for i, additional_result in enumerate(additional_results):
                if additional_result.get("status") == "success":
                    additional_citations = additional_result.get("citations", [])
                    for citation in additional_citations:
                        citation["source_stage"] = f"additional_{i+1}"
                        citation["priority_score"] = 0.8 - (i * 0.1)  # 순서에 따라 우선순위 감소
                        all_citations.append(citation)
            
            # 중복 제거
            deduplicated_citations = self._deduplicate_citations(all_citations)
            
            # 의도 기반 우선순위 정렬
            prioritized_citations = self._prioritize_citations_by_intent(
                deduplicated_citations, 
                analysis_result
            )
            
            # 최종 결과 구성
            integrated_result = {
                "status": "success",
                "citations": prioritized_citations,
                "total_citations": len(prioritized_citations),
                "deduplication_stats": {
                    "original_count": len(all_citations),
                    "deduplicated_count": len(deduplicated_citations),
                    "final_count": len(prioritized_citations),
                    "deduplication_ratio": round(
                        (len(all_citations) - len(deduplicated_citations)) / max(len(all_citations), 1) * 100, 1
                    )
                }
            }
            
            return integrated_result
            
        except Exception as e:
            agent_logger.log_error(e, "search_result_integration")
            return {
                "status": "error",
                "error": str(e),
                "citations": primary_results.get("citations", [])
            }
    
    def _is_duplicate_citation(
        self, 
        citation: Dict[str, Any], 
        existing_citations: List[Dict[str, Any]]
    ) -> bool:
        """Citation 중복 여부 확인"""
        
        citation_id = citation.get("id", "")
        citation_uri = citation.get("uri", citation.get("document_uri", ""))
        citation_text = citation.get("preview", "")[:200]  # 처음 200자만 비교
        
        for existing in existing_citations:
            # 1. ID 기반 중복 확인
            if citation_id and citation_id == existing.get("id", ""):
                return True
            
            # 2. URI 기반 중복 확인
            existing_uri = existing.get("uri", existing.get("document_uri", ""))
            if citation_uri and citation_uri == existing_uri:
                return True
            
            # 3. 텍스트 유사도 기반 중복 확인 (간단한 방식)
            existing_text = existing.get("preview", "")[:200]
            if citation_text and existing_text:
                similarity = self._calculate_text_similarity(citation_text, existing_text)
                if similarity > 0.9:  # 90% 이상 유사하면 중복으로 판단
                    return True
        
        return False
    
    def _deduplicate_citations(self, citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Citation 중복 제거"""
        
        deduplicated = []
        seen_ids = set()
        seen_uris = set()
        
        # 우선순위 순으로 정렬 (priority_score 높은 순)
        sorted_citations = sorted(
            citations, 
            key=lambda x: x.get("priority_score", 0), 
            reverse=True
        )
        
        for citation in sorted_citations:
            citation_id = citation.get("id", "")
            citation_uri = citation.get("uri", citation.get("document_uri", ""))
            
            # ID 기반 중복 확인
            if citation_id and citation_id in seen_ids:
                continue
            
            # URI 기반 중복 확인
            if citation_uri and citation_uri in seen_uris:
                continue
            
            # 텍스트 기반 중복 확인
            is_duplicate = False
            citation_text = citation.get("preview", "")[:200]
            
            for existing in deduplicated:
                existing_text = existing.get("preview", "")[:200]
                if citation_text and existing_text:
                    similarity = self._calculate_text_similarity(citation_text, existing_text)
                    if similarity > 0.9:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                deduplicated.append(citation)
                if citation_id:
                    seen_ids.add(citation_id)
                if citation_uri:
                    seen_uris.add(citation_uri)
        
        return deduplicated
    
    def _prioritize_citations_by_intent(
        self, 
        citations: List[Dict[str, Any]], 
        analysis_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """의도 기반 Citation 우선순위 정렬"""
        
        primary_intent = analysis_result.get("primary_intent", "")
        key_entities = analysis_result.get("key_entities", [])
        
        # 각 Citation에 의도 기반 점수 부여
        for citation in citations:
            intent_score = 0.0
            preview_text = citation.get("preview", "").lower()
            
            # 1. 의도별 키워드 매칭
            intent_keywords = {
                "절차_문의": ["절차", "단계", "프로세스", "방법", "순서"],
                "규정_확인": ["규정", "기준", "법령", "조항", "요구사항"],
                "기술_질문": ["기술", "방법", "해결책", "구현", "적용"],
                "비교_분석": ["비교", "차이점", "장단점", "선택", "기준"],
                "문제_해결": ["해결", "대응", "조치", "방안", "처리"]
            }
            
            if primary_intent in intent_keywords:
                for keyword in intent_keywords[primary_intent]:
                    if keyword in preview_text:
                        intent_score += 0.2
            
            # 2. 핵심 엔티티 매칭
            for entity in key_entities:
                if entity.lower() in preview_text:
                    intent_score += 0.3
            
            # 3. 기존 우선순위 점수와 결합
            original_score = citation.get("priority_score", 0.5)
            citation["final_score"] = original_score + intent_score
        
        # 최종 점수 기준으로 정렬
        sorted_citations = sorted(
            citations,
            key=lambda x: (
                x.get("final_score", 0),
                x.get("confidence", 0),
                -x.get("index", 999)  # 인덱스는 낮을수록 좋음
            ),
            reverse=True
        )
        
        return sorted_citations
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """간단한 텍스트 유사도 계산 (Jaccard 유사도)"""
        if not text1 or not text2:
            return 0.0
        
        # 단어 단위로 분할
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        # Jaccard 유사도 계산
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_deduplication_ratio(
        self,
        primary_results: Dict[str, Any],
        additional_results: List[Dict[str, Any]],
        integrated_results: Dict[str, Any]
    ) -> float:
        """중복 제거 비율 계산"""
        
        total_original = len(primary_results.get("citations", []))
        for result in additional_results:
            total_original += len(result.get("citations", []))
        
        final_count = len(integrated_results.get("citations", []))
        
        if total_original == 0:
            return 0.0
        
        return round((total_original - final_count) / total_original * 100, 1)
    
    def _save_execution_history(
        self, 
        analysis_result: Dict[str, Any], 
        final_result: Dict[str, Any]
    ):
        """실행 히스토리 저장"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "primary_intent": analysis_result.get("primary_intent", "unknown"),
                "requires_additional_search": analysis_result.get("requires_additional_search", False),
                "search_stages": len(self.search_stages),
                "final_citation_count": len(final_result.get("citations", [])),
                "total_search_time": final_result.get("metadata", {}).get("total_search_time", 0),
                "deduplication_ratio": final_result.get("metadata", {}).get("deduplication_ratio", 0)
            }
            
            self.execution_history.append(history_entry)
            
            # 히스토리 크기 제한 (최근 50개만 유지)
            if len(self.execution_history) > 50:
                self.execution_history = self.execution_history[-50:]
                
        except Exception as e:
            agent_logger.log_error(e, "save_execution_history")
    
    def _get_error_result(self, error_message: str) -> Dict[str, Any]:
        """에러 결과 반환"""
        return {
            "status": "error",
            "error": error_message,
            "citations": [],
            "search_stages": [stage.to_dict() for stage in self.search_stages],
            "metadata": {
                "total_search_time": 0,
                "primary_result_count": 0,
                "additional_search_count": 0,
                "final_citation_count": 0
            }
        }
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """실행 통계 반환"""
        if not self.execution_history:
            return {"total_executions": 0}
        
        total_executions = len(self.execution_history)
        avg_search_time = sum(h.get("total_search_time", 0) for h in self.execution_history) / total_executions
        avg_citation_count = sum(h.get("final_citation_count", 0) for h in self.execution_history) / total_executions
        additional_search_rate = sum(1 for h in self.execution_history if h.get("requires_additional_search", False)) / total_executions * 100
        
        return {
            "total_executions": total_executions,
            "average_search_time": round(avg_search_time, 3),
            "average_citation_count": round(avg_citation_count, 1),
            "additional_search_rate": round(additional_search_rate, 1),
            "last_execution_time": self.execution_history[-1]["timestamp"]
        }
