"""
Scan the /submissions folder, read every employee_info.json, and upsert
each employee into the database.

Usage (from the backend/ directory):
    python seed_employees.py

Optional flags:
    --dry-run   Print what would be inserted without touching the database.
    --verbose   Show per-employee DEBUG lines.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
SUBMISSIONS_DIR = PROJECT_ROOT / "submissions"

# Load .env from project root so DATABASE_URL is available when the script
# is run from backend/ (where pydantic-settings' env_file=".env" would miss it).
load_dotenv(PROJECT_ROOT / ".env", override=False)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("seed_employees")


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class EmployeeRecord:
    employee_id: str
    name: str
    grade: int
    title: str
    department: str
    manager_id: str | None
    home_base: str
    source_folder: str


# ── Parsing ───────────────────────────────────────────────────────────────────
REQUIRED_FIELDS = {"employee_id", "name", "grade", "title", "department", "home_base"}


def parse_employee(data: dict, source_folder: str) -> EmployeeRecord:
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        raise ValueError(f"Missing fields {missing}")
    return EmployeeRecord(
        employee_id=data["employee_id"],
        name=data["name"],
        grade=int(data["grade"]),
        title=data["title"],
        department=data["department"],
        manager_id=data.get("manager_id"),
        home_base=data["home_base"],
        source_folder=source_folder,
    )


def collect_employee_records() -> list[EmployeeRecord]:
    """Walk submissions/ and return one EmployeeRecord per employee_info.json."""
    json_files = sorted(SUBMISSIONS_DIR.glob("*/employee_info.json"))
    if not json_files:
        log.warning("No employee_info.json files found under %s", SUBMISSIONS_DIR)
        return []

    records: list[EmployeeRecord] = []
    for path in json_files:
        folder = path.parent.name
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            rec = parse_employee(data, folder)
            records.append(rec)
            log.debug("Parsed %s (%s) from %s", rec.employee_id, rec.name, folder)
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            log.error("Skipping %s — %s", path, exc)

    # Deduplicate by employee_id; keep first occurrence
    seen: dict[str, EmployeeRecord] = {}
    for rec in records:
        if rec.employee_id in seen:
            log.warning(
                "Duplicate employee_id %s in %s (already seen in %s) — skipping",
                rec.employee_id,
                rec.source_folder,
                seen[rec.employee_id].source_folder,
            )
        else:
            seen[rec.employee_id] = rec

    return list(seen.values())


# ── Database operations ───────────────────────────────────────────────────────
async def seed_employees(
    conn: asyncpg.Connection,
    records: list[EmployeeRecord],
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Two-pass upsert:
      Pass 1 — insert all employees with manager_id = NULL to avoid FK
               violations when the manager's own row hasn't been inserted yet.
      Pass 2 — update manager_id where the referenced manager now exists in
               the table (covers the subset of managers who are also submitters).
    """
    counts = {"inserted": 0, "already_existed": 0, "manager_resolved": 0}

    if dry_run:
        log.info("[DRY RUN] Would attempt to insert %d employee(s):", len(records))
        for r in records:
            log.info(
                "  %s | %-30s | grade=%d | dept=%-20s | manager=%s",
                r.employee_id, r.name, r.grade, r.department, r.manager_id or "—",
            )
        return counts

    # ── Pass 1: insert without manager_id ────────────────────────────────────
    for rec in records:
        tag = await conn.execute(
            """
            INSERT INTO employees
                (employee_id, name, grade, title, department, manager_id, home_base)
            VALUES ($1, $2, $3, $4, $5, NULL, $6)
            ON CONFLICT (employee_id) DO NOTHING
            """,
            rec.employee_id, rec.name, rec.grade,
            rec.title, rec.department, rec.home_base,
        )
        if tag == "INSERT 0 1":
            counts["inserted"] += 1
            log.debug("Inserted  %s  %s", rec.employee_id, rec.name)
        else:
            counts["already_existed"] += 1
            log.debug("Skipped   %s  %s  (already exists)", rec.employee_id, rec.name)

    # ── Pass 2: resolve manager_ids that now exist in the table ───────────────
    for rec in records:
        if rec.manager_id is None:
            continue
        tag = await conn.execute(
            """
            UPDATE employees
            SET    manager_id = $1
            WHERE  employee_id = $2
              AND  EXISTS (SELECT 1 FROM employees WHERE employee_id = $1)
            """,
            rec.manager_id, rec.employee_id,
        )
        if tag == "UPDATE 1":
            counts["manager_resolved"] += 1
            log.debug(
                "Resolved  manager_id=%s  for  %s", rec.manager_id, rec.employee_id
            )

    return counts


# ── Entrypoint ────────────────────────────────────────────────────────────────
async def main(dry_run: bool, verbose: bool) -> None:
    if verbose:
        log.setLevel(logging.DEBUG)

    log.info("Scanning submissions at: %s", SUBMISSIONS_DIR)
    records = collect_employee_records()

    if not records:
        log.warning("Nothing to seed — exiting.")
        return

    log.info("Found %d unique employee record(s) across %d submission folder(s)",
             len(records), len(list(SUBMISSIONS_DIR.glob("*/employee_info.json"))))

    if dry_run:
        await seed_employees(None, records, dry_run=True)  # type: ignore[arg-type]
        return

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log.error(
            "DATABASE_URL is not set. "
            "Copy .env.example to .env at the project root and fill in the value."
        )
        sys.exit(1)

    # asyncpg uses the plain postgres:// DSN; strip SQLAlchemy driver prefixes.
    dsn = (
        database_url
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )

    log.info("Connecting to database…")
    try:
        conn = await asyncpg.connect(dsn)
    except (asyncpg.InvalidPasswordError, OSError) as exc:
        log.error("Could not connect: %s", exc)
        sys.exit(1)

    try:
        counts = await seed_employees(conn, records)
    finally:
        await conn.close()

    log.info(
        "Seeding complete — inserted: %d | already existed: %d | manager links resolved: %d",
        counts["inserted"], counts["already_existed"], counts["manager_resolved"],
    )

    if counts["manager_resolved"] < len([r for r in records if r.manager_id]):
        unresolved = len([r for r in records if r.manager_id]) - counts["manager_resolved"]
        log.info(
            "%d manager_id reference(s) left as NULL "
            "(those managers are not in the submissions data — populate from HR export).",
            unresolved,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed employees from submissions/")
    parser.add_argument("--dry-run", action="store_true", help="Print without inserting")
    parser.add_argument("--verbose", action="store_true", help="Show per-row DEBUG lines")
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run, verbose=args.verbose))
