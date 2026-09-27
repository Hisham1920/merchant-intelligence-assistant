"""Exercise the actual local HTTP service with the challenge's fixed sample clock."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib import error, request


ROOT = Path(__file__).parent
NOW = datetime.fromisoformat("2026-04-26T10:00:00+00:00")


def iso(offset):
    return (NOW + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z")


class LocalBot:
    def __init__(self, base):
        self.base = base
        self.latencies = {}

    def call(self, route, body=None):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = request.Request(self.base + route, data=data,
                              headers={"Content-Type": "application/json"},
                              method="POST" if data is not None else "GET")
        start = time.monotonic()
        try:
            with request.urlopen(req, timeout=15) as response:
                result = json.load(response)
                status = response.status
        except error.HTTPError as exc:
            result = json.loads(exc.read().decode())
            status = exc.code
        self.latencies.setdefault(route, []).append(round((time.monotonic() - start) * 1000, 1))
        return status, result

    def push(self, scope, record, version=1):
        key = {"category": "slug", "merchant": "merchant_id", "customer": "customer_id", "trigger": "id"}[scope]
        status, response = self.call("/v1/context", {"scope": scope, "context_id": record[key],
                                                      "version": version, "payload": record})
        assert status == 200 and response["accepted"], (scope, record[key], response)

    def tick(self, triggers, offset):
        status, response = self.call("/v1/tick", {"now": iso(offset), "available_triggers": triggers})
        assert status == 200, response
        return response["actions"]

    def reply(self, action, message, turn):
        status, response = self.call("/v1/reply", {"conversation_id": action["conversation_id"],
                                                      "merchant_id": action["merchant_id"],
                                                      "customer_id": action.get("customer_id"),
                                                      "from_role": "customer" if action.get("customer_id") else "merchant",
                                                      "turn_number": turn, "message": message,
                                                      "received_at": iso(125)})
        assert status == 200, response
        return response


def start_server(db_path, port, log):
    env = {**os.environ, "VERA_DB": str(db_path), "PORT": str(port)}
    env.pop("DATABASE_URL", None)
    env.pop("OPENAI_API_KEY", None)
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                                "--port", str(port), "--log-level", "warning"],
                               cwd=ROOT, env=env, stdout=log, stderr=log)
    bot = LocalBot(f"http://127.0.0.1:{port}")
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Local service exited before health check")
        try:
            status, _ = bot.call("/v1/healthz")
            if status == 200:
                return process, bot
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("Local service did not start")


def stop_server(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def clear_test_conversations(db_path):
    with sqlite3.connect(db_path) as db:
        for name in ("sent", "conversations", "opt_out", "auto_replies"):
            db.execute(f"DELETE FROM {name}")


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values)-1, int((len(values)-1)*q))] if values else None


def run(output):
    with tempfile.TemporaryDirectory(prefix="vera_http_check_") as temp:
        temp = Path(temp)
        dataset = temp / "expanded"
        subprocess.run([sys.executable, "dataset/generate_dataset.py", "--seed-dir", "dataset",
                        "--out", str(dataset)], cwd=ROOT, check=True, capture_output=True, text=True)
        categories = [json.loads(p.read_text()) for p in sorted((dataset/"categories").glob("*.json"))]
        merchants = [json.loads(p.read_text()) for p in sorted((dataset/"merchants").glob("*.json"))]
        customers = [json.loads(p.read_text()) for p in sorted((dataset/"customers").glob("*.json"))]
        triggers = [json.loads(p.read_text()) for p in sorted((dataset/"triggers").glob("*.json"))]
        pairs = json.loads((dataset/"test_pairs.json").read_text())["pairs"]
        trigger_by_id = {t["id"]: t for t in triggers}
        db_path = temp / "service.sqlite3"
        with socket.socket() as socket_handle:
            socket_handle.bind(("127.0.0.1", 0))
            port = socket_handle.getsockname()[1]
        with (temp/"server.log").open("w") as log:
            process, bot = start_server(db_path, port, log)
            report = {"test_clock": iso(0), "environment": "isolated localhost HTTP + temporary SQLite, no AI key",
                      "dataset": {"categories": len(categories), "merchants": len(merchants),
                                  "customers": len(customers), "triggers": len(triggers), "pairs": len(pairs)},
                      "checks": {}}
            try:
                for scope, records in (("category", categories), ("merchant", merchants),
                                       ("customer", customers), ("trigger", triggers)):
                    for record in records:
                        bot.push(scope, record)
                _, health = bot.call("/v1/healthz")
                report["checks"]["contexts_loaded"] = health["contexts_loaded"]

                pair_cases = []
                for pair in pairs:
                    clear_test_conversations(db_path)
                    actions = bot.tick([pair["trigger_id"]], 0)
                    trigger = trigger_by_id[pair["trigger_id"]]
                    pair_cases.append({"test_id": pair["test_id"], "kind": trigger["kind"],
                                       "placeholder": bool(trigger.get("payload", {}).get("placeholder")),
                                       "sent": len(actions) == 1})
                report["checks"]["fresh_pair_replay"] = {
                    "sent": sum(x["sent"] for x in pair_cases), "skipped": sum(not x["sent"] for x in pair_cases),
                    "cases": pair_cases, "note": "Local sent state reset between pairs; coverage, not scored accuracy."}

                clear_test_conversations(db_path)
                all_ids = [t["id"] for t in triggers]
                initial = bot.tick(all_ids, 0)
                repeated = bot.tick(all_ids, 0)
                five_minutes = bot.tick(all_ids, 5)
                sixty_one = bot.tick(all_ids, 61)
                report["checks"]["timed_ticks"] = {
                    "first_actions": len(initial), "same_time_actions": len(repeated),
                    "five_minute_actions": len(five_minutes), "after_61_minutes_actions": len(sixty_one),
                    "first_categories": sorted({next(m["category_slug"] for m in merchants
                                                       if m["merchant_id"] == a["merchant_id"]) for a in initial}),
                    "duplicate_suppression_keys": len({(a["customer_id"] or a["merchant_id"], a["suppression_key"])
                                                       for a in initial+repeated+five_minutes+sixty_one}) !=
                                                  len(initial+repeated+five_minutes+sixty_one)}

                category = next(c for c in categories if c["slug"] == "dentists")
                category["digest"].append({"id": "evaluation_fixture", "kind": "operations",
                                            "title": "Sample clinic listing checklist", "source": "Local evaluation fixture",
                                            "summary": "Review your published opening hours."})
                bot.push("category", category, 2)
                dentist = next(m for m in merchants if m["merchant_id"].startswith("m_001_"))
                new_trigger = {"id": "local_new_digest_fixture", "merchant_id": dentist["merchant_id"],
                               "scope": "merchant", "kind": "research_digest", "urgency": 4,
                               "suppression_key": "local:new_digest_fixture",
                               "expires_at": iso(200), "payload": {"top_item_id": "evaluation_fixture"}}
                bot.push("trigger", new_trigger)
                version_actions = bot.tick([new_trigger["id"]], 122)
                report["checks"]["version_update"] = {
                    "actions": len(version_actions),
                    "new_fact_present": any("Sample clinic listing checklist" in a["body"] for a in version_actions)}

                merchant_action = next(a for a in initial if not a["customer_id"])
                accepted = bot.reply(merchant_action, "Yes, draft it", 2)
                duplicate = bot.reply(merchant_action, "Yes, draft it", 2)
                question = bot.reply(merchant_action, "Kitna cost hoga?", 3)
                customer_action = next((a for a in initial if a["customer_id"]), None)
                customer_yes = bot.reply(customer_action, "Haan, details bhejo", 2) if customer_action else None
                report["checks"]["replies"] = {"yes": accepted, "same_turn_idempotent": duplicate == accepted,
                                               "hindi_question": question, "customer_hinglish_yes": customer_yes}
                other = next(a for a in initial if a["conversation_id"] != merchant_action["conversation_id"])
                stop = bot.reply(other, "STOP", 2)
                stop_repeat = bot.reply(other, "STOP", 2)
                blocked_trigger = {**trigger_by_id[other["trigger_id"]], "id": "local_opt_out_check",
                                   "suppression_key": "local:opt_out_check", "expires_at": iso(220)}
                bot.push("trigger", blocked_trigger)
                report["checks"]["opt_out"] = {"response": stop, "idempotent": stop_repeat == stop,
                                                 "future_actions": len(bot.tick([blocked_trigger["id"]], 180))}
                stop_server(process)
                process, restarted = start_server(db_path, port, log)
                _, after_restart = restarted.call("/v1/healthz")
                report["checks"]["restart"] = {
                    "contexts_loaded": after_restart["contexts_loaded"],
                    "suppressed_actions": len(restarted.tick([blocked_trigger["id"]], 185))}

                report["latency_ms"] = {route: {"count": len(times), "median": percentile(times, .5),
                                                 "p95": percentile(times, .95), "max": max(times)}
                                        for route, times in bot.latencies.items()}
                checks = report["checks"]
                report["passed"] = all((
                    checks["contexts_loaded"] == {"category": 5, "merchant": 50, "customer": 200, "trigger": 100},
                    checks["fresh_pair_replay"]["sent"] == 15,
                    checks["fresh_pair_replay"]["skipped"] == 15,
                    1 <= checks["timed_ticks"]["first_actions"] <= 20,
                    not checks["timed_ticks"]["duplicate_suppression_keys"],
                    checks["timed_ticks"]["same_time_actions"] == 0,
                    checks["timed_ticks"]["five_minute_actions"] == 0,
                    checks["version_update"]["new_fact_present"],
                    accepted["action"] == "send", checks["replies"]["same_turn_idempotent"],
                    question["action"] == "send" and "price" in question["body"].lower() and
                        "confirmed" in question["body"].lower() and question["body"] != accepted["body"],
                    customer_yes is not None and customer_yes["action"] == "send" and
                        "draft" in customer_yes["body"].lower() and "Bilkul" in customer_yes["body"],
                    stop["action"] == "end", checks["opt_out"]["idempotent"],
                    checks["opt_out"]["future_actions"] == 0,
                    checks["restart"]["suppressed_actions"] == 0,
                ))
            finally:
                if process.poll() is None:
                    stop_server(process)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print("Isolated HTTP check:", "PASS" if report["passed"] else "FAIL")
        print("Pair sends/skips:", report["checks"]["fresh_pair_replay"]["sent"],
              report["checks"]["fresh_pair_replay"]["skipped"])
        print("Ticks:", report["checks"]["timed_ticks"])
        print("Replies:", {k:v.get("action") if isinstance(v, dict) else v
                           for k,v in report["checks"]["replies"].items()})
        print("Report:", output)
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve())
