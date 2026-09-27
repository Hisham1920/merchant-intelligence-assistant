"""Keep the scorecard improvements tied to actual supplied facts."""

from copy import deepcopy
import unittest

from engine import compose
from judge_eval import sample_cases


class MessageImprovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {test_id: (category, merchant, trigger, customer)
                     for test_id, _, category, merchant, trigger, customer in sample_cases()}

    def test_webinar_details_are_grounded_in_calendar(self):
        category, merchant, trigger, customer = self.cases["T06"]
        text = compose(category, merchant, trigger, customer)["body"]
        self.assertIn("2 CDE credits", text)
        self.assertIn("02 May", text)
        self.assertIn("Dr. Meera", text)
        self.assertIn("Free for IDA members", text)

    def test_no_performance_claim_without_performance_data(self):
        category, merchant, trigger, customer = self.cases["T11"]
        self.assertIn("20%", compose(category, merchant, trigger, customer)["body"])
        missing = deepcopy(merchant)
        missing["performance"].pop("delta_7d", None)
        text = compose(category, missing, trigger, customer)["body"]
        self.assertNotIn("20%", text)
        self.assertIn("what service", text.lower())

    def test_revised_cases_use_all_five_categories_and_stay_short(self):
        from judge_eval import sample_cases
        cases = list(sample_cases())
        self.assertEqual({category["slug"] for _, _, category, *_ in cases},
                         {"dentists", "salons", "restaurants", "gyms", "pharmacies"})
        self.assertTrue(all(len(message["body"]) <= 550 for _, message, *_ in cases))

    def test_match_day_does_not_advertise_weekday_offer_on_sunday(self):
        category, merchant, trigger, customer = self.cases["T21"]
        text = compose(category, merchant, trigger, customer)["body"]
        self.assertIn("SK Pizza Junction", text)
        self.assertIn("Sant Nagar", text)
        self.assertNotIn("Buy 1 Pizza Get 1 Free", text)

    def test_pharmacy_directions_are_read_without_inventing_percent_units(self):
        category, merchant, trigger, customer = self.cases["T05"]
        text = compose(category, merchant, trigger, customer)["body"]
        self.assertIn("rising for ORS", text)
        self.assertIn("falling for cold and cough", text)
        self.assertNotIn("40%", text)
        invalid = deepcopy(trigger)
        invalid["payload"]["trends"] = ["unknown_trend"]
        self.assertIsNone(compose(category, merchant, invalid, customer))

    def test_performance_and_offer_only_when_source_contains_them(self):
        category, merchant, trigger, customer = self.cases["T26"]
        text = compose(category, merchant, trigger, customer)["body"]
        self.assertIn("15% over 7 days", text)
        self.assertIn("First Month @ ₹499", text)
        unoffered = deepcopy(merchant)
        unoffered["offers"] = []
        self.assertNotIn("₹499", compose(category, unoffered, trigger, customer)["body"])
        no_driver = deepcopy(trigger)
        no_driver["payload"].pop("likely_driver")
        self.assertNotIn("kids yoga post", compose(category, merchant, no_driver, customer)["body"])


if __name__ == "__main__":
    unittest.main()
