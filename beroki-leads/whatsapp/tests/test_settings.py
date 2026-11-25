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
}
SEND = {
    **BASE,
    "DA_WHATSAPP_SEND_ENABLED": "true",
    "GITHUB_ACTIONS": "true",
    "GITHUB_REF": "refs/heads/release",
    "DA_WHATSAPP_DEFAULT_BRANCH": "release",
    "DA_WHATSAPP_MESSAGE": "Hi {first_name}, fictional approved text.",
}


class SettingsTest(unittest.TestCase):
    def test_dry_run_defaults(self):
        loaded = settings.load(BASE, "dry-run")
        self.assertEqual((loaded.batch, loaded.message, loaded.sender), (3, None, "61491570110"))

    def test_missing_credentials_are_named(self):
        with self.assertRaisesRegex(SettingsError, "VOLT_API_KEY"):
            settings.load({**BASE, "VOLT_API_KEY": ""}, "dry-run")

    def test_batch_is_validated(self):
        self.assertEqual(settings.load({**BASE, "DA_WHATSAPP_BATCH_SIZE": "5"}, "dry-run").batch, 5)
        for bad in ("0", "11", "-1", "3.5", "three"):
            with self.assertRaises(SettingsError):
                settings.load({**BASE, "DA_WHATSAPP_BATCH_SIZE": bad}, "dry-run")

    def test_message_is_validated(self):
        for bad in ("Hi {name}", "Hi {first_name", "x" * 1001):
            with self.assertRaises(SettingsError):
                settings.load({**BASE, "DA_WHATSAPP_MESSAGE": bad}, "dry-run")

    def test_send_mode_guards(self):
        self.assertEqual(settings.load(SEND, "send").mode, "send")
        for change in (
            {"DA_WHATSAPP_SEND_ENABLED": "false"},
            {"DA_WHATSAPP_SEND_ENABLED": "TRUE"},
            {"GITHUB_ACTIONS": ""},
            {"GITHUB_REF": "refs/heads/feature"},
            {"GITHUB_REF": "refs/pull/1/merge"},
            {"DA_WHATSAPP_DEFAULT_BRANCH": ""},
            {"DA_WHATSAPP_MESSAGE": ""},
        ):
            with self.assertRaises(SettingsError, msg=str(change)):
                settings.load({**SEND, **change}, "send")

    def test_unknown_mode(self):
        with self.assertRaises(SettingsError):
            settings.load(BASE, "schedule")


if __name__ == "__main__":
    unittest.main()
