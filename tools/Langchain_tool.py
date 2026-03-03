from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import Tool
from langchain_experimental.utilities import PythonREPL
import os
from pathlib import Path
from langchain_core.documents import Document
# Keep credential injection path-agnostic.
# Prefer externally provided env vars; only set a relative fallback when missing.
if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    repo_root = Path(__file__).resolve().parents[1]
    fallback_cred = repo_root / "tools" / "bigquery" / "ee-guihousun-f062ac4ad3a3.json"
    if fallback_cred.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(fallback_cred)
# 创建 BigQuery 客户端
from langchain_core.tools import StructuredTool
from langchain_google_community import BigQueryLoader
import os
# from exa_py import Exa
from langchain_core.tools import tool
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.tools.playwright.utils import (
    create_async_playwright_browser,  # A synchronous browser is available, though it isn't compatible with jupyter.\n",	  },
)# This import is required only for jupyter notebooks, since they have their own eventloop
# import nest_asyncio

# project_id = 'empyrean-caster-430308-m2'
# ee.Initialize(project=project_id)
### Build search tool ###

# # 定义BigQuery查询工具
# def query_bigquery(query: str) -> list[Document]:
#     loader = BigQueryLoader(query)  # 使用BigQueryLoader工具
#     data = loader.load()  # 加载查询结果
#     return data  # 将结果转换为字符串形式返回
# # 创建StructuredTool
# gdelt_query_tool = StructuredTool.from_function(
#     query_bigquery,
#     name="gdelt_query_tool",
    # description=(
    #     "This tool allows you to query GDELT datasets on Google BigQuery. The queries should be written in standard "
    #     "SQL syntax. Since quota is limited, queries should be scoped to the necessary thing relevant to the analysis.\n\n"
    #     "Example:\n"
    #     "- Query: 'SELECT GlobalEventID, SQLDATE, EventCode, EventBaseCode, Actor1Name, Actor1CountryCode, Actor2Name, "
    #     "Actor2CountryCode, Actor1Geo_FullName, ActionGeo_FullName, ActionGeo_Lat, ActionGeo_Long, NumMentions, "
    #     "NumSources, NumArticles, AvgTone, SOURCEURL FROM gdelt-bq.gdeltv2.events WHERE (EventCode IN ('051', '030', '014', "
    #     "'010', '015', '140') OR EventBaseCode IN ('051', '051') OR (EventCode = '060' AND EventBaseCode = '060')) AND "
    #     "(Actor1Name LIKE '%concert%' OR Actor2Name LIKE '%concert%' OR ActionGeo_FullName LIKE '%fireworks%' OR "
    #     "ActionGeo_FullName LIKE '%light show%' OR EventCode = '060' OR EventBaseCode = '015' OR EventCode = '140') AND "
    #     "SQLDATE BETWEEN 20240101 AND 20241231 AND NumMentions > 5 AND NumSources > 2 ORDER BY SQLDATE DESC LIMIT 100;'\n\n"
    # ),
#     input_type=str  # 输入类型是查询字符串
# )

import re
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from google.cloud import bigquery

# 1. 定义参数模型
class GDELTQuerySchema(BaseModel):
    query: str = Field(
        ..., 
        description="Standard SQL query for GDELT. MUST include 'LIMIT' and a 'SQLDATE' filter."
    )

# 2. 带有“保险”逻辑的查询函数
def query_bigquery_safe(query: str) -> str:
    client = bigquery.Client()
    
    # --- 保险 A: 强制 LIMIT 检查 ---
    # 如果没写 LIMIT，或者 LIMIT 大于 500，强制设为 100
    limit_match = re.search(r"LIMIT\s+(\d+)", query, re.IGNORECASE)
    if not limit_match:
        query = query.rstrip().rstrip(';') + " LIMIT 100;"
    elif int(limit_match.group(1)) > 500:
        query = re.sub(r"LIMIT\s+\d+", "LIMIT 500", query, flags=re.IGNORECASE)

    # --- 保险 B: 强制日期过滤检查 (针对 GDELT) ---
    if "SQLDATE" not in query.upper():
        return "Error: For quota safety, your query must include a 'SQLDATE' filter (e.g., SQLDATE BETWEEN 20240101 AND 20240131)."

    # --- 保险 C: 预估扫描量 (Dry Run) ---
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    try:
        query_job = client.query(query, job_config=job_config)
        estimated_bytes = query_job.total_bytes_processed
        
        # 设定阈值：例如单次查询不允许超过 500MB
        MAX_ALLOWED_BYTES = 500 * 1024 * 1024 
        if estimated_bytes > MAX_ALLOWED_BYTES:
            return f"Error: Query rejected. Estimated scan size ({estimated_bytes / 1024**2:.2f} MB) exceeds safety limit."
    except Exception as e:
        return f"SQL Syntax Error during dry run: {str(e)}"

    # --- 执行查询 ---
    # 这里可以使用你原来的 BigQueryLoader，或者直接用 client 转换
    try:
        # 建议实际执行时也带上配置，防止意外
        real_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_ALLOWED_BYTES)
        data = client.query(query, job_config=real_config).to_dataframe()
        
        # 转换为字符串返回给 LLM（或者返回 Document list）
        if data.empty:
            return "Query successful but no results found."
        return data.to_markdown(index=False) 
    except Exception as e:
        return f"Execution Error: {str(e)}"

# 3. 创建 StructuredTool
gdelt_query_tool = StructuredTool.from_function(
    func=query_bigquery_safe,
    name="gdelt_query_tool",
    description=(
        "Query GDELT datasets on BigQuery. "
        "Safety Rules: 1. Always use 'SQLDATE' to filter rows. 2. Max limit is 500. "
        "3. Queries scanning >500MB will be blocked. "
        "Example SQL: SELECT EventCode, Actor1Name FROM `gdelt-bq.gdeltv2.events` "
        "WHERE SQLDATE = 20240501 LIMIT 10"
    ),
    args_schema=GDELTQuerySchema
)


from typing import Any, Dict, Union
import requests
import yaml


def _get_schema(response_json: Union[dict, list]) -> dict:
    if isinstance(response_json, list):
        response_json = response_json[0] if response_json else {}
    return {key: type(value).__name__ for key, value in response_json.items()}

def _get_api_spec() -> str:
    base_url = "https://jsonplaceholder.typicode.com"
    endpoints = [
        "/posts",
        "/comments",
    ]
    common_query_parameters = [
        {
            "name": "_limit",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "example": 2},
            "description": "Limit the number of results",
        }
    ]
    openapi_spec: Dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "JSONPlaceholder API", "version": "1.0.0"},
        "servers": [{"url": base_url}],
        "paths": {},
    }
    # Iterate over the endpoints to construct the paths
    for endpoint in endpoints:
        response = requests.get(base_url + endpoint)
        if response.status_code == 200:
            schema = _get_schema(response.json())
            openapi_spec["paths"][endpoint] = {
                "get": {
                    "summary": f"Get {endpoint[1:]}",
                    "parameters": common_query_parameters,
                    "responses": {
                        "200": {
                            "description": "Successful response",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": schema}
                                }
                            },
                        }
                    },
                }
            }
    return yaml.dump(openapi_spec, sort_keys=False)
api_spec = _get_api_spec()

from langchain_community.agent_toolkits.openapi.toolkit import RequestsToolkit
from langchain_community.utilities.requests import TextRequestsWrapper
ALLOW_DANGEROUS_REQUEST = True
toolkit = RequestsToolkit(
    requests_wrapper=TextRequestsWrapper(headers={}),
    allow_dangerous_requests=ALLOW_DANGEROUS_REQUEST,
)
Browser_Toolkit = toolkit.get_tools()


# from langchain_community.tools import DuckDuckGoSearchResults
#
# DuckDuckGoSearch = DuckDuckGoSearchResults(output_format="list",max_results=8)
#

from langchain_community.utilities import GoogleSerperAPIWrapper

GoogleSerpersearch = GoogleSerperAPIWrapper()
GoogleSerper_search=Tool(
        name="GoogleSerper_search",
        func=GoogleSerpersearch.run,
        description="useful for when you need to ask with search; especial query Google question and Google Places",
    )

# from langchain_community.tools.riza.command import ExecPython
# from langchain_community.tools.riza.command import ExecPython
# from langchain.agents import AgentExecutor, create_tool_calling_agent, create_openai_functions_agent
# from langchain_anthropic import ChatAnthropic
# from langchain_core.prompts import ChatPromptTemplate
# Initialize Python REPL to execute code
python_repl = PythonREPL()
### Build Python repl ###
# You can create the tool to pass to an agent
repl_tool = Tool(
    name="python_repl",
    description=(
        """
        A Python shell. Use this to execute Python commands. Input should be a valid Python command. 
        To ensure correct path handling, all file paths should be provided as raw strings (e.g., r'C:\\path\\to\\file'). 
        Paths should also be constructed using os.path.join() for cross-platform compatibility. 
        Additionally, verify the existence of files before attempting to access them.
        After executing the command, use the `print` function to output the results. 
        Finally print('Task Completed').
        For tasks related to nighttime light processing and visualization, please first seek help from the code assistant!!!
        """

    ),
    func=python_repl.run,
)

# ExecPython = ExecPython()
# Riza_tool=Tool(
#         name="Riza_Code_Interpreter",
#         description="The Riza Code Interpreter is a WASM-based isolated environment for running Python or JavaScript generated by AI agents.Only return text",
#         func=ExecPython.run,
#     )


# from langchain_community.tools.wikidata.tool import WikidataAPIWrapper, WikidataQueryRun

# wikidata = WikidataQueryRun(api_wrapper=WikidataAPIWrapper())

# print(wikidata.run("Alan Turing"))



# wolfram_alpha = WolframAlphaAPIWrapper()
