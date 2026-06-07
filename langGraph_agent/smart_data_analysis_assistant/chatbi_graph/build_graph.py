import sys
import os
import json
import re
import uuid
from pathlib import Path
# 获取当前脚本所在目录
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, ".."))
sys.path.append(script_dir)
from contextlib import asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from my_llm import llm
from my_state import BIState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from dotenv import load_dotenv
# 加载环境变量
for env_path in [
    Path(script_dir).parents[2] / ".env",
    Path(script_dir) / ".env",
]:
    load_dotenv(env_path)
#加载MCP服务器址的地：本地服务器
server_url=os.getenv("server_url", "localhost")
MAX_SQL_REPAIR_ATTEMPTS = int(os.getenv("MAX_SQL_REPAIR_ATTEMPTS", "1"))
#数据库查询MCP
mcp_server_config = {
    "search_db_mcp":{
    "url": f"http://{server_url}:9004/sse",
    "transport": "sse",
    "timeout": 30000,  # 增加超时时间
    "sse_read_timeout": 30000
    },
    # #机器学习MCP
    # "machine_learning_mcp":{
    # "url": f"http://{server_url}:9003/mcp",
    # "transport": "streamable_http",
    # "timeout": 20000,  # 机器学习时间需要久一些
    # "sse_read_timeout": 20000
    # },
    #生成python代码，执行python程序的MCP
    "python_chart_mcp":{
    "url": f"http://{server_url}:9002/sse",
    "transport": "sse",
    "timeout": 30000,  # 增加超时时间
    "sse_read_timeout": 30000
    },
    # #业务分流MCP
    # "ywfl_mcp":{
    # "url": f"http://{server_url}:9005/mcp",
    # "transport": "streamable_http",
    # "timeout": 20000.0,  # 机器学习时间需要久一些
    # "sse_read_timeout": 20000.0
    # },
}

CHATBI_SYSTEM_PROMPT = """
你是一个企业级 ChatBI 数据分析助手，可以进行普通聊天，也可以通过 MCP 工具查询数据库和生成图表。

处理数据库问题时必须遵守：
1. 如果本轮对话中还没有数据库表结构信息，必须先调用 list_tables_tool 获取表名、字段和样例数据。
2. 根据真实表结构生成 MySQL SQL，只能调用 db_sql_tool 执行只读 SELECT 查询。
3. 不允许生成或执行 INSERT、UPDATE、DELETE、DROP、TRUNCATE、ALTER 等写入或破坏性 SQL。
4. 不要臆造表名和字段名。字段不确定时先调用 list_tables_tool。
5. 查询时只选择回答问题需要的字段，除非用户明确要求明细，否则聚合类问题优先使用 COUNT、SUM、AVG、GROUP BY 等 SQL 计算。
6. db_sql_tool 返回错误时，结合错误信息和表结构修正 SQL，最多重试一次。
7. db_sql_tool 返回结果后，必须用中文给出最终业务回答；不要只输出 SQL 或原始工具结果。
8. 如果用户要求图表，先查询数据，再调用 run_python_script_tool 绘图，并在最终回答中给出图片路径。

普通闲聊或代码问题不需要调用数据库工具，直接回答。
""".strip()

SQL_REPAIR_SYSTEM_PROMPT = """
你是一个 MySQL Text2SQL 修复专家。
你的任务是根据用户原问题、历史表结构、失败 SQL 和错误信息，生成修复后的只读 SQL，并调用 db_sql_tool 重新执行。

规则：
1. 只能调用 db_sql_tool，不要直接输出自然语言答案。
2. 只能生成 SELECT/WITH/DESCRIBE/DESC/EXPLAIN 等只读查询。
3. 不要生成 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE 等写入或DDL语句。
4. 不要使用 Markdown 代码块。
5. 优先修复表名、字段名、别名、聚合、条件、类型转换等问题。
6. 如果错误来自表名或字段名不存在，必须根据已有 schema 选择真实表名和字段名。
""".strip()


def _with_system_prompt(messages):
    """确保每次模型调用都有 ChatBI 系统提示。"""
    if any(isinstance(message, SystemMessage) for message in messages):
        return messages
    return [SystemMessage(content=CHATBI_SYSTEM_PROMPT), *messages]


def _message_text(message) -> str:
    """将不同消息内容统一转换为可检索的文本。"""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                text_parts.append(str(item.get("text") or item.get("content") or item))
            else:
                text_parts.append(str(item))
        return "\n".join(text_parts)
    return str(content)


def _tool_call_name(tool_call: dict) -> str:
    """兼容不同工具调用结构，提取工具名称。"""
    return tool_call.get("name") or tool_call.get("function", {}).get("name", "")


def _tool_call_args(tool_call: dict) -> dict:
    """兼容不同工具调用结构，提取工具参数。"""
    args = tool_call.get("args")
    if isinstance(args, dict):
        return args
    raw_args = tool_call.get("function", {}).get("arguments")
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return {"raw": raw_args}
    return {}


def _latest_tool_call_name(messages, tool_message: ToolMessage) -> str:
    """根据 ToolMessage 的 tool_call_id 反查对应工具名称。"""
    tool_call_id = getattr(tool_message, "tool_call_id", None)
    for message in reversed(messages):
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            continue
        for tool_call in tool_calls:
            if tool_call.get("id") == tool_call_id:
                return _tool_call_name(tool_call)
    return getattr(tool_message, "name", "") or ""


def _latest_db_sql_query(messages) -> str:
    """从历史消息中提取最近一次 db_sql_tool 调用的 SQL。"""
    for message in reversed(messages):
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            continue
        for tool_call in reversed(tool_calls):
            if _tool_call_name(tool_call) == "db_sql_tool":
                args = _tool_call_args(tool_call)
                query = args.get("query")
                if query:
                    return str(query)
    return ""


def _is_db_sql_error_tool_message(messages) -> bool:
    """判断最后一条工具消息是否为 db_sql_tool 返回的错误。"""
    if not messages:
        return False
    last_message = messages[-1]
    if not isinstance(last_message, ToolMessage):
        return False
    if _latest_tool_call_name(messages, last_message) != "db_sql_tool":
        return False
    content_text = _message_text(last_message)
    return "错误:" in content_text or "error" in content_text.lower()


def _strip_sql_code_fence(text: str) -> str:
    """去掉模型可能返回的 SQL Markdown 代码块。"""
    text = text.strip()
    fenced_match = re.fullmatch(r"```(?:sql)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()
    return text


def _extract_sql_from_text(text: str) -> str:
    """从修复模型的普通文本输出中提取 SQL。"""
    text = _strip_sql_code_fence(text)
    sql_match = re.search(r"\b(select|with|describe|desc|explain)\b[\s\S]*", text, flags=re.IGNORECASE)
    if not sql_match:
        return ""
    sql = sql_match.group(0).strip()
    return sql.rstrip(";").strip()


def _ensure_db_sql_tool_call(message: AIMessage) -> AIMessage:
    """确保修复节点输出的是 db_sql_tool 工具调用。"""
    if message.tool_calls:
        return message

    sql = _extract_sql_from_text(_message_text(message))
    if not sql:
        return message

    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "db_sql_tool",
                "args": {"query": sql},
                "id": f"repair_{uuid.uuid4().hex}",
                "type": "tool_call",
            }
        ],
    )


def should_continue(state: BIState):
    """LLM 有工具调用就执行工具，否则结束。"""
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None)
    if tool_calls:
        print("检测到工具调用:", tool_calls)
        return "all_tool_node"
    return END


def should_repair_or_continue(state: BIState):
    """工具执行后判断是否进入 SQL 自动修复节点。"""
    repair_count = state.get("sql_repair_count", 0)
    if _is_db_sql_error_tool_message(state["messages"]) and repair_count < MAX_SQL_REPAIR_ATTEMPTS:
        print(f"SQL执行失败，进入自动修复流程，当前修复次数: {repair_count}")
        return "repair_sql_query"
    return "call_python_coder"



#%%
@asynccontextmanager  # 作用：用于快速创建异步上下文管理器。它使得异步资源的获取和释放可以像同步代码一样通过 async with 语法优雅地管理。
async def make_graph():
    """定义，并且编译工作流"""
    tools=[] #所有工具

    client = MultiServerMCPClient(mcp_server_config) #接收一个MCP服务器组对象
    print(client)

    # 使用 get_tools：工具在每次调用时按需新建 MCP 会话；勿在短生命周期 session 内 load_mcp_tools 后复用，否则会 ClosedResourceError
    for server_name in mcp_server_config:
        try:
            server_tools = await client.get_tools(server_name=server_name)
            tools.extend(server_tools)
            print(f"成功加载 {server_name} 工具")
        except Exception as e:
            print(f"无法加载 {server_name} 工具: {str(e)}")

    print("所有tools列表:",tools)
        
    # 解析tool获取工具变量
    run_python_script_tool = None
    list_tables_tool = None
    db_sql_tool = None
    
    for one_tool in tools:
        print("one_tool:",one_tool)
        if one_tool.name == "run_python_script_tool":
            run_python_script_tool=one_tool
        elif one_tool.name == "list_tables_tool":
            list_tables_tool=one_tool
        elif one_tool.name == "db_sql_tool":
            db_sql_tool=one_tool
        else:
            print(f"遇到了其它tools:{one_tool.name}")
    
    # 如果没有加载到任何工具，使用默认聊天图
    if not tools:
        print("没有加载到任何工具，使用默认配置")
        def call_python_coder(state: BIState):
            """直接调用LLM"""
            result = llm.invoke(_with_system_prompt(state["messages"]))
            print("直接调用LLM结果:",result)
            return {'messages': [result]}
        
        workflow = StateGraph(BIState)
        workflow.add_node(call_python_coder)
        workflow.add_edge(START, "call_python_coder")
        workflow.add_edge("call_python_coder", END)
    else:
        # 至少加载到了一个工具，采用 ReAct 循环：LLM -> ToolNode -> LLM -> ... -> END
        all_tools = []
        if run_python_script_tool:
            all_tools.append(run_python_script_tool)
        if list_tables_tool:
            all_tools.append(list_tables_tool)
        if db_sql_tool:
            all_tools.append(db_sql_tool)

        print(f"已绑定工具: {[tool.name for tool in all_tools]}")
        llm_with_tools = llm.bind_tools(all_tools)

        def call_python_coder(state: BIState):
            """让模型决定直接回答还是调用 MCP 工具。"""
            python_coder_result = llm_with_tools.invoke(_with_system_prompt(state["messages"]))
            print("LLM 节点结果:",python_coder_result)
            return {'messages': [python_coder_result]}

        def repair_sql_query(state: BIState):
            """根据最近一次SQL错误生成修复后的db_sql_tool调用。"""
            repair_count = state.get("sql_repair_count", 0)
            failed_sql = _latest_db_sql_query(state["messages"])
            error_message = _message_text(state["messages"][-1])
            repair_messages = [
                SystemMessage(content=SQL_REPAIR_SYSTEM_PROMPT),
                *[message for message in state["messages"] if not isinstance(message, SystemMessage)],
                HumanMessage(
                    content=(
                        "上一次 SQL 执行失败，请结合历史表结构和错误信息修复 SQL，并调用 db_sql_tool 重新执行。\n"
                        f"失败 SQL:\n{failed_sql}\n\n"
                        f"错误信息:\n{error_message}\n\n"
                        f"这是第 {repair_count + 1} 次修复，最多允许 {MAX_SQL_REPAIR_ATTEMPTS} 次。"
                    )
                ),
            ]
            sql_repair_llm = llm.bind_tools([db_sql_tool], tool_choice="db_sql_tool")
            repair_result = sql_repair_llm.invoke(repair_messages)
            repair_result = _ensure_db_sql_tool_call(repair_result)
            print("SQL修复节点结果:", repair_result)
            return {
                "messages": [repair_result],
                "sql_repair_count": repair_count + 1,
            }

        all_tool_node = ToolNode(all_tools, name="all_tool_node")

        workflow = StateGraph(BIState)
        workflow.add_node(call_python_coder)
        workflow.add_node(all_tool_node)
        workflow.add_node(repair_sql_query)
        workflow.add_edge(START, "call_python_coder")
        workflow.add_conditional_edges(
            "call_python_coder",
            should_continue,
            {
                "all_tool_node": "all_tool_node",
                END: END,
            },
        )
        workflow.add_conditional_edges(
            "all_tool_node",
            should_repair_or_continue,
            {
                "repair_sql_query": "repair_sql_query",
                "call_python_coder": "call_python_coder",
            },
        )
        workflow.add_edge("repair_sql_query", "all_tool_node")
    
    #构建带有MemorySaver的图结构
    # memory=MemorySaver()
    print("正在创建LangGraph图....")
    try:
        graph = workflow.compile() # checkpointer=memory
    except Exception as e:
        print("创建图出现错误:",e)
        import traceback
        traceback.print_exc()
        # 如果创建图失败，返回一个简单的图
        def simple_node(state: BIState):
            """图编译失败时使用的兜底LLM节点。"""
            result = llm.invoke(_with_system_prompt(state["messages"]))
            return {'messages': [result]}
        
        workflow = StateGraph(BIState)
        workflow.add_node(simple_node)
        workflow.add_edge(START, "simple_node")
        workflow.add_edge("simple_node", END)
        graph = workflow.compile()
    
    #绘制langGraph流程图并保存到本地
    try:
        graph_png = graph.get_graph().draw_mermaid_png()
        print(f"Graph PNG generated, size: {len(graph_png)} bytes")
        
        # 保存到当前目录
        current_dir = os.getcwd()
        print(f"Current directory: {current_dir}")
        
        # 保存到chatbi_graph目录
        chatbi_graph_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"Chatbi graph directory: {chatbi_graph_dir}")
        
        # 保存到两个位置，确保至少有一个成功
        with open("./build_graph.png", "wb") as f:
            f.write(graph_png)
        print("Saved build_graph.png to current directory")
        
        with open(os.path.join(chatbi_graph_dir, "build_graph.png"), "wb") as f:
            f.write(graph_png)
        print("Saved build_graph.png to chatbi_graph directory")
        
    except Exception as e:
        print(f"Error generating or saving graph: {str(e)}")
        import traceback
        traceback.print_exc()

    yield graph

# 调用make_graph函数生成build_graph.png
if __name__ == "__main__":
    import asyncio
    async def main():
        """本地调试入口：创建并编译图。"""
        async with make_graph() as graph:
            print("Graph created successfully!")
    asyncio.run(main())
