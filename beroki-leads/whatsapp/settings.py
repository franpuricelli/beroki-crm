import re
from dataclasses import dataclass

from . import phones
from .config import WHATSAPP

BATCH = WHATSAPP["batch"]
SERVICES = WHATSAPP["draft"]["services"]
MODES = ("dry-run", "send")
REQUIRED = (
    "CRM_API_URL",
    "CRM_API_KEY",
    "VOLT_API_KEY",
    "KAIRON_API_KEY",
    "AGENT_URL",
    "DA_WHATSAPP_DRAFT_SECRET",
    "DA_WHATSAPP_SERVICES",
    "DA_WHATSAPP_VOLT_INSTANCE_ID",
    "DA_WHATSAPP_SENDER",
)


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    mode: str
    batch: int
    services: tuple
    crm_url: str
    crm_key: str
    volt_key: str
    kairon_key: str
    agent_url: str
    draft_secret: str
    volt_instance: str
    sender: str
    run_id: str


def batch_size(raw):
    value = (raw or "").strip()
    if not value:
        return BATCH["default"]
    if not value.isdigit():
        raise SettingsError("DA_WHATSAPP_BATCH_SIZE must be a whole number")
    size = int(value)
    if not BATCH["min"] <= size <= BATCH["max"]:
        raise SettingsError(f"DA_WHATSAPP_BATCH_SIZE must be between {BATCH['min']} and {BATCH['max']}")
    return size


def service_list(raw):
    services = tuple(" ".join(item.split()) for item in re.split(r"[\n;]", raw or "") if item.strip())
    if not 1 <= len(services) <= SERVICES["max"]:
        raise SettingsError(f"DA_WHATSAPP_SERVICES needs 1 to {SERVICES['max']} services, one per line or separated by ;")
    if any(len(service) > SERVICES["max_chars"] for service in services):
        raise SettingsError(f"each service in DA_WHATSAPP_SERVICES must be {SERVICES['max_chars']} characters or fewer")
    return services


def load(env, mode):
    if mode not in MODES:
        raise SettingsError(f"mode must be one of {', '.join(MODES)}")
    missing = [name for name in REQUIRED if not (env.get(name) or "").strip()]
    if missing:
        raise SettingsError("missing configuration: " + ", ".join(missing))
    services = service_list(env.get("DA_WHATSAPP_SERVICES"))
    if mode == "send":
        if env.get("DA_WHATSAPP_SEND_ENABLED") != "true":
            raise SettingsError("send mode needs DA_WHATSAPP_SEND_ENABLED=true")
        if env.get("GITHUB_ACTIONS") != "true":
            raise SettingsError("send mode runs only in GitHub Actions")
        branch = (env.get("DA_WHATSAPP_DEFAULT_BRANCH") or "").strip()
        if not branch or env.get("GITHUB_REF") != "refs/heads/" + branch:
            raise SettingsError("send mode runs only from the default branch")
    return Settings(
        mode=mode,
        batch=batch_size(env.get("DA_WHATSAPP_BATCH_SIZE")),
        services=services,
        crm_url=env["CRM_API_URL"].strip(),
        crm_key=env["CRM_API_KEY"].strip(),
        volt_key=env["VOLT_API_KEY"].strip(),
        kairon_key=env["KAIRON_API_KEY"].strip(),
        agent_url=env["AGENT_URL"].strip(),
        draft_secret=env["DA_WHATSAPP_DRAFT_SECRET"].strip(),
        volt_instance=env["DA_WHATSAPP_VOLT_INSTANCE_ID"].strip(),
        sender=phones.digits_of(env["DA_WHATSAPP_SENDER"]),
        run_id=(env.get("GITHUB_RUN_ID") or "local").strip(),
    )
