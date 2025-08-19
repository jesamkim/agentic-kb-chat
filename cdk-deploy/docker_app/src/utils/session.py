"""
세션 관리 유틸리티
대화 연속성과 컨텍스트 관리를 담당합니다.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import uuid
import threading
import time
from config.settings import settings
from src.utils.logger import session_logger
from src.utils.citation import CitationCollection


@dataclass
class Message:
    """대화 메시지 데이터 모델"""
    id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    citations: Optional[CitationCollection] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        result = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
        
        if self.citations:
            result["citations"] = self.citations.to_dict()
        
        return result
    
    @classmethod
    def create_user_message(cls, content: str) -> 'Message':
        """사용자 메시지 생성"""
        return cls(
            id=str(uuid.uuid4()),
            role="user",
            content=content
        )
    
    @classmethod
    def create_assistant_message(cls, content: str, citations: Optional[CitationCollection] = None) -> 'Message':
        """어시스턴트 메시지 생성"""
        return cls(
            id=str(uuid.uuid4()),
            role="assistant",
            content=content,
            citations=citations
        )
    
    @classmethod
    def create_system_message(cls, content: str) -> 'Message':
        """시스템 메시지 생성"""
        return cls(
            id=str(uuid.uuid4()),
            role="system",
            content=content
        )


@dataclass
class SessionContext:
    """세션 컨텍스트 정보"""
    system_prompt: str = ""
    kb_id: str = settings.knowledge_base.kb_id
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    custom_settings: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "kb_id": self.kb_id,
            "user_preferences": self.user_preferences,
            "custom_settings": self.custom_settings
        }


class ChatSession:
    """개별 채팅 세션 관리"""
    
    def __init__(self, session_id: Optional[str] = None, context: Optional[SessionContext] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.context = context or SessionContext()
        self.messages: List[Message] = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self._lock = threading.Lock()
        
        session_logger.log_session_event(self.session_id, "created")
    
    def add_message(self, message: Message) -> None:
        """메시지 추가"""
        with self._lock:
            self.messages.append(message)
            self.last_activity = datetime.now()
            
            # 히스토리 길이 제한
            max_length = settings.session.max_history_length
            if len(self.messages) > max_length:
                # 시스템 메시지는 보존하고 오래된 대화만 제거
                system_messages = [msg for msg in self.messages if msg.role == "system"]
                other_messages = [msg for msg in self.messages if msg.role != "system"]
                
                # 최근 메시지만 유지
                recent_messages = other_messages[-(max_length - len(system_messages)):]
                self.messages = system_messages + recent_messages
                
                session_logger.log_session_event(
                    self.session_id, 
                    "history_trimmed", 
                    f"Kept {len(self.messages)} messages"
                )
    
    def get_conversation_history(self, include_system: bool = True) -> List[Message]:
        """대화 히스토리 반환"""
        with self._lock:
            if include_system:
                return self.messages.copy()
            else:
                return [msg for msg in self.messages if msg.role != "system"]
    
    def get_recent_context(self, max_messages: int = 10) -> List[Message]:
        """최근 컨텍스트 반환"""
        with self._lock:
            return self.messages[-max_messages:] if self.messages else []
    
    def update_context(self, **kwargs) -> None:
        """세션 컨텍스트 업데이트"""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.context, key):
                    setattr(self.context, key, value)
                    session_logger.log_session_event(
                        self.session_id, 
                        "context_updated", 
                        f"{key} updated"
                    )
    
    def clear_history(self, keep_system_messages: bool = True) -> None:
        """대화 히스토리 초기화"""
        with self._lock:
            if keep_system_messages:
                system_messages = [msg for msg in self.messages if msg.role == "system"]
                self.messages = system_messages
            else:
                self.messages = []
            
            session_logger.log_session_event(self.session_id, "history_cleared")
    
    def is_expired(self) -> bool:
        """세션 만료 여부 확인"""
        timeout = timedelta(minutes=settings.session.session_timeout_minutes)
        return datetime.now() - self.last_activity > timeout
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        with self._lock:
            return {
                "session_id": self.session_id,
                "context": self.context.to_dict(),
                "messages": [msg.to_dict() for msg in self.messages],
                "created_at": self.created_at.isoformat(),
                "last_activity": self.last_activity.isoformat(),
                "message_count": len(self.messages)
            }


class SessionManager:
    """전역 세션 관리자"""
    
    def __init__(self):
        self.sessions: Dict[str, ChatSession] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = None
        self._start_cleanup_thread()
    
    def create_session(self, context: Optional[SessionContext] = None) -> ChatSession:
        """새 세션 생성"""
        session = ChatSession(context=context)
        
        with self._lock:
            self.sessions[session.session_id] = session
        
        session_logger.log_session_event(session.session_id, "registered")
        return session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """세션 반환"""
        with self._lock:
            session = self.sessions.get(session_id)
            if session and not session.is_expired():
                return session
            elif session and session.is_expired():
                # 만료된 세션 제거
                del self.sessions[session_id]
                session_logger.log_session_event(session_id, "expired_and_removed")
            return None
    
    def get_or_create_session(self, session_id: Optional[str] = None, 
                            context: Optional[SessionContext] = None) -> ChatSession:
        """세션 반환 또는 생성"""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        
        # 새 세션 생성
        return self.create_session(context)
    
    def delete_session(self, session_id: str) -> bool:
        """세션 삭제"""
        with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                session_logger.log_session_event(session_id, "deleted")
                return True
            return False
    
    def get_active_sessions(self) -> List[str]:
        """활성 세션 ID 목록 반환"""
        with self._lock:
            active_sessions = []
            for session_id, session in self.sessions.items():
                if not session.is_expired():
                    active_sessions.append(session_id)
            return active_sessions
    
    def cleanup_expired_sessions(self) -> int:
        """만료된 세션 정리"""
        expired_count = 0
        
        with self._lock:
            expired_sessions = []
            for session_id, session in self.sessions.items():
                if session.is_expired():
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del self.sessions[session_id]
                expired_count += 1
        
        if expired_count > 0:
            session_logger.log_session_event(
                "system", 
                "cleanup_completed", 
                f"Removed {expired_count} expired sessions"
            )
        
        return expired_count
    
    def _start_cleanup_thread(self):
        """정리 스레드 시작"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(settings.session.memory_cleanup_interval)
                    self.cleanup_expired_sessions()
                except Exception as e:
                    session_logger.log_error(e, "cleanup_thread")
        
        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        session_logger.log_session_event("system", "cleanup_thread_started")
    
    def get_stats(self) -> Dict[str, Any]:
        """세션 통계 반환"""
        with self._lock:
            total_sessions = len(self.sessions)
            active_sessions = len(self.get_active_sessions())
            
            total_messages = sum(len(session.messages) for session in self.sessions.values())
            
            return {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "expired_sessions": total_sessions - active_sessions,
                "total_messages": total_messages,
                "average_messages_per_session": total_messages / total_sessions if total_sessions > 0 else 0
            }


# 전역 세션 매니저 인스턴스
session_manager = SessionManager()
