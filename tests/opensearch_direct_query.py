#!/usr/bin/env python3
"""
OpenSearch Serverless에 직접 쿼리하여 Knowledge Base chunk와 파일명 매핑을 확인하는 스크립트
"""

import boto3
import json
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

def get_opensearch_client(collection_endpoint: str, region: str = 'us-west-2'):
    """OpenSearch Serverless 클라이언트 생성"""
    session = boto3.Session()
    credentials = session.get_credentials()
    
    # AWS 인증 설정 수정
    awsauth = AWSRequestsAuth(
        aws_access_key=credentials.access_key,
        aws_secret_access_key=credentials.secret_key,
        aws_token=credentials.token,
        aws_region=region,
        aws_service='aoss'
    )
    
    client = OpenSearch(
        hosts=[{'host': collection_endpoint.replace('https://', ''), 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )
    
    return client

def search_all_documents(client, index_name: str, size: int = 10):
    """모든 문서 검색"""
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

def search_by_text(client, index_name: str, query_text: str, size: int = 10):
    """텍스트로 검색"""
    search_body = {
        "query": {
            "match": {
                "AMAZON_BEDROCK_TEXT": query_text
            }
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

def get_index_mapping(client, index_name: str):
    """인덱스 매핑 정보 조회"""
    try:
        response = client.indices.get_mapping(index=index_name)
        return response
    except Exception as e:
        print(f"매핑 조회 오류: {str(e)}")
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
        print(f"메타데이터:")
        
        # S3 URI 추출
        source_uri = metadata.get('x-amz-bedrock-kb-source-uri', 'N/A')
        if source_uri != 'N/A':
            file_name = source_uri.split('/')[-1]
            print(f"  - 파일명: {file_name}")
            print(f"  - S3 URI: {source_uri}")
        
        # 페이지 번호
        page_number = metadata.get('x-amz-bedrock-kb-document-page-number', 'N/A')
        print(f"  - 페이지 번호: {page_number}")
        
        # 데이터 소스 ID
        data_source_id = metadata.get('x-amz-bedrock-kb-data-source-id', 'N/A')
        print(f"  - 데이터 소스 ID: {data_source_id}")
        
        print("-" * 80)

def main():
    """메인 함수"""
    collection_endpoint = "https://xtl0nz46hgtplj8lkys6.us-west-2.aoss.amazonaws.com"
    index_name = "bedrock-knowledge-base-default-index"
    
    print("=== OpenSearch Serverless 직접 쿼리 ===\n")
    
    # OpenSearch 클라이언트 생성
    try:
        client = get_opensearch_client(collection_endpoint)
        print("OpenSearch 클라이언트 연결 성공!")
    except Exception as e:
        print(f"OpenSearch 클라이언트 연결 실패: {str(e)}")
        return
    
    # 인덱스 매핑 정보 조회
    print(f"\n인덱스 '{index_name}' 매핑 정보 조회 중...")
    mapping = get_index_mapping(client, index_name)
    if mapping:
        print("매핑 정보 조회 성공!")
        # 매핑 정보의 주요 필드만 출력
        try:
            properties = mapping[index_name]['mappings']['properties']
            print("사용 가능한 필드:")
            for field_name in properties.keys():
                print(f"  - {field_name}")
        except KeyError:
            print("매핑 구조를 파싱할 수 없습니다.")
    
    while True:
        print("\n" + "=" * 60)
        print("1. 모든 문서 검색")
        print("2. 텍스트로 검색")
        print("3. 종료")
        
        choice = input("\n선택하세요 (1-3): ").strip()
        
        if choice == '1':
            size = input("검색할 문서 수 (기본값: 5): ").strip()
            size = int(size) if size.isdigit() else 5
            
            print(f"\n모든 문서 검색 중... (최대 {size}개)")
            response = search_all_documents(client, index_name, size)
            display_results(response)
            
        elif choice == '2':
            query_text = input("검색할 텍스트를 입력하세요: ").strip()
            if not query_text:
                print("검색 텍스트를 입력해주세요.")
                continue
                
            size = input("검색할 문서 수 (기본값: 5): ").strip()
            size = int(size) if size.isdigit() else 5
            
            print(f"\n'{query_text}' 검색 중... (최대 {size}개)")
            response = search_by_text(client, index_name, query_text, size)
            display_results(response)
            
        elif choice == '3':
            print("프로그램을 종료합니다.")
            break
            
        else:
            print("잘못된 선택입니다. 1-3 중에서 선택해주세요.")

if __name__ == "__main__":
    main()
