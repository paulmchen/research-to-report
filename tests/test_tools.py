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


def test_notebooklm_reader_unwraps_exception_group_to_ntb003():
    """ExceptionGroup from asyncio TaskGroup must be unwrapped; inner error message used."""
    from tools.notebooklm_reader import query_notebook, ToolError

    inner = Exception("MCP server connection failed")
    eg = ExceptionGroup("unhandled errors in a TaskGroup", [inner])

    with patch("asyncio.run", side_effect=eg):
        with pytest.raises(ToolError, match="ERR-NTB-003") as exc_info:
            query_notebook("nb-id", "query")
    # The error message must reflect the inner exception, not the ExceptionGroup wrapper
    assert "MCP server connection failed" in str(exc_info.value)
    assert "TaskGroup" not in str(exc_info.value)


def test_notebooklm_reader_unwraps_exception_group_to_ntb001():
    """ExceptionGroup wrapping a 'not found' error must map to ERR-NTB-001."""
    from tools.notebooklm_reader import query_notebook, ToolError

    inner = Exception("notebook not found: bad-id")
    eg = ExceptionGroup("unhandled errors in a TaskGroup", [inner])

    with patch("asyncio.run", side_effect=eg):
        with pytest.raises(ToolError, match="ERR-NTB-001"):
            query_notebook("bad-id", "query")


def test_unwrap_exception_group_returns_innermost():
    """_unwrap_exception_group must recurse through nested ExceptionGroups."""
    from tools.notebooklm_reader import _unwrap_exception_group

    innermost = ValueError("real error")
    mid = ExceptionGroup("mid", [innermost])
    outer = ExceptionGroup("outer", [mid])

    result = _unwrap_exception_group(outer)
    assert result is innermost


def test_verify_notebooklm_auth_skips_when_no_ids():
    """verify_notebooklm_auth must be a no-op when given an empty list."""
    from tools.notebooklm_reader import verify_notebooklm_auth
    with patch("asyncio.run") as mock_run:
        verify_notebooklm_auth([])
    mock_run.assert_not_called()


def test_verify_notebooklm_auth_passes_when_ping_succeeds():
    """verify_notebooklm_auth must not raise when asyncio.run returns without error."""
    from tools.notebooklm_reader import verify_notebooklm_auth
    with patch("asyncio.run", return_value=None):
        verify_notebooklm_auth(["nb-uuid-1"])  # should not raise


def test_verify_notebooklm_auth_raises_auth_error_on_expired_session():
    """verify_notebooklm_auth must raise ERR-AUTH-009 when ping detects auth expiry."""
    from tools.notebooklm_reader import verify_notebooklm_auth, ToolError
    expired = ToolError("[ERR-AUTH-009] NotebookLM authentication expired. Run 'nlm login'...")
    with patch("asyncio.run", side_effect=expired):
        with pytest.raises(ToolError, match="ERR-AUTH-009") as exc_info:
            verify_notebooklm_auth(["nb-uuid-1"])
    assert "nlm login" in str(exc_info.value)


def test_verify_notebooklm_auth_raises_ntb003_on_server_failure():
    """verify_notebooklm_auth must raise ERR-NTB-003 on MCP startup failure."""
    from tools.notebooklm_reader import verify_notebooklm_auth, ToolError
    with patch("asyncio.run", side_effect=Exception("Connection refused")):
        with pytest.raises(ToolError, match="ERR-NTB-003"):
            verify_notebooklm_auth(["nb-uuid-1"])


def test_verify_notebooklm_auth_unwraps_exception_group_auth_error():
    """An ExceptionGroup wrapping an auth error must surface as ERR-AUTH-009."""
    from tools.notebooklm_reader import verify_notebooklm_auth, ToolError

    inner = Exception("Authentication expired. Please re-authenticate.")
    eg = ExceptionGroup("unhandled errors in a TaskGroup", [inner])

    with patch("asyncio.run", side_effect=eg):
        with pytest.raises(ToolError, match="ERR-AUTH-009"):
            verify_notebooklm_auth(["nb-uuid-1"])
