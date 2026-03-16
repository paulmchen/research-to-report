import pytest
from unittest.mock import patch, MagicMock


def test_web_search_returns_results():
    from tools.web_search import web_search
    mock_response = {
        "results": [
            {"title": "Article 1", "url": "https://example.com/1", "content": "Content 1"},
            {"title": "Article 2", "url": "https://example.com/2", "content": "Content 2"},
        ]
    }
    with patch("tools.web_search.TavilyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        mock_cls.return_value = mock_client
        results = web_search("AI healthcare trends", api_key="test-key")
    assert len(results) == 2
    assert results[0]["title"] == "Article 1"
    assert results[0]["url"] == "https://example.com/1"


def test_web_search_raises_on_quota_exceeded():
    from tools.web_search import web_search, ToolError
    with patch("tools.web_search.TavilyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("quota exceeded")
        mock_cls.return_value = mock_client
        with pytest.raises(ToolError, match="ERR-AUTH-005"):
            web_search("topic", api_key="test-key")


def test_web_search_raises_on_invalid_key():
    from tools.web_search import web_search, ToolError
    with patch("tools.web_search.TavilyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("invalid api key")
        mock_cls.return_value = mock_client
        with pytest.raises(ToolError, match="ERR-AUTH-003"):
            web_search("topic", api_key="bad-key")


def test_notebooklm_reader_returns_sources():
    from tools.notebooklm_reader import query_notebook
    expected = {"name": "NotebookLM (notebook1...)", "content": "Synthesized answer about AI trends"}
    with patch("asyncio.run", return_value=expected):
        result = query_notebook("notebook1-uuid", "AI trends")
    assert "NotebookLM" in result["name"]
    assert result["content"] == "Synthesized answer about AI trends"


def test_notebooklm_reader_raises_on_not_found():
    from tools.notebooklm_reader import query_notebook, ToolError
    with patch("asyncio.run", side_effect=Exception("notebook not found")):
        with pytest.raises(ToolError, match="ERR-NTB-001"):
            query_notebook("bad-notebook-id", "query")


def test_notebooklm_reader_raises_on_permission_denied():
    from tools.notebooklm_reader import query_notebook, ToolError
    with patch("asyncio.run", side_effect=Exception("MCP server connection failed")):
        with pytest.raises(ToolError, match="ERR-NTB-003"):
            query_notebook("notebook-id", "query")


def test_fetch_notebook_image_returns_none_on_error():
    """Any MCP error must return None — never raise."""
    from tools.notebooklm_reader import fetch_notebook_image
    with patch("asyncio.run", side_effect=Exception("MCP server error")):
        result = fetch_notebook_image("nb-id", "diagram.png")
    assert result is None


def test_fetch_notebook_image_returns_bytes_on_success():
    """When asyncio.run returns bytes (mocked), propagate them."""
    from tools.notebooklm_reader import fetch_notebook_image
    fake_bytes = b'\x89PNG\r\n' + b'\x00' * 20
    with patch("asyncio.run", return_value=fake_bytes):
        result = fetch_notebook_image("nb-id", "diagram.png")
    assert result == fake_bytes
