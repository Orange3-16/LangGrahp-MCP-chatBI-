"""
测试MCP服务器运行
"""
import sys
import os
import time
from dotenv import load_dotenv
from mcp.server import FastMCP

# 加载环境变量
try:
    load_dotenv()
    print("加载环境变量成功")
except Exception as e:
    print(f"加载环境变量失败: {str(e)}")
    sys.exit(1)

# 创建MCP服务器
try:
    mcp = FastMCP(name='test_mcp', instructions='测试MCP', host="0.0.0.0", port=9005)
    print("创建MCP服务器成功")
except Exception as e:
    print(f"创建MCP服务器失败: {str(e)}")
    sys.exit(1)

# 添加一个简单的工具
@mcp.tool()
def test_tool() -> str:
    """测试工具"""
    return "测试工具响应"

# 测试运行MCP服务器
try:
    print("正在启动MCP服务器...")
    print("服务器地址: http://0.0.0.0:9005")
    # 使用非阻塞方式运行，这样我们可以在几秒钟后停止它
    import threading
    def run_server():
        try:
            mcp.run(transport='sse')
        except Exception as e:
            print(f"运行MCP服务器失败: {str(e)}")
    
    # 在后台线程中运行服务器
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    # 等待几秒钟，然后停止测试
    print("服务器已启动，等待5秒钟...")
    time.sleep(5)
    print("测试完成，服务器将停止")
    
except Exception as e:
    print(f"测试MCP服务器运行失败: {str(e)}")
    import traceback
    traceback.print_exc()

print("测试完成")
