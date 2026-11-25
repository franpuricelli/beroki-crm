import re
from dataclasses import dataclass

import phonenumbers
from phonenumbers import PhoneNumberType

from .config import WHATSAPP

PHONE = WHATSAPP["phone"]
AMBIGUOUS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in PHONE["ambiguous"])
TYPE_NAMES = {value: name for name, value in vars(PhoneNumberType).items() if name.isupper()}


@dataclass(frozen=True)
class Phone:
    e164: str
    country: str

    @property
    def digits(self):
        return self.e164[1:]

    @property
    def jid(self):
        return self.digits + "@s.whatsapp.net"


@dataclass(frozen=True)
class PhoneResult:
    phone: Phone | None
    reason: str | None


def normalize(raw):
    text = (raw or "").strip()
    if not text:
        return PhoneResult(None, "phone_missing")
    if any(pattern.search(text) for pattern in AMBIGUOUS):
        return PhoneResult(None, "phone_ambiguous")
    if text.startswith("00"):
        text = "+" + text[2:]
    if not text.startswith("+"):
        return PhoneResult(None, "phone_ambiguous")
    try:
        number = phonenumbers.parse(text, None)
    except phonenumbers.NumberParseException:
        return PhoneResult(None, "phone_invalid")
    if not phonenumbers.is_valid_number(number):
        return PhoneResult(None, "phone_invalid")
    country = phonenumbers.region_code_for_number(number)
    allowed = PHONE["countries"].get(country)
    if allowed is None:
        return PhoneResult(None, "phone_other_country")
    if TYPE_NAMES.get(phonenumbers.number_type(number)) not in allowed["types"]:
        return PhoneResult(None, "phone_not_mobile")
    e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    return PhoneResult(Phone(e164, country), None)


def digits_of(value):
    return re.sub(r"\D", "", value or "")
