# MCP LangGraph ChatBI

这是一个基于 **LangGraph + MCP + FastAPI** 的智能 ChatBI 实验项目，目标是让用户通过自然语言查询业务数据库，并由系统完成表结构获取、Text2SQL、SQL 安全校验、SQL 执行、结果总结和图表生成。

当前版本是第一版工程化整理，重点在 **Text2SQL 链路可运行、SQL 执行更安全、API 启动方式清晰、具备初步评测能力**。

## 当前已实现能力

### 1. LangGraph + MCP 工具调用链路

- 使用 LangGraph 构建 ChatBI Agent 工作流。
- 通过 MCP 加载数据库查询工具和 Python 图表工具。
- 支持循环式工具调用：

```text
LLM -> ToolNode -> LLM -> ToolNode -> ... -> 最终回答
```

- 修复了早期版本中“模型调用 `list_tables_tool` 获取 schema 后直接结束”的问题。

### 2. 数据库 schema 获取与缓存

- `list_tables_tool` 可以返回数据库中的表结构、字段信息和部分样例数据。
- 已增加内存 TTL 缓存，减少重复查询数据库 schema。
- 支持强制刷新 schema：

```python
list_tables_tool(force_refresh=True)
```

相关配置：

```env
SCHEMA_CACHE_TTL_SECONDS=3600
SCHEMA_MAX_RETURN_CHARS=10000
```

### 3. Text2SQL 查询

- 用户输入自然语言问题后，模型会先获取表结构，再生成 SQL。
- SQL 通过 `db_sql_tool` 执行。
- 工具执行结果会回到 LLM，由 LLM 生成中文业务回答。

示例问题：

```text
运动类商品有多少
王一珂的平均在线时长是多少
抽纸过去12个月每个月的销量是多少
查询商品洗碗布的月销量数据，并绘制柱状图
```

### 4. SQL 安全防护

`db_sql_tool` 执行前会进行安全校验：

- 只允许单条 SQL。
- 只允许只读查询类语句：

```text
SELECT, WITH, SHOW, DESCRIBE, DESC, EXPLAIN
```

- 拦截写入、DDL 和高风险关键字。
- 拒绝 SQL 注释，避免注释绕过。
- 自动去除模型可能生成的 Markdown SQL 代码块。
- 对没有 `LIMIT` 的 `SELECT/WITH` 自动补默认限制。

相关配置：

```env
DEFAULT_SQL_LIMIT=200
MAX_SQL_LENGTH=5000
```

### 5. SQL 表名和字段名校验

执行 SQL 前会检查常见 SQL 中的表名和字段名：

- 检查 `FROM/JOIN` 引用的表是否存在。
- 检查 `table.column` 或 `alias.column` 引用的字段是否存在。
- 检查常见单表/多表查询中的未限定字段。
- 支持 `DESCRIBE/DESC` 表名校验。

说明：当前校验是保守实现。复杂 CTE、深层嵌套子查询、聚合别名等场景仍可能交给数据库执行错误兜底。

### 6. SQL 自动修复

当 `db_sql_tool` 返回 SQL 错误时，LangGraph 会进入 SQL 修复节点：

```text
LLM -> db_sql_tool -> SQL错误 -> repair_sql_query -> db_sql_tool -> LLM总结
```

- 默认最多自动修复 1 次。
- 修复节点只绑定 `db_sql_tool`，避免修复过程中调用无关工具。
- 如果模型返回普通 SQL 文本，会尝试转换成 `db_sql_tool` 工具调用。

相关配置：

```env
MAX_SQL_REPAIR_ATTEMPTS=1
```

### 7. 图表生成

- 集成 `python_chart_mcp`。
- 支持模型生成 Python 代码并通过 `run_python_script_tool` 执行。
- 如果生成图表，会返回本地图片路径。

说明：当前图表工具仍是实验性能力，执行 Python 代码的安全隔离还不适合生产环境直接使用。

### 8. FastAPI 服务

API 入口：

```text
langGraph_agent/smart_data_analysis_assistant/chatbi_graph/chat_api.py
```

当前接口：

```text
GET  /health
POST /chatbi_service
```

`chat_api.py` 使用 FastAPI lifespan：

```text
API 启动 -> make_graph() -> 请求复用 app.state.graph -> API 关闭释放上下文
```

这样可以避免每个请求重复构建图和重复加载 MCP tools。

### 9. Text2SQL 评测集

已新增评测目录：

```text
evals/
```

包含：

- `evals/text2sql_cases.jsonl`：当前 12 条评测用例。
- `evals/run_text2sql_eval.py`：评测脚本。
- `evals/README.md`：评测说明。

评测会统计：

- SQL 工具调用率
- 表名命中率
- 字段命中率
- SQL 关键词命中率
- 答案文本命中率
- 图表调用命中率
- 总通过率
- 平均耗时

## 项目结构

```text
.
├── langGraph_agent/
│   ├── langGraph_basic_learning/              # LangGraph 学习和实验代码
│   ├── project_data/                          # 示例 Excel 数据
│   └── smart_data_analysis_assistant/
│       ├── chatbi_graph/                      # ChatBI LangGraph 工作流和 API
│       └── mcp_server/                        # MCP 工具服务
├── evals/                                     # Text2SQL 评测集和评测脚本
├── scripts/                                   # 开发启动脚本
├── .env.example                               # 环境变量示例
├── API_STARTUP.md                             # API 启动说明
├── 修改与待修改.md                            # 当前修改记录和未来计划
└── requirements.txt
```

## 环境准备

建议使用项目自带虚拟环境或自行创建虚拟环境。

安装依赖：

```powershell
pip install -r requirements.txt
```

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

填写 `.env`：

```env
QWEN_API_KEY=
DEEPSEEK_API_KEY=

db_host=localhost
db_user=root
password=
dbname=seles_chat
server_url=localhost
```

说明：

- 当前默认实际使用的是通义千问兼容 OpenAI 接口配置。
- DeepSeek 配置代码保留，但当前 `my_llm.py` 中最终生效的 `llm` 是 Qwen 配置。
- `.env` 不会提交到 Git。

## 启动方式

### 方式一：分别启动

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

### 方式二：开发脚本启动

```powershell
.\scripts\start_dev.ps1
```

该脚本会后台启动数据库 MCP 和图表 MCP，然后前台启动 ChatBI API。

## 接口示例

健康检查：

```powershell
Invoke-RestMethod http://localhost:9008/health
```

ChatBI 查询：

```powershell
Invoke-RestMethod `
  -Uri http://localhost:9008/chatbi_service `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"user_id":"demo","message":"运动类商品有多少","history":[]}'
```

请求体：

```json
{
  "user_id": "demo",
  "message": "运动类商品有多少",
  "history": []
}
```

返回示例：

```json
{
  "message": "运动类商品共有 301 种。"
}
```

## 运行评测

运行前需要启动数据库 MCP、图表 MCP 和可用的大模型配置。

运行全部评测：

```powershell
.venv\Scripts\python.exe evals\run_text2sql_eval.py
```

只运行前 3 条：

```powershell
.venv\Scripts\python.exe evals\run_text2sql_eval.py --limit 3
```

评测报告会输出到：

```text
evals/reports/
```

该目录已加入 `.gitignore`。

## 当前限制

以下能力目前尚未达到生产可用标准：

- 没有完整前端页面。
- 没有 Docker Compose，一键部署能力还不完整。
- 数据库初始化和 Excel 数据导入流程尚未标准化。
- 目前没有用户认证、表级权限、字段级权限和行级权限。
- 没有敏感字段脱敏。
- 没有审计日志和正式日志框架，核心链路仍有大量 `print()`。
- SQL 静态校验覆盖常见查询，但复杂 CTE、深层嵌套子查询仍需增强。
- Python 图表工具会执行模型生成代码，当前仅适合本地实验，不适合生产环境直接开放。
- 评测集目前只有 12 条，还不能充分覆盖真实业务问题。
- 启动脚本不会自动回收后台 MCP 进程，开发时需要手动管理。
- 当前没有 CI、pytest 测试和自动化回归流程。

## 未来修改计划

### P0：稳定性与正确性

- 扩充 Text2SQL 评测集到 20 到 50 条。
- 增加失败原因分类和评测趋势对比。
- 增强复杂 SQL 静态校验，覆盖 CTE、子查询、聚合别名等场景。
- 增加多轮上下文解析，支持“它”“这个商品”“上个月”等指代。
- 标准化数据库初始化和测试数据导入流程。

### P1：企业级能力

- 增加指标口径知识库，例如销量、GMV、活跃用户、复购率。
- 增加表级、字段级、行级权限控制。
- 增加敏感字段脱敏。
- 增加审计日志，记录用户问题、生成 SQL、执行状态、耗时、错误信息。
- 增加慢查询保护、查询超时和结果大小限制。

### P2：数据分析能力

- 自动图表推荐，根据查询结果选择柱状图、折线图、饼图或表格。
- 支持归因分析，例如“为什么下降”“哪个维度贡献最大”。
- 支持 Markdown/PDF 报告生成。
- 支持异步任务，复杂查询或绘图任务不阻塞接口。

### P3：工程化整理

- 增加 Docker Compose。
- 增加标准项目 README、架构图和接口文档。
- 增加 pytest 测试，覆盖 SQL 安全、schema 缓存、SQL 修复、评测脚本。
- 将 MCP server 配置从代码中抽到独立配置文件。
- 引入 logging，替换核心链路中的 `print()`。
- 增加 CI，自动运行语法检查和基础单元测试。

## 安全说明

- 不要提交 `.env`。
- 不要在代码注释中写真实 API Key、数据库密码或 Token。
- 当前仓库已经移除历史中误写的 LangSmith token，并已通过 GitHub Push Protection 检查后上传。

