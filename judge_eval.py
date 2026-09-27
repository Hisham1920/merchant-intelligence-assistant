"""One bounded, repeatable scorecard using the challenge's supplied LLM scorer."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Thread

from challenge_judge import LLMScorer, OpenAIProvider
from engine import compose
from storage import connect


DATA = Path(__file__).with_name("dataset")
CASE_IDS = {
    "T01": "trg_013_corporate_thali_planning",
    "T02": "trg_016_kids_yoga_program_drafting",
    "T05": "trg_020_summer_demand_shift",
    "T06": "trg_022_cde_webinar_dentists",
    "T09": "trg_023_competitor_opened_dentist",
    "T11": "trg_008_curious_ask_studio11",
    "T13": "trg_015_winback_rashmi",
    "T16": "trg_025_dormancy_glamour",
    "T20": "trg_021_unverified_gbp_sunrise",
    "T21": "trg_010_ipl_match_delhi",
    "T22": "trg_012_milestone_mylari",
    "T24": "trg_004_perf_dip_bharat",
    "T26": "trg_024_perf_spike_zen",
    "T28": "trg_003_recall_due_priya",
    "T30": "trg_002_compliance_dci_radiograph",
}
DIMENSIONS = ("specificity", "category_fit", "merchant_fit", "decision_quality", "engagement_compulsion")


def sample_cases():
    merchants = {m["merchant_id"]: m for m in json.loads((DATA / "merchants_seed.json").read_text())["merchants"]}
    customers = {c["customer_id"]: c for c in json.loads((DATA / "customers_seed.json").read_text())["customers"]}
    triggers = {t["id"]: t for t in json.loads((DATA / "triggers_seed.json").read_text())["triggers"]}
    categories = {p.stem: json.loads(p.read_text()) for p in (DATA / "categories").glob("*.json")}
    for test_id, trigger_id in CASE_IDS.items():
        trigger = triggers[trigger_id]
        merchant = merchants[trigger["merchant_id"]]
        customer = customers.get(trigger.get("customer_id"))
        category = categories[merchant["category_slug"]]
        message = compose(category, merchant, trigger, customer)
        if message is None:
            raise ValueError(f"Baseline case {test_id} is no longer eligible")
        yield test_id, message, category, merchant, trigger, customer


def _summary(results):
    valid = [r for r in results if "score" in r]
    if not valid:
        return {"scored": 0, "average_out_of_50": None, "dimensions": {}}
    return {
        "scored": len(valid),
        "average_out_of_50": round(sum(r["score"]["total"] for r in valid) / len(valid), 2),
        "dimensions": {key: round(sum(r["score"][key] for r in valid) / len(valid), 2) for key in DIMENSIONS},
    }


def _save(run_id, results, status):
    document = {"run_id": run_id, "judge_model": os.environ.get("VERA_EVAL_MODEL", "gpt-4.1-mini"),
                "scoring": "supplied judge_simulator.py LLMScorer, 15 fixed factual pairs, deterministic messages",
                "simulated_now": "2026-04-26T10:00:00Z", "status": status,
                "cases": results, "summary": _summary(results)}
    with connect() as db:
        db.execute("UPDATE eval_runs SET status=?, result=? WHERE run_id=?",
                   (status, json.dumps(document, ensure_ascii=False), run_id))


def _run(run_id):
    results = []
    try:
        scorer = LLMScorer(OpenAIProvider(os.environ["OPENAI_API_KEY"],
                                          os.environ.get("VERA_EVAL_MODEL", "gpt-4.1-mini")), None)
        for test_id, message, category, merchant, trigger, customer in sample_cases():
            score = scorer.score(message, category, merchant, trigger, customer)
            entry = {"test_id": test_id, "trigger_id": trigger["id"], "kind": trigger["kind"],
                     "category": category["slug"], "merchant": merchant["identity"]["name"],
                     "body": message["body"]}
            reasons = ("specificity_reason", "category_fit_reason", "merchant_fit_reason",
                       "decision_quality_reason", "engagement_reason")
            if score.specificity_reason.startswith("Fallback:") or not all(
                    getattr(score, key, None) for key in reasons):
                entry["error"] = "The LLM score failed; fallback numbers are excluded."
            else:
                entry["score"] = {**asdict(score), "total": score.total}
            results.append(entry)
            _save(run_id, results, "running")
        _save(run_id, results, "complete" if all("score" in r for r in results) else "partial")
    except Exception as exc:
        results.append({"error": f"Evaluation stopped: {type(exc).__name__}: {exc}"})
        _save(run_id, results, "error")


def start_if_configured():
    run_id = os.environ.get("VERA_EVAL_RUN_ID", "merchant-specific-20260927")
    if not os.environ.get("OPENAI_API_KEY"):
        return
    with connect() as db:
        row = db.execute("SELECT status FROM eval_runs WHERE run_id=?", (run_id,)).fetchone()
        if row:
            return
        db.execute("INSERT INTO eval_runs(run_id,status,result,started_at) VALUES(?,?,?,?)",
                   (run_id, "running", "{}", datetime.now(timezone.utc).isoformat()))
    Thread(target=_run, args=(run_id,), daemon=True).start()


def current_report():
    run_id = os.environ.get("VERA_EVAL_RUN_ID", "merchant-specific-20260927")
    with connect() as db:
        row = db.execute("SELECT status,result FROM eval_runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        return {"status": "pending", "run_id": run_id}
    report = json.loads(row["result"])
    return report if report else {"status": row["status"], "run_id": run_id}
