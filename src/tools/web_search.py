import os
from tavily import TavilyClient


class ToolError(Exception):
    pass


def web_search(query: str, api_key: str = None, max_results: int = 5) -> list[dict]:
    key = api_key or os.environ.get("TAVILY_API_KEY")
    if not key:
        raise ToolError("[ERR-AUTH-003] TAVILY_API_KEY not set")

    try:
        client = TavilyClient(api_key=key)
        response = client.search(query, max_results=max_results)
    except Exception as e:
        msg = str(e).lower()
        if "quota" in msg or "limit" in msg:
            raise ToolError(f"[ERR-AUTH-005] Tavily quota exceeded: {e}")
        if "invalid" in msg or "unauthorized" in msg or "api key" in msg:
            raise ToolError(f"[ERR-AUTH-003] Invalid or expired Tavily API key: {e}")
        raise ToolError(f"[ERR-NET-003] Tavily API unreachable: {e}")

    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in response.get("results", [])
    ]
