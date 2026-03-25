# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
pip install -r requirements.txt && pip install -e .

# Run all tests (138 tests, zero API calls, ~5 seconds)
pytest tests/ -v

# Run a single test file
pytest tests/test_orchestrator.py -v

# Run the agent (ad-hoc)
research-report research "Your topic here"
research-report research "AI trends" --email boss@company.com --dry-run

# Start scheduled runner
research-report scheduler start

# Resume an incomplete run
research-report resume
```

## Architecture

**Flow:** CLI → Orchestrator → N parallel Researchers → Synthesizer → PDF Formatter → Approval Gate → Email

```
src/
├── main.py                  # Click CLI: research / scheduler / resume commands
├── agents/
│   ├── orchestrator.py      # Decomposes topic into subtopics; dispatches parallel researchers
│   ├── researcher.py        # Per-subtopic: web search + NotebookLM + LLM synthesis
│   └── synthesizer.py       # Merges findings into final report text + title
├── tools/
│   ├── web_search.py        # Tavily API wrapper
│   └── notebooklm_reader.py # NotebookLM via MCP browser automation
├── pdf/
│   ├── formatter.py         # ReportLab: text, tables, charts, images → PDF
│   └── translator.py        # Multi-language PDF translation (zh-CN, zh-TW)
├── delivery/
│   ├── email_sender.py      # Gmail via Composio OAuth bridge
│   └── approval.py          # Human-in-the-loop prompt (ad-hoc mode only)
├── config/config.py         # Loads config.yaml + .env; validates settings
├── log/
│   ├── logger.py            # Structured app + JSON audit logging
│   └── state.py             # JSON state files: master-{run_id}.json + subtopic-{idx}-{run_id}.json
└── run/
    ├── preflight.py         # Validates network, API keys, Gmail connection before running
    ├── scheduler.py         # APScheduler cron runner (scheduled mode, no approval gate)
    └── resume.py            # Discovers incomplete runs and offers retry
```

**Key design decisions:**

- **Model-agnostic via LiteLLM:** All LLM calls use `litellm.completion()`. Default model is `claude-sonnet-4-6`, changeable in `config.yaml`.
- **Parallel research:** `ThreadPoolExecutor` with one worker per subtopic. Each agent writes its own state file — no locking needed.
- **Non-fatal PDF failures:** Chart/image rendering errors produce grey placeholder boxes instead of crashing the run.
- **Structured error codes:** All errors are `[ERR-{CATEGORY}-{CODE}]` (e.g. `[ERR-AUTH-002]`, `[ERR-NET-001]`). See `docs/plans/research-to-report-design-v1.md` for the full table.
- **Rate-limit retry:** LLM calls retry 3 times with 15/30/60 s backoff on rate-limit errors.
- **Audit trail:** Append-only JSON-lines log of key events (RUN_STARTED, EMAIL_SENT, etc.).

## Configuration

Copy `config.yaml.example` → `config.yaml` and `.env.example` → `.env`.

Required env vars: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `COMPOSIO_API_KEY`.

Key config settings in `config.yaml`:
- `agent.default_model` — LiteLLM model string
- `agent.max_subtopics` — number of parallel research agents
- `schedule.enabled` / `schedule.cron` — APScheduler cron (e.g. `"0 8 * * MON"`)
- `notebooklm.notebook_ids` — leave empty to skip NotebookLM (uses Chrome browser session)
- `timeouts.*` — per-phase timeouts in seconds

## Testing

All 138 tests mock every external call (Tavily, Composio, LiteLLM, urllib). No API keys required to run tests.

Pattern: patch at the module-import boundary (e.g. `patch("src.agents.researcher.litellm.completion")`).

Known test workaround: when `asyncio.run()` is mocked, the coroutine argument must be closed explicitly to suppress GC warnings. See `tests/test_tools.py:78-90`.

## Known SDK Workaround

`composio` v1.0.0rc10 has a bug where `tools.execute()` raises `KeyError` on non-custom tools. Workaround in `src/delivery/email_sender.py:57-67` pre-populates `_tool_schemas` to bypass the broken code path. Do not remove.

## Documentation

Design and implementation details live in `docs/plans/`. Update these files whenever architecture or module interfaces change.
