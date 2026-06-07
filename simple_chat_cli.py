from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

# 获取数据库连接信息
db_host = os.getenv("db_host")
db_user = os.getenv("db_user")
db_password = os.getenv("password")
db_name = os.getenv("dbname")
db_port=3306

# 连接到数据库
db = SQLDatabase.from_uri(f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

# 获取LLM
llm = ChatOpenAI(
    model_name="qwen-plus-latest",
    temperature=0.0,
    openai_api_key=os.getenv("QWEN_API_KEY"),
    openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 定义工具
def list_tables():
    """获取数据库中的所有表及其结构信息"""
    table_names = db.get_usable_table_names()
    result = []
    for table_name in table_names:
        schema = db.get_table_info([table_name])
        result.append(f"表名: {table_name}\n{schema}")
    return "\n\n".join(result)

def run_sql(query):
    """执行SQL查询并返回结果"""
    try:
        result = db.run(query)
        return result
    except Exception as e:
        return f"错误: 执行SQL查询失败: {str(e)}"

# 创建工具
tools = [
    Tool(
        name="list_tables",
        func=list_tables,
        description="获取数据库中的所有表及其结构信息"
    ),
    Tool(
        name="run_sql",
        func=run_sql,
        description="执行SQL查询并返回结果"
    )
]

# 绑定工具
llm_with_tools = llm.bind_tools(tools)

# 系统提示
system_prompt = """
你是一个数据分析助手，能够查询数据库并回答用户的问题。

首先，你应该使用list_tables工具获取数据库中的表结构信息，然后根据表结构生成正确的SQL查询。

注意：
- user_online_record表中的字段名是username，不是user_name
- user_online_record表中的字段名是online_time，不是online_duration
- 确保SQL查询语法正确，特别是字段名和表名的拼写
"""

# 主循环
def main():
    print("ChatBI 数据分析智能助手")
    print("输入 'exit' 退出聊天")
    print("=" * 50)
    
    # 初始化聊天历史
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    while True:
        # 获取用户输入
        user_input = input("你: ")
        
        # 检查是否退出
        if user_input.lower() == 'exit':
            print("再见！")
            break
        
        # 添加用户消息
        messages.append({"role": "user", "content": user_input})
        
        try:
            # 调用LLM
            result = llm_with_tools.invoke(messages)
            
            # 处理工具调用
            if result.tool_calls:
                for tool_call in result.tool_calls:
                    if tool_call['name'] == "list_tables":
                        tool_result = list_tables()
                    elif tool_call['name'] == "run_sql":
                        tool_result = run_sql(tool_call['args']['query'])
                    
                    # 添加工具结果
                    messages.append({"role": "assistant", "content": "", "tool_calls": [tool_call]})
                    messages.append({"role": "tool", "content": tool_result, "name": tool_call['name']})
                
                # 再次调用LLM处理工具结果
                final_result = llm_with_tools.invoke(messages)
                print(f"助手: {final_result.content}")
                messages.append({"role": "assistant", "content": final_result.content})
            else:
                print(f"助手: {result.content}")
                messages.append({"role": "assistant", "content": result.content})
                
        except Exception as e:
            print(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
