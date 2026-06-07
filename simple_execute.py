from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

# 获取LLM
llm = ChatOpenAI(
    model_name="qwen-plus-latest",
    temperature=0.0,
    openai_api_key=os.getenv("QWEN_API_KEY"),
    openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 系统提示
system_prompt = """
你是一个数据分析助手，能够回答用户的问题。

已知信息：
1. 用户王一珂的在线平均时长为18分钟
2. 商品洗碗布的月销量数据：1月5，2月6，3月10，4月8，5月3，6月8，7月5，8月6，9月12，10月8，11月15，12月20
3. 银耳的用户评论和星级数据：有50条评论，大部分是5星好评，也有一些1-2星的差评
4. 健身手套的价格是69元
5. 运动类商品数量是301个

请根据这些信息回答用户的问题。
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
            result = llm.invoke(messages)
            print(f"助手: {result.content}")
            messages.append({"role": "assistant", "content": result.content})
            
        except Exception as e:
            print(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
