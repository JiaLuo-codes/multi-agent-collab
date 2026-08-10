"""
Multi-Agent 协同系统 —— LangGraph StateGraph 编排（优化版）

流程: 规划 → 搜索 → 写作 → 输出（最多 2 轮搜索）
"""
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import DASHSCOPE_API_KEY, MODEL_NAME, TEMPERATURE
from tools import web_search


# ═══════════════════════════════════════════════════════
# 状态
# ═══════════════════════════════════════════════════════

class AgentState(TypedDict):
    query: str
    search_queries: list
    search_results: str
    round_count: int
    final_report: str


# ═══════════════════════════════════════════════════════
# LLM —— 用 ChatOpenAI 兼容模式调 DashScope（比 langchain_community 快）
# ═══════════════════════════════════════════════════════

def get_llm():
    return ChatOpenAI(
        model=MODEL_NAME,
        api_key=DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=TEMPERATURE,
    )


# ═══════════════════════════════════════════════════════
# 节点 1: 规划 —— 直接输出搜索词（不要 JSON，减少 token）
# ═══════════════════════════════════════════════════════

def planner_node(state: AgentState) -> dict:
    """拆解问题 → 输出 3 个搜索关键词"""
    llm = get_llm()

    if state.get("search_results") and state["round_count"] > 0:
        prompt = f"""用户问题: {state['query']}

已搜索到的信息:
{state['search_results'][:2000]}

判断信息是否足够回答问题。如果足够，只回复一个字: 够
如果不够，列出 3 个补充搜索关键词（每行一个，不要编号）。"""
    else:
        prompt = f"为研究以下问题，列出 3 个最佳搜索关键词（每行一个，不要编号）:\n{state['query']}"

    response = llm.invoke([HumanMessage(content=prompt)])
    text = response.content.strip()

    # 判断是否充足
    if text == "够" or text.startswith("够"):
        return {
            "search_queries": state.get("search_queries", []),
            "is_sufficient_for_route": True,
            "round_count": state.get("round_count", 0),
        }

    # 解析搜索关键词
    queries = [q.strip("-•·1234567890. ") for q in text.split("\n") if q.strip()]
    queries = [q for q in queries if len(q) > 2 and len(q) < 100][:3]
    if not queries:
        queries = [state["query"]]

    return {
        "search_queries": queries,
        "is_sufficient_for_route": False,
        "round_count": state.get("round_count", 0),
    }


# ═══════════════════════════════════════════════════════
# 节点 2: 搜索 —— 联网搜 + 直接拼接（不额外调 LLM 整理，省一次调用）
# ═══════════════════════════════════════════════════════

def searcher_node(state: AgentState) -> dict:
    """搜索 + 拼接结果"""
    queries = state.get("search_queries", [state["query"]])
    round_count = state.get("round_count", 0) + 1

    all_parts = []
    for q in queries[:3]:
        result = web_search.invoke(q)
        all_parts.append(f"【关键词: {q}】\n{result}")

    combined = "\n\n---\n\n".join(all_parts)

    # 直接拼接，不调 LLM 整理（省 5~10 秒）
    return {
        "search_results": combined,
        "round_count": round_count,
    }


# ═══════════════════════════════════════════════════════
# 节点 3: 写作 —— 整合 → 报告
# ═══════════════════════════════════════════════════════

WRITER_PROMPT = """你是一个专业的研究助理。根据搜索结果回答用户问题，生成一份简洁的报告。

要求:
- 先给出一句话结论
- 按要点列出关键发现（每条标注信息来源）
- 最后给出总结
- 用 Markdown 格式，2000字以内"""

def writer_node(state: AgentState) -> dict:
    """生成最终报告"""
    llm = get_llm()

    report = llm.invoke([
        SystemMessage(content=WRITER_PROMPT),
        HumanMessage(content=f"问题: {state['query']}\n\n参考资料:\n{state.get('search_results', '')[:8000]}")
    ])

    return {"final_report": report.content}


# ═══════════════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════════════

# 用一个独立的 key 做路由判断，不和 state 字段混淆
def route_after_planner(state: AgentState) -> Literal["searcher", "writer"]:
    if state.get("is_sufficient_for_route"):
        return "writer"
    return "searcher"

def route_after_searcher(state: AgentState) -> Literal["planner", "writer"]:
    if state.get("round_count", 0) < 2:
        return "planner"
    return "writer"


# ═══════════════════════════════════════════════════════
# 构建图
# ═══════════════════════════════════════════════════════

def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("searcher", searcher_node)
    workflow.add_node("writer", writer_node)

    workflow.set_entry_point("planner")
    workflow.add_conditional_edges("planner", route_after_planner, {
        "searcher": "searcher",
        "writer": "writer",
    })
    workflow.add_conditional_edges("searcher", route_after_searcher, {
        "planner": "planner",
        "writer": "writer",
    })
    workflow.add_edge("writer", END)

    return workflow.compile()


def run(query: str) -> dict:
    graph = build_graph()
    result = graph.invoke({
        "query": query,
        "search_queries": [],
        "search_results": "",
        "round_count": 0,
        "final_report": "",
    })
    return result


if __name__ == "__main__":
    query = "2026年AI Agent领域有哪些重要进展"
    print(f"问题: {query}\n")
    result = run(query)
    print("=" * 60)
    print(result.get("final_report", "未生成"))
    print(f"\n搜索轮次: {result.get('round_count', 0)}")
