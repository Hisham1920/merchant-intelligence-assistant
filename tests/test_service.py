import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient


TEMP = tempfile.TemporaryDirectory()
os.environ["VERA_DB"] = str(Path(TEMP.name) / "test.sqlite3")

from app import app, connect, LOCK  # noqa: E402


DATA = Path(__file__).resolve().parents[1] / "dataset"
SEEDS = {
    "merchant": json.loads((DATA / "merchants_seed.json").read_text())["merchants"],
    "customer": json.loads((DATA / "customers_seed.json").read_text())["customers"],
    "trigger": json.loads((DATA / "triggers_seed.json").read_text())["triggers"],
}
CATEGORY = json.loads((DATA / "categories" / "dentists.json").read_text())


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        with LOCK, connect() as db:
            for table in ("contexts", "sent", "conversations", "opt_out", "auto_replies", "compositions"):
                db.execute(f"DELETE FROM {table}")

    def push(self, scope, payload, version=1):
        identity = {"category": "slug", "merchant": "merchant_id",
                    "customer": "customer_id", "trigger": "id"}[scope]
        return self.client.post("/v1/context", json={"scope": scope,
            "context_id": payload[identity], "version": version, "payload": payload})

    def dentist(self):
        merchant = SEEDS["merchant"][0]
        self.push("category", CATEGORY)
        self.push("merchant", merchant)
        return merchant

    def tick(self, trigger, now="2026-04-26T10:00:00Z"):
        return self.client.post("/v1/tick", json={"now": now,
            "available_triggers": [trigger["id"]]})

    def test_versioned_push_and_health(self):
        self.dentist()
        self.assertEqual(self.client.get("/v1/healthz").json()["contexts_loaded"]["merchant"], 1)
        merchant = copy.deepcopy(SEEDS["merchant"][0])
        merchant["performance"]["calls"] = 42
        self.assertTrue(self.push("merchant", merchant, 2).json()["accepted"])
        self.assertEqual(self.push("merchant", SEEDS["merchant"][0], 1).status_code, 409)
        self.assertTrue(self.push("merchant", SEEDS["merchant"][0], 2).json()["accepted"])
        trigger = SEEDS["trigger"][0]
        self.push("trigger", trigger)
        self.assertEqual(self.tick(trigger).status_code, 200)

    def test_seed_event_grounded_and_no_repeat(self):
        self.dentist()
        trigger = SEEDS["trigger"][0]
        self.push("trigger", trigger)
        first = self.tick(trigger).json()["actions"]
        self.assertEqual(len(first), 1)
        self.assertIn("JIDA", first[0]["body"])
        self.assertEqual(first[0]["send_as"], "vera")
        self.assertEqual(len(first[0]["template_params"]), 1)
        self.assertEqual(self.tick(trigger).json()["actions"], [])

    def test_version_bump_informs_new_message(self):
        self.dentist()
        old = SEEDS["trigger"][0]
        self.push("trigger", old)
        self.tick(old)
        category = copy.deepcopy(CATEGORY)
        category["digest"].append({"id": "new_2026", "title": "New dentist topic for May",
                                   "source": "Practice digest", "summary": "Check the updated guidance."})
        self.push("category", category, 2)
        new = copy.deepcopy(old)
        new.update(id="trg_new", suppression_key="research:new:2026")
        new["payload"] = {"top_item_id": "new_2026"}
        self.push("trigger", new)
        actions = self.tick(new, "2026-04-26T11:05:00Z").json()["actions"]
        self.assertEqual(len(actions), 1)
        self.assertIn("New dentist topic", actions[0]["body"])

    def test_customer_consent_and_expiry(self):
        merchant = self.dentist()
        customer = copy.deepcopy(SEEDS["customer"][0])
        self.push("customer", customer)
        trigger = copy.deepcopy(SEEDS["trigger"][2])
        self.push("trigger", trigger)
        actions = self.tick(trigger).json()["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["send_as"], "merchant_on_behalf")
        self.assertIn(customer["identity"]["name"], actions[0]["body"])
        blocked = copy.deepcopy(customer)
        blocked["consent"]["scope"] = []
        self.push("customer", blocked, 2)
        new = copy.deepcopy(trigger)
        new["id"] = "trg_recall_without_consent"
        new["suppression_key"] = "recall_without_consent"
        self.push("trigger", new)
        self.assertEqual(self.tick(new, "2026-04-26T11:05:00Z").json()["actions"], [])
        self.assertEqual(self.tick(trigger, "2027-01-01T10:00:00Z").json()["actions"], [])

    def test_yes_produces_preview_and_stop_blocks_next_send(self):
        self.dentist()
        trigger = SEEDS["trigger"][0]
        self.push("trigger", trigger)
        action = self.tick(trigger).json()["actions"][0]
        conversation_id = action["conversation_id"]
        reply = {"conversation_id": conversation_id, "merchant_id": trigger["merchant_id"],
                 "from_role": "merchant", "message": "Yes, send me the summary", "turn_number": 2}
        result = self.client.post("/v1/reply", json=reply).json()
        self.assertEqual(result["action"], "send")
        self.assertIn("Draft summary", result["body"])
        self.assertEqual(self.client.post("/v1/reply", json=reply).json(), result)
        reply.update(message="STOP", turn_number=3)
        self.assertEqual(self.client.post("/v1/reply", json=reply).json()["action"], "end")
        reply.update(message="Actually yes", turn_number=4)
        self.assertEqual(self.client.post("/v1/reply", json=reply).json()["action"], "end")
        another = copy.deepcopy(trigger)
        another.update(id="trg_other", suppression_key="other")
        self.push("trigger", another)
        self.assertEqual(self.tick(another, "2026-04-26T11:05:00Z").json()["actions"], [])

    def test_auto_reply_repetition_and_placeholder_respect(self):
        merchant = self.dentist()
        reply = {"merchant_id": merchant["merchant_id"], "from_role": "merchant",
                 "message": "Thank you for contacting us! Our team will respond shortly.",
                 "turn_number": 2}
        reply["conversation_id"] = "auto_one"
        self.assertEqual(self.client.post("/v1/reply", json=reply).json()["action"], "wait")
        reply["conversation_id"] = "auto_two"
        self.assertEqual(self.client.post("/v1/reply", json=reply).json()["action"], "end")
        placeholder = {"id": "trg_placeholder", "scope": "merchant", "kind": "perf_dip",
                       "merchant_id": merchant["merchant_id"], "payload": {"placeholder": True},
                       "suppression_key": "placeholder", "urgency": 5,
                       "expires_at": "2026-05-01T00:00:00Z"}
        self.push("trigger", placeholder)
        self.assertEqual(self.tick(placeholder).json()["actions"], [])


if __name__ == "__main__":
    unittest.main()
