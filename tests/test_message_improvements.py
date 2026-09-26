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


if __name__ == "__main__":
    unittest.main()
