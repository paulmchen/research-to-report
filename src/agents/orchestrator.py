import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.researcher import run_research_agent, litellm_complete


class OrchestratorError(Exception):
    pass


def decompose_topic(topic: str, cfg: dict) -> list[str]:
    model = cfg["agent"]["default_model"]
    n = cfg["agent"].get("max_subtopics", 5)
    prompt = (
        f"Break the following research topic into exactly {n} focused subtopics suitable for independent research.\n"
        f"Topic: {topic}\n\n"
        f"Return ONLY a numbered list of exactly {n} items, one subtopic per line. No explanations."
    )
    raw = litellm_complete(model, [{"role": "user", "content": prompt}], max_tokens=512)
    subtopics = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[\d]+[\.\)]\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        if line:
            subtopics.append(line)
    return subtopics


def run_parallel_research(
    run_id: str,
    subtopics: list[str],
    cfg: dict,
    state_dir: str,
    dry_run: bool = False,
) -> dict[str, str]:
    results: dict[str, str] = {}
    errors: dict[str, Exception] = {}

    with ThreadPoolExecutor(max_workers=len(subtopics)) as executor:
        futures = {
            executor.submit(
                run_research_agent,
                run_id, idx + 1, subtopic, cfg, state_dir, dry_run
            ): subtopic
            for idx, subtopic in enumerate(subtopics)
        }
        for future in as_completed(futures):
            subtopic = futures[future]
            try:
                results[subtopic] = future.result()
            except Exception as e:
                errors[subtopic] = e

    if errors and not results:
        raise OrchestratorError(
            f"[ERR-RES-003] All subtopics failed: {', '.join(errors.keys())}"
        )

    return results
