import unittest

from whatsapp import phones


class NormalizeTest(unittest.TestCase):
    def reason(self, raw):
        return phones.normalize(raw).reason

    def test_australian_mobile_becomes_e164(self):
        result = phones.normalize("+61 491 570 006")
        self.assertIsNone(result.reason)
        self.assertEqual(result.phone.e164, "+61491570006")
        self.assertEqual(result.phone.jid, "61491570006@s.whatsapp.net")
        self.assertEqual(phones.normalize("0061 491 570 006").phone.e164, "+61491570006")

    def test_united_states_number_needs_a_us_area_code(self):
        self.assertEqual(phones.normalize("+1 (212) 555-0123").phone.country, "US")
        self.assertEqual(self.reason("+1 416 555 0123"), "phone_other_country")
        self.assertEqual(self.reason("+1 876 555 0123"), "phone_other_country")

    def test_number_without_country_code_is_ambiguous(self):
        self.assertEqual(self.reason("0491 570 006"), "phone_ambiguous")
        self.assertEqual(self.reason("61491570006"), "phone_ambiguous")

    def test_two_numbers_or_an_extension_are_ambiguous(self):
        self.assertEqual(self.reason("+61 491 570 006 / +61 491 570 156"), "phone_ambiguous")
        self.assertEqual(self.reason("+61 491 570 006, +61 491 570 156"), "phone_ambiguous")
        self.assertEqual(self.reason("+1 212 555 0123 ext 4"), "phone_ambiguous")
        self.assertEqual(self.reason("+61 491 570 006 or +61 491 570 156"), "phone_ambiguous")

    def test_invalid_missing_and_landline(self):
        self.assertEqual(self.reason("+61 12"), "phone_invalid")
        self.assertEqual(self.reason(None), "phone_missing")
        self.assertEqual(self.reason("  "), "phone_missing")
        self.assertEqual(self.reason("+61 7 5550 1234"), "phone_not_mobile")


if __name__ == "__main__":
    unittest.main()
