"""
MCP RAG 챗봇 설정 파일
모든 설정값은 이 파일에서 중앙 관리됩니다.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class ModelConfig:
    """LLM 모델 설정"""
    # Claude 3.7 Sonnet (Cross-Region Inference)
    primary_model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    region: str = "us-west-2"
    max_tokens: int = 4000
    temperature: float = 0.0  # 정확성 우선 (사용자 요구사항)
    
    # ReRank 모델
    rerank_model_id: str = "cohere.rerank-v3-5:0"
    rerank_top_k: int = 10  # ReRank 후 상위 몇 개 결과를 사용할지
    
    # Embedding 모델 (필요시)
    embedding_model_id: str = "amazon.titan-embed-text-v2:0"


@dataclass
class KnowledgeBaseConfig:
    """Knowledge Base 설정"""
    kb_id: str = "CQLBN9MFDZ"
    region: str = "us-west-2"
    search_type: str = "HYBRID"  # HYBRID, SEMANTIC, or LEXICAL
    max_results: int = 30
    
    # ReRank 설정 (현재 비활성화)
    enable_rerank: bool = False  # ReRank 기능 비활성화
    rerank_threshold: float = 0.5  # 이 점수 이하는 필터링


@dataclass
class SessionConfig:
    """세션 관리 설정"""
    max_history_length: int = 20  # 최대 대화 히스토리 길이
    session_timeout_minutes: int = 60  # 세션 타임아웃 (분)
    memory_cleanup_interval: int = 300  # 메모리 정리 간격 (초)


@dataclass
class CitationConfig:
    """Citation 설정"""
    max_citations_per_response: int = 30  # 응답당 최대 Citation 수
    min_confidence_score: float = 0.0  # 최소 신뢰도 점수 (모든 결과 포함)
    include_chunk_text: bool = True  # Citation에 chunk 텍스트 포함 여부
    max_chunk_preview_length: int = 200  # Citation 미리보기 텍스트 최대 길이


@dataclass
class APIConfig:
    """API 설정"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list = None  # 프로덕션에서는 구체적인 도메인 지정
    
    def __post_init__(self):
        if self.cors_origins is None:
            # 개발 환경에서만 모든 origin 허용
            self.cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]


@dataclass
class LoggingConfig:
    """로깅 설정"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: str = "logs/mcp-rag.log"
    max_file_size_mb: int = 10
    backup_count: int = 5


class Settings:
    """전체 설정 클래스"""
    
    def __init__(self):
        self.model = ModelConfig()
        self.knowledge_base = KnowledgeBaseConfig()
        self.session = SessionConfig()
        self.citation = CitationConfig()
        self.api = APIConfig()
        self.logging = LoggingConfig()
        
        # 환경변수에서 설정 오버라이드
        self._load_from_env()
    
    def _load_from_env(self):
        """환경변수에서 설정값 로드"""
        # AWS 설정
        if os.getenv("AWS_REGION"):
            self.model.region = os.getenv("AWS_REGION")
            self.knowledge_base.region = os.getenv("AWS_REGION")
        
        # Knowledge Base ID
        if os.getenv("KB_ID"):
            self.knowledge_base.kb_id = os.getenv("KB_ID")
        
        # 모델 설정
        if os.getenv("PRIMARY_MODEL_ID"):
            self.model.primary_model_id = os.getenv("PRIMARY_MODEL_ID")
        
        if os.getenv("RERANK_MODEL_ID"):
            self.model.rerank_model_id = os.getenv("RERANK_MODEL_ID")
        
        # API 설정
        if os.getenv("API_HOST"):
            self.api.host = os.getenv("API_HOST")
        
        if os.getenv("API_PORT"):
            self.api.port = int(os.getenv("API_PORT"))
        
        if os.getenv("DEBUG"):
            self.api.debug = os.getenv("DEBUG").lower() == "true"
    
    def validate(self) -> bool:
        """설정값 유효성 검증"""
        errors = []
        
        # 필수 설정 확인
        if not self.knowledge_base.kb_id:
            errors.append("KB_ID is required")
        
        if not self.model.primary_model_id:
            errors.append("PRIMARY_MODEL_ID is required")
        
        # 범위 검증
        if self.model.temperature < 0 or self.model.temperature > 1:
            errors.append("Temperature must be between 0 and 1")
        
        if self.knowledge_base.max_results < 1 or self.knowledge_base.max_results > 100:
            errors.append("KB max_results must be between 1 and 100")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")
        
        return True


# 전역 설정 인스턴스
settings = Settings()

# 설정 검증
try:
    settings.validate()
    print("Configuration loaded and validated successfully")
except ValueError as e:
    print(f"Configuration error: {e}")
    raise
