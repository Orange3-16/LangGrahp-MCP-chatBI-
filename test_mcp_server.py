"""
测试MCP服务器启动
"""
import sys
import os
from dotenv import load_dotenv

# 加载环境变量
try:
    load_dotenv()
    print("加载环境变量成功")
except Exception as e:
    print(f"加载环境变量失败: {str(e)}")
    sys.exit(1)

# 测试导入MCP
try:
    from mcp.server import FastMCP
    print("导入FastMCP成功")
except Exception as e:
    print(f"导入FastMCP失败: {str(e)}")
    sys.exit(1)

# 测试数据库连接
try:
    from langchain_community.utilities import SQLDatabase
    print("导入SQLDatabase成功")
    
    # 获取环境变量
    db_host = os.getenv("db_host")
    password = os.getenv("password")
    dbname = os.getenv("dbname") or "seles_chat"
    db_port = 3306
    user = os.getenv("db_user") or os.getenv("user")
    
    print(f"数据库连接信息:")
    print(f"  主机: {db_host}")
    print(f"  端口: {db_port}")
    print(f"  用户: {user}")
    print(f"  数据库: {dbname}")
    
    # 尝试连接数据库
    if db_host and user and password and dbname:
        db = SQLDatabase.from_uri(f"mysql+pymysql://{user}:{password}@{db_host}:{db_port}/{dbname}")
        print("数据库连接成功!")
        
        # 测试获取表名
        try:
            table_names = db.get_usable_table_names()
            print(f"数据库中的表: {table_names}")
        except Exception as e:
            print(f"获取表名失败: {str(e)}")
    else:
        print("数据库连接信息不完整，无法连接数据库")
except Exception as e:
    print(f"测试数据库连接失败: {str(e)}")

# 测试创建MCP服务器
try:
    mcp = FastMCP(name='test_mcp', instructions='测试MCP', host="0.0.0.0", port=9005)
    print("创建MCP服务器成功")
except Exception as e:
    print(f"创建MCP服务器失败: {str(e)}")

print("测试完成")
