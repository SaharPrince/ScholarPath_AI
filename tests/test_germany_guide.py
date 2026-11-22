import unittest

from app import main as api
from app.germany_guide import GUIDE_VERSION, get_germany_guide


class GermanyGuideTests(unittest.TestCase):
    def test_guide_has_ordered_practical_sections(self):
        guide = get_germany_guide()
        ids = [section["id"] for section in guide["sections"]]
        self.assertEqual(ids[0], "before-you-apply")
        self.assertIn("flight-from-pakistan", ids)
        self.assertIn("accommodation", ids)
        self.assertIn("pakistani-community", ids)
        self.assertIn("first-weeks", ids)
        self.assertEqual(guide["version"], GUIDE_VERSION)

    def test_every_item_has_short_bullets_and_valid_official_links(self):
        guide = get_germany_guide()
        self.assertGreaterEqual(len(guide["sections"]), 7)
        for section in guide["sections"]:
            self.assertTrue(section["title"])
            self.assertTrue(section["items"])
            for item in section["items"]:
                self.assertTrue(item["title"])
                self.assertGreaterEqual(len(item["bullets"]), 1)
                self.assertLessEqual(len(item["bullets"]), 5)
                for link in item["links"]:
                    self.assertTrue(link["url"].startswith("https://"))
                    self.assertTrue(link["label"])

    def test_guide_includes_minor_safety_and_housing_scams(self):
        guide = get_germany_guide()
        all_bullets = " ".join(
            bullet
            for section in guide["sections"]
            for item in section["items"]
            for bullet in item["bullets"]
        ).lower()
        self.assertIn("under 18", all_bullets)
        self.assertIn("scam", all_bullets)
        self.assertIn("parent/legal guardian", all_bullets)

    def test_guide_api_returns_the_catalogue(self):
        result = api.germany_guide()
        self.assertEqual(result["country"], "Germany")
        self.assertEqual(result["audience"], "Students planning to travel from Pakistan")
        self.assertGreaterEqual(len(result["sections"]), 7)
        self.assertIn("confirm details", result["notice"].lower())


if __name__ == "__main__":
    unittest.main()
