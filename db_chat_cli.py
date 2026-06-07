from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
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

# 获取数据库表结构信息
table_names = db.get_usable_table_names()
table_info = ""
for table_name in table_names:
    table_info += f"表名: {table_name}\n"
    table_info += db.get_table_info([table_name])
    table_info += "\n\n"

# 系统提示
system_prompt = f"""
你是一个数据分析助手，能够查询数据库并回答用户的问题。

数据库表结构信息：
{table_info}

注意：
- user_online_record表中的字段名是username，不是user_name
- user_online_record表中的字段名是online_time，不是online_duration
- 确保SQL查询语法正确，特别是字段名和表名的拼写
- 对于用户的问题，生成正确的SQL查询并执行，然后根据查询结果回答用户的问题
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
            # 调用LLM生成SQL查询
            result = llm.invoke(messages)
            
            # 提取SQL查询
            sql_query = None
            if "```sql" in result.content and "```" in result.content:
                sql_query = result.content.split("```sql")[1].split("```")[0].strip()
            elif "SQL查询:" in result.content:
                sql_query = result.content.split("SQL查询:")[1].strip()
            
            if sql_query:
                print(f"生成的SQL查询:")
                print(sql_query)
                
                # 执行SQL查询
                try:
                    query_result = db.run(sql_query)
                    print(f"查询结果:")
                    print(query_result)
                    
                    # 生成最终回答
                    messages.append({"role": "assistant", "content": result.content})
                    messages.append({"role": "user", "content": f"SQL查询结果: {query_result}\n请根据查询结果回答我的问题: {user_input}"})
                    final_result = llm.invoke(messages)
                    print(f"助手: {final_result.content}")
                    messages.append({"role": "assistant", "content": final_result.content})
                except Exception as e:
                    print(f"执行SQL查询失败: {str(e)}")
                    messages.append({"role": "assistant", "content": f"执行SQL查询失败: {str(e)}"})
                    print(f"助手: 执行SQL查询失败: {str(e)}")
            else:
                print(f"助手: {result.content}")
                messages.append({"role": "assistant", "content": result.content})
                
        except Exception as e:
            print(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
