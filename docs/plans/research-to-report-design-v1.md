# Research-to-Report Agent — Design Document

**Date:** 2026-03-12
**Status:** Approved
**Language:** Python
**SDK:** LiteLLM (model-agnostic — supports Claude, Gemini, GPT, and more)
**Default Model:** claude-sonnet-4-6 (configurable)

---

## 1. Overview

An autonomous Research-to-Report agent that accepts a topic, spawns parallel research sub-agents to gather information from web search and NotebookLM sources, synthesizes findings into a professional PDF report, and delivers it via email. Supports both on-demand (ad-hoc) and scheduled runs with configurable human-in-the-loop approval.

---

## 2. Trigger Modes

| Mode | Description | Approval Gate |
|---|---|---|
| **Ad-hoc** | User runs CLI with a topic manually | Yes — preview + y/n/edit before email |
| **Scheduled** | APScheduler fires on cron schedule | No — fully automated |

**CLI usage:**
```bash
# Ad-hoc (human approval before email)
research-report research "AI trends in healthcare"

# Ad-hoc with recipients
research-report research "AI trends" --email boss@company.com,analyst@company.com

# Ad-hoc with CC
research-report research "AI trends" --email boss@company.com --email-cc reviewer@company.com,manager@company.com

# Start scheduler (runs automated on cron)
research-report scheduler start

# Resume an incomplete run
research-report resume

# Dry run (no API calls — for testing)
research-report research "AI trends" --dry-run

# Override log level
research-report research "AI trends" --log-level DEBUG
```

The `research-report` binary is installed via:
```bash
pip install -r requirements.txt
pip install -e .
```

If the command is not found after installing, the pip Scripts/bin directory is not on PATH. Add it once:

| OS | Default Scripts/bin location | Fix |
|---|---|---|
| Windows | `%APPDATA%\Python\Python3XX\Scripts` | Add to user PATH via System Properties or PowerShell `[Environment]::SetEnvironmentVariable(...)` |
| macOS | `~/Library/Python/3.X/bin` | Add `export PATH="$HOME/Library/Python/3.X/bin:$PATH"` to `~/.zshrc` |
| Linux | `~/.local/bin` | Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` |

Running `python src/main.py <command>` works as a direct alternative without installing.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Entry Points                      │
│   CLI (ad-hoc)          Scheduler (APScheduler)     │
└──────────────┬──────────────────┬───────────────────┘
               └────────┬─────────┘
                        ↓
           ┌────────────────────────┐
           │   Orchestrator Agent   │
           │  - pre-flight checks   │
           │  - breaks topic into   │
           │    N subtopics         │
           │  - spawns sub-agents   │
           │  - monitors heartbeats │
           │  - collects results    │
           └────────────┬───────────┘
                        ↓ (parallel — see Section 6)
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
  Research Agent  Research Agent  Research Agent
  (subtopic 1)    (subtopic 2)    (subtopic N)
     ├─ web_search   ├─ web_search   ├─ web_search
     └─ notebooklm   └─ notebooklm   └─ notebooklm
        ↓               ↓               ↓
        └───────────────┼───────────────┘
                        ↓
           ┌────────────────────────┐
           │    Synthesis Agent     │
           │  - executive summary   │
           │  - full report body    │
           │  - professional tone   │
           └────────────┬───────────┘
                        ↓
               PDF Formatter (ReportLab)
                        ↓
            ┌───────────────────────┐
            │  Human-in-the-Loop?   │
            │  ad-hoc  → YES        │
            │  scheduled → SKIP     │
            └───────────┬───────────┘
                        ↓
         Gmail Delivery + Local File Save
```

---

## 4. Project Structure

```
research-to-report/
├── .env                          # API keys (never committed to git)
├── .env.example                  # Template for .env
├── config.yaml                   # Topics, schedule, email, notebook IDs
├── requirements.txt
├── pyproject.toml                # Package config: CLI entry point + pytest pythonpath
├── README.md
│
├── src/
│   ├── main.py                       # CLI entry point (research / scheduler / resume commands)
│   ├── agents/                       # AI research pipeline agents
│   │   ├── orchestrator.py           # topic decomposition + parallel sub-agent dispatch
│   │   ├── researcher.py             # research sub-agent: web search + NotebookLM + LLM synthesis
│   │   └── synthesizer.py           # final report synthesis agent
│   ├── tools/                        # External tool integrations
│   │   ├── web_search.py             # Tavily web search
│   │   └── notebooklm_reader.py     # NotebookLM MCP client (query + image fetch)
│   ├── pdf/                          # PDF generation and translation
│   │   ├── formatter.py              # ReportLab PDF formatter (text, tables, charts, images)
│   │   └── translator.py            # translate existing PDF to zh-CN / zh-TW
│   ├── delivery/                     # Report delivery
│   │   ├── email_sender.py          # Gmail delivery via Composio
│   │   └── approval.py              # human-in-the-loop approval prompt
│   ├── config/                       # Configuration
│   │   └── config.py                # YAML config loading and validation
│   ├── log/                          # Logging and state management
│   │   ├── logger.py                # structured logging + audit log writer
│   │   └── state.py                 # run state file read/write (master + subtopic)
│   └── run/                          # Execution control
│       ├── scheduler.py             # APScheduler cron runner
│       ├── resume.py                # resume UI (display summary, choose option)
│       └── preflight.py            # startup validation (network, API keys, dirs, emails)
│
├── reports/                      # Generated PDFs
│   ├── logs/
│   │   ├── agent.log             # Application log (configurable level)
│   │   └── audit.log             # Audit log (always on, append-only JSON)
│   └── state/                    # Run state files for resume
│       └── archive/              # Completed run states
│
├── docs/
│   └── plans/                    # Design docs + implementation plans
│
└── tests/
    ├── test_orchestrator.py
    ├── test_researcher.py
    ├── test_synthesizer.py
    └── test_tools.py
```

---

## 5. Tools & Integrations

| Tool | Purpose | Library/API |
|---|---|---|
| `web_search` | Research sub-agents search the web | Tavily API (1,000 free credits/month) |
| `notebooklm_reader` | Query sources from NotebookLM notebooks (**optional** — only used when `notebooklm.notebook_ids` is non-empty) | notebooklm-mcp-cli (MCP, browser automation via Chrome) |
| `pdf_generator` | Render professional PDF report with text, tables, charts, and images | ReportLab (platypus + graphics) |
| `chart_renderer` | Render bar, hbar, line, pie, stacked_bar charts inline in PDF | ReportLab graphics (native — no extra dependency) |
| `image_embedder` | Embed images from web URLs, local files, or NotebookLM sources inline in PDF | urllib.request (stdlib), notebooklm-mcp-cli |
| `email_sender` | Send report via Gmail | Composio Gmail MCP |
| `file_saver` | Save PDF to local output folder | Python stdlib |

**Tavily credit estimate:** ~14–28 credits per report → 35–71 reports/month on free tier.

---

## 6. Sub-Agent Execution Modes

### v1 — Mode 1: Fully Parallel (Initial Implementation)

All sub-agents run simultaneously, completely independent. Fastest execution.

```
Orchestrator
  ├── Sub-agent 1 (subtopic A)  ─┐
  ├── Sub-agent 2 (subtopic B)  ─┤  all run simultaneously
  ├── Sub-agent 3 (subtopic C)  ─┤
  └── Sub-agent 4 (subtopic D)  ─┘
       ↓ all complete (or timed out)
  Orchestrator collects results → Synthesis Agent
```

- Best for: independent subtopics
- Sub-agents never read peer state files
- Zero contention guaranteed

---

### Future Enhancement — Mode 2: Sequential with Context Passing

Each sub-agent receives prior agents' completed findings as context before starting. Produces richer, more coherent research.

```
Orchestrator
  └── Sub-agent 1 (subtopic A)
        ↓ result passed as context
  └── Sub-agent 2 (subtopic B — informed by agent 1)
        ↓ result passed as context
  └── Sub-agent 3 (subtopic C — informed by agents 1+2)
        ↓ result passed as context
  └── Sub-agent 4 (subtopic D — informed by agents 1+2+3)
        ↓
  Synthesis Agent
```

- Best for: deeply related subtopics requiring narrative continuity
- Slower — each waits for previous to complete

---

### Future Enhancement — Mode 3: Hybrid Parallel Waves

Sub-agents run in parallel waves. Wave 2 is informed by Wave 1 results, balancing speed and context richness.

```
Wave 1 (parallel):  Sub-agent 1, Sub-agent 2
                         ↓ both complete
Wave 2 (parallel):  Sub-agent 3, Sub-agent 4  ← informed by wave 1
                         ↓ both complete
Synthesis Agent
```

- Best for: balance of speed and coherence
- Sub-agents may only READ peers with status `COMPLETED` — never `IN_PROGRESS`

**Safe cross-read rules (Modes 2 & 3):**
- Sub-agents may only READ peer state files, never write them
- Sub-agents may only read peers with status `COMPLETED`
- Orchestrator controls launch sequencing — guarantees peers are complete before dependent agents start

---

## 7. State Management & Resume

### State File Ownership (Zero Contention Design)

Each sub-agent owns its own state file exclusively. The orchestrator owns the master state file. No file locking required by default.

```
reports/state/
├── {run_id}-master.json          ← orchestrator writes only
├── {run_id}-subtopic-1.json      ← sub-agent 1 writes only
├── {run_id}-subtopic-2.json      ← sub-agent 2 writes only
├── {run_id}-subtopic-3.json      ← sub-agent 3 writes only
└── {run_id}-subtopic-4.json      ← sub-agent 4 writes only
```

| File | Writer | Readers |
|---|---|---|
| `master.json` | Orchestrator only | Resume CLI, logging |
| `subtopic-N.json` | Sub-agent N only | Orchestrator (polling, read-only) |
| `audit.log` | Append-only (safe) | User, resume CLI |
| `agent.log` | Python logging (thread-safe) | User |

File locking (`filelock` library) included as optional safety net for future multi-orchestrator scenarios.

### Master State File Structure

```json
{
  "run_id": "2026-03-12T08-00-01",
  "topic": "AI trends in healthcare",
  "mode": "scheduled",
  "status": "IN_PROGRESS",
  "started_at": "2026-03-12T08:00:01Z",
  "last_updated": "2026-03-12T08:01:23Z",
  "subtopics": [
    {
      "id": 1,
      "topic": "market trends",
      "status": "COMPLETED",
      "started_at": "2026-03-12T08:00:03Z",
      "completed_at": "2026-03-12T08:00:11Z",
      "result_file": "state/{run_id}-subtopic-1.md"
    },
    {
      "id": 3,
      "topic": "regulation",
      "status": "TIMED_OUT",
      "started_at": "2026-03-12T08:00:03Z",
      "completed_at": null,
      "error": "RES-001",
      "result_file": null
    }
  ],
  "synthesis": { "status": "PENDING", "result_file": null },
  "pdf": { "status": "PENDING", "file": null },
  "email": { "status": "PENDING", "sent_at": null }
}
```

### Sub-Agent Heartbeat

Each sub-agent updates `last_heartbeat` in its own state file every 10 seconds. The orchestrator monitors heartbeats and cancels stuck processes:

```
08:00:03  [Sub-agent 3 | topic: "regulation" | PID: 4821] started        last_heartbeat: 08:00:03
08:00:13  [Sub-agent 3 | topic: "regulation" | PID: 4821] searching...   last_heartbeat: 08:00:13
08:00:33  [Sub-agent 3 | topic: "regulation" | PID: 4821] STUCK          last_heartbeat: 08:00:33
...
08:02:33  ERROR [ERR-RES-001] Sub-agent 3 (topic: "regulation" | PID: 4821) — no heartbeat for 120s — process cancelled.
          Resume with: python src/main.py resume
```

### Resume Flow

```
$ python src/main.py resume

Finding incomplete runs...
  Found: 2026-03-12T08-00-01 — "AI trends in healthcare" (IN_PROGRESS)

Run summary:
  ✓ Subtopic 1: market trends     — completed
  ✓ Subtopic 2: key players       — completed
  ✗ Subtopic 3: regulation        — timed out [ERR-RES-001]
  ✓ Subtopic 4: future outlook    — completed
  ○ Synthesis                     — pending
  ○ PDF generation                — pending
  ○ Email delivery                — pending

Resume options:
  [1] Retry failed subtopic 3, then continue
  [2] Skip subtopic 3, continue with 3/4 completed subtopics
  [3] Restart entire run from scratch
  [4] Abort and discard

Choice: _
```

### Pipeline Resume Points

| Stage | Resumable | Notes |
|---|---|---|
| Topic decomposition | Yes | Re-run if state missing |
| Research (parallel) | Yes | Skip completed, retry failed |
| Synthesis | Yes | Re-run if PDF not yet made |
| PDF generation | Yes | Re-run if email not yet sent |
| Human approval | Yes | Re-ask approval |
| Email delivery | **Check first** | Audit log checked — never send duplicate |

---

## 8. Report Format

- **Executive summary** at the top (1–2 pages): key findings + recommendations
- **Full report body** below: background, findings per subtopic, analysis, recommendations (5–10 pages)
- **Professional styling** via ReportLab: cover page, table of contents, section headers, page numbers, footer with run timestamp
- **Output:** All language PDFs saved to `reports/`. Only the English PDF is emailed — translated PDFs are available locally.
- **Charts & images:** The LLM places ` ```chart` JSON blocks and `![caption](src)` image references inline in the markdown. The PDF formatter renders them as native ReportLab flowables. Supported chart types: `bar`, `hbar`, `line`, `pie`, `stacked_bar`. Image sources: web URL, local file path, or `notebooklm://notebook-id/filename` URI. Any chart or image that cannot be rendered (invalid JSON, broken URL, unsupported NotebookLM source) is replaced with a visible grey placeholder box — PDF generation never aborts.

---

## 9. Human-in-the-Loop (Ad-hoc Mode)

```
Report ready: "AI trends in healthcare"

To:  you@gmail.com, team@company.com, boss@company.com
CC:  manager@company.com, reviewer@company.com
PDF: ./reports/ai-trends-in-healthcare-2026-03-14.pdf
PDF: ./reports/ai-trends-in-healthcare-2026-03-14-zh-CN.pdf

Send this report? [y/n/edit]: _
  → y:    English PDF emailed; all PDFs saved locally
  → n:    all PDFs saved locally only, no email
  → edit: open English PDF in default editor, re-confirm before sending
```

**Note:** The Composio Gmail API supports one attachment per send call. Only the English PDF is attached to the email. All translated PDFs are generated and saved to `reports/` and are available locally.

Scheduled runs skip this gate entirely.

---

## 10. Email Configuration

### `config.yaml` email section:
```yaml
email:
  default_recipients:
    - you@gmail.com
    - team@company.com
  default_cc:
    - manager@company.com   # optional
```

### CLI overrides (ad-hoc only):
```bash
# Comma-separated TO recipients
python src/main.py research "AI trends" --email boss@company.com,analyst@company.com

# With CC
python src/main.py research "AI trends" --email boss@company.com --email-cc reviewer@company.com,manager@company.com
```

### Merge & deduplication rules:
- Config recipients + CLI recipients merged
- Case-insensitive deduplication (`You@Gmail.com` == `you@gmail.com`)
- Config recipients listed first, CLI additions appended
- If same email appears in both TO and CC → kept in TO, removed from CC with warning
- Invalid emails caught at pre-flight with `EML-003`

```
TO  config:  [you@gmail.com, team@company.com]
TO  CLI:     [boss@company.com, you@gmail.com]   ← duplicate
CC  config:  [manager@company.com]
CC  CLI:     [reviewer@company.com]
                    ↓
final TO:    [you@gmail.com, team@company.com, boss@company.com]
final CC:    [manager@company.com, reviewer@company.com]
```

---

## 11. Configuration

### `config.yaml`
```yaml
user_email: you@gmail.com
output_dir: ./reports

agent:
  default_model: claude-sonnet-4-6    # used by all agents unless overridden
  max_tokens: 8096                    # covers full report generation (~6,000–7,000 tokens for synthesis)
  max_subtopics: 5                    # number of parallel research agents to spawn (default: 5)

  # optional per-agent overrides — only specify if different from default_model
  # orchestrator_model: claude-opus-4-6
  # orchestrator_max_tokens: 1024
  # researcher_model: claude-haiku-4-5-20251001
  # researcher_max_tokens: 3000
  # synthesizer_model: claude-opus-4-6
  # synthesizer_max_tokens: 8096

email:
  default_recipients:
    - you@gmail.com
  default_cc: []

schedule:
  enabled: true
  cron: "0 8 * * MON"        # every Monday at 8am
  timezone: "America/New_York"
  topics:
    - "AI industry news"
    - "Cybersecurity threats this week"

# Report language versions. Supported: en, zh-CN, zh-TW
# en is always generated. Add zh-CN / zh-TW for translated PDFs.
languages:
  - en
  - zh-CN    # Simplified Chinese (mainland China)
  - zh-TW    # Traditional Chinese (Taiwan)

notebooklm:
  notebook_ids:              # leave empty ([]) to use web search only; no credentials needed
    - "your-notebooklm-notebook-uuid"   # UUID from the NotebookLM URL

timeouts:
  sub_agent_sec: 120
  synthesis_sec: 180
  pdf_generation_sec: 60
  email_delivery_sec: 30
  total_run_sec: 600

logging:
  level: INFO                 # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_to_file: true
  log_file: reports/logs/agent.log
  max_file_size_mb: 10
  backup_count: 5

audit:
  enabled: true               # always true — cannot be disabled
  log_file: reports/logs/audit.log
  format: json
```

### `.env`
```
ANTHROPIC_API_KEY=...         # required if using Claude models
GOOGLE_API_KEY=...            # required if using Gemini models
OPENAI_API_KEY=...            # required if using GPT models
TAVILY_API_KEY=...            # required (web search)
COMPOSIO_API_KEY=...          # required (Gmail delivery via Composio)
LOG_LEVEL=INFO                # overrides config.yaml if set
```

NotebookLM authentication is handled by the `notebooklm-mcp-cli` MCP server, which uses a Chrome browser session. No API key or service account file is needed — you log in once via the browser and the session is saved locally.

**Log level priority:** CLI flag `--log-level` → ENV `LOG_LEVEL` → `config.yaml` → default `INFO`

---

## 12. Logging

### Application Log (`agent.log`)

| Level | Default | Purpose |
|---|---|---|
| DEBUG | Off | API payloads, sub-agent prompts, raw responses |
| INFO | On | Normal flow — run started, subtopics created, report saved |
| WARNING | On | Non-fatal — subtopic skipped, fallback to web-only |
| ERROR | On | Failures with error codes |
| CRITICAL | On | Fatal — process aborts |

Log rotation: 10MB max, 5 backups kept.

### Audit Log (`audit.log`) — Always On

Structured JSON, one entry per line, append-only. Records every external action:

```json
{"timestamp": "2026-03-12T08:00:01Z", "event": "RUN_STARTED", "mode": "scheduled", "topic": "AI trends in healthcare", "triggered_by": "scheduler"}
{"timestamp": "2026-03-12T08:00:03Z", "event": "WEB_SEARCH", "run_id": "2026-03-12T08-00-01", "subtopic_idx": 1, "subtopic": "AI healthcare market trends", "query": "AI healthcare market trends latest research 2026", "results_count": 5}
{"timestamp": "2026-03-12T08:00:05Z", "event": "WEB_SEARCH", "run_id": "2026-03-12T08-00-01", "subtopic_idx": 2, "subtopic": "regulatory landscape", "query": "regulatory landscape latest research 2026", "results_count": 4}
{"timestamp": "2026-03-12T08:00:10Z", "event": "NOTEBOOKLM_QUERY", "run_id": "2026-03-12T08-00-01", "subtopic_idx": 1, "notebook_id": "176a5e31-0401-4f09-9c89-4229c7d6a668", "subtopic": "AI healthcare market trends"}
{"timestamp": "2026-03-12T08:00:12Z", "event": "NOTEBOOKLM_QUERY_FAILED", "run_id": "2026-03-12T08-00-01", "subtopic_idx": 2, "notebook_id": "176a5e31-0401-4f09-9c89-4229c7d6a668", "subtopic": "regulatory landscape", "error": "[ERR-NTB-003] NotebookLM MCP server error: browser session expired"}
{"timestamp": "2026-03-12T08:00:45Z", "event": "REPORT_GENERATED", "filename": "2026-03-12-ai-healthcare.pdf", "size_kb": 284}
{"timestamp": "2026-03-12T08:00:46Z", "event": "APPROVAL_REQUESTED", "mode": "ad-hoc"}
{"timestamp": "2026-03-12T08:01:02Z", "event": "APPROVAL_DECISION", "decision": "approved", "wait_time_sec": 16}
{"timestamp": "2026-03-12T08:01:04Z", "event": "EMAIL_SENT", "to": ["you@gmail.com", "boss@company.com"], "cc": ["manager@company.com"], "to_from_config": ["you@gmail.com"], "to_from_cli": ["boss@company.com"], "cc_from_config": ["manager@company.com"], "cc_from_cli": [], "duplicates_removed": 0}
{"timestamp": "2026-03-12T08:01:04Z", "event": "RUN_COMPLETED", "duration_sec": 63, "status": "success"}
```

**Sub-agent audit events** (written by each research sub-agent):

| Event | Fields | When |
|---|---|---|
| `WEB_SEARCH` | `run_id`, `subtopic_idx`, `subtopic`, `query`, `results_count` | After every web search |
| `NOTEBOOKLM_QUERY` | `run_id`, `subtopic_idx`, `notebook_id`, `subtopic` | After a successful NotebookLM query |
| `NOTEBOOKLM_QUERY_FAILED` | `run_id`, `subtopic_idx`, `notebook_id`, `subtopic`, `error` | After a failed NotebookLM query (non-fatal — run continues) |

Audit log cannot be disabled. If `enabled: false` is set in config:
```
Warning [WRN-CFG-006]: Audit logging cannot be disabled. Agent actions will always be recorded.
```

---

## 13. Pre-flight Checks (Startup Validation Order)

```
1. Network connectivity          → fast-fail before anything else
2. API key validation            → ANTHROPIC_API_KEY, TAVILY_API_KEY, COMPOSIO_API_KEY always required; model-provider keys checked only if that model is configured
3. config.yaml validation        → cron format, timezone, required fields, supported languages
4. Output directory writable     → reports/, reports/logs/, reports/state/
5. Begin research
```

When `notebooklm.notebook_ids` is non-empty, the `notebooklm-mcp-cli` MCP server must already be running (started separately). No additional API key is required — authentication is via the Chrome browser session managed by the MCP server.

**Pre-flight output example:**
```
Checking network connectivity...
  ✓ Internet reachable
  ✓ Anthropic API reachable
  ✓ Tavily API reachable
  ✓ Google APIs reachable

Validating API keys...
  ✓ ANTHROPIC_API_KEY — valid  (required by claude-sonnet-4-6)
  - GOOGLE_API_KEY    — skipped (no Gemini models configured)
  - OPENAI_API_KEY    — skipped (no GPT models configured)

Validating config.yaml...
  ✓ Cron expression valid: "0 8 * * MON"
  ✓ Timezone valid: "America/New_York"
  ✓ All required fields present
```

---

## 14. Structured Message Codes

All non-routine log messages carry a structured prefix so they can be searched, alerted on, and cross-referenced:

| Prefix | Level | Meaning |
|---|---|---|
| `ERR-` | ERROR / CRITICAL | Hard failure — operation aborted |
| `WRN-` | WARNING | Actionable non-fatal issue — run continues with altered behaviour |
| *(free text)* | INFO / DEBUG | Normal flow messages — no code needed |

Format: `[PREFIX-CAT-NNN]` where CAT is the category and NNN is a three-digit number.

---

### ERR — Errors

#### NET — Network & Connectivity
| Code | Description |
|---|---|
| NET-001 | No internet connection |
| NET-002 | Anthropic API unreachable |
| NET-003 | Tavily API unreachable |
| NET-004 | Google APIs unreachable |
| NET-005 | Connection lost mid-run |

#### AUTH — Authentication
| Code | Description |
|---|---|
| AUTH-001 | Missing .env file |
| AUTH-002 | Invalid Anthropic API key |
| AUTH-003 | Invalid or expired Tavily API key |
| AUTH-004 | NotebookLM MCP server unreachable or not running |
| AUTH-005 | LLM API rate limit exceeded — automatically retried up to 3 times (15s / 30s / 60s backoff) before raising |
| AUTH-006 | LiteLLM provider API key missing for configured model |
| AUTH-007 | Configured model name not recognised by LiteLLM |
| AUTH-008 | COMPOSIO_API_KEY missing or no active Gmail connection in Composio |

#### CFG — Configuration
| Code | Description |
|---|---|
| CFG-001 | Missing config.yaml |
| CFG-002 | Invalid cron expression format |
| CFG-003 | Invalid cron field value |
| CFG-004 | Missing required config field |
| CFG-005 | Invalid timezone |
| CFG-007 | Unsupported language in `languages` list — only `en`, `zh-CN`, `zh-TW` supported |

#### RES — Research Sub-agents
| Code | Description |
|---|---|
| RES-001 | Sub-agent timed out (no heartbeat) |
| RES-002 | Sub-agent returned empty results |
| RES-003 | All subtopics failed |
| RES-004 | Sub-agent state file corrupted or missing |

#### SYN — Synthesis
| Code | Description |
|---|---|
| SYN-001 | Synthesis agent produced empty report |
| SYN-002 | Report below quality threshold |

#### PDF — PDF Generation
| Code | Description |
|---|---|
| PDF-001 | PDF generation failed |
| PDF-002 | Output directory not writable |

#### EML — Email Delivery
| Code | Description |
|---|---|
| EML-001 | Gmail authentication failed |
| EML-002 | Email delivery failed |
| EML-003 | Invalid recipient email address |
| EML-004 | Email already sent for this run — duplicate prevented |
| EML-005 | No recipients configured — set default_recipients in config.yaml or pass --email |

#### SCH — Scheduler
| Code | Description |
|---|---|
| SCH-001 | Scheduler failed to start |
| SCH-002 | Scheduled run failed — logged for retry |

#### NTB — NotebookLM (only raised when `notebooklm.notebook_ids` is non-empty)
| Code | Description |
|---|---|
| NTB-001 | NotebookLM notebook not found (invalid notebook UUID) |
| NTB-002 | No readable sources in notebook |
| NTB-003 | NotebookLM MCP server error (browser session may have expired — re-login required) |

#### STA — State Management
| Code | Description |
|---|---|
| STA-001 | State file cannot be written (disk full or permissions) |
| STA-002 | State file corrupted — cannot resume, must restart |
| STA-003 | No incomplete runs found to resume |
| STA-004 | Sub-agent heartbeat timeout — process assumed dead |
| STA-005 | File lock acquisition timeout on master.json |
| STA-006 | Subtopic state file missing — sub-agent may have crashed |

---

### WRN — Warnings

Warnings use the same category codes as errors but carry the `WRN-` prefix. Run continues after a warning with altered behaviour.

#### WRN-CFG — Configuration Warnings
| Code | Description |
|---|---|
| WRN-CFG-006 | Attempt to disable audit log — ignored, audit always stays on |

#### WRN-EML — Email Warnings
| Code | Description |
|---|---|
| WRN-EML-006 | Same email in both TO and CC — removed from CC, kept in TO |

**Error message format:**
```
[ERROR-CODE] <component> <identifier> (context) — <what happened> — <suggested action>

Example:
[ERR-RES-001] Sub-agent 3 (topic: "regulation" | PID: 4821) — no heartbeat for 120s — process cancelled.
          Resume with: python src/main.py resume
```

---

## 15. Error Handling Strategy

| Scenario | Strategy |
|---|---|
| No internet at startup | Pre-flight fails immediately with NET-001 |
| Internet drops mid-run | Save state, log NET-005, prompt resume |
| Invalid API key | Pre-flight fails with AUTH-00x, show fix hint |
| LLM rate limit mid-run | Auto-retry up to 3× with 15s/30s/60s backoff; raises AUTH-005 only if all retries exhausted |
| Sub-agent stuck | Heartbeat monitor cancels after timeout, marks TIMED_OUT |
| One sub-agent fails | Others continue, partial report generated with note |
| All sub-agents fail | RES-003, save state, prompt resume or restart |
| PDF generation fails | Save raw markdown as fallback |
| Invalid chart JSON or unknown type | Grey placeholder box rendered inline — PDF generation continues |
| Image URL unreachable / local file missing / NotebookLM unavailable | Grey placeholder box rendered inline — PDF generation continues |
| Email fails | PDF already saved locally, log EML-002 |
| Scheduled run offline | Log SCH-002, retry at next scheduled time |
| Duplicate email attempt | Check audit log first, skip with EML-004 |

---

## 16. Testing Strategy

### Philosophy

All unit tests make zero API calls — every external dependency is mocked. Integration tests use real APIs and consume Tavily credits. The dry-run mode provides a full end-to-end smoke test with zero credits.

```
Unit Tests (zero API calls — all mocked)
├── test_config.py       — configuration loading and validation
├── test_logger.py       — logging setup and audit log writing
├── test_state.py        — run state file read/write/heartbeat
├── test_preflight.py    — startup validation: network, API keys, email, dirs
├── test_orchestrator.py — topic decomposition and parallel sub-agent dispatch
├── test_researcher.py   — research sub-agent: web search, NotebookLM, dry run
├── test_synthesizer.py  — synthesis agent: prompt structure, output parsing
├── test_tools.py        — web search and NotebookLM MCP tools in isolation
├── test_pdf_formatter.py       — PDF file generation and structure
├── test_pdf_charts_images.py   — chart renderers, image fetch, placeholder fallback
├── test_email_sender.py — Composio Gmail delivery and duplicate prevention
├── test_approval.py     — human-in-the-loop approval prompt flow
├── test_scheduler.py    — cron validation and scheduler start/stop
├── test_resume.py       — resume UI display and option selection
└── test_main.py         — CLI commands exist and dry-run executes end-to-end

Integration Tests (real APIs — ~14 Tavily credits per run)
├── Full pipeline: topic → PDF saved to disk
├── NotebookLM reader against a real notebook via notebooklm-mcp-cli browser session
└── End-to-end: topic → PDF → email delivered via Composio Gmail

Dry-run Mode
└── Full pipeline with stub results (zero API calls, zero credits)
    Used during development to verify flow without consuming credits
```

### Unit Test Details

#### `tests/test_config.py`
| Test | Goal |
|---|---|
| `test_load_config_returns_dict` | Config YAML loads successfully and returns a dict |
| `test_missing_config_raises_cfg001` | Missing config file raises ERR-CFG-001 |
| `test_log_level_env_overrides_config` | `LOG_LEVEL` env var overrides config.yaml value |
| `test_audit_cannot_be_disabled` | Setting `audit.enabled: false` in config is silently ignored |

#### `tests/test_logger.py`
| Test | Goal |
|---|---|
| `test_get_agent_logger_uses_configured_level` | Logger respects log level set in config |
| `test_audit_log_writes_json_line` | `write_audit()` appends a valid JSON line to the audit file |
| `test_audit_log_appends_not_overwrites` | Multiple `write_audit()` calls append; file is not truncated |

#### `tests/test_state.py`
| Test | Goal |
|---|---|
| `test_create_master_state` | Master state file created with correct initial structure |
| `test_update_master_state` | Patches are applied and `last_updated` timestamp advances |
| `test_create_subtopic_state` | Subtopic state file created with status=IN_PROGRESS |
| `test_update_heartbeat` | `last_heartbeat` timestamp updated without altering other fields |
| `test_find_incomplete_runs` | Returns only runs with status=IN_PROGRESS |

#### `tests/test_preflight.py`
| Test | Goal |
|---|---|
| `test_preflight_passes_with_all_mocked` | Full preflight succeeds when all checks are mocked to pass |
| `test_invalid_email_raises_eml003` | Malformed email address raises ERR-EML-003 |
| `test_valid_emails_pass` | Well-formed addresses pass validation without error |
| `test_dedup_to_and_cc` | Address in both TO and CC is kept in TO and removed from CC |
| `test_no_recipients_raises_eml005` | Empty TO list raises ERR-EML-005 |
| `test_notebooklm_configured_no_google_credentials_needed` | NotebookLM via MCP requires no Google credentials |
| `test_composio_api_key_required` | Missing COMPOSIO_API_KEY raises ERR-AUTH-008 |

#### `tests/test_orchestrator.py`
| Test | Goal |
|---|---|
| `test_decompose_topic_returns_subtopics` | LLM output is parsed into a clean list of subtopic strings |
| `test_decompose_topic_respects_max_subtopics` | `agent.max_subtopics` config value controls the number of subtopics |
| `test_decompose_topic_handles_numbered_list` | Numbered list format (1. 2. 3.) is stripped correctly |
| `test_run_parallel_research_collects_results` | All subtopic results are collected into a dict keyed by subtopic |
| `test_run_parallel_research_continues_on_single_failure` | One failing sub-agent does not abort the others |
| `test_all_subtopics_fail_raises_res003` | All sub-agents failing raises ERR-RES-003 |

#### `tests/test_researcher.py`
| Test | Goal |
|---|---|
| `test_researcher_returns_markdown` | Sub-agent returns a non-empty markdown string |
| `test_researcher_skips_notebooklm_when_not_configured` | `notebook_ids: []` means NotebookLM is never called |
| `test_researcher_calls_notebooklm_when_configured` | Each configured notebook ID triggers one `query_notebook` call |
| `test_researcher_writes_state_file` | Sub-agent writes COMPLETED state with result to its state file |
| `test_researcher_dry_run_skips_api_calls` | `--dry-run` returns stub without calling web_search or LLM |

#### `tests/test_synthesizer.py`
| Test | Goal |
|---|---|
| `test_synthesize_returns_executive_summary_and_body` | Output dict contains both `executive_summary` and `full_report` keys |
| `test_synthesize_dry_run_returns_stub` | `dry_run=True` returns stub strings without calling LLM |
| `test_synthesize_empty_result_raises_syn001` | Empty LLM response raises ERR-SYN-001 |
| `test_synthesize_prompt_includes_chart_instruction` | Prompt sent to LLM includes chart block and image markdown instructions |

#### `tests/test_tools.py`
| Test | Goal |
|---|---|
| `test_web_search_returns_results` | Tavily response is parsed into a list of `{title, url, content}` dicts |
| `test_web_search_raises_on_quota_exceeded` | Quota exceeded error raises ERR-AUTH-005 |
| `test_web_search_raises_on_invalid_key` | Invalid API key error raises ERR-AUTH-003 |
| `test_notebooklm_reader_returns_sources` | `query_notebook()` returns `{name, content}` dict |
| `test_notebooklm_reader_raises_on_not_found` | Invalid notebook UUID raises ERR-NTB-001 |
| `test_notebooklm_reader_raises_on_permission_denied` | MCP connection failure raises ERR-NTB-003 |
| `test_fetch_notebook_image_returns_none_on_error` | Any MCP error from `fetch_notebook_image()` returns None, never raises |
| `test_fetch_notebook_image_returns_bytes_on_success` | Successful MCP response returns raw image bytes |

#### `tests/test_pdf_formatter.py`
| Test | Goal |
|---|---|
| `test_generate_pdf_creates_file` | `generate_pdf()` produces a `.pdf` file on disk |
| `test_generate_pdf_file_is_nonempty` | Generated PDF is at least 1KB |
| `test_generate_pdf_filename_contains_run_id` | Filename includes the date portion of run_id |
| `test_generate_pdf_raises_on_unwritable_dir` | Unwritable output directory raises ERR-PDF-002 |
| `test_placeholder_box_returns_table` | `_placeholder_box()` returns a ReportLab Table flowable |
| `test_placeholder_box_contains_message` | `_placeholder_box()` does not raise and returns non-None |

#### `tests/test_pdf_charts_images.py`
| Test | Goal |
|---|---|
| `test_fetch_image_local_file` | Local file path returns correct bytes |
| `test_fetch_image_local_missing_returns_none` | Missing local file returns None |
| `test_fetch_image_url_success` | HTTP URL (mocked) returns bytes |
| `test_fetch_image_url_failure_returns_none` | Network error returns None |
| `test_fetch_image_notebooklm_delegates` | `notebooklm://` URI delegates to `fetch_notebook_image()` |
| `test_fetch_image_notebooklm_unavailable_returns_none` | `fetch_notebook_image()` returning None propagates as None |
| `test_render_bar_returns_drawing` | Bar chart spec produces a ReportLab Drawing |
| `test_render_bar_with_title` | Bar chart with optional title produces a Drawing |
| `test_render_hbar_returns_drawing` | Horizontal bar chart spec produces a Drawing |
| `test_render_pie_returns_drawing` | Pie chart spec produces a Drawing |
| `test_render_pie_zero_values_no_crash` | All-zero values do not cause division by zero |
| `test_render_line_returns_drawing` | Multi-series line chart produces a Drawing |
| `test_render_stacked_bar_returns_drawing` | Multi-series stacked bar produces a Drawing |
| `test_md_chart_bar_renders_drawing` | ` ```chart ` block in markdown produces a Drawing flowable |
| `test_md_chart_invalid_json_renders_placeholder` | Malformed JSON in chart block produces a placeholder Table |
| `test_md_chart_unknown_type_renders_placeholder` | Unknown chart type produces a placeholder Table |
| `test_md_chart_missing_values_renders_placeholder` | Missing required field produces a placeholder Table |
| `test_md_image_success_renders_image_flowable` | Valid image bytes produce a ReportLab Image flowable |
| `test_md_image_fetch_failure_renders_placeholder` | Failed image fetch produces a placeholder Table |
| `test_md_image_notebooklm_unavailable_renders_placeholder` | Unavailable NotebookLM image produces a placeholder Table |
| `test_md_image_caption_rendered` | Non-empty alt text produces a caption Paragraph below the image |

#### `tests/test_email_sender.py`
| Test | Goal |
|---|---|
| `test_send_email_calls_composio` | `send_report_email()` invokes Composio `GMAIL_SEND_EMAIL` with correct args |
| `test_send_email_prevents_duplicate` | Second call for same run_id raises ERR-EML-004 |
| `test_send_email_raises_on_missing_recipients` | Empty TO list raises ERR-EML-005 |

#### `tests/test_approval.py`
| Test | Goal |
|---|---|
| `test_approval_y_returns_approved` | Input "y" returns "approved" |
| `test_approval_n_returns_declined` | Input "n" returns "declined" |
| `test_approval_invalid_then_y` | Invalid input loops until valid; "y" eventually returns "approved" |
| `test_approval_edit_then_y` | Input "edit" opens PDF viewer, then "y" returns "approved" |

#### `tests/test_scheduler.py`
| Test | Goal |
|---|---|
| `test_validate_cron_valid` | Well-formed 5-field cron expression passes validation |
| `test_validate_cron_invalid_raises_cfg002` | Non-5-field cron raises ERR-CFG-002 |
| `test_validate_cron_invalid_field_raises_cfg003` | Invalid field value raises ERR-CFG-003 |
| `test_start_scheduler_disabled_exits_early` | `schedule.enabled: false` causes `start_scheduler()` to return immediately |

#### `tests/test_resume.py`
| Test | Goal |
|---|---|
| `test_display_run_summary_shows_all_stages` | Summary output includes all subtopics, synthesis, pdf, and email stages |
| `test_choose_resume_option_1_retry` | Option 1 returns action=retry with failed subtopics listed |
| `test_choose_resume_option_2_skip` | Option 2 returns action=skip |
| `test_choose_resume_option_3_restart` | Option 3 returns action=restart |
| `test_choose_resume_option_4_abort` | Option 4 returns action=abort |

#### `tests/test_main.py`
| Test | Goal |
|---|---|
| `test_research_command_exists` | CLI `research` command is registered and responds to `--help` |
| `test_scheduler_command_exists` | CLI `scheduler` command is registered and responds to `--help` |
| `test_resume_command_exists` | CLI `resume` command is registered and responds to `--help` |
| `test_dry_run_flag_runs_without_api_calls` | `research --dry-run` completes without any real API calls |

---

## 17. Future Enhancements

- Mode 2: Sequential sub-agents with context passing
- Mode 3: Hybrid parallel waves with context enrichment
- LiteLLM already in place — add Gemini/GPT models by updating config.yaml and .env only
- Desktop notifications for scheduled run results
- Web dashboard to view report history and audit log
- Support for additional sources (RSS feeds, arXiv, GitHub trending)
- Multi-recipient email delivery
- Report templates (technical, executive, academic)
