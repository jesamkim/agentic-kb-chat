# MCP RAG 챗봇 개발 계획

## 프로젝트 개요
Amazon Bedrock Knowledge Base를 활용한 ReAct 기반 MCP 챗봇 구현
- KB_ID: CQLBN9MFDZ (us-west-2, Hybrid 검색, 50개 chunk)
- Strands Agents 프레임워크 활용
- ReRank 모델: Cohere Rerank 3.5
- Citation 기능 포함

## 아키텍처 설계

### Agent 구조
```
사용자 쿼리 → Orchestration Agent → Action Agent → MCP Tool → 응답 생성 (with Citation)
```

1. **Orchestration Agent**: 사용자 쿼리 분석 및 검색 전략 수립
2. **Action Agent**: MCP 도구 호출 및 KB 검색 실행
3. **Response Generator**: 수집된 정보 통합 및 최종 응답 생성 (Citation 포함)

### ReAct 패턴 구현
- **Thought**: 모델의 내부 추론 과정
- **Action**: 도구 사용 결정 (KB 검색, ReRank 등)
- **Observation**: 행동 결과 분석 (Citation 메타데이터 포함)
- 최종 답변까지 순환 반복

## 개발 단계

### Phase 1: 기본 설정 및 구조 구축

#### 1.1 프로젝트 구조 생성
```
mcp-rag/
├── config/
│   └── settings.py          # 모델 설정, KB_ID 등
├── src/
│   ├── agents/
│   │   ├── orchestration.py # Orchestration Agent
│   │   ├── action.py        # Action Agent
│   │   └── response.py      # Response Generator (Citation 포함)
│   ├── mcp/
│   │   ├── server.py        # MCP 서버 구현
│   │   ├── kb_client.py     # Bedrock KB 클라이언트
│   │   └── rerank_client.py # Cohere ReRank 클라이언트
│   ├── utils/
│   │   ├── session.py       # 세션 관리
│   │   ├── citation.py      # Citation 처리 유틸리티
│   │   └── logger.py        # 로깅 유틸리티
│   └── main.py              # 메인 애플리케이션
├── tests/                   # 테스트 코드
├── ui/                      # React 프론트엔드 (Phase 6)
├── api/                     # FastAPI 백엔드 (Phase 6)
├── development.log          # 개발 진행 상황 로그
└── README.md
```

#### 1.2 기본 설정 파일 생성
- config/settings.py: 모델 설정, API 키, KB_ID 등
- development.log 초기화

### Phase 2: MCP 서버 및 클라이언트 구현

#### 2.1 Bedrock Knowledge Base MCP 클라이언트
- boto3를 활용한 KB 검색 기능
- Hybrid 검색 지원 (50개 chunk)
- **Citation 메타데이터 수집**: 문서 URI, 제목, 페이지 번호, chunk 위치 등
- 에러 처리 및 로깅

#### 2.2 Cohere ReRank 클라이언트
- 검색된 chunk들의 순위 재조정
- Cohere Rerank 3.5 모델 활용
- **Citation 정보 보존**: ReRank 후에도 원본 문서 정보 유지
- 성능 최적화

#### 2.3 MCP 서버 구현
- Strands Agents SDK 활용
- @tool 데코레이터를 통한 도구 등록
- KB 검색 및 ReRank 도구 통합
- **Citation 데이터 전달**: 도구 응답에 Citation 정보 포함

### Phase 3: Agent 구현

#### 3.1 Orchestration Agent
- 사용자 쿼리 분석
- 다중 검색 키워드 생성 전략
- 검색 계획 수립 (aaaa, bbbb, cccc 형태의 다중 검색)

#### 3.2 Action Agent
- MCP 도구 호출 실행
- KB 검색 수행
- ReRank 처리
- **Citation 정보 수집**: 각 검색 결과의 출처 정보 추적
- 결과 수집 및 정리

#### 3.3 Response Generator
- 수집된 정보 통합
- 컨텍스트 기반 응답 생성
- **Citation 통합**: 답변 내용과 출처 정보 매핑
- 대화 연속성 유지

### Phase 4: Citation 시스템 구현

#### 4.1 Citation 데이터 모델
```python
@dataclass
class Citation:
    id: str                    # 고유 식별자
    document_uri: str          # 문서 URI
    document_title: str        # 문서 제목
    chunk_text: str           # 관련 텍스트 chunk
    page_number: Optional[int] # 페이지 번호
    confidence_score: float    # ReRank 점수
    relevance_score: float     # 원본 검색 점수
```

#### 4.2 Citation 처리 유틸리티
- Citation 정보 추출 및 정규화
- 중복 제거 및 병합
- 신뢰도 기반 정렬
- 답변 텍스트와 Citation 매핑

### Phase 5: 세션 관리 및 대화 연속성

#### 5.1 세션 관리 시스템
- 세션별 메모리 구현
- 대화 히스토리 유지
- **Citation 히스토리**: 이전 대화의 Citation 정보 보존
- 컨텍스트 관리

#### 5.2 ReAct 패턴 통합
- Thought-Action-Observation 순환 구조
- 단계별 추론 과정 로깅
- **Citation 추적**: 각 단계에서 사용된 출처 정보 기록
- 최적화된 프롬프트 설계

### Phase 6: 테스트 및 검증

#### 6.1 단위 테스트 (./tests/)
- KB 클라이언트 테스트
- ReRank 기능 테스트
- **Citation 처리 테스트**: 정확한 출처 정보 추출 및 매핑 검증
- 각 Agent 모듈 테스트
- MCP 연동 테스트

#### 6.2 통합 테스트
- 전체 워크플로우 테스트
- 세션 관리 테스트
- **Citation 정확성 테스트**: 답변과 출처의 일치성 검증
- 성능 테스트

### Phase 7: UI 구현

#### 7.1 FastAPI 백엔드
- RESTful API 엔드포인트
- CORS 설정 (보안 고려)
- 세션 관리 API
- **Citation API**: Citation 정보 제공 엔드포인트
- WebSocket 지원 (실시간 채팅)

#### 7.2 React 프론트엔드
- 다크 테마 적용
- 채팅 인터페이스
- System Prompt 설정 기능
- KB_ID 설정 기능
- 새 세션/리셋 기능
- **Citation 표시 기능**:
  - 답변 하단에 출처 목록 표시
  - 각 Citation에 대한 상세 정보 (문서명, 페이지, 신뢰도)
  - Citation 클릭 시 원본 문서 링크 (가능한 경우)
  - 답변 텍스트 내 인라인 Citation 번호 표시 [1], [2] 형태
- pnpm 패키지 관리

#### 7.3 Citation UI 컴포넌트
```typescript
interface CitationProps {
  citations: Citation[];
  showInline: boolean;
  expandable: boolean;
}

// Citation 표시 형태:
// 1. 인라인: "이 정보는 AWS 문서에 따르면 [1] ..."
// 2. 하단 목록: 
//    [1] AWS Lambda Developer Guide, Page 15, Confidence: 0.95
//    [2] Amazon S3 User Guide, Page 42, Confidence: 0.87
```

## 기술 스택

### 백엔드
- Python 3.9+
- Strands Agents SDK
- boto3 (AWS SDK)
- FastAPI
- uvicorn

### 프론트엔드
- React 18+
- TypeScript
- pnpm
- 다크 테마 UI 라이브러리
- Citation 표시용 컴포넌트

### AWS 서비스
- Amazon Bedrock (Claude 3.7 Sonnet)
- Amazon Bedrock Knowledge Base
- Cohere Rerank 3.5

## 보안 및 모범 사례

### 보안 고려사항
- API 키 환경변수 관리
- CORS 정책 적절히 설정
- 입력 검증 및 sanitization
- 세션 보안
- **Citation 보안**: 민감한 문서 정보 노출 방지

### 개발 원칙
- 하드코딩 금지 (설정은 config/settings.py 참조)
- 단위 모듈별 테스트 필수
- 진행 상황 development.log에 기록
- 이모지 사용 금지
- 코드 품질 및 문서화

## 성공 기준

1. **기능적 요구사항**
   - 사용자 쿼리에 대한 정확한 KB 검색
   - ReRank를 통한 결과 품질 향상
   - 세션 내 대화 연속성 유지
   - 다중 검색 전략 실행
   - **정확한 Citation 표시**: 답변과 출처의 정확한 매핑

2. **비기능적 요구사항**
   - 응답 시간 < 10초
   - 안정적인 세션 관리
   - 확장 가능한 아키텍처
   - 적절한 에러 처리
   - **Citation 성능**: Citation 처리로 인한 지연 최소화

3. **사용자 경험**
   - 직관적인 UI
   - 실시간 응답
   - 설정 가능한 파라미터
   - 명확한 피드백
   - **투명한 출처 표시**: 사용자가 답변의 근거를 쉽게 확인 가능

4. **Citation 품질**
   - 답변 내용과 Citation의 정확한 일치
   - 중복 Citation 제거
   - 신뢰도 기반 Citation 순서 정렬
   - 사용자 친화적인 Citation 표시

## 다음 단계

1. development.log 초기화
2. 기본 프로젝트 구조 생성
3. config/settings.py 구현
4. Citation 데이터 모델 설계
5. MCP 서버 기본 구조 구축 (Citation 지원 포함)
6. 단계별 구현 및 테스트

이 계획을 바탕으로 Citation 기능을 포함한 체계적이고 안정적인 MCP RAG 챗봇을 구현할 예정입니다.
