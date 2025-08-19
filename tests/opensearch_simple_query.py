#!/usr/bin/env python3
"""
OpenSearch Serverless에 직접 쿼리하여 Knowledge Base chunk와 파일명 매핑을 확인하는 스크립트 (간단 버전)
"""

import boto3
import json
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def get_opensearch_client(collection_endpoint: str, region: str = 'us-west-2'):
    """OpenSearch Serverless 클라이언트 생성"""
    session = boto3.Session()
    credentials = session.get_credentials()
    
    # AWS4Auth 사용
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        'aoss',
        session_token=credentials.token
    )
    
    host = collection_endpoint.replace('https://', '')
    
    client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30
    )
    
    return client

def search_documents(client, index_name: str, query_text: str = None, size: int = 5):
    """문서 검색"""
    if query_text:
        search_body = {
            "query": {
                "match": {
                    "AMAZON_BEDROCK_TEXT": query_text
                }
            },
            "size": size,
            "_source": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
        }
    else:
        search_body = {
            "query": {
                "match_all": {}
            },
            "size": size,
            "_source": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
        }
    
    try:
        response = client.search(index=index_name, body=search_body)
        return response
    except Exception as e:
        print(f"검색 오류: {str(e)}")
        return None

def display_results(response, max_content_length: int = 200):
    """검색 결과 출력"""
    if not response or 'hits' not in response:
        print("검색 결과가 없습니다.")
        return
    
    hits = response['hits']['hits']
    total = response['hits']['total']['value']
    
    print(f"총 {total}개의 문서를 찾았습니다.")
    print("=" * 80)
    
    for i, hit in enumerate(hits, 1):
        print(f"\n[문서 {i}]")
        print(f"문서 ID: {hit['_id']}")
        print(f"점수: {hit['_score']:.4f}")
        
        source = hit['_source']
        
        # 텍스트 내용
        text_content = source.get('AMAZON_BEDROCK_TEXT', '')
        if len(text_content) > max_content_length:
            text_preview = text_content[:max_content_length] + '...'
        else:
            text_preview = text_content
        
        print(f"내용 미리보기: {text_preview}")
        
        # 메타데이터
        metadata = source.get('AMAZON_BEDROCK_METADATA', {})
        
        # S3 URI 추출
        source_uri = metadata.get('x-amz-bedrock-kb-source-uri', 'N/A')
        if source_uri != 'N/A':
            file_name = source_uri.split('/')[-1]
            print(f"파일명: {file_name}")
            print(f"S3 URI: {source_uri}")
        
        # 페이지 번호
        page_number = metadata.get('x-amz-bedrock-kb-document-page-number', 'N/A')
        print(f"페이지 번호: {page_number}")
        
        # 데이터 소스 ID
        data_source_id = metadata.get('x-amz-bedrock-kb-data-source-id', 'N/A')
        print(f"데이터 소스 ID: {data_source_id}")
        
        print("-" * 80)

def main():
    """메인 함수"""
    collection_endpoint = "https://xtl0nz46hgtplj8lkys6.us-west-2.aoss.amazonaws.com"
    index_name = "bedrock-knowledge-base-default-index"
    
    print("=== OpenSearch Serverless 직접 쿼리 (간단 버전) ===\n")
    
    # OpenSearch 클라이언트 생성
    try:
        client = get_opensearch_client(collection_endpoint)
        print("OpenSearch 클라이언트 연결 성공!")
    except Exception as e:
        print(f"OpenSearch 클라이언트 연결 실패: {str(e)}")
        print("requests-aws4auth 패키지가 필요할 수 있습니다: pip install requests-aws4auth")
        return
    
    # 모든 문서 검색 (5개)
    print(f"\n모든 문서 검색 중... (최대 5개)")
    response = search_documents(client, index_name, size=5)
    display_results(response)
    
    # 특정 텍스트 검색
    print(f"\n\n'품질' 키워드로 검색 중... (최대 3개)")
    response = search_documents(client, index_name, query_text="품질", size=3)
    display_results(response)

if __name__ == "__main__":
    main()
