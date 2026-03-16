"""
notebooklm_reader.py — Query a NotebookLM notebook via the notebooklm-mcp-cli MCP server.

The MCP server controls a Chrome browser session logged into NotebookLM.
No API key or Google service account is required — authentication is handled
by the saved Chrome browser session managed by notebooklm-mcp-cli.

Setup:
    Install:  uvx install notebooklm-mcp-cli
    Login:    notebooklm-mcp-cli auth login
    The MCP server starts automatically when query_notebook() is called.

Notebook UUID:
    Found in the NotebookLM URL:
    https://notebooklm.google.com/notebooklm?notebook=<UUID>
"""
import asyncio
import base64
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools.web_search import ToolError

# Command used to launch the notebooklm-mcp-cli MCP server.
# Requires `uvx` to be in PATH (installed with uv).
_MCP_COMMAND = "uvx"
_MCP_ARGS = ["notebooklm-mcp-cli"]


async def _query_async(notebook_id: str, query: str) -> dict:
    server_params = StdioServerParameters(command=_MCP_COMMAND, args=_MCP_ARGS)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "notebook_query",
                {"notebook_id": notebook_id, "query": query},
            )

    if not result.content:
        raise ToolError(f"[ERR-NTB-002] No readable sources in notebook: {notebook_id}")

    raw = result.content[0].text
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = {"answer": raw}

    if data.get("status") == "error":
        raise ToolError(
            f"[ERR-NTB-003] NotebookLM MCP error for notebook {notebook_id}: "
            f"{data.get('error', raw)}"
        )

    answer = data.get("answer", raw)
    if not answer:
        raise ToolError(f"[ERR-NTB-002] No readable sources in notebook: {notebook_id}")

    return {"name": f"NotebookLM ({notebook_id[:8]}...)", "content": answer}


def query_notebook(notebook_id: str, query: str) -> dict:
    """Query a NotebookLM notebook via the notebooklm-mcp-cli MCP server.

    Spawns the MCP server as a subprocess, sends the query to NotebookLM's AI,
    and returns a synthesized answer grounded in the notebook's sources.

    :param notebook_id: NotebookLM notebook UUID (from the URL)
    :param query: Question to ask — typically the research subtopic
    :return: {"name": str, "content": str} with the AI-synthesized answer
    :raises ToolError: NTB-001 if notebook not found, NTB-002 if no sources,
                       NTB-003 if the MCP server errors or is unreachable
    """
    try:
        return asyncio.run(_query_async(notebook_id, query))
    except ToolError:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or "invalid" in msg or "404" in msg:
            raise ToolError(
                f"[ERR-NTB-001] NotebookLM notebook not found: {notebook_id} — {e}"
            )
        raise ToolError(f"[ERR-NTB-003] NotebookLM MCP server error: {e}")


async def _fetch_image_async(notebook_id: str, filename: str) -> bytes | None:
    server_params = StdioServerParameters(command=_MCP_COMMAND, args=_MCP_ARGS)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "source_get_content",
                {"notebook_id": notebook_id, "source_name": filename},
            )
    if not result.content:
        return None
    try:
        return base64.b64decode(result.content[0].text)
    except Exception:
        return None


def fetch_notebook_image(notebook_id: str, filename: str) -> bytes | None:
    """Attempt to fetch raw image bytes from a NotebookLM notebook source via MCP.

    Returns None if unsupported, not found, or any error — never raises.
    The notebooklm-mcp-cli server may not support image extraction;
    callers must handle None by rendering a placeholder.
    """
    try:
        return asyncio.run(_fetch_image_async(notebook_id, filename))
    except Exception:
        return None
