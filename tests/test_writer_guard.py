"""Reject attractive AI rewrites that alter a fact or an offer's meaning."""

import unittest

from judge_eval import sample_cases
from writer import valid


class WriterGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {case_id: (message, category, merchant, trigger, customer)
                     for case_id, message, category, merchant, trigger, customer in sample_cases()}

    def context_for(self, case_id):
        message, category, merchant, trigger, customer = self.cases[case_id]
        baseline = message["body"]
        anchors = [o["title"] for o in merchant.get("offers", [])
                   if o.get("status") == "active" and o.get("title")
                   and o["title"].casefold() in baseline.casefold()]
        return baseline, {"customer": {"identity": customer["identity"]} if customer else None,
                          "merchant": {"identity": merchant["identity"]}, "fact_anchors": anchors}

    def test_exact_grounded_message_is_allowed(self):
        for case in ("T01", "T13", "T21", "T26"):
            baseline, context = self.context_for(case)
            self.assertTrue(valid(baseline, baseline, context), case)

    def test_new_number_from_unrelated_merchant_field_is_rejected(self):
        baseline, context = self.context_for("T26")
        self.assertFalse(valid(baseline.replace("15%", "18%"), baseline, context))

    def test_same_price_attached_to_new_service_is_rejected(self):
        baseline, context = self.context_for("T26")
        self.assertFalse(valid(baseline.replace("First Month @ ₹499", "Kids Yoga @ ₹499"),
                               baseline, context))

    def test_reversed_direction_and_free_claim_rejected(self):
        baseline, context = self.context_for("T26")
        self.assertFalse(valid(baseline.replace("up 15%", "down 15%"), baseline, context))
        self.assertFalse(valid(baseline + " Free membership included.", baseline, context))

    def test_customer_name_and_price_cannot_disappear(self):
        baseline, context = self.context_for("T13")
        self.assertFalse(valid(baseline.replace("Rashmi", "Member"), baseline, context))
        baseline, context = self.context_for("T01")
        self.assertFalse(valid(baseline.replace("₹149", ""), baseline, context))


if __name__ == "__main__":
    unittest.main()
