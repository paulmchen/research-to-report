from agents.researcher import litellm_complete

_DRY_RUN_EXEC = "## [DRY RUN] Executive Summary\n\nThis is a dry-run stub executive summary."
_DRY_RUN_BODY = "## [DRY RUN] Full Report\n\nThis is a dry-run stub full report body."
_SEPARATOR = "---"


class SynthesisError(Exception):
    pass


def synthesize(
    topic: str,
    findings: dict[str, str],
    cfg: dict,
    dry_run: bool = False,
) -> dict[str, str]:
    if dry_run:
        return {"executive_summary": _DRY_RUN_EXEC, "full_report": _DRY_RUN_BODY}

    model = cfg["agent"]["default_model"]
    max_tokens = cfg["agent"].get("max_tokens", 8096)

    findings_text = "\n\n".join(
        f"### {subtopic}\n{content}" for subtopic, content in findings.items()
    )

    prompt = (
        f"You are a senior research analyst. Using the subtopic research below, "
        f"write a professional report on: **{topic}**\n\n"
        f"Structure your response EXACTLY as follows — with '---' as the separator:\n\n"
        f"# Executive Summary\n"
        f"[1-2 page executive summary with key findings and recommendations]\n\n"
        f"{_SEPARATOR}\n\n"
        f"# Full Report\n"
        f"[5-10 page detailed report: background, findings per subtopic, analysis, recommendations]\n\n"
        f"When relevant, enrich the report with visual elements placed inline:\n"
        f"- Charts: use ```chart blocks with JSON. "
        f"Supported types: bar, hbar, line, pie, stacked_bar.\n"
        f'  Example: ```chart\n{{"type":"bar","title":"Title","labels":["A","B"],"values":[10,20]}}\n```\n'
        f"  For line and stacked_bar use 'series': "
        f'[{{"name":"Label","values":[...]}}] instead of \'values\'.\n'
        f"- Images: use standard markdown ![caption](url). Only include real, publicly accessible URLs.\n"
        f"Only include charts where you have concrete numeric data. "
        f"Place visuals immediately after the text they illustrate.\n\n"
        f"---\n\nSubtopic Research:\n\n{findings_text}"
    )

    raw = litellm_complete(model, [{"role": "user", "content": prompt}], max_tokens)

    if not raw or not raw.strip():
        raise SynthesisError("[ERR-SYN-001] Synthesis agent produced empty report")

    parts = raw.split(f"\n{_SEPARATOR}\n", 1)
    if len(parts) == 2:
        executive_summary, full_report = parts[0].strip(), parts[1].strip()
    else:
        executive_summary = raw[:500].strip()
        full_report = raw.strip()

    return {"executive_summary": executive_summary, "full_report": full_report}
