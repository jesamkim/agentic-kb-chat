"""
Citation Display Functions
Citation 표시를 위한 함수들
"""

import streamlit as st
import pandas as pd
import boto3
from typing import Dict, List, Any, Optional
from enum import Enum
import re


class CitationType(Enum):
    TEXT = "text"
    TABLE = "table" 
    IMAGE = "image"
    IMAGE_TEXT = "image_text"


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
    """Citation 렌더링 (expander 없이 내용만)"""
    filename = extract_filename_from_citation(citation)
    confidence = citation.get('confidence', 0)
    preview = citation.get('preview', '')
    document_uri = citation.get('uri', citation.get('document_uri', ''))
    
    citation_type = classify_citation_type(citation)
    
    # 기본 정보 표시
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
            s3_uri = citation.get('uri', citation.get('document_uri', ''))
        
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
        st.markdown("**🔗 문서 정보:**")
        st.code(document_uri, language="text")


def display_citation_expandable_with_id(citations: List[Dict], response_text: str, message_id: str):
    """Citation을 확장 가능한 형태로 표시"""
    if not citations:
        return
    
    st.markdown("### 📚 참고 문서")
    
    for i, citation in enumerate(citations, 1):
        is_used = f"[{i}]" in response_text
        filename = extract_filename_from_citation(citation)
        
        # 사용 여부에 따른 스타일링
        if is_used:
            title = f"📄 [{i}] {filename} ✅"
        else:
            title = f"📄 [{i}] {filename}"
        
        # 각 citation을 개별 expander로 감싸기
        with st.expander(title, expanded=False):
            render_citation(citation, i, message_id, is_used)


def display_citation_expandable(citations: List[Dict], response_text: str):
    """Citation을 확장 가능한 형태로 표시"""
    if not citations:
        return
    
    import time
    timestamp = str(int(time.time() * 1000))
    display_citation_expandable_with_id(citations, response_text, f"new_{timestamp}")
