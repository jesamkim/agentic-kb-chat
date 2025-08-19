"""
로깅 유틸리티
프로젝트 전반에서 사용할 로깅 설정과 유틸리티 함수들
"""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional
from config.settings import settings


class Logger:
    """중앙화된 로거 관리 클래스"""
    
    _loggers = {}
    _initialized = False
    
    @classmethod
    def setup_logging(cls) -> None:
        """로깅 시스템 초기화"""
        if cls._initialized:
            return
        
        # 로그 디렉토리 생성
        log_dir = Path(settings.logging.file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 루트 로거 설정
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, settings.logging.level.upper()))
        
        # 기존 핸들러 제거
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 포맷터 생성
        formatter = logging.Formatter(settings.logging.format)
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # 파일 핸들러 (로테이션)
        file_handler = logging.handlers.RotatingFileHandler(
            settings.logging.file_path,
            maxBytes=settings.logging.max_file_size_mb * 1024 * 1024,
            backupCount=settings.logging.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, settings.logging.level.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        cls._initialized = True
        
        # 초기화 로그
        logger = cls.get_logger("Logger")
        logger.info("Logging system initialized")
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """이름별 로거 반환"""
        if not cls._initialized:
            cls.setup_logging()
        
        if name not in cls._loggers:
            logger = logging.getLogger(name)
            cls._loggers[name] = logger
        
        return cls._loggers[name]


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """편의 함수: 로거 반환"""
    if name is None:
        # 호출한 모듈의 이름을 자동으로 사용
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'unknown')
    
    return Logger.get_logger(name)


class StructuredLogger:
    """구조화된 로깅을 위한 클래스"""
    
    def __init__(self, name: str):
        self.logger = get_logger(name)
    
    def log_agent_action(self, agent_name: str, action: str, details: dict = None):
        """Agent 액션 로깅"""
        message = f"[{agent_name}] {action}"
        if details:
            message += f" - {details}"
        self.logger.info(message)
    
    def log_mcp_call(self, tool_name: str, parameters: dict, result_summary: str):
        """MCP 도구 호출 로깅"""
        self.logger.info(f"MCP Call: {tool_name} | Params: {parameters} | Result: {result_summary}")
    
    def log_kb_search(self, query: str, result_count: int, search_time: float):
        """KB 검색 로깅"""
        self.logger.info(f"KB Search: '{query}' | Results: {result_count} | Time: {search_time:.2f}s")
    
    def log_rerank(self, original_count: int, reranked_count: int, rerank_time: float):
        """ReRank 처리 로깅"""
        self.logger.info(f"ReRank: {original_count} -> {reranked_count} results | Time: {rerank_time:.2f}s")
    
    def log_citation_processing(self, citation_count: int, duplicates_removed: int):
        """Citation 처리 로깅"""
        self.logger.info(f"Citations: {citation_count} processed, {duplicates_removed} duplicates removed")
    
    def log_session_event(self, session_id: str, event: str, details: str = ""):
        """세션 이벤트 로깅"""
        message = f"Session[{session_id[:8]}]: {event}"
        if details:
            message += f" - {details}"
        self.logger.info(message)
    
    def log_error(self, error: Exception, context: str = ""):
        """에러 로깅"""
        message = f"Error in {context}: {str(error)}" if context else f"Error: {str(error)}"
        self.logger.error(message, exc_info=True)
    
    def log_performance(self, operation: str, duration: float, details: dict = None):
        """성능 로깅"""
        message = f"Performance: {operation} took {duration:.2f}s"
        if details:
            message += f" | {details}"
        self.logger.info(message)


# 전역 구조화된 로거 인스턴스들
main_logger = StructuredLogger("main")
agent_logger = StructuredLogger("agents")
mcp_logger = StructuredLogger("mcp")
session_logger = StructuredLogger("session")
api_logger = StructuredLogger("api")

# 로깅 시스템 초기화
Logger.setup_logging()
