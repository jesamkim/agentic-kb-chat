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
    IMAGE_TEXT = "image_text"  # 이미지에서 추출된 텍스트

def detect_table_content(text: str) -> bool:
    """텍스트가 테이블 형태인지 감지"""
    if not text:
        return False
    
    table_indicators = [
        # Markdown table indicators
        '|',
        # Tab separated values
        '\t',
        # Table keywords
        'Table', 'table', '표', '테이블',
        '행', '열', 'row', 'column',
        # Common table patterns
        '번호\t', '항목\t', '구분\t',
        '순번', '항목명', '기준', '규격',
        # Multiple spaces (often used in formatted tables)
        '   ',  # 3+ spaces
    ]
    
    # Check for table indicators
    indicator_count = sum(1 for indicator in table_indicators if indicator in text)
    
    # Check for structured data patterns
    lines = text.split('\n')
    structured_lines = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for patterns that suggest tabular data
        if ('|' in line or 
            '\t' in line or 
            len(line.split()) > 3 and any(char.isdigit() for char in line)):
            structured_lines += 1
    
    # Consider it a table if:
    # 1. Has table indicators AND structured lines
    # 2. More than 30% of lines are structured
    return (indicator_count > 0 and structured_lines > 2) or (structured_lines > len(lines) * 0.3)

def parse_table_content(text: str) -> Optional[pd.DataFrame]:
    """테이블 텍스트를 DataFrame으로 변환"""
    try:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            return None
        
        # Try different parsing methods
        
        # Method 1: Markdown table
        if '|' in text:
            table_lines = [line for line in lines if '|' in line]
            if len(table_lines) >= 2:
                # Parse markdown table
                headers = [col.strip() for col in table_lines[0].split('|') if col.strip()]
                
                data = []
                for line in table_lines[2:]:  # Skip header separator
                    row = [col.strip() for col in line.split('|') if col.strip()]
                    if len(row) == len(headers):
                        data.append(row)
                
                if data:
                    return pd.DataFrame(data, columns=headers)
        
        # Method 2: Tab separated
        if '\t' in text:
            try:
                from io import StringIO
                df = pd.read_csv(StringIO(text), sep='\t')
                if not df.empty:
                    return df
            except:
                pass
        
        # Method 3: Space separated (structured text)
        if len(lines) >= 3:
            # Try to identify columns by consistent spacing
            first_line = lines[0]
            if len(first_line.split()) >= 2:
                try:
                    # Simple space-separated parsing
                    data = []
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 2:
                            data.append(parts)
                    
                    if data:
                        # Use first row as headers if it looks like headers
                        headers = data[0] if not any(char.isdigit() for char in ' '.join(data[0])) else [f'Column_{i+1}' for i in range(len(data[0]))]
                        df_data = data[1:] if headers == data[0] else data
                        
                        if df_data:
                            return pd.DataFrame(df_data, columns=headers[:len(df_data[0])])
                except:
                    pass
        
        return None
        
    except Exception as e:
        print(f"Table parsing error: {e}")
        return None

def detect_image_based_text(citation: Dict) -> tuple[bool, str]:
    """이미지 기반 텍스트 청크 감지 및 S3 URI 추출"""
    content = citation.get('preview', '') or citation.get('content', {}).get('text', '')
    
    # 이미지 기반 텍스트 지시어들
    image_text_indicators = [
        'extracted from image',
        'OCR result',
        'image contains',
        '이미지에서 추출',
        '그림에서',
        'figure shows',
        'diagram',
        '도표', '도면', '그래프'
    ]
    
    is_image_text = any(indicator in content.lower() for indicator in image_text_indicators)
    
    # S3 URI 추출
    s3_uri = ""
    
    # location에서 S3 URI 찾기
    location = citation.get('location', {})
    if location:
        s3_location = location.get('s3Location', {})
        if s3_location:
            s3_uri = s3_location.get('uri', '')
    
    # 다른 필드에서 S3 URI 찾기
    if not s3_uri:
        uri_fields = ['uri', 'document_uri', 's3_uri']
        for field in uri_fields:
            uri = citation.get(field, '')
            if uri and uri.startswith('s3://'):
                s3_uri = uri
                break
    
    return is_image_text, s3_uri

def classify_citation_type(citation: Dict) -> CitationType:
    """Citation 타입 자동 분류"""
    content = citation.get('preview', '') or citation.get('content', {}).get('text', '')
    
    # 테이블 감지
    if detect_table_content(content):
        return CitationType.TABLE
    
    # 이미지 청크 감지
    if is_image_chunk(citation):
        return CitationType.IMAGE
    
    # 이미지 기반 텍스트 감지
    is_img_text, _ = detect_image_based_text(citation)
    if is_img_text:
        return CitationType.IMAGE_TEXT
    
    return CitationType.TEXT

def generate_presigned_url(s3_uri: str, expiration: int = 3600) -> Optional[str]:
    """S3 URI에서 presigned URL 생성"""
    try:
        # S3 URI 파싱: s3://bucket/path/file.png
        if not s3_uri.startswith('s3://'):
            return None
        
        # s3:// 제거하고 bucket과 key 분리
        path_parts = s3_uri[5:].split('/', 1)  # s3:// 제거
        if len(path_parts) != 2:
            return None
        
        bucket_name = path_parts[0]
        object_key = path_parts[1]
        
        # S3 클라이언트 생성
        s3_client = boto3.client('s3')
        
        # Presigned URL 생성
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
    # content_type 확인
    content_type = citation.get('content_type', '')
    if 'image' in content_type.lower():
        return True
    
    # URI에서 이미지 확장자 확인
    uri_fields = ['uri', 'document_uri']
    for field in uri_fields:
        uri = citation.get(field, '')
        if uri:
            lower_uri = uri.lower()
            if any(ext in lower_uri for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                return True
    
    # location에서 확인
    location = citation.get('location', {})
    if location:
        s3_location = location.get('s3Location', {})
        if s3_location:
            s3_uri = s3_location.get('uri', '')
            if s3_uri:
                lower_uri = s3_uri.lower()
                if any(ext in lower_uri for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
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
    """Citation 데이터 구조를 상세히 분석 (디버깅용)"""
    print(f"\n=== Citation {citation_num} Debug Info ===")
    print(f"Top-level keys: {list(citation.keys())}")
    
    for key, value in citation.items():
        if isinstance(value, dict):
            print(f"{key} (dict): {list(value.keys())}")
            for sub_key, sub_value in value.items():
                print(f"  {sub_key}: {type(sub_value)} = {sub_value}")
        elif isinstance(value, list):
            print(f"{key} (list): length={len(value)}")
            if value:
                print(f"  First item: {type(value[0])} = {value[0]}")
        else:
            print(f"{key}: {type(value)} = {value}")
    print("=" * 50)

def extract_filename_from_citation(citation: Dict) -> str:
    """Citation에서 파일명 추출 (고급 로직)"""
    
    # 1. Bedrock KB 전용 메타데이터 필드들 확인
    metadata = citation.get('metadata', {})
    if metadata:
        # Bedrock KB 전용 필드들
        bedrock_fields = [
            'x-amz-bedrock-kb-source-uri',
            'x-amz-bedrock-kb-data-source-id',
            'x-amz-bedrock-kb-chunk-id',
            'source',
            'document_id',
            'file_name',
            'fileName',
            'document_name'
        ]
        
        for field in bedrock_fields:
            value = metadata.get(field, '')
            if value:
                # S3 URI에서 파일명 추출
                if value.startswith('s3://'):
                    filename = value.split('/')[-1]
                    if filename and '.' in filename:
                        return filename
                # 직접 파일명인 경우
                elif '.' in value and any(ext in value.lower() for ext in ['.pdf', '.doc', '.txt', '.html', '.xlsx']):
                    return value
    
    # 2. location.s3Location.uri에서 추출 (Bedrock KB 표준 구조)
    location = citation.get('location', {})
    if location:
        s3_location = location.get('s3Location', {})
        if s3_location:
            s3_uri = s3_location.get('uri', '')
            if s3_uri and s3_uri.startswith('s3://'):
                filename = s3_uri.split('/')[-1]
                if filename and '.' in filename:
                    return filename
    
    # 3. 직접 URI 필드들 확인
    uri_fields = ['uri', 'document_uri', 's3_uri', 'source_uri']
    for field in uri_fields:
        uri = citation.get(field, '')
        if uri and uri.startswith('s3://'):
            filename = uri.split('/')[-1]
            if filename and '.' in filename:
                return filename
    
    # 4. title 필드 확인 (실제 파일명인 경우만)
    title_fields = ['title', 'document_title', 'documentTitle']
    for field in title_fields:
        title = citation.get(field, '')
        if title and title != 'Unknown Document' and title != 'Unknown':
            # 파일 확장자가 포함된 경우만 파일명으로 인정
            if '.' in title and any(ext in title.lower() for ext in ['.pdf', '.doc', '.docx', '.txt', '.html', '.xlsx', '.csv']):
                return title
    
    # 5. content에서 파일 참조 찾기
    content = citation.get('content', {})
    if content:
        text = content.get('text', '')
        if text:
            # 텍스트에서 파일명 패턴 찾기
            file_pattern = r'([a-zA-Z0-9가-힣_\-\s]+\.(pdf|doc|docx|txt|html|xlsx|csv))'
            matches = re.findall(file_pattern, text, re.IGNORECASE)
            if matches:
                filename = matches[0][0]  # 첫 번째 매치의 전체 파일명
                return filename
    
    # 6. preview에서 파일명 패턴 찾기
    preview = citation.get('preview', '')
    if preview:
        file_pattern = r'([a-zA-Z0-9가-힣_\-\s]+\.(pdf|doc|docx|txt|html|xlsx|csv))'
        matches = re.findall(file_pattern, preview, re.IGNORECASE)
        if matches:
            filename = matches[0][0]
            return filename
    
    # 7. ID 기반 파일명 생성
    doc_id = citation.get('id', '')
    if doc_id:
        # ID에서 의미있는 부분 추출
        if '/' in doc_id:
            id_part = doc_id.split('/')[-1]
        else:
            id_part = doc_id
        
        # ID가 파일명 형태인지 확인
        if '.' in id_part:
            return id_part
    
    # 8. 기본값 - 실제 데이터 기반으로 생성
    # title이나 다른 정보를 기반으로 의미있는 이름 생성
    title = citation.get('title', '')
    if title and title not in ['Unknown Document', 'Unknown', '']:
        # 특수문자 제거하고 파일명으로 사용
        clean_title = re.sub(r'[^\w\s가-힣-]', '', title)
        clean_title = re.sub(r'\s+', '_', clean_title.strip())
        if clean_title:
            return f"{clean_title}.pdf"
    
    # 9. 최종 기본값
    index = citation.get('index', citation.get('id', ''))
    return f"문서_{index}.pdf" if index else "문서.pdf"

def render_table_citation(citation: Dict, citation_num: int, message_id: str, is_used: bool):
    """테이블 Citation 렌더링"""
    filename = extract_filename_from_citation(citation)
    confidence = citation.get('confidence', 0)
    preview = citation.get('preview', '')
    
    confidence_text = f" (신뢰도: {confidence:.1%})" if confidence > 0 else ""
    icon = "📊"
    status = " ✅" if is_used else ""
    
    with st.expander(f"{icon} [{citation_num}] {filename}{confidence_text}{status}", expanded=False):
        st.markdown(f"**파일명:** {filename}")
        if confidence > 0:
            st.markdown(f"**신뢰도:** {confidence:.1%}")
        
        # 테이블 데이터 파싱 및 표시
        if preview:
            table_df = parse_table_content(preview)
            if table_df is not None and not table_df.empty:
                st.markdown("**📊 테이블 데이터:**")
                st.dataframe(table_df, use_container_width=True)
            else:
                st.markdown("**문서 내용:**")
                st.text_area(
                    "내용 미리보기",
                    value=preview,
                    height=200 if is_used else 150,
                    key=f"citation_table_{'used' if is_used else 'unused'}_{citation_num}_{message_id}",
                    disabled=True
                )

def render_image_citation(citation: Dict, citation_num: int, message_id: str, is_used: bool):
    """이미지 Citation 렌더링"""
    filename = extract_filename_from_citation(citation)
    confidence = citation.get('confidence', 0)
    preview = citation.get('preview', '')
    
    confidence_text = f" (신뢰도: {confidence:.1%})" if confidence > 0 else ""
    icon = "🖼️"
    status = " ✅" if is_used else ""
    
    with st.expander(f"{icon} [{citation_num}] {filename}{confidence_text}{status}", expanded=False):
        st.markdown(f"**파일명:** {filename}")
        if confidence > 0:
            st.markdown(f"**신뢰도:** {confidence:.1%}")
        
        # S3 이미지 표시
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
            st.text_area(
                "내용 미리보기",
                value=preview,
                height=150,
                key=f"citation_image_{'used' if is_used else 'unused'}_{citation_num}_{message_id}",
                disabled=True
            )

def render_image_text_citation(citation: Dict, citation_num: int, message_id: str, is_used: bool):
    """이미지 기반 텍스트 Citation 렌더링"""
    filename = extract_filename_from_citation(citation)
    confidence = citation.get('confidence', 0)
    preview = citation.get('preview', '')
    
    confidence_text = f" (신뢰도: {confidence:.1%})" if confidence > 0 else ""
    icon = "🖼️📝"
    status = " ✅" if is_used else ""
    
    with st.expander(f"{icon} [{citation_num}] {filename}{confidence_text}{status}", expanded=False):
        st.markdown(f"**파일명:** {filename}")
        if confidence > 0:
            st.markdown(f"**신뢰도:** {confidence:.1%}")
        
        # 원본 이미지 표시 (이미지 기반 텍스트의 경우)
        _, s3_uri = detect_image_based_text(citation)
        if s3_uri:
            st.markdown("**📷 원본 이미지:**")
            display_s3_image(s3_uri, f"Citation {citation_num} - 원본 이미지")
        
        if preview:
            st.markdown("**📝 추출된 텍스트:**")
            st.text_area(
                "이미지에서 추출된 내용",
                value=preview,
                height=200 if is_used else 150,
                key=f"citation_imgtext_{'used' if is_used else 'unused'}_{citation_num}_{message_id}",
                disabled=True
            )

def render_text_citation(citation: Dict, citation_num: int, message_id: str, is_used: bool):
    """일반 텍스트 Citation 렌더링"""
    filename = extract_filename_from_citation(citation)
    confidence = citation.get('confidence', 0)
    preview = citation.get('preview', '')
    document_uri = citation.get('uri', '')
    
    confidence_text = f" (신뢰도: {confidence:.1%})" if confidence > 0 else ""
    icon = "📖" if is_used else "📄"
    status = " ✅" if is_used else ""
    
    with st.expander(f"{icon} [{citation_num}] {filename}{confidence_text}{status}", expanded=False):
        st.markdown(f"**파일명:** {filename}")
        if confidence > 0:
            st.markdown(f"**신뢰도:** {confidence:.1%}")
        
        if preview:
            st.markdown("**문서 내용:**")
            st.text_area(
                "내용 미리보기",
                value=preview,
                height=200 if is_used else 150,
                key=f"citation_text_{'used' if is_used else 'unused'}_{citation_num}_{message_id}",
                disabled=True
            )
        
        # 원본 URI 정보 (개발자용)
        if document_uri:
            with st.expander("🔗 문서 정보", expanded=False):
                st.code(document_uri, language="text")

def render_citation_by_type(citation: Dict, citation_num: int, message_id: str, is_used: bool):
    """Citation 타입에 따른 맞춤형 렌더링"""
    citation_type = classify_citation_type(citation)
    
    if citation_type == CitationType.TABLE:
        render_table_citation(citation, citation_num, message_id, is_used)
    elif citation_type == CitationType.IMAGE:
        render_image_citation(citation, citation_num, message_id, is_used)
    elif citation_type == CitationType.IMAGE_TEXT:
        render_image_text_citation(citation, citation_num, message_id, is_used)
    else:
        render_text_citation(citation, citation_num, message_id, is_used)
    
    # Citation 번호 추출 및 매핑
    citation_map = {}
    for i, citation in enumerate(citations, 1):
        citation_map[i] = citation
    
    # Citation 번호별로 확장 가능한 섹션 생성
    for citation_num, citation in citation_map.items():
        # 파일명 추출
        filename = extract_filename_from_citation(citation)
        
        confidence = citation.get('confidence', 0)
        preview = citation.get('preview', '')
        document_uri = citation.get('uri', '')
        
        # Citation이 응답에서 사용되었는지 확인
        is_used = f"[{citation_num}]" in response_text
        
        # 신뢰도 표시 (0.0%가 아닌 경우만)
        confidence_text = f" (신뢰도: {confidence:.1%})" if confidence > 0 else ""
        
        # 사용된 Citation은 다른 색상으로 표시
        if is_used:
            with st.expander(f"📖 [{citation_num}] {filename}{confidence_text} ✅", expanded=False):
                st.markdown(f"**파일명:** {filename}")
                if confidence > 0:
                    st.markdown(f"**신뢰도:** {confidence:.1%}")
                
                if preview:
                    st.markdown("**문서 내용:**")
                    st.text_area(
                        "내용 미리보기",
                        value=preview,
                        height=200,
                        key=f"citation_used_{citation_num}_{message_id}",
                        disabled=True
                    )
                
                # 원본 URI 정보 (개발자용)
                if document_uri:
                    with st.expander("🔗 문서 정보", expanded=False):
                        st.code(document_uri, language="text")
                
                # 이미지 정보 표시
                if citation.get('has_images') and citation.get('images'):
                    st.markdown("**관련 이미지:**")
                    for img_idx, img_info in enumerate(citation['images'][:3]):  # 최대 3개
                        if img_info.get('alt_text'):
                            st.markdown(f"- {img_info['alt_text']}")
        else:
            with st.expander(f"📄 [{citation_num}] {filename}{confidence_text}", expanded=False):
                st.markdown(f"**파일명:** {filename}")
                if confidence > 0:
                    st.markdown(f"**신뢰도:** {confidence:.1%}")
                
                if preview:
                    st.markdown("**문서 내용:**")
                    st.text_area(
                        "내용 미리보기",
                        value=preview,
                        height=150,
                        key=f"citation_unused_{citation_num}_{message_id}",
                        disabled=True
                    )
                
                # 원본 URI 정보 (개발자용)
                if document_uri:
                    with st.expander("🔗 문서 정보", expanded=False):
                        st.code(document_uri, language="text")

def display_citation_expandable(citations: List[Dict], response_text: str):
    """Citation을 확장 가능한 형태로 표시"""
    if not citations:
        return
    
    # 고유한 키 생성을 위한 타임스탬프
    import time
    timestamp = str(int(time.time() * 1000))
    
    # 고유 ID로 함수 호출
    display_citation_expandable_with_id(citations, response_text, f"new_{timestamp}")

def display_citation_expandable_with_id(citations: List[Dict], response_text: str, message_id: str):
    """Citation을 확장 가능한 형태로 표시 (타입별 렌더링)"""
    if not citations:
        return
    
    st.markdown("### 📚 참고 문서")
    
    # Citation 번호 추출 및 매핑
    citation_map = {}
    for i, citation in enumerate(citations, 1):
        citation_map[i] = citation
    
    # Citation 번호별로 타입에 따른 렌더링
    for citation_num, citation in citation_map.items():
        # Citation이 응답에서 사용되었는지 확인
        is_used = f"[{citation_num}]" in response_text
        
        # 타입별 렌더링
        render_citation_by_type(citation, citation_num, message_id, is_used)

def display_citation_expandable(citations: List[Dict], response_text: str):
    """Citation을 확장 가능한 형태로 표시"""
    if not citations:
        return
    
    # 고유한 키 생성을 위한 타임스탬프
    import time
    timestamp = str(int(time.time() * 1000))
    
    # 고유 ID로 함수 호출
    display_citation_expandable_with_id(citations, response_text, f"new_{timestamp}")
    """진행 상황을 표시하면서 쿼리 처리"""
    
    # 진행 상황 표시 컨테이너
    progress_placeholder = st.empty()
    
    try:
        # 1. Orchestration 단계
        with progress_placeholder.container():
            st.markdown("### 🔄 처리 진행 상황")
            st.markdown("**🧠 질문 분석 및 검색 전략 수립** ⏳ 진행 중...")
            st.markdown("🔍 Knowledge Base 검색 ⏸️ 대기 중")
            st.markdown("📝 답변 생성 ⏸️ 대기 중")
        
        # ReAct Agent로 처리 (이미지 데이터 포함)
        result = st.session_state.react_agent.process_query(
            user_query=query,
            session_id=st.session_state.session_id,
            image_data=image_data
        )
        
        # 진행 상황 완료 표시
        with progress_placeholder.container():
            st.markdown("### ✅ 처리 완료")
            st.markdown("**🧠 질문 분석 및 검색 전략 수립** ✅ 완료")
            st.markdown("**🔍 Knowledge Base 검색** ✅ 완료")
            st.markdown("**📝 답변 생성** ✅ 완료")
            
            # 처리 통계 표시
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

def process_query_with_progress(query: str, image_data: Optional[str] = None):
    """진행 상황을 표시하면서 쿼리 처리"""
    
    # 진행 상황 표시 컨테이너
    progress_placeholder = st.empty()
    
    try:
        # 1. Orchestration 단계
        with progress_placeholder.container():
            st.markdown("### 🔄 처리 진행 상황")
            st.markdown("**🧠 질문 분석 및 검색 전략 수립** ⏳ 진행 중...")
            st.markdown("🔍 Knowledge Base 검색 ⏸️ 대기 중")
            st.markdown("📝 답변 생성 ⏸️ 대기 중")
        
        # ReAct Agent로 처리 (이미지 데이터 포함)
        result = st.session_state.react_agent.process_query(
            user_query=query,
            session_id=st.session_state.session_id,
            image_data=image_data
        )
        
        # 진행 상황 완료 표시
        with progress_placeholder.container():
            st.markdown("### ✅ 처리 완료")
            st.markdown("**🧠 질문 분석 및 검색 전략 수립** ✅ 완료")
            st.markdown("**🔍 Knowledge Base 검색** ✅ 완료")
            st.markdown("**📝 답변 생성** ✅ 완료")
            
            # 처리 통계 표시
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
    st.title("MCP RAG Chatbot")
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
            st.session_state.react_agent = None  # Agent 재초기화 필요
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
        """)
        
        st.divider()
        
        # 사용 가이드
        st.subheader("💡 사용 가이드")
        st.markdown("""
        **주요 기능:**
        - 🔍 Knowledge Base 검색
        - 📚 Citation 기반 답변
        - 🔄 ReAct 패턴 추론
        - 🖼️ 이미지 첨부 지원
        
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
                # 이미지가 있는 경우 표시
                if "image" in message:
                    st.image(message["image"], caption="첨부된 이미지", width=300)
            else:
                # AI 응답 표시
                st.markdown(message["content"])
                
                # Citation 표시 (고유한 키 생성)
                if "citations" in message and message["citations"]:
                    # 메시지별 고유 식별자 추가
                    message_id = f"msg_{idx}_{hash(str(message.get('timestamp', '')))}"
                    display_citation_expandable_with_id(message["citations"], message["content"], message_id)
                
                # 메타데이터 표시
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
                # AI 응답 표시
                response_content = result.get("content", "응답을 생성할 수 없습니다.")
                st.markdown(response_content)
                
                # Citation 표시
                citations = result.get("citations", [])
                if citations:
                    # 새 응답용 고유 ID 생성
                    import time
                    new_response_id = f"new_{int(time.time() * 1000)}"
                    display_citation_expandable_with_id(citations, response_content, new_response_id)
                
                # 메타데이터 표시
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
