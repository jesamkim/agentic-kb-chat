"""
Multi-Stage Search Executor - Complete Fixed Version
Citation 처리 메서드명을 수정하고 완전히 통합된 버전
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time
import hashlib

from config.settings import settings
from src.utils.logger import agent_logger
from src.mcp.server import execute_mcp_tool_sync
from src.utils.citation import CitationCollection, CitationProcessor, Citation
from src.mcp.kb_client import BedrockKBClient


class SearchStage:
    """검색 단계 정보"""
    
    def __init__(self, stage_type: str, query: str, stage_number: int = 0):
        self.stage_type = stage_type  # "primary" or "additional"
        self.query = query
        self.stage_number = stage_number
        self.start_time = None
        self.end_time = None
        self.results = []
        self.status = "pending"  # pending, running, completed, failed
        self.error_message = None
    
    def start(self):
        """검색 단계 시작"""
        self.start_time = datetime.now()
        self.status = "running"
    
    def complete(self, results: List[Dict[str, Any]]):
        """검색 단계 완료"""
        self.end_time = datetime.now()
        self.results = results
        self.status = "completed"
    
    def fail(self, error_message: str):
        """검색 단계 실패"""
        self.end_time = datetime.now()
        self.status = "failed"
        self.error_message = error_message
    
    def get_duration(self) -> float:
        """검색 소요 시간 반환"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "stage_type": self.stage_type,
            "query": self.query,
            "stage_number": self.stage_number,
            "status": self.status,
            "duration": self.get_duration(),
            "result_count": len(self.results),
            "error_message": self.error_message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
        }


class MultiStageSearchExecutor:
    """다단계 검색 실행기 - 완전 수정된 버전"""
    
    def __init__(self):
        self.kb_client = BedrockKBClient()
        self.search_stages = []
        self.execution_history = []
        agent_logger.log_agent_action("MultiStageSearchExecutor", "initialized", {})
    
    def execute_multi_stage_search(
        self,
        analysis_result: Dict[str, Any],
        max_additional_searches: int = 5,
        primary_search_limit: int = 50
    ) -> Dict[str, Any]:
        """다단계 검색 실행"""
        try:
            start_time = time.time()
            self.search_stages = []
            
            # 원본 쿼리 추출
            original_query = analysis_result.get("original_query", "")
            if not original_query:
                original_query = analysis_result.get("search_queries", [""])[0]
            
            agent_logger.log_agent_action(
                "MultiStageSearchExecutor",
                "multi_stage_search_start",
                {
                    "original_query": original_query[:100],
                    "requires_additional_search": analysis_result.get("requires_additional_search", False),
                    "max_additional_searches": max_additional_searches
                }
            )
            
            # 1단계: 1차 하이브리드 검색 (50개)
            primary_results = self._perform_primary_search(
                original_query, 
                primary_search_limit
            )
            
            # 2단계: 추가 검색 필요성 판단 및 실행
            additional_results = []
            if analysis_result.get("requires_additional_search", False):
                additional_queries = analysis_result.get("additional_search_queries", [])
                if additional_queries:
                    additional_results = self._perform_additional_searches(
                        additional_queries[:max_additional_searches],
                        primary_results
                    )
            
            # 3단계: 검색 결과 통합 및 중복 제거
            integrated_results = self._integrate_search_results(
                primary_results,
                additional_results,
                analysis_result
            )
            
            # 실행 시간 계산
            total_time = time.time() - start_time
            
            # 결과 구성
            final_result = {
                "status": "success",
                "primary_results": primary_results,
                "additional_results": additional_results,
                "integrated_results": integrated_results,
                "citations": integrated_results.get("citations", []),
                "search_stages": [stage.to_dict() for stage in self.search_stages],
                "metadata": {
                    "total_search_time": round(total_time, 3),
                    "primary_result_count": len(primary_results.get("citations", [])),
                    "additional_search_count": len(additional_results),
                    "final_citation_count": len(integrated_results.get("citations", [])),
                    "deduplication_ratio": self._calculate_deduplication_ratio(
                        primary_results, additional_results, integrated_results
                    )
                }
            }
            
            # 실행 히스토리 저장
            self._save_execution_history(analysis_result, final_result)
            
            agent_logger.log_agent_action(
                "MultiStageSearchExecutor",
                "multi_stage_search_complete",
                {
                    "total_time": total_time,
                    "final_citation_count": len(integrated_results.get("citations", [])),
                    "search_stages": len(self.search_stages)
                }
            )
            
            return final_result
            
        except Exception as e:
            agent_logger.log_error(e, "multi_stage_search_execution")
            return self._get_error_result(str(e))
    
    def _perform_primary_search(
        self, 
        query: str, 
        max_results: int = 50
    ) -> Dict[str, Any]:
        """1차 하이브리드 검색 수행"""
        
        stage = SearchStage("primary", query, 1)
        self.search_stages.append(stage)
        stage.start()
        
        try:
            agent_logger.log_agent_action(
                "MultiStageSearchExecutor",
                "primary_search_start",
                {"query": query[:100], "max_results": max_results}
            )
            
            # KB 검색 실행
            search_results, search_time = self.kb_client.search_knowledge_base(
                query=query,
                max_results=max_results,
                search_type="HYBRID"
            )
            
            # Citation 처리 - 수정된 부분
            citations = []
            for result in search_results:
                try:
                    # Citation.from_kb_result 직접 사용
                    citation = Citation.from_kb_result(result)
                    citations.append(citation.to_dict())
                except Exception as e:
                    agent_logger.log_error(e, f"citation_processing_primary")
                    # 기본 Citation 생성
                    basic_citation = self._create_basic_citation(result)
                    if basic_citation:
                        citations.append(basic_citation)
            
            result = {
                "status": "success",
                "citations": citations,
                "search_time": search_time,
                "query": query,
                "search_type": "HYBRID",
                "result_count": len(citations)
            }
            
            stage.complete(citations)
            
            agent_logger.log_agent_action(
                "MultiStageSearchExecutor",
                "primary_search_complete",
                {
                    "result_count": len(citations),
                    "search_time": search_time
                }
            )
            
            return result
            
        except Exception as e:
            stage.fail(str(e))
            agent_logger.log_error(e, "primary_search")
            return {
                "status": "error",
                "error": str(e),
                "citations": [],
                "search_time": 0,
                "query": query
            }
    
    def _perform_additional_searches(
        self,
        additional_queries: List[str],
        primary_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """의도 기반 추가 검색 수행 - 수정된 버전"""
        
        additional_results = []
        primary_citations = primary_results.get("citations", [])
        
        for i, query in enumerate(additional_queries, 1):
            stage = SearchStage("additional", query, i)
            self.search_stages.append(stage)
            stage.start()
            
            try:
                agent_logger.log_agent_action(
                    "MultiStageSearchExecutor",
                    f"additional_search_{i}_start",
                    {"query": query[:100]}
                )
                
                # 중복 방지를 위한 필터링된 검색
                search_results, search_time = self.kb_client.search_knowledge_base(
                    query=query,
                    max_results=20,  # 추가 검색은 20개로 제한
                    search_type="HYBRID"
                )
                
                # Citation 처리 및 중복 제거 - 수정된 부분
                citations = []
                for result in search_results:
                    try:
                        # Citation.from_kb_result 직접 사용
                        citation = Citation.from_kb_result(result)
                        citation_dict = citation.to_dict()
                        
                        # 중복 확인
                        if not self._is_duplicate_citation(citation_dict, primary_citations):
                            citations.append(citation_dict)
                    except Exception as e:
                        agent_logger.log_error(e, f"citation_processing_additional_{i}")
                        # 기본 Citation 생성
                        basic_citation = self._create_basic_citation(result)
                        if basic_citation and not self._is_duplicate_citation(basic_citation, primary_citations):
                            citations.append(basic_citation)
                
                result = {
                    "status": "success",
                    "citations": citations,
                    "search_time": search_time,
                    "query": query,
                    "search_type": "HYBRID",
                    "result_count": len(citations),
                    "stage_number": i
                }
                
                additional_results.append(result)
                stage.complete(citations)
                
                agent_logger.log_agent_action(
                    "MultiStageSearchExecutor",
                    f"additional_search_{i}_complete",
                    {
                        "result_count": len(citations),
                        "search_time": search_time
                    }
                )
                
            except Exception as e:
                stage.fail(str(e))
                agent_logger.log_error(e, f"additional_search_{i}")
                
                error_result = {
                    "status": "error",
                    "error": str(e),
                    "citations": [],
                    "search_time": 0,
                    "query": query,
                    "stage_number": i
                }
                additional_results.append(error_result)
        
        return additional_results
    
    def _create_basic_citation(self, kb_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """기본 Citation 생성 (fallback)"""
        try:
            content = kb_result.get('content', {})
            metadata = kb_result.get('metadata', {})
            location = kb_result.get('location', {})
            
            # 기본 정보 추출
            document_uri = ""
            document_title = "Unknown Document"
            
            # S3 URI 추출
            if location and 's3Location' in location:
                document_uri = location['s3Location'].get('uri', '')
            elif 'x-amz-bedrock-kb-source-uri' in metadata:
                document_uri = metadata['x-amz-bedrock-kb-source-uri']
            
            # 파일명 추출
            if document_uri and document_uri.startswith('s3://'):
                filename = document_uri.split('/')[-1]
                if filename and '.' in filename:
                    try:
                        from urllib.parse import unquote
                        filename = unquote(filename)
                    except:
                        pass
                    document_title = filename
            
            # 페이지 번호
            page_number = metadata.get('x-amz-bedrock-kb-document-page-number')
            if page_number is not None:
                try:
                    page_number = int(float(page_number))
                except (ValueError, TypeError):
                    page_number = None
            
            return {
                "id": hashlib.md5(f"{document_uri}:{content.get('text', '')[:100]}".encode()).hexdigest()[:12],
                "document_uri": document_uri,
                "document_title": document_title,
                "uri": document_uri,
                "title": document_title,
                "preview": content.get('text', '')[:200],
                "confidence": kb_result.get('score', 0.0),
                "relevance": kb_result.get('score', 0.0),
                "page_number": page_number,
                "metadata": metadata,
                "location": location if location else {"s3Location": {"uri": document_uri}} if document_uri else {}
            }
            
        except Exception as e:
            agent_logger.log_error(e, "create_basic_citation")
            return None
    
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


# 전역 인스턴스
multi_stage_search_executor = MultiStageSearchExecutor()
