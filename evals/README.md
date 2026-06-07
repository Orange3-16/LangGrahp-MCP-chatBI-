# Text2SQL 评测集

该目录用于评测 ChatBI 的 Text2SQL 能力。评测脚本会复用现有 LangGraph 工作流，统计模型是否调用了正确工具、是否命中期望表名/字段名/SQL 关键词，以及最终答案是否包含关键内容。

## 文件说明

- `text2sql_cases.jsonl`：评测用例，每行一个 JSON。
- `run_text2sql_eval.py`：评测执行脚本。
- `reports/`：运行后生成的评测报告目录，不需要提交到 Git。

## 用例字段

```json
{
  "id": "count_sports_goods",
  "question": "运动类商品有多少",
  "expected_tables": ["sports_goods_price_list"],
  "expected_columns": [],
  "expected_sql_keywords": ["COUNT"],
  "expected_answer_contains": ["301"],
  "need_chart": false
}
```

字段含义：

- `id`：用例唯一标识。
- `question`：用户问题。
- `expected_tables`：期望 SQL 命中的表名。
- `expected_columns`：期望 SQL 命中的字段名。
- `expected_sql_keywords`：期望 SQL 包含的关键字，例如 `COUNT`、`AVG`、`JOIN`。
- `expected_answer_contains`：最终回答需要包含的文本片段。
- `need_chart`：是否期望调用绘图工具或返回图片路径。

## 运行前准备

先启动 MCP 服务：

```powershell
.venv\Scripts\python.exe langGraph_agent\smart_data_analysis_assistant\mcp_server\statistic_db_mcp_tools.py
.venv\Scripts\python.exe langGraph_agent\smart_data_analysis_assistant\mcp_server\python_chart_mcp.py
```

再运行评测：

```powershell
.venv\Scripts\python.exe evals\run_text2sql_eval.py
```

只跑前 3 条：

```powershell
.venv\Scripts\python.exe evals\run_text2sql_eval.py --limit 3
```

自定义报告目录：

```powershell
.venv\Scripts\python.exe evals\run_text2sql_eval.py --report-dir evals\reports
```

## 输出指标

- SQL 执行工具调用率
- 表名命中率
- 字段命中率
- SQL 关键词命中率
- 答案文本命中率
- 图表调用命中率
- 总通过率
- 平均耗时

评测报告会生成 Markdown 和 JSON 两份文件，便于人工 review 和后续自动化对比。
