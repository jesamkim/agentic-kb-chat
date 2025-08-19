"""
Configuration file for Agentic RAG Chatbot deployment
"""
import os


class Config:
    """Configuration class for CDK deployment"""
    
    # Stack configuration
    STACK_NAME = "agentic-rag-chatbot"
    
    # Application configuration
    APP_NAME = "agentic-rag-chatbot"
    APP_PORT = 8501
    
    # AWS Configuration
    AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
    
    # Bedrock Configuration
    KB_ID = os.getenv("KB_ID", "YOUR_KB_ID_HERE")
    MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
    
    # ECS Configuration
    CPU = 1024  # 1 vCPU
    MEMORY = 2048  # 2GB RAM
    MIN_CAPACITY = 1
    MAX_CAPACITY = 3
    
    # Health check configuration
    HEALTH_CHECK_PATH = "/health"
    HEALTH_CHECK_INTERVAL = 30
    HEALTH_CHECK_TIMEOUT = 5
    HEALTH_CHECK_RETRIES = 3
    
    # CloudFront configuration
    CUSTOM_HEADER_NAME = "X-Agentic-RAG-Header"
    CUSTOM_HEADER_VALUE = os.getenv("CUSTOM_HEADER_VALUE", "agentic-rag-secret-header")
    
    # Logging configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if cls.KB_ID == "YOUR_KB_ID_HERE":
            raise ValueError("KB_ID must be set in environment variables")
        
        return True
