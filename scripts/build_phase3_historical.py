from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NORMALIZED = ROOT / "raw" / "dart" / "normalized"
PHASE3_ROOT = NORMALIZED / "phase3" / "runs"
FLOW_METRICS = ("revenue", "operating_income", "net_income", "operating_cash_flow")
POINT_METRICS = ("assets", "liabilities", "equity", "cash", "inventory", "trade_and_other_current_receivables")
PERIOD_TO_QUARTER = {"Q1": 1, "H1": 2, "Q3": 3, "FY": 4}
PREVIOUS_CUMULATIVE_PERIOD = {"Q1": None, "H1": "Q1", "Q3": "H1", "FY": "Q3"}
KST = timezone(timedelta(hours=9))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quarter_dates(year: int, quarter: int) -> tuple[date, date]:
    start_month = 1 + (quarter - 1) * 3
    start = date(year, start_month, 1)
    if quarter == 4:
        end = date(year, 12, 31)
    else:
        end = date(year, start_month + 3, 1) - timedelta(days=1)
    return start, end


def ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def pct_change(current: int | float | None, previous: int | float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return current / previous - 1


def latest_gate_summary() -> Path:
    candidates = sorted((ROOT / "raw" / "dart" / "phase3" / "gates").glob("*/gate_summary.json"))
    if not candidates:
        raise FileNotFoundError("No Phase 3 OpenDART gate summary found")
    return candidates[-1]


def build_historical(key_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    by_year_period = {(int(row["year"]), str(row["period"])): row for row in key_rows}
    independent_rows: list[dict[str, Any]] = []

    for source in sorted(key_rows, key=lambda row: (int(row["year"]), PERIOD_TO_QUARTER[str(row["period"])])):
        year = int(source["year"])
        source_period = str(source["period"])
        quarter = PERIOD_TO_QUARTER[source_period]
        previous_period = PREVIOUS_CUMULATIVE_PERIOD[source_period]
        previous_source = by_year_period.get((year, previous_period)) if previous_period else None
        start, end = quarter_dates(year, quarter)
        independent_values: dict[str, int | float | None] = {}
        formulas: dict[str, str] = {}

        for metric in FLOW_METRICS:
            current_value = source["values"].get(metric)
            if previous_source is None:
                independent_values[metric] = current_value
                formulas[metric] = f"{source_period} cumulative"
            else:
                previous_value = previous_source["values"].get(metric)
                if current_value is None or previous_value is None:
                    independent_values[metric] = None
                else:
                    independent_values[metric] = current_value - previous_value
                formulas[metric] = f"{source_period} cumulative - {previous_period} cumulative"

        point_values = {metric: source["values"].get(metric) for metric in POINT_METRICS}
        row = {
            "quarter": f"{year}Q{quarter}",
            "year": year,
            "quarter_number": quarter,
            "quarter_start": start.isoformat(),
            "quarter_end": end.isoformat(),
            "basis": "CFS",
            "unit": "KRW",
            "source_period": source_period,
            "source_id": source["source_id"],
            "source_rcept_no": source["rcept_no"],
            "previous_source_id": previous_source["source_id"] if previous_source else None,
            "previous_source_rcept_no": previous_source["rcept_no"] if previous_source else None,
            "flow_values": independent_values,
            "flow_formulas": formulas,
            "period_end_values": point_values,
            "derived": {
                "operating_margin": ratio(independent_values["operating_income"], independent_values["revenue"]),
                "net_margin": ratio(independent_values["net_income"], independent_values["revenue"]),
                "operating_cash_flow_to_revenue": ratio(independent_values["operating_cash_flow"], independent_values["revenue"]),
            },
        }
        independent_rows.append(row)

    for index, row in enumerate(independent_rows):
        previous = independent_rows[index - 1] if index else None
        if previous:
            row["quarter_over_quarter"] = {
                "revenue_change_krw": row["flow_values"]["revenue"] - previous["flow_values"]["revenue"],
                "revenue_change_pct": pct_change(row["flow_values"]["revenue"], previous["flow_values"]["revenue"]),
                "operating_cash_flow_change_krw": row["flow_values"]["operating_cash_flow"] - previous["flow_values"]["operating_cash_flow"],
                "inventory_change_krw": row["period_end_values"]["inventory"] - previous["period_end_values"]["inventory"],
                "inventory_change_pct": pct_change(row["period_end_values"]["inventory"], previous["period_end_values"]["inventory"]),
                "receivables_change_krw": row["period_end_values"]["trade_and_other_current_receivables"] - previous["period_end_values"]["trade_and_other_current_receivables"],
                "receivables_change_pct": pct_change(row["period_end_values"]["trade_and_other_current_receivables"], previous["period_end_values"]["trade_and_other_current_receivables"]),
                "cash_change_krw": row["period_end_values"]["cash"] - previous["period_end_values"]["cash"],
                "cash_change_pct": pct_change(row["period_end_values"]["cash"], previous["period_end_values"]["cash"]),
            }
        else:
            row["quarter_over_quarter"] = None

    for year in sorted({int(row["year"]) for row in key_rows}):
        available = {period: by_year_period.get((year, period)) for period in PERIOD_TO_QUARTER}
        if not all(available.values()):
            continue
        quarter_rows = [row for row in independent_rows if row["year"] == year]
        quarter_rows.sort(key=lambda row: row["quarter_number"])
        for metric in FLOW_METRICS:
            q1 = quarter_rows[0]["flow_values"][metric]
            q2 = quarter_rows[1]["flow_values"][metric]
            q3 = quarter_rows[2]["flow_values"][metric]
            q4 = quarter_rows[3]["flow_values"][metric]
            expected_h1 = available["H1"]["values"][metric]
            expected_9m = available["Q3"]["values"][metric]
            expected_fy = available["FY"]["values"][metric]
            for name, actual, expected, formula in (
                ("H1_ROLLUP", q1 + q2, expected_h1, "Q1 + Q2 = H1 cumulative"),
                ("9M_ROLLUP", q1 + q2 + q3, expected_9m, "Q1 + Q2 + Q3 = 9M cumulative"),
                ("FY_ROLLUP", q1 + q2 + q3 + q4, expected_fy, "Q1 + Q2 + Q3 + Q4 = FY"),
            ):
                difference = actual - expected
                checks.append(
                    {
                        "check_id": f"{name}-{year}-{metric}",
                        "category": "quarterization",
                        "actual": actual,
                        "expected": expected,
                        "difference": difference,
                        "tolerance": 0,
                        "passed": difference == 0,
                        "formula": formula,
                    }
                )

    result = {
        "title": "Exicon CFS independent-quarter historical series",
        "method": {
            "basis": "Consolidated financial statements (CFS) only",
            "income_statement": "Q1 direct; Q2=H1-Q1; Q3=9M-H1; Q4=FY-9M",
            "cash_flow_statement": "Q1 direct; Q2=H1-Q1; Q3=9M-H1; Q4=FY-9M",
            "balance_sheet": "Period-end point-in-time values; not differenced",
            "unknown_handling": "Missing values remain null and are not converted to zero",
        },
        "source_file": "raw/dart/normalized/key_financials_cfs.json",
        "source_sha256": sha256(NORMALIZED / "key_financials_cfs.json"),
        "row_count": len(independent_rows),
        "rows": independent_rows,
    }
    return result, checks


def build_contract_evidence(contracts: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    contract_rows: list[dict[str, Any]] = []
    schedule_rows: list[dict[str, Any]] = []

    for contract in contracts["latest_contracts"]:
        recognition_status = "U"
        contract_row = {
            **contract,
            "acceptance_or_customer_signoff_evidence": None,
            "revenue_recognition_evidence": None,
            "recognition_status": recognition_status,
            "confirmed_recognized_revenue_krw": None,
            "timing_unassigned_contract_amount_krw": contract["contract_amount_krw"],
            "interpretation": "Contract amount is known, but no period allocation is made without acceptance or revenue-recognition evidence.",
        }
        contract_rows.append(contract_row)

    for year, quarters in ((2025, (3, 4)), (2026, (1, 2, 3, 4))):
        for quarter in quarters:
            q_start, q_end = quarter_dates(year, quarter)
            active: list[dict[str, Any]] = []
            for contract in contract_rows:
                c_start = date.fromisoformat(contract["start_date"])
                c_end = date.fromisoformat(contract["end_date"])
                if c_start <= q_end and c_end >= q_start:
                    active.append(
                        {
                            "original_rcept_no": contract["original_rcept_no"],
                            "latest_rcept_no": contract["latest_rcept_no"],
                            "source_ids": contract["source_ids"],
                            "product": contract["product"],
                            "contract_amount_context_krw": contract["contract_amount_krw"],
                            "overlap_start": max(c_start, q_start).isoformat(),
                            "overlap_end": min(c_end, q_end).isoformat(),
                            "recognition_status": "U",
                            "allocated_revenue_krw": None,
                        }
                    )
            schedule_rows.append(
                {
                    "quarter": f"{year}Q{quarter}",
                    "quarter_start": q_start.isoformat(),
                    "quarter_end": q_end.isoformat(),
                    "active_contract_count": len(active),
                    "active_contract_amount_context_krw": sum(row["contract_amount_context_krw"] for row in active),
                    "active_new_2026_contract_amount_context_krw": sum(
                        row["contract_amount_context_krw"]
                        for row in active
                        if next(item for item in contract_rows if item["original_rcept_no"] == row["original_rcept_no"])["is_new_2026_contract"]
                    ),
                    "allocated_revenue_krw": None,
                    "recognition_status": "U",
                    "active_contracts": active,
                }
            )

    total_all = sum(row["contract_amount_krw"] for row in contract_rows)
    total_new_2026 = sum(row["contract_amount_krw"] for row in contract_rows if row["is_new_2026_contract"])
    checks.extend(
        [
            {
                "check_id": "CONTRACT-UNIQUE-COUNT",
                "category": "contract_evidence",
                "actual": len(contract_rows),
                "expected": contracts["unique_contract_count"],
                "difference": len(contract_rows) - contracts["unique_contract_count"],
                "tolerance": 0,
                "passed": len(contract_rows) == contracts["unique_contract_count"],
            },
            {
                "check_id": "CONTRACT-NEW-2026-TOTAL",
                "category": "contract_evidence",
                "actual": total_new_2026,
                "expected": contracts["new_2026_contract_total_krw"],
                "difference": total_new_2026 - contracts["new_2026_contract_total_krw"],
                "tolerance": 0,
                "passed": total_new_2026 == contracts["new_2026_contract_total_krw"],
            },
            {
                "check_id": "CONTRACT-CANCELLATION-COUNT",
                "category": "contract_evidence",
                "actual": contracts["cancellation_count"],
                "expected": 0,
                "difference": contracts["cancellation_count"],
                "tolerance": 0,
                "passed": contracts["cancellation_count"] == 0,
            },
            {
                "check_id": "CONTRACT-RECOGNITION-STATUS-U",
                "category": "contract_evidence",
                "actual": sum(row["recognition_status"] == "U" for row in contract_rows),
                "expected": len(contract_rows),
                "difference": sum(row["recognition_status"] == "U" for row in contract_rows) - len(contract_rows),
                "tolerance": 0,
                "passed": all(row["recognition_status"] == "U" for row in contract_rows),
            },
        ]
    )

    result = {
        "title": "Exicon contract timing and recognition-evidence ledger",
        "rules": {
            "contract_end_date": "Not treated as a revenue-recognition date",
            "payment_terms": "Not treated as a revenue-recognition percentage",
            "acceptance_rule": "Without inspection, customer acceptance, or revenue-recognition evidence, contract-level recognized amount is U",
            "schedule_rule": "Quarter overlap is timing context only; active contract amounts may repeat across quarters and are not backlog or revenue",
        },
        "source_file": "raw/dart/normalized/contracts.json",
        "source_sha256": sha256(NORMALIZED / "contracts.json"),
        "summary": {
            "unique_contract_count": len(contract_rows),
            "known_contract_amount_total_krw": total_all,
            "new_2026_contract_count": sum(row["is_new_2026_contract"] for row in contract_rows),
            "new_2026_contract_amount_total_krw": total_new_2026,
            "acceptance_evidenced_contract_amount_krw": 0,
            "confirmed_recognized_revenue_krw": None,
            "recognition_timing_unverified_contract_amount_krw": total_all,
            "cancellation_count": contracts["cancellation_count"],
        },
        "contracts": contract_rows,
        "quarter_schedule": schedule_rows,
    }
    return result, checks


def main() -> int:
    generated_at = datetime.now(KST)
    run_id = generated_at.strftime("%Y%m%dT%H%M%S%z")
    run_dir = PHASE3_ROOT / run_id
    key_path = NORMALIZED / "key_financials_cfs.json"
    contracts_path = NORMALIZED / "contracts.json"
    gate_path = latest_gate_summary()
    key_rows = read_json(key_path)
    contracts = read_json(contracts_path)
    gate = read_json(gate_path)

    historical, historical_checks = build_historical(key_rows)
    contract_evidence, contract_checks = build_contract_evidence(contracts)

    gate_checks = [
        {
            "check_id": "GATE-STATUS",
            "category": "latest_disclosure_gate",
            "actual": gate["status"],
            "expected": "000",
            "difference": None,
            "tolerance": None,
            "passed": gate["status"] == "000",
        },
        {
            "check_id": "GATE-NEW-RELEVANT",
            "category": "latest_disclosure_gate",
            "actual": gate["new_relevant_count"],
            "expected": 0,
            "difference": gate["new_relevant_count"],
            "tolerance": 0,
            "passed": gate["new_relevant_count"] == 0,
            "notes": "If nonzero, refresh the financial or contract source layer before using this run.",
        },
        {
            "check_id": "GATE-HALF-YEAR-FILING",
            "category": "latest_disclosure_gate",
            "actual": gate["half_year_count"],
            "expected": 0,
            "difference": gate["half_year_count"],
            "tolerance": 0,
            "passed": gate["half_year_count"] == 0,
            "notes": "This expected value applies to the project cutoff and the 2026-08-13 requery run only.",
        },
    ]
    checks = gate_checks + historical_checks + contract_checks
    check_output = {
        "generated_at": generated_at.isoformat(),
        "check_count": len(checks),
        "passed_count": sum(check["passed"] for check in checks),
        "failed_count": sum(not check["passed"] for check in checks),
        "checks": checks,
    }

    outputs = {
        "historical_independent_quarters_cfs.json": historical,
        "contract_timing_evidence.json": contract_evidence,
        "phase3_checks.json": check_output,
    }
    for name, value in outputs.items():
        write_json(run_dir / name, value)

    manifest = {
        "phase": "Phase 3 Historical and contract evidence",
        "run_id": run_id,
        "generated_at": generated_at.isoformat(),
        "inputs": [
            {"path": str(key_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(key_path)},
            {"path": str(contracts_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(contracts_path)},
            {"path": str(gate_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(gate_path)},
        ],
        "outputs": [
            {
                "path": str((run_dir / name).relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(run_dir / name),
            }
            for name in outputs
        ],
        "api_key_logged": False,
        "checks": {
            "count": check_output["check_count"],
            "passed": check_output["passed_count"],
            "failed": check_output["failed_count"],
        },
    }
    write_json(run_dir / "phase3_run_manifest.json", manifest)

    print(
        json.dumps(
            {
                "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
                "historical_rows": historical["row_count"],
                "contracts": contract_evidence["summary"]["unique_contract_count"],
                "checks_passed": check_output["passed_count"],
                "checks_failed": check_output["failed_count"],
            },
            ensure_ascii=False,
        )
    )
    return 1 if check_output["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
