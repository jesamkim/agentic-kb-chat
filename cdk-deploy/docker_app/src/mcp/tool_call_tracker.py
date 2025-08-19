"""
MCP Tool Call Tracker
MCP Tool 호출을 추적하고 UI에 표시할 메시지를 생성하는 모듈
"""

from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import time
from dataclasses import dataclass
from enum import Enum

from src.utils.logger import mcp_logger


class ToolCallStatus(Enum):
    """Tool 호출 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ToolCallInfo:
    """Tool 호출 정보"""
    call_id: str
    tool_name: str
    parameters: Dict[str, Any]
    stage: str
    status: ToolCallStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    ui_message: Optional[str] = None
    
    def get_duration(self) -> float:
        """호출 소요 시간 반환"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "stage": self.stage,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.get_duration(),
            "ui_message": self.ui_message,
            "error_message": self.error_message,
            "result_summary": self._get_result_summary()
        }
    
    def _get_result_summary(self) -> Dict[str, Any]:
        """결과 요약 정보"""
        if not self.result:
            return {}
        
        if self.tool_name == "kb_search":
            return {
                "citation_count": len(self.result.get("citations", [])),
                "search_time": self.result.get("search_time", 0)
            }
        
        return {"status": self.result.get("status", "unknown")}


class MCPToolCallTracker:
    """MCP Tool 호출 추적 및 표시 시스템"""
    
    def __init__(self):
        self.active_calls: Dict[str, ToolCallInfo] = {}
        self.completed_calls: List[ToolCallInfo] = []
        self.ui_callback: Optional[Callable] = None
        self.call_counter = 0
        
        mcp_logger.log_mcp_call("tool_call_tracker_init", {}, "success")
    
    def set_ui_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """UI 업데이트 콜백 설정"""
        self.ui_callback = callback
    
    def start_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        stage: str = "search"
    ) -> str:
        """
        Tool 호출 시작 추적
        
        Args:
            tool_name: 호출할 도구 이름
            parameters: 도구 파라미터
            stage: 호출 단계 (primary_search, additional_search_1, etc.)
            
        Returns:
            호출 ID
        """
        self.call_counter += 1
        call_id = f"call_{self.call_counter}_{int(time.time() * 1000)}"
        
        # UI 메시지 생성
        ui_message = self._generate_ui_message(tool_name, parameters, stage, "start")
        
        # 호출 정보 생성
        call_info = ToolCallInfo(
            call_id=call_id,
            tool_name=tool_name,
            parameters=parameters,
            stage=stage,
            status=ToolCallStatus.RUNNING,
            start_time=datetime.now(),
            ui_message=ui_message
        )
        
        self.active_calls[call_id] = call_info
        
        # UI 업데이트
        if self.ui_callback:
            self.ui_callback("tool_call_start", call_info.to_dict())
        
        mcp_logger.log_mcp_call(
            "tool_call_start",
            {
                "call_id": call_id,
                "tool_name": tool_name,
                "stage": stage,
                "parameters_summary": self._summarize_parameters(parameters)
            },
            "success"
        )
        
        return call_id
    
    def complete_tool_call(
        self,
        call_id: str,
        result: Dict[str, Any]
    ):
        """Tool 호출 완료 처리"""
        if call_id not in self.active_calls:
            return
        
        call_info = self.active_calls[call_id]
        call_info.status = ToolCallStatus.COMPLETED
        call_info.end_time = datetime.now()
        call_info.result = result
        
        # 완료 UI 메시지 생성
        completion_message = self._generate_ui_message(
            call_info.tool_name,
            call_info.parameters,
            call_info.stage,
            "complete",
            result
        )
        call_info.ui_message = completion_message
        
        # 완료된 호출로 이동
        self.completed_calls.append(call_info)
        del self.active_calls[call_id]
        
        # UI 업데이트
        if self.ui_callback:
            self.ui_callback("tool_call_complete", call_info.to_dict())
        
        mcp_logger.log_mcp_call(
            "tool_call_complete",
            {
                "call_id": call_id,
                "duration": call_info.get_duration(),
                "result_summary": call_info._get_result_summary()
            },
            "success"
        )
    
    def fail_tool_call(
        self,
        call_id: str,
        error_message: str
    ):
        """Tool 호출 실패 처리"""
        if call_id not in self.active_calls:
            return
        
        call_info = self.active_calls[call_id]
        call_info.status = ToolCallStatus.FAILED
        call_info.end_time = datetime.now()
        call_info.error_message = error_message
        
        # 실패 UI 메시지 생성
        failure_message = self._generate_ui_message(
            call_info.tool_name,
            call_info.parameters,
            call_info.stage,
            "fail",
            error_message=error_message
        )
        call_info.ui_message = failure_message
        
        # 완료된 호출로 이동
        self.completed_calls.append(call_info)
        del self.active_calls[call_id]
        
        # UI 업데이트
        if self.ui_callback:
            self.ui_callback("tool_call_failed", call_info.to_dict())
        
        mcp_logger.log_mcp_call(
            "tool_call_failed",
            {
                "call_id": call_id,
                "error": error_message,
                "duration": call_info.get_duration()
            },
            "error"
        )
    
    def _generate_ui_message(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        stage: str,
        action: str,  # start, complete, fail
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> str:
        """UI 표시용 메시지 생성"""
        
        # 단계별 아이콘 및 설명
        stage_info = {
            "primary_search": {"icon": "🔍", "desc": "1차 검색"},
            "additional_search_1": {"icon": "🔍", "desc": "추가 검색 1"},
            "additional_search_2": {"icon": "🔍", "desc": "추가 검색 2"},
            "additional_search_3": {"icon": "🔍", "desc": "추가 검색 3"},
            "additional_search_4": {"icon": "🔍", "desc": "추가 검색 4"},
            "additional_search_5": {"icon": "🔍", "desc": "추가 검색 5"},
            "rerank": {"icon": "📊", "desc": "결과 재정렬"},
            "integration": {"icon": "🔗", "desc": "결과 통합"}
        }
        
        # 기본 정보
        icon = stage_info.get(stage, {}).get("icon", "🔧")
        desc = stage_info.get(stage, {}).get("desc", stage)
        
        # 도구별 메시지 생성
        if tool_name == "kb_search":
            query = parameters.get("query", "")[:50]  # 50자로 제한
            
            if action == "start":
                return f"{icon} {desc}: '{query}' 키워드로 KB 검색 중..."
            elif action == "complete" and result:
                citation_count = len(result.get("citations", []))
                search_time = result.get("search_time", 0)
                return f"✅ {desc} 완료: {citation_count}개 결과 ({search_time:.1f}초)"
            elif action == "fail":
                return f"❌ {desc} 실패: {error_message}"
        
        elif tool_name == "rerank":
            if action == "start":
                return f"{icon} {desc}: 검색 결과 재정렬 중..."
            elif action == "complete" and result:
                reranked_count = len(result.get("reranked_results", []))
                return f"✅ {desc} 완료: {reranked_count}개 결과 재정렬"
            elif action == "fail":
                return f"❌ {desc} 실패: {error_message}"
        
        # 기본 메시지
        if action == "start":
            return f"{icon} {desc} 실행 중..."
        elif action == "complete":
            return f"✅ {desc} 완료"
        elif action == "fail":
            return f"❌ {desc} 실패: {error_message}"
        
        return f"{icon} {desc}"
    
    def _summarize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """파라미터 요약 (로깅용)"""
        summary = {}
        
        for key, value in parameters.items():
            if key == "query" and isinstance(value, str):
                summary[key] = value[:100]  # 쿼리는 100자로 제한
            elif key == "max_results":
                summary[key] = value
            elif key == "search_type":
                summary[key] = value
            else:
                summary[key] = str(type(value).__name__)
        
        return summary
    
    def get_active_calls(self) -> List[Dict[str, Any]]:
        """현재 활성 호출 목록 반환"""
        return [call_info.to_dict() for call_info in self.active_calls.values()]
    
    def get_completed_calls(self, limit: int = 10) -> List[Dict[str, Any]]:
        """완료된 호출 목록 반환 (최근 순)"""
        return [call_info.to_dict() for call_info in self.completed_calls[-limit:]]
    
    def get_call_statistics(self) -> Dict[str, Any]:
        """호출 통계 반환"""
        total_calls = len(self.completed_calls)
        if total_calls == 0:
            return {"total_calls": 0}
        
        successful_calls = sum(1 for call in self.completed_calls if call.status == ToolCallStatus.COMPLETED)
        failed_calls = sum(1 for call in self.completed_calls if call.status == ToolCallStatus.FAILED)
        
        total_duration = sum(call.get_duration() for call in self.completed_calls)
        avg_duration = total_duration / total_calls
        
        # 도구별 통계
        tool_stats = {}
        for call in self.completed_calls:
            tool_name = call.tool_name
            if tool_name not in tool_stats:
                tool_stats[tool_name] = {"count": 0, "success": 0, "total_duration": 0}
            
            tool_stats[tool_name]["count"] += 1
            tool_stats[tool_name]["total_duration"] += call.get_duration()
            if call.status == ToolCallStatus.COMPLETED:
                tool_stats[tool_name]["success"] += 1
        
        # 평균 계산
        for tool_name, stats in tool_stats.items():
            stats["avg_duration"] = stats["total_duration"] / stats["count"]
            stats["success_rate"] = stats["success"] / stats["count"] * 100
        
        return {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "success_rate": round(successful_calls / total_calls * 100, 1),
            "average_duration": round(avg_duration, 3),
            "active_calls": len(self.active_calls),
            "tool_statistics": tool_stats
        }
    
    def clear_completed_calls(self):
        """완료된 호출 기록 정리"""
        # 최근 50개만 유지
        if len(self.completed_calls) > 50:
            self.completed_calls = self.completed_calls[-50:]
    
    def generate_progress_summary(self) -> Dict[str, Any]:
        """진행 상황 요약 생성 (UI용)"""
        active_calls = list(self.active_calls.values())
        recent_completed = self.completed_calls[-5:] if self.completed_calls else []
        
        progress_messages = []
        
        # 활성 호출 메시지
        for call in active_calls:
            progress_messages.append({
                "type": "active",
                "message": call.ui_message,
                "stage": call.stage,
                "status": "running"
            })
        
        # 최근 완료된 호출 메시지
        for call in recent_completed:
            progress_messages.append({
                "type": "completed",
                "message": call.ui_message,
                "stage": call.stage,
                "status": call.status.value,
                "duration": call.get_duration()
            })
        
        return {
            "active_count": len(active_calls),
            "completed_count": len(self.completed_calls),
            "progress_messages": progress_messages,
            "overall_status": "running" if active_calls else "idle"
        }


# 전역 인스턴스
tool_call_tracker = MCPToolCallTracker()
