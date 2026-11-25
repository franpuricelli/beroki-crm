import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import WHATSAPP

WINDOW = WHATSAPP["window"]
ZONES = WHATSAPP["zones"]


@dataclass(frozen=True)
class Zones:
    names: tuple
    exact: bool


@dataclass(frozen=True)
class ZoneResult:
    zones: Zones | None
    reason: str | None


def contact_zones(country, verified_zone):
    candidates = ZONES.get(country)
    if not candidates:
        return ZoneResult(None, "zone_unclear")
    if verified_zone:
        name = verified_zone.strip()
        if name not in candidates:
            return ZoneResult(None, "zone_conflict")
        return ZoneResult(Zones((name,), True), None)
    return ZoneResult(Zones(tuple(candidates), False), None)


def is_business_time(moment, zone_name):
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    try:
        local = moment.astimezone(ZoneInfo(zone_name))
    except ZoneInfoNotFoundError:
        return False
    if local.weekday() not in WINDOW["weekdays"]:
        return False
    start = local.replace(hour=WINDOW["start_hour"], minute=0, second=0, microsecond=0)
    end = local.replace(hour=WINDOW["end_hour"], minute=0, second=0, microsecond=0)
    return start <= local < end


def in_window(moment, zones):
    return all(is_business_time(moment, name) for name in zones.names)


def utc_now():
    return dt.datetime.now(dt.timezone.utc)
