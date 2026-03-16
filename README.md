Research To Report Agent
========================

Turn any research topic into a polished, emailed PDF report — fully automated, with a human-in-the-loop option.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## What Is This?

Keeping up with a fast-moving domain is genuinely hard. Whether you are tracking industry trends, monitoring a competitor landscape, or building a knowledge base for a team, the work is the same: search, read, synthesize, write, format, share. Done manually, a single quality research brief can take hours. Done poorly, it produces a wall of raw notes that nobody reads.

Research-to-Report is an autonomous agent that does that entire loop for you. You give it a topic. It breaks the topic into focused subtopics and spins up parallel research agents — each one independently searching the web, pulling from your own curated knowledge sources in NotebookLM, and synthesising what it finds. A final synthesis agent combines the results into a structured, professional PDF report that is delivered to your inbox.

What makes this approach different from a simple "ask ChatGPT to research X" workflow is the architecture. Each research agent works on a narrow slice of the problem, which means they go deeper and stay focused rather than producing shallow summaries. NotebookLM acts as a personal RAG layer on top of general web search — your curated sources get equal weight alongside live web results, so domain-specific knowledge you have already collected is not lost. And because the agents are running in parallel, a topic that might take a person half a day produces a finished report in minutes.

The human-in-the-loop design is intentional. On ad-hoc runs, you see a preview of the report and approve it before the email is sent — you stay in control of what lands in people's inboxes. Scheduled runs skip the gate and deliver automatically, which works well for recurring briefings where the cadence matters more than per-report review. Both modes write a full audit log, so you always know what was searched, what was found, and when.

---

## How It Works

```
You provide a topic
        ↓
Orchestrator decomposes it into N subtopics
        ↓
N Research Agents run in parallel
  ├── Web search (Tavily)
  └── NotebookLM query (optional personal RAG)
        ↓
Synthesis Agent writes the full report
        ↓
PDF Formatter renders it (text, tables, charts, images)
        ↓
Human approval gate (ad-hoc runs only)
        ↓
Gmail delivery + local file save
```

---

## Prerequisites

| Requirement | Purpose | Required? |
|---|---|---|
| Python 3.11+ | Runtime | Yes |
| Anthropic API key | Claude LLM — research and synthesis | Yes |
| Tavily API key | Web search | Yes |
| Composio API key | Gmail delivery via OAuth | Yes |
| Google service account | NotebookLM access | Only if using NotebookLM |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

`requirements.txt` contains all the Python libraries this project depends on — the LLM client, PDF renderer, web search client, and more. Without them, the agent cannot run. The second command (`pip install -e .`) registers the `research-report` CLI binary on your system using the entry point defined in `pyproject.toml`, so you can run the agent from anywhere in your terminal.

**If `research-report` is not found after installing**, pip placed the binary in a Scripts/bin directory that is not yet on your system PATH. This is a common one-time setup step. Find and add the right folder for your OS:

<details>
<summary>Windows</summary>

Find your Scripts folder:
```powershell
python -m site --user-base
# Returns something like: C:\Users\YourName\AppData\Roaming\Python
# Add \Python3XX\Scripts to the end (match your Python version, e.g. Python314)
```

Add it to your user PATH permanently (run in PowerShell, then restart your terminal):
```powershell
[Environment]::SetEnvironmentVariable(
    "PATH",
    $env:PATH + ";C:\Users\YourName\AppData\Roaming\Python\Python314\Scripts",
    "User"
)
```

Alternatively, add it via **System Properties → Advanced → Environment Variables → User variables → Path → Edit → New**.

</details>

<details>
<summary>macOS</summary>

Find your bin folder:
```bash
python3 -m site --user-base
# Returns something like: /Users/yourname/Library/Python/3.11
# Append /bin to get the full path
```

Add it permanently (append to `~/.zshrc` or `~/.bash_profile`, then restart your terminal):
```bash
export PATH="$HOME/Library/Python/3.11/bin:$PATH"
```

</details>

<details>
<summary>Linux</summary>

pip places user-installed binaries in `~/.local/bin` by default.

Add it permanently (append to `~/.bashrc` or `~/.zshrc`, then restart your terminal):
```bash
export PATH="$HOME/.local/bin:$PATH"
```

</details>

If you prefer not to install the binary at all, you can always run the agent directly:
```bash
python src/main.py research "your topic here"
```

---

### 2. Get your API keys

Each service the agent talks to requires its own API key. These keys authenticate the agent's requests and are billed to your account — they are never shared and should never be committed to version control.

**Anthropic (Claude LLM)**

The agent uses Claude for topic decomposition, research synthesis, and final report writing. Without this key, no AI reasoning happens.

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Navigate to **API Keys** → **Create Key**
3. Copy the key — it starts with `sk-ant-`

**Tavily (web search)**

Tavily is the web search engine the research agents use. Each subtopic search costs a small number of credits. The free tier provides 1,000 credits/month, which covers approximately 35–70 reports depending on depth.

1. Go to [tavily.com](https://tavily.com) and sign up
2. Copy your API key from the dashboard

**Composio (Gmail delivery)**

Composio handles Gmail OAuth so you never need to configure Google credentials directly. It acts as a secure bridge between the agent and your Gmail account.

1. Go to [app.composio.dev](https://app.composio.dev) and sign up
2. Navigate to **Settings** → **API Keys** → **Create API Key**
3. Copy the key

---

### 3. Connect Gmail via Composio

The agent sends reports from your Gmail account. Composio handles the OAuth flow — you grant access once and it manages the tokens from then on.

1. Log in at [app.composio.dev](https://app.composio.dev)
2. Go to **Apps** → search for **Gmail** → click **Connect**
3. Complete the Google OAuth flow and authorise the Gmail scopes

After connecting, every report email will be sent from the Google account you authorised.

---

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the keys you collected in step 2:

```env
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
COMPOSIO_API_KEY=...
```

This file is loaded at startup. It is listed in `.gitignore` — never commit it.

---

### 5. Configure recipients

Open `config.yaml` and set who receives every report:

```yaml
email:
  default_recipients:
    - you@gmail.com
    - colleague@company.com
  default_cc: []
```

You can override recipients at run time with `--email` and `--email-cc` flags (see Usage below).

---

## Usage

```bash
# Ad-hoc run — research, generate PDF, prompt for approval, then send
research-report research "AI trends in healthcare"

# Override recipients for this run only
research-report research "AI trends" --email boss@company.com --email-cc reviewer@company.com

# Dry run — validates config and shows what would happen, no API calls made
research-report research "AI trends" --dry-run

# Start the scheduler (automated cron runs, no approval gate)
research-report scheduler start

# Resume an incomplete run
research-report resume
```

---

## Configuration

Edit `config.yaml` to control agent behaviour. Key settings:

| Setting | Default | Notes |
|---|---|---|
| `agent.default_model` | `claude-sonnet-4-6` | Any LiteLLM-supported model (Claude, Gemini, GPT-4, etc.) |
| `agent.max_subtopics` | `5` | Number of parallel research agents to spawn |
| `languages` | `[en]` | Report language versions to generate |
| `notebooklm.notebook_ids` | `[]` | Leave empty for web-only research |
| `schedule.enabled` | `false` | Set `true` to enable cron runs |
| `email.default_recipients` | `[]` | Who receives every report |

### Using NotebookLM as a personal knowledge source

If you maintain notebooks in [NotebookLM](https://notebooklm.google.com), you can point the agent at them to include your curated sources alongside web search results. This turns NotebookLM into a personal RAG layer — your existing research gets incorporated into every new report rather than being siloed.

Add your notebook IDs to `config.yaml`:

```yaml
notebooklm:
  notebook_ids:
    - your-notebook-id-here
```

Leave this list empty to use web search only. The `notebooklm-mcp-cli` package (included in requirements) handles the connection via browser automation — Chrome must be installed.

### Multi-language reports

English is always generated. Add Chinese variants to produce additional translated PDFs automatically:

```yaml
languages:
  - en       # English (always generated)
  - zh-CN    # Simplified Chinese
  - zh-TW    # Traditional Chinese
```

Each language produces a separate PDF file. Only the English version is emailed; translated PDFs are saved locally.

To translate an existing PDF manually:
```bash
python src/pdf/translator.py reports/my-report.pdf --lang zh-CN
```

---

## Testing

```bash
# Run all 89 unit tests (zero API calls made — all external services are mocked)
pytest tests/ -v

# Dry-run smoke test (validates your config without making any API calls)
research-report research "AI trends" --dry-run
```

---

## Project Structure

```
research-to-report/
├── src/
│   ├── main.py                   # CLI entry point
│   ├── agents/                   # AI pipeline
│   │   ├── orchestrator.py       # topic decomposition + parallel dispatch
│   │   ├── researcher.py         # per-subtopic research agent
│   │   └── synthesizer.py        # final report synthesis
│   ├── tools/                    # External integrations
│   │   ├── web_search.py         # Tavily web search
│   │   └── notebooklm_reader.py  # NotebookLM MCP client
│   ├── pdf/                      # PDF generation
│   │   ├── formatter.py          # ReportLab renderer (text, tables, charts, images)
│   │   └── translator.py         # PDF translation to zh-CN / zh-TW
│   ├── delivery/                 # Report delivery
│   │   ├── email_sender.py       # Gmail via Composio
│   │   └── approval.py           # human-in-the-loop approval prompt
│   ├── config/                   # Configuration loading
│   ├── log/                      # Structured logging and run state
│   └── run/                      # Scheduler, resume, preflight checks
├── tests/                        # Unit tests (89 tests, zero external calls)
├── reports/                      # Generated PDFs and logs (git-ignored)
├── docs/plans/                   # Design and implementation docs
├── config.yaml
├── pyproject.toml
└── requirements.txt
```

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and the project Code of Conduct.
