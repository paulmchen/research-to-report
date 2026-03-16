import os
import sys

from datetime import datetime, timezone

import click
from dotenv import load_dotenv

from config import load_config, ConfigError
from log.logger import setup_loggers, write_audit
from run.preflight import run_preflight, PreflightError, merge_recipients, validate_emails
from agents.orchestrator import decompose_topic, run_parallel_research, OrchestratorError
from agents.researcher import LLMError
from agents.synthesizer import synthesize, SynthesisError
from pdf.formatter import generate_pdf, PDFError
from pdf.translator import generate_translation
from delivery.email_sender import send_report_email, EmailError
from delivery.approval import request_approval
from log.state import create_master_state, update_master_state, find_incomplete_runs
from run.resume import display_run_summary, choose_resume_option

load_dotenv()


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


@click.group()
def cli():
    """Research-to-Report: autonomous research agent."""
    pass


@cli.command()
@click.argument("topic")
@click.option("--email", "cli_to", default="", help="Comma-separated TO recipients")
@click.option("--email-cc", "cli_cc", default="", help="Comma-separated CC recipients")
@click.option("--dry-run", is_flag=True, default=False, help="Run without making API calls")
@click.option("--log-level", default=None, help="Override log level (DEBUG/INFO/WARNING/ERROR)")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def research(topic, cli_to, cli_cc, dry_run, log_level, config_path):
    """Run research pipeline for TOPIC."""
    if log_level:
        os.environ["LOG_LEVEL"] = log_level

    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    setup_loggers(cfg)
    audit_path = cfg["audit"]["log_file"]
    state_dir = os.path.join(cfg["output_dir"], "state")
    run_id = _run_id()

    config_to = cfg["email"].get("default_recipients", [])
    config_cc = cfg["email"].get("default_cc", [])
    parsed_cli_to = [e.strip() for e in cli_to.split(",") if e.strip()]
    parsed_cli_cc = [e.strip() for e in cli_cc.split(",") if e.strip()]

    try:
        to_list, cc_list, warnings = merge_recipients(config_to, parsed_cli_to, config_cc, parsed_cli_cc)
        for w in warnings:
            click.echo(f"Warning: {w}")
        validate_emails(to_list + cc_list)
    except PreflightError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    if not dry_run:
        try:
            run_preflight(cfg)
        except PreflightError as e:
            click.echo(str(e), err=True)
            sys.exit(1)

    write_audit(audit_path, {"event": "RUN_STARTED", "run_id": run_id,
                              "mode": "ad-hoc", "topic": topic, "triggered_by": "cli"})
    create_master_state(run_id, topic, "ad-hoc", state_dir)

    try:
        click.echo(f"Decomposing topic: {topic}")
        subtopics = decompose_topic(topic, cfg) if not dry_run else ["Subtopic A (dry run)", "Subtopic B (dry run)"]

        click.echo(f"Launching {len(subtopics)} research agents:")
        for i, st in enumerate(subtopics, 1):
            click.echo(f"  {i}. {st}")
        click.echo("This may take several minutes while all agents run in parallel...")
        findings = run_parallel_research(run_id, subtopics, cfg, state_dir, dry_run=dry_run)

        click.echo("Synthesizing findings (this may also take a moment)...")
        report = synthesize(topic, findings, cfg, dry_run=dry_run)

        report_data = {
            "topic": topic, "run_id": run_id,
            "executive_summary": report["executive_summary"],
            "full_report": report["full_report"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        click.echo("Generating PDF...")
        pdf_path = generate_pdf(data=report_data, output_dir=cfg["output_dir"])
        write_audit(audit_path, {"event": "REPORT_GENERATED", "run_id": run_id, "file": pdf_path})
        click.echo(f"PDF saved: {pdf_path}")
        all_pdf_paths = [pdf_path]

        # Generate translated versions
        for lang in cfg.get("languages", ["en"]):
            if lang == "en":
                continue
            click.echo(f"Generating {lang} translation...")
            try:
                zh_path = generate_translation(
                    data=report_data,
                    language=lang,
                    output_dir=cfg["output_dir"],
                    model=cfg["agent"]["default_model"],
                )
                write_audit(audit_path, {"event": "REPORT_GENERATED", "run_id": run_id,
                                         "file": zh_path, "language": lang})
                click.echo(f"PDF saved: {zh_path}")
                all_pdf_paths.append(zh_path)
            except Exception as e:
                click.echo(f"Warning: {lang} translation failed — {e}", err=True)

    except (OrchestratorError, SynthesisError, PDFError, LLMError) as e:
        click.echo(str(e), err=True)
        update_master_state(run_id, state_dir, {"status": "FAILED"})
        sys.exit(1)

    if dry_run:
        click.echo("[DRY RUN] Skipping email delivery.")
        update_master_state(run_id, state_dir, {"status": "COMPLETED"})
        return

    decision = request_approval(topic, to_list, cc_list, all_pdf_paths)
    write_audit(audit_path, {"event": "APPROVAL_DECISION", "run_id": run_id, "decision": decision})

    if decision == "approved":
        try:
            send_report_email(all_pdf_paths, topic, to_list, cc_list, audit_path, run_id)
            write_audit(audit_path, {"event": "EMAIL_SENT", "run_id": run_id,
                                      "to": to_list, "cc": cc_list})
            click.echo("Email sent successfully.")
        except EmailError as e:
            click.echo(str(e), err=True)
    else:
        click.echo("Email skipped. PDF saved locally.")

    update_master_state(run_id, state_dir, {"status": "COMPLETED"})
    write_audit(audit_path, {"event": "RUN_COMPLETED", "run_id": run_id, "status": "success"})


@cli.command()
@click.argument("action", type=click.Choice(["start", "stop"]))
@click.option("--config", "config_path", default="config.yaml")
def scheduler(action, config_path):
    """Start or stop the APScheduler cron scheduler."""
    if action == "start":
        try:
            cfg = load_config(config_path)
        except ConfigError as e:
            click.echo(str(e), err=True)
            sys.exit(1)
        from run.scheduler import start_scheduler
        start_scheduler(cfg)
    else:
        click.echo("Scheduler stopped.")


@cli.command("resume")
@click.option("--config", "config_path", default="config.yaml")
def resume_cmd(config_path):
    """Resume an incomplete research run."""
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    state_dir = os.path.join(cfg["output_dir"], "state")
    runs = find_incomplete_runs(state_dir)

    if not runs:
        click.echo("[ERR-STA-003] No incomplete runs found to resume.")
        return

    click.echo("\nFinding incomplete runs...")
    for run in runs:
        click.echo(f"  Found: {run['run_id']} — \"{run['topic']}\" ({run['status']})")
        display_run_summary(run)
        decision = choose_resume_option(run)
        click.echo(f"Action: {decision['action']}")


if __name__ == "__main__":
    cli()
