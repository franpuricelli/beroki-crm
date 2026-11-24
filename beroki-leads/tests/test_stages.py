import argparse
import csv
import datetime as dt
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from pipeline import run
from pipeline.candidates import select, select_lodged
from pipeline.common import FIELDS, PREVIOUS_FIELDS, Stats, normalize, normalize_stage
from pipeline.documents import first_plan, form_units, is_plan
from pipeline.sources.developmenti import CHANGE_APPLICATION, VERSIONED, brisbane_customer_stage, goldcoast_stage, is_mcu
from pipeline.storage import read_rows, upsert

TODAY = dt.date(2026, 11, 24)
SINCE = dt.date(2026, 11, 1)
DESCRIPTION = "Material Change of Use - Multiple Dwelling x 40"


def lodged(stage="presentado", **values):
    return normalize_stage(dict(council="Gold Coast", state="QLD", application_number="MCU/2026/1",
                                description=DESCRIPTION, use="Residential", date_lodged="2026-11-10",
                                etapa=stage, plans_url="https://example.org/plans", **values), SINCE, TODAY)


def decided(decision="Approved", **values):
    return normalize(dict(council="Gold Coast", state="QLD", application_number="MCU/2026/1",
                          description=DESCRIPTION, use="Residential", date_lodged="2026-11-10",
                          date_decided="2026-11-20", decision=decision, **values), SINCE, TODAY)


def tracked(stage, date_decided=""):
    return normalize_stage(dict(council="Gold Coast", state="QLD", application_number="MCU/2026/1",
                                description=DESCRIPTION, use="Residential", date_lodged="2026-11-10",
                                date_decided=date_decided, etapa=stage), filter_units=False)


class UpsertStages(unittest.TestCase):
    def test_lodged_then_approved_is_the_same_row(self):
        rows = {}
        upsert(rows, [lodged()], "2026-11-11T00:00:00+00:00")
        first_seen = rows[("Gold Coast", "MCU/2026/1")]["first_seen"]
        inserted, updated, _, changes = upsert(rows, [decided()], "2026-11-21T00:00:00+00:00")
        self.assertEqual((inserted, updated, len(rows)), (0, 1, 1))
        row = rows[("Gold Coast", "MCU/2026/1")]
        self.assertEqual(row["etapa"], "aprobado")
        self.assertEqual(row["decision"], "Approved")
        self.assertEqual(row["etapa_desde"], "2026-11-20")
        self.assertEqual(row["historial_etapas"], "presentado:2026-11-10;aprobado:2026-11-20")
        self.assertEqual(row["first_seen"], first_seen)
        self.assertEqual(row["last_updated"], "2026-11-21T00:00:00+00:00")
        self.assertEqual(row["plans_url"], "https://example.org/plans")
        self.assertEqual(changes[0]["from"], "presentado")

    def test_lodged_then_refused(self):
        rows = {}
        upsert(rows, [lodged()], "2026-11-11T00:00:00+00:00")
        upsert(rows, [tracked("info_request")], "2026-11-15T00:00:00+00:00")
        upsert(rows, [tracked("rechazado", "2026-11-22")], "2026-11-23T00:00:00+00:00")
        row = rows[("Gold Coast", "MCU/2026/1")]
        self.assertEqual(row["etapa"], "rechazado")
        self.assertEqual(row["decision"], "Refused")
        self.assertEqual(row["units"], "40")
        self.assertEqual(row["historial_etapas"],
                         "presentado:2026-11-10;info_request:2026-11-15;rechazado:2026-11-22")

    def test_directly_approved(self):
        rows = {}
        upsert(rows, [decided()], "2026-11-21T00:00:00+00:00")
        row = rows[("Gold Coast", "MCU/2026/1")]
        self.assertEqual((row["etapa"], row["etapa_desde"]), ("aprobado", "2026-11-20"))
        self.assertEqual(row["historial_etapas"], "aprobado:2026-11-20")

    def test_open_stage_never_replaces_a_final_one(self):
        rows = {}
        upsert(rows, [decided()], "2026-11-21T00:00:00+00:00")
        _, updated, unchanged, changes = upsert(rows, [lodged("en_evaluacion")], "2026-11-22T00:00:00+00:00")
        self.assertEqual((updated, unchanged), (0, 1))
        self.assertEqual(rows[("Gold Coast", "MCU/2026/1")]["etapa"], "aprobado")
        self.assertEqual(changes[0]["ignored"], "final stage kept")

    def test_us_permit_stage(self):
        row = normalize(dict(council="Austin", state="TX", application_number="MASTER:1", description="Apartments",
                             use="Apartments", units=50, date_decided="2026-11-20", decision="Approved"),
                        SINCE, TODAY)
        self.assertEqual(row["etapa"], "permiso_emitido")


class ReadPreviousSchema(unittest.TestCase):
    def test_previous_file_gets_a_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "approvals.csv"
            row = {f: "" for f in PREVIOUS_FIELDS}
            row.update(council="Brisbane", state="QLD", application_number="A1", decision="Approved",
                       date_decided="2026-10-01", first_seen="2026-10-02T00:00:00+00:00", country="AU")
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=PREVIOUS_FIELDS)
                writer.writeheader()
                writer.writerow(row)
            loaded = read_rows(path)[("Brisbane", "A1")]
            self.assertEqual(loaded["etapa"], "aprobado")
            self.assertEqual(loaded["historial_etapas"], "aprobado:2026-10-01")


class RunTwice(unittest.TestCase):
    def execute(self, db, results, recheck=None):
        args = argparse.Namespace(since=SINCE, lodged_since=SINCE, no_lodged=False, recheck=recheck, db_dir=db,
                                  sources=["goldcoast"], include_plansa=False, workers=1, timeout=1)

        def fake(name, since, until, timeout, lodged_since=None, numbers=()):
            stats = Stats(name)
            stats.rechecked = len(numbers)
            return stats, results

        with mock.patch.object(run, "collect", side_effect=fake), redirect_stdout(io.StringIO()) as out:
            run.execute(args)
        return json.loads(out.getvalue())

    def test_no_duplicate_across_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)
            self.execute(db, [lodged()])
            summary = self.execute(db, [decided()])
            rows = read_rows(db / "approvals.csv")
            self.assertEqual(list(rows), [("Gold Coast", "MCU/2026/1")])
            self.assertEqual(rows[("Gold Coast", "MCU/2026/1")]["etapa"], "aprobado")
            self.assertEqual(summary["stage_changes"][0]["to"], "aprobado")
            with (db / "approvals.csv").open() as f:
                self.assertEqual(next(csv.reader(f)), FIELDS)

    def test_lodged_and_decided_in_the_same_run(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)
            self.execute(db, [decided(), lodged("en_evaluacion")])
            rows = read_rows(db / "approvals.csv")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[("Gold Coast", "MCU/2026/1")]["etapa"], "aprobado")

    def test_open_rows_are_rechecked(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)
            self.execute(db, [lodged()])
            summary = self.execute(db, [])
            self.assertEqual(summary["recheck_requested"], 1)
            self.assertEqual(summary["sources"][0]["rechecked"], 1)


class RecheckFile(unittest.TestCase):
    def test_council_from_da_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "recheck.json"
            path.write_text(json.dumps([
                {"application_number": "A007111446",
                 "da_record": "https://developmenti.brisbane.qld.gov.au/Home/FilterDirect?filters=DANumber%3DA007111446"},
                {"council": "Gold Coast", "application_number": "MCU/2026/1"},
            ]))
            self.assertEqual(run.recheck_file(path), [("Brisbane", "A007111446"), ("Gold Coast", "MCU/2026/1")])

    def test_unknown_record_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "recheck.json"
            path.write_text(json.dumps([{"application_number": "X1", "da_record": "https://example.org"}]))
            with self.assertRaises(ValueError):
                run.recheck_file(path)


class Candidates(unittest.TestCase):
    def test_lodged_needs_plans_and_units(self):
        with_plans = {**lodged(), "first_seen": "", "last_updated": ""}
        without = {**with_plans, "application_number": "MCU/2026/2", "plans_url": ""}
        unknown = {**with_plans, "application_number": "MCU/2026/3", "units": "", "units_known": ""}
        result = select_lodged([with_plans, without, unknown])
        self.assertEqual([r["application_number"] for r in result["eligible"]], ["MCU/2026/1"])
        self.assertTrue(result["eligible"][0]["priority"])
        self.assertEqual(result["skipped"], {"unknown_units": 1, "under_min_units": 0, "no_plans": 1})
        self.assertEqual(select([with_plans])["eligible"], [])


class Parsers(unittest.TestCase):
    def test_form_units(self):
        form = ("d) Provide a brief description of the proposal (e.g. 6 unit apartment building defined as "
                "multi-unit dwelling, reconfiguration of 1 lot into 3 lots): 15 Storey Multiple Dwelling e) "
                "Relevant plans ... Number of dwelling units (if applicable) Gross floor area (m2) (if applicable) "
                "Multiple Dwelling Multiple dwelling means a residential use of premises involving 3 or more "
                "dwellings, whether attached or detached. 116 8.2) Does the proposed use")
        self.assertEqual(form_units(form), 116)

    def test_plan_detection(self):
        docs = [{"name": "Att G Landscape Concept Plan", "category": "Plan - Applicant Proposed", "url": "g"},
                {"name": "Plans - Civil Sketch Register", "url": "c"},
                {"name": "Appendix B - Architectural Plans", "url": "b"}]
        self.assertFalse(is_plan(docs[0]["name"], docs[0]["category"]))
        self.assertEqual(first_plan(docs), "b")

    def test_goldcoast_combined_application_is_mcu(self):
        description = "Combined Application Material Change of Use and Reconfiguring a Lot Multiple Dwelling x73"
        self.assertTrue(is_mcu("Combined Application", description, "Residential"))
        self.assertFalse(is_mcu("Minor Change", description, "Residential"))

    def test_change_applications_are_not_new_leads(self):
        self.assertTrue(CHANGE_APPLICATION.search("Caloundra - Minor Change to Existing Approval - Multiple Dwelling"))
        self.assertTrue(CHANGE_APPLICATION.search("Bokarina - Generally in Accordance - Multiple Dwelling Units"))
        self.assertTrue(VERSIONED.search("MCU25/0185.01"))
        self.assertFalse(CHANGE_APPLICATION.search("Material Change of Use - Multiple Dwelling (123 Units)"))
        self.assertFalse(VERSIONED.search("MCU26/0316"))

    def test_goldcoast_stage_table(self):
        rows = [{"name": "Pre-Assessment", "status": "", "stamps": [1, 1]},
                {"name": "Information Request", "status": "", "stamps": [2, 3]},
                {"name": "Response to Information Request", "status": "", "stamps": [3, 0]},
                {"name": "Decision", "status": "", "stamps": [0, 0]}]
        self.assertEqual(goldcoast_stage(rows), "info_request")

    def test_brisbane_with_customer(self):
        sent = [{"name": "Information Request Sent Date", "status": "Completed", "stamps": [1]},
                {"name": "Final Response Received Date", "status": "", "stamps": [0]}]
        self.assertEqual(brisbane_customer_stage(sent), "info_request")
        self.assertEqual(brisbane_customer_stage(sent[1:]), "presentado")


if __name__ == "__main__":
    unittest.main()
