"""
Multi-Stage Search Executor - Fixed Version
Citation 처리 메서드명을 수정한 버전
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
    """다단계 검색 실행기 - 수정된 버전"""
    
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
