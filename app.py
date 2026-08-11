"""
Multi-Agent 协同系统 —— Streamlit 交互界面
"""
import streamlit as st
from graph import run

st.set_page_config(page_title="Multi-Agent 协同", page_icon="🤝", layout="wide")
st.title("🤝 Multi-Agent 协同研究系统")
st.caption("规划Agent → 搜索Agent → 写作Agent · LangGraph 编排 · 多轮自纠偏")

# ── 侧边栏 ──
with st.sidebar:
    st.header("🏗️ 系统架构")
    st.markdown("""
    ```
    📋 规划Agent
      ↓ 拆解问题
    🔍 搜索Agent
      ↓ 联网检索
    📋 规划Agent
      ↓ 评估完整性 → 不足则重新搜索
    ✍️ 写作Agent
      ↓
    📄 结构化报告
    ```
    """)
    st.divider()
    st.markdown("**核心特性:**")
    st.markdown("- 三 Agent 角色分工")
    st.markdown("- 规划者评估信息完整性")
    st.markdown("- 信息不足自动补搜（≤2轮）")
    st.markdown("- 联网搜索 + 结构化报告")
    st.divider()
    if st.button("🗑️ 清空输出"):
        st.session_state.results = []
        st.rerun()

# ── 初始化 ──
if "results" not in st.session_state:
    st.session_state.results = []

# ── 输入区 ──
st.markdown("### 📝 输入研究问题")
col1, col2 = st.columns([4, 1])
with col1:
    query = st.text_input(
        "问题",
        placeholder="例如: 2026年AI Agent领域有哪些重要进展？Llama 4与GPT-5对比分析？...",
        label_visibility="collapsed",
    )
with col2:
    go = st.button("🚀 开始研究", use_container_width=True, type="primary")

if go and query.strip():
    with st.spinner("Agent 协作中，请稍候..."):
        result = run(query.strip())

        st.session_state.results.insert(0, {
            "query": query,
            "search_queries": result.get("search_queries", []),
            "report": result.get("final_report", ""),
            "rounds": result.get("round_count", 0),
        })

# ── 展示结果 ──
for i, r in enumerate(st.session_state.results):
    with st.expander(f"📄 {r['query'][:80]}...", expanded=(i == 0)):
        col_a, col_b = st.columns([1, 3])

        with col_a:
            st.metric("搜索轮次", r["rounds"])
            if r.get("search_queries"):
                st.markdown("**搜索关键词:**")
                for q in r["search_queries"]:
                    st.markdown(f"- `{q}`")

        with col_b:
            st.markdown(r["report"])
