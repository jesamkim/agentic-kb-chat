#!/usr/bin/env python3
"""
Amazon Bedrock Knowledge Base에서 특정 chunk의 원본 파일명을 조회하는 스크립트
"""

import boto3
import json
from typing import List, Dict, Any

def retrieve_chunks_with_metadata(knowledge_base_id: str, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Bedrock Knowledge Base에서 chunk를 검색하고 메타데이터를 반환
    
    Args:
        knowledge_base_id: Knowledge Base ID
        query: 검색 쿼리
        max_results: 최대 결과 수
    
    Returns:
        검색 결과와 메타데이터 리스트
    """
    bedrock_agent = boto3.client('bedrock-agent-runtime', region_name='us-west-2')
    
    try:
        response = bedrock_agent.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={
                'text': query
            },
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': max_results
                }
            }
        )
        
        results = []
        for i, result in enumerate(response['retrievalResults']):
            chunk_info = {
                'rank': i + 1,
                'score': result.get('score', 0),
                'content': result['content']['text'][:200] + '...' if len(result['content']['text']) > 200 else result['content']['text'],
                'full_content': result['content']['text'],
                'location': result['location'],
                'metadata': result.get('metadata', {})
            }
            
            # S3 URI에서 파일명 추출
            if 'location' in result and 's3Location' in result['location']:
                s3_uri = result['location']['s3Location']['uri']
                file_name = s3_uri.split('/')[-1]
                chunk_info['file_name'] = file_name
                chunk_info['s3_uri'] = s3_uri
            
            results.append(chunk_info)
        
        return results
        
    except Exception as e:
        print(f"Error retrieving chunks: {str(e)}")
        return []

def search_opensearch_directly(collection_endpoint: str, index_name: str, query: str) -> List[Dict[str, Any]]:
    """
    OpenSearch Serverless에 직접 쿼리하여 chunk 정보 조회
    
    Args:
        collection_endpoint: OpenSearch 컬렉션 엔드포인트
        index_name: 인덱스 이름
        query: 검색 쿼리
    
    Returns:
        검색 결과 리스트
    """
    from opensearchpy import OpenSearch, RequestsHttpConnection
    from aws_requests_auth.aws_auth import AWSRequestsAuth
    
    # AWS 인증 설정
    session = boto3.Session()
    credentials = session.get_credentials()
    awsauth = AWSRequestsAuth(credentials, 'us-west-2', 'aoss')
    
    # OpenSearch 클라이언트 생성
    client = OpenSearch(
        hosts=[{'host': collection_endpoint.replace('https://', ''), 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )
    
    try:
        # 모든 문서 검색 (메타데이터 포함)
        search_body = {
            "query": {
                "match_all": {}
            },
            "size": 100,
            "_source": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
        }
        
        if query:
            search_body["query"] = {
                "match": {
                    "AMAZON_BEDROCK_TEXT": query
                }
            }
        
        response = client.search(
            index=index_name,
            body=search_body
        )
        
        results = []
        for hit in response['hits']['hits']:
            source = hit['_source']
            chunk_info = {
                'id': hit['_id'],
                'score': hit['_score'],
                'content': source.get('AMAZON_BEDROCK_TEXT', '')[:200] + '...',
                'full_content': source.get('AMAZON_BEDROCK_TEXT', ''),
                'metadata': source.get('AMAZON_BEDROCK_METADATA', {})
            }
            
            # 메타데이터에서 S3 URI 추출
            metadata = source.get('AMAZON_BEDROCK_METADATA', {})
            if 'location' in metadata and 's3Location' in metadata['location']:
                s3_uri = metadata['location']['s3Location']['uri']
                file_name = s3_uri.split('/')[-1]
                chunk_info['file_name'] = file_name
                chunk_info['s3_uri'] = s3_uri
            
            results.append(chunk_info)
        
        return results
        
    except Exception as e:
        print(f"Error searching OpenSearch: {str(e)}")
        return []

def main():
    """메인 함수"""
    knowledge_base_id = "CQLBN9MFDZ"
    collection_endpoint = "https://xtl0nz46hgtplj8lkys6.us-west-2.aoss.amazonaws.com"
    index_name = "bedrock-knowledge-base-default-index"
    
    print("=== Amazon Bedrock Knowledge Base Chunk 파일명 조회 ===\n")
    
    # 사용자 입력
    query = input("검색할 내용을 입력하세요 (전체 조회는 엔터): ").strip()
    if not query:
        query = "*"  # 전체 검색
    
    print(f"\n검색 쿼리: {query}")
    print("=" * 60)
    
    # 방법 1: Bedrock Knowledge Base API 사용
    print("\n[방법 1] Bedrock Knowledge Base Retrieve API 사용:")
    print("-" * 50)
    
    chunks = retrieve_chunks_with_metadata(knowledge_base_id, query, max_results=5)
    
    if chunks:
        for chunk in chunks:
            print(f"순위: {chunk['rank']}")
            print(f"점수: {chunk['score']:.4f}")
            print(f"파일명: {chunk.get('file_name', 'N/A')}")
            print(f"S3 URI: {chunk.get('s3_uri', 'N/A')}")
            print(f"내용 미리보기: {chunk['content']}")
            print(f"메타데이터: {json.dumps(chunk['metadata'], indent=2, ensure_ascii=False)}")
            print("-" * 50)
    else:
        print("검색 결과가 없습니다.")
    
    # 방법 2: OpenSearch 직접 쿼리 (선택사항)
    try_opensearch = input("\nOpenSearch에 직접 쿼리하시겠습니까? (y/N): ").strip().lower()
    
    if try_opensearch == 'y':
        print("\n[방법 2] OpenSearch Serverless 직접 쿼리:")
        print("-" * 50)
        
        try:
            os_results = search_opensearch_directly(collection_endpoint, index_name, query if query != "*" else "")
            
            if os_results:
                for i, result in enumerate(os_results[:5], 1):
                    print(f"문서 {i}:")
                    print(f"ID: {result['id']}")
                    print(f"점수: {result['score']:.4f}")
                    print(f"파일명: {result.get('file_name', 'N/A')}")
                    print(f"S3 URI: {result.get('s3_uri', 'N/A')}")
                    print(f"내용 미리보기: {result['content']}")
                    print("-" * 50)
            else:
                print("OpenSearch 검색 결과가 없습니다.")
                
        except ImportError:
            print("OpenSearch 직접 쿼리를 위해서는 다음 패키지가 필요합니다:")
            print("pip install opensearch-py aws-requests-auth")

if __name__ == "__main__":
    main()
