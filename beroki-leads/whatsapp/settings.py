import re
from dataclasses import dataclass

from . import phones
from .config import WHATSAPP

BATCH = WHATSAPP["batch"]
MESSAGE = WHATSAPP["message"]
MODES = ("dry-run", "send")
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
REQUIRED = ("CRM_API_URL", "CRM_API_KEY", "VOLT_API_KEY", "KAIRON_API_KEY", "DA_WHATSAPP_VOLT_INSTANCE_ID", "DA_WHATSAPP_SENDER")


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    mode: str
    batch: int
    message: str | None
    crm_url: str
    crm_key: str
    volt_key: str
    kairon_key: str
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


def message_text(raw):
    value = (raw or "").strip()
    if not value:
        return None
    if len(value) > MESSAGE["max_chars"]:
        raise SettingsError(f"DA_WHATSAPP_MESSAGE is longer than {MESSAGE['max_chars']} characters")
    names = PLACEHOLDER.findall(value)
    if any(name not in MESSAGE["placeholders"] for name in names):
        raise SettingsError("DA_WHATSAPP_MESSAGE has a placeholder other than {first_name}")
    if PLACEHOLDER.sub("", value).count("{") or PLACEHOLDER.sub("", value).count("}"):
        raise SettingsError("DA_WHATSAPP_MESSAGE has an unmatched brace")
    return value


def render(template, contact):
    return template.replace("{first_name}", contact.first_name.strip())


def load(env, mode):
    if mode not in MODES:
        raise SettingsError(f"mode must be one of {', '.join(MODES)}")
    missing = [name for name in REQUIRED if not (env.get(name) or "").strip()]
    if missing:
        raise SettingsError("missing configuration: " + ", ".join(missing))
    message = message_text(env.get("DA_WHATSAPP_MESSAGE"))
    if mode == "send":
        if env.get("DA_WHATSAPP_SEND_ENABLED") != "true":
            raise SettingsError("send mode needs DA_WHATSAPP_SEND_ENABLED=true")
        if env.get("GITHUB_ACTIONS") != "true":
            raise SettingsError("send mode runs only in GitHub Actions")
        branch = (env.get("DA_WHATSAPP_DEFAULT_BRANCH") or "").strip()
        if not branch or env.get("GITHUB_REF") != "refs/heads/" + branch:
            raise SettingsError("send mode runs only from the default branch")
        if message is None:
            raise SettingsError("send mode needs DA_WHATSAPP_MESSAGE")
    return Settings(
        mode=mode,
        batch=batch_size(env.get("DA_WHATSAPP_BATCH_SIZE")),
        message=message,
        crm_url=env["CRM_API_URL"].strip(),
        crm_key=env["CRM_API_KEY"].strip(),
        volt_key=env["VOLT_API_KEY"].strip(),
        kairon_key=env["KAIRON_API_KEY"].strip(),
        volt_instance=env["DA_WHATSAPP_VOLT_INSTANCE_ID"].strip(),
        sender=phones.digits_of(env["DA_WHATSAPP_SENDER"]),
        run_id=(env.get("GITHUB_RUN_ID") or "local").strip(),
    )
