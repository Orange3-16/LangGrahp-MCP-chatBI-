"""
简化版数据库查询MCP服务
"""
from mcp.server import FastMCP

# 创建MCP服务
mcp = FastMCP(name='simple_db_mcp', instructions='简化版数据库查询MCP', host="0.0.0.0", port=9006)

@mcp.tool()
async def list_tables_tool() -> str:
    """
    输入是个空字符串, 返回数据库中的所有表及其结构信息
    :return: 数据库中的所有表及其结构信息的格式化字符串
    """
    return "数据库连接失败: 数据库 'sales_chat' 不存在"

@mcp.tool()
def db_sql_tool(query: str) -> str:
    """
    执行SQL查询并返回结果
    :param query: 非空的要执行的SQL查询语句
    :return:str: 查询结果或错误信息
    """
    return "数据库连接失败: 数据库 'sales_chat' 不存在"

if __name__ == "__main__":
    # 以标准 sse方式运行 MCP 服务器
    print("启动简化版数据库查询MCP服务...")
    mcp.run(transport='sse')
