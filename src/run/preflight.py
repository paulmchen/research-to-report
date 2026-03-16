import os
import re
import socket


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


def run_preflight(cfg: dict) -> None:
    check_network(cfg)
    check_api_keys(cfg)
    check_output_dirs(cfg)
