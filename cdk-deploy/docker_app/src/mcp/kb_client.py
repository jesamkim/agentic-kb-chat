"""
Bedrock Knowledge Base MCP 클라이언트
KB 검색 기능과 Citation 생성을 담당합니다.
"""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import List, Dict, Any, Optional, Tuple
import time
from datetime import datetime

from config.settings import settings
from src.utils.logger import mcp_logger
from src.utils.citation import Citation, CitationCollection, CitationProcessor


class BedrockKBClient:
    """Bedrock Knowledge Base 클라이언트"""
    
    def __init__(self, kb_id: Optional[str] = None, region: Optional[str] = None):
        self.kb_id = kb_id or settings.knowledge_base.kb_id
        self.region = region or settings.knowledge_base.region
        
        try:
            self.bedrock_agent_runtime = boto3.client(
                'bedrock-agent-runtime',
                region_name=self.region
            )
            mcp_logger.log_mcp_call("bedrock_client_init", {"kb_id": self.kb_id}, "success")
        except NoCredentialsError:
            mcp_logger.log_error(
                Exception("AWS credentials not found"), 
                "bedrock_client_init"
            )
            raise
        except Exception as e:
            mcp_logger.log_error(e, "bedrock_client_init")
            raise
    
    def search_knowledge_base(
        self,
        query: str,
        max_results: Optional[int] = None,
        search_type: Optional[str] = None,
        filter_criteria: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], float]:
        """
        Knowledge Base 검색 수행
        
        Args:
            query: 검색 쿼리
            max_results: 최대 결과 수 (기본값: settings에서 가져옴)
            search_type: 검색 타입 (HYBRID, SEMANTIC, LEXICAL)
            filter_criteria: 추가 필터 조건
            
        Returns:
            Tuple[검색 결과 리스트, 검색 소요 시간]
        """
        start_time = time.time()
        
        # 기본값 설정
        max_results = max_results or settings.knowledge_base.max_results
        search_type = search_type or settings.knowledge_base.search_type
        
        try:
            # 검색 파라미터 구성
            retrieve_params = {
                'knowledgeBaseId': self.kb_id,
                'retrievalQuery': {
                    'text': query
                },
                'retrievalConfiguration': {
                    'vectorSearchConfiguration': {
                        'numberOfResults': max_results,
                        'overrideSearchType': search_type
                    }
                }
            }
            
            # 필터 조건 추가 (있는 경우)
            if filter_criteria:
                retrieve_params['retrievalConfiguration']['vectorSearchConfiguration']['filter'] = filter_criteria
            
            mcp_logger.log_mcp_call(
                "kb_search_start", 
                {"query": query[:100], "max_results": max_results, "search_type": search_type}, 
                "initiated"
            )
            
            # KB 검색 실행
            response = self.bedrock_agent_runtime.retrieve(**retrieve_params)
            
            # 결과 추출
            results = response.get('retrievalResults', [])
            search_time = time.time() - start_time
            
            mcp_logger.log_kb_search(query, len(results), search_time)
            
            return results, search_time
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            mcp_logger.log_error(
                Exception(f"KB search failed: {error_code} - {error_message}"),
                "kb_search"
            )
            raise
            
        except Exception as e:
            mcp_logger.log_error(e, "kb_search")
            raise
    
    def search_and_create_citations(
        self,
        query: str,
        max_results: Optional[int] = None,
        search_type: Optional[str] = None,
        filter_criteria: Optional[Dict[str, Any]] = None
    ) -> Tuple[CitationCollection, float]:
        """
        KB 검색 후 Citation 생성
        
        Returns:
            Tuple[CitationCollection, 검색 소요 시간]
        """
        # KB 검색 수행
        kb_results, search_time = self.search_knowledge_base(
            query=query,
            max_results=max_results,
            search_type=search_type,
            filter_criteria=filter_criteria
        )
        
        # Citation 생성
        citations = CitationCollection()
        
        for result in kb_results:
            try:
                # KB 결과에서 Citation 생성 (이미지 지원 포함)
                citation = Citation.from_kb_result(result)
                citations.add_citation(citation)
                
            except Exception as e:
                mcp_logger.log_error(
                    Exception(f"Failed to create citation from KB result: {e}"),
                    "citation_creation"
                )
                continue
        
        # 중복 제거 및 정리
        citations.remove_duplicates()
        citations.merge_similar_citations()
        
        mcp_logger.log_citation_processing(
            len(citations), 
            len(kb_results) - len(citations)  # 제거된 중복 수
        )
        
        return citations, search_time
    
    def multi_query_search(
        self,
        queries: List[str],
        max_results_per_query: Optional[int] = None,
        search_type: Optional[str] = None
    ) -> Tuple[CitationCollection, List[float]]:
        """
        다중 쿼리 검색 (Orchestration Agent에서 사용)
        
        Args:
            queries: 검색 쿼리 리스트
            max_results_per_query: 쿼리당 최대 결과 수
            search_type: 검색 타입
            
        Returns:
            Tuple[통합된 CitationCollection, 각 쿼리별 검색 시간 리스트]
        """
        all_citations = CitationCollection()
        search_times = []
        
        mcp_logger.log_mcp_call(
            "multi_query_search",
            {"query_count": len(queries), "queries": [q[:50] for q in queries]},
            "started"
        )
        
        for i, query in enumerate(queries):
            try:
                citations, search_time = self.search_and_create_citations(
                    query=query,
                    max_results=max_results_per_query,
                    search_type=search_type
                )
                
                # Citation에 쿼리 정보 추가
                for citation in citations:
                    citation.metadata['source_query'] = query
                    citation.metadata['query_index'] = i
                
                all_citations.add_citations(list(citations))
                search_times.append(search_time)
                
            except Exception as e:
                mcp_logger.log_error(
                    Exception(f"Multi-query search failed for query {i}: {e}"),
                    "multi_query_search"
                )
                search_times.append(0.0)
                continue
        
        # 전체 결과 정리
        all_citations.remove_duplicates()
        all_citations.merge_similar_citations()
        
        total_time = sum(search_times)
        mcp_logger.log_performance(
            "multi_query_search",
            total_time,
            {"queries": len(queries), "total_citations": len(all_citations)}
        )
        
        return all_citations, search_times
    
    def get_kb_info(self) -> Dict[str, Any]:
        """Knowledge Base 정보 조회"""
        try:
            bedrock_agent = boto3.client('bedrock-agent', region_name=self.region)
            response = bedrock_agent.get_knowledge_base(knowledgeBaseId=self.kb_id)
            
            kb_info = response.get('knowledgeBase', {})
            
            return {
                'kb_id': self.kb_id,
                'name': kb_info.get('name', 'Unknown'),
                'description': kb_info.get('description', ''),
                'status': kb_info.get('status', 'Unknown'),
                'created_at': kb_info.get('createdAt'),
                'updated_at': kb_info.get('updatedAt'),
                'role_arn': kb_info.get('roleArn', ''),
                'knowledge_base_configuration': kb_info.get('knowledgeBaseConfiguration', {})
            }
            
        except Exception as e:
            mcp_logger.log_error(e, "get_kb_info")
            return {
                'kb_id': self.kb_id,
                'error': str(e)
            }
    
    def health_check(self) -> Dict[str, Any]:
        """KB 클라이언트 상태 확인"""
        try:
            # 간단한 테스트 쿼리로 연결 확인
            test_query = "test connection"
            start_time = time.time()
            
            response = self.bedrock_agent_runtime.retrieve(
                knowledgeBaseId=self.kb_id,
                retrievalQuery={'text': test_query},
                retrievalConfiguration={
                    'vectorSearchConfiguration': {
                        'numberOfResults': 1
                    }
                }
            )
            
            response_time = time.time() - start_time
            
            return {
                'status': 'healthy',
                'kb_id': self.kb_id,
                'region': self.region,
                'response_time': round(response_time, 3),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'kb_id': self.kb_id,
                'region': self.region,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


# 전역 KB 클라이언트 인스턴스
kb_client = BedrockKBClient()


# MCP 도구로 사용할 함수들
def search_knowledge_base_tool(
    query: str,
    max_results: int = None,
    search_type: str = None
) -> Dict[str, Any]:
    """
    MCP 도구: Knowledge Base 검색
    Strands Agents에서 @tool 데코레이터와 함께 사용
    """
    try:
        citations, search_time = kb_client.search_and_create_citations(
            query=query,
            max_results=max_results,
            search_type=search_type
        )
        
        # 응답용 포맷팅
        formatted_citations = CitationProcessor.format_citations_for_response(
            list(citations.get_top_citations(
                n=settings.citation.max_citations_per_response,
                min_confidence=settings.citation.min_confidence_score
            )),
            include_images=True
        )
        
        return {
            'status': 'success',
            'query': query,
            'search_time': round(search_time, 3),
            'total_results': len(citations),
            'citations': formatted_citations,
            'metadata': {
                'kb_id': kb_client.kb_id,
                'search_type': search_type or settings.knowledge_base.search_type,
                'max_results': max_results or settings.knowledge_base.max_results
            }
        }
        
    except Exception as e:
        mcp_logger.log_error(e, "search_knowledge_base_tool")
        return {
            'status': 'error',
            'query': query,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


def multi_search_knowledge_base_tool(
    queries: List[str],
    max_results_per_query: int = None
) -> Dict[str, Any]:
    """
    MCP 도구: 다중 쿼리 Knowledge Base 검색
    Orchestration Agent에서 사용
    """
    try:
        citations, search_times = kb_client.multi_query_search(
            queries=queries,
            max_results_per_query=max_results_per_query
        )
        
        # 응답용 포맷팅
        formatted_citations = CitationProcessor.format_citations_for_response(
            list(citations.get_top_citations(
                n=settings.citation.max_citations_per_response,
                min_confidence=settings.citation.min_confidence_score
            )),
            include_images=True
        )
        
        return {
            'status': 'success',
            'queries': queries,
            'search_times': [round(t, 3) for t in search_times],
            'total_search_time': round(sum(search_times), 3),
            'total_results': len(citations),
            'citations': formatted_citations,
            'metadata': {
                'kb_id': kb_client.kb_id,
                'query_count': len(queries)
            }
        }
        
    except Exception as e:
        mcp_logger.log_error(e, "multi_search_knowledge_base_tool")
        return {
            'status': 'error',
            'queries': queries,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
