# ChatBI API 启动说明

## 1. 配置环境变量

复制 `.env.example` 为 `.env`，填写模型和数据库配置。

```powershell
Copy-Item .env.example .env
```

关键配置：

```env
QWEN_API_KEY=
db_host=localhost
db_user=root
password=
dbname=seles_chat
server_url=localhost
CHATBI_API_PORT=9008
```

## 2. 分别启动服务

启动数据库 MCP：

```powershell
.venv\Scripts\python.exe langGraph_agent\smart_data_analysis_assistant\mcp_server\statistic_db_mcp_tools.py
```

启动图表 MCP：

```powershell
.venv\Scripts\python.exe langGraph_agent\smart_data_analysis_assistant\mcp_server\python_chart_mcp.py
```

启动 ChatBI API：

```powershell
.venv\Scripts\python.exe -m uvicorn langGraph_agent.smart_data_analysis_assistant.chatbi_graph.chat_api:app --host 0.0.0.0 --port 9008
```

## 3. 一键开发启动

Windows PowerShell：

```powershell
.\scripts\start_dev.ps1
```

该脚本会在后台启动数据库 MCP 和图表 MCP，然后以前台方式启动 ChatBI API。

## 4. 健康检查

```powershell
Invoke-RestMethod http://localhost:9008/health
```

期望返回：

```json
{"status":"ok"}
```

## 5. 调用示例

```powershell
Invoke-RestMethod `
  -Uri http://localhost:9008/chatbi_service `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"user_id":"demo","message":"运动类商品有多少","history":[]}'
```

## 6. 设计说明

`chat_api.py` 使用 FastAPI lifespan 在服务启动时构建一次 LangGraph：

```text
API 启动 -> make_graph() -> 请求复用 app.state.graph -> API 关闭释放上下文
```

这样可以避免每个请求都重新加载 MCP tools，提升请求稳定性和响应速度。
