#!/usr/bin/env python3
"""
seed_spanner.py — Idempotent Spanner table seeder for the air-routing demo.

Reads CSV files from ontology/test_data/ and upserts all rows into the four
Spanner physical tables in FK-dependency order:
  1. operation
  2. network_routing
  3. network_routing_segment
  4. transit_path

Usage (from repo root in Cloud Shell):
    python scripts/seed_spanner.py

Environment overrides (optional):
    SPANNER_PROJECT   default: migiration-demo
    SPANNER_INSTANCE  default: ontology-demo
    SPANNER_DATABASE  default: ontology-db
"""

import csv
import os
import sys
from datetime import date
from pathlib import Path

from google.cloud import spanner

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT  = os.environ.get("SPANNER_PROJECT",  "migiration-demo")
INSTANCE = os.environ.get("SPANNER_INSTANCE", "ontology-demo")
DATABASE = os.environ.get("SPANNER_DATABASE", "ontology-db")

REPO_ROOT  = Path(__file__).resolve().parent.parent
DATA_DIR   = REPO_ROOT / "ontology" / "test_data"

# ── Type coercions ─────────────────────────────────────────────────────────────
def _coerce_row(table: str, row: dict) -> tuple:
    """Return a tuple of values with correct Python types for the Spanner columns."""
    if table == "operation":
        return (
            row["operation_id"],
            row["operation_type"] or None,
            row["location_code"] or None,
        )
    if table == "network_routing":
        return (
            row["routing_id"],
            row["origin_operation_id"],
            row["destination_operation_id"],
            row["service_commit"] or None,
            date.fromisoformat(row["zulu_day"]),
        )
    if table == "network_routing_segment":
        return (
            row["segment_id"],
            row["routing_id"],
            row["origin_operation_id"],
            row["destination_operation_id"],
            row["transport_mode"] or None,
            float(row["weight"])  if row["weight"]  else None,
            int(row["pieces"])    if row["pieces"]   else None,
            date.fromisoformat(row["zulu_day"]),
        )
    if table == "transit_path":
        return (
            row["transit_path_id"],
            row["segment_id"],
            int(row["total_transit_minutes"]) if row["total_transit_minutes"] else None,
        )
    raise ValueError(f"Unknown table: {table}")


# ── Table load order + column lists ───────────────────────────────────────────
TABLES = [
    {
        "table":   "operation",
        "csv":     DATA_DIR / "operation.csv",
        "columns": ["operation_id", "operation_type", "location_code"],
    },
    {
        "table":   "network_routing",
        "csv":     DATA_DIR / "network_routing.csv",
        "columns": ["routing_id", "origin_operation_id", "destination_operation_id",
                    "service_commit", "zulu_day"],
    },
    {
        "table":   "network_routing_segment",
        "csv":     DATA_DIR / "network_routing_segment.csv",
        "columns": ["segment_id", "routing_id", "origin_operation_id",
                    "destination_operation_id", "transport_mode",
                    "weight", "pieces", "zulu_day"],
    },
    {
        "table":   "transit_path",
        "csv":     DATA_DIR / "transit_path.csv",
        "columns": ["transit_path_id", "segment_id", "total_transit_minutes"],
    },
]


def load_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return [r for r in csv.DictReader(f) if any(v.strip() for v in r.values())]


def seed_table(db, spec: dict) -> int:
    rows = load_csv(spec["csv"])
    if not rows:
        print(f"  ⚠️  {spec['table']}: CSV is empty, skipping.")
        return 0

    values = [_coerce_row(spec["table"], r) for r in rows]

    def _upsert(tx):
        tx.insert_or_update(
            table=spec["table"],
            columns=spec["columns"],
            values=values,
        )

    db.run_in_transaction(_upsert)
    return len(values)


def verify_counts(db) -> dict[str, int]:
    counts = {}
    with db.snapshot() as snap:
        for spec in TABLES:
            t = spec["table"]
            result = snap.execute_sql(f"SELECT COUNT(*) FROM {t}")
            counts[t] = list(result)[0][0]
    return counts


def main():
    print(f"\n🚀  Spanner Seed Script")
    print(f"    Project  : {PROJECT}")
    print(f"    Instance : {INSTANCE}")
    print(f"    Database : {DATABASE}\n")

    client   = spanner.Client(project=PROJECT)
    instance = client.instance(INSTANCE)
    db       = instance.database(DATABASE)

    results = {}
    for spec in TABLES:
        print(f"  ↳ Loading {spec['table']} from {spec['csv'].name}...")
        try:
            n = seed_table(db, spec)
            results[spec["table"]] = ("✅", n)
            print(f"     {n} rows upserted.")
        except Exception as e:
            results[spec["table"]] = ("❌", str(e))
            print(f"     ERROR: {e}")

    print("\n── Verification (live row counts) ──────────────────────────────")
    try:
        counts = verify_counts(db)
        for spec in TABLES:
            t   = spec["table"]
            sym = results[t][0]
            n   = counts.get(t, "?")
            print(f"  {sym}  {t:<30} {n:>5} rows")
    except Exception as e:
        print(f"  Could not verify counts: {e}")

    print("\nDone. ✨\n")
    failed = [t for t, (sym, _) in results.items() if sym == "❌"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
