import datetime as dt
import math
import statistics
from collections import defaultdict

from .common import date, months_before
from .config import CLOSED_STAGES
from .storage import from_lodgement


FIELDS = ["council", "state", "approved_6m", "all_kept_6m", "approved_12m", "all_kept_12m"]
for window in ["6m", "12m"]:
    for basis in ["approved", "all_kept"]:
        FIELDS += [f"median_days_{basis}_{window}", f"mean_days_{basis}_{window}"]
FIELDS += ["last_decision_date", "suggested_check_interval_days",
           "lodged_6m", "lodged_12m", "median_days_lodged_12m", "mean_days_lodged_12m", "last_lodged_date"]


def intervals(rows, field="date_decided"):
    days = sorted(dt.date.fromisoformat(r[field]) for r in rows)
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    if not gaps:
        return "", ""
    return f"{statistics.median(gaps):g}", f"{statistics.mean(gaps):.6f}".rstrip("0").rstrip(".")


def calculate(rows, today):
    councils = defaultdict(list)
    for r in rows:
        councils[(r["council"], r["state"])].append(r)
    result = []
    for (council, state), records in sorted(councils.items()):
        out = {"council": council, "state": state}
        for months in [6, 12]:
            selected = [r for r in records if date(r["date_decided"]) and r["etapa"] not in CLOSED_STAGES
                        and str(months_before(today, months)) <= r["date_decided"] <= str(today)]
            approved = [r for r in selected if r["decision"] == "Approved"]
            out[f"all_kept_{months}m"] = len(selected)
            out[f"approved_{months}m"] = len(approved)
            for basis, subset in [("approved", approved), ("all_kept", selected)]:
                median, mean = intervals(subset)
                out[f"median_days_{basis}_{months}m"] = median
                out[f"mean_days_{basis}_{months}m"] = mean
        valid_dates = [r["date_decided"] for r in records if date(r["date_decided"])
                       and r["date_decided"] <= str(today)]
        out["last_decision_date"] = max(valid_dates, default="")
        median = out["median_days_approved_12m"] or out["median_days_all_kept_12m"]
        out["suggested_check_interval_days"] = min(7, max(1, math.floor(float(median) / 2))) if median else 7
        lodged = [r for r in records if from_lodgement(r) and date(r["date_lodged"]) and r["date_lodged"] <= str(today)]
        for months in [6, 12]:
            out[f"lodged_{months}m"] = sum(r["date_lodged"] >= str(months_before(today, months)) for r in lodged)
        recent = [r for r in lodged if r["date_lodged"] >= str(months_before(today, 12))]
        out["median_days_lodged_12m"], out["mean_days_lodged_12m"] = intervals(recent, "date_lodged")
        out["last_lodged_date"] = max((r["date_lodged"] for r in lodged), default="")
        result.append(out)
    return result
