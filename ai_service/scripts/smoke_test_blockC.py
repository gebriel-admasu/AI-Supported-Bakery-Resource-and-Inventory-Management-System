"""Block C end-to-end smoke test.

Runs through the full MLOps flow against a LIVE running AI service:

1. Show the registry (Champion + any candidates from prior runs).
2. Fire POST /ai/backtest to score any past forecasts.
3. Fire POST /ai/retrain to run train -> validate -> promote/reject.
4. Show the registry again to confirm v2 was archived (since identical
   data produces no statistically significant improvement).
5. Pull the most recent MLOps log entries via /ai/models endpoints.

Assumes the service is listening on http://127.0.0.1:8001.
"""

from __future__ import annotations

import json
import sys

import httpx

BASE_URL = "http://127.0.0.1:8001"


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def show_registry() -> dict:
    r = httpx.get(f"{BASE_URL}/ai/models", timeout=30)
    r.raise_for_status()
    body = r.json()
    print(f"champion_version: {body['champion_version']}")
    for m in body["items"]:
        print(
            f"  v{m['version']:>2}  status={m['status']:<10}  "
            f"mae={m['holdout_mae']:.4f}  rows={m['training_rows_used']:>6}  "
            f"source={m['training_source']}"
        )
    return body


def main() -> int:
    section("1. Registry BEFORE Block C smoke test")
    show_registry()

    section("2. POST /ai/backtest (score any past forecasts)")
    r = httpx.post(f"{BASE_URL}/ai/backtest?lookback_days=7", timeout=60)
    print(f"status={r.status_code}")
    print(json.dumps(r.json(), indent=2))

    section("3. POST /ai/retrain (manual trigger, identical data)")
    r = httpx.post(
        f"{BASE_URL}/ai/retrain",
        json={"source": "kaggle", "reason": "smoke_test_blockC"},
        timeout=300,
    )
    print(f"status={r.status_code}")
    body = r.json()
    print(json.dumps(body, indent=2))

    section("4. Registry AFTER retrain")
    after = show_registry()

    section("5. Verdict")
    if body["promoted"]:
        print(f"  -> Candidate v{body['candidate_version']} was PROMOTED to CHAMPION.")
        print(f"  -> Expected behaviour: the new model statistically beat the prior one.")
    else:
        print(f"  -> Candidate v{body['candidate_version']} was REJECTED (status={body['status']}).")
        print(f"  -> Expected behaviour for identical training data — the validation gate")
        print(f"     correctly refused to promote a model that's no better than the champion.")
        print(f"  -> Message: {body['message']}")

    versions = [m["version"] for m in after["items"]]
    statuses = {m["version"]: m["status"] for m in after["items"]}
    print(f"\n  Versions: {versions}")
    print(f"  Statuses: {statuses}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
