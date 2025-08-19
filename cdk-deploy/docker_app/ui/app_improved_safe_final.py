"""
Improved MCP RAG Chatbot - Final Safe Streamlit UI
Citation 표시 기능이 포함된 최종 안전한 UI
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
import time
import threading
from queue import Queue

# 프로젝트 루트를 Python path에 추가 (컨테이너 환경 대응)
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # /app 디렉토리
sys.path.append(project_root)

# 이미지 처리 유틸리티 import
from utils.image_utils import process_image_for_bedrock, get_image_info

from src.agents.react_agent_improved_safe import improved_react_agent
from src.utils.session import SessionManager
from config.settings import settings
from ui.citation_display import display_citation_expandable_with_id, display_citation_expandable

# 페이지 설정
st.set_page_config(
    page_title="Agentic RAG chatbot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "improved_react_agent" not in st.session_state:
    st.session_state.improved_react_agent = None
if "session_manager" not in st.session_state:
    st.session_state.session_manager = None
if "kb_id" not in st.session_state:
    st.session_state.kb_id = "CQLBN9MFDZ"
if "ui_updates" not in st.session_state:
    st.session_state.ui_updates = Queue()
if "current_progress" not in st.session_state:
    st.session_state.current_progress = {}


def initialize_improved_agents(kb_id: str):
    """개선된 Agent 및 세션 매니저 초기화"""
    try:
        # KB_ID 설정 업데이트
        settings.knowledge_base.kb_id = kb_id
        
        # 개선된 Agent 초기화 (안전한 버전)
        react_agent = improved_react_agent
        session_manager = SessionManager()
        
        return react_agent, session_manager
    except Exception as e:
        st.error(f"개선된 Agent 초기화 실패: {e}")
        return None, None


def ui_callback(update_type: str, data: Dict[str, Any]):
    """UI 업데이트 콜백 함수"""
    try:
        # 세션 상태에 업데이트 저장
        st.session_state.ui_updates.put({
            "type": update_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
        
        # 현재 진행 상황 업데이트
        if update_type == "stage_update":
            stage = data.get("stage", "unknown")
            message = data.get("message", "")
            st.session_state.current_progress[stage] = {
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "data": data
            }
        elif update_type in ["tool_call_start", "tool_call_complete", "tool_call_failed"]:
            # Tool 호출 정보 업데이트
            call_info = data
            call_id = call_info.get("call_id", "unknown")
            st.session_state.current_progress[f"tool_call_{call_id}"] = call_info
            
    except Exception as e:
        print(f"UI 콜백 오류: {e}")


def display_enhanced_progress():
    """개선된 진행 상황 표시"""
    if not st.session_state.current_progress:
        return
    
    progress_container = st.container()
    
    with progress_container:
        st.markdown("### 🔄 처리 진행 상황")
        
        # 단계별 진행 상황
        stages = [
            ("intent_analysis", "🧠 의도 분석"),
            ("multi_stage_search", "🔍 다단계 검색"),
            ("response_generation", "📝 응답 생성")
        ]
        
        cols = st.columns(len(stages))
        
        for i, (stage_key, stage_name) in enumerate(stages):
            with cols[i]:
                if stage_key in st.session_state.current_progress:
                    stage_info = st.session_state.current_progress[stage_key]
                    message = stage_info.get("message", "")
                    
                    if "완료" in message or "✅" in message:
                        st.success(f"{stage_name} ✅")
                    elif "중" in message or "⏳" in message:
                        st.info(f"{stage_name} ⏳")
                    else:
                        st.info(f"{stage_name} ⏸️")
                else:
                    st.info(f"{stage_name} ⏸️")
        
        # Tool 호출 상세 정보
        tool_calls = [
            key for key in st.session_state.current_progress.keys() 
            if key.startswith("tool_call_")
        ]
        
        if tool_calls:
            st.markdown("#### 🔧 MCP Tool 호출 상황")
            
            for tool_call_key in tool_calls[-5:]:  # 최근 5개만 표시
                call_info = st.session_state.current_progress[tool_call_key]
                ui_message = call_info.get("ui_message", "")
                status = call_info.get("status", "unknown")
                
                if status == "completed":
                    st.success(ui_message)
                elif status == "running":
                    st.info(ui_message)
                elif status == "failed":
                    st.error(ui_message)
                else:
                    st.info(ui_message)


def display_intent_analysis_results(analysis_result: Dict[str, Any]):
    """의도 분석 결과 표시"""
    if not analysis_result:
        return
    
    with st.expander("🧠 의도 분석 결과", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "주요 의도", 
                analysis_result.get("primary_intent", "unknown").replace("_", " ")
            )
        
        with col2:
            st.metric(
                "복잡도", 
                analysis_result.get("complexity", "보통")
            )
        
        with col3:
            additional_searches = analysis_result.get("requires_additional_search", False)
            st.metric(
                "추가 검색", 
                "필요" if additional_searches else "불필요"
            )
        
        # 추가 검색 쿼리
        additional_queries = analysis_result.get("additional_search_queries", [])
        if additional_queries:
            st.markdown("**추가 검색 쿼리:**")
            for i, query in enumerate(additional_queries, 1):
                st.markdown(f"{i}. {query}")
        
        # 핵심 엔티티
        key_entities = analysis_result.get("key_entities", [])
        if key_entities:
            st.markdown("**핵심 엔티티:**")
            st.markdown(", ".join(key_entities))


def display_search_quality_metrics(search_results: Dict[str, Any]):
    """검색 품질 메트릭 표시"""
    quality_metrics = search_results.get("quality_metrics", {})
    if not quality_metrics:
        return
    
    with st.expander("📊 검색 품질 메트릭", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "전체 품질", 
                f"{quality_metrics.get('overall_quality', 0):.2f}",
                help="검색 결과의 전반적인 품질 점수"
            )
        
        with col2:
            st.metric(
                "관련성", 
                f"{quality_metrics.get('relevance_score', 0):.2f}",
                help="검색 결과의 관련성 점수"
            )
        
        with col3:
            st.metric(
                "커버리지", 
                f"{quality_metrics.get('coverage_score', 0):.2f}",
                help="핵심 엔티티 커버리지 점수"
            )
        
        with col4:
            st.metric(
                "다양성", 
                f"{quality_metrics.get('diversity_score', 0):.2f}",
                help="검색 결과의 다양성 점수"
            )


def display_response_quality_metrics(response_metadata: Dict[str, Any]):
    """응답 품질 메트릭 표시"""
    response_quality = response_metadata.get("response_quality", {})
    token_usage = response_metadata.get("token_usage", {})
    
    if not response_quality and not token_usage:
        return
    
    with st.expander("📝 응답 품질 메트릭", expanded=False):
        if response_quality:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "전체 품질", 
                    f"{response_quality.get('overall_quality', 0):.2f}"
                )
            
            with col2:
                st.metric(
                    "구조화 점수", 
                    f"{response_quality.get('structure_score', 0):.2f}"
                )
            
            with col3:
                st.metric(
                    "의도 충족도", 
                    f"{response_quality.get('intent_score', 0):.2f}"
                )
            
            with col4:
                st.metric(
                    "Citation 활용", 
                    f"{response_quality.get('citation_score', 0):.2f}"
                )
        
        if token_usage:
            st.markdown("**토큰 사용량:**")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("총 토큰", token_usage.get("total_tokens", 0))
            
            with col2:
                st.metric("단어 수", token_usage.get("word_count", 0))
            
            with col3:
                utilization = token_usage.get("utilization_rate", 0)
                st.metric("사용률", f"{utilization}%")
                
                # 사용률에 따른 색상 표시
                if utilization > 90:
                    st.warning("토큰 사용률이 높습니다 (90% 이상)")
                elif utilization > 70:
                    st.info("토큰 사용률이 적절합니다 (70-90%)")


def process_enhanced_query_with_progress(query: str, image_data: Optional[str] = None):
    """개선된 진행 상황 표시와 함께 쿼리 처리"""
    
    # 진행 상황 초기화
    st.session_state.current_progress = {}
    
    # 진행 상황 표시 영역
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    
    try:
        # 1단계: 의도 분석 시작
        with progress_placeholder.container():
            st.markdown("### 🔄 처리 중...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.text("🧠 사용자 의도 분석 중...")
        
        # 개선된 ReAct Agent로 처리 (안전한 버전)
        def progress_callback(stage, message, progress=None):
            """진행 상황 업데이트 콜백"""
            try:
                with progress_placeholder.container():
                    st.markdown("### 🔄 처리 중...")
                    
                    if progress is not None:
                        progress_bar = st.progress(progress / 100)
                    else:
                        progress_bar = st.progress(0)
                    
                    # 단계별 상태 표시
                    if stage == "intent_analysis":
                        status_text = st.empty()
                        status_text.text(f"🧠 {message}")
                        if progress is None:
                            progress_bar.progress(10)
                    elif stage == "kb_search":
                        status_text = st.empty()
                        status_text.text(f"🔍 {message}")
                        if progress is None:
                            progress_bar.progress(30)
                    elif stage == "multi_stage_search":
                        status_text = st.empty()
                        status_text.text(f"🔍 {message}")
                        if progress is None:
                            progress_bar.progress(60)
                    elif stage == "response_generation":
                        status_text = st.empty()
                        status_text.text(f"📝 {message}")
                        if progress is None:
                            progress_bar.progress(80)
                    elif stage == "complete":
                        status_text = st.empty()
                        status_text.text(f"✅ {message}")
                        progress_bar.progress(100)
                        
            except Exception as e:
                print(f"Progress callback error: {e}")
        
        # 커스텀 UI 콜백 함수
        def enhanced_ui_callback(update_type: str, data: Dict[str, Any]):
            """향상된 UI 콜백"""
            try:
                if update_type == "stage_update":
                    stage = data.get("stage", "unknown")
                    message = data.get("message", "처리 중...")
                    progress = data.get("progress")
                    progress_callback(stage, message, progress)
                    
                elif update_type == "tool_call_start":
                    tool_name = data.get("tool_name", "도구")
                    if "kb" in tool_name.lower() or "search" in tool_name.lower():
                        progress_callback("kb_search", f"KB 검색 실행 중... ({tool_name})")
                    else:
                        progress_callback("processing", f"도구 실행 중... ({tool_name})")
                        
                elif update_type == "tool_call_complete":
                    tool_name = data.get("tool_name", "도구")
                    duration = data.get("duration", 0)
                    if "kb" in tool_name.lower() or "search" in tool_name.lower():
                        progress_callback("kb_search", f"KB 검색 완료 ({duration:.2f}초)")
                    
                elif update_type == "search_stage_complete":
                    stage_num = data.get("stage_number", 0)
                    total_stages = data.get("total_stages", 1)
                    progress_callback("multi_stage_search", 
                                    f"검색 단계 {stage_num}/{total_stages} 완료")
                    
            except Exception as e:
                print(f"Enhanced UI callback error: {e}")
        
        # 처리 시작
        result = st.session_state.improved_react_agent.process_query_enhanced(
            user_query=query,
            session_id=st.session_state.session_id,
            image_data=image_data,
            ui_callback=enhanced_ui_callback
        )
        
        # 최종 완료 상태 표시
        progress_callback("complete", "처리 완료!", 100)
        
        # 잠시 후 진행 상황 표시 제거
        import time
        time.sleep(1)
        progress_placeholder.empty()
        
        # 최종 처리 결과 요약 (간단하게)
        with status_placeholder.container():
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("처리 시간", f"{result.get('total_processing_time', 0):.1f}초")
            
            with col2:
                st.metric("Citation 수", f"{len(result.get('citations', []))}")
            
            with col3:
                search_stages = len(result.get("metadata", {}).get("search_stages", []))
                st.metric("검색 단계", f"{search_stages}단계")
        
        return result
        
    except Exception as e:
        with progress_placeholder.container():
            st.error(f"처리 중 오류 발생: {e}")
        return None


def main():
    # 헤더
    st.title("🤖 Agentic RAG chatbot")
    
    # 고정된 레인보우 그라데이션 이탤릭체 텍스트 (왼쪽 정렬)
    st.markdown("""
    <style>
    .rainbow-subtitle-docker {
        font-style: italic;
        font-size: 16px;
        background: linear-gradient(90deg, 
            #ff0000, #ff7f00, #ffff00, #00ff00, 
            #0000ff, #4b0082, #9400d3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: left;
        margin-bottom: 20px;
        font-weight: 500;
    }
    </style>
    <div class="rainbow-subtitle-docker">개선된 ReAct 기반 AI 어시스턴트 - 완전한 Citation 표시 지원</div>
    """, unsafe_allow_html=True)
    
    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 개선된 설정 (Final)")
        
        # KB_ID 설정
        st.subheader("Knowledge Base 설정")
        new_kb_id = st.text_input(
            "KB_ID",
            value=st.session_state.kb_id,
            help="Amazon Bedrock Knowledge Base ID"
        )
        
        if new_kb_id != st.session_state.kb_id:
            st.session_state.kb_id = new_kb_id
            st.session_state.improved_react_agent = None
            st.session_state.session_manager = None
            st.rerun()
        
        # 개선된 Agent 초기화
        if st.session_state.improved_react_agent is None or st.session_state.session_manager is None:
            with st.spinner("개선된 Agent 초기화 중..."):
                react_agent, session_manager = initialize_improved_agents(st.session_state.kb_id)
                if react_agent and session_manager:
                    st.session_state.improved_react_agent = react_agent
                    st.session_state.session_manager = session_manager
                    st.success("개선된 Agent 초기화 완료!")
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
                st.session_state.current_progress = {}
                st.success("새 세션이 생성되었습니다!")
                st.rerun()
        
        if st.session_state.session_id:
            st.info(f"세션 ID: {st.session_state.session_id[:8]}...")
        
        st.divider()
        
        # 개선된 시스템 정보
        st.subheader("시스템 상태")
        
        # 시스템 검증
        if st.session_state.improved_react_agent:
            validation_result = st.session_state.improved_react_agent.validate_enhanced_system()
            system_status = validation_result.get("system_status", "unknown")
            
            if system_status == "healthy":
                st.success("✅ 모든 개선 기능 정상 작동")
            elif system_status == "degraded":
                st.warning(f"⚠️ 일부 기능 제한: {validation_result.get('issues', '')}")
            else:
                st.error(f"❌ 시스템 오류: {validation_result.get('error', '')}")
        
        # 개선 기능 목록
        st.info(f"""
        **개선된 기능들 (Final Version):**
        🧠 **의도 분석**: 사용자 쿼리 의도 자동 파악
        🔍 **다단계 검색**: 1차 검색 + 추가 검색 (최대 5회)
        📝 **토큰 제한**: 3000 토큰 이내 응답 생성 (안전 처리)
        🔧 **Tool 추적**: MCP Tool 호출 실시간 표시
        📊 **품질 메트릭**: 검색 및 응답 품질 측정
        📚 **Citation 표시**: 완전한 파일명 및 내용 표시
        
        **KB_ID**: {st.session_state.kb_id}
        **모델**: Claude 3.7 Sonnet
        **토큰 처리**: tiktoken 안전 fallback 지원
        **Citation**: 파일명 추출 및 확장 표시
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
                if "image" in message:
                    st.image(message["image"], caption="첨부된 이미지", width=300)
            else:
                st.markdown(message["content"])
                
                # 개선된 메타데이터 표시
                if "metadata" in message:
                    metadata = message["metadata"]
                    
                    # 의도 분석 결과
                    if "intent_analysis" in metadata:
                        display_intent_analysis_results(metadata["intent_analysis"])
                    
                    # 검색 품질 메트릭
                    if "search_quality" in metadata:
                        display_search_quality_metrics({"quality_metrics": metadata["search_quality"]})
                    
                    # 응답 품질 메트릭
                    if "response_quality" in metadata or "token_usage" in metadata:
                        display_response_quality_metrics({
                            "response_quality": metadata.get("response_quality", {}),
                            "token_usage": metadata.get("token_usage", {})
                        })
                
                # Citation 표시 - 개선된 버전
                if "citations" in message and message["citations"]:
                    message_id = f"final_msg_{idx}_{hash(str(message.get('timestamp', '')))}"
                    display_citation_expandable_with_id(message["citations"], message["content"], message_id)
    
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
        
        # 이미지 처리 (5MB 제한 대응)
        image_data = None
        image_display = None
        if uploaded_image is not None:
            # 원본 이미지 정보 표시
            original_image = Image.open(uploaded_image)
            original_info = get_image_info(original_image)
            
            # 5MB 초과 시 경고 메시지 표시
            if original_info["size_mb"] > 5.0:
                st.warning(f"⚠️ 이미지 크기가 {original_info['size_mb']}MB로 Bedrock 제한(5MB)을 초과합니다. 자동으로 리사이징합니다.")
            
            # 이미지 처리 (리사이징 포함)
            with st.spinner("이미지 처리 중..."):
                image_data, image_display = process_image_for_bedrock(uploaded_image)
            
            if image_data is None:
                st.error("❌ 이미지 처리에 실패했습니다. 다른 이미지를 시도해보세요.")
                return
            
            # 처리된 이미지 정보 표시
            processed_info = get_image_info(image_display)
            if original_info["size_mb"] > 5.0:
                st.success(f"✅ 이미지가 {processed_info['size_mb']}MB로 리사이징되었습니다.")
                st.info(f"📊 원본: {original_info['width']}x{original_info['height']} ({original_info['size_mb']}MB) → 처리됨: {processed_info['width']}x{processed_info['height']} ({processed_info['size_mb']}MB)")
        
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
            result = process_enhanced_query_with_progress(user_input, image_data)
            
            if result:
                response_content = result.get("content", "응답을 생성할 수 없습니다.")
                st.markdown(response_content)
                
                # 개선된 메타데이터 표시
                metadata = result.get("metadata", {})
                response_metadata = result.get("response_metadata", {})
                
                # 의도 분석 결과 표시
                if "intent_analysis" in result:
                    display_intent_analysis_results(result["intent_analysis"])
                
                # 검색 품질 메트릭 표시
                if "search_quality" in metadata:
                    display_search_quality_metrics({"quality_metrics": metadata["search_quality"]})
                
                # 응답 품질 메트릭 표시
                if response_metadata:
                    display_response_quality_metrics(response_metadata)
                
                # Citation 표시 - 개선된 버전
                citations = result.get("citations", [])
                if citations:
                    new_response_id = f"final_new_{int(time.time() * 1000)}"
                    display_citation_expandable_with_id(citations, response_content, new_response_id)
                
                # 세션에 AI 응답 추가
                ai_message = {
                    "role": "assistant",
                    "content": response_content,
                    "citations": citations,
                    "metadata": {
                        "processing_time": result.get('total_processing_time', 0),
                        "iterations_used": result.get('iterations_used', 0),
                        "primary_intent": metadata.get('primary_intent', 'unknown'),
                        "search_quality": metadata.get('search_quality', {}),
                        "response_quality": response_metadata.get('response_quality', {}),
                        "token_usage": response_metadata.get('token_usage', {}),
                        "enhanced_features": result.get('enhanced_features', {})
                    },
                    "timestamp": datetime.now()
                }
                st.session_state.messages.append(ai_message)
            else:
                st.error("응답을 생성할 수 없습니다. 다시 시도해주세요.")


if __name__ == "__main__":
    main()
