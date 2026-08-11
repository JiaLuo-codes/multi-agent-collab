"""工具定义 —— 联网搜索"""
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults


@tool
def web_search(query: str) -> str:
    """联网搜索，获取最新信息。输入搜索关键词，返回相关结果摘要（含标题、摘要和链接）。"""
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
