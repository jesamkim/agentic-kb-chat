#!/bin/bash

# Agentic RAG Chatbot CDK Deployment Script

set -e

echo "🚀 Starting Agentic RAG Chatbot deployment..."

# Check if required environment variables are set
if [ -z "$KB_ID" ]; then
    echo "❌ Error: KB_ID environment variable is required"
    echo "Please set your Knowledge Base ID:"
    echo "export KB_ID=your_knowledge_base_id"
    exit 1
fi

if [ -z "$AWS_REGION" ]; then
    echo "⚠️  Warning: AWS_REGION not set, using default us-west-2"
    export AWS_REGION=us-west-2
fi

echo "📋 Configuration:"
echo "  - KB_ID: $KB_ID"
echo "  - AWS_REGION: $AWS_REGION"
echo "  - Stack Name: agentic-rag-chatbot"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🔧 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install CDK dependencies
echo "📦 Installing CDK dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check if CDK is installed
if ! command -v cdk &> /dev/null; then
    echo "❌ AWS CDK is not installed. Please install it:"
    echo "npm install -g aws-cdk"
    exit 1
fi

# Bootstrap CDK (if not already done)
echo "🔧 Bootstrapping CDK..."
cdk bootstrap

# Synthesize the stack
echo "🔍 Synthesizing CDK stack..."
cdk synth

# Deploy the stack
echo "🚀 Deploying stack..."
cdk deploy --require-approval never

echo "✅ Deployment completed!"
echo ""
echo "📋 Next steps:"
echo "1. Check the CloudFormation outputs for the CloudFront URL"
echo "2. Wait for the ECS service to be healthy (may take 5-10 minutes)"
echo "3. Access your chatbot via the CloudFront URL"
echo ""
echo "🔍 To check deployment status:"
echo "aws ecs describe-services --cluster agentic-rag-chatbot-cluster --services agentic-rag-chatbot-service"
