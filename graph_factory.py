from __future__ import annotations

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph_supervisor import create_supervisor
from pydantic import SecretStr


def build_ntl_graph(
    model_name: str,
    api_key: str,
    request_timeout_s: int = 120,
    graph_name: str = "NTL-GPT",
):
    """
    Build and compile the NTL multi-agent LangGraph without Streamlit dependency.
    """
    from tools import Code_tools, Engineer_tools, data_searcher_tools
    from agents.NTL_Code_Assistant import Code_Assistant_system_prompt_text
    from agents.NTL_Data_Searcher import system_prompt_data_searcher
    from agents.NTL_Engineer import system_prompt_text

    if "qwen" in model_name.lower():
        llm = ChatOpenAI(
            api_key=SecretStr(api_key),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model=model_name,
            timeout=request_timeout_s
        )
    else:
        llm = init_chat_model(
            model_name,
            model_provider="openai",
            api_key=api_key,
            temperature=0,
            timeout=request_timeout_s,
            max_retries=3,
        )

    error_interceptor = []

    code_assistant = create_agent(
        llm,
        tools=Code_tools,
        system_prompt=Code_Assistant_system_prompt_text,
        name="Code_Assistant",
        middleware=error_interceptor,
    )

    data_searcher = create_agent(
        llm,
        tools=data_searcher_tools,
        system_prompt=system_prompt_data_searcher,
        name="Data_Searcher",
        middleware=error_interceptor,
    )

    workflow = create_supervisor(
        model=llm,
        agents=[data_searcher, code_assistant],
        prompt=system_prompt_text,
        add_handoff_back_messages=True,
        output_mode="full_history",
        tools=list(Engineer_tools),
        supervisor_name="NTL_Engineer",
    )

    return workflow.compile(checkpointer=MemorySaver(), name=graph_name)
