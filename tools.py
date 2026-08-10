"""工具定义 —— 联网搜索 + RAG 文档检索"""
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults


@tool
def web_search(query: str) -> str:
    """联网搜索，获取最新信息。输入搜索关键词，返回相关结果摘要。"""
    try:
        search = DuckDuckGoSearchResults(max_results=3, output_format="list")
        results = search.invoke(query)
        if not results:
            return "未找到相关结果，请尝试更换搜索关键词。"
        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "无标题")
            snippet = r.get("snippet", "")[:300]
            link = r.get("link", "")
            lines.append(f"[{i}] {title}\n   {snippet}\n   {link}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"搜索出错: {e}。请稍后重试或更换关键词。"


@tool
def summarize(text: str) -> str:
    """对长文本进行摘要提炼。输入原文，返回关键要点。"""
    # 简单的提取式摘要
    sentences = [s.strip() for s in text.replace('\n', ' ').split('。') if s.strip()]
    if len(sentences) <= 3:
        return text
    return "。\n".join(sentences[:3]) + "。"
