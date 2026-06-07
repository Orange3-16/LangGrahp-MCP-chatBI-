$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "未找到虚拟环境 Python: $Python"
}

Write-Host "启动数据库 MCP 服务..."
$DbMcp = Start-Process -FilePath $Python `
    -ArgumentList "langGraph_agent\smart_data_analysis_assistant\mcp_server\statistic_db_mcp_tools.py" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -PassThru

Write-Host "启动图表 MCP 服务..."
$ChartMcp = Start-Process -FilePath $Python `
    -ArgumentList "langGraph_agent\smart_data_analysis_assistant\mcp_server\python_chart_mcp.py" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -PassThru

Write-Host "数据库 MCP PID: $($DbMcp.Id)"
Write-Host "图表 MCP PID: $($ChartMcp.Id)"
Write-Host "启动 ChatBI API，停止 API 后请手动结束 MCP 进程。"

& $Python -m uvicorn `
    langGraph_agent.smart_data_analysis_assistant.chatbi_graph.chat_api:app `
    --host 0.0.0.0 `
    --port 9008
