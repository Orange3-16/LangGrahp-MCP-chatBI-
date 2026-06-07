from mcp.server import FastMCP

mcp = FastMCP(name='test_mcp', instructions='Test MCP server', host="0.0.0.0", port=9002)

@mcp.tool()
async def test_tool(message: str) -> str:
    """Test tool"""
    return f"Hello, {message}!"

if __name__ == "__main__":
    mcp.run(transport='streamable-http')