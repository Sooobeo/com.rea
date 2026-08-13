from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "raw" / "dart" / "normalized" / "phase4" / "runs"
FIGURES = ROOT / "figures"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def latest_run() -> Path:
    candidates = sorted(
        path for path in RUNS.iterdir() if path.is_dir() and (path / "conditional_forecast_and_scenarios.json").exists()
    )
    if not candidates:
        raise FileNotFoundError("No complete Phase 4 normalized run found")
    return candidates[-1]


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Malgun Gothic",
            "axes.unicode_minus": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def render_evidence_gate(run_dir: Path) -> Path:
    model = read_json(run_dir / "conditional_forecast_and_scenarios.json")
    contracts = model["contract_states"]
    columns = ["계약 체결", "최신 일정", "납품 표기", "고객 수락", "수익 인식"]
    rows = []
    for contract in contracts:
        source = "+".join(contract["source_ids"])
        rows.append(
            {
                "label": f"{source}  {contract['product']}",
                "cells": [
                    ("공식 확인", "known"),
                    ("종료일 정정", "warning") if contract["schedule_status"] == "revised-end-date" else ("최신 공시", "known"),
                    ("표기 있음\n(매출 아님)", "context")
                    if contract["delivery_context"]["status"] == "reported-in-order-table"
                    else ("미연결", "unknown"),
                    ("U", "unknown"),
                    ("U", "unknown"),
                ],
            }
        )

    colors = {"known": "#2F6B9A", "warning": "#E39D3E", "context": "#6BAED6", "unknown": "#D9DDE3"}
    text_colors = {"known": "white", "warning": "#2B2B2B", "context": "white", "unknown": "#444444"}
    fig, ax = plt.subplots(figsize=(14.2, 6.5))
    fig.subplots_adjust(left=0.31, right=0.98, top=0.80, bottom=0.17)
    ax.set_xlim(0, len(columns))
    ax.set_ylim(0, len(rows))
    ax.invert_yaxis()
    ax.set_xticks([index + 0.5 for index in range(len(columns))])
    ax.set_xticklabels(columns, fontsize=11, fontweight="bold")
    ax.xaxis.tick_top()
    ax.set_yticks([index + 0.5 for index in range(len(rows))])
    ax.set_yticklabels([row["label"] for row in rows], fontsize=10)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    for row_index, row in enumerate(rows):
        for column_index, (label, status) in enumerate(row["cells"]):
            rect = plt.Rectangle(
                (column_index + 0.05, row_index + 0.08),
                0.90,
                0.84,
                facecolor=colors[status],
                edgecolor="white",
                linewidth=1.5,
            )
            ax.add_patch(rect)
            ax.text(
                column_index + 0.5,
                row_index + 0.5,
                label,
                ha="center",
                va="center",
                fontsize=9.5,
                color=text_colors[status],
                fontweight="bold" if status in {"known", "warning"} else "normal",
            )

    fig.suptitle("엑시콘 계약 증거 게이트: 계약은 확인, 매출 전환은 U", fontsize=17, fontweight="bold", y=0.97)
    ax.set_title(
        "납품 표기나 계약 종료일은 검수·고객 수락·수익 인식의 대체 증거가 아니다",
        loc="left",
        fontsize=11.5,
        pad=40,
        color="#444444",
    )
    fig.legend(
        handles=[
            Patch(facecolor=colors["known"], label="공식 확인"),
            Patch(facecolor=colors["warning"], label="일정 정정 경고"),
            Patch(facecolor=colors["context"], label="맥락 증거(매출 아님)"),
            Patch(facecolor=colors["unknown"], label="U / 미확인"),
        ],
        frameon=False,
        ncol=4,
        loc="lower center",
        bbox_to_anchor=(0.58, 0.055),
    )
    fig.text(
        0.01,
        0.01,
        f"출처: R01~R07, 2025년 연결감사보고서 핵심감사사항. Phase 4 run {run_dir.name}. U=검수·수락·수익 인식 증거 미확인.",
        fontsize=8.5,
        color="#555555",
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    output = FIGURES / "04_phase4_contract_evidence_gate.png"
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output


def render_sensitivity(run_dir: Path) -> Path:
    model = read_json(run_dir / "conditional_forecast_and_scenarios.json")
    sensitivity = model["counterfactual_sensitivity"]
    cases = sensitivity["contract_value_cases"]
    anchors = sensitivity["margin_anchors"]
    rows_by_key = {
        (row["contract_case_id"], row["margin_anchor_id"]): row for row in sensitivity["rows"]
    }
    matrix = [
        [
            rows_by_key[(case["case_id"], anchor["anchor_id"])]["counterfactual_operating_result_krw"] / 1e8
            for anchor in anchors
        ]
        for case in cases
    ]
    flat = [value for row in matrix for value in row]
    norm = TwoSlopeNorm(vmin=min(flat), vcenter=0, vmax=max(flat))

    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    fig.subplots_adjust(left=0.30, right=0.94, top=0.78, bottom=0.22)
    image = ax.imshow(matrix, cmap="RdYlBu", norm=norm, aspect="auto")
    ax.set_xticks(range(len(anchors)))
    ax.set_xticklabels(
        [
            "2026Q1\n저매출·적자 관측",
            "2025FY\n연간 손익분기 관측",
            "2025Q4\n고납품·레버리지 관측",
        ],
        fontsize=10,
    )
    ax.set_yticks(range(len(cases)))
    ax.set_yticklabels([f"{case['case_id']}  {case['label']}" for case in cases], fontsize=10)
    ax.tick_params(length=0)
    for row_index, row in enumerate(matrix):
        for column_index, value in enumerate(row):
            ax.text(
                column_index,
                row_index,
                f"{value:,.1f}억원",
                ha="center",
                va="center",
                fontsize=10,
                fontweight="bold",
                color="white" if abs(value) > max(abs(min(flat)), abs(max(flat))) * 0.42 else "#222222",
            )

    colorbar = fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03)
    colorbar.set_label("기계적 영업손익 반응(억원)", fontsize=10)
    fig.suptitle("공식 계약가치 × 과거 관측 OPM 반사실 민감도", fontsize=17, fontweight="bold", y=0.97)
    ax.set_title(
        "전액 인식·동일 OPM이라는 극단 가정의 반응표이며, 매출 전망·제품 마진·확률이 아니다",
        loc="left",
        fontsize=11.5,
        pad=38,
        color="#444444",
    )
    fig.text(
        0.01,
        0.07,
        "읽는 법: 계약별 인식액과 기간은 모두 U다. 이 표는 공식 계약가치와 연결 CFS의 실제 OPM 관측점만 결합한 계산 민감도다.",
        fontsize=9,
        color="#444444",
    )
    fig.text(
        0.01,
        0.025,
        f"출처: R01~R07, OpenDART 연결 CFS. Phase 4 run {run_dir.name}. 산식: 공식 계약가치 × 관측 OPM.",
        fontsize=8.5,
        color="#555555",
    )
    output = FIGURES / "04_phase4_counterfactual_opm_sensitivity.png"
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output


def render_scenario_state(run_dir: Path) -> Path:
    model = read_json(run_dir / "conditional_forecast_and_scenarios.json")
    scenarios = model["scenarios"]
    status_styles = {
        "active": ("#2F6B9A", "현재 상태"),
        "not-entered": ("#D9DDE3", "증거 대기"),
        "partial-warning": ("#E39D3E", "부분 경고"),
    }
    fig, ax = plt.subplots(figsize=(12.8, 5.4))
    fig.subplots_adjust(left=0.25, right=0.96, top=0.76, bottom=0.22)
    y = list(range(len(scenarios)))
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, len(scenarios) - 0.5)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks(y)
    ax.set_yticklabels([scenario["label"] for scenario in scenarios], fontsize=11, fontweight="bold")
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    descriptions = [
        "계약은 유지되지만 검수·수익 인식은 미확인",
        "계약별 수락·인식 금액과 기간 확인 필요",
        "Base 증거 + 신규 양산·마진·OCF 개선 필요",
        "Board 일정 연장·재고/OCF 경고, 회사 전체 영향은 미확정",
    ]
    for index, scenario in enumerate(scenarios):
        color, status_label = status_styles[scenario["status"]]
        ax.barh(index, 0.22, left=0.02, height=0.56, color=color)
        ax.text(0.13, index, status_label, ha="center", va="center", color="white" if scenario["status"] != "not-entered" else "#333333", fontsize=9.5, fontweight="bold")
        ax.text(0.29, index, descriptions[index], ha="left", va="center", fontsize=10.2, color="#333333")

    fig.suptitle("Phase 4 사건 시나리오 상태", fontsize=17, fontweight="bold", y=0.96)
    ax.set_title("확률이나 임의 인식률 없이 공식 사건이 발생할 때만 상태가 전이된다", loc="left", fontsize=11.5, pad=32, color="#444444")
    fig.text(
        0.01,
        0.02,
        f"출처: R01~R07, OpenDART 연결 CFS. Phase 4 run {run_dir.name}. 시나리오별 숫자 출력은 현재 U.",
        fontsize=8.5,
        color="#555555",
    )
    output = FIGURES / "04_phase4_scenario_state.png"
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> int:
    setup_style()
    run_dir = latest_run()
    outputs = [render_evidence_gate(run_dir), render_scenario_state(run_dir), render_sensitivity(run_dir)]
    print(
        json.dumps(
            {
                "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
                "figures": [str(path.relative_to(ROOT)).replace("\\", "/") for path in outputs],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
