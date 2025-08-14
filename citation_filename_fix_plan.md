# Citation 파일명 문제 해결 계획

## 🔍 문제 분석

### 현재 상황
- Streamlit UI에서 Knowledge Base 검색 후 citation 표시 시 파일명이 "문서_1.pdf" 형태로 나타남
- 실제 원본 파일명이 아닌 기본값이 표시되는 문제

### 원인 분석

#### 1. Citation 클래스의 파일명 추출 로직 문제
**파일 위치**: `/Workshop/mcp-rag/src/utils/citation.py`

```python
@classmethod
def from_kb_result(cls, kb_result: Dict[str, Any], confidence_score: float = 0.0) -> 'Citation':
    content = kb_result.get('content', {})
    metadata = kb_result.get('metadata', {})
    
    citation = cls(
        id="",
        document_uri=metadata.get('source', ''),  # ❌ 'source' 키가 없음
        document_title=metadata.get('title', 'Unknown Document'),  # ❌ 'title' 키가 없음
        # ...
    )
```

**문제점**: 
- `metadata.get('source', '')` → 실제로는 `x-amz-bedrock-kb-source-uri` 키 사용
- `metadata.get('title', 'Unknown Document')` → 실제로는 title 정보가 없음

#### 2. Streamlit UI의 파일명 추출 함수 문제
**파일 위치**: `/Workshop/mcp-rag/ui/app.py`

```python
def extract_filename_from_citation(citation: Dict) -> str:
    # 1. Citation 메타데이터에서 직접 추출
    metadata = citation.get('metadata', {})
    if metadata:
        source_uri = metadata.get('x-amz-bedrock-kb-source-uri', '')  # ✅ 올바른 키
        # ...
    
    # 5. 기본값
    index = citation.get('index', citation.get('id', ''))
    return f"문서_{index}.pdf" if index else "문서.pdf"  # ❌ 기본값으로 떨어짐
```

**문제점**: 
- Citation 객체의 구조와 UI에서 기대하는 구조가 다름
- 메타데이터가 제대로 전달되지 않아 기본값으로 떨어짐

#### 3. 실제 KB 검색 결과 구조
앞서 테스트에서 확인한 실제 구조:
```json
{
    "location": {
        "s3Location": {
            "uri": "s3://250813-quality-test/data/건설공사 품질관리 업무지침(국토교통부고시)(제2025-311호)(20250612).pdf"
        }
    },
    "metadata": {
        "x-amz-bedrock-kb-source-uri": "s3://250813-quality-test/data/건설공사 품질관리 업무지침(국토교통부고시)(제2025-311호)(20250612).pdf",
        "x-amz-bedrock-kb-document-page-number": 173.0,
        "x-amz-bedrock-kb-data-source-id": "4OUMXWCAIX"
    }
}
```

## 🎯 해결 계획

### Phase 1: Citation 클래스 수정
1. `Citation.from_kb_result()` 메서드 수정
2. 올바른 메타데이터 키 사용
3. 파일명 추출 로직 개선

### Phase 2: KB 클라이언트 수정
1. `BedrockKBClient`에서 Citation 생성 시 올바른 데이터 전달
2. 메타데이터 매핑 확인

### Phase 3: Streamlit UI 수정
1. `extract_filename_from_citation()` 함수 개선
2. Citation 객체 구조에 맞는 파일명 추출
3. 디버깅 정보 추가

### Phase 4: 테스트 및 검증
1. 실제 KB 검색 결과로 테스트
2. 파일명 표시 확인
3. Citation 정보 정확성 검증

## 🔧 구체적 수정 사항

### 1. Citation 클래스 수정
```python
@classmethod
def from_kb_result(cls, kb_result: Dict[str, Any], confidence_score: float = 0.0) -> 'Citation':
    content = kb_result.get('content', {})
    metadata = kb_result.get('metadata', {})
    location = kb_result.get('location', {})
    
    # S3 URI에서 파일명 추출
    document_uri = ""
    document_title = "Unknown Document"
    
    # 1. location에서 S3 URI 추출
    if location and 's3Location' in location:
        document_uri = location['s3Location'].get('uri', '')
    
    # 2. metadata에서 S3 URI 추출 (fallback)
    if not document_uri:
        document_uri = metadata.get('x-amz-bedrock-kb-source-uri', '')
    
    # 3. 파일명을 제목으로 사용
    if document_uri:
        filename = document_uri.split('/')[-1]
        if filename:
            document_title = filename
    
    citation = cls(
        id="",
        document_uri=document_uri,
        document_title=document_title,
        chunk_text=content.get('text', ''),
        page_number=metadata.get('x-amz-bedrock-kb-document-page-number'),
        confidence_score=confidence_score,
        relevance_score=kb_result.get('score', 0.0),
        metadata=metadata
    )
```

### 2. Streamlit UI 수정
```python
def extract_filename_from_citation(citation: Dict) -> str:
    # 1. Citation 객체의 document_title 사용
    document_title = citation.get('document_title', '')
    if document_title and document_title != 'Unknown Document':
        return document_title
    
    # 2. Citation 객체의 document_uri에서 추출
    document_uri = citation.get('document_uri', '')
    if document_uri and document_uri.startswith('s3://'):
        filename = document_uri.split('/')[-1]
        if filename and '.' in filename:
            return filename
    
    # 3. 메타데이터에서 직접 추출 (기존 로직 유지)
    metadata = citation.get('metadata', {})
    if metadata:
        source_uri = metadata.get('x-amz-bedrock-kb-source-uri', '')
        if source_uri and source_uri.startswith('s3://'):
            filename = source_uri.split('/')[-1]
            if filename and '.' in filename:
                return filename
    
    # 4. location에서 추출 (기존 로직 유지)
    location = citation.get('location', {})
    if location:
        s3_location = location.get('s3Location', {})
        if s3_location:
            s3_uri = s3_location.get('uri', '')
            if s3_uri and s3_uri.startswith('s3://'):
                filename = s3_uri.split('/')[-1]
                if filename and '.' in filename:
                    return filename
    
    # 5. 기본값 (최후 수단)
    index = citation.get('index', citation.get('id', ''))
    return f"문서_{index}.pdf" if index else "문서.pdf"
```

## 📋 실행 순서

1. **Citation 클래스 수정** → 근본적 해결
2. **KB 클라이언트 확인** → 데이터 전달 검증
3. **Streamlit UI 수정** → 사용자 인터페이스 개선
4. **통합 테스트** → 전체 플로우 검증

## 🎯 예상 결과

수정 후:
- Citation에 "건설공사 품질관리 업무지침(국토교통부고시)(제2025-311호)(20250612).pdf" 표시
- 실제 원본 파일명 정확히 표시
- 페이지 번호 및 기타 메타데이터 정상 표시

## 🔍 추가 개선 사항

1. **파일명 한글 처리**: URL 디코딩 필요시 처리
2. **에러 핸들링**: 파일명 추출 실패시 더 나은 fallback
3. **로깅**: 파일명 추출 과정 디버깅 정보 추가
4. **캐싱**: 동일한 파일의 반복 처리 최적화
