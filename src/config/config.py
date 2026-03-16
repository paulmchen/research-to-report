import os
import yaml


class ConfigError(Exception):
    pass


def load_config(path: str = "config.yaml") -> dict:
    if not os.path.exists(path):
        raise ConfigError(f"[ERR-CFG-001] config.yaml not found at: {path}")

    with open(path, "r") as f:
        cfg = yaml.safe_load(f)

    # ENV override: log level
    env_level = os.environ.get("LOG_LEVEL")
    if env_level:
        cfg.setdefault("logging", {})["level"] = env_level

    # Audit cannot be disabled
    if not cfg.get("audit", {}).get("enabled", True):
        print("Warning [WRN-CFG-006]: Audit logging cannot be disabled. Agent actions will always be recorded.")
        cfg["audit"]["enabled"] = True

    # Validate languages — default to English only
    _valid = {"en", "zh-CN", "zh-TW"}
    languages = cfg.get("languages", ["en"])
    invalid = [l for l in languages if l not in _valid]
    if invalid:
        raise ConfigError(
            f"[ERR-CFG-007] Unsupported language(s): {invalid}. "
            f"Supported: en, zh-CN, zh-TW"
        )
    if "en" not in languages:
        languages = ["en"] + languages   # en is always generated
    cfg["languages"] = languages

    return cfg
