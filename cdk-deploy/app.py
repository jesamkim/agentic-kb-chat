#!/usr/bin/env python3
"""
Agentic RAG Chatbot CDK App
AWS CDK deployment for the enhanced ReAct-based chatbot
"""

import os
import aws_cdk as cdk
from cdk.agentic_rag_stack import AgenticRagStack
from docker_app.config_file import Config


def main():
    """Main CDK app entry point"""
    app = cdk.App()
    
    # Create the main stack
    AgenticRagStack(
        app, 
        Config.STACK_NAME,
        description="Agentic RAG Chatbot with ReAct pattern and multi-stage search",
        env=cdk.Environment(
            account=os.getenv('CDK_DEFAULT_ACCOUNT'),
            region=os.getenv('CDK_DEFAULT_REGION', 'us-west-2')
        )
    )
    
    app.synth()


if __name__ == "__main__":
    main()
