from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
DEFAULT_OUTPUT = ROOT / "YIG_엑시콘_최종산출물_매니페스트_2026-08-31.json"
EXTERNAL_VISUALIZATION = Path(
    r"C:\Users\kuri\OneDrive\com.rea-visualizations\exicon-evidence-state.html"
)


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


def resolve(path: Path) -> Path:
    candidate = path if path.is_absolute() else ROOT / path
    candidate = candidate.resolve()
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    return candidate


def project_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def file_entry(path: Path) -> dict[str, Any]:
    path = resolve(path)
    return {
        "file": project_path(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def assert_manifest_files(rows: list[dict[str, Any]], path_key: str) -> None:
    for row in rows:
        path = resolve(Path(row[path_key]))
        actual = sha256(path)
        expected = str(row["sha256"]).lower()
        if actual != expected:
            raise ValueError(f"Manifest hash mismatch for {path}: {actual} != {expected}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a tracked final artifact and evidence manifest.")
    parser.add_argument("--gate-summary", type=Path, required=True)
    parser.add_argument("--phase3-run-dir", type=Path, required=True)
    parser.add_argument("--phase4-run-dir", type=Path, required=True)
    parser.add_argument("--phase5-run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gate_path = resolve(args.gate_summary)
    phase3_dir = resolve(args.phase3_run_dir)
    phase4_dir = resolve(args.phase4_run_dir)
    phase5_dir = resolve(args.phase5_run_dir)

    phase2_manifest_path = resolve(Path("raw/dart/normalized/normalization_manifest.json"))
    phase2_checks_path = resolve(Path("raw/dart/normalized/checks.json"))
    phase3_manifest_path = resolve(phase3_dir / "phase3_run_manifest.json")
    phase4_manifest_path = resolve(phase4_dir / "phase4_run_manifest.json")
    phase5_manifest_path = resolve(phase5_dir / "phase5_run_manifest.json")
    render_manifest_path = resolve(phase5_dir / "phase5_render_manifest.json")
    manual_qa_path = resolve(phase5_dir / "phase5_manual_visual_qa.json")

    gate = read_json(gate_path)
    phase2_manifest = read_json(phase2_manifest_path)
    phase2_checks = read_json(phase2_checks_path)
    phase3_manifest = read_json(phase3_manifest_path)
    phase4_manifest = read_json(phase4_manifest_path)
    phase5_manifest = read_json(phase5_manifest_path)
    render_manifest = read_json(render_manifest_path)
    manual_qa = read_json(manual_qa_path)

    assert_manifest_files(phase2_manifest["outputs"], "file")
    assert_manifest_files(phase3_manifest["inputs"], "path")
    assert_manifest_files(phase3_manifest["outputs"], "path")
    assert_manifest_files(phase4_manifest["inputs"], "path")
    assert_manifest_files(phase4_manifest["outputs"], "path")
    assert_manifest_files(phase5_manifest["input_files"], "file")
    assert_manifest_files(phase5_manifest["output_files"], "file")
    assert_manifest_files(render_manifest["figures"], "file")

    required_deliverables = [
        Path("03_엑시콘_기업분석_보고서.md"),
        Path("output/pdf/03_엑시콘_기업분석_보고서.pdf"),
        Path("05_엑시콘_Phase5_시각화_검증.md"),
        Path("05_엑시콘_분석한계와_업데이트체크리스트.md"),
        Path("YIG_엑시콘_프로젝트_결과보고서_2026-08-31.md"),
        Path("YIG_엑시콘_기업분석_보고서_구현계획서.md"),
        Path("YIG_엑시콘_기업분석_작업로그.md"),
        Path("requirements-chartpack.txt"),
        Path("requirements-report.txt"),
    ]

    manifest = {
        "manifest_version": 1,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "project": {
            "issuer": "엑시콘",
            "stock_code": "092870",
            "corp_code": "00611736",
            "disclosure_cutoff": gate["project_cutoff"],
            "market_date": "2026-08-28",
            "financial_date": "2026-06-30",
        },
        "latest_disclosure_gate": {
            **file_entry(gate_path),
            "status": gate["status"],
            "row_count": gate["row_count"],
            "half_year_count": gate["half_year_count"],
            "new_relevant_count": gate["new_relevant_count"],
            "termination_or_cancellation_count": gate["termination_or_cancellation_count"],
            "half_year_rcept_no": gate["half_year_filings"][0]["rcept_no"],
            "api_key_logged": gate["api_key_logged"],
        },
        "pipeline_qa": {
            "phase2": {
                "manifest": file_entry(phase2_manifest_path),
                "checks": file_entry(phase2_checks_path),
                "total": phase2_checks["check_count"],
                "passed": phase2_checks["passed_count"],
                "failed": phase2_checks["failed_count"],
            },
            "phase3": {
                "manifest": file_entry(phase3_manifest_path),
                **phase3_manifest["checks"],
            },
            "phase4": {
                "manifest": file_entry(phase4_manifest_path),
                **phase4_manifest["checks"],
            },
            "phase5_data": {
                "manifest": file_entry(phase5_manifest_path),
                **phase5_manifest["checks"],
            },
            "phase5_render": {
                "manifest": file_entry(render_manifest_path),
                **render_manifest["automated_checks"],
                "figure_count": render_manifest["figure_count"],
            },
            "manual_visual_qa": {
                "record": file_entry(manual_qa_path),
                "status": manual_qa["status"],
                "figures_reviewed": len(manual_qa["figures_reviewed"]),
                "unresolved_visual_defects": len(manual_qa["unresolved_visual_defects"]),
            },
        },
        "evidence_state_corrections": {
            "2026Q2_income_statement": "F - R17 directly reported 3-month columns",
            "2026Q2_operating_cash_flow": "E - H1 cumulative minus Q1 cumulative",
            "2026H1_soc_share": "F - disclosed 0.0%",
            "2026H1_soc_amount": "E - source cell blank; zero inferred by total reconciliation",
            "contract_recognition": "U - contract-level acceptance and revenue attribution not disclosed",
        },
        "deliverables": [file_entry(path) for path in required_deliverables],
        "external_visualizations": [file_entry(EXTERNAL_VISUALIZATION)],
        "figures": render_manifest["figures"],
        "xlsx_deliverables": {
            "status": "blocked",
            "reason": "Required @oai/artifact-tool/load_workspace_dependencies runtime is not enabled; prohibited fallback spreadsheet libraries were not used.",
            "rechecked_on": "2026-08-31",
            "files_not_created": [
                "01_엑시콘_소스로그.xlsx",
                "02_엑시콘_분석모델.xlsx",
                "04_엑시콘_차트데이터.xlsx",
            ],
        },
        "security": {
            "api_keys_logged": False,
            "secret_values_in_manifest": False,
        },
    }

    output = args.output if args.output.is_absolute() else ROOT / args.output
    write_json(output, manifest)
    print(
        json.dumps(
            {
                "output": project_path(output),
                "deliverables": len(manifest["deliverables"]),
                "figures": len(manifest["figures"]),
                "phase_failures": sum(
                    int(manifest["pipeline_qa"][phase].get("failed", 0))
                    for phase in ("phase2", "phase3", "phase4", "phase5_data", "phase5_render")
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
