# Amazon Bedrock Knowledge Base RAG Chatbot

A ReAct (Reasoning and Acting) pattern-based AI chatbot that leverages Amazon Bedrock Knowledge Base for document retrieval and citation generation.

## Features

- **ReAct Agent Pattern**: Implements reasoning and acting cycles for intelligent query processing
- **Knowledge Base Integration**: Seamless integration with Amazon Bedrock Knowledge Base
- **Citation Management**: Accurate citation extraction with proper filename display
- **Multi-modal Support**: Text and image processing capabilities
- **Streamlit UI**: Interactive web interface for chatbot interactions
- **Session Management**: Persistent conversation context across interactions
- **MCP Integration**: Model Context Protocol for standardized tool connectivity

## Architecture

### Core Components

- **ReAct Agent**: Main orchestration agent implementing the ReAct pattern
- **Orchestration Agent**: Query analysis and search strategy planning
- **Action Agent**: Knowledge Base search execution
- **Response Agent**: Final response generation with citation integration
- **Citation System**: Advanced citation processing with filename extraction

### Technology Stack

- **Backend**: Python, FastAPI
- **Frontend**: Streamlit
- **AI Models**: Amazon Bedrock Claude 3.7 Sonnet
- **Vector Store**: OpenSearch Serverless
- **Knowledge Base**: Amazon Bedrock Knowledge Base
- **Session Management**: Custom session handling with cleanup

## Installation

### Prerequisites

- Python 3.8+
- AWS CLI configured with appropriate permissions
- Amazon Bedrock Knowledge Base setup

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure settings:
```bash
cp config/settings.py.example config/settings.py
# Edit config/settings.py with your AWS and Knowledge Base settings
```

## Configuration

### Knowledge Base Settings

Update `config/settings.py` with your Knowledge Base configuration:

```python
class KnowledgeBaseSettings:
    kb_id = "YOUR_KB_ID"
    region = "us-west-2"
    max_results = 10
    search_type = "HYBRID"
```

### Model Settings

Configure your preferred Bedrock models:

```python
class ModelSettings:
    primary_model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    region = "us-west-2"
    temperature = 0.0
```

## Usage

### Streamlit UI

1. Start the Streamlit application:
```bash
streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
```

2. Open your browser and navigate to `http://localhost:8501`

3. Configure your Knowledge Base ID in the sidebar

4. Start asking questions and receive responses with accurate citations

### Programmatic Usage

```python
from src.agents.react_agent import ReActAgent

# Initialize the ReAct agent
agent = ReActAgent()

# Process a query
result = agent.process_query(
    user_query="What are the quality management requirements?",
    kb_id="YOUR_KB_ID"
)

print(result["content"])
print(result["citations"])
```

## Key Features

### Citation System

The citation system has been enhanced to properly extract and display original filenames:

- **Before**: "document_1.pdf", "document_2.pdf"
- **After**: "Construction Quality Management Guidelines (Ministry of Land, Infrastructure and Transport Notice) (No. 2025-311) (20250612).pdf"

### ReAct Pattern Implementation

The system implements a complete ReAct cycle:

1. **Reasoning**: Analyze user query and determine search strategy
2. **Acting**: Execute Knowledge Base searches
3. **Observation**: Process search results and generate citations
4. **Response**: Create final response with integrated citations

### Session Management

- Persistent conversation context
- Automatic session cleanup
- Message history tracking
- Context-aware responses

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/test_phase1_basic.py
pytest tests/test_citation_images.py
pytest tests/test_real_kb_search.py
```

Test citation filename extraction:

```bash
python test_citation_filename_fix.py
```

## Project Structure

```
├── src/
│   ├── agents/          # ReAct agent implementations
│   ├── mcp/            # MCP server and clients
│   └── utils/          # Utility functions and citation processing
├── ui/                 # Streamlit user interface
├── config/             # Configuration files
├── tests/              # Test suites
├── logs/               # Application logs
└── requirements.txt    # Python dependencies
```

## Recent Updates

### Citation Filename Fix

- Fixed citation filename extraction to show actual document names
- Enhanced Citation.from_kb_result() method
- Improved Streamlit UI filename display logic
- Added comprehensive testing for citation processing

### Performance Improvements

- Optimized Knowledge Base search queries
- Enhanced session management
- Improved error handling and logging

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:

1. Check the existing issues in the repository
2. Create a new issue with detailed description
3. Include relevant logs and configuration details

## Acknowledgments

- Amazon Bedrock team for the Knowledge Base service
- Streamlit team for the excellent UI framework
- The ReAct pattern research community
