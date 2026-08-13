from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = ROOT / "raw" / "market" / "phase4" / "runs"
KST = timezone(timedelta(hours=9))


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_text(opener: urllib.request.OpenerDirector, request: urllib.request.Request) -> tuple[int, str]:
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def parse_naver_daily_close(payload: str, trade_date: str) -> int | None:
    compact_date = trade_date.replace("-", "")
    for line in payload.splitlines():
        if compact_date not in line:
            continue
        values = re.findall(r"-?\d+(?:\.\d+)?", line)
        if len(values) >= 5 and values[0] == compact_date:
            return int(float(values[4]))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the Phase 4 cutoff-date market snapshot without secrets.")
    parser.add_argument("--trade-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--kind-close", required=True, type=int)
    parser.add_argument("--kind-listed-shares", required=True, type=int)
    parser.add_argument("--kind-observed-at", required=True, help="ISO 8601 timestamp with KST offset")
    args = parser.parse_args()

    generated_at = datetime.now(KST)
    run_id = generated_at.strftime("%Y%m%dT%H%M%S%z")
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    user_agent = "Mozilla/5.0 (compatible; evidence-capture/1.0)"

    krx_landing_url = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"
    krx_data_url = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    krx_landing_status, krx_landing_body = fetch_text(
        opener,
        urllib.request.Request(krx_landing_url, headers={"User-Agent": user_agent}),
    )
    krx_form = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01701",
        "locale": "ko_KR",
        "isuCd": "KR7092870009",
        "isuCd2": "092870",
        "strtDd": args.trade_date.replace("-", ""),
        "endDd": args.trade_date.replace("-", ""),
        "share": "1",
        "money": "1",
    }
    krx_request = urllib.request.Request(
        krx_data_url,
        data=urllib.parse.urlencode(krx_form).encode("ascii"),
        headers={
            "User-Agent": user_agent,
            "Referer": krx_landing_url,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        method="POST",
    )
    krx_data_status, krx_data_body = fetch_text(opener, krx_request)

    compact_date = args.trade_date.replace("-", "")
    naver_url = (
        "https://api.finance.naver.com/siseJson.naver?"
        + urllib.parse.urlencode(
            {
                "symbol": "092870",
                "requestType": "1",
                "startTime": compact_date,
                "endTime": compact_date,
                "timeframe": "day",
            }
        )
    )
    naver_status, naver_body = fetch_text(
        urllib.request.build_opener(),
        urllib.request.Request(naver_url, headers={"User-Agent": user_agent}),
    )
    naver_close = parse_naver_daily_close(naver_body, args.trade_date)

    write_text(run_dir / "krx_landing.html", krx_landing_body)
    write_text(run_dir / "krx_data_attempt.txt", krx_data_body)
    write_text(run_dir / "naver_daily_response.txt", naver_body)

    market_cap = args.kind_close * args.kind_listed_shares
    snapshot = {
        "title": "Exicon cutoff-date market snapshot",
        "generated_at": generated_at.isoformat(),
        "security": {"name": "엑시콘", "ticker": "092870", "isin": "KR7092870009", "market": "KOSDAQ"},
        "trade_date": args.trade_date,
        "official_observation": {
            "operator": "Korea Exchange (KRX)",
            "surface": "KIND listed-company total information",
            "url": "https://kind.krx.co.kr/corpdetail/totalinfo.do?method=loadInitPage",
            "lookup_condition": "ticker=092870; 종합정보→주요시세 and 주식현황→상장주식현황; observed after market close",
            "observed_at": args.kind_observed_at,
            "close_krw": args.kind_close,
            "listed_shares": args.kind_listed_shares,
            "calculated_market_cap_krw": market_cap,
            "market_cap_formula": "close_krw * listed_shares",
            "classification": "F for observed price and shares; E for calculated market capitalization",
            "capture_method": "interactive read-only browser observation; value recorded by this script",
        },
        "krx_data_marketplace_attempt": {
            "landing_url": krx_landing_url,
            "landing_http_status": krx_landing_status,
            "data_url": krx_data_url,
            "data_http_status": krx_data_status,
            "request_parameters_without_credentials": krx_form,
            "response_file": "krx_data_attempt.txt",
            "usable_for_security_row": False,
            "reason": "The public statistical endpoint did not return an authenticated Exicon row in this session.",
        },
        "secondary_corroboration": {
            "provider": "Naver Finance",
            "url": naver_url,
            "lookup_condition": f"symbol=092870; daily; {args.trade_date} only",
            "http_status": naver_status,
            "close_krw": naver_close,
            "classification": "B/F secondary market-data corroboration",
            "response_file": "naver_daily_response.txt",
        },
        "checks": {
            "official_close_equals_secondary_close": naver_close == args.kind_close,
            "market_cap_positive": market_cap > 0,
        },
        "api_key_logged": False,
    }
    write_json(run_dir / "market_snapshot.json", snapshot)

    output_paths = [
        run_dir / "krx_landing.html",
        run_dir / "krx_data_attempt.txt",
        run_dir / "naver_daily_response.txt",
        run_dir / "market_snapshot.json",
    ]
    manifest = {
        "phase": "Phase 4 market snapshot",
        "run_id": run_id,
        "generated_at": generated_at.isoformat(),
        "outputs": [
            {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path)}
            for path in output_paths
        ],
        "api_key_logged": False,
    }
    write_json(run_dir / "market_snapshot_manifest.json", manifest)

    print(
        json.dumps(
            {
                "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
                "official_close": args.kind_close,
                "secondary_close": naver_close,
                "corroboration_passed": naver_close == args.kind_close,
                "krx_data_http_status": krx_data_status,
            },
            ensure_ascii=False,
        )
    )
    return 0 if naver_close == args.kind_close else 1


if __name__ == "__main__":
    raise SystemExit(main())
