import calendar
import datetime as dt
import html
import re
from dataclasses import dataclass, field

from .config import STAGE, STAGE_DECISION


FIELDS = (
    "council state application_number address suburb postcode lat lon description use "
    "units units_known storeys assessment_level date_lodged date_decided decision "
    "applicant developer planner_firm planner_contacts architect documents_url "
    "source_url first_seen last_updated related_applications relationship_notes"
).split()
LEGACY_FIELDS = FIELDS[:]
FIELDS = FIELDS[:-2] + "country owner owner_contacts applicant_contacts contractor contractor_contacts permit_numbers valuation".split() + FIELDS[-2:]
PREVIOUS_FIELDS = FIELDS[:]
FIELDS = FIELDS[:-2] + "etapa etapa_desde historial_etapas plans_url".split() + FIELDS[-2:]
UNVERIFIED = "Determined (unverified)"
RESIDENTIAL = re.compile(
    r"apartments?|multiple\s+(?:residential|dwellings?)|multi[ -]?(?:dwelling|unit)|"
    r"residential\s+flat\s+buildings?|shop[ -]top\s+housing|town\s*houses?|"
    r"build[ -]to[ -]rent|\bbtr\b", re.I
)
WORDS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)
))
WORDS.update(dict(zip(
    "twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)
)))


def months_before(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def text(value):
    return "" if value is None else str(value).strip()


def plain(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text(value))).split())


def date(value):
    if value in (None, "", "-", 0, "0"):
        return ""
    s = text(value)
    if re.fullmatch(r"\d{12,13}", s):
        try:
            return dt.datetime.fromtimestamp(int(s) / 1000, dt.timezone.utc).date().isoformat()
        except (ValueError, OverflowError, OSError):
            return ""
    for fmt, part in [("%Y-%m-%d", s[:10]), ("%d/%m/%Y", s),
                      ("%d %B %Y", s), ("%d %b %Y", s)]:
        try:
            day = dt.datetime.strptime(part, fmt).date()
            return day.isoformat() if day.year > 1970 else ""
        except ValueError:
            pass
    return ""


def numbers(value):
    s = plain(value).lower()
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
    for tens in list(WORDS)[20:]:
        for one in list(WORDS)[1:10]:
            s = re.sub(r"\b" + tens + r"[ -]" + one + r"\b",
                       str(WORDS[tens] + WORDS[one]), s)
    for word, number in WORDS.items():
        s = re.sub(r"\b" + word + r"\b", str(number), s)
    return s


def unit_count(description):
    s = numbers(description)
    s = re.sub(r"\bpre[\s\-\u2010-\u2015\u00ad]*\d{4}\b", "pre-era", s)
    revised = re.findall(r"(?:reduc\w*|increas\w*)[^.;\n]{0,30}\b(?:units?|dwellings?|apartments?|townhouses?)\s+from\s+(\d+)\s+to\s+(\d+)", s)
    if revised:
        return max(int(new) for old, new in revised)
    # Ranges and minimums do not state a definite proposed count.
    s = re.sub(r"\b\d+\s*(?:-|–|to|or more)\s*\d*\s*(?:units?|dwellings?|apartments?)", "", s)
    noun = r"(?:residential\s+)?(?:dwelling\s+units?|units?|dwellings?(?!\s+houses?\b)|apartments?|town\s*houses?)\b"
    qualifier = r"(?:(?:single|double|triple|\d+)[ -]storey|\d+[ -]bedroom|residential|additional|new|proposed|adjoined|attached|detached|manager['’]s)"
    pattern = r"(?<![\w.-])(\d+)\s*\)?\s*(?:" + qualifier + r"\s+)*" + noun
    matches = []
    for m in re.finditer(pattern, s):
        before = s[max(0, m.start() - 35):m.start()]
        if re.search(r"(?:existing|demoli\w*|remov\w*|from|unit)\s*(?:of\s+)?(?:\(\s*)?$", before):
            continue
        if re.search(r"(?:commercial|industrial|storage|retail)\s*$", before):
            continue
        if re.search(r"\b(?:unit|apartment|dwelling)$", m.group(0)) and re.match(r"\s*\d+\b", s[m.end():]):
            continue
        matches.append((int(m.group(1)), m.group(0), m.start(), m.end()))
    extra = [int(m.group(1)) for m in re.finditer(
        r"(?:multiple\s+dwellings?|apartments?|units?)\s*[x:]\s*(\d+)\b", s
    )]
    extra += [int(m.group(1)) for m in re.finditer(r"\b(\d+)\s*x\s*\d+[- ]bedroom\s+" + noun, s)]
    # Distinct dwelling types joined explicitly are additive, not repeated totals.
    totals = []
    for a, b in zip(matches, matches[1:]):
        between = s[a[3]:b[2]]
        if re.fullmatch(r"\s*(?:and|\+|plus)\s*(?:\w+\s+)*?(?:\(\s*)?", between):
            if ("town" in a[1] and "apartment" in b[1]) or ("apartment" in a[1] and "town" in b[1]):
                totals.append(a[0] + b[0])
            elif "manager" in b[1] and "dwelling" in a[1]:
                totals.append(a[0] + b[0])
    stages = {}
    for m in re.finditer(r"\bstage\s*:?\s*(\d+)\s*[-–]\s*multiple\s+dwellings?\s*\(\s*(\d+)\s+units?", s):
        stages[m.group(1)] = max(stages.get(m.group(1), 0), int(m.group(2)))
    if len(stages) > 1:
        totals.append(sum(stages.values()))
    values = [m[0] for m in matches] + extra + totals
    if values:
        return max(values)
    if re.search(r"dual[ -]occupancy", s) and re.search(r"\bdwellings?\b", s):
        return 2
    return None


def storeys(description):
    m = re.search(r"\b(\d+)\s*[- ]?\s*store(?:y|ys|ies)\b", numbers(description))
    return int(m.group(1)) if m else None


def is_residential(use, description):
    combined = plain(use) + " " + plain(description)
    if RESIDENTIAL.search(combined):
        return True
    # Generic mixed-use alone can be an office/shop project.
    return bool(re.search(r"mixed[ -]use", combined, re.I)
                and re.search(r"dwellings|residential|housing", combined, re.I)) or bool(
        re.search(r"(?:construct|develop|erect|building).*\bdwellings\b", combined, re.I)
    )


def outcome(value):
    s = plain(value).lower()
    if any(word in s for word in ["refus", "reject", "withdraw", "cancel", "lapsed"]):
        return ""
    grants = {
        "approved", "granted", "approval conditional", "conditional approval",
        "approved with conditions", "approved subject to conditions", "permit issued",
        "negotiated decision approved", "amended decision approved",
        "amended permit approved", "development approved", "consent granted",
    }
    return "Approved" if s in grants else UNVERIFIED


def closing_stage(value):
    s = plain(value).lower()
    if re.search(r"refus|reject|denied|prohibit", s):
        return STAGE["refused"]
    if re.search(r"withdraw|cancel|void|abort|returned", s):
        return STAGE["withdrawn"]
    if re.search(r"laps|expir", s):
        return STAGE["lapsed"]
    return ""


def decided_stage(decision, country):
    if decision == "Approved":
        return STAGE["permit_issued"] if country == "US" else STAGE["approved"]
    if decision == UNVERIFIED:
        return STAGE["determined"]
    return closing_stage(decision)


def row(**values):
    result = {key: "" for key in FIELDS}
    result.update({k: text(v) for k, v in values.items() if k in result})
    result["country"] = result["country"] or ("US" if result["state"] in {"FL", "TX"} else "AU")
    return result


def normalize(values, since, until, *, infer_units=True):
    r = row(**values)
    if not r["council"] or not r["application_number"]:
        raise ValueError("Record is missing council or application_number")
    decided = date(r["date_decided"])
    if not decided or not since.isoformat() <= decided <= until.isoformat():
        return None
    if not is_residential(r["use"], r["description"]):
        return None
    decision = outcome(r["decision"])
    if not decision:
        return None
    count = r["units"]
    if count:
        try:
            numeric = float(count)
            if numeric < 0 or not numeric.is_integer():
                raise ValueError("Invalid unit count: " + count)
            count = int(numeric)
        except ValueError as exc:
            raise ValueError("Invalid unit count: " + count) from exc
    else:
        count = unit_count(r["description"]) if infer_units else None
    if count is not None and count < 10:
        return None
    r.update(date_decided=decided, date_lodged=date(r["date_lodged"]),
             decision=decision, units=text(count), units_known=str(count is not None).lower())
    r["country"] = r["country"] or ("US" if r["state"] in {"FL", "TX"} else "AU")
    if not r["storeys"]:
        r["storeys"] = text(storeys(r["description"]))
    r["etapa"] = decided_stage(decision, r["country"])
    return r


def unit_value(count):
    if count in (None, ""):
        return None
    try:
        numeric = float(count)
    except ValueError as exc:
        raise ValueError("Invalid unit count: " + text(count)) from exc
    if numeric < 0 or not numeric.is_integer():
        raise ValueError("Invalid unit count: " + text(count))
    return int(numeric)


def normalize_stage(values, since=None, until=None, *, filter_units=True):
    r = row(**values)
    if not r["council"] or not r["application_number"]:
        raise ValueError("Record is missing council or application_number")
    if not r["etapa"]:
        raise ValueError("Tracked record lacks a stage: " + r["application_number"])
    lodged = date(r["date_lodged"])
    if since and (not lodged or not since.isoformat() <= lodged <= until.isoformat()):
        return None
    if filter_units and not is_residential(r["use"], r["description"]):
        return None
    count = unit_value(r["units"])
    if filter_units and count is None:
        count = unit_count(r["description"])
    if filter_units and count is not None and count < 10:
        return None
    decision = STAGE_DECISION.get(r["etapa"], UNVERIFIED if r["etapa"] == STAGE["determined"] else "")
    r.update(date_lodged=lodged, date_decided=date(r["date_decided"]) if decision else "",
             decision=decision, units=text(count), units_known="true" if count is not None else "")
    if not r["storeys"]:
        r["storeys"] = text(storeys(r["description"]))
    return r


@dataclass
class Stats:
    source: str
    fetched: int = 0
    kept: int = 0
    approved: int = 0
    errors: int = 0
    lodged: int = 0
    rechecked: int = 0
    since: str = ""
    rejected: set = field(default_factory=set, repr=False)

    def error(self, logger, message, *args):
        self.errors += 1
        logger.error(message, *args)
