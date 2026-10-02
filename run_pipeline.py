"""
Master pipeline for the Industrial SPC & Quality Analytics project (anonymized "Plant X" data).

Steps
  1. Verify the packaged anonymized CSVs (and that no source-identifying columns are present).
  2. Run the SPC engine (Laney p'-charts, SKU/monthly charts, Cp/Cpk, tests -> JSON + results_table.md).
  3. Rebuild the SQLite database FROM THE CSVs (never patch an old file), apply the SQL views,
     smoke-test every view and cross-check SQL vs Python numbers. Exits non-zero on any failure.

Usage:  python run_pipeline.py
"""
import json
import os
import sqlite3
import subprocess
import sys

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(BASE, "data", "processed")
BATCHES_CSV = os.path.join(PROC, "plant_insulation_batches_anonymized.csv")
SAMPLES_CSV = os.path.join(PROC, "plant_density_samples_anonymized.csv")
DB_FILE = os.path.join(PROC, "industrial_qc.db")
SQL_FILE = os.path.join(BASE, "sql", "anonymized_qc_views.sql")
FORBIDDEN_COLS = {"file", "filename", "path", "source_file", "workbook"}
VIEWS = ["view_executive_quality_summary", "view_sku_defect_performance",
         "view_pareto_failure_modes", "view_rolling_batch_quality", "view_monthly_quality"]


def fail(msg):
    print(f"\nPIPELINE FAILED: {msg}")
    sys.exit(1)


def main():
    print("=" * 75)
    print("INDUSTRIAL STATISTICAL PROCESS CONTROL (SPC) ENGINE - PLANT X")
    print("=" * 75)

    # 1. verify inputs ---------------------------------------------------------------
    for f in (BATCHES_CSV, SAMPLES_CSV):
        if not os.path.exists(f):
            fail(f"missing dataset {f}")
    batches = pd.read_csv(BATCHES_CSV)
    samples = pd.read_csv(SAMPLES_CSV)
    leaked = FORBIDDEN_COLS & (set(batches.columns) | set(samples.columns))
    if leaked:
        fail(f"source-identifying columns present in CSVs: {sorted(leaked)}")
    print(f"\n[Step 1/3] Datasets OK: {len(batches)} batches, {len(samples):,} density readings")

    # 2. SPC engine -------------------------------------------------------------------
    print("\n[Step 2/3] Running SPC engine ...")
    subprocess.run([sys.executable, os.path.join(BASE, "src", "spc_laney_engine.py")], check=True)

    # 3. rebuild DB from CSV, apply views, smoke-test ----------------------------------
    print("\n[Step 3/3] Rebuilding SQLite database from CSVs and applying views ...")
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)                       # fresh file: no leftover pages/tables
    conn = sqlite3.connect(DB_FILE)
    batches.to_sql("qc_batch_production", conn, index=False)      # insertion order = CSV order
    samples.to_sql("qc_density_samples", conn, index=False)
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()

    for v in VIEWS:                                # SQLite does not validate views at CREATE time
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
        except sqlite3.Error as e:
            conn.close()
            fail(f"view {v} is broken: {e}")
        if n == 0:
            conn.close()
            fail(f"view {v} returned no rows")
        print(f" -> {v}: OK ({n} rows)")

    # cross-check SQL against the Python results
    with open(os.path.join(PROC, "statistical_evaluation_summary.json")) as f:
        res = json.load(f)["overall_test"]
    sql_rate = dict(conn.execute(
        "SELECT phase, overall_volume_reject_pct FROM view_executive_quality_summary").fetchall())
    for phase, key in (("Pre-Intervention", "pre_reject_rate"), ("Post-Intervention", "post_reject_rate")):
        if abs(sql_rate[phase] - res[key] * 100) > 0.01:
            conn.close()
            fail(f"SQL vs Python mismatch for {phase}: {sql_rate[phase]} vs {res[key] * 100:.2f}")
    print(" -> SQL and Python reject rates agree")
    conn.close()

    print("\n" + "=" * 75)
    print("PIPELINE COMPLETED SUCCESSFULLY")
    print("Charts: dashboard/ | numbers: data/processed/statistical_evaluation_summary.json")
    print("README table: data/processed/results_table.md (paste it, do not retype numbers)")
    print("=" * 75)


if __name__ == "__main__":
    main()
