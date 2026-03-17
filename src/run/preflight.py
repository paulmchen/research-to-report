import os
import re
import socket
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=UserWarning, module="composio_client")
    from composio.sdk import Composio


class PreflightError(Exception):
    pass


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_emails(emails: list[str]) -> None:
    for email in emails:
        if not _EMAIL_RE.match(email):
            raise PreflightError(f"[ERR-EML-003] Invalid recipient email address: {email}")


def merge_recipients(
    config_to: list[str],
    cli_to: list[str],
    config_cc: list[str],
    cli_cc: list[str],
) -> tuple[list[str], list[str], list[str]]:
    def norm(e): return e.lower().strip()

    seen_to: dict[str, str] = {}
    for e in config_to + cli_to:
        seen_to[norm(e)] = e

    seen_cc: dict[str, str] = {}
    for e in config_cc + cli_cc:
        seen_cc[norm(e)] = e

    warnings = []
    for key in list(seen_cc.keys()):
        if key in seen_to:
            warnings.append(f"[WRN-EML-006] {seen_cc[key]} is in both TO and CC — removed from CC, kept in TO")
            del seen_cc[key]

    to_list = list(seen_to.values())
    cc_list = list(seen_cc.values())

    if not to_list:
        raise PreflightError("[ERR-EML-005] No recipients configured — set default_recipients in config.yaml or pass --email")

    return to_list, cc_list, warnings


def check_network(cfg: dict) -> None:
    try:
        socket.setdefaulttimeout(5)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
    except Exception:
        raise PreflightError("[ERR-NET-001] No internet connection")


def check_api_keys(cfg: dict) -> None:
    model = cfg.get("agent", {}).get("default_model", "")
    if "claude" in model and not os.environ.get("ANTHROPIC_API_KEY"):
        raise PreflightError("[ERR-AUTH-002] ANTHROPIC_API_KEY is required for Claude models but is not set")
    if "gemini" in model and not os.environ.get("GOOGLE_API_KEY"):
        raise PreflightError("[ERR-AUTH-006] GOOGLE_API_KEY is required for Gemini models but is not set")
    if "gpt" in model and not os.environ.get("OPENAI_API_KEY"):
        raise PreflightError("[ERR-AUTH-006] OPENAI_API_KEY is required for GPT models but is not set")

    # Composio API key required for Gmail delivery
    if not os.environ.get("COMPOSIO_API_KEY"):
        raise PreflightError(
            "[ERR-AUTH-008] COMPOSIO_API_KEY is not set. "
            "Required for Gmail delivery — get your key at app.composio.dev."
        )



def check_output_dirs(cfg: dict) -> None:
    base = cfg.get("output_dir", "./reports")
    for subdir in ["", "logs", "state", "state/archive"]:
        path = os.path.join(base, subdir)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise PreflightError(f"[ERR-PDF-002] Output directory not writable: {path} — {e}")


def check_composio_gmail(cfg: dict) -> None:
    """Verify the Composio Gmail OAuth connection is active before research starts.

    The Composio API key itself does not expire, but the Gmail OAuth link inside
    Composio can become invalid (user revokes Google access, token expiry, or
    disconnect via the Composio dashboard). This check catches that early without
    sending any email — it only lists connected accounts.
    """
    api_key = os.environ.get("COMPOSIO_API_KEY")
    if not api_key:
        return  # check_api_keys already caught the missing key case

    try:
        composio = Composio(api_key=api_key)
        accounts = composio._client.connected_accounts.list()
        gmail_account = next(
            (a for a in accounts.items if a.toolkit.slug == "gmail" and a.status == "ACTIVE"),
            None,
        )
    except Exception as e:
        raise PreflightError(
            f"[ERR-AUTH-008] Composio API key is invalid or unreachable: {e}\n"
            "  Verify your COMPOSIO_API_KEY at app.composio.dev."
        )

    if gmail_account is None:
        raise PreflightError(
            "[ERR-AUTH-008] No active Gmail connection found in Composio.\n"
            "  Connect your Gmail account at app.composio.dev → Apps → Gmail → Connect."
        )


def check_notebooklm(cfg: dict) -> None:
    notebook_ids = cfg.get("notebooklm", {}).get("notebook_ids", [])
    if not notebook_ids:
        return
    from tools.notebooklm_reader import verify_notebooklm_auth, ToolError
    try:
        verify_notebooklm_auth(notebook_ids)
    except ToolError as e:
        msg = str(e)
        if "ERR-AUTH-009" in msg:
            raise PreflightError(
                "[ERR-AUTH-009] NotebookLM authentication has expired.\n"
                "  Run 'nlm login' in your terminal to re-authenticate, then retry."
            )
        raise PreflightError(
            f"[ERR-NTB-003] NotebookLM preflight check failed: {e}\n"
            "  Ensure 'uvx install notebooklm-mcp-cli' has been run and 'nlm login' is up to date."
        )


def run_preflight(cfg: dict) -> None:
    check_network(cfg)
    check_api_keys(cfg)
    check_output_dirs(cfg)
    check_composio_gmail(cfg)
    check_notebooklm(cfg)
