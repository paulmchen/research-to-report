import json
import os

from composio.sdk import Composio


class EmailError(Exception):
    pass


def _already_sent(audit_log_path: str, run_id: str) -> bool:
    if not os.path.exists(audit_log_path):
        return False
    with open(audit_log_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("event") == "EMAIL_SENT" and entry.get("run_id") == run_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def _send_via_composio(
    to_list: list,
    cc_list: list,
    subject: str,
    body: str,
    pdf_paths: list,
    api_key: str = None,
) -> dict:
    key = api_key or os.environ.get("COMPOSIO_API_KEY")
    if not key:
        raise EmailError(
            "[ERR-AUTH-008] COMPOSIO_API_KEY is not set. "
            "Add it to your .env file — get your key at app.composio.dev."
        )

    composio = Composio(api_key=key)

    # Find the active Gmail connected account
    accounts = composio._client.connected_accounts.list()
    gmail_account = next(
        (a for a in accounts.items if a.toolkit.slug == "gmail" and a.status == "ACTIVE"),
        None,
    )
    if gmail_account is None:
        raise EmailError(
            "[ERR-AUTH-008] No active Gmail connection found in Composio. "
            "Connect your Gmail account at app.composio.dev → Apps → Gmail → Connect."
        )

    response = composio.tools.execute(
        slug="GMAIL_SEND_EMAIL",
        arguments={
            "recipient_email": to_list[0],
            "extra_recipients": to_list[1:] if len(to_list) > 1 else [],
            "cc": cc_list,
            "subject": subject,
            "body": body,
            "attachment": pdf_paths[0],
        },
        connected_account_id=gmail_account.id,
        user_id=gmail_account.user_id,
        dangerously_skip_version_check=True,
    )

    if not response["successful"]:
        error = response.get("error") or "unknown error"
        raise EmailError(f"[ERR-EML-002] Email delivery failed: {error}")

    return response["data"]


def send_report_email(
    pdf_paths: list[str],
    topic: str,
    to_list: list[str],
    cc_list: list[str],
    audit_log_path: str,
    run_id: str,
    api_key: str = None,
) -> dict:
    if not to_list:
        raise EmailError(
            "[ERR-EML-005] No recipients configured — set default_recipients in config.yaml or pass --email"
        )

    if _already_sent(audit_log_path, run_id):
        raise EmailError(
            f"[ERR-EML-004] Email already sent for run {run_id} — duplicate prevented"
        )

    try:
        return _send_via_composio(
            to_list=to_list,
            cc_list=cc_list,
            subject=f"Research Report: {topic}",
            body=f"Please find attached the research report on: {topic}",
            pdf_paths=pdf_paths,
            api_key=api_key,
        )
    except EmailError:
        raise
    except Exception as e:
        raise EmailError(f"[ERR-EML-002] Email delivery failed: {e}")
