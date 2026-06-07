#%%
from langchain_openai import ChatOpenAI
from pathlib import Path
from dotenv import load_dotenv
import os
# 获取当前脚本所在目录
script_dir = Path(__file__).resolve().parent
# 加载根目录和当前目录下的 .env，兼容不同入口脚本启动方式
for env_path in [
    script_dir.parents[2] / ".env",
    script_dir / ".env",
]:
    load_dotenv(env_path)


#DEEPSEEK llm
llm = ChatOpenAI(
    temperature=0,
    model='deepseek-chat',
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com")

# 通义千问LLM
llm = ChatOpenAI(
    temperature=0,
    model="qwen-plus-latest", #qwen-plus
    openai_api_key=os.getenv("QWEN_API_KEY"),
    openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    model_kwargs={"parallel_tool_calls": False}
)
# ,"parallel_tool_calls":True
