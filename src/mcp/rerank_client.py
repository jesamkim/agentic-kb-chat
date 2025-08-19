"""
Cohere ReRank 클라이언트
KB 검색 결과의 순위를 재조정합니다.
"""

import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any, Optional, Tuple
import json
import time
from datetime import datetime

from config.settings import settings
from src.utils.logger import mcp_logger
from src.utils.citation import Citation, CitationCollection


class CohereRerankClient:
    """Cohere ReRank 클라이언트"""
    
    def __init__(self, model_id: Optional[str] = None, region: Optional[str] = None):
        self.model_id = model_id or settings.model.rerank_model_id
        self.region = region or settings.model.region
        self.top_k = settings.model.rerank_top_k
        
        try:
            self.bedrock_runtime = boto3.client(
                'bedrock-runtime',
                region_name=self.region
            )
            mcp_logger.log_mcp_call("rerank_client_init", {"model_id": self.model_id}, "success")
        except Exception as e:
            mcp_logger.log_error(e, "rerank_client_init")
            raise
    
    def rerank_documents(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        return_documents: bool = True
    ) -> Tuple[List[float], List[int], float]:
        """
        문서들을 쿼리에 대해 재순위 매김
        
        Args:
            query: 검색 쿼리
            documents: 재순위를 매길 문서 텍스트 리스트
            top_k: 상위 몇 개 결과를 반환할지
            return_documents: 문서 내용도 함께 반환할지
            
        Returns:
            Tuple[점수 리스트, 원본 인덱스 리스트, 처리 시간]
        """
        start_time = time.time()
        top_k = top_k or self.top_k
        
        if not documents:
            return [], [], 0.0
        
        try:
            # Cohere ReRank 요청 구성
            request_body = {
                "message": query,
                "documents": documents,
                "top_k": min(top_k, len(documents)),
                "return_documents": return_documents
            }
            
            mcp_logger.log_mcp_call(
                "rerank_start",
                {
                    "query": query[:100], 
                    "document_count": len(documents), 
                    "top_k": top_k
                },
                "initiated"
            )
            
            # Bedrock을 통해 Cohere ReRank 호출
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )
            
            # 응답 파싱
            response_body = json.loads(response['body'].read())
            results = response_body.get('results', [])
            
            # 점수와 인덱스 추출
            scores = []
            indices = []
            
            for result in results:
                scores.append(result.get('relevance_score', 0.0))
                indices.append(result.get('index', 0))
            
            rerank_time = time.time() - start_time
            
            mcp_logger.log_rerank(
                len(documents), 
                len(results), 
                rerank_time
            )
            
            return scores, indices, rerank_time
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            mcp_logger.log_error(
                Exception(f"ReRank failed: {error_code} - {error_message}"),
                "rerank_documents"
            )
            raise
            
        except Exception as e:
            mcp_logger.log_error(e, "rerank_documents")
            raise
    
    def rerank_citations(
        self,
        query: str,
        citations: CitationCollection,
        top_k: Optional[int] = None
    ) -> Tuple[CitationCollection, float]:
        """
        Citation들을 쿼리에 대해 재순위 매김
        
        Args:
            query: 검색 쿼리
            citations: 재순위를 매길 Citation 컬렉션
            top_k: 상위 몇 개 결과를 반환할지
            
        Returns:
            Tuple[재순위된 CitationCollection, 처리 시간]
        """
        if not citations or len(citations) == 0:
            return CitationCollection(), 0.0
        
        # Citation에서 텍스트 추출
        documents = []
        citation_list = list(citations)
        
        for citation in citation_list:
            # 텍스트와 이미지 alt_text 결합
            text_content = citation.chunk_text
            
            # 이미지가 있는 경우 alt_text도 포함
            if citation.has_images():
                image_texts = []
                for img in citation.images:
                    if img.alt_text:
                        image_texts.append(img.alt_text)
                    if img.caption:
                        image_texts.append(img.caption)
                
                if image_texts:
                    text_content += " " + " ".join(image_texts)
            
            documents.append(text_content)
        
        try:
            # ReRank 수행
            scores, indices, rerank_time = self.rerank_documents(
                query=query,
                documents=documents,
                top_k=top_k
            )
            
            # 재순위된 Citation 컬렉션 생성
            reranked_citations = CitationCollection()
            
            for i, (score, original_index) in enumerate(zip(scores, indices)):
                if original_index < len(citation_list):
                    citation = citation_list[original_index]
                    # ReRank 점수 업데이트
                    citation.confidence_score = score
                    citation.metadata['rerank_position'] = i + 1
                    citation.metadata['original_position'] = original_index + 1
                    
                    reranked_citations.add_citation(citation)
            
            return reranked_citations, rerank_time
            
        except Exception as e:
            mcp_logger.log_error(e, "rerank_citations")
            # ReRank 실패 시 원본 Citation 반환
            return citations, 0.0
    
    def rerank_with_threshold(
        self,
        query: str,
        citations: CitationCollection,
        threshold: Optional[float] = None,
        top_k: Optional[int] = None
    ) -> Tuple[CitationCollection, float]:
        """
        임계값을 적용한 Citation 재순위 매김
        
        Args:
            query: 검색 쿼리
            citations: Citation 컬렉션
            threshold: 최소 신뢰도 임계값
            top_k: 최대 결과 수
            
        Returns:
            Tuple[필터링된 CitationCollection, 처리 시간]
        """
        threshold = threshold or settings.knowledge_base.rerank_threshold
        
        # 먼저 재순위 매김
        reranked_citations, rerank_time = self.rerank_citations(
            query=query,
            citations=citations,
            top_k=top_k
        )
        
        # 임계값 적용
        filtered_citations = CitationCollection()
        
        for citation in reranked_citations:
            if citation.confidence_score >= threshold:
                filtered_citations.add_citation(citation)
        
        mcp_logger.log_mcp_call(
            "rerank_with_threshold",
            {
                "original_count": len(citations),
                "reranked_count": len(reranked_citations),
                "filtered_count": len(filtered_citations),
                "threshold": threshold
            },
            f"filtered {len(citations)} -> {len(filtered_citations)}"
        )
        
        return filtered_citations, rerank_time
    
    def health_check(self) -> Dict[str, Any]:
        """ReRank 클라이언트 상태 확인"""
        try:
            from config.settings import settings
            
            # ReRank가 비활성화된 경우
            if not settings.knowledge_base.enable_rerank:
                return {
                    'status': 'disabled',
                    'model_id': self.model_id,
                    'region': self.region,
                    'message': 'ReRank functionality is disabled in settings',
                    'timestamp': datetime.now().isoformat()
                }
            
            # 간단한 연결 테스트만 수행 (실제 API 호출 없이)
            # Bedrock 클라이언트가 정상적으로 초기화되었는지만 확인
            if hasattr(self, 'bedrock_runtime') and self.bedrock_runtime is not None:
                return {
                    'status': 'healthy',
                    'model_id': self.model_id,
                    'region': self.region,
                    'message': 'ReRank client initialized successfully',
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {
                    'status': 'unhealthy',
                    'model_id': self.model_id,
                    'region': self.region,
                    'error': 'Bedrock runtime client not initialized',
                    'timestamp': datetime.now().isoformat()
                }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'model_id': self.model_id,
                'region': self.region,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


# 전역 ReRank 클라이언트 인스턴스 (조건부 초기화)
try:
    from config.settings import settings
    if settings.knowledge_base.enable_rerank:
        rerank_client = CohereRerankClient()
    else:
        # ReRank가 비활성화된 경우 더미 클라이언트 생성
        class DisabledRerankClient:
            def __init__(self):
                self.model_id = "disabled"
                self.region = "disabled"
                
            def health_check(self):
                return {
                    'status': 'disabled',
                    'message': 'ReRank functionality is disabled in settings',
                    'timestamp': datetime.now().isoformat()
                }
            
            def rerank_documents(self, *args, **kwargs):
                return [], [], 0.0
            
            def rerank_citations(self, *args, **kwargs):
                # 원본 citations를 그대로 반환
                citations = kwargs.get('citations', [])
                return citations, 0.0
            
            def rerank_with_threshold(self, *args, **kwargs):
                # 원본 citations를 그대로 반환
                citations = kwargs.get('citations', [])
                return citations, 0.0
        
        rerank_client = DisabledRerankClient()
        
except Exception as e:
    # 초기화 실패 시 더미 클라이언트 생성
    class ErrorRerankClient:
        def __init__(self, error):
            self.error = error
            self.model_id = "error"
            self.region = "error"
        
        def health_check(self):
            return {
                'status': 'error',
                'error': str(self.error),
                'timestamp': datetime.now().isoformat()
            }
        
        def rerank_documents(self, *args, **kwargs):
            return [], [], 0.0
        
        def rerank_citations(self, *args, **kwargs):
            citations = kwargs.get('citations', [])
            return citations, 0.0
        
        def rerank_with_threshold(self, *args, **kwargs):
            citations = kwargs.get('citations', [])
            return citations, 0.0
        
        def rerank_with_threshold(self, *args, **kwargs):
            citations = kwargs.get('citations', [])
            return citations, 0.0
    
    rerank_client = ErrorRerankClient(e)


# MCP 도구로 사용할 함수들
def rerank_search_results_tool(
    query: str,
    citations_data: List[Dict[str, Any]],
    top_k: int = None,
    threshold: float = None
) -> Dict[str, Any]:
    """
    MCP 도구: 검색 결과 재순위 매김
    Strands Agents에서 @tool 데코레이터와 함께 사용
    """
    try:
        # Citation 딕셔너리에서 CitationCollection 재구성
        citations = CitationCollection()
        
        for citation_data in citations_data:
            try:
                # 기본 Citation 정보로 Citation 객체 생성
                citation = Citation(
                    id=citation_data.get('id', ''),
                    document_uri=citation_data.get('uri', ''),
                    document_title=citation_data.get('title', ''),
                    chunk_text=citation_data.get('preview', ''),
                    confidence_score=citation_data.get('confidence', 0.0),
                    relevance_score=citation_data.get('relevance', 0.0)
                )
                citations.add_citation(citation)
                
            except Exception as e:
                mcp_logger.log_error(
                    Exception(f"Failed to reconstruct citation: {e}"),
                    "rerank_tool_citation_reconstruction"
                )
                continue
        
        # ReRank 수행
        reranked_citations, rerank_time = rerank_client.rerank_with_threshold(
            query=query,
            citations=citations,
            threshold=threshold,
            top_k=top_k
        )
        
        # 응답용 포맷팅
        from src.utils.citation import CitationProcessor
        formatted_citations = CitationProcessor.format_citations_for_response(
            list(reranked_citations),
            include_images=True
        )
        
        return {
            'status': 'success',
            'query': query,
            'rerank_time': round(rerank_time, 3),
            'original_count': len(citations_data),
            'reranked_count': len(reranked_citations),
            'citations': formatted_citations,
            'metadata': {
                'model_id': rerank_client.model_id,
                'threshold': threshold or settings.knowledge_base.rerank_threshold,
                'top_k': top_k or settings.model.rerank_top_k
            }
        }
        
    except Exception as e:
        mcp_logger.log_error(e, "rerank_search_results_tool")
        return {
            'status': 'error',
            'query': query,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


def combined_search_and_rerank_tool(
    query: str,
    max_results: int = None,
    rerank_top_k: int = None,
    threshold: float = None
) -> Dict[str, Any]:
    """
    MCP 도구: KB 검색 + ReRank 통합 수행
    가장 일반적으로 사용될 도구
    """
    try:
        # KB 검색 수행
        from src.mcp.kb_client import kb_client
        
        citations, search_time = kb_client.search_and_create_citations(
            query=query,
            max_results=max_results
        )
        
        # ReRank 수행 (KB 검색 결과가 있는 경우에만)
        rerank_time = 0.0
        if len(citations) > 1:  # 결과가 2개 이상일 때만 ReRank 수행
            citations, rerank_time = rerank_client.rerank_with_threshold(
                query=query,
                citations=citations,
                threshold=threshold,
                top_k=rerank_top_k
            )
        
        # 응답용 포맷팅
        from src.utils.citation import CitationProcessor
        formatted_citations = CitationProcessor.format_citations_for_response(
            list(citations.get_top_citations(
                n=settings.citation.max_citations_per_response,
                min_confidence=threshold or settings.citation.min_confidence_score
            )),
            include_images=True
        )
        
        return {
            'status': 'success',
            'query': query,
            'search_time': round(search_time, 3),
            'rerank_time': round(rerank_time, 3),
            'total_time': round(search_time + rerank_time, 3),
            'total_results': len(citations),
            'citations': formatted_citations,
            'metadata': {
                'kb_id': kb_client.kb_id,
                'rerank_model': rerank_client.model_id,
                'threshold': threshold or settings.knowledge_base.rerank_threshold
            }
        }
        
    except Exception as e:
        mcp_logger.log_error(e, "combined_search_and_rerank_tool")
        return {
            'status': 'error',
            'query': query,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
