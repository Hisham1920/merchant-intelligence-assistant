"""Reject attractive AI rewrites that alter a fact or an offer's meaning."""

import unittest
import io
import json
from unittest.mock import patch

from judge_eval import sample_cases
from writer import improve, valid


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

    def test_dates_prices_and_metrics_remain_attached_to_the_right_fact(self):
        baseline, context = self.context_for("T28")
        swapped_dates = baseline.replace("12 Nov", "05 Nov").replace(
            "05 Nov at 6:00", "12 Nov at 6:00")
        self.assertFalse(valid(swapped_dates, baseline, context))

        baseline, context = self.context_for("T09")
        swapped_prices = baseline.replace(
            "Their listed offer is Dental Cleaning @ ₹199. Your current offer is Dental Cleaning @ ₹299.",
            "Their listed offer is Dental Cleaning @ ₹299. Your current offer is Dental Cleaning @ ₹199.")
        self.assertFalse(valid(swapped_prices, baseline, context))

        baseline, context = self.context_for("T26")
        misplaced_metric = baseline.replace("Your calls are up 15% over 7 days.",
                                            "Your First Month offer is up 15% over 7 days.")
        self.assertFalse(valid(misplaced_metric, baseline, context))

    def test_listing_status_cannot_reverse_without_changing_a_number(self):
        baseline, context = self.context_for("T24")
        self.assertFalse(valid(baseline.replace("marked unverified", "marked verified"),
                               baseline, context))

    def test_safe_cta_wording_can_still_change(self):
        baseline, context = self.context_for("T24")
        candidate = baseline.replace("Want a short listing checklist and patient-friendly post draft for your clinic?",
                                     "Would a short checklist and patient-friendly post draft for your clinic help?")
        self.assertTrue(valid(candidate, baseline, context))

    def test_unsafe_model_response_falls_back_to_grounded_message(self):
        message, category, merchant, trigger, customer = self.cases["T28"]
        unsafe = message["body"].replace("12 Nov", "05 Nov").replace(
            "05 Nov at 6:00", "12 Nov at 6:00")
        response = {"choices": [{"message": {"content": json.dumps({"body": unsafe})}}]}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch(
            "writer.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())
        ):
            self.assertEqual(improve(message, category, merchant, trigger, customer), message)

    def test_safe_model_response_can_polish_the_call_to_action(self):
        message, category, merchant, trigger, customer = self.cases["T24"]
        candidate = message["body"].replace(
            "Want a short listing checklist and patient-friendly post draft for your clinic?",
            "Would a short checklist and patient-friendly post draft for your clinic help?")
        response = {"choices": [{"message": {"content": json.dumps({"body": candidate})}}]}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch(
            "writer.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())
        ):
            actual = improve(message, category, merchant, trigger, customer)
        self.assertEqual(actual["body"], candidate)


if __name__ == "__main__":
    unittest.main()
