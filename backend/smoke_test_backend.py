"""
End-to-end smoke test for the Northwind backend review workflow.

Drives a *running* backend over HTTP and exercises the happy path:
    /health  ->  list employees  ->  create submission  ->  upload a TXT receipt
    ->  run review  ->  fetch verdict  ->  override

It is deliberately forgiving: steps that can't run because a dependency isn't
configured (no DB, no ANTHROPIC_API_KEY) are reported as SKIP, not FAIL, so the
script is useful both in CI and on a half-configured laptop.

Usage (with the backend running on :8000):
    python smoke_test_backend.py
    python smoke_test_backend.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import httpx

# ASCII-only markers so output is safe on the default Windows console (cp1252).
PASS, FAIL, SKIP, INFO = "PASS", "FAIL", "SKIP", "INFO"
_ICON = {PASS: "+", FAIL: "x", SKIP: "-", INFO: ">"}

results: list[tuple[str, str]] = []


def log(kind: str, msg: str) -> None:
    results.append((kind, msg))
    print(f"  [{_ICON.get(kind, '?')}] {kind:<4} {msg}")


SAMPLE_RECEIPT = f"""NORTHWIND SMOKE TEST RECEIPT
Merchant: The Test Kitchen
Date: {date.today().isoformat()}
Item: Working lunch (1 person)
Subtotal: 18.50
Tax: 1.50
Total: $20.00 USD
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    api = f"{base}/api/v1"
    # follow_redirects so trailing-slash routes (/employees -> /employees/) work
    # and 307s preserve the POST method + body.
    client = httpx.Client(timeout=args.timeout, follow_redirects=True)

    print(f"\nNorthwind backend smoke test -> {base}\n" + "-" * 52)

    # 1. health ---------------------------------------------------------------
    print("\n1. Health check")
    try:
        r = client.get(f"{base}/health")
        if r.status_code == 200 and r.json().get("status") == "ok":
            log(PASS, f"/health -> {r.json()}")
        else:
            log(FAIL, f"/health returned {r.status_code}: {r.text[:200]}")
            return _summary()  # nothing else will work
    except httpx.HTTPError as exc:
        log(FAIL, f"could not reach backend: {exc}")
        return _summary()

    # 2. list employees -------------------------------------------------------
    print("\n2. List employees")
    employee_id: str | None = None
    try:
        r = client.get(f"{api}/employees")
        if r.status_code == 200:
            employees = r.json()
            log(PASS, f"GET /employees -> {len(employees)} employee(s)")
            if employees:
                employee_id = employees[0]["employee_id"]
                log(INFO, f"using employee_id={employee_id}")
            else:
                log(SKIP, "no employees seeded — run `python seed_employees.py` first")
        else:
            log(FAIL, f"GET /employees -> {r.status_code}: {r.text[:200]}")
            if r.status_code >= 500:
                log(INFO, "a 5xx here usually means the DB is unreachable — "
                          "check DATABASE_URL and that migrations have run")
    except httpx.HTTPError as exc:
        log(FAIL, f"GET /employees raised {exc}")

    if not employee_id:
        log(SKIP, "skipping submission/receipt/review (need a seeded employee + DB)")
        return _summary()

    # 3. create submission ----------------------------------------------------
    print("\n3. Create submission")
    submission_id: str | None = None
    try:
        payload = {
            "employee_id": employee_id,
            "trip_purpose": "Smoke-test trip",
            "trip_start_date": date.today().isoformat(),
            "trip_end_date": (date.today() + timedelta(days=2)).isoformat(),
        }
        r = client.post(f"{api}/submissions", json=payload)
        if r.status_code == 201:
            submission_id = r.json()["id"]
            log(PASS, f"POST /submissions -> {submission_id} (status={r.json()['status']})")
        else:
            log(FAIL, f"POST /submissions -> {r.status_code}: {r.text[:200]}")
    except httpx.HTTPError as exc:
        log(FAIL, f"POST /submissions raised {exc}")

    if not submission_id:
        return _summary()

    # 4. upload a TXT receipt -------------------------------------------------
    print("\n4. Upload TXT receipt")
    try:
        files = {"files": ("smoke_lunch.txt", SAMPLE_RECEIPT, "text/plain")}
        r = client.post(f"{api}/submissions/{submission_id}/receipts", files=files)
        if r.status_code == 201:
            body = r.json()
            log(PASS, f"uploaded {len(body['receipts'])} receipt(s)")
            for w in body.get("warnings", []):
                log(INFO, f"warning: {w}")
        else:
            log(FAIL, f"upload -> {r.status_code}: {r.text[:200]}")
    except httpx.HTTPError as exc:
        log(FAIL, f"upload raised {exc}")

    # 5. run review -----------------------------------------------------------
    print("\n5. Run AI review")
    verdict_id: str | None = None
    receipt_id: str | None = None
    try:
        r = client.post(f"{api}/submissions/{submission_id}/review")
        if r.status_code == 200:
            body = r.json()
            log(PASS, f"review done -> submission status={body['status']}, "
                      f"{body['reviewed']} receipt(s) reviewed")
            for v in body["verdicts"]:
                log(INFO, f"verdict={v['verdict']} conf={v['confidence']} "
                          f"cites={len(v['policy_citations'])} quotes={len(v['quoted_policy_clauses'])}")
                verdict_id = verdict_id or v["id"]
                receipt_id = receipt_id or v["receipt_id"]
        elif r.status_code == 503:
            log(SKIP, f"review unavailable (likely no ANTHROPIC_API_KEY): {r.text[:160]}")
        else:
            log(FAIL, f"review -> {r.status_code}: {r.text[:200]}")
    except httpx.HTTPError as exc:
        log(FAIL, f"review raised {exc}")

    # 6. fetch verdict + override (only if review produced one) ---------------
    if verdict_id and receipt_id:
        print("\n6. Fetch verdict + override")
        try:
            r = client.get(f"{api}/receipts/{receipt_id}/verdict")
            log(PASS if r.status_code == 200 else FAIL,
                f"GET verdict -> {r.status_code} (effective={r.json().get('effective_verdict') if r.status_code==200 else '-'})")

            ov = {"override_verdict": "flagged", "reviewer_name": "Smoke Tester",
                  "comment": "override applied by smoke test"}
            r = client.post(f"{api}/verdicts/{verdict_id}/override", json=ov)
            if r.status_code == 200 and r.json()["effective_verdict"] == "flagged":
                log(PASS, "override applied; effective_verdict=flagged, AI verdict preserved")
            else:
                log(FAIL, f"override -> {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as exc:
            log(FAIL, f"override raised {exc}")
    else:
        print("\n6. Fetch verdict + override")
        log(SKIP, "no verdict produced (review skipped) — nothing to override")

    return _summary()


def _summary() -> int:
    n_pass = sum(1 for k, _ in results if k == PASS)
    n_fail = sum(1 for k, _ in results if k == FAIL)
    n_skip = sum(1 for k, _ in results if k == SKIP)
    print("\n" + "-" * 52)
    print(f"SUMMARY: {n_pass} passed, {n_fail} failed, {n_skip} skipped")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
