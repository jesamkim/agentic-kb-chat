"""
Production settings for Agentic RAG Chatbot
Environment variable based configuration for containerized deployment
"""
import os
from typing import Optional


class KnowledgeBaseSettings:
    """Knowledge Base configuration"""
    kb_id: str = os.getenv("KB_ID", "YOUR_KB_ID_HERE")
    region: str = os.getenv("AWS_REGION", "us-west-2")
    max_results: int = int(os.getenv("KB_MAX_RESULTS", "50"))
    search_type: str = os.getenv("KB_SEARCH_TYPE", "HYBRID")
    enable_rerank: bool = os.getenv("ENABLE_RERANK", "false").lower() == "true"


class ModelSettings:
    """Model configuration"""
    primary_model_id: str = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    region: str = os.getenv("AWS_REGION", "us-west-2")
    temperature: float = float(os.getenv("MODEL_TEMPERATURE", "0.0"))
    max_tokens: int = int(os.getenv("MODEL_MAX_TOKENS", "4000"))


class ReRankSettings:
    """ReRank service configuration"""
    model_id: str = os.getenv("RERANK_MODEL_ID", "cohere.rerank-v3-5:0")
    region: str = os.getenv("AWS_REGION", "us-west-2")
    top_k: int = int(os.getenv("RERANK_TOP_K", "20"))


class UISettings:
    """UI configuration"""
    page_title: str = "Agentic RAG Chatbot"
    page_icon: str = "🤖"
    layout: str = "wide"
    sidebar_state: str = "expanded"
    theme: str = "light"


class LoggingSettings:
    """Logging configuration"""
    level: str = os.getenv("LOG_LEVEL", "INFO")
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class Settings:
    """Main settings class"""
    knowledge_base = KnowledgeBaseSettings()
    model = ModelSettings()
    rerank = ReRankSettings()
    ui = UISettings()
    logging = LoggingSettings()
    
    # Application settings
    app_name: str = "Agentic RAG Chatbot"
    version: str = "1.0.0"
    environment: str = os.getenv("ENVIRONMENT", "production")
    
    # Health check settings
    health_check_path: str = "/health"
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        if cls.knowledge_base.kb_id == "YOUR_KB_ID_HERE":
            raise ValueError("KB_ID environment variable must be set")
        
        return True


# Global settings instance
settings = Settings()

# Validate settings on import
if os.getenv("SKIP_VALIDATION") != "true":
    try:
        settings.validate()
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
        # Don't raise in production, just log
        if settings.environment != "production":
            raise
