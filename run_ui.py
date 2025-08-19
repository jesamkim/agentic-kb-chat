#!/usr/bin/env python3
"""
MCP RAG Chatbot UI 실행 스크립트
"""

import subprocess
import sys
import os

def main():
    """Streamlit UI 실행"""
    
    # 프로젝트 루트 디렉토리로 이동
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    # Streamlit 앱 실행
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        "ui/app.py",
        "--server.port", "8501",
        "--server.address", "0.0.0.0",
        "--server.headless", "true"
    ]
    
    print("🚀 MCP RAG Chatbot UI 시작 중...")
    print(f"📍 URL: http://localhost:8501")
    print("🔄 Ctrl+C로 종료")
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n👋 UI 종료됨")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()
