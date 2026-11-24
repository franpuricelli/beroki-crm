LEAD = {
    "min_units": 10,
    "priority_units": 20,
    "approved_decision": "Approved",
    "lookback_days": 14,
}

STAGE = {
    "lodged": "presentado",
    "assessment": "en_evaluacion",
    "info_request": "info_request",
    "notification": "notificacion_publica",
    "approved": "aprobado",
    "refused": "rechazado",
    "withdrawn": "retirado",
    "lapsed": "caducado",
    "permit_review": "permiso_en_revision",
    "permit_issued": "permiso_emitido",
    "determined": "determinado",
}

OPEN_STAGES = (
    STAGE["lodged"], STAGE["assessment"], STAGE["info_request"],
    STAGE["notification"], STAGE["permit_review"],
)
APPROVED_STAGES = (STAGE["approved"], STAGE["permit_issued"])
CLOSED_STAGES = (STAGE["refused"], STAGE["withdrawn"], STAGE["lapsed"])
FINAL_STAGES = APPROVED_STAGES + CLOSED_STAGES
STAGE_DECISION = {
    STAGE["approved"]: "Approved",
    STAGE["permit_issued"]: "Approved",
    STAGE["refused"]: "Refused",
    STAGE["withdrawn"]: "Withdrawn",
    STAGE["lapsed"]: "Lapsed",
}

DOCUMENTS = {
    "max_bytes": 20_000_000,
    "form_pages": 12,
}

RECORD_HOSTS = {
    "developmenti.brisbane.qld.gov.au": "Brisbane",
    "developmenti.goldcoast.qld.gov.au": "Gold Coast",
    "developmenti.sunshinecoast.qld.gov.au": "Sunshine Coast",
}
