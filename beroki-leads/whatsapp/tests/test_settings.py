import unittest

from whatsapp import settings
from whatsapp.settings import SettingsError

BASE = {
    "CRM_API_URL": "https://crm.invalid",
    "CRM_API_KEY": "k",
    "VOLT_API_KEY": "k",
    "KAIRON_API_KEY": "k",
    "DA_WHATSAPP_VOLT_INSTANCE_ID": "inst",
    "DA_WHATSAPP_SENDER": "+61 491 570 110",
    "AGENT_URL": "https://agent.invalid",
    "DA_WHATSAPP_DRAFT_SECRET": "s",
    "DA_WHATSAPP_SERVICES": "Exterior renders\nInterior renders; Launch imagery",
}
SEND = {
    **BASE,
    "DA_WHATSAPP_SEND_ENABLED": "true",
    "GITHUB_ACTIONS": "true",
    "GITHUB_REF": "refs/heads/release",
    "DA_WHATSAPP_DEFAULT_BRANCH": "release",
}


class SettingsTest(unittest.TestCase):
    def test_dry_run_defaults(self):
        loaded = settings.load(BASE, "dry-run")
        self.assertEqual((loaded.batch, loaded.sender), (3, "61491570110"))
        self.assertEqual(loaded.services, ("Exterior renders", "Interior renders", "Launch imagery"))

    def test_missing_credentials_are_named(self):
        with self.assertRaisesRegex(SettingsError, "VOLT_API_KEY"):
            settings.load({**BASE, "VOLT_API_KEY": ""}, "dry-run")

    def test_batch_is_validated(self):
        self.assertEqual(settings.load({**BASE, "DA_WHATSAPP_BATCH_SIZE": "5"}, "dry-run").batch, 5)
        for bad in ("0", "11", "-1", "3.5", "three"):
            with self.assertRaises(SettingsError):
                settings.load({**BASE, "DA_WHATSAPP_BATCH_SIZE": bad}, "dry-run")

    def test_services_are_validated(self):
        for bad in (" ; \n ", ";".join(["Renders"] * 9), "x" * 121):
            with self.assertRaises(SettingsError):
                settings.load({**BASE, "DA_WHATSAPP_SERVICES": bad}, "dry-run")
        with self.assertRaisesRegex(SettingsError, "DA_WHATSAPP_DRAFT_SECRET"):
            settings.load({**BASE, "DA_WHATSAPP_DRAFT_SECRET": ""}, "dry-run")

    def test_send_mode_guards(self):
        self.assertEqual(settings.load(SEND, "send").mode, "send")
        for change in (
            {"DA_WHATSAPP_SEND_ENABLED": "false"},
            {"DA_WHATSAPP_SEND_ENABLED": "TRUE"},
            {"GITHUB_ACTIONS": ""},
            {"GITHUB_REF": "refs/heads/feature"},
            {"GITHUB_REF": "refs/pull/1/merge"},
            {"DA_WHATSAPP_DEFAULT_BRANCH": ""},
        ):
            with self.assertRaises(SettingsError, msg=str(change)):
                settings.load({**SEND, **change}, "send")

    def test_unknown_mode(self):
        with self.assertRaises(SettingsError):
            settings.load(BASE, "schedule")


if __name__ == "__main__":
    unittest.main()
