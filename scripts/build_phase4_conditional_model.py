from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NORMALIZED = ROOT / "raw" / "dart" / "normalized"
PHASE4_RUNS = NORMALIZED / "phase4" / "runs"
MARKET_RUNS = ROOT / "raw" / "market" / "phase4" / "runs"
KST = timezone(timedelta(hours=9))

PERIOD_ORDER = {"Q1": 1, "H1": 2, "Q3": 3, "FY": 4}
PREVIOUS_PERIOD = {"Q1": None, "H1": "Q1", "Q3": "H1", "FY": "Q3"}
FLOW_ACCOUNT_IDS = {
    "revenue": "ifrs-full_Revenue",
    "cost_of_sales": "ifrs-full_CostOfSales",
    "gross_profit": "ifrs-full_GrossProfit",
    "selling_general_and_administrative_expenses": "dart_TotalSellingGeneralAdministrativeExpenses",
    "operating_income": "dart_OperatingIncomeLoss",
}
BALANCE_ACCOUNT_IDS = {
    "cash_and_cash_equivalents": "ifrs-full_CashAndCashEquivalents",
    "short_term_deposits": "ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents",
    "current_borrowing_debt": "ifrs-full_OtherCurrentFinancialLiabilities",
    "noncurrent_borrowing_debt": "ifrs-full_OtherNoncurrentFinancialLiabilities",
    "equity": "ifrs-full_Equity",
}


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


def latest_file(root: Path, filename: str) -> Path:
    candidates = sorted(path / filename for path in root.iterdir() if path.is_dir() and (path / filename).exists())
    if not candidates:
        raise FileNotFoundError(f"No {filename} under {root}")
    return candidates[-1]


def latest_gate_summary() -> Path:
    candidates = sorted((ROOT / "raw" / "dart" / "phase3" / "gates").glob("*/gate_summary.json"))
    if not candidates:
        raise FileNotFoundError("No OpenDART gate summary found")
    return candidates[-1]


def ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def cumulative_value(row: dict[str, Any]) -> int | float | None:
    numeric = row["numeric"]
    period = row["period"]
    if period == "FY":
        return numeric.get("thstrm_amount")
    return numeric.get("thstrm_add_amount", numeric.get("thstrm_amount"))


def make_check(
    check_id: str,
    category: str,
    actual: Any,
    expected: Any,
    *,
    tolerance: float | None = 0,
    notes: str | None = None,
) -> dict[str, Any]:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and not isinstance(actual, bool):
        difference = actual - expected
        passed = abs(difference) <= (tolerance or 0)
    else:
        difference = None
        passed = actual == expected
    result = {
        "check_id": check_id,
        "category": category,
        "actual": actual,
        "expected": expected,
        "difference": difference,
        "tolerance": tolerance,
        "passed": passed,
    }
    if notes:
        result["notes"] = notes
    return result


def select_flow_rows(financial_rows: list[dict[str, Any]]) -> dict[tuple[int, str, str], dict[str, Any]]:
    selected: dict[tuple[int, str, str], dict[str, Any]] = {}
    reverse_ids = {account_id: metric for metric, account_id in FLOW_ACCOUNT_IDS.items()}
    for row in financial_rows:
        account_id = row["raw"].get("account_id")
        if row["fs_div"] != "CFS" or row["raw"].get("sj_div") != "CIS" or account_id not in reverse_ids:
            continue
        key = (int(row["year"]), str(row["period"]), reverse_ids[account_id])
        if key in selected:
            raise ValueError(f"Duplicate CFS flow row: {key}")
        selected[key] = row
    return selected


def build_margin_history(
    financial_rows: list[dict[str, Any]], phase3_history: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    selected = select_flow_rows(financial_rows)
    periods = sorted({(year, period) for year, period, _ in selected}, key=lambda item: (item[0], PERIOD_ORDER[item[1]]))
    cumulative: dict[tuple[int, str], dict[str, Any]] = {}
    for year, period in periods:
        values: dict[str, int | float | None] = {}
        sources: dict[str, dict[str, Any]] = {}
        for metric in FLOW_ACCOUNT_IDS:
            row = selected[(year, period, metric)]
            values[metric] = cumulative_value(row)
            sources[metric] = {
                "source_id": row["source_id"],
                "rcept_no": row["raw"]["rcept_no"],
                "account_id": row["raw"]["account_id"],
                "source_file": row["source_file"],
            }
        cumulative[(year, period)] = {"values": values, "sources": sources}

    phase3_by_quarter = {row["quarter"]: row for row in phase3_history["rows"]}
    independent_rows: list[dict[str, Any]] = []
    for year, period in periods:
        quarter_number = PERIOD_ORDER[period]
        quarter = f"{year}Q{quarter_number}"
        previous_period = PREVIOUS_PERIOD[period]
        current = cumulative[(year, period)]
        previous = cumulative.get((year, previous_period)) if previous_period else None
        values: dict[str, int | float | None] = {}
        formulas: dict[str, str] = {}
        for metric in FLOW_ACCOUNT_IDS:
            current_value = current["values"][metric]
            if previous is None:
                values[metric] = current_value
                formulas[metric] = f"{period} cumulative"
            else:
                previous_value = previous["values"][metric]
                values[metric] = None if current_value is None or previous_value is None else current_value - previous_value
                formulas[metric] = f"{period} cumulative - {previous_period} cumulative"
        row = {
            "quarter": quarter,
            "year": year,
            "quarter_number": quarter_number,
            "basis": "CFS",
            "classification": "F inputs; E quarter subtraction and ratios",
            "unit": "KRW",
            "source_period": period,
            "flow_values": values,
            "formulas": formulas,
            "sources": current["sources"],
            "previous_period_sources": previous["sources"] if previous else None,
            "derived": {
                "gross_margin": ratio(values["gross_profit"], values["revenue"]),
                "operating_margin": ratio(values["operating_income"], values["revenue"]),
                "sga_to_revenue": ratio(values["selling_general_and_administrative_expenses"], values["revenue"]),
            },
        }
        independent_rows.append(row)

        checks.append(
            make_check(
                f"PHASE3-REVENUE-CROSSCHECK-{quarter}",
                "phase3_crosscheck",
                values["revenue"],
                phase3_by_quarter[quarter]["flow_values"]["revenue"],
            )
        )
        checks.append(
            make_check(
                f"PHASE3-OI-CROSSCHECK-{quarter}",
                "phase3_crosscheck",
                values["operating_income"],
                phase3_by_quarter[quarter]["flow_values"]["operating_income"],
            )
        )
        checks.append(
            make_check(
                f"GROSS-PROFIT-IDENTITY-{quarter}",
                "income_statement_identity",
                values["revenue"] - values["cost_of_sales"],
                values["gross_profit"],
            )
        )
        checks.append(
            make_check(
                f"OPERATING-INCOME-IDENTITY-{quarter}",
                "income_statement_identity",
                values["gross_profit"] - values["selling_general_and_administrative_expenses"],
                values["operating_income"],
            )
        )

    for year in (2023, 2024, 2025):
        year_rows = sorted((row for row in independent_rows if row["year"] == year), key=lambda row: row["quarter_number"])
        if len(year_rows) != 4:
            continue
        for metric in FLOW_ACCOUNT_IDS:
            q = [row["flow_values"][metric] for row in year_rows]
            expected_h1 = cumulative[(year, "H1")]["values"][metric]
            expected_9m = cumulative[(year, "Q3")]["values"][metric]
            expected_fy = cumulative[(year, "FY")]["values"][metric]
            checks.extend(
                [
                    make_check(f"MARGIN-H1-{year}-{metric}", "margin_quarterization", q[0] + q[1], expected_h1),
                    make_check(f"MARGIN-9M-{year}-{metric}", "margin_quarterization", q[0] + q[1] + q[2], expected_9m),
                    make_check(f"MARGIN-FY-{year}-{metric}", "margin_quarterization", sum(q), expected_fy),
                ]
            )

    by_quarter = {row["quarter"]: row for row in independent_rows}
    fy2025 = cumulative[(2025, "FY")]["values"]
    reference_states = [
        {
            "state_id": "LATEST_Q1_STRESS",
            "label": "latest low-throughput observation",
            "period": "2026Q1",
            "values": by_quarter["2026Q1"]["flow_values"],
            "gross_margin": by_quarter["2026Q1"]["derived"]["gross_margin"],
            "operating_margin": by_quarter["2026Q1"]["derived"]["operating_margin"],
            "classification": "F/E historical observation, not a forecast",
        },
        {
            "state_id": "FY2025_TRANSITION",
            "label": "full-year near-break-even observation",
            "period": "2025FY",
            "values": fy2025,
            "gross_margin": ratio(fy2025["gross_profit"], fy2025["revenue"]),
            "operating_margin": ratio(fy2025["operating_income"], fy2025["revenue"]),
            "classification": "F/E historical observation, not a normalized margin",
        },
        {
            "state_id": "Q4_2025_HIGH_DELIVERY",
            "label": "high-delivery quarter observation",
            "period": "2025Q4",
            "values": by_quarter["2025Q4"]["flow_values"],
            "gross_margin": by_quarter["2025Q4"]["derived"]["gross_margin"],
            "operating_margin": by_quarter["2025Q4"]["derived"]["operating_margin"],
            "classification": "F/E historical observation, not a repeatable normal case",
        },
    ]
    profitable_quarters = [row["quarter"] for row in independent_rows if row["flow_values"]["operating_income"] > 0]
    loss_quarters = [row["quarter"] for row in independent_rows if row["flow_values"]["operating_income"] < 0]

    result = {
        "title": "Exicon CFS independent-quarter margin drivers",
        "method": {
            "basis": "CFS only",
            "quarterization": "Q1 direct; Q2=H1-Q1; Q3=9M-H1; Q4=FY-9M",
            "gross_profit_identity": "revenue - cost of sales",
            "operating_income_identity": "gross profit - selling, general and administrative expenses",
            "unknown_handling": "Missing values remain null and are never converted to zero",
        },
        "source_files": [
            "raw/dart/normalized/financial_rows.json",
            "raw/dart/normalized/phase3/runs/.../historical_independent_quarters_cfs.json",
        ],
        "row_count": len(independent_rows),
        "rows": independent_rows,
        "historical_reference_states": reference_states,
        "diagnostic": {
            "profitable_quarters": profitable_quarters,
            "loss_quarters": loss_quarters,
            "interpretation": "Low revenue quarters repeatedly produced operating losses and high-volume quarters showed operating leverage, but the observed gap does not establish a stable break-even point or normalized margin.",
        },
    }
    return result, checks


def build_contract_and_scenarios(
    contracts: dict[str, Any],
    contract_evidence: dict[str, Any],
    margin_history: dict[str, Any],
    phase3_history: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    evidence_by_original = {row["original_rcept_no"]: row for row in contract_evidence["contracts"]}
    contract_states: list[dict[str, Any]] = []
    for contract in contracts["latest_contracts"]:
        evidence = evidence_by_original[contract["original_rcept_no"]]
        is_board_revision = set(contract["source_ids"]) == {"R04", "R07"}
        has_delivery_context = contract["source_ids"] == ["R03"]
        state = {
            "source_ids": contract["source_ids"],
            "original_rcept_no": contract["original_rcept_no"],
            "latest_rcept_no": contract["latest_rcept_no"],
            "product": contract["product"],
            "contract_value_krw": contract["contract_amount_krw"],
            "contract_period": {"start": contract["start_date"], "end": contract["end_date"]},
            "contract_validity_status": "valid-no-cancellation-at-cutoff",
            "schedule_status": "revised-end-date" if is_board_revision else "latest-disclosed-period",
            "delivery_context": {
                "status": "reported-in-order-table" if has_delivery_context else "not-linked",
                "reported_amount_krw": 8_000_000_000 if has_delivery_context else None,
                "source_id": "R01" if has_delivery_context else None,
                "warning": "Delivery is not customer acceptance or revenue recognition evidence." if has_delivery_context else None,
            },
            "acceptance_or_customer_signoff_evidence": evidence["acceptance_or_customer_signoff_evidence"],
            "revenue_recognition_evidence": evidence["revenue_recognition_evidence"],
            "recognition_state": "U",
            "confirmed_recognized_revenue_krw": None,
            "contract_value_with_unverified_recognition_krw": contract["contract_amount_krw"],
            "classification": "F contract value and schedule; U recognized amount",
        }
        contract_states.append(state)

    latest = phase3_history["rows"][-1]
    previous = phase3_history["rows"][-2]
    inventory_increased = latest["period_end_values"]["inventory"] > previous["period_end_values"]["inventory"]
    ocf_worsened = latest["flow_values"]["operating_cash_flow"] < previous["flow_values"]["operating_cash_flow"]

    forecast = {
        "period": "2026FY",
        "status": "U",
        "classification": "F actual through 2026Q1; U for unreported periods and contract recognition",
        "formula": "reported 2026 CFS revenue + officially confirmed post-period contract revenue + officially confirmed other revenue + U",
        "components": {
            "reported_cfs_revenue_through_2026q1_krw": latest["flow_values"]["revenue"],
            "unreported_existing_business_revenue_krw": None,
            "officially_confirmed_contract_revenue_after_2026q1_krw": None,
            "officially_confirmed_other_revenue_krw": None,
            "forecast_total_revenue_krw": None,
            "forecast_gross_profit_krw": None,
            "forecast_operating_income_krw": None,
            "forecast_operating_cash_flow_krw": None,
        },
        "reason": "Existing-business revenue and contract acceptance by period are not disclosed. Zero is not substituted for unknown future revenue.",
        "double_count_control": "Before adding a confirmed contract amount, verify that it is not already included in reported CFS revenue.",
    }

    scenarios = [
        {
            "scenario_id": "CURRENT_UNRESOLVED",
            "label": "현재 미해결 상태",
            "status": "active",
            "probability": None,
            "entry_evidence": "Contracts remain valid, but contract-level inspection, customer acceptance and recognized amount are unverified.",
            "numeric_output": None,
        },
        {
            "scenario_id": "BASE_EVIDENCE_GATE",
            "label": "Base 진입 조건",
            "status": "not-entered",
            "probability": None,
            "entry_evidence": "A filing or other official issuer source identifies contract-level inspection/customer acceptance or recognized revenue amount and period.",
            "calculation_rule": "Add only the confirmed amount after checking overlap with reported CFS revenue; keep all other amounts U.",
            "numeric_output": None,
        },
        {
            "scenario_id": "BULL_EVIDENCE_GATE",
            "label": "Bull 진입 조건",
            "status": "not-entered",
            "probability": None,
            "entry_evidence": "Base evidence plus a new official contract or production revenue for a new product, together with actual margin and operating-cash-flow improvement.",
            "calculation_rule": "Use only officially confirmed incremental amounts and actual CFS margins; do not preload CXL, Gen6 or service revenue.",
            "numeric_output": None,
        },
        {
            "scenario_id": "BEAR_EVIDENCE_GATE",
            "label": "Bear 경고 조건",
            "status": "partial-warning",
            "probability": None,
            "entry_evidence": {
                "contract_specific_schedule_warning": "active for R04+R07 because the official end date was extended",
                "cash_conversion_warning": "active because inventory rose while OCF weakened from 2025Q4 to 2026Q1",
                "enterprise_case": "not quantified without contract-level impact or a new half-year filing",
            },
            "calculation_rule": "Defer or remove only the amount officially linked to a delay, reduction or cancellation; use actual margin and cash-flow deterioration without an arbitrary haircut.",
            "numeric_output": None,
        },
    ]

    state_by_id = {state["state_id"]: state for state in margin_history["historical_reference_states"]}
    margin_anchors = [
        {
            "anchor_id": anchor_id,
            "period": state_by_id[anchor_id]["period"],
            "observed_operating_margin": state_by_id[anchor_id]["operating_margin"],
            "classification": state_by_id[anchor_id]["classification"],
        }
        for anchor_id in ("LATEST_Q1_STRESS", "FY2025_TRANSITION", "Q4_2025_HIGH_DELIVERY")
    ]
    new_contracts = [row for row in contract_states if next(c for c in contracts["latest_contracts"] if c["original_rcept_no"] == row["original_rcept_no"])["is_new_2026_contract"]]
    contract_value_cases = [
        {
            "case_id": "+".join(row["source_ids"]),
            "label": row["product"],
            "contract_value_krw": row["contract_value_krw"],
            "source_ids": row["source_ids"],
        }
        for row in sorted(new_contracts, key=lambda row: row["contract_value_krw"])
    ]
    contract_value_cases.append(
        {
            "case_id": "ALL_NEW_2026",
            "label": "2026년 신규계약 4건 합계",
            "contract_value_krw": sum(row["contract_value_krw"] for row in new_contracts),
            "source_ids": [source_id for row in new_contracts for source_id in row["source_ids"]],
        }
    )
    sensitivity_rows: list[dict[str, Any]] = []
    for case in contract_value_cases:
        for anchor in margin_anchors:
            sensitivity_rows.append(
                {
                    "contract_case_id": case["case_id"],
                    "contract_value_krw": case["contract_value_krw"],
                    "margin_anchor_id": anchor["anchor_id"],
                    "observed_operating_margin": anchor["observed_operating_margin"],
                    "counterfactual_operating_result_krw": round(case["contract_value_krw"] * anchor["observed_operating_margin"]),
                    "formula": "official contract value × observed company-wide CFS operating margin",
                    "classification": "M/E counterfactual response; not a forecast, product margin or recognized revenue",
                }
            )

    sensitivity = {
        "title": "Official contract-value × observed CFS operating-margin response table",
        "status": "counterfactual-only",
        "warning": "This table assumes full recognition only to show mechanical sensitivity. It is not assigned a period or probability and must not be added to reported revenue because recognition and overlap are U.",
        "contract_value_cases": contract_value_cases,
        "margin_anchors": margin_anchors,
        "rows": sensitivity_rows,
    }

    for state in contract_states:
        checks.append(make_check(f"CONTRACT-U-{state['latest_rcept_no']}", "contract_state", state["recognition_state"], "U"))
        checks.append(make_check(f"CONTRACT-REVENUE-NULL-{state['latest_rcept_no']}", "contract_state", state["confirmed_recognized_revenue_krw"], None))
    checks.extend(
        [
            make_check("CONTRACT-CANCELLATION-COUNT", "contract_state", contracts["cancellation_count"], 0),
            make_check("FORECAST-TOTAL-REMAINS-U", "forecast", forecast["components"]["forecast_total_revenue_krw"], None),
            make_check("SCENARIO-PROBABILITIES-UNASSIGNED", "scenario", all(row["probability"] is None for row in scenarios), True),
            make_check("BASE-NUMERIC-OUTPUT-UNASSIGNED", "scenario", scenarios[1]["numeric_output"], None),
            make_check("SENSITIVITY-LABEL", "sensitivity", sensitivity["status"], "counterfactual-only"),
            make_check("WORKING-CAPITAL-WARNING", "scenario", inventory_increased and ocf_worsened, True),
        ]
    )

    result = {
        "title": "Exicon conditional forecast and evidence-gated scenarios",
        "revenue_recognition_rule": {
            "source_ids": ["R01", "R02"],
            "rule": "Equipment revenue requires completed installation, testing and inspection plus customer acceptance that the equipment operates as designed.",
            "audit_evidence": "The 2025 CFS auditor identified premature product-revenue recognition and cutoff as a key audit matter.",
            "prohibited_shortcuts": [
                "contract end date as revenue date",
                "payment terms as recognition percentage",
                "delivery amount as accepted or recognized revenue",
                "unknown values converted to zero",
            ],
        },
        "contract_states": contract_states,
        "forecast": forecast,
        "scenarios": scenarios,
        "counterfactual_sensitivity": sensitivity,
        "next_evidence_gate": {
            "filing": "2026 half-year report or later periodic report",
            "required_checks": [
                "contract-level inspection/customer acceptance or recognized revenue evidence",
                "inventory composition and valuation loss",
                "revenue, receivables and OCF conversion together",
                "new, corrected, reduced or terminated contract disclosures",
                "whether any confirmed contract revenue is already included in actual CFS revenue",
            ],
        },
    }
    return result, checks


def select_balance_values(financial_rows: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, Any]]:
    reverse_ids = {account_id: metric for metric, account_id in BALANCE_ACCOUNT_IDS.items()}
    values: dict[str, int] = {}
    sources: dict[str, Any] = {}
    for row in financial_rows:
        if row["source_id"] != "DART-FS-2026-Q1-CFS" or row["raw"].get("sj_div") != "BS":
            continue
        account_id = row["raw"].get("account_id")
        if account_id not in reverse_ids:
            continue
        metric = reverse_ids[account_id]
        values[metric] = int(row["numeric"]["thstrm_amount"])
        sources[metric] = {
            "source_id": row["source_id"],
            "rcept_no": row["raw"]["rcept_no"],
            "account_id": account_id,
            "account_name": row["raw"]["account_nm"],
            "source_file": row["source_file"],
        }
    missing = sorted(set(BALANCE_ACCOUNT_IDS) - set(values))
    if missing:
        raise ValueError(f"Missing balance accounts: {missing}")
    return values, sources


def dart_listed_shares(share_rows: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    candidates = [
        row
        for row in share_rows
        if row["source_id"] == "DART-STOCK_TOTAL-2026-Q1"
        and row["dataset"] == "stock_total"
        and row["raw"].get("se") == "합계"
    ]
    if len(candidates) != 1:
        raise ValueError(f"Expected one 2026Q1 DART stock-total row, got {len(candidates)}")
    row = candidates[0]
    return int(row["numeric"]["istc_totqy"]), {
        "source_id": row["source_id"],
        "rcept_no": row["raw"]["rcept_no"],
        "source_file": row["source_file"],
        "stlm_dt": row["raw"]["stlm_dt"],
    }


def build_market_and_peers(
    market_snapshot: dict[str, Any],
    financial_rows: list[dict[str, Any]],
    share_rows: list[dict[str, Any]],
    phase3_history: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    official = market_snapshot["official_observation"]
    close = int(official["close_krw"])
    listed_shares = int(official["listed_shares"])
    market_cap = close * listed_shares
    dart_shares, dart_share_source = dart_listed_shares(share_rows)
    balance, balance_sources = select_balance_values(financial_rows)

    net_cash = (
        balance["cash_and_cash_equivalents"]
        + balance["short_term_deposits"]
        - balance["current_borrowing_debt"]
        - balance["noncurrent_borrowing_debt"]
    )
    enterprise_value = market_cap - net_cash

    rows = {row["quarter"]: row for row in phase3_history["rows"]}
    ltm_quarters = ["2025Q2", "2025Q3", "2025Q4", "2026Q1"]
    ltm_revenue = sum(rows[quarter]["flow_values"]["revenue"] for quarter in ltm_quarters)
    ltm_operating_income = sum(rows[quarter]["flow_values"]["operating_income"] for quarter in ltm_quarters)
    fy2025_revenue = sum(rows[quarter]["flow_values"]["revenue"] for quarter in ("2025Q1", "2025Q2", "2025Q3", "2025Q4"))
    fy2025_operating_income = sum(rows[quarter]["flow_values"]["operating_income"] for quarter in ("2025Q1", "2025Q2", "2025Q3", "2025Q4"))
    ltm_revenue_formula_check = fy2025_revenue + rows["2026Q1"]["flow_values"]["revenue"] - rows["2025Q1"]["flow_values"]["revenue"]
    ltm_oi_formula_check = fy2025_operating_income + rows["2026Q1"]["flow_values"]["operating_income"] - rows["2025Q1"]["flow_values"]["operating_income"]

    valuation = {
        "market_date": market_snapshot["trade_date"],
        "price_krw": close,
        "listed_shares": listed_shares,
        "market_cap_krw": market_cap,
        "share_count_rule": "Use total listed shares for KRX market capitalization, not free-float shares.",
        "balance_sheet_date": "2026-03-31",
        "net_cash_bridge": {
            "cash_and_cash_equivalents_krw": balance["cash_and_cash_equivalents"],
            "short_term_deposits_krw": balance["short_term_deposits"],
            "current_borrowing_debt_krw": balance["current_borrowing_debt"],
            "noncurrent_borrowing_debt_krw": balance["noncurrent_borrowing_debt"],
            "net_cash_krw": net_cash,
            "formula": "cash + short-term deposits - current borrowing debt - noncurrent borrowing debt",
            "scope_note": "Strategic and other non-current financial investments are excluded; no separate lease adjustment is added beyond the filing's borrowing-debt accounts.",
        },
        "enterprise_value_krw": enterprise_value,
        "enterprise_value_formula": "market capitalization - net cash",
        "ltm_period": "2025Q2-2026Q1",
        "ltm_revenue_krw": ltm_revenue,
        "ltm_operating_income_krw": ltm_operating_income,
        "self_diagnostic_multiples": {
            "ev_to_ltm_sales": ratio(enterprise_value, ltm_revenue),
            "ev_to_ltm_operating_income": ratio(enterprise_value, ltm_operating_income),
            "market_cap_to_2026q1_equity": ratio(market_cap, balance["equity"]),
            "classification": "E current-price diagnostics, not fair value or a target price",
        },
        "time_mismatch_warning": "The market price is at 2026-08-13 while net cash and LTM financials end at 2026-03-31.",
    }

    peers = [
        {
            "source_id": "R14",
            "company": "ISC",
            "official_source": "https://kind.krx.co.kr/external/2026/05/15/000123/20260515000186/11013.htm",
            "structural_difference": "The core business is consumable test sockets, with equipment/material additions; revenue cadence and replacement demand differ from Exicon's acceptance-gated equipment sales.",
            "usable_scope": "business-model and cash-conversion comparison only",
        },
        {
            "source_id": "R15",
            "company": "TechWing",
            "official_source": "https://kind.krx.co.kr/external/2026/05/15/001510/20260515003309/11013.htm",
            "structural_difference": "Its portfolio includes handlers, burn-in equipment, HBM prober development and a large parts/peripherals stream, so consolidated mix is not the same as Exicon.",
            "usable_scope": "equipment-cycle and recurring-parts contrast only",
        },
        {
            "source_id": "R16",
            "company": "FormFactor",
            "official_source": "https://www.sec.gov/Archives/edgar/data/1039399/000103939926000023/form-20260328.htm",
            "structural_difference": "It is a global probe-card and test-and-measurement platform reporting under US GAAP and in USD, with a broader installed base and segment mix.",
            "usable_scope": "global test-demand and margin-structure context only",
        },
    ]
    reverse_expectation = {
        "conclusion": "Current enterprise value can be measured, but a defensible required-revenue point cannot be produced until a same-date, same-basis peer multiple is available.",
        "required_revenue_function": "enterprise value / selected comparable EV-to-sales multiple",
        "selected_comparable_ev_to_sales_multiple": None,
        "required_revenue_krw": None,
        "required_operating_income_function": "enterprise value / selected comparable EV-to-operating-income multiple",
        "selected_comparable_ev_to_operating_income_multiple": None,
        "required_operating_income_krw": None,
        "target_price_krw": None,
        "interpretation": "Because LTM operating profit depends heavily on one high-delivery quarter and current contract recognition is U, the market value implies reliance on future execution rather than only the current trailing run rate.",
    }

    checks.extend(
        [
            make_check("MARKET-CAP-IDENTITY", "valuation", market_cap, official["calculated_market_cap_krw"]),
            make_check("DART-KRX-LISTED-SHARES", "valuation", dart_shares, listed_shares),
            make_check("NAVER-CLOSE-CORROBORATION", "valuation", market_snapshot["secondary_corroboration"]["close_krw"], close),
            make_check(
                "NET-CASH-IDENTITY",
                "valuation",
                net_cash,
                balance["cash_and_cash_equivalents"]
                + balance["short_term_deposits"]
                - balance["current_borrowing_debt"]
                - balance["noncurrent_borrowing_debt"],
            ),
            make_check("ENTERPRISE-VALUE-IDENTITY", "valuation", enterprise_value, market_cap - net_cash),
            make_check("LTM-REVENUE-BRIDGE", "valuation", ltm_revenue, ltm_revenue_formula_check),
            make_check("LTM-OI-BRIDGE", "valuation", ltm_operating_income, ltm_oi_formula_check),
            make_check("PEER-MULTIPLE-NOT-FORCED", "peer", reverse_expectation["selected_comparable_ev_to_sales_multiple"], None),
            make_check("TARGET-PRICE-NOT-PRODUCED", "valuation", reverse_expectation["target_price_krw"], None),
        ]
    )

    result = {
        "title": "Exicon market-value bridge, reverse-expectation framework and peer-screen result",
        "market_snapshot_source": market_snapshot,
        "valuation": valuation,
        "sources": {"balance_sheet_accounts": balance_sources, "dart_share_count": dart_share_source},
        "peer_screen": {
            "companies": peers,
            "same_basis_multiple_set_available": False,
            "decision": "Do not average or apply peer multiples in Phase 4; retain peers as structural cross-checks.",
        },
        "reverse_expectation": reverse_expectation,
    }
    return result, checks


def main() -> int:
    generated_at = datetime.now(KST)
    run_id = generated_at.strftime("%Y%m%dT%H%M%S%z")
    run_dir = PHASE4_RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    financial_path = NORMALIZED / "financial_rows.json"
    share_path = NORMALIZED / "share_rows.json"
    contracts_path = NORMALIZED / "contracts.json"
    phase3_history_path = latest_file(NORMALIZED / "phase3" / "runs", "historical_independent_quarters_cfs.json")
    phase3_contract_path = phase3_history_path.parent / "contract_timing_evidence.json"
    market_path = latest_file(MARKET_RUNS, "market_snapshot.json")
    gate_path = latest_gate_summary()
    q1_xml_path = ROOT / "raw" / "dart" / "documents" / "extracted" / "20260515001551" / "20260515001551.xml"
    audit_xml_path = ROOT / "raw" / "dart" / "documents" / "extracted" / "20260316001681" / "20260316001681_00761.xml"

    financial_rows = read_json(financial_path)
    share_rows = read_json(share_path)
    contracts = read_json(contracts_path)
    phase3_history = read_json(phase3_history_path)
    phase3_contract = read_json(phase3_contract_path)
    market_snapshot = read_json(market_path)
    gate = read_json(gate_path)

    margin_history, margin_checks = build_margin_history(financial_rows, phase3_history)
    conditional_model, contract_checks = build_contract_and_scenarios(
        contracts, phase3_contract, margin_history, phase3_history
    )
    market_model, market_checks = build_market_and_peers(
        market_snapshot, financial_rows, share_rows, phase3_history
    )
    gate_checks = [
        make_check("GATE-STATUS", "latest_disclosure_gate", gate["status"], "000"),
        make_check("GATE-NEW-RELEVANT", "latest_disclosure_gate", gate["new_relevant_count"], 0),
        make_check("GATE-HALF-YEAR", "latest_disclosure_gate", gate["half_year_count"], 0),
        make_check(
            "GATE-CANCELLATION",
            "latest_disclosure_gate",
            gate["termination_or_cancellation_count"],
            0,
        ),
    ]
    checks = gate_checks + margin_checks + contract_checks + market_checks
    check_output = {
        "generated_at": generated_at.isoformat(),
        "check_count": len(checks),
        "passed_count": sum(check["passed"] for check in checks),
        "failed_count": sum(not check["passed"] for check in checks),
        "checks": checks,
    }

    outputs = {
        "historical_margin_drivers_cfs.json": margin_history,
        "conditional_forecast_and_scenarios.json": conditional_model,
        "market_expectations_and_peers.json": market_model,
        "phase4_checks.json": check_output,
    }
    for name, value in outputs.items():
        write_json(run_dir / name, value)

    input_paths = [
        financial_path,
        share_path,
        contracts_path,
        phase3_history_path,
        phase3_contract_path,
        market_path,
        gate_path,
        q1_xml_path,
        audit_xml_path,
    ]
    manifest = {
        "phase": "Phase 4 conditional forecast, scenarios and valuation",
        "run_id": run_id,
        "generated_at": generated_at.isoformat(),
        "inputs": [
            {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path)} for path in input_paths
        ],
        "outputs": [
            {"path": str((run_dir / name).relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(run_dir / name)}
            for name in outputs
        ],
        "source_hierarchy": {
            "issuer_and_fss": "OpenDART/DART primary",
            "market_actions": "KIND supplemental",
            "price": "KRX-operated KIND official observation; Naver Finance secondary corroboration",
        },
        "api_key_logged": False,
        "checks": {
            "count": check_output["check_count"],
            "passed": check_output["passed_count"],
            "failed": check_output["failed_count"],
        },
    }
    write_json(run_dir / "phase4_run_manifest.json", manifest)

    print(
        json.dumps(
            {
                "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
                "margin_rows": margin_history["row_count"],
                "contracts": len(conditional_model["contract_states"]),
                "forecast_status": conditional_model["forecast"]["status"],
                "scenario_state": conditional_model["scenarios"][0]["scenario_id"],
                "checks_passed": check_output["passed_count"],
                "checks_failed": check_output["failed_count"],
            },
            ensure_ascii=False,
        )
    )
    return 1 if check_output["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
