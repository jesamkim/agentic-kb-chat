"""
MCP RAG Chatbot - Advanced Streamlit UI
KB_ID 설정, 이미지 첨부, 진행 상황 표시, Citation 확장 기능 포함
"""

import streamlit as st
import sys
import os
import base64
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from PIL import Image
import io
import boto3
from botocore.exceptions import ClientError
import requests
from io import BytesIO
import pandas as pd
import re
from enum import Enum

# 프로젝트 루트를 Python path에 추가
sys.path.append('/Workshop/mcp-rag')

from src.agents.react_agent import ReActAgent
from src.utils.session import SessionManager
from config.settings import settings

# 페이지 설정
st.set_page_config(
    page_title="MCP RAG Chatbot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "react_agent" not in st.session_state:
    st.session_state.react_agent = None
if "session_manager" not in st.session_state:
    st.session_state.session_manager = None
if "kb_id" not in st.session_state:
    st.session_state.kb_id = "CQLBN9MFDZ"

def initialize_agents(kb_id: str):
    """Agent 및 세션 매니저 초기화"""
    try:
        # KB_ID 설정 업데이트
        settings.knowledge_base.kb_id = kb_id
        
        # Agent 초기화
        react_agent = ReActAgent()
        session_manager = SessionManager()
        
        return react_agent, session_manager
    except Exception as e:
        st.error(f"Agent 초기화 실패: {e}")
        return None, None

def encode_image_to_base64(image: Image.Image) -> str:
    """이미지를 base64로 인코딩"""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return img_str

class CitationType(Enum):
    TEXT = "text"
    TABLE = "table" 
    IMAGE = "image"
    IMAGE_TEXT = "image_text"

def get_opensearch_client(kb_id: str = None):
    """OpenSearch Serverless 클라이언트 생성"""
    try:
        # AWS 자격 증명 설정
        credentials = boto3.Session().get_credentials()
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            'us-west-2',  # 리전 설정
            'aoss',  # OpenSearch Serverless 서비스
            session_token=credentials.token
        )
        
        # KB ID로부터 Collection endpoint 조회
        if kb_id:
            collection_endpoint = get_kb_collection_endpoint(kb_id)
        else:
            # 기본 KB ID 사용
            collection_endpoint = get_kb_collection_endpoint(st.session_state.kb_id)
        
        if not collection_endpoint:
            print("Collection endpoint를 찾을 수 없습니다.")
            return None
        
        # https:// 제거하고 호스트명만 추출
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
    except Exception as e:
        print(f"OpenSearch 클라이언트 생성 실패: {e}")
        return None

def get_filename_from_opensearch(chunk_id: str) -> Optional[str]:
    """OpenSearch에서 chunk ID로 파일명 조회"""
    try:
        client = get_opensearch_client()
        if not client:
            return None
        
        # chunk ID로 문서 검색
        query = {
            "query": {
                "term": {
                    "_id": chunk_id
                }
            },
            "_source": ["x-amz-bedrock-kb-source-uri"]
        }
        
        response = client.search(
            index="bedrock-knowledge-base-default-index",
            body=query
        )
        
        if response['hits']['total']['value'] > 0:
            source_uri = response['hits']['hits'][0]['_source'].get('x-amz-bedrock-kb-source-uri', '')
            if source_uri and source_uri.startswith('s3://'):
                filename = source_uri.split('/')[-1]
                if filename:
                    return filename
        
        return None
        
    except Exception as e:
        print(f"OpenSearch 쿼리 실패: {e}")
        return None

def detect_table_content(text: str) -> bool:
    """텍스트가 테이블 형태인지 감지"""
    if not text:
        return False
    
    table_indicators = ['|', '\t', 'Table', 'table', '표', '테이블', '행', '열', 'row', 'column']
    indicator_count = sum(1 for indicator in table_indicators if indicator in text)
    
    lines = text.split('\n')
    structured_lines = sum(1 for line in lines if line.strip() and ('|' in line or '\t' in line))
    
    return (indicator_count > 0 and structured_lines > 2) or (structured_lines > len(lines) * 0.3)

def parse_table_content(text: str) -> Optional[pd.DataFrame]:
    """테이블 텍스트를 DataFrame으로 변환"""
    try:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not lines:
            return None
        
        # Markdown table
        if '|' in text:
            table_lines = [line for line in lines if '|' in line]
            if len(table_lines) >= 2:
                headers = [col.strip() for col in table_lines[0].split('|') if col.strip()]
                data = []
                for line in table_lines[2:]:
                    row = [col.strip() for col in line.split('|') if col.strip()]
                    if len(row) == len(headers):
                        data.append(row)
                if data:
                    return pd.DataFrame(data, columns=headers)
        
        # Tab separated
        if '\t' in text:
            try:
                from io import StringIO
                df = pd.read_csv(StringIO(text), sep='\t')
                if not df.empty:
                    return df
            except:
                pass
        
        return None
    except Exception as e:
        return None

def get_kb_collection_endpoint(kb_id: str) -> Optional[str]:
    """KB ID로부터 OpenSearch Collection endpoint 조회"""
    try:
        bedrock_agent = boto3.client('bedrock-agent', region_name='us-west-2')
        
        # Knowledge Base 정보 조회
        response = bedrock_agent.get_knowledge_base(knowledgeBaseId=kb_id)
        
        # Vector DB 설정에서 Collection ARN 추출
        storage_config = response['knowledgeBase']['storageConfiguration']
        if storage_config['type'] == 'OPENSEARCH_SERVERLESS':
            collection_arn = storage_config['opensearchServerlessConfiguration']['collectionArn']
            
            # ARN에서 Collection ID 추출
            # arn:aws:aoss:region:account:collection/collection-id
            collection_id = collection_arn.split('/')[-1]
            
            # Collection endpoint 구성
            region = collection_arn.split(':')[3]
            endpoint = f"https://{collection_id}.{region}.aoss.amazonaws.com"
            
            return endpoint
        
        return None
        
    except Exception as e:
        print(f"KB Collection endpoint 조회 실패: {e}")
        return None
    """텍스트가 테이블 형태인지 감지"""
    if not text:
        return False
    
    table_indicators = ['|', '\t', 'Table', 'table', '표', '테이블', '행', '열', 'row', 'column']
    indicator_count = sum(1 for indicator in table_indicators if indicator in text)
    
    lines = text.split('\n')
    structured_lines = sum(1 for line in lines if line.strip() and ('|' in line or '\t' in line))
    
    return (indicator_count > 0 and structured_lines > 2) or (structured_lines > len(lines) * 0.3)

def parse_table_content(text: str) -> Optional[pd.DataFrame]:
    """테이블 텍스트를 DataFrame으로 변환"""
    try:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not lines:
            return None
        
        # Markdown table
        if '|' in text:
            table_lines = [line for line in lines if '|' in line]
            if len(table_lines) >= 2:
                headers = [col.strip() for col in table_lines[0].split('|') if col.strip()]
                data = []
                for line in table_lines[2:]:
                    row = [col.strip() for col in line.split('|') if col.strip()]
                    if len(row) == len(headers):
                        data.append(row)
                if data:
                    return pd.DataFrame(data, columns=headers)
        
        # Tab separated
        if '\t' in text:
            try:
                from io import StringIO
                df = pd.read_csv(StringIO(text), sep='\t')
                if not df.empty:
                    return df
            except:
                pass
        
        return None
    except Exception as e:
        return None

def generate_presigned_url(s3_uri: str, expiration: int = 3600) -> Optional[str]:
    """S3 URI에서 presigned URL 생성"""
    try:
        if not s3_uri.startswith('s3://'):
            return None
        
        path_parts = s3_uri[5:].split('/', 1)
        if len(path_parts) != 2:
            return None
        
        bucket_name = path_parts[0]
        object_key = path_parts[1]
        
        s3_client = boto3.client('s3')
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_key},
            ExpiresIn=expiration
        )
        
        return presigned_url
    except Exception as e:
        st.error(f"Presigned URL 생성 실패: {e}")
        return None

def is_image_chunk(citation: Dict) -> bool:
    """Citation이 이미지 청크인지 확인"""
    content_type = citation.get('content_type', '')
    if 'image' in content_type.lower():
        return True
    
    uri_fields = ['uri', 'document_uri']
    for field in uri_fields:
        uri = citation.get(field, '')
        if uri and any(ext in uri.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            return True
    
    location = citation.get('location', {})
    if location:
        s3_location = location.get('s3Location', {})
        if s3_location:
            s3_uri = s3_location.get('uri', '')
            if s3_uri and any(ext in s3_uri.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                return True
    
    return False

def display_s3_image(s3_uri: str, caption: str = ""):
    """S3에 저장된 이미지를 표시"""
    try:
        presigned_url = generate_presigned_url(s3_uri)
        if presigned_url:
            st.image(presigned_url, caption=caption, use_column_width=True)
            return True
        else:
            st.warning(f"이미지를 불러올 수 없습니다: {s3_uri}")
            return False
    except Exception as e:
        st.error(f"이미지 표시 실패: {e}")
        return False

def classify_citation_type(citation: Dict) -> CitationType:
    """Citation 타입 자동 분류"""
    content = citation.get('preview', '') or citation.get('content', {}).get('text', '')
    
    if detect_table_content(content):
        return CitationType.TABLE
    elif is_image_chunk(citation):
        return CitationType.IMAGE
    else:
        return CitationType.TEXT

def debug_citation_data(citation: Dict, citation_num: int):
    """Citation 데이터 구조 디버깅 (개선된 버전)"""
    print(f"\n=== Citation {citation_num} Debug ===")
    print(f"전체 키: {list(citation.keys())}")
    
    # ID 확인
    chunk_id = citation.get('id', '')
    print(f"ID: {chunk_id}")
    
    # Document 정보 확인
    document_title = citation.get('document_title', '')
    document_uri = citation.get('document_uri', '')
    print(f"Document Title: {document_title}")
    print(f"Document URI: {document_uri}")
    
    # Title 및 URI 필드 확인
    title = citation.get('title', '')
    uri = citation.get('uri', '')
    print(f"Title: {title}")
    print(f"URI: {uri}")
    
    # 메타데이터 확인
    metadata = citation.get('metadata', {})
    if metadata:
        print(f"Metadata 키: {list(metadata.keys())}")
        source_uri = metadata.get('x-amz-bedrock-kb-source-uri', '')
        page_number = metadata.get('x-amz-bedrock-kb-document-page-number', '')
        data_source_id = metadata.get('x-amz-bedrock-kb-data-source-id', '')
        print(f"Source URI (metadata): {source_uri}")
        print(f"Page Number: {page_number}")
        print(f"Data Source ID: {data_source_id}")
    
    # Location 확인
    location = citation.get('location', {})
    if location:
        print(f"Location: {location}")
        s3_location = location.get('s3Location', {})
        if s3_location:
            s3_uri = s3_location.get('uri', '')
            print(f"S3 URI (location): {s3_uri}")
    
    # 파일명 추출 테스트
    extracted_filename = extract_filename_from_citation(citation)
    print(f"추출된 파일명: {extracted_filename}")
    
    print("=" * 50)

def extract_filename_from_citation(citation: Dict) -> str:
    """Citation에서 파일명 추출 (개선된 버전)"""
    
    # 1. Citation 객체의 document_title 사용 (가장 우선)
    document_title = citation.get('document_title', '')
    if document_title and document_title != 'Unknown Document' and '.' in document_title:
        return document_title
    
    # 2. Citation 객체의 document_uri에서 추출
    document_uri = citation.get('document_uri', '')
    if document_uri and document_uri.startswith('s3://'):
        filename = document_uri.split('/')[-1]
        if filename and '.' in filename:
            # URL 디코딩 처리
            try:
                from urllib.parse import unquote
                filename = unquote(filename)
            except:
                pass
            return filename
    
    # 3. Citation 객체의 title 필드 확인
    title = citation.get('title', '')
    if title and title != 'Unknown Document' and '.' in title:
        return title
    
    # 4. Citation 객체의 uri 필드 확인
    uri = citation.get('uri', '')
    if uri and uri.startswith('s3://'):
        filename = uri.split('/')[-1]
        if filename and '.' in filename:
            try:
                from urllib.parse import unquote
                filename = unquote(filename)
            except:
                pass
            return filename
    
    # 5. 메타데이터에서 직접 추출 (기존 로직 유지)
    metadata = citation.get('metadata', {})
    if metadata:
        source_uri = metadata.get('x-amz-bedrock-kb-source-uri', '')
        if source_uri and source_uri.startswith('s3://'):
            filename = source_uri.split('/')[-1]
            if filename and '.' in filename:
                try:
                    from urllib.parse import unquote
                    filename = unquote(filename)
                except:
                    pass
                return filename
    
    # 6. location에서 추출 (기존 로직 유지)
    location = citation.get('location', {})
    if location:
        s3_location = location.get('s3Location', {})
        if s3_location:
            s3_uri = s3_location.get('uri', '')
            if s3_uri and s3_uri.startswith('s3://'):
                filename = s3_uri.split('/')[-1]
                if filename and '.' in filename:
                    try:
                        from urllib.parse import unquote
                        filename = unquote(filename)
                    except:
                        pass
                    return filename
    
    # 7. 기본값 (최후 수단)
    index = citation.get('index', citation.get('id', ''))
    return f"문서_{index}.pdf" if index else "문서.pdf"

def render_citation(citation: Dict, citation_num: int, message_id: str, is_used: bool):
    """Citation 렌더링"""
    filename = extract_filename_from_citation(citation)
    confidence = citation.get('confidence', 0)
    preview = citation.get('preview', '')
    document_uri = citation.get('uri', '')
    
    citation_type = classify_citation_type(citation)
    
    # 아이콘 선택
    if citation_type == CitationType.TABLE:
        icon = "📊"
    elif citation_type == CitationType.IMAGE:
        icon = "🖼️"
    else:
        icon = "📖" if is_used else "📄"
    
    confidence_text = f" (신뢰도: {confidence:.1%})" if confidence > 0 else ""
    status = " ✅" if is_used else ""
    
    with st.expander(f"{icon} [{citation_num}] {filename}{confidence_text}{status}", expanded=False):
        st.markdown(f"**파일명:** {filename}")
        if confidence > 0:
            st.markdown(f"**신뢰도:** {confidence:.1%}")
        
        # 테이블 렌더링
        if citation_type == CitationType.TABLE and preview:
            table_df = parse_table_content(preview)
            if table_df is not None and not table_df.empty:
                st.markdown("**📊 테이블 데이터:**")
                st.dataframe(table_df, use_container_width=True)
            else:
                st.markdown("**문서 내용:**")
                st.text_area("내용 미리보기", value=preview, height=150, 
                           key=f"citation_{citation_num}_{message_id}", disabled=True)
        
        # 이미지 렌더링
        elif citation_type == CitationType.IMAGE:
            s3_uri = None
            location = citation.get('location', {})
            if location:
                s3_location = location.get('s3Location', {})
                if s3_location:
                    s3_uri = s3_location.get('uri', '')
            
            if not s3_uri:
                s3_uri = citation.get('uri', '')
            
            if s3_uri:
                st.markdown("**📷 이미지:**")
                display_s3_image(s3_uri, f"Citation {citation_num} - {filename}")
            
            if preview:
                st.markdown("**문서 내용:**")
                st.text_area("내용 미리보기", value=preview, height=150,
                           key=f"citation_{citation_num}_{message_id}", disabled=True)
        
        # 일반 텍스트 렌더링
        else:
            if preview:
                st.markdown("**문서 내용:**")
                st.text_area("내용 미리보기", value=preview, height=150,
                           key=f"citation_{citation_num}_{message_id}", disabled=True)
        
        # 개발자 정보
        if document_uri:
            with st.expander("🔗 문서 정보", expanded=False):
                st.code(document_uri, language="text")

def display_citation_expandable_with_id(citations: List[Dict], response_text: str, message_id: str):
    """Citation을 확장 가능한 형태로 표시"""
    if not citations:
        return
    
    st.markdown("### 📚 참고 문서")
    
    for i, citation in enumerate(citations, 1):
        is_used = f"[{i}]" in response_text
        render_citation(citation, i, message_id, is_used)

def display_citation_expandable(citations: List[Dict], response_text: str):
    """Citation을 확장 가능한 형태로 표시"""
    if not citations:
        return
    
    import time
    timestamp = str(int(time.time() * 1000))
    display_citation_expandable_with_id(citations, response_text, f"new_{timestamp}")

def process_query_with_progress(query: str, image_data: Optional[str] = None):
    """진행 상황을 표시하면서 쿼리 처리"""
    progress_placeholder = st.empty()
    
    try:
        with progress_placeholder.container():
            st.markdown("### 🔄 처리 진행 상황")
            st.markdown("**🧠 질문 분석 및 검색 전략 수립** ⏳ 진행 중...")
            st.markdown("🔍 Knowledge Base 검색 ⏸️ 대기 중")
            st.markdown("📝 답변 생성 ⏸️ 대기 중")
        
        result = st.session_state.react_agent.process_query(
            user_query=query,
            session_id=st.session_state.session_id,
            image_data=image_data
        )
        
        with progress_placeholder.container():
            st.markdown("### ✅ 처리 완료")
            st.markdown("**🧠 질문 분석 및 검색 전략 수립** ✅ 완료")
            st.markdown("**🔍 Knowledge Base 검색** ✅ 완료")
            st.markdown("**📝 답변 생성** ✅ 완료")
            
            metadata = result.get('metadata', {})
            if metadata:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("처리 시간", f"{result.get('total_processing_time', 0):.1f}초")
                with col2:
                    st.metric("반복 횟수", f"{result.get('iterations_used', 0)}회")
                with col3:
                    st.metric("Citation 수", f"{len(result.get('citations', []))}")
        
        return result
        
    except Exception as e:
        progress_placeholder.error(f"처리 중 오류 발생: {e}")
        return None

def main():
    # 헤더
    st.title("🤖 MCP RAG Chatbot")
    st.markdown("Amazon Bedrock Knowledge Base를 활용한 ReAct 기반 AI 어시스턴트")
    
    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # KB_ID 설정
        st.subheader("Knowledge Base 설정")
        new_kb_id = st.text_input(
            "KB_ID",
            value=st.session_state.kb_id,
            help="Amazon Bedrock Knowledge Base ID"
        )
        
        if new_kb_id != st.session_state.kb_id:
            st.session_state.kb_id = new_kb_id
            st.session_state.react_agent = None
            st.session_state.session_manager = None
            st.rerun()
        
        # Agent 초기화
        if st.session_state.react_agent is None or st.session_state.session_manager is None:
            with st.spinner("Agent 초기화 중..."):
                react_agent, session_manager = initialize_agents(st.session_state.kb_id)
                if react_agent and session_manager:
                    st.session_state.react_agent = react_agent
                    st.session_state.session_manager = session_manager
                    st.success("Agent 초기화 완료!")
                else:
                    st.error("Agent 초기화 실패")
                    st.stop()
        
        # 세션 관리
        st.subheader("세션 관리")
        if st.button("🆕 새 대화 시작"):
            if st.session_state.session_manager:
                session = st.session_state.session_manager.create_session()
                st.session_state.session_id = session.session_id
                st.session_state.messages = []
                st.success("새 세션이 생성되었습니다!")
                st.rerun()
        
        if st.session_state.session_id:
            st.info(f"세션 ID: {st.session_state.session_id[:8]}...")
        
        st.divider()
        
        # 모델 설정 정보
        st.subheader("모델 설정")
        st.info(f"""
        **모델**: Claude 3.7 Sonnet
        **Temperature**: 0 (정확성 우선)
        **KB_ID**: {st.session_state.kb_id}
        **최대 반복**: 5회
        """)
    
    # 메인 채팅 영역
    if not st.session_state.session_id and st.session_state.session_manager:
        session = st.session_state.session_manager.create_session()
        st.session_state.session_id = session.session_id
    
    # 채팅 히스토리 표시
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
                if "image" in message:
                    st.image(message["image"], caption="첨부된 이미지", width=300)
            else:
                st.markdown(message["content"])
                
                if "citations" in message and message["citations"]:
                    message_id = f"msg_{idx}_{hash(str(message.get('timestamp', '')))}"
                    display_citation_expandable_with_id(message["citations"], message["content"], message_id)
                
                if "metadata" in message:
                    metadata = message["metadata"]
                    with st.expander("📊 처리 정보", expanded=False):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("처리 시간", f"{metadata.get('processing_time', 0):.1f}초")
                        with col2:
                            st.metric("반복 횟수", f"{metadata.get('iterations_used', 0)}회")
                        with col3:
                            st.metric("검색 전략", metadata.get('search_strategy', 'N/A'))
    
    # 채팅 입력 영역
    st.markdown("### 💬 메시지 입력")
    
    # 이미지 업로드
    uploaded_image = st.file_uploader(
        "이미지 첨부 (선택사항)",
        type=['png', 'jpg', 'jpeg'],
        help="질문과 관련된 이미지를 첨부할 수 있습니다."
    )
    
    # 텍스트 입력
    user_input = st.chat_input("메시지를 입력하세요...")
    
    if user_input:
        if not st.session_state.session_id:
            st.error("세션이 생성되지 않았습니다. 새로고침 후 다시 시도해주세요.")
            return
        
        # 이미지 처리
        image_data = None
        image_display = None
        if uploaded_image is not None:
            image = Image.open(uploaded_image)
            image_data = encode_image_to_base64(image)
            image_display = image
        
        # 사용자 메시지 추가
        user_message = {
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now()
        }
        if image_display:
            user_message["image"] = image_display
        
        st.session_state.messages.append(user_message)
        
        # 사용자 메시지 표시
        with st.chat_message("user"):
            st.markdown(user_input)
            if image_display:
                st.image(image_display, caption="첨부된 이미지", width=300)
        
        # AI 응답 생성
        with st.chat_message("assistant"):
            result = process_query_with_progress(user_input, image_data)
            
            if result:
                response_content = result.get("content", "응답을 생성할 수 없습니다.")
                st.markdown(response_content)
                
                citations = result.get("citations", [])
                if citations:
                    import time
                    new_response_id = f"new_{int(time.time() * 1000)}"
                    display_citation_expandable_with_id(citations, response_content, new_response_id)
                
                metadata = result.get("metadata", {})
                if metadata:
                    with st.expander("📊 처리 정보", expanded=False):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("처리 시간", f"{result.get('total_processing_time', 0):.1f}초")
                        with col2:
                            st.metric("반복 횟수", f"{result.get('iterations_used', 0)}회")
                        with col3:
                            st.metric("Citation 수", f"{len(citations)}")
                
                # 세션에 AI 응답 추가
                ai_message = {
                    "role": "assistant",
                    "content": response_content,
                    "citations": citations,
                    "metadata": {
                        "processing_time": result.get('total_processing_time', 0),
                        "iterations_used": result.get('iterations_used', 0),
                        "search_strategy": metadata.get('search_strategy', 'N/A')
                    },
                    "timestamp": datetime.now()
                }
                st.session_state.messages.append(ai_message)
            else:
                st.error("응답을 생성할 수 없습니다. 다시 시도해주세요.")

if __name__ == "__main__":
    main()
