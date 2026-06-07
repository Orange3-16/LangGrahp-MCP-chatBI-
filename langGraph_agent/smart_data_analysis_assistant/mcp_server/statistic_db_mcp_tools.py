"""
TEXT2SQL 数据库查询MCP:
list_tables_tool:获取数据表结构信息工具
db_sql_tool:写SQL并执行SQL查询并返回数据库运算结果
pip install langchain_community
pip install mcp
pip install dotenv
pip install pymysql
"""
import sys
import os
import re
import threading
import time
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from mcp.server import FastMCP
from sqlalchemy import inspect as sqlalchemy_inspect

# 加载环境变量
try:
    load_dotenv()
except Exception as e:
    print(f"加载环境变量失败: {str(e)}")

# 获取环境变量
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
db_host = os.getenv("db_host")
password = os.getenv("password")
dbname = os.getenv("dbname") or "seles_chat"
db_port = 3306
user = os.getenv("db_user") or os.getenv("user")
DEFAULT_SQL_LIMIT = int(os.getenv("DEFAULT_SQL_LIMIT", "200"))
MAX_SQL_LENGTH = int(os.getenv("MAX_SQL_LENGTH", "5000"))
SCHEMA_CACHE_TTL_SECONDS = int(os.getenv("SCHEMA_CACHE_TTL_SECONDS", "3600"))
SCHEMA_MAX_RETURN_CHARS = int(os.getenv("SCHEMA_MAX_RETURN_CHARS", "10000"))

ALLOWED_SQL_START_KEYWORDS = ("select", "with", "show", "describe", "desc", "explain")
DANGEROUS_SQL_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "truncate",
    "alter",
    "create",
    "replace",
    "rename",
    "grant",
    "revoke",
    "load",
    "outfile",
    "infile",
    "call",
    "execute",
    "prepare",
    "deallocate",
    "set",
    "use",
    "lock",
    "unlock",
)

_schema_cache = {
    "value": None,
    "updated_at": 0.0,
}
_schema_cache_lock = threading.Lock()
_schema_metadata_cache = {
    "value": None,
    "updated_at": 0.0,
}
_schema_metadata_cache_lock = threading.Lock()

print(f"数据库连接信息:")
print(f"  主机: {db_host}")
print(f"  端口: {db_port}")
print(f"  用户: {user}")
print(f"  数据库: {dbname}")
print(f"  密码: {'*' * len(password) if password else '未设置'}")

# 验证必要的环境变量
if not all([db_host, user, password, dbname]):
    print("警告: 数据库连接信息不完整，可能导致连接失败")
    print(f"  主机: {'已设置' if db_host else '未设置'}")
    print(f"  用户: {'已设置' if user else '未设置'}")
    print(f"  密码: {'已设置' if password else '未设置'}")
    print(f"  数据库: {'已设置' if dbname else '未设置'}")

# 初始化MCP服务器
try:
    mcp = FastMCP(name='search_db_mcp', instructions='数据库查询MCP', host="0.0.0.0", port=9004)
except Exception as e:
    print(f"初始化MCP服务器失败: {str(e)}")
    sys.exit(1)

db = None

# 尝试连接数据库
try:
    if db_host and user and password and dbname:
        print(f"正在连接数据库: mysql+pymysql://{user}:{'*' * len(password)}@{db_host}:{db_port}/{dbname}")
        db = SQLDatabase.from_uri(f"mysql+pymysql://{user}:{password}@{db_host}:{db_port}/{dbname}")
        print("数据库连接成功!")
        
        # 测试数据库连接
        try:
            # 使用get_usable_table_names()代替已废弃的get_table_names()
            table_names = db.get_usable_table_names()
            print(f"数据库中的表: {table_names}")
        except Exception as e:
            print(f"测试数据库连接失败: {str(e)}")
            print("警告: 数据库连接可能不稳定，部分功能可能不可用")
            # 不设置db = None，因为连接可能仍然部分可用
    else:
        print("数据库连接信息不完整，无法连接数据库")
        print("服务将继续运行，但数据库相关功能将不可用")
except Exception as e:
    print(f"数据库连接失败: {str(e)}")
    print("服务将继续运行，但数据库相关功能将不可用")
    # 保持db为None，这样工具函数会返回错误信息而不是崩溃

#%%
def _strip_sql_code_fence(query: str) -> str:
    """去掉模型可能返回的 Markdown SQL 代码块。"""
    query = query.strip()
    fenced_match = re.fullmatch(r"```(?:sql)?\s*(.*?)\s*```", query, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()
    return query


def _normalize_sql(query: str) -> str:
    """清洗 SQL 文本，仅保留单条语句主体。"""
    query = _strip_sql_code_fence(query)
    query = query.strip()
    if query.endswith(";"):
        query = query[:-1].strip()
    return query


def _contains_sql_comment(query: str) -> bool:
    """拒绝注释，避免模型或输入通过注释隐藏多语句/危险片段。"""
    return bool(re.search(r"(--|#|/\*|\*/)", query))


def _contains_multiple_statements(query: str) -> bool:
    """保守处理：清理末尾分号后，主体中仍有分号则视为多语句。"""
    return ";" in query


def _first_sql_keyword(query: str) -> str:
    match = re.match(r"^\s*([a-zA-Z]+)\b", query)
    return match.group(1).lower() if match else ""


def _contains_dangerous_keyword(query: str) -> bool:
    lowered_query = query.lower()
    for keyword in DANGEROUS_SQL_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered_query):
            return True
    return False


def _has_limit(query: str) -> bool:
    return bool(re.search(r"\blimit\s+\d+\b", query, flags=re.IGNORECASE))


def _should_append_limit(query: str) -> bool:
    first_keyword = _first_sql_keyword(query)
    if first_keyword not in ("select", "with"):
        return False
    if _has_limit(query):
        return False
    return True


def _append_limit(query: str) -> str:
    if _should_append_limit(query):
        return f"{query} LIMIT {DEFAULT_SQL_LIMIT}"
    return query


SQL_RESERVED_WORDS = {
    "select",
    "from",
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "full",
    "cross",
    "on",
    "as",
    "and",
    "or",
    "not",
    "in",
    "is",
    "null",
    "like",
    "between",
    "group",
    "by",
    "order",
    "having",
    "limit",
    "offset",
    "distinct",
    "union",
    "all",
    "case",
    "when",
    "then",
    "else",
    "end",
    "asc",
    "desc",
    "true",
    "false",
    "with",
    "over",
    "partition",
}
SQL_FUNCTION_NAMES = {
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "round",
    "cast",
    "coalesce",
    "ifnull",
    "date",
    "year",
    "month",
    "day",
    "concat",
    "substring",
    "substr",
}
CLAUSE_KEYWORDS = SQL_RESERVED_WORDS | SQL_FUNCTION_NAMES
TABLE_ALIAS_STOP_WORDS = {
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "full",
    "cross",
    "on",
    "group",
    "order",
    "having",
    "limit",
    "union",
}


def _clean_identifier(identifier: str) -> str:
    identifier = identifier.strip()
    identifier = identifier.strip("`")
    identifier = re.sub(r"\s+", "", identifier)
    if "." in identifier:
        identifier = identifier.split(".")[-1].strip("`")
    return identifier


def _identifier_key(identifier: str) -> str:
    return _clean_identifier(identifier).lower()


def _strip_string_literals(query: str) -> str:
    query = re.sub(r"'(?:''|[^'])*'", " ", query)
    query = re.sub(r'"(?:""|[^"])*"', " ", query)
    return query


def _is_metadata_cache_valid() -> bool:
    cached_value = _schema_metadata_cache["value"]
    if not cached_value:
        return False
    cache_age = time.time() - _schema_metadata_cache["updated_at"]
    return cache_age < SCHEMA_CACHE_TTL_SECONDS


def _build_schema_metadata() -> dict:
    """读取数据库表和字段元数据，用于执行前 SQL 静态校验。"""
    table_names = db.get_usable_table_names()
    inspector = sqlalchemy_inspect(db._engine)

    table_lookup = {}
    columns_by_table = {}
    for table_name in table_names:
        table_key = table_name.lower()
        table_lookup[table_key] = table_name
        columns = inspector.get_columns(table_name)
        columns_by_table[table_key] = {
            column["name"].lower(): column["name"] for column in columns
        }

    return {
        "table_lookup": table_lookup,
        "columns_by_table": columns_by_table,
    }


def get_cached_schema_metadata(force_refresh: bool = False) -> dict:
    """读取表/字段元数据，优先使用 TTL 内的内存缓存。"""
    with _schema_metadata_cache_lock:
        if not force_refresh and _is_metadata_cache_valid():
            cache_age = int(time.time() - _schema_metadata_cache["updated_at"])
            print(f"使用数据库schema元数据缓存，缓存年龄: {cache_age}s")
            return _schema_metadata_cache["value"]

        print("刷新数据库schema元数据缓存")
        metadata = _build_schema_metadata()
        _schema_metadata_cache["value"] = metadata
        _schema_metadata_cache["updated_at"] = time.time()
        return metadata


def _extract_cte_names(query: str) -> set[str]:
    if _first_sql_keyword(query) != "with":
        return set()
    return {
        _identifier_key(match.group(1))
        for match in re.finditer(r"(?:with|,)\s+(`[^`]+`|[A-Za-z_][\w$]*)\s+as\s*\(", query, flags=re.IGNORECASE)
    }


def _extract_table_references(query: str) -> tuple[dict[str, str], list[str], set[str]]:
    cte_names = _extract_cte_names(query)
    alias_to_table = {}
    referenced_tables = []

    table_pattern = re.compile(
        r"\b(?:from|join)\s+((?:`[^`]+`|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:`[^`]+`|[A-Za-z_][\w$]*))?)"
        r"(?:\s+(?:as\s+)?(`[^`]+`|[A-Za-z_][\w$]*))?",
        flags=re.IGNORECASE,
    )
    for match in table_pattern.finditer(query):
        table_name = _clean_identifier(match.group(1))
        table_key = table_name.lower()
        if table_key in cte_names:
            continue

        referenced_tables.append(table_key)
        alias_to_table[table_key] = table_key

        alias = match.group(2)
        if alias:
            alias_key = _identifier_key(alias)
            if alias_key not in TABLE_ALIAS_STOP_WORDS:
                alias_to_table[alias_key] = table_key

    return alias_to_table, referenced_tables, cte_names


def _extract_select_aliases(query: str) -> set[str]:
    return {
        _identifier_key(match.group(1))
        for match in re.finditer(r"\bas\s+(`[^`]+`|[A-Za-z_][\w$]*)", query, flags=re.IGNORECASE)
    }


def _extract_qualified_column_refs(query: str) -> list[tuple[str, str]]:
    refs = []
    qualified_pattern = re.compile(
        r"(`[^`]+`|[A-Za-z_][\w$]*)\s*\.\s*(`[^`]+`|[A-Za-z_][\w$]*)",
        flags=re.IGNORECASE,
    )
    for match in qualified_pattern.finditer(query):
        refs.append((_identifier_key(match.group(1)), _identifier_key(match.group(2))))
    return refs


def _extract_unqualified_identifiers(query: str) -> set[str]:
    cleaned_query = _strip_string_literals(query)
    cleaned_query = re.sub(r"(`[^`]+`|[A-Za-z_][\w$]*)\s*\.\s*(`[^`]+`|[A-Za-z_][\w$]*)", " ", cleaned_query)

    identifiers = set()
    for match in re.finditer(r"`([^`]+)`|\b([A-Za-z_][\w$]*)\b", cleaned_query):
        token = match.group(1) or match.group(2)
        token_key = token.lower()
        if token_key in CLAUSE_KEYWORDS:
            continue
        next_chars = cleaned_query[match.end(): match.end() + 8].lstrip()
        if next_chars.startswith("("):
            continue
        identifiers.add(token_key)
    return identifiers


def validate_sql_schema_references(query: str) -> tuple[bool, str]:
    """
    执行前校验 SQL 中引用的表名和字段名是否存在。
    该校验覆盖常见 SELECT/JOIN SQL；复杂 CTE 或子查询无法静态判断时交给数据库执行错误兜底。
    """
    first_keyword = _first_sql_keyword(query)
    if first_keyword not in ("select", "with", "describe", "desc", "explain"):
        return True, ""

    metadata = get_cached_schema_metadata()
    table_lookup = metadata["table_lookup"]
    columns_by_table = metadata["columns_by_table"]

    if first_keyword in ("describe", "desc"):
        parts = query.split()
        if len(parts) >= 2:
            table_key = _identifier_key(parts[1])
            if table_key not in table_lookup:
                return False, f"错误: SQL引用了不存在的表: {parts[1]}"
        return True, ""

    alias_to_table, referenced_tables, cte_names = _extract_table_references(query)
    missing_tables = sorted({table for table in referenced_tables if table not in table_lookup})
    if missing_tables:
        return False, f"错误: SQL引用了不存在的表: {', '.join(missing_tables)}"

    if not referenced_tables and cte_names:
        return True, ""

    for qualifier, column in _extract_qualified_column_refs(query):
        table_key = alias_to_table.get(qualifier, qualifier)
        if table_key in cte_names:
            continue
        if table_key not in table_lookup:
            return False, f"错误: SQL引用了不存在的表或别名: {qualifier}"
        if column != "*" and column not in columns_by_table[table_key]:
            table_name = table_lookup[table_key]
            return False, f"错误: SQL在表 {table_name} 中引用了不存在的字段: {column}"

    if not referenced_tables:
        return True, ""

    valid_column_union = set()
    for table_key in referenced_tables:
        valid_column_union.update(columns_by_table.get(table_key, {}).keys())

    ignored_identifiers = set(alias_to_table.keys()) | set(referenced_tables) | cte_names | _extract_select_aliases(query)
    for identifier in _extract_unqualified_identifiers(query):
        if identifier in ignored_identifiers:
            continue
        if identifier not in valid_column_union:
            return False, f"错误: SQL引用了不存在的字段: {identifier}"

    return True, ""


def validate_and_prepare_readonly_sql(query: str) -> tuple[bool, str, str]:
    """
    校验并准备只读 SQL。
    :return: (是否通过, 可执行SQL或原SQL, 错误信息)
    """
    if not query or not isinstance(query, str):
        return False, "", "错误: SQL查询语句不能为空"

    prepared_query = _normalize_sql(query)
    if not prepared_query:
        return False, "", "错误: SQL查询语句不能为空"

    if len(prepared_query) > MAX_SQL_LENGTH:
        return False, prepared_query, f"错误: SQL查询语句过长，最大允许 {MAX_SQL_LENGTH} 字符"

    if _contains_sql_comment(prepared_query):
        return False, prepared_query, "错误: SQL查询语句中不允许包含注释"

    if _contains_multiple_statements(prepared_query):
        return False, prepared_query, "错误: 只允许执行单条SQL查询语句"

    first_keyword = _first_sql_keyword(prepared_query)
    if first_keyword not in ALLOWED_SQL_START_KEYWORDS:
        allowed_keywords = ", ".join(keyword.upper() for keyword in ALLOWED_SQL_START_KEYWORDS)
        return False, prepared_query, f"错误: 只允许执行只读查询语句，SQL必须以 {allowed_keywords} 开头"

    if _contains_dangerous_keyword(prepared_query):
        return False, prepared_query, "错误: SQL查询语句包含写入、DDL或高风险关键字，已拒绝执行"

    is_schema_valid, schema_error_msg = validate_sql_schema_references(prepared_query)
    if not is_schema_valid:
        return False, prepared_query, schema_error_msg

    return True, _append_limit(prepared_query), ""


#%%
def get_table_comments(db):
    """获取所有表及其字段的注释信息"""
    # 执行查询，直接使用db.get_table_names()获取表名
    try:
        if db is None:
            print("错误: 数据库连接失败，无法获取表注释信息")
            return {}
        
        # 获取所有表名
        table_names = db.get_usable_table_names()
        print(f"数据库中的表: {table_names}")
        
        # 组织结果
        tables = {}
        for table_name in table_names:
            # 获取表的结构信息
            schema = db.get_table_info([table_name])
            print(f"表 {table_name} 的结构: {schema}")
            
            # 简化处理，直接存储表名和结构信息
            tables[table_name] = {
                'comment': '',
                'columns': []
            }
            
            # 尝试解析schema获取列信息
            lines = schema.split('\n')
            for line in lines:
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 3:
                        column_name = parts[1].strip()
                        column_type = parts[2].strip()
                        if column_name and column_type and column_name != 'Column':
                            tables[table_name]['columns'].append({
                                'name': column_name,
                                'type': column_type,
                                'comment': ''
                            })
        
        return tables
    except Exception as e:
        print(f"执行查询失败: {str(e)}")
        return {}


# tables=get_table_comments(db)
# print(tables) #RAG
#%%
def _truncate_schema_result(schema_text: str) -> str:
    if len(schema_text) <= SCHEMA_MAX_RETURN_CHARS:
        return schema_text
    print("警告: 返回结果过长，将进行截断")
    return schema_text[: SCHEMA_MAX_RETURN_CHARS - 10] + "\n... (结果被截断)"


def _build_database_schema_text() -> str:
    """从数据库读取所有表结构，并格式化为模型可用的 schema 文本。"""
    table_names = db.get_usable_table_names()
    print(f"数据库中的表: {table_names}")

    if not table_names:
        return "数据库中没有表"

    result = []
    for table_name in table_names:
        try:
            schema = db.get_table_info([table_name])
            print(f"表 {table_name} 的结构: {schema}")
            result.append(f"表名: {table_name}\n{schema}")
        except Exception as e:
            print(f"获取表 {table_name} 的结构失败: {str(e)}")
            result.append(f"表名: {table_name}\n错误: 无法获取表结构信息")

    final_result = "\n\n".join(result)
    print(f"返回的结果长度: {len(final_result)}")
    return _truncate_schema_result(final_result)


def _is_schema_cache_valid() -> bool:
    cached_value = _schema_cache["value"]
    if not cached_value:
        return False
    cache_age = time.time() - _schema_cache["updated_at"]
    return cache_age < SCHEMA_CACHE_TTL_SECONDS


def get_cached_database_schema(force_refresh: bool = False) -> str:
    """读取数据库 schema，优先使用 TTL 内的内存缓存。"""
    with _schema_cache_lock:
        if not force_refresh and _is_schema_cache_valid():
            cache_age = int(time.time() - _schema_cache["updated_at"])
            print(f"使用数据库schema缓存，缓存年龄: {cache_age}s")
            return _schema_cache["value"]

        print("刷新数据库schema缓存")
        schema_text = _build_database_schema_text()
        _schema_cache["value"] = schema_text
        _schema_cache["updated_at"] = time.time()
        return schema_text


@mcp.tool()
async def list_tables_tool(force_refresh: bool = False) -> str:
    """
    返回数据库中的所有表及其结构信息，包括表和字段的注释。
    :param force_refresh: 是否强制刷新schema缓存，默认为False
    :return: 数据库中的所有表及其结构信息的格式化字符串
    """
    if db is None:
        return "错误: 数据库连接失败，无法获取表结构信息"
    
    try:
        final_result = get_cached_database_schema(force_refresh=force_refresh)
        print(f"返回的结果前500字符: {final_result[:500]}")
        return final_result
    except Exception as e:
        print(f"获取表结构信息失败: {str(e)}")
        return f"错误: 获取表结构信息失败: {str(e)}"

# async def main():
#     result=await list_tables_tool()
#     print(result)
# import asyncio
# asyncio.run(main())
#%%
@mcp.tool()
def db_sql_tool(query: str) -> str:
    """
    执行SQL查询并返回结果。如果查询不正确，将返回错误信息;如果返回错误，请重写查询语句，检查后重试。
    :param query: 非空的要执行的SQL查询语句
    :return:str: 查询结果或错误信息
    """
    if db is None:
        return "错误: 数据库连接失败，无法执行SQL查询"
    
    try:
        is_valid, safe_query, error_msg = validate_and_prepare_readonly_sql(query)
        if not is_valid:
            print(f"拒绝执行SQL: {safe_query}; 原因: {error_msg}")
            return error_msg
        
        print(f"执行SQL查询: {safe_query}")
        
        #利用的是关系型数据库查询SQL的内置方法
        result = db.run(safe_query)  # 执行查询
        
        print(f"查询结果: {result}")
        
        if not result:
            return "提示: 查询成功，但没有返回结果"
        
        # 限制返回结果的长度，避免过大的响应
        if len(result) > 5000:
            print("警告: 查询结果过长，将进行截断")
            result = result[:4990] + "\n... (结果被截断)"
        
        return result
    except Exception as e:
        error_msg = f"错误: 执行SQL查询失败: {str(e)}"
        print(error_msg)
        return error_msg


if __name__ == "__main__":
    try:
        # 以标准 sse方式运行 MCP 服务器
        print("正在启动MCP服务器...")
        print("服务器地址: http://0.0.0.0:9004")
        mcp.run(transport='sse')
    except Exception as e:
        print(f"启动MCP服务器失败: {str(e)}")
        import traceback
        traceback.print_exc()

#nohup python statistic_db_mcp_tools.py &
#nohup uv run statistic_db_mcp_tools.py &  -->官方更推荐这个方法
