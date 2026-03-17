import logging
import re

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import ConfigError

logger = logging.getLogger("agent")

_CRON_RE = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$")


def validate_cron(expr: str) -> None:
    if not _CRON_RE.match(expr.strip()):
        raise ConfigError(f"[ERR-CFG-002] Invalid cron expression format: '{expr}'")
    try:
        CronTrigger.from_crontab(expr)
    except ValueError as e:
        raise ConfigError(f"[ERR-CFG-003] Invalid cron field value in '{expr}': {e}")


def start_scheduler(cfg: dict) -> None:
    sched_cfg = cfg.get("schedule", {})
    if not sched_cfg.get("enabled", False):
        logger.info("Scheduler is disabled in config.")
        return

    cron = sched_cfg.get("cron", "0 8 * * MON")
    timezone = sched_cfg.get("timezone", "UTC")
    topics = sched_cfg.get("topics", [])
    validate_cron(cron)

    def run_scheduled_topic(topic: str) -> None:
        from agents.orchestrator import decompose_topic, run_parallel_research, OrchestratorError
        from agents.synthesizer import synthesize, summarize_title, SynthesisError
        from pdf.formatter import generate_pdf, PDFError
        from delivery.email_sender import send_report_email, EmailError
        from log.state import create_master_state, update_master_state
        from log.logger import write_audit
        from datetime import datetime, timezone as tz
        import os

        run_id = datetime.now(tz.utc).strftime("%Y-%m-%dT%H-%M-%S")
        state_dir = os.path.join(cfg["output_dir"], "state")
        audit_path = cfg["audit"]["log_file"]
        write_audit(audit_path, {"event": "RUN_STARTED", "run_id": run_id,
                                  "mode": "scheduled", "topic": topic, "triggered_by": "scheduler"})
        create_master_state(run_id, topic, "scheduled", state_dir)
        try:
            title = summarize_title(topic, cfg)
            subtopics = decompose_topic(topic, cfg)
            findings = run_parallel_research(run_id, subtopics, cfg, state_dir, dry_run=False)
            report = synthesize(topic, findings, cfg)
            pdf_path = generate_pdf(
                data={"topic": topic, "title": title, "run_id": run_id,
                      "executive_summary": report["executive_summary"],
                      "full_report": report["full_report"],
                      "generated_at": datetime.now(tz.utc).isoformat()},
                output_dir=cfg["output_dir"],
            )
            to_list = cfg["email"].get("default_recipients", [])
            cc_list = cfg["email"].get("default_cc", [])
            send_report_email(pdf_path, topic, to_list, cc_list, audit_path, run_id, title=title)
            write_audit(audit_path, {"event": "EMAIL_SENT", "run_id": run_id, "to": to_list})
            write_audit(audit_path, {"event": "RUN_COMPLETED", "run_id": run_id, "status": "success"})
            update_master_state(run_id, state_dir, {"status": "COMPLETED"})
        except Exception as e:
            logger.error(f"[ERR-SCH-002] Scheduled run failed for '{topic}': {e}")
            write_audit(audit_path, {"event": "RUN_FAILED", "run_id": run_id, "error": str(e)})
            update_master_state(run_id, state_dir, {"status": "FAILED"})

    scheduler = BlockingScheduler(timezone=timezone)
    trigger = CronTrigger.from_crontab(cron, timezone=timezone)
    for topic in topics:
        scheduler.add_job(run_scheduled_topic, trigger, args=[topic], id=f"research-{topic[:20]}")

    logger.info(f"Scheduler started. Cron: '{cron}' | Topics: {topics}")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
    except Exception as e:
        raise ConfigError(f"[ERR-SCH-001] Scheduler failed to start: {e}")
