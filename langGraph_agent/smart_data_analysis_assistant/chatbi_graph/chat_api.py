"""
ChatBI API 服务入口。

启动时会构建一次 LangGraph 图，请求处理阶段复用该图，避免每次请求重复加载 MCP 工具。
"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field


script_dir = Path(__file__).resolve().parent
project_dir = script_dir.parent.parent
sys.path.append(str(project_dir))
sys.path.append(str(script_dir))

from build_graph import make_graph  # noqa: E402


class UserInput(BaseModel):
    """ChatBI 对话接口请求体。"""

    user_id: str
    message: str
    history: list[dict[str, Any]] = Field(default_factory=list)


def build_app() -> FastAPI:
    """创建 FastAPI 应用并注册生命周期、路由和中间件。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """服务启动时创建 LangGraph，服务关闭时释放图上下文。"""
        async with make_graph() as graph:
            app.state.graph = graph
            print("ChatBI LangGraph 创建完成")
            yield
            print("ChatBI LangGraph 已释放")

    app = FastAPI(title="MCP LangGraph ChatBI", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """健康检查接口，用于确认 API 服务已经启动。"""
        return {"status": "ok"}

    @app.post("/chatbi_service")
    async def chatbi_server(user_input: UserInput) -> dict[str, str]:
        """处理 ChatBI 对话请求，并返回最终 AI 回复。"""
        graph = getattr(app.state, "graph", None)
        if graph is None:
            raise HTTPException(status_code=503, detail="ChatBI graph is not ready")

        history = list(user_input.history)
        history.append({"role": "user", "content": user_input.message})
        print(f"用户Id:{user_input.user_id}, 本轮输入:{user_input.message}")

        final_answer = ""
        async for event in graph.astream({"messages": history}, stream_mode="values"):
            message = event["messages"][-1]
            if hasattr(message, "pretty_print"):
                message.pretty_print()

            if isinstance(message, AIMessage) and message.content and not message.tool_calls:
                final_answer = str(message.content)

        if not final_answer:
            raise HTTPException(status_code=500, detail="ChatBI did not return a final answer")

        print("本轮回复:", final_answer)
        return {"message": final_answer}

    return app


app = build_app()


if __name__ == "__main__":
    """本地调试入口。"""
    import uvicorn

    host = os.getenv("CHATBI_API_HOST", "0.0.0.0")
    port = int(os.getenv("CHATBI_API_PORT", "9008"))
    uvicorn.run(app, host=host, port=port)
