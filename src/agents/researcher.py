import os
import threading
import time

from log.logger import write_audit
from log.state import create_subtopic_state, update_subtopic_state, update_heartbeat
from tools.web_search import web_search
from tools.notebooklm_reader import query_notebook

import litellm

litellm.suppress_debug_info = True  # silence "Give Feedback / Get Help" footer spam

_DRY_RUN_STUB = "## [DRY RUN] Stub Findings\n\nThis is a dry-run result. No API calls were made."

# Retry settings for rate limit errors
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BACKOFF = [15, 30, 60]  # seconds to wait before each retry


class LLMError(Exception):
    pass


def litellm_complete(model: str, messages: list[dict], max_tokens: int) -> str:
    for attempt, wait in enumerate([0] + _RATE_LIMIT_BACKOFF):
        if wait:
            time.sleep(wait)
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except litellm.exceptions.AuthenticationError:
            raise LLMError("[ERR-AUTH-002] Invalid or missing API key. Check your .env file.")
        except litellm.exceptions.BadRequestError as e:
            msg = str(e).lower()
            if "credit" in msg or "billing" in msg or "balance" in msg:
                raise LLMError(
                    "[ERR-AUTH-002] Anthropic API credit balance too low.\n"
                    "         → Add credits at: console.anthropic.com → Plans & Billing"
                )
            raise LLMError(f"[ERR-AUTH-007] Model '{model}' returned a bad request error: {e}")
        except litellm.exceptions.RateLimitError:
            if attempt < _RATE_LIMIT_RETRIES:
                continue  # wait and retry
            raise LLMError("[ERR-AUTH-005] API rate limit exceeded. Wait a moment and try again.")
        except litellm.exceptions.APIConnectionError:
            raise LLMError("[ERR-NET-002] Could not reach the Anthropic API. Check your internet connection.")
        except Exception as e:
            raise LLMError(f"[LLM] Unexpected error from model '{model}': {e}")


def _heartbeat_loop(run_id: str, idx: int, state_dir: str, stop_event: threading.Event):
    while not stop_event.wait(10):
        try:
            update_heartbeat(run_id, idx, state_dir)
        except Exception:
            pass


def run_research_agent(
    run_id: str,
    subtopic_idx: int,
    subtopic: str,
    cfg: dict,
    state_dir: str,
    dry_run: bool = False,
) -> str:
    create_subtopic_state(run_id, subtopic_idx, subtopic, state_dir)

    if dry_run:
        update_subtopic_state(run_id, subtopic_idx, state_dir, {
            "status": "COMPLETED", "result": _DRY_RUN_STUB,
            "completed_at": None,
        })
        return _DRY_RUN_STUB

    stop_event = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(run_id, subtopic_idx, state_dir, stop_event),
        daemon=True,
    )
    heartbeat_thread.start()

    audit_path = cfg.get("audit", {}).get("log_file")

    def _audit(data: dict) -> None:
        if audit_path:
            write_audit(audit_path, {"run_id": run_id, "subtopic_idx": subtopic_idx, **data})

    try:
        model = cfg["agent"]["default_model"]
        max_tokens = cfg["agent"].get("max_tokens", 8096)
        notebook_ids = cfg.get("notebooklm", {}).get("notebook_ids", [])
        api_key = os.environ.get("TAVILY_API_KEY")

        # Web search — always
        query = f"{subtopic} latest research 2026"
        web_results = web_search(query, api_key=api_key)
        _audit({"event": "WEB_SEARCH", "subtopic": subtopic,
                "query": query, "results_count": len(web_results)})
        sources_text = "\n\n".join(
            f"**{r['title']}** ({r['url']})\n{r['content']}" for r in web_results
        )

        # NotebookLM — only if configured
        if notebook_ids:
            notebook_sections = []
            for notebook_id in notebook_ids:
                try:
                    result = query_notebook(notebook_id, subtopic)
                    notebook_sections.append(f"**{result['name']}** (NotebookLM)\n{result['content']}")
                    _audit({"event": "NOTEBOOKLM_QUERY", "notebook_id": notebook_id,
                            "subtopic": subtopic})
                except Exception as e:
                    _audit({"event": "NOTEBOOKLM_QUERY_FAILED", "notebook_id": notebook_id,
                            "subtopic": subtopic, "error": str(e)})
            if notebook_sections:
                sources_text += "\n\n" + "\n\n".join(notebook_sections)

        # Synthesize findings with LLM
        prompt = (
            f"You are a research analyst. Based on the following sources, write a thorough "
            f"markdown research brief on: **{subtopic}**\n\n"
            f"Sources:\n{sources_text}\n\n"
            f"Write in professional tone. Include key findings, statistics, and insights."
        )
        findings = litellm_complete(model, [{"role": "user", "content": prompt}], max_tokens)

        update_subtopic_state(run_id, subtopic_idx, state_dir, {
            "status": "COMPLETED",
            "result": findings,
            "completed_at": None,
        })
        return findings

    except Exception as e:
        update_subtopic_state(run_id, subtopic_idx, state_dir, {
            "status": "FAILED",
            "error": str(e),
        })
        raise
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=1)
