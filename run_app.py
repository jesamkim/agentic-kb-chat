#!/usr/bin/env python3
"""
Agentic RAG Chatbot 실행 스크립트
"""

import subprocess
import sys
import os

def main():
    """메인 애플리케이션 실행"""
    try:
        # 현재 디렉토리를 프로젝트 루트로 변경
        project_root = os.path.dirname(os.path.abspath(__file__))
        os.chdir(project_root)
        
        print("🚀 Agentic RAG Chatbot 시작 중...")
        print(f"📁 프로젝트 경로: {project_root}")
        print("🌐 브라우저에서 http://localhost:8501 로 접속하세요")
        print("⏹️  종료하려면 Ctrl+C를 누르세요")
        print("-" * 50)
        
        # Streamlit 앱 실행
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            "ui/app_improved_safe_final.py",
            "--server.port", "8501",
            "--server.address", "0.0.0.0"
        ])
        
    except KeyboardInterrupt:
        print("\n👋 애플리케이션을 종료합니다.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
