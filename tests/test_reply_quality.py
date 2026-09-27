"""Conversation outcomes that matter to a recipient, not only status codes."""

import unittest

from demo import CATEGORIES, CUSTOMERS, MERCHANTS, TRIGGERS
from engine import answer_question, draft_reply, reply_in_language, reply_intent


def case(trigger_id):
    event = TRIGGERS[trigger_id]
    merchant = MERCHANTS[event["merchant_id"]]
    return merchant, CATEGORIES[merchant["category_slug"]], event, CUSTOMERS.get(event.get("customer_id"))


class ReplyQualityTests(unittest.TestCase):
    def test_hinglish_yes_and_cost_question_have_separate_intents(self):
        self.assertEqual(reply_intent("Haan, details bhejo"), "yes")
        self.assertEqual(reply_intent("Kitna cost hoga?"), "question")
        self.assertEqual(reply_intent("Haan, but kitna cost hoga?"), "question")
        self.assertEqual(reply_intent("What is next?"), "question")
        self.assertEqual(reply_intent("message band karo"), "stop")

    def test_pharmacy_alert_yes_yields_stock_check_without_claiming_it_happened(self):
        m, c, t, u = case("trg_018_supply_atorvastatin_recall")
        draft = draft_reply(m, c, t, u)
        self.assertIn("Stock-check draft", draft)
        self.assertIn("Stock has not been checked", draft)
        self.assertIn("pharmacist", draft)

    def test_planning_yes_creates_customer_copy_not_a_group_price(self):
        m, c, t, u = case("trg_013_corporate_thali_planning")
        draft = draft_reply(m, c, t, u)
        self.assertIn("group size", draft)
        self.assertIn("separate bulk quote", draft)
        self.assertNotIn("₹149", draft)
        answer = answer_question("Kitna cost hoga?", m, c, t, u)
        self.assertIn("price", answer)
        self.assertIn("group quote", answer)

    def test_customer_hinglish_yes_has_customer_specific_draft(self):
        m, c, t, u = case("trg_003_recall_due_priya")
        answer = reply_in_language(draft_reply(m, c, t, u), "Haan, details bhejo", "yes")
        self.assertIn(u["identity"]["name"], answer)
        self.assertIn("Bilkul", answer)
        self.assertIn("No appointment has been booked", answer)


if __name__ == "__main__":
    unittest.main()
