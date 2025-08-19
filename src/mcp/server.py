"""
MCP 서버 구현
Strands Agents와 통합되는 MCP 서버
"""

from typing import Dict, Any, List, Optional
import asyncio
import json
from datetime import datetime

from src.utils.logger import mcp_logger
from src.mcp.kb_client import (
    search_knowledge_base_tool,
    multi_search_knowledge_base_tool,
    kb_client
)
from src.mcp.rerank_client import (
    rerank_search_results_tool,
    combined_search_and_rerank_tool,
    rerank_client
)


class MCPServer:
    """MCP 서버 클래스"""
    
    def __init__(self):
        self.tools = {}
        self.initialized = False
        self._register_tools()
    
    def _register_tools(self):
        """MCP 도구들을 등록"""
        self.tools = {
            # KB 검색 도구들
            'search_knowledge_base': {
                'function': search_knowledge_base_tool,
                'description': 'Search the Knowledge Base with a single query',
                'parameters': {
                    'query': {'type': 'string', 'required': True, 'description': 'Search query'},
                    'max_results': {'type': 'integer', 'required': False, 'description': 'Maximum number of results'},
                    'search_type': {'type': 'string', 'required': False, 'description': 'Search type (HYBRID, SEMANTIC, LEXICAL)'}
                }
            },
            
            'multi_search_knowledge_base': {
                'function': multi_search_knowledge_base_tool,
                'description': 'Search the Knowledge Base with multiple queries (for complex analysis)',
                'parameters': {
                    'queries': {'type': 'array', 'required': True, 'description': 'List of search queries'},
                    'max_results_per_query': {'type': 'integer', 'required': False, 'description': 'Maximum results per query'}
                }
            },
            
            # ReRank 도구들
            'rerank_search_results': {
                'function': rerank_search_results_tool,
                'description': 'Rerank search results using Cohere ReRank model',
                'parameters': {
                    'query': {'type': 'string', 'required': True, 'description': 'Original search query'},
                    'citations_data': {'type': 'array', 'required': True, 'description': 'List of citation data to rerank'},
                    'top_k': {'type': 'integer', 'required': False, 'description': 'Number of top results to return'},
                    'threshold': {'type': 'number', 'required': False, 'description': 'Minimum confidence threshold'}
                }
            },
            
            # 통합 도구 (가장 일반적으로 사용)
            'search_and_rerank': {
                'function': combined_search_and_rerank_tool,
                'description': 'Combined KB search and rerank in one operation (recommended)',
                'parameters': {
                    'query': {'type': 'string', 'required': True, 'description': 'Search query'},
                    'max_results': {'type': 'integer', 'required': False, 'description': 'Maximum search results'},
                    'rerank_top_k': {'type': 'integer', 'required': False, 'description': 'Top K results after reranking'},
                    'threshold': {'type': 'number', 'required': False, 'description': 'Minimum confidence threshold'}
                }
            },
            
            # 시스템 도구들
            'health_check': {
                'function': self._health_check_tool,
                'description': 'Check the health status of MCP server and connected services',
                'parameters': {}
            },
            
            'get_server_info': {
                'function': self._get_server_info_tool,
                'description': 'Get information about the MCP server and its capabilities',
                'parameters': {}
            }
        }
        
        mcp_logger.log_mcp_call(
            "tools_registered", 
            {"tool_count": len(self.tools)}, 
            f"Registered {len(self.tools)} tools"
        )
    
    def get_available_tools(self) -> Dict[str, Any]:
        """사용 가능한 도구 목록 반환"""
        tools_info = {}
        
        for tool_name, tool_config in self.tools.items():
            tools_info[tool_name] = {
                'description': tool_config['description'],
                'parameters': tool_config['parameters']
            }
        
        return tools_info
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """도구 호출"""
        if tool_name not in self.tools:
            error_msg = f"Tool '{tool_name}' not found"
            mcp_logger.log_error(Exception(error_msg), "call_tool")
            return {
                'status': 'error',
                'error': error_msg,
                'available_tools': list(self.tools.keys())
            }
        
        try:
            tool_config = self.tools[tool_name]
            tool_function = tool_config['function']
            
            mcp_logger.log_mcp_call(
                tool_name,
                parameters,
                "started"
            )
            
            # 동기 함수를 비동기로 실행
            if asyncio.iscoroutinefunction(tool_function):
                result = await tool_function(**parameters)
            else:
                result = tool_function(**parameters)
            
            mcp_logger.log_mcp_call(
                tool_name,
                parameters,
                f"completed - status: {result.get('status', 'unknown')}"
            )
            
            return result
            
        except TypeError as e:
            error_msg = f"Invalid parameters for tool '{tool_name}': {e}"
            mcp_logger.log_error(Exception(error_msg), "call_tool")
            return {
                'status': 'error',
                'tool': tool_name,
                'error': error_msg,
                'expected_parameters': tool_config['parameters']
            }
            
        except Exception as e:
            mcp_logger.log_error(e, f"call_tool_{tool_name}")
            return {
                'status': 'error',
                'tool': tool_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _health_check_tool(self) -> Dict[str, Any]:
        """시스템 상태 확인 도구"""
        try:
            from config.settings import settings
            
            # KB 클라이언트 상태 확인
            kb_health = kb_client.health_check()
            
            # ReRank 클라이언트 상태 확인 (활성화된 경우에만)
            if settings.knowledge_base.enable_rerank:
                rerank_health = rerank_client.health_check()
            else:
                rerank_health = {
                    'status': 'disabled',
                    'message': 'ReRank functionality is disabled in settings'
                }
            
            # 전체 상태 결정
            overall_status = 'healthy'
            if kb_health['status'] != 'healthy':
                overall_status = 'degraded'
            elif settings.knowledge_base.enable_rerank and rerank_health['status'] != 'healthy':
                overall_status = 'degraded'
            
            return {
                'status': overall_status,
                'timestamp': datetime.now().isoformat(),
                'components': {
                    'knowledge_base': kb_health,
                    'rerank_service': rerank_health,
                    'mcp_server': {
                        'status': 'healthy',
                        'tools_count': len(self.tools),
                        'initialized': self.initialized
                    }
                },
                'configuration': {
                    'rerank_enabled': settings.knowledge_base.enable_rerank
                }
            }
            
        except Exception as e:
            mcp_logger.log_error(e, "health_check_tool")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _get_server_info_tool(self) -> Dict[str, Any]:
        """서버 정보 반환 도구"""
        try:
            from config.settings import settings
            
            # KB 정보 조회
            kb_info = kb_client.get_kb_info()
            
            return {
                'status': 'success',
                'server_info': {
                    'name': 'MCP RAG Server',
                    'version': '1.0.0',
                    'description': 'MCP server for RAG operations with Bedrock KB and Cohere ReRank',
                    'tools_count': len(self.tools),
                    'available_tools': list(self.tools.keys())
                },
                'configuration': {
                    'knowledge_base': {
                        'kb_id': settings.knowledge_base.kb_id,
                        'region': settings.knowledge_base.region,
                        'search_type': settings.knowledge_base.search_type,
                        'max_results': settings.knowledge_base.max_results
                    },
                    'rerank': {
                        'model_id': settings.model.rerank_model_id,
                        'top_k': settings.model.rerank_top_k,
                        'threshold': settings.knowledge_base.rerank_threshold
                    },
                    'citation': {
                        'max_citations': settings.citation.max_citations_per_response,
                        'min_confidence': settings.citation.min_confidence_score
                    }
                },
                'knowledge_base_info': kb_info,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            mcp_logger.log_error(e, "get_server_info_tool")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def initialize(self) -> bool:
        """서버 초기화"""
        try:
            from config.settings import settings
            
            # KB 클라이언트 상태 확인
            kb_health = kb_client.health_check()
            if kb_health['status'] != 'healthy':
                mcp_logger.log_error(
                    Exception(f"KB client unhealthy: {kb_health.get('error', 'Unknown error')}"),
                    "server_initialization"
                )
                return False
            
            # ReRank 클라이언트 상태 확인 (ReRank가 활성화된 경우에만)
            if settings.knowledge_base.enable_rerank:
                rerank_health = rerank_client.health_check()
                if rerank_health['status'] != 'healthy':
                    mcp_logger.log_error(
                        Exception(f"ReRank client unhealthy: {rerank_health.get('error', 'Unknown error')}"),
                        "server_initialization"
                    )
                    return False
            else:
                mcp_logger.log_mcp_call(
                    "rerank_disabled",
                    {"enable_rerank": False},
                    "ReRank functionality disabled in settings"
                )
            
            self.initialized = True
            mcp_logger.log_mcp_call(
                "server_initialized",
                {"tools": len(self.tools), "rerank_enabled": settings.knowledge_base.enable_rerank},
                "MCP server ready"
            )
            
            return True
            
        except Exception as e:
            mcp_logger.log_error(e, "server_initialization")
            return False


# 전역 MCP 서버 인스턴스
mcp_server = MCPServer()


# Strands Agents와의 통합을 위한 래퍼 함수들
def get_mcp_tools() -> Dict[str, Any]:
    """Strands Agents에서 사용할 도구 목록 반환"""
    return mcp_server.get_available_tools()


async def execute_mcp_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Strands Agents에서 MCP 도구 실행"""
    return await mcp_server.call_tool(tool_name, kwargs)


# 동기 버전 (필요한 경우)
def execute_mcp_tool_sync(tool_name: str, **kwargs) -> Dict[str, Any]:
    """동기 방식으로 MCP 도구 실행"""
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(mcp_server.call_tool(tool_name, kwargs))
    except RuntimeError:
        # 이벤트 루프가 없는 경우 새로 생성
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(mcp_server.call_tool(tool_name, kwargs))
        finally:
            loop.close()


# 서버 초기화
if not mcp_server.initialize():
    mcp_logger.log_error(
        Exception("Failed to initialize MCP server"),
        "module_import"
    )
