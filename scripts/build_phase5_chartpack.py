from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NORMALIZED = ROOT / "raw" / "dart" / "normalized"
PHASE5_RUNS = NORMALIZED / "phase5" / "runs"
KST = timezone(timedelta(hours=9))
RUN_ID_FORMAT = "%Y%m%dT%H%M%S%z"


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


def parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp for {label}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp for {label} must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def run_timestamp(path: Path, manifest_name: str | None = None) -> datetime:
    if manifest_name:
        manifest_path = path / manifest_name
        if manifest_path.is_file():
            generated_at = read_json(manifest_path).get("generated_at")
            if generated_at:
                return parse_timestamp(generated_at, str(manifest_path))
    try:
        return datetime.strptime(path.name, RUN_ID_FORMAT).astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Run directory has no parseable timestamp: {path}") from exc


def latest_run_dir(root: Path, required_filename: str, manifest_name: str | None = None) -> Path:
    candidates = [path.parent for path in root.glob(f"*/{required_filename}") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No {required_filename} under {root}")
    return max(candidates, key=lambda path: run_timestamp(path, manifest_name))


def resolve_path(value: str, *, base: Path = ROOT) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_run_dir(value: str | None, root: Path, required_filename: str, manifest_name: str) -> Path:
    if value is None:
        return latest_run_dir(root, required_filename, manifest_name)
    direct = resolve_path(value)
    if direct.is_dir():
        run_dir = direct
    else:
        run_dir = (root / value).resolve()
    required = run_dir / required_filename
    if not required.is_file():
        raise FileNotFoundError(f"Input run is missing {required_filename}: {run_dir}")
    return run_dir


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def manifest_record(manifest: dict[str, Any], key: str, suffix: str) -> dict[str, Any]:
    matches = [row for row in manifest.get(key, []) if row.get("path", "").replace("\\", "/").endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {key} record ending with {suffix!r}; found {len(matches)}")
    return matches[0]


def verify_record(record: dict[str, Any]) -> Path:
    path = resolve_path(record["path"])
    if not path.is_file():
        raise FileNotFoundError(f"Manifest input/output is missing: {path}")
    expected_hash = record.get("sha256")
    if expected_hash and sha256(path) != expected_hash:
        raise ValueError(f"Manifest hash mismatch: {path}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Phase 5 chart-data package from one coherent Phase 4 lineage.")
    parser.add_argument(
        "--input-run",
        help="Phase 4 run directory or run id. Defaults to the newest run by parsed manifest timestamp.",
    )
    parser.add_argument("--gate", help="Explicit gate_summary.json. It must match the selected Phase 4 manifest lineage.")
    parser.add_argument("--output-dir", help="Explicit Phase 5 output directory. Defaults to a new timestamped run directory.")
    parser.add_argument("--max-gate-age-hours", type=float, default=24.0, help="Maximum gate age at build time (default: 24).")
    parser.add_argument("--allow-stale-inputs", action="store_true", help="Allow an old but lineage-consistent gate for historical reproduction.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of Phase 5 JSON outputs in an explicit output directory.")
    return parser.parse_args()


def validate_freshness(
    generated_at: datetime,
    phase4_manifest: dict[str, Any],
    gate: dict[str, Any],
    *,
    max_gate_age_hours: float,
    allow_stale_inputs: bool,
) -> None:
    if max_gate_age_hours <= 0:
        raise ValueError("--max-gate-age-hours must be positive")
    gate_retrieved = parse_timestamp(gate["retrieved_at"], "gate.retrieved_at")
    gate_cutoff = parse_timestamp(gate["project_cutoff"], "gate.project_cutoff")
    phase4_generated = parse_timestamp(phase4_manifest["generated_at"], "phase4 manifest generated_at")
    build_time = generated_at.astimezone(timezone.utc)
    if gate_cutoff > gate_retrieved:
        raise ValueError("Gate project_cutoff is later than gate retrieval time")
    if phase4_generated < gate_retrieved:
        raise ValueError("Selected Phase 4 run predates its disclosure gate")
    if build_time < phase4_generated - timedelta(minutes=5):
        raise ValueError("Selected Phase 4 run is implausibly newer than the build clock")
    gate_age = build_time - gate_retrieved
    if gate_age > timedelta(hours=max_gate_age_hours) and not allow_stale_inputs:
        raise ValueError(
            f"Disclosure gate is stale ({gate_age.total_seconds() / 3600:.1f}h old); "
            "refresh upstream data or pass --allow-stale-inputs for historical reproduction"
        )
    if gate.get("status") != "000":
        raise ValueError(f"Disclosure gate status is not successful: {gate.get('status')!r}")


def make_check(
    check_id: str,
    category: str,
    actual: Any,
    expected: Any,
    *,
    tolerance: float | None = None,
    note: str = "",
) -> dict[str, Any]:
    if tolerance is None:
        passed = actual == expected
        difference = None
    else:
        difference = abs(float(actual) - float(expected))
        passed = difference <= tolerance
    return {
        "check_id": check_id,
        "category": category,
        "actual": actual,
        "expected": expected,
        "difference": difference,
        "tolerance": tolerance,
        "passed": passed,
        "note": note,
    }


def clean_xml_text(segment: str) -> str:
    value = re.sub(r"<[^>]+>", " ", segment)
    value = html.unescape(value)
    return " ".join(value.split())


def last_amount_share(block: str) -> tuple[int, float]:
    matches = re.findall(r"([0-9][0-9,]*)\s*\(([0-9]+(?:\.[0-9]+)?)%\)", block)
    if not matches:
        if re.search(r"(?:^|\s)-\s*$", block) or re.search(r"\(0(?:\.0+)?%\)", block):
            return 0, 0.0
        raise ValueError(f"No amount/share pair found in block: {block[-300:]}")
    amount, share = matches[-1]
    return int(amount.replace(",", "")) * 1_000_000, float(share) / 100.0


def extract_product_mix(
    rcept_no: str,
    period: str,
    period_type: str,
    marker: str,
) -> dict[str, Any]:
    source_path = ROOT / "raw" / "dart" / "documents" / "extracted" / rcept_no / f"{rcept_no}.xml"
    raw = source_path.read_text(encoding="utf-8", errors="replace")
    start = raw.find(marker)
    note = "상기 매출액 및 비율은 별도 기준"
    end = raw.find(note, start)
    if start < 0 or end < 0:
        raise ValueError(f"Could not locate OFS product-mix table in {rcept_no}")
    text = clean_xml_text(raw[start : end + len(note) + 100])

    positions = {
        "Memory Tester": text.find("Memory Tester"),
        "SSD Tester": text.find("SSD Tester"),
        "SoC Tester": text.find("SoC Tester"),
        "total": text.find("합 계"),
        "note": text.find(note),
    }
    if not (positions["Memory Tester"] < positions["SSD Tester"] < positions["SoC Tester"] < positions["total"]):
        raise ValueError(f"Unexpected product order in {rcept_no}: {positions}")

    memory = last_amount_share(text[positions["Memory Tester"] : positions["SSD Tester"]])
    ssd = last_amount_share(text[positions["SSD Tester"] : positions["SoC Tester"]])
    soc = last_amount_share(text[positions["SoC Tester"] : positions["total"]])
    total = last_amount_share(text[positions["total"] : positions["note"]])

    products = [
        {"product": "Memory Tester", "amount_krw": memory[0], "share": memory[1]},
        {"product": "SSD Tester", "amount_krw": ssd[0], "share": ssd[1]},
        {"product": "SoC Tester", "amount_krw": soc[0], "share": soc[1]},
    ]
    reported_zero_products = [
        item["product"]
        for item, block in zip(
            products,
            [
                text[positions["Memory Tester"] : positions["SSD Tester"]],
                text[positions["SSD Tester"] : positions["SoC Tester"]],
                text[positions["SoC Tester"] : positions["total"]],
            ],
        )
        if item["amount_krw"] == 0
        and (re.search(r"(?:^|\s)-\s*$", block) or re.search(r"\(0(?:\.0+)?%\)", block))
    ]
    for item in products:
        item["amount_classification"] = (
            "E zero amount inferred from a reported blank/dash plus product-total reconciliation"
            if item["product"] in reported_zero_products
            else "F issuer-disclosed amount"
        )
        item["share_classification"] = "F issuer-disclosed share"
    return {
        "period": period,
        "period_type": period_type,
        "basis": "OFS",
        "unit": "KRW",
        "products": products,
        "total_krw": total[0],
        "reported_total_share": total[1],
        "source_id": {
            "20250317000963": "DART-PRODUCT-2024FY-OFS",
            "20260316001681": "R02",
            "20250514000989": "DART-PRODUCT-2025Q1-OFS",
            "20260515001551": "R01",
            "20260814001521": "R17",
        }[rcept_no],
        "rcept_no": rcept_no,
        "source_file": source_path.relative_to(ROOT).as_posix(),
        "extraction_marker": marker,
        "classification": (
            "F disclosed shares and nonblank amounts; E blank/dash zero amounts reconciled to the disclosed total"
            if reported_zero_products
            else "F issuer-disclosed separate-basis product revenue"
        ),
        "warning": "OFS product mix only; do not use as the denominator of the CFS time series. CLT and boards remain inside Memory Tester.",
        "normalization_note": (
            f"Reported dash or blank amount at 0.0% treated as zero for {', '.join(reported_zero_products)} after product-total reconciliation."
            if reported_zero_products
            else None
        ),
    }


def build_visualizations(
    phase3_history: dict[str, Any],
    phase4_margin: dict[str, Any],
    phase4_conditional: dict[str, Any],
    phase4_market: dict[str, Any],
    gate: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []

    v1 = {
        "title": "AI·HPC 수요에서 엑시콘 매출까지: 중간 증거가 필요한 경로",
        "message": "산업 수요가 커져도 고객 투자·장비 발주·설치·검수·수락을 통과해야 엑시콘의 연결 매출이 된다.",
        "format": "left-to-right evidence path",
        "nodes": [
            {
                "id": "industry_demand",
                "label": "AI·HPC·고성능 메모리\n테스트 수요",
                "state": "C",
                "source_ids": ["R11", "R12", "R13"],
                "scope": "industry context; not Exicon-specific demand",
            },
            {
                "id": "customer_investment",
                "label": "고객의 테스트 투자·\n설비 필요",
                "state": "C",
                "source_ids": ["R12", "R13"],
                "scope": "industry/customer context; Exicon linkage not automatic",
            },
            {
                "id": "contract",
                "label": "엑시콘 장비 계약",
                "state": "F",
                "source_ids": ["R03", "R04", "R05", "R06", "R07"],
                "scope": "official contract value and schedule",
            },
            {
                "id": "production_delivery",
                "label": "제작·납품·설치·테스트",
                "state": "F/U",
                "source_ids": ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R17"],
                "scope": "delivery-table context is disclosed for 2026 orders; contract-level acceptance remains unverified",
            },
            {
                "id": "acceptance",
                "label": "검수·고객 수락",
                "state": "U",
                "source_ids": ["R01", "R02", "R17"],
                "scope": "required evidence under revenue-recognition policy; contract-level evidence absent",
            },
            {
                "id": "revenue",
                "label": "연결 매출 인식",
                "state": "U",
                "source_ids": ["R01", "R02", "R17"],
                "scope": "contract-level amount and period unverified",
            },
            {
                "id": "cash",
                "label": "채권·현금 회수",
                "state": "F/U",
                "source_ids": ["R01", "R03", "R04", "R05", "R06", "R07", "R17"],
                "scope": "CFS balances are factual; contract-level collection remains unlinked",
            },
        ],
        "edges": [
            {"from": "industry_demand", "to": "customer_investment", "style": "dashed", "state": "C"},
            {"from": "customer_investment", "to": "contract", "style": "dashed", "state": "U-link"},
            {"from": "contract", "to": "production_delivery", "style": "solid", "state": "F-process/U-completion"},
            {"from": "production_delivery", "to": "acceptance", "style": "solid", "state": "U-contract"},
            {"from": "acceptance", "to": "revenue", "style": "solid", "state": "accounting-gate"},
            {"from": "revenue", "to": "cash", "style": "solid", "state": "timing-not-equivalent"},
        ],
        "forbidden_shortcut": "AI/HPC demand -> Exicon revenue",
        "source_note": "R01~R07, R11~R13, R17. Industry evidence is context only; contract end dates, delivery and payment terms are not acceptance evidence.",
    }

    v2 = {
        "title": "반도체 테스트 흐름에서 엑시콘 제품의 공시상 위치",
        "message": "엑시콘의 현재 공시 제품은 후공정 전기검사·신뢰성·에이징 영역에 걸치지만 제품별 단계와 매출 기여는 공시된 범위까지만 확인된다.",
        "format": "process map",
        "stages": [
            {"id": "wafer", "label": "웨이퍼 제조", "scope": "upstream context", "exicon": []},
            {"id": "package", "label": "패키징·조립", "scope": "upstream context", "exicon": []},
            {
                "id": "package_test",
                "label": "웨이퍼·패키지 전기검사·\n기능 테스트",
                "scope": "company-disclosed use",
                "exicon": ["Memory Tester", "SoC/CIS Tester*"],
            },
            {
                "id": "reliability",
                "label": "번인·저주파·\n신뢰성 검사",
                "scope": "company-disclosed use",
                "exicon": ["Burn-in Tester", "CLT·CIB/Board**"],
            },
            {
                "id": "module_system",
                "label": "SSD 에이징·\n모듈/시스템 검사",
                "scope": "company-disclosed use",
                "exicon": ["SSD Tester"],
            },
            {"id": "shipment", "label": "고객 출하·양산", "scope": "downstream context", "exicon": []},
        ],
        "notes": [
            "* SoC 표에는 CIS Tester가 공시되며, 현재 제품표가 세부 공정 단계를 모두 분리하지는 않는다.",
            "** CLT·CIB·Board는 공시상 Memory Tester 범주에 포함되며 별도 매출선으로 분해하지 않는다.",
            "위치는 제품 용도에 관한 공시 설명이며 시장점유율·경쟁우위를 뜻하지 않는다.",
        ],
        "source_note": "R01, R02 and the issuer's disclosed product-use descriptions.",
    }

    product_periods = [
        extract_product_mix("20250317000963", "2024A", "annual", "2024년 12월 31일 기준"),
        extract_product_mix("20260316001681", "2025A", "annual", "2025년 12월 31일 기준"),
        extract_product_mix("20250514000989", "2025Q1A", "quarter", "2025년 3월 31일 기준"),
        extract_product_mix("20260515001551", "2026Q1A", "quarter", "2026년 3월 31일 기준"),
        extract_product_mix("20260814001521", "2026H1A", "half-year", "(2026년 6월 30일 기준)"),
    ]
    v3 = {
        "title": "별도 공시 제품매출 구성: Memory Tester 중심으로 이동",
        "message": "별도 기준 제품 구성은 Memory Tester 쪽으로 집중됐으며, CLT·CIB·Board는 그 안에 포함돼 별도 매출로 분리할 수 없다.",
        "basis": "OFS",
        "classification": "F",
        "periods": product_periods,
        "warning": "Annual and quarterly periods are shown in separate panels; compare composition within each panel. Do not merge with CFS charts.",
        "source_note": "R01, R02, R17 and 2024FY/2025Q1 issuer periodic reports; product tables on OFS basis. A disclosed 0.0% share is F; a blank/dash amount normalized to zero after product-total reconciliation is E.",
    }

    v4_rows = []
    for row in phase4_margin["rows"]:
        direct_r17_q2 = row["quarter"] == "2026Q2" and {
            source["rcept_no"] for source in row["sources"].values()
        } == {"20260814001521"}
        v4_rows.append(
            {
                "quarter": row["quarter"],
                "basis": row["basis"],
                "classification": (
                    "F revenue and operating income from the R17 disclosed 3-month column; E operating-margin ratio"
                    if direct_r17_q2
                    else row["classification"]
                ),
                "revenue_krw": row["flow_values"]["revenue"],
                "operating_income_krw": row["flow_values"]["operating_income"],
                "operating_margin": row["derived"]["operating_margin"],
                "metric_classification": (
                    {
                        "revenue_krw": "F R17 disclosed 3-month column",
                        "gross_profit_krw": "F R17 disclosed 3-month column",
                        "operating_income_krw": "F R17 disclosed 3-month column",
                        "net_income_krw": "F R17 disclosed 3-month column",
                        "operating_margin": "E operating_income / revenue",
                        "operating_cash_flow_krw": "E R17 H1 cumulative - R01 Q1 cumulative (shown in V5)",
                    }
                    if direct_r17_q2
                    else None
                ),
                "source_ids": (
                    ["R17"]
                    if direct_r17_q2
                    else sorted({source["source_id"] for source in row["sources"].values()})
                ),
                "source_rcept_nos": sorted({source["rcept_no"] for source in row["sources"].values()}),
            }
        )
    v4 = {
        "title": "연결 독립 분기 매출·영업이익·OPM",
        "message": "2026Q2는 매출 314.7억원·OPM 13.1%로 흑자 전환했지만, 정상 마진을 고정할 만큼 반복 관측은 충분하지 않다.",
        "basis": "CFS",
        "periodicity": "independent quarter",
        "rows": v4_rows,
        "source_note": "OpenDART CFS. For 2026Q2, revenue/gross profit/operating income/net income are R17 disclosed 3-month-column facts (F); only OCF in V5 is H1-Q1 (E). Other derived quarters use cumulative subtraction where a direct quarter column is unavailable.",
    }

    v5_rows = []
    for row in phase3_history["rows"]:
        v5_rows.append(
            {
                "quarter": row["quarter"],
                "basis": row["basis"],
                "inventory_krw": row["period_end_values"]["inventory"],
                "trade_and_other_current_receivables_krw": row["period_end_values"][
                    "trade_and_other_current_receivables"
                ],
                "operating_cash_flow_krw": row["flow_values"]["operating_cash_flow"],
                "operating_cash_flow_classification": row.get("flow_classifications", {}).get(
                    "operating_cash_flow"
                ),
                "operating_cash_flow_formula": row["flow_formulas"]["operating_cash_flow"],
                "balance_measurement": "period-end stock",
                "cash_flow_measurement": "independent-quarter flow",
                "source_id": row["source_id"],
                "source_rcept_no": row["source_rcept_no"],
            }
        )
    v5 = {
        "title": "연결 기말 운전자본과 독립 분기 OCF",
        "message": "2026Q2 매출·이익은 회복됐지만 재고와 채권이 늘고 OCF는 -30.7억원으로 음수여서 현금 전환은 아직 확인되지 않았다.",
        "basis": "CFS",
        "rows": v5_rows,
        "warning": "Inventory and receivables are period-end stocks; OCF is an independent-quarter flow. Co-movement is not causation.",
        "source_note": "R01, R02 and OpenDART CFS historical filings. 2026Q2 OCF is E: R17 H1 cumulative minus R01 Q1 cumulative; Q2 income-statement metrics in V4 are direct R17 3-month facts (F).",
    }

    v6_contracts = []
    for state in phase4_conditional["contract_states"]:
        v6_contracts.append(
            {
                "contract_id": "+".join(state["source_ids"]),
                "source_ids": state["source_ids"],
                "product": state["product"],
                "contract_value_krw": state["contract_value_krw"],
                "start": state["contract_period"]["start"],
                "end": state["contract_period"]["end"],
                "original_end": "2026-07-31" if state["source_ids"] == ["R04", "R07"] else None,
                "schedule_status": state["schedule_status"],
                "recognition_state": state["recognition_state"],
                "confirmed_recognized_revenue_krw": state["confirmed_recognized_revenue_krw"],
                "delivered_amount_context_krw": state["delivery_context"]["reported_amount_krw"],
                "classification": state["classification"],
            }
        )
    v6 = {
        "title": "공시 계약기간과 매출 인식 증거 상태",
        "message": "2026 수주표의 기납품액 172.03억원은 확인되지만, 다섯 계약 모두 검수·고객 수락·수익 인식 금액과 기간은 U다.",
        "contracts": v6_contracts,
        "warning": "Bars encode disclosed contract periods only, not recognition periods or revenue allocation.",
        "source_note": "R03~R07, R17 and P2025-CORR-01; revenue-recognition policy in R01/R02/R17.",
    }

    new_contracts = [state for state in v6_contracts if "P2025-CORR-01" not in state["source_ids"]]
    new_contract_total = sum(row["contract_value_krw"] for row in new_contracts)
    reported_2026_h1 = phase4_conditional["forecast"]["components"][
        "reported_cfs_revenue_through_latest_actual_krw"
    ]
    v7 = {
        "title": "비가산 증거 레인: 실제 매출·계약가치·인식증거",
        "message": "2026H1 실제 매출 412.74억원과 공식 계약가치는 확인되지만 둘을 더할 수 없고, 계약별 수락·인식 귀속이 없어 2026FY는 U다.",
        "format": "non-additive evidence lanes",
        "reported_actuals": [
            {
                "period": "2025FY",
                "revenue_krw": sum(
                    row["flow_values"]["revenue"]
                    for row in phase3_history["rows"]
                    if row["year"] == 2025
                ),
                "basis": "CFS",
                "classification": "F",
            },
            {
                "period": "2026H1",
                "revenue_krw": reported_2026_h1,
                "basis": "CFS",
                "classification": "F",
            },
        ],
        "contract_value_context": {
            "new_2026_contract_value_krw": new_contract_total,
            "contracts": new_contracts,
            "classification": "F contract value; not revenue, backlog or recognized amount",
            "additive_to_revenue": False,
        },
        "recognition_gate": {
            "contracts_with_confirmed_recognition": sum(
                row["confirmed_recognized_revenue_krw"] is not None for row in v6_contracts
            ),
            "confirmed_recognized_revenue_krw": None,
            "state": "U",
        },
        "forecast_2026fy": phase4_conditional["forecast"],
        "warning": "The three lanes are not a waterfall and must not be summed. Contract end dates and payment terms do not allocate revenue.",
        "source_note": "R01~R07, R17; Phase 4 conditional forecast.",
    }

    label_map = {
        "CURRENT_UNRESOLVED": "현재 미해결",
        "BASE_EVIDENCE_GATE": "기준 전환 조건",
        "BULL_EVIDENCE_GATE": "상방 확인 조건",
        "BEAR_EVIDENCE_GATE": "하방 경고 조건",
    }
    v8_scenarios = []
    for scenario in phase4_conditional["scenarios"]:
        v8_scenarios.append(
            {
                **scenario,
                "display_label": label_map[scenario["scenario_id"]],
            }
        )
    v8 = {
        "title": "공식 사건이 들어올 때만 바뀌는 상태",
        "message": "현재는 미해결 상태이며, 기준·상방 조건은 증거 대기, 하방은 일정 정정과 재고·채권·음수 OCF에서 부분 경고가 켜져 있다.",
        "format": "state table without numeric axis",
        "scenarios": v8_scenarios,
        "warning": "No probabilities and no numeric case outputs are assigned.",
        "source_note": "R01~R07, R17 and Phase 4 event-state model.",
    }

    sensitivity = phase4_conditional["counterfactual_sensitivity"]
    allowed_case_ids = {"R03", "R04+R07", "R05", "R06"}
    v9_cases = [row for row in sensitivity["contract_value_cases"] if row["case_id"] in allowed_case_ids]
    v9_rows = [row for row in sensitivity["rows"] if row["contract_case_id"] in allowed_case_ids]
    v9 = {
        "title": "반사실 계산: 공식 계약가치 × 과거 연결 OPM",
        "message": "같은 계약가치라도 과거에 관측된 전사 OPM 상태에 따라 손익 반응 방향이 크게 달라져, 계약금액만으로 이익을 추정할 수 없다.",
        "status": "counterfactual; not forecast",
        "metric_definition": "official contract value × observed company-wide CFS operating margin",
        "contract_cases": v9_cases,
        "margin_anchors": sensitivity["margin_anchors"],
        "rows": v9_rows,
        "warning": "Each row is independent. Full contract value and identical company-wide OPM are extreme mechanical assumptions; no recognition rate, product margin or probability is implied.",
        "source_note": "R01~R07; Phase 4 CFS margin observations.",
    }

    valuation = phase4_market["valuation"]
    reverse = phase4_market["reverse_expectation"]
    v10 = {
        "title": "시점 혼합 추정 EV와 내재 기대의 산출 가능 범위",
        "message": "시장가치와 기업가치는 계산할 수 있지만, 동일 기준 Peer 배수가 없어 요구 매출·이익과 목표가격은 U다.",
        "valuation": valuation,
        "reverse_expectation": reverse,
        "format": "market-value bridge plus calculation gates",
        "warning": valuation["time_mismatch_warning"] + " Self-diagnostic multiples are not fair value.",
        "source_note": "R09 and R17; KIND/KRX-operated market data plus CFS balance-sheet data.",
    }

    latest_retrieval = gate["retrieved_at"]
    v11 = {
        "title": "근거 기반 업데이트 모니터링",
        "message": "다음 공시에서는 계약 규모보다 검수·인식, 재고 전환, OCF 회복이 함께 확인되는지를 먼저 본다.",
        "format": "tri-state monitoring table",
        "allowed_states": ["확인", "경고", "U"],
        "rows": [
            {
                "item": "2026년 반기보고서 제출 여부",
                "scope": "회사 전체",
                "state": "확인",
                "current_evidence": "2026-08-14 제출·모델 반영 완료",
                "transition": "3분기보고서 제출 시 CFS 누계·주석 재구성",
                "changes": "V3~V5, V7~V11",
                "source_ids": ["R10", "R17"],
            },
            {
                "item": "신규·정정·감액·해지 공시",
                "scope": "계약별",
                "state": "확인",
                "current_evidence": "8/31 기준원장 대비 신규 관련 0, 해지·취소 0",
                "transition": "새 공시의 원계약 체인 연결",
                "changes": "V6~V9, V11",
                "source_ids": ["R10"],
            },
            {
                "item": "계약별 검수·고객 수락·인식액",
                "scope": "다섯 계약",
                "state": "U",
                "current_evidence": "기납품 172.03억원 확인; 검수·수락·인식 귀속 U",
                "transition": "공식 금액·기간 확인 및 CFS 중복검사",
                "changes": "V6~V10",
                "source_ids": ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R17"],
            },
            {
                "item": "R04+R07 Interface Board 일정",
                "scope": "해당 계약만",
                "state": "경고",
                "current_evidence": "공식 종료일 정정",
                "transition": "추가 연장·감액·검수 확인",
                "changes": "V6, V8, V11",
                "source_ids": ["R04", "R07"],
            },
            {
                "item": "재고·채권·OCF 전환",
                "scope": "회사 전체",
                "state": "경고",
                "current_evidence": "Q2 재고·채권 증가, OCF -30.7억원",
                "transition": "재고·채권 정상화와 OCF 양수 전환 확인",
                "changes": "V5, V8, V11",
                "source_ids": ["R01", "R02", "R17"],
            },
            {
                "item": "제품 구성과 고객 집중",
                "scope": "OFS 제품표/CFS 고객",
                "state": "확인",
                "current_evidence": "2026H1 OFS Memory 91.1%, SSD 8.9%",
                "transition": "분산 또는 추가 집중을 공식 표로 확인",
                "changes": "V3, V11",
                "source_ids": ["R01", "R02", "R17"],
            },
            {
                "item": "SoC·CXL·서비스 양산매출",
                "scope": "신규 제품·서비스",
                "state": "U",
                "current_evidence": "별도 연결 매출 기여 미확인",
                "transition": "공식 양산·매출 금액 확인",
                "changes": "V1~V3, V8, V11",
                "source_ids": ["R01", "R02", "R17"],
            },
            {
                "item": "시장가치·순현금",
                "scope": "가치평가 입력",
                "state": "확인",
                "current_evidence": "가격 8/28, 재무 6/30 시점 차이 존재",
                "transition": "새 종가·새 CFS로 같은 기준 갱신",
                "changes": "V10, V11",
                "source_ids": ["R09", "R17"],
            },
            {
                "item": "동일 기준 Peer 배수",
                "scope": "역산 입력",
                "state": "U",
                "current_evidence": "선택 가능한 공식 동일 기준 배수 없음",
                "transition": "동일 일자·기간·순현금 정의 확보",
                "changes": "V10, V11",
                "source_ids": ["R14", "R15", "R16"],
            },
        ],
        "latest_retrieval": latest_retrieval,
        "source_note": "R01~R17; latest OpenDART gate.",
    }

    visualizations = {
        "V1": v1,
        "V2": v2,
        "V3": v3,
        "V4": v4,
        "V5": v5,
        "V6": v6,
        "V7": v7,
        "V8": v8,
        "V9": v9,
        "V10": v10,
        "V11": v11,
    }

    # Gate checks
    checks.extend(
        [
            make_check("P5-GATE-STATUS", "latest_gate", gate["status"], "000"),
            make_check("P5-GATE-HALF-YEAR", "latest_gate", gate["half_year_count"], 1),
            make_check("P5-GATE-NEW-RELEVANT", "latest_gate", gate["new_relevant_count"], 0),
            make_check("P5-GATE-TERMINATION", "latest_gate", gate["termination_or_cancellation_count"], 0),
            make_check("P5-GATE-KEY-LOG", "security", gate["api_key_logged"], False),
        ]
    )

    # V1/V2 evidence and shortcut controls
    checks.extend(
        [
            make_check("P5-V1-NODE-COUNT", "V1", len(v1["nodes"]), 7),
            make_check("P5-V1-NO-SHORTCUT", "V1", any(edge["from"] == "industry_demand" and edge["to"] == "revenue" for edge in v1["edges"]), False),
            make_check("P5-V1-ACCEPTANCE-U", "V1", next(node for node in v1["nodes"] if node["id"] == "acceptance")["state"], "U"),
            make_check("P5-V2-MEMORY-NO-SPLIT", "V2", any("CLT·CIB/Board" in item for stage in v2["stages"] for item in stage["exicon"]), True),
        ]
    )

    # V3 OFS product mix checks
    for period in product_periods:
        amount_sum = sum(item["amount_krw"] for item in period["products"])
        share_sum = sum(item["share"] for item in period["products"])
        checks.extend(
            [
                make_check(f"P5-V3-{period['period']}-BASIS", "V3", period["basis"], "OFS"),
                make_check(f"P5-V3-{period['period']}-AMOUNT", "V3", amount_sum, period["total_krw"]),
                make_check(f"P5-V3-{period['period']}-SHARE", "V3", share_sum, 1.0, tolerance=0.0011),
            ]
        )
    h1_soc = next(
        item
        for period in product_periods
        if period["period"] == "2026H1A"
        for item in period["products"]
        if item["product"] == "SoC Tester"
    )
    checks.extend(
        [
            make_check("P5-V3-2026H1-SOC-SHARE-CLASS", "V3", h1_soc["share_classification"], "F issuer-disclosed share"),
            make_check(
                "P5-V3-2026H1-SOC-AMOUNT-CLASS",
                "V3",
                h1_soc["amount_classification"],
                "E zero amount inferred from a reported blank/dash plus product-total reconciliation",
            ),
        ]
    )

    # V4/V5 historical checks
    phase3_by_quarter = {row["quarter"]: row for row in phase3_history["rows"]}
    checks.append(make_check("P5-V4-ROW-COUNT", "V4", len(v4_rows), len(phase4_margin["rows"])))
    for row in v4_rows:
        expected_opm = row["operating_income_krw"] / row["revenue_krw"]
        matching = phase3_by_quarter[row["quarter"]]
        checks.extend(
            [
                make_check(f"P5-V4-{row['quarter']}-BASIS", "V4", row["basis"], "CFS"),
                make_check(f"P5-V4-{row['quarter']}-OPM", "V4", row["operating_margin"], expected_opm, tolerance=1e-12),
                make_check(f"P5-V4-{row['quarter']}-REV-TIE", "V4", row["revenue_krw"], matching["flow_values"]["revenue"]),
                make_check(f"P5-V4-{row['quarter']}-OP-TIE", "V4", row["operating_income_krw"], matching["flow_values"]["operating_income"]),
            ]
        )
    q2_2026 = next(row for row in v4_rows if row["quarter"] == "2026Q2")
    checks.extend(
        [
            make_check(
                "P5-V4-2026Q2-REVENUE-CLASS",
                "V4",
                q2_2026["metric_classification"]["revenue_krw"],
                "F R17 disclosed 3-month column",
            ),
            make_check(
                "P5-V4-2026Q2-OP-CLASS",
                "V4",
                q2_2026["metric_classification"]["operating_income_krw"],
                "F R17 disclosed 3-month column",
            ),
            make_check(
                "P5-V4-2026Q2-OCF-CLASS",
                "V4",
                q2_2026["metric_classification"]["operating_cash_flow_krw"],
                "E R17 H1 cumulative - R01 Q1 cumulative (shown in V5)",
            ),
        ]
    )
    checks.append(make_check("P5-V5-ROW-COUNT", "V5", len(v5_rows), len(phase3_history["rows"])))
    checks.append(make_check("P5-V5-BASIS", "V5", sorted({row["basis"] for row in v5_rows}), ["CFS"]))
    checks.append(make_check("P5-V5-STOCK-FLOW", "V5", sorted({row["balance_measurement"] for row in v5_rows}), ["period-end stock"]))
    q2_2026_v5 = next(row for row in v5_rows if row["quarter"] == "2026Q2")
    checks.append(
        make_check(
            "P5-V5-2026Q2-OCF-CLASS",
            "V5",
            q2_2026_v5["operating_cash_flow_classification"],
            "E",
        )
    )

    # V6/V7 contract and unknown-state checks
    checks.extend(
        [
            make_check("P5-V6-UNIQUE", "V6", len(v6_contracts), 5),
            make_check("P5-V6-R04-R07", "V6", sum(row["source_ids"] == ["R04", "R07"] for row in v6_contracts), 1),
            make_check("P5-V6-ALL-U", "V6", sorted({row["recognition_state"] for row in v6_contracts}), ["U"]),
            make_check("P5-V6-RECOGNIZED-NULL", "V6", sum(row["confirmed_recognized_revenue_krw"] is not None for row in v6_contracts), 0),
            make_check(
                "P5-V6-DELIVERY-CONTEXT",
                "V6",
                sum(row["delivered_amount_context_krw"] or 0 for row in v6_contracts),
                17_203_000_000,
            ),
            make_check("P5-V7-ENDPOINT-U", "V7", v7["forecast_2026fy"]["status"], "U"),
            make_check("P5-V7-H1-ACTUAL", "V7", v7["reported_actuals"][1]["revenue_krw"], 41_274_152_310),
            make_check("P5-V7-TOTAL-NULL", "V7", v7["forecast_2026fy"]["components"]["forecast_total_revenue_krw"], None),
            make_check("P5-V7-RECOGNITION-U", "V7", v7["recognition_gate"]["state"], "U"),
            make_check("P5-V7-NONADDITIVE", "V7", v7["contract_value_context"]["additive_to_revenue"], False),
        ]
    )

    # V8/V9 scenario and counterfactual checks
    checks.extend(
        [
            make_check("P5-V8-NO-NUMERIC", "V8", sum(row["numeric_output"] is not None for row in v8_scenarios), 0),
            make_check("P5-V8-NO-PROBABILITY", "V8", sum(row["probability"] is not None for row in v8_scenarios), 0),
            make_check("P5-V8-ACTIVE", "V8", sum(row["status"] == "active" for row in v8_scenarios), 1),
            make_check("P5-V9-CASE-COUNT", "V9", len(v9_cases), 4),
            make_check("P5-V9-NO-AGGREGATE", "V9", any(row["case_id"] == "ALL_NEW_2026" for row in v9_cases), False),
            make_check("P5-V9-CELL-COUNT", "V9", len(v9_rows), 16),
            make_check("P5-V9-METRIC", "V9", v9["metric_definition"], "official contract value × observed company-wide CFS operating margin"),
        ]
    )
    for row in v9_rows:
        expected = round(row["contract_value_krw"] * row["observed_operating_margin"])
        checks.append(
            make_check(
                f"P5-V9-{row['contract_case_id']}-{row['margin_anchor_id']}",
                "V9",
                row["counterfactual_operating_result_krw"],
                expected,
                tolerance=1,
            )
        )

    # V10/V11 valuation and monitoring checks
    checks.extend(
        [
            make_check("P5-V10-EV", "V10", valuation["enterprise_value_krw"], valuation["market_cap_krw"] - valuation["net_cash_bridge"]["net_cash_krw"]),
            make_check("P5-V10-PEER-U", "V10", reverse["selected_comparable_ev_to_sales_multiple"], None),
            make_check("P5-V10-REQUIRED-REVENUE-U", "V10", reverse["required_revenue_krw"], None),
            make_check("P5-V10-TARGET-U", "V10", reverse["target_price_krw"], None),
            make_check("P5-V11-STATE-SET", "V11", sorted({row["state"] for row in v11["rows"]}), ["U", "경고", "확인"]),
            make_check("P5-V11-R04-SCOPE", "V11", next(row for row in v11["rows"] if row["item"].startswith("R04+R07"))["scope"], "해당 계약만"),
            make_check("P5-V11-LATEST-GATE", "V11", v11["latest_retrieval"], gate["retrieved_at"]),
        ]
    )

    return visualizations, checks


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(KST)
    phase4_run_dir = resolve_run_dir(
        args.input_run,
        NORMALIZED / "phase4" / "runs",
        "phase4_run_manifest.json",
        "phase4_run_manifest.json",
    )
    phase4_manifest_path = phase4_run_dir / "phase4_run_manifest.json"
    phase4_manifest = read_json(phase4_manifest_path)
    if phase4_manifest.get("run_id") and phase4_manifest["run_id"] != phase4_run_dir.name:
        raise ValueError("Phase 4 manifest run_id does not match its directory")

    phase3_record = manifest_record(
        phase4_manifest,
        "inputs",
        "/historical_independent_quarters_cfs.json",
    )
    lineage_gate_record = manifest_record(phase4_manifest, "inputs", "/gate_summary.json")
    phase3_history_path = verify_record(phase3_record)
    lineage_gate_path = verify_record(lineage_gate_record)

    phase4_margin_path = verify_record(
        manifest_record(phase4_manifest, "outputs", "/historical_margin_drivers_cfs.json")
    )
    phase4_conditional_path = verify_record(
        manifest_record(phase4_manifest, "outputs", "/conditional_forecast_and_scenarios.json")
    )
    phase4_market_path = verify_record(
        manifest_record(phase4_manifest, "outputs", "/market_expectations_and_peers.json")
    )
    for phase4_path in (phase4_margin_path, phase4_conditional_path, phase4_market_path):
        if phase4_path.parent.resolve() != phase4_run_dir.resolve():
            raise ValueError(f"Phase 4 manifest output escapes the selected run directory: {phase4_path}")

    if args.gate:
        gate_path = resolve_path(args.gate)
        if not gate_path.is_file():
            raise FileNotFoundError(f"Explicit gate does not exist: {gate_path}")
        if sha256(gate_path) != lineage_gate_record.get("sha256"):
            raise ValueError("Explicit gate does not match the selected Phase 4 lineage; rebuild Phase 4 first")
    else:
        gate_path = lineage_gate_path

    run_id = generated_at.strftime(RUN_ID_FORMAT)
    run_dir = resolve_path(args.output_dir) if args.output_dir else PHASE5_RUNS / run_id
    if args.output_dir:
        run_id = run_dir.name
    output_names = ("phase5_chart_data.json", "phase5_checks.json", "phase5_run_manifest.json")
    existing_outputs = [run_dir / name for name in output_names if (run_dir / name).exists()]
    if existing_outputs and not args.overwrite:
        raise FileExistsError(f"Output files already exist; pass --overwrite to replace them: {existing_outputs}")

    input_paths = [
        phase4_manifest_path,
        phase3_history_path,
        phase4_margin_path,
        phase4_conditional_path,
        phase4_market_path,
        gate_path,
        ROOT / "raw" / "dart" / "documents" / "extracted" / "20250317000963" / "20250317000963.xml",
        ROOT / "raw" / "dart" / "documents" / "extracted" / "20260316001681" / "20260316001681.xml",
        ROOT / "raw" / "dart" / "documents" / "extracted" / "20250514000989" / "20250514000989.xml",
        ROOT / "raw" / "dart" / "documents" / "extracted" / "20260515001551" / "20260515001551.xml",
        ROOT / "raw" / "dart" / "documents" / "extracted" / "20260814001521" / "20260814001521.xml",
    ]

    phase3_history = read_json(phase3_history_path)
    phase4_margin = read_json(phase4_margin_path)
    phase4_conditional = read_json(phase4_conditional_path)
    phase4_market = read_json(phase4_market_path)
    gate = read_json(gate_path)
    validate_freshness(
        generated_at,
        phase4_manifest,
        gate,
        max_gate_age_hours=args.max_gate_age_hours,
        allow_stale_inputs=args.allow_stale_inputs,
    )

    visualizations, checks = build_visualizations(
        phase3_history,
        phase4_margin,
        phase4_conditional,
        phase4_market,
        gate,
    )

    chart_data = {
        "title": "엑시콘 Phase 5 evidence-centered chart data",
        "phase": "Phase 5",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "project_cutoff": gate["project_cutoff"],
        "latest_disclosure_gate": {
            "retrieved_at": gate["retrieved_at"],
            "status": gate["status"],
            "row_count": gate["row_count"],
            "half_year_count": gate["half_year_count"],
            "new_relevant_count": gate["new_relevant_count"],
            "termination_or_cancellation_count": gate["termination_or_cancellation_count"],
            "source_file": display_path(gate_path),
        },
        "state_legend": {
            "F": "officially confirmed fact",
            "E": "calculation from confirmed facts",
            "C": "context or management/industry statement; not issuer actual",
            "M": "methodological/counterfactual output",
            "U": "unverified; never replaced with zero",
        },
        "visualizations": visualizations,
        "sources": {
            "R01": "2026 Q1 report, rcept_no 20260515001551",
            "R02": "2025 annual report/audited CFS, rcept_no 20260316001681",
            "R03-R07": "2026 official contract disclosures and correction chain",
            "R09": "KRX-operated KIND market snapshot and calculated market capitalization",
            "R10": "OpenDART latest-disclosure list gate",
            "R11-R13": "official industry/customer/global tester context; not Exicon actual",
            "R14-R16": "official peer filings; structural comparison only",
            "R17": "2026 half-year report, rcept_no 20260814001521",
        },
        "input_lineage": [
            {"file": display_path(path), "sha256": sha256(path)} for path in input_paths
        ],
    }

    forbidden_tokens = ["crtfc_key", "DART_API_KEY"]
    serialized = json.dumps(chart_data, ensure_ascii=False)
    checks.extend(
        make_check(f"P5-SECURITY-{token}", "security", token in serialized, False) for token in forbidden_tokens
    )

    check_output = {
        "title": "Phase 5 chart-data checks",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "check_count": len(checks),
        "passed_count": sum(check["passed"] for check in checks),
        "failed_count": sum(not check["passed"] for check in checks),
        "checks": checks,
    }
    if check_output["failed_count"]:
        failed = [check["check_id"] for check in checks if not check["passed"]]
        raise RuntimeError(f"Phase 5 checks failed: {failed}")

    outputs = {
        "phase5_chart_data.json": chart_data,
        "phase5_checks.json": check_output,
    }
    for name, value in outputs.items():
        write_json(run_dir / name, value)

    manifest = {
        "phase": "Phase 5",
        "run_id": run_id,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "project_cutoff": gate["project_cutoff"],
        "api_calls": 0,
        "latest_gate_file": display_path(gate_path),
        "input_files": [
            {"file": display_path(path), "sha256": sha256(path)} for path in input_paths
        ],
        "output_files": [
            {"file": display_path(run_dir / name), "sha256": sha256(run_dir / name)}
            for name in outputs
        ],
        "checks": {
            "total": check_output["check_count"],
            "passed": check_output["passed_count"],
            "failed": check_output["failed_count"],
        },
        "api_key_logged": False,
        "xlsx_status": "blocked-no-load_workspace_dependencies-tool",
    }
    write_json(run_dir / "phase5_run_manifest.json", manifest)

    print(
        json.dumps(
            {
                "run_dir": display_path(run_dir),
                "input_run": display_path(phase4_run_dir),
                "gate": display_path(gate_path),
                "checks_passed": check_output["passed_count"],
                "checks_failed": check_output["failed_count"],
                "visualizations": len(visualizations),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
