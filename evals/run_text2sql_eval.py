import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHATBI_GRAPH_DIR = PROJECT_ROOT / "langGraph_agent" / "smart_data_analysis_assistant" / "chatbi_graph"
DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "text2sql_cases.jsonl"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent / "reports"

sys.path.append(str(CHATBI_GRAPH_DIR))

from build_graph import make_graph  # noqa: E402


def load_cases(cases_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """从 JSONL 文件读取评测用例，可通过 limit 限制读取数量。"""
    cases = []
    with cases_path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {cases_path}:{line_no}: {exc}") from exc
            if limit and len(cases) >= limit:
                break
    return cases


def normalize_text(value: Any) -> str:
    """将模型输出、工具结果等任意值统一转换为字符串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def contains_all(text: str, expected_items: list[str]) -> bool:
    """判断文本中是否包含所有期望片段，比较时忽略大小写。"""
    lowered_text = text.lower()
    return all(item.lower() in lowered_text for item in expected_items)


def extract_tool_call_name(tool_call: dict[str, Any]) -> str:
    """兼容不同工具调用格式，提取工具名称。"""
    return tool_call.get("name") or tool_call.get("function", {}).get("name", "")


def extract_tool_call_args(tool_call: dict[str, Any]) -> dict[str, Any]:
    """兼容不同工具调用格式，提取工具参数。"""
    args = tool_call.get("args")
    if isinstance(args, dict):
        return args
    function_args = tool_call.get("function", {}).get("arguments")
    if isinstance(function_args, str):
        try:
            return json.loads(function_args)
        except json.JSONDecodeError:
            return {"raw": function_args}
    return {}


async def run_case(graph, case: dict[str, Any], recursion_limit: int) -> dict[str, Any]:
    """执行单条评测用例，并收集工具调用、SQL、最终回答和耗时。"""
    started_at = time.perf_counter()
    final_answer = ""
    generated_sqls = []
    tool_calls = []
    tool_results = []
    error = ""

    try:
        async for event in graph.astream(
            {"messages": [{"role": "user", "content": case["question"]}]},
            stream_mode="values",
            config={"recursion_limit": recursion_limit},
        ):
            message = event["messages"][-1]

            if isinstance(message, AIMessage):
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = extract_tool_call_name(tool_call)
                        args = extract_tool_call_args(tool_call)
                        tool_calls.append({"name": tool_name, "args": args})
                        if tool_name == "db_sql_tool" and "query" in args:
                            generated_sqls.append(args["query"])
                elif message.content:
                    final_answer = normalize_text(message.content)

            if isinstance(message, ToolMessage):
                tool_results.append(
                    {
                        "name": getattr(message, "name", ""),
                        "content": normalize_text(message.content),
                    }
                )
    except Exception as exc:
        error = f"{exc.__class__.__name__}: {exc}"

    elapsed_seconds = time.perf_counter() - started_at
    return score_case(
        case=case,
        final_answer=final_answer,
        generated_sqls=generated_sqls,
        tool_calls=tool_calls,
        tool_results=tool_results,
        elapsed_seconds=elapsed_seconds,
        error=error,
    )


def score_case(
    case: dict[str, Any],
    final_answer: str,
    generated_sqls: list[str],
    tool_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    elapsed_seconds: float,
    error: str,
) -> dict[str, Any]:
    """根据期望表名、字段、关键词和答案片段计算单条用例是否通过。"""
    sql_text = "\n".join(generated_sqls)
    tool_names = [tool_call["name"] for tool_call in tool_calls]
    expected_tables = case.get("expected_tables", [])
    expected_columns = case.get("expected_columns", [])
    expected_sql_keywords = case.get("expected_sql_keywords", [])
    expected_answer_contains = case.get("expected_answer_contains", [])
    need_chart = bool(case.get("need_chart", False))

    table_hit = contains_all(sql_text, expected_tables)
    column_hit = contains_all(sql_text, expected_columns)
    keyword_hit = contains_all(sql_text, expected_sql_keywords)
    answer_hit = contains_all(final_answer, expected_answer_contains)
    sql_tool_called = "db_sql_tool" in tool_names
    chart_hit = True
    if need_chart:
        chart_hit = "run_python_script_tool" in tool_names or ".png" in final_answer.lower()

    passed = all([table_hit, column_hit, keyword_hit, answer_hit, chart_hit, sql_tool_called, not error])

    return {
        "id": case["id"],
        "question": case["question"],
        "passed": passed,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "error": error,
        "checks": {
            "sql_tool_called": sql_tool_called,
            "table_hit": table_hit,
            "column_hit": column_hit,
            "keyword_hit": keyword_hit,
            "answer_hit": answer_hit,
            "chart_hit": chart_hit,
        },
        "expected": {
            "tables": expected_tables,
            "columns": expected_columns,
            "sql_keywords": expected_sql_keywords,
            "answer_contains": expected_answer_contains,
            "need_chart": need_chart,
        },
        "generated_sqls": generated_sqls,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "final_answer": final_answer,
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总所有评测结果，计算总通过率、平均耗时和分项命中率。"""
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    avg_elapsed = sum(result["elapsed_seconds"] for result in results) / total if total else 0
    check_names = ["sql_tool_called", "table_hit", "column_hit", "keyword_hit", "answer_hit", "chart_hit"]
    check_rates = {}
    for check_name in check_names:
        check_rates[check_name] = round(
            sum(1 for result in results if result["checks"][check_name]) / total,
            4,
        ) if total else 0

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0,
        "avg_elapsed_seconds": round(avg_elapsed, 3),
        "check_rates": check_rates,
    }


def write_reports(results: list[dict[str, Any]], report_dir: Path) -> tuple[Path, Path]:
    """将评测结果写入 JSON 和 Markdown 报告文件。"""
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = summarize_results(results)
    json_report_path = report_dir / f"text2sql_eval_{timestamp}.json"
    markdown_report_path = report_dir / f"text2sql_eval_{timestamp}.md"

    with json_report_path.open("w", encoding="utf-8") as file:
        json.dump({"summary": summary, "results": results}, file, ensure_ascii=False, indent=2)

    markdown_lines = [
        "# Text2SQL 评测报告",
        "",
        f"- 用例总数: {summary['total']}",
        f"- 通过数: {summary['passed']}",
        f"- 失败数: {summary['failed']}",
        f"- 总通过率: {summary['pass_rate']:.2%}",
        f"- 平均耗时: {summary['avg_elapsed_seconds']}s",
        "",
        "## 分项命中率",
        "",
    ]
    for check_name, rate in summary["check_rates"].items():
        markdown_lines.append(f"- {check_name}: {rate:.2%}")

    markdown_lines.extend(["", "## 用例明细", ""])
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        markdown_lines.extend(
            [
                f"### {result['id']} - {status}",
                "",
                f"- 问题: {result['question']}",
                f"- 耗时: {result['elapsed_seconds']}s",
                f"- 错误: {result['error'] or '无'}",
                f"- 检查: `{json.dumps(result['checks'], ensure_ascii=False)}`",
                "- 生成 SQL:",
                "",
                "```sql",
                "\n\n".join(result["generated_sqls"]) or "(无)",
                "```",
                "",
                "- 最终回答:",
                "",
                "```text",
                result["final_answer"] or "(无)",
                "```",
                "",
            ]
        )

    with markdown_report_path.open("w", encoding="utf-8") as file:
        file.write("\n".join(markdown_lines))

    return json_report_path, markdown_report_path


async def run_eval(args: argparse.Namespace) -> int:
    """执行完整评测流程：加载用例、运行图、生成报告并返回退出码。"""
    cases = load_cases(args.cases, limit=args.limit)
    if not cases:
        print("No eval cases loaded.")
        return 1

    print(f"Loaded {len(cases)} eval cases from {args.cases}")
    results = []
    async with make_graph() as graph:
        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case['id']}: {case['question']}")
            result = await run_case(graph, case, recursion_limit=args.recursion_limit)
            results.append(result)
            print(f"  -> {'PASS' if result['passed'] else 'FAIL'} ({result['elapsed_seconds']}s)")

    json_report_path, markdown_report_path = write_reports(results, args.report_dir)
    summary = summarize_results(results)
    print(f"Pass rate: {summary['pass_rate']:.2%} ({summary['passed']}/{summary['total']})")
    print(f"JSON report: {json_report_path}")
    print(f"Markdown report: {markdown_report_path}")
    return 0 if summary["failed"] == 0 else 2


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Run ChatBI Text2SQL evaluation cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH, help="Path to JSONL eval cases.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Directory for eval reports.")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N cases.")
    parser.add_argument("--recursion-limit", type=int, default=12, help="LangGraph recursion limit per case.")
    return parser.parse_args()


def main() -> int:
    """脚本入口函数。"""
    args = parse_args()
    return asyncio.run(run_eval(args))


if __name__ == "__main__":
    raise SystemExit(main())
