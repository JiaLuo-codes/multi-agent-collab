"""
Multi-Agent 协同系统 —— LangGraph StateGraph 编排

架构：规划Agent → 搜索Agent → 写作Agent → (重规划) → 输出

三 Agent 角色：
  规划者(Planner)  - 拆解问题，制定搜索计划，评估信息完整性
  搜索者(Searcher) - 按计划联网搜索，收集原始信息
  写作者(Writer)   - 整合信息，生成结构化报告

短路逻辑：规划者评估信息不足 → 重新调度搜索者（最多 2 轮）
"""
from typing import TypedDict, Annotated, Sequence, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_community.llms import Tongyi
from langchain_core.messages import HumanMessage, SystemMessage

from config import DASHSCOPE_API_KEY, MODEL_NAME, TEMPERATURE
from tools import web_search, summarize

# ═══════════════════════════════════════════════════════
# 状态定义
# ═══════════════════════════════════════════════════════

class AgentState(TypedDict):
    query: str                # 用户原始问题
    plan: str                 # 规划Agent 的搜索计划
    search_queries: list      # 规划Agent 拆解的搜索关键词列表
    search_results: str       # 搜索Agent 返回的汇总结果
    round_count: int          # 当前搜索轮次
    is_sufficient: bool       # 信息是否充足
    draft: str                # Writer 草稿
    final_report: str         # 最终报告


# ═══════════════════════════════════════════════════════
# LLM 实例（三个 Agent 共用）
# ═══════════════════════════════════════════════════════

def get_llm():
    return Tongyi(
        model=MODEL_NAME,
        dashscope_api_key=DASHSCOPE_API_KEY,
        temperature=TEMPERATURE,
    )


# ═══════════════════════════════════════════════════════
# 节点 1: 规划Agent —— 拆解问题 + 评估信息
# ═══════════════════════════════════════════════════════

PLANNER_PROMPT = """你是一个任务规划专家。用户会给你一个问题，你需要：

1. 分析问题的核心要点
2. 拆解为 3-5 个具体的搜索关键词（用于联网搜索）
3. 制定搜索计划

如果这是第 2 轮规划（已有上一轮搜索结果），请：
- 评估已有信息是否足以回答用户问题
- 如果不足，指出缺什么，制定补充搜索计划
- 如果已足够，明确说明"信息已充足"

请用 JSON 格式输出：
{
  "analysis": "问题分析（一句话）",
  "search_queries": ["关键词1", "关键词2", "关键词3"],
  "plan": "搜索计划简述",
  "is_sufficient": false
}
"""

def planner_node(state: AgentState) -> dict:
    """规划 Agent: 拆解问题 → 输出搜索计划"""
    llm = get_llm()

    # 构建 prompt
    if state.get("search_results") and state["round_count"] > 0:
        user_msg = f"""用户问题: {state['query']}

上一轮搜索结果:
{state['search_results'][:3000]}

请评估信息是否充足，不足则制定补充搜索计划。输出 JSON。"""
    else:
        user_msg = f"用户问题: {state['query']}\n请拆解问题并制定搜索计划。输出 JSON。"

    response = llm.invoke(PLANNER_PROMPT + "\n\n" + user_msg)

    # 解析 JSON
    import json, re
    try:
        json_str = re.search(r'\{[\s\S]*\}', response).group()
        plan_data = json.loads(json_str)
    except:
        plan_data = {
            "analysis": "自动分析",
            "search_queries": [state["query"]],
            "plan": "直接搜索用户问题",
            "is_sufficient": False,
        }

    return {
        "plan": plan_data.get("plan", ""),
        "search_queries": plan_data.get("search_queries", [state["query"]]),
        "is_sufficient": plan_data.get("is_sufficient", False),
        "round_count": state.get("round_count", 0),
    }


# ═══════════════════════════════════════════════════════
# 节点 2: 搜索Agent —— 联网搜索 + 初步整理
# ═══════════════════════════════════════════════════════

SEARCHER_PROMPT = """你是一个信息检索专家。你收到一个搜索关键词列表，需要：

1. 对每个关键词执行联网搜索
2. 筛选最相关的信息（去除广告、无关内容）
3. 整理为结构化摘要

从搜索结果中提取关键事实、数据、观点，标注每条信息的来源。"""

def searcher_node(state: AgentState) -> dict:
    """搜索 Agent: 按搜索计划联网搜索并整理结果"""
    queries = state.get("search_queries", [state["query"]])
    round_count = state.get("round_count", 0) + 1

    all_results = []
    for q in queries[:4]:  # 每轮最多 4 个搜索
        result = web_search.invoke(q)
        all_results.append(f"## 搜索: {q}\n{result}")

    combined = "\n\n---\n\n".join(all_results)

    # 用 LLM 整理搜索结果
    llm = get_llm()
    summary = llm.invoke(
        f"{SEARCHER_PROMPT}\n\n用户问题: {state['query']}\n\n"
        f"原始搜索结果:\n{combined[:5000]}\n\n"
        f"请提取关键信息，整理为结构化摘要（按要点列出，标注来源）。"
    )

    return {
        "search_results": summary,
        "round_count": round_count,
    }


# ═══════════════════════════════════════════════════════
# 节点 3: 写作Agent —— 整合信息 → 结构化报告
# ═══════════════════════════════════════════════════════

WRITER_PROMPT = """你是一个专业报告撰写专家。根据用户问题和搜索结果，生成一份结构化的分析报告。

报告格式:
1. 📋 问题概述
2. 🔍 关键信息（按要点列出）
3. 📊 分析总结
4. 💡 结论与建议（如适用）
5. 📚 信息来源

要求：客观、简洁、有数据支撑，用 Markdown 格式输出。"""

def writer_node(state: AgentState) -> dict:
    """写作 Agent: 整合搜索信息 → 生成结构化报告"""
    llm = get_llm()

    # 先整理草稿
    draft = llm.invoke(
        f"{WRITER_PROMPT}\n\n"
        f"用户问题: {state['query']}\n\n"
        f"搜索到的信息:\n{state.get('search_results', '')[:6000]}\n\n"
        f"请生成报告。"
    )

    return {
        "draft": draft,
        "final_report": draft,
    }


# ═══════════════════════════════════════════════════════
# 路由: 信息是否充足？
# ═══════════════════════════════════════════════════════

def route_after_planner(state: AgentState) -> Literal["searcher", "writer"]:
    """规划 Agent 判断：信息已充足 → 直接写作；不足 → 搜索"""
    if state.get("is_sufficient") and state.get("search_results"):
        return "writer"
    return "searcher"


def route_after_searcher(state: AgentState) -> Literal["planner", "writer"]:
    """搜索完成后：最多 2 轮搜索，超限则直接写作"""
    if state.get("round_count", 0) >= 2:
        return "writer"
    return "planner"


def route_after_writer(state: AgentState) -> Literal["planner", "end"]:
    """写作完成后：评估是否需要补充搜索"""
    return "end"


# ═══════════════════════════════════════════════════════
# 构建 StateGraph
# ═══════════════════════════════════════════════════════

def build_graph():
    """构建 Multi-Agent 协同图"""
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("planner", planner_node)
    workflow.add_node("searcher", searcher_node)
    workflow.add_node("writer", writer_node)

    # 边
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


# ═══════════════════════════════════════════════════════
# 运行入口
# ═══════════════════════════════════════════════════════

def run(query: str) -> dict:
    """运行 Multi-Agent 协同系统，返回完整结果"""
    graph = build_graph()
    initial_state: AgentState = {
        "query": query,
        "plan": "",
        "search_queries": [],
        "search_results": "",
        "round_count": 0,
        "is_sufficient": False,
        "draft": "",
        "final_report": "",
    }
    result = graph.invoke(initial_state)
    return result


if __name__ == "__main__":
    query = "2026年AI Agent领域有哪些重要进展"
    print(f"🚀 Multi-Agent 启动\n📋 问题: {query}\n")
    result = run(query)
    print("=" * 60)
    print(result.get("final_report", "未生成报告"))
    print(f"\n⏱ 搜索轮次: {result.get('round_count', 0)}")
