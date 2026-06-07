import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 加载MCP服务器地址
test_server_url = os.getenv("server_url", "localhost")

# 数据库查询MCP测试配置
mcp_server_config = {
    "search_db_mcp":{
        "url": f"http://{test_server_url}:9004/sse",
        "transport": "sse",
        "timeout": 30000,
        "sse_read_timeout": 30000
    },
    "python_chart_mcp":{
        "url": f"http://{test_server_url}:9002/sse",
        "transport": "sse",
        "timeout": 30000,
        "sse_read_timeout": 30000
    },
}

async def test_mcp_connections():
    """测试MCP服务连接"""
    try:
        print("正在创建MCP客户端...")
        client = MultiServerMCPClient(mcp_server_config)
        print("MCP客户端创建成功")
        
        # 测试数据库查询MCP
        print("\n测试数据库查询MCP...")
        try:
            async with client.session("search_db_mcp") as search_db_session:
                print("成功创建search_db_mcp会话")
                search_db_server_tools = await load_mcp_tools(search_db_session)
                print(f"成功加载数据库查询工具: {[tool.name for tool in search_db_server_tools]}")
        except Exception as e:
            print(f"数据库查询MCP测试失败: {str(e)}")
        
        # 测试Python绘图MCP
        print("\n测试Python绘图MCP...")
        try:
            async with client.session("python_chart_mcp") as python_chart_session:
                print("成功创建python_chart_mcp会话")
                python_chart_server_tools = await load_mcp_tools(python_chart_session)
                print(f"成功加载Python绘图工具: {[tool.name for tool in python_chart_server_tools]}")
        except Exception as e:
            print(f"Python绘图MCP测试失败: {str(e)}")
        
        print("\nMCP服务连接测试完成")
    except Exception as e:
        print(f"测试过程中出现错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_mcp_connections())
