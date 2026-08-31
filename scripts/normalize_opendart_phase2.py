from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "dart"
OUT = RAW / "normalized"

PERIOD_ORDER = {"Q1": 1, "H1": 2, "Q3": 3, "FY": 4}
FINANCIAL_FILE_RE = re.compile(
    r"^(?P<year>\d{4})_(?P<period>Q1|H1|Q3|FY)_(?P<fs_div>CFS|OFS)\.json$"
)
SHARE_FILE_RE = re.compile(
    r"^(?P<dataset>[a-z_]+)_(?P<year>\d{4})_(?P<period>Q1|H1|Q3|FY)\.json$"
)

CONTRACT_SOURCE_IDS = {
    "20260304901110": "R03",
    "20260506900318": "R04",
    "20260604900245": "R05",
    "20260710900182": "R06",
    "20260727900650": "R07",
    "20260102900767": "P2025-CORR-01",
}

KEY_ACCOUNTS = {
    "assets": {
        "statements": ("BS",),
        "ids": ("ifrs-full_Assets",),
        "name_pattern": r"^자산총계$",
    },
    "liabilities": {
        "statements": ("BS",),
        "ids": ("ifrs-full_Liabilities",),
        "name_pattern": r"^부채총계$",
    },
    "equity": {
        "statements": ("BS",),
        "ids": ("ifrs-full_Equity",),
        "name_pattern": r"^자본총계$",
    },
    "cash": {
        "statements": ("BS",),
        "ids": ("ifrs-full_CashAndCashEquivalents",),
        "name_pattern": r"현금및현금성자산",
    },
    "inventory": {
        "statements": ("BS",),
        "ids": ("ifrs-full_Inventories",),
        "name_pattern": r"^재고자산$",
    },
    "trade_and_other_current_receivables": {
        "statements": ("BS",),
        "ids": ("ifrs-full_TradeAndOtherCurrentReceivables",),
        "name_pattern": r"매출채권.*기타유동채권",
    },
    "revenue": {
        "statements": ("CIS", "IS"),
        "ids": (
            "ifrs-full_Revenue",
            "ifrs-full_RevenueFromContractsWithCustomers",
            "dart_Revenue",
        ),
        "name_pattern": r"^(수익|매출액|수익\(매출액\))$",
    },
    "operating_income": {
        "statements": ("CIS", "IS"),
        "ids": ("dart_OperatingIncomeLoss",),
        "name_pattern": r"^영업이익(?:\(손실\))?$",
    },
    "net_income": {
        "statements": ("CIS", "IS"),
        "ids": ("ifrs-full_ProfitLoss",),
        "name_pattern": r"^당기순이익(?:\(손실\))?$",
    },
    "operating_cash_flow": {
        "statements": ("CF",),
        "ids": ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
        "name_pattern": r"영업활동.*현금흐름",
    },
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number_or_none(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "--", "N/A"}:
        return None
    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1]
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    result: int | float = float(text) if "." in text else int(text)
    return -result if negative_parentheses else result


def numeric_fields(row: dict[str, Any]) -> dict[str, int | float]:
    converted: dict[str, int | float] = {}
    for key, value in row.items():
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            continue
        number = number_or_none(value)
        if number is not None:
            converted[key] = number
    return converted


def statement_priority(statement: str, allowed: Iterable[str]) -> int:
    order = list(allowed)
    try:
        return order.index(statement)
    except ValueError:
        return len(order)


def select_account(
    rows: list[dict[str, Any]], key: str
) -> tuple[dict[str, Any] | None, str | None, int]:
    rule = KEY_ACCOUNTS[key]
    allowed = rule["statements"]
    by_id = [
        row
        for row in rows
        if row.get("sj_div") in allowed and row.get("account_id") in rule["ids"]
    ]
    candidates = by_id
    method = "account_id" if by_id else None
    if not candidates:
        pattern = re.compile(rule["name_pattern"])
        candidates = [
            row
            for row in rows
            if row.get("sj_div") in allowed
            and pattern.search(str(row.get("account_nm", "")))
        ]
        method = "account_nm_fallback" if candidates else None
    if not candidates:
        return None, method, 0

    primary = [
        row
        for row in candidates
        if str(row.get("account_detail", "")).strip() in {"", "-"}
    ]
    if primary:
        candidates = primary
    candidates.sort(
        key=lambda row: (
            statement_priority(str(row.get("sj_div", "")), allowed),
            number_or_none(row.get("ord")) or 999999,
            str(row.get("account_detail", "")),
        )
    )
    return candidates[0], method, len(candidates)


def current_or_cumulative_amount(
    row: dict[str, Any] | None, period: str, key: str
) -> int | float | None:
    if row is None:
        return None
    if key in {
        "assets",
        "liabilities",
        "equity",
        "cash",
        "inventory",
        "trade_and_other_current_receivables",
    }:
        return number_or_none(row.get("thstrm_amount"))
    if key == "operating_cash_flow":
        return number_or_none(row.get("thstrm_amount"))
    if period in {"H1", "Q3"}:
        added = number_or_none(row.get("thstrm_add_amount"))
        if added is not None:
            return added
    return number_or_none(row.get("thstrm_amount"))


def normalize_financials() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_rows: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    key_cfs: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    paths = sorted(
        (RAW / "financials").glob("*.json"),
        key=lambda path: (
            int(FINANCIAL_FILE_RE.match(path.name).group("year")),
            PERIOD_ORDER[FINANCIAL_FILE_RE.match(path.name).group("period")],
            FINANCIAL_FILE_RE.match(path.name).group("fs_div"),
        ),
    )
    for path in paths:
        match = FINANCIAL_FILE_RE.match(path.name)
        if not match:
            continue
        meta = match.groupdict()
        payload = read_json(path)
        rows = list(payload.get("list") or [])
        rcept_nos = sorted({str(row.get("rcept_no")) for row in rows if row.get("rcept_no")})
        statements = sorted({str(row.get("sj_div")) for row in rows if row.get("sj_div")})
        source_id = f"DART-FS-{meta['year']}-{meta['period']}-{meta['fs_div']}"
        payloads.append(
            {
                **meta,
                "source_id": source_id,
                "source_file": path.relative_to(ROOT).as_posix(),
                "status": payload.get("status"),
                "message": payload.get("message"),
                "row_count": len(rows),
                "rcept_nos": rcept_nos,
                "statements": statements,
                "official_url": (
                    f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_nos[0]}"
                    if len(rcept_nos) == 1
                    else None
                ),
            }
        )
        for row_index, row in enumerate(rows, start=1):
            normalized_rows.append(
                {
                    "source_id": source_id,
                    "source_file": path.relative_to(ROOT).as_posix(),
                    "year": meta["year"],
                    "period": meta["period"],
                    "fs_div": meta["fs_div"],
                    "row_index": row_index,
                    "raw": row,
                    "numeric": numeric_fields(row),
                }
            )

        presence_pass = (
            payload.get("status") == "000"
            and "BS" in statements
            and "CF" in statements
            and any(statement in statements for statement in ("IS", "CIS"))
            and "SCE" in statements
            and len(rcept_nos) == 1
        )
        checks.append(
            {
                "check_id": f"FS-PAYLOAD-{meta['year']}-{meta['period']}-{meta['fs_div']}",
                "category": "financial_payload",
                "passed": presence_pass,
                "details": {
                    "status": payload.get("status"),
                    "row_count": len(rows),
                    "rcept_nos": rcept_nos,
                    "statements": statements,
                },
            }
        )

        selected: dict[str, dict[str, Any] | None] = {}
        selected_meta: dict[str, Any] = {}
        for key in KEY_ACCOUNTS:
            row, method, candidate_count = select_account(rows, key)
            selected[key] = row
            selected_meta[key] = {
                "method": method,
                "candidate_count_after_primary_filter": candidate_count,
                "account_id": row.get("account_id") if row else None,
                "account_nm": row.get("account_nm") if row else None,
                "sj_div": row.get("sj_div") if row else None,
                "account_detail": row.get("account_detail") if row else None,
                "thstrm_amount_raw": row.get("thstrm_amount") if row else None,
                "thstrm_add_amount_raw": row.get("thstrm_add_amount") if row else None,
            }
        key_values = {
            key: current_or_cumulative_amount(row, meta["period"], key)
            for key, row in selected.items()
        }

        assets = key_values["assets"]
        liabilities = key_values["liabilities"]
        equity = key_values["equity"]
        equation_difference = (
            assets - liabilities - equity
            if all(value is not None for value in (assets, liabilities, equity))
            else None
        )
        checks.append(
            {
                "check_id": f"FS-BALANCE-{meta['year']}-{meta['period']}-{meta['fs_div']}",
                "category": "balance_sheet_equation",
                "passed": equation_difference == 0,
                "details": {
                    "assets": assets,
                    "liabilities": liabilities,
                    "equity": equity,
                    "assets_minus_liabilities_minus_equity": equation_difference,
                },
            }
        )

        cf_end_cash_candidates = [
            row
            for row in rows
            if row.get("sj_div") == "CF"
            and row.get("account_id") == "dart_CashAndCashEquivalentsAtEndOfPeriodCf"
        ]
        cf_end_cash_primary = [
            row
            for row in cf_end_cash_candidates
            if str(row.get("account_detail", "")).strip() in {"", "-"}
        ]
        if cf_end_cash_primary:
            cf_end_cash_candidates = cf_end_cash_primary
        cf_end_cash_row = (
            sorted(
                cf_end_cash_candidates,
                key=lambda row: number_or_none(row.get("ord")) or 999999,
            )[0]
            if cf_end_cash_candidates
            else None
        )
        cf_end_cash = (
            number_or_none(cf_end_cash_row.get("thstrm_amount"))
            if cf_end_cash_row
            else None
        )
        cash_difference = (
            key_values["cash"] - cf_end_cash
            if key_values["cash"] is not None and cf_end_cash is not None
            else None
        )
        checks.append(
            {
                "check_id": f"FS-CASH-RECON-{meta['year']}-{meta['period']}-{meta['fs_div']}",
                "category": "cash_bs_cf_reconciliation",
                "passed": cash_difference == 0,
                "details": {
                    "bs_cash": key_values["cash"],
                    "cf_end_cash": cf_end_cash,
                    "difference": cash_difference,
                    "cf_account_id": (
                        cf_end_cash_row.get("account_id") if cf_end_cash_row else None
                    ),
                    "cf_account_nm": (
                        cf_end_cash_row.get("account_nm") if cf_end_cash_row else None
                    ),
                },
            }
        )

        missing_keys = [key for key, value in key_values.items() if value is None]
        checks.append(
            {
                "check_id": f"FS-KEYS-{meta['year']}-{meta['period']}-{meta['fs_div']}",
                "category": "key_account_mapping",
                "passed": not missing_keys,
                "details": {"missing_keys": missing_keys, "mapping": selected_meta},
            }
        )

        if meta["fs_div"] == "CFS":
            key_cfs.append(
                {
                    "source_id": source_id,
                    "year": int(meta["year"]),
                    "period": meta["period"],
                    "rcept_no": rcept_nos[0] if len(rcept_nos) == 1 else None,
                    "classification": "F",
                    "basis": "CFS",
                    "unit": "KRW",
                    "values": key_values,
                    "mapping": selected_meta,
                    "value_semantics": {
                        "BS": "period-end point-in-time thstrm_amount",
                        "IS_CIS": "Q1/FY thstrm_amount; H1/Q3 thstrm_add_amount cumulative",
                        "CF": "cumulative thstrm_amount",
                    },
                }
            )

    return normalized_rows, payloads, key_cfs, checks


def normalize_share_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_rows: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    paths = sorted(
        (RAW / "share").glob("*.json"),
        key=lambda path: path.name,
    )
    for path in paths:
        match = SHARE_FILE_RE.match(path.name)
        if not match:
            continue
        meta = match.groupdict()
        payload = read_json(path)
        rows = list(payload.get("list") or [])
        rcept_nos = sorted({str(row.get("rcept_no")) for row in rows if row.get("rcept_no")})
        source_id = f"DART-{meta['dataset'].upper()}-{meta['year']}-{meta['period']}"
        payloads.append(
            {
                **meta,
                "source_id": source_id,
                "source_file": path.relative_to(ROOT).as_posix(),
                "status": payload.get("status"),
                "message": payload.get("message"),
                "row_count": len(rows),
                "rcept_nos": rcept_nos,
            }
        )
        for row_index, row in enumerate(rows, start=1):
            normalized_rows.append(
                {
                    "source_id": source_id,
                    "source_file": path.relative_to(ROOT).as_posix(),
                    "dataset": meta["dataset"],
                    "year": meta["year"],
                    "period": meta["period"],
                    "row_index": row_index,
                    "raw": row,
                    "numeric": numeric_fields(row),
                }
            )

        checks.append(
            {
                "check_id": f"SHARE-PAYLOAD-{meta['dataset']}-{meta['year']}-{meta['period']}",
                "category": "share_payload",
                "passed": payload.get("status") == "000" and len(rcept_nos) <= 1,
                "details": {
                    "status": payload.get("status"),
                    "row_count": len(rows),
                    "rcept_nos": rcept_nos,
                },
            }
        )

        if meta["dataset"] == "stock_total":
            total_rows = [row for row in rows if row.get("se") == "합계"]
            total = total_rows[0] if len(total_rows) == 1 else None
            now_issued = number_or_none(total.get("now_to_isu_stock_totqy")) if total else None
            decreased = number_or_none(total.get("now_to_dcrs_stock_totqy")) if total else None
            issued = number_or_none(total.get("istc_totqy")) if total else None
            treasury = number_or_none(total.get("tesstk_co")) if total else None
            distributed = number_or_none(total.get("distb_stock_co")) if total else None
            issue_difference = (
                now_issued - decreased - issued
                if all(value is not None for value in (now_issued, decreased, issued))
                else None
            )
            distribution_difference = (
                issued - treasury - distributed
                if all(value is not None for value in (issued, treasury, distributed))
                else None
            )
            checks.append(
                {
                    "check_id": f"SHARE-STOCK-EQUATION-{meta['year']}-{meta['period']}",
                    "category": "stock_total_equation",
                    "passed": (
                        len(total_rows) == 1
                        and issue_difference == 0
                        and distribution_difference == 0
                    ),
                    "details": {
                        "total_row_count": len(total_rows),
                        "now_to_isu_stock_totqy": now_issued,
                        "now_to_dcrs_stock_totqy": decreased,
                        "istc_totqy": issued,
                        "tesstk_co": treasury,
                        "distb_stock_co": distributed,
                        "issue_difference": issue_difference,
                        "distribution_difference": distribution_difference,
                    },
                }
            )

    return normalized_rows, payloads, checks


def table_rows(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8")
    document = etree.HTML(text)
    rows: list[list[str]] = []
    for tr in document.xpath("//tr"):
        cells = []
        for cell in tr.xpath("./th|./td"):
            value = " ".join(" ".join(cell.itertext()).split())
            cells.append(value)
        if cells:
            rows.append(cells)
    return rows


def find_row(rows: list[list[str]], label: str) -> list[str] | None:
    for row in rows:
        if any(label in cell for cell in row):
            return row
    return None


def row_last(rows: list[list[str]], label: str) -> str | None:
    row = find_row(rows, label)
    return row[-1] if row and len(row) >= 2 else None


def normalized_product(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "").casefold())


def normalize_contracts(disclosures_2026: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    disclosure_by_rcept = {
        str(row.get("rcept_no")): row for row in disclosures_2026 if row.get("rcept_no")
    }
    contract_disclosures = [
        row
        for row in disclosures_2026
        if "단일판매" in str(row.get("report_nm", ""))
        or "공급계약" in str(row.get("report_nm", ""))
    ]
    records: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    for disclosure in sorted(contract_disclosures, key=lambda row: str(row.get("rcept_no"))):
        rcept_no = str(disclosure["rcept_no"])
        source_dir = RAW / "documents" / "extracted" / rcept_no
        files = sorted(source_dir.glob("*"))
        rows = table_rows(files[0]) if files else []
        correction_row = next(
            (row for row in rows if row and "계약기간 종료일" in row[0] and len(row) >= 3),
            None,
        )
        amount_raw = row_last(rows, "계약금액 총액")
        report_name = str(disclosure.get("report_nm", ""))
        is_correction = "정정" in report_name or correction_row is not None
        record = {
            "source_id": CONTRACT_SOURCE_IDS.get(rcept_no, f"DART-CONTRACT-{rcept_no}"),
            "rcept_no": rcept_no,
            "rcept_dt": disclosure.get("rcept_dt"),
            "report_nm": report_name,
            "is_correction": is_correction,
            "product": row_last(rows, "판매ㆍ공급계약 내용"),
            "contract_amount_krw_raw": amount_raw,
            "contract_amount_krw": number_or_none(amount_raw),
            "counterparty": row_last(rows, "계약상대방"),
            "start_date": row_last(rows, "시작일"),
            "end_date": row_last(rows, "종료일"),
            "payment_terms": row_last(rows, "대금지급 조건"),
            "contract_date": row_last(rows, "계약(수주)일자"),
            "correction_end_date_before": correction_row[1] if correction_row else None,
            "correction_end_date_after": correction_row[2] if correction_row else None,
            "source_file": files[0].relative_to(ROOT).as_posix() if files else None,
            "official_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
            "classification": "F",
            "raw_table_rows": rows,
        }
        records.append(record)
        required = (
            record["product"],
            record["contract_amount_krw"],
            record["counterparty"],
            record["start_date"],
            record["end_date"],
            record["contract_date"],
        )
        checks.append(
            {
                "check_id": f"CONTRACT-PARSE-{rcept_no}",
                "category": "contract_parse",
                "passed": bool(files) and all(value is not None for value in required),
                "details": {
                    "source_file_count": len(files),
                    "required_values": list(required),
                },
            }
        )

    groups: dict[tuple[str, int | float | None, str | None], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            normalized_product(record["product"]),
            record["contract_amount_krw"],
            record["contract_date"],
        )
        groups.setdefault(key, []).append(record)

    latest_contracts: list[dict[str, Any]] = []
    for group_records in groups.values():
        ordered = sorted(group_records, key=lambda row: str(row["rcept_no"]))
        latest = ordered[-1]
        latest_contracts.append(
            {
                "original_rcept_no": ordered[0]["rcept_no"],
                "latest_rcept_no": latest["rcept_no"],
                "correction_rcept_nos": [
                    row["rcept_no"] for row in ordered[1:] if row["is_correction"]
                ],
                "source_ids": [row["source_id"] for row in ordered],
                "product": latest["product"],
                "contract_amount_krw": latest["contract_amount_krw"],
                "counterparty": latest["counterparty"],
                "start_date": latest["start_date"],
                "end_date": latest["end_date"],
                "payment_terms": latest["payment_terms"],
                "contract_date": latest["contract_date"],
                "is_new_2026_contract": str(latest["contract_date"]).startswith("2026-"),
                "latest_official_url": latest["official_url"],
            }
        )

    latest_contracts.sort(key=lambda row: (str(row["contract_date"]), str(row["latest_rcept_no"])))
    new_2026 = [row for row in latest_contracts if row["is_new_2026_contract"]]
    new_2026_total = sum(
        int(row["contract_amount_krw"] or 0) for row in new_2026
    )
    cancellation_rows = [
        row
        for row in disclosures_2026
        if any(word in str(row.get("report_nm", "")) for word in ("해지", "취소"))
    ]

    checks.extend(
        [
            {
                "check_id": "CONTRACT-2026-UNIQUE-COUNT",
                "category": "contract_ledger",
                "passed": len(new_2026) == 4,
                "details": {"expected": 4, "actual": len(new_2026)},
            },
            {
                "check_id": "CONTRACT-2026-NEW-TOTAL",
                "category": "contract_ledger",
                "passed": new_2026_total == 101_801_700_000,
                "details": {
                    "expected_krw": 101_801_700_000,
                    "actual_krw": new_2026_total,
                },
            },
            {
                "check_id": "CONTRACT-2026-CANCELLATIONS",
                "category": "contract_ledger",
                "passed": len(cancellation_rows) == 0,
                "details": {"count": len(cancellation_rows), "rows": cancellation_rows},
            },
        ]
    )

    return (
        {
            "raw_contract_disclosure_count": len(records),
            "unique_contract_count": len(latest_contracts),
            "new_2026_contract_count": len(new_2026),
            "new_2026_contract_total_krw": new_2026_total,
            "new_2026_contract_total_eok_krw": new_2026_total / 100_000_000,
            "cancellation_count": len(cancellation_rows),
            "records": records,
            "latest_contracts": latest_contracts,
        },
        checks,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_manifest = read_json(RAW / "run_manifest.json")
    manifest_by_dataset = {
        str(row.get("dataset")): row for row in raw_manifest.get("datasets", [])
    }
    disclosures_all_path = ROOT / manifest_by_dataset["disclosures_all"]["output_file"]
    disclosures_2026_path = ROOT / manifest_by_dataset["disclosures_2026"]["output_file"]
    disclosures_all_payload = read_json(disclosures_all_path)
    disclosures_2026_payload = read_json(disclosures_2026_path)
    disclosures_all = list(disclosures_all_payload.get("list") or [])
    disclosures_2026 = list(disclosures_2026_payload.get("list") or [])

    financial_rows, financial_payloads, key_cfs, financial_checks = normalize_financials()
    share_rows, share_payloads, share_checks = normalize_share_data()
    contracts, contract_checks = normalize_contracts(disclosures_2026)

    periodic_2026 = [
        row
        for row in disclosures_2026
        if any(word in str(row.get("report_nm", "")) for word in ("사업보고서", "반기보고서", "분기보고서"))
    ]
    half_year_2026 = [
        row for row in periodic_2026 if "반기보고서" in str(row.get("report_nm", ""))
    ]
    manifest_statuses = [row.get("status") for row in raw_manifest.get("datasets", [])]
    expected_document_receipts = {
        str(row.get("rcept_no"))
        for row in disclosures_2026
        if row.get("rcept_no")
    }
    expected_document_receipts.update(
        str(rcept_no)
        for payload in financial_payloads
        for rcept_no in payload.get("rcept_nos", [])
    )
    actual_document_receipts = {
        str(row.get("dataset", "")).removeprefix("document_")
        for row in raw_manifest.get("datasets", [])
        if str(row.get("dataset", "")).startswith("document_")
    }
    expected_dataset_count = (
        3
        + len(financial_payloads)
        + len(share_payloads)
        + len(expected_document_receipts)
    )
    general_checks = [
        {
            "check_id": "RAW-MANIFEST-STATUS",
            "category": "raw_collection",
            "passed": (
                len(manifest_statuses) == expected_dataset_count
                and set(manifest_statuses) == {"000"}
                and actual_document_receipts == expected_document_receipts
            ),
            "details": {
                "dataset_count": len(manifest_statuses),
                "expected_dataset_count": expected_dataset_count,
                "document_count": len(actual_document_receipts),
                "expected_document_count": len(expected_document_receipts),
                "missing_document_receipts": sorted(
                    expected_document_receipts - actual_document_receipts
                ),
                "unexpected_document_receipts": sorted(
                    actual_document_receipts - expected_document_receipts
                ),
                "status_counts": {
                    str(status): manifest_statuses.count(status)
                    for status in sorted(set(manifest_statuses), key=str)
                },
            },
        },
        {
            "check_id": "DISCLOSURE-COUNTS",
            "category": "disclosures",
            "passed": (
                len(disclosures_all) == int(disclosures_all_payload["total_count"])
                and len(disclosures_2026) == int(disclosures_2026_payload["total_count"])
            ),
            "details": {
                "2023_to_cutoff_expected": int(disclosures_all_payload["total_count"]),
                "2023_to_cutoff_actual": len(disclosures_all),
                "2026_expected": int(disclosures_2026_payload["total_count"]),
                "2026_actual": len(disclosures_2026),
            },
        },
        {
            "check_id": "DISCLOSURE-2026-HALF-YEAR",
            "category": "disclosures",
            "passed": len(half_year_2026) == 1,
            "details": {
                "cutoff": raw_manifest["run"]["cutoff_date"],
                "expected_half_year_report_count": 1,
                "half_year_report_count": len(half_year_2026),
                "latest_periodic_reports": periodic_2026,
            },
        },
    ]
    all_checks = general_checks + financial_checks + share_checks + contract_checks

    disclosures_output = {
        "retrieved_at": raw_manifest["run"]["retrieved_at"],
        "cutoff_date": raw_manifest["run"]["cutoff_date"],
        "corp_code": raw_manifest["run"]["corp_code"],
        "all_disclosures_count": len(disclosures_all),
        "disclosures_2026_count": len(disclosures_2026),
        "periodic_2026": periodic_2026,
        "half_year_report_2026_count": len(half_year_2026),
        "disclosures_2026": disclosures_2026,
    }

    outputs = {
        "disclosures_summary.json": disclosures_output,
        "financial_rows.json": financial_rows,
        "financial_payloads.json": financial_payloads,
        "key_financials_cfs.json": key_cfs,
        "share_rows.json": share_rows,
        "share_payloads.json": share_payloads,
        "contracts.json": contracts,
        "checks.json": {
            "check_count": len(all_checks),
            "passed_count": sum(1 for check in all_checks if check["passed"]),
            "failed_count": sum(1 for check in all_checks if not check["passed"]),
            "checks": all_checks,
        },
    }
    for name, value in outputs.items():
        write_json(OUT / name, value)

    output_manifest = {
        "normalized_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "raw_retrieved_at": raw_manifest["run"]["retrieved_at"],
        "cutoff_date": raw_manifest["run"]["cutoff_date"],
        "corp_code": raw_manifest["run"]["corp_code"],
        "normalizer": "scripts/normalize_opendart_phase2.py",
        "api_key_logged": False,
        "outputs": [
            {
                "file": (OUT / name).relative_to(ROOT).as_posix(),
                "sha256": sha256(OUT / name),
                "bytes": (OUT / name).stat().st_size,
            }
            for name in outputs
        ],
    }
    write_json(OUT / "normalization_manifest.json", output_manifest)

    summary = {
        "raw_datasets": len(raw_manifest.get("datasets", [])),
        "disclosures_all": len(disclosures_all),
        "disclosures_2026": len(disclosures_2026),
        "financial_payloads": len(financial_payloads),
        "financial_rows": len(financial_rows),
        "share_payloads": len(share_payloads),
        "share_rows": len(share_rows),
        "contract_disclosures": contracts["raw_contract_disclosure_count"],
        "new_2026_contracts": contracts["new_2026_contract_count"],
        "new_2026_contract_total_krw": contracts["new_2026_contract_total_krw"],
        "checks_passed": outputs["checks.json"]["passed_count"],
        "checks_failed": outputs["checks.json"]["failed_count"],
        "output_dir": OUT.relative_to(ROOT).as_posix(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["checks_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
