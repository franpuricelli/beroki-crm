import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from whatsapp import hours
from whatsapp.config import WHATSAPP

from .fakes import utc


def zones(country, verified=None):
    return hours.contact_zones(country, verified).zones


class ZoneListTest(unittest.TestCase):
    def test_every_configured_zone_exists(self):
        for names in WHATSAPP["zones"].values():
            for name in names:
                ZoneInfo(name)

    def test_zone_lists_cover_the_iana_country_table(self):
        table = Path("/usr/share/zoneinfo/zone.tab")
        if not table.exists():
            self.skipTest("no zone.tab on this machine")
        listed = {"AU": set(), "US": set()}
        for line in table.read_text().splitlines():
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if parts[0] in listed:
                listed[parts[0]].add(parts[2])
        for country, names in listed.items():
            self.assertTrue(names <= set(WHATSAPP["zones"][country]), country)

    def test_unknown_country_is_unclear(self):
        self.assertEqual(hours.contact_zones("NZ", None).reason, "zone_unclear")

    def test_verified_zone_outside_the_phone_country_conflicts(self):
        self.assertEqual(hours.contact_zones("AU", "America/New_York").reason, "zone_conflict")
        self.assertEqual(hours.contact_zones("AU", "Australia/Brisbane").zones.names, ("Australia/Brisbane",))


class ExactZoneWindowTest(unittest.TestCase):
    def test_start_is_inclusive_and_end_is_exclusive(self):
        brisbane = zones("AU", "Australia/Brisbane")
        self.assertFalse(hours.in_window(utc(2026, 11, 22, 22, 59, 59), brisbane))
        self.assertTrue(hours.in_window(utc(2026, 11, 22, 23, 0), brisbane))
        self.assertTrue(hours.in_window(utc(2026, 11, 23, 6, 59, 59), brisbane))
        self.assertFalse(hours.in_window(utc(2026, 11, 23, 7, 0), brisbane))

    def test_local_weekend_is_closed(self):
        brisbane = zones("AU", "Australia/Brisbane")
        self.assertFalse(hours.in_window(utc(2026, 11, 28, 1, 0), brisbane))
        self.assertFalse(hours.in_window(utc(2026, 11, 29, 1, 0), brisbane))
        self.assertTrue(hours.in_window(utc(2026, 11, 29, 23, 30), brisbane))

    def test_naive_time_is_refused(self):
        import datetime as dt
        with self.assertRaises(ValueError):
            hours.is_business_time(dt.datetime(2026, 11, 25, 3, 0), "Australia/Brisbane")


class AllZonesWindowTest(unittest.TestCase):
    def test_australia_intersection_moves_with_daylight_saving(self):
        australia = zones("AU")
        self.assertTrue(hours.in_window(utc(2026, 11, 25, 3, 17), australia))
        self.assertFalse(hours.in_window(utc(2026, 11, 25, 6, 17), australia))
        self.assertTrue(hours.in_window(utc(2026, 7, 15, 6, 17), australia))
        self.assertFalse(hours.in_window(utc(2026, 11, 25, 1, 17), australia))

    def test_australia_closes_when_one_zone_is_outside(self):
        australia = zones("AU")
        self.assertFalse(hours.in_window(utc(2026, 11, 26, 23, 17), australia))

    def test_united_states_intersection_moves_with_daylight_saving(self):
        states = zones("US")
        self.assertTrue(hours.in_window(utc(2026, 11, 25, 21, 17), states))
        self.assertFalse(hours.in_window(utc(2026, 7, 15, 21, 17), states))
        self.assertTrue(hours.in_window(utc(2026, 7, 15, 19, 17), states))
        self.assertFalse(hours.in_window(utc(2026, 11, 25, 18, 17), states))

    def test_united_states_week_ends_on_friday_afternoon(self):
        states = zones("US")
        self.assertTrue(hours.in_window(utc(2026, 11, 27, 21, 17), states))
        self.assertFalse(hours.in_window(utc(2026, 11, 28, 21, 17), states))

    def test_spring_forward_monday(self):
        states = zones("US")
        self.assertFalse(hours.in_window(utc(2026, 3, 9, 21, 17), states))
        self.assertTrue(hours.in_window(utc(2026, 3, 9, 20, 17), states))
        eastern = zones("US", "America/New_York")
        self.assertTrue(hours.in_window(utc(2026, 3, 9, 13, 0), eastern))
        self.assertFalse(hours.in_window(utc(2026, 3, 9, 12, 59), eastern))

    def test_autumn_back_monday_in_sydney(self):
        sydney = zones("AU", "Australia/Sydney")
        self.assertTrue(hours.in_window(utc(2026, 4, 5, 23, 0), sydney))
        self.assertFalse(hours.in_window(utc(2026, 4, 5, 22, 59), sydney))


if __name__ == "__main__":
    unittest.main()
