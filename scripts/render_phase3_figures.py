from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "raw" / "dart" / "normalized" / "phase3" / "runs"
FIGURES = ROOT / "figures"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def latest_run() -> Path:
    candidates = sorted(path for path in RUNS.iterdir() if path.is_dir())
    if not candidates:
        raise FileNotFoundError("No Phase 3 normalized run found")
    return candidates[-1]


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Malgun Gothic",
            "axes.unicode_minus": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.18,
            "grid.linewidth": 0.7,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def render_historical(run_dir: Path) -> Path:
    historical = read_json(run_dir / "historical_independent_quarters_cfs.json")
    rows = historical["rows"]
    labels = [row["quarter"] for row in rows]
    revenue = [row["flow_values"]["revenue"] / 1e8 for row in rows]
    op_income = [row["flow_values"]["operating_income"] / 1e8 for row in rows]
    net_income = [row["flow_values"]["net_income"] / 1e8 for row in rows]
    ocf = [row["flow_values"]["operating_cash_flow"] / 1e8 for row in rows]
    inventory = [row["period_end_values"]["inventory"] / 1e8 for row in rows]
    receivables = [row["period_end_values"]["trade_and_other_current_receivables"] / 1e8 for row in rows]

    x = list(range(len(rows)))
    fig, axes = plt.subplots(2, 1, figsize=(13.2, 8.4), sharex=True, constrained_layout=True)
    fig.suptitle("엑시콘 연결 독립 분기 실적과 운전자본", fontsize=16, fontweight="bold")

    axes[0].bar(x, revenue, color="#2F6B9A", alpha=0.88, label="매출")
    axes[0].plot(x, op_income, color="#C44E52", marker="o", linewidth=2.0, label="영업이익")
    axes[0].plot(x, net_income, color="#7A5195", marker="s", linewidth=1.7, label="순이익")
    axes[0].axhline(0, color="#444444", linewidth=0.8)
    axes[0].set_ylabel("억원")
    axes[0].set_title("누계 공시 차감으로 재구성한 손익", loc="left", fontsize=12)
    axes[0].legend(frameon=False, ncol=3, loc="upper left")

    axes[1].bar(x, ocf, color="#E6A23C", alpha=0.78, label="영업활동현금흐름")
    axes[1].plot(x, inventory, color="#1B9E77", marker="o", linewidth=2.0, label="기말 재고")
    axes[1].plot(x, receivables, color="#4C78A8", marker="s", linewidth=1.8, label="기말 매출채권·기타유동채권")
    axes[1].axhline(0, color="#444444", linewidth=0.8)
    axes[1].set_ylabel("억원")
    axes[1].set_title("현금흐름과 기말 운전자본 잔액 — 인과관계가 아닌 동행 확인용", loc="left", fontsize=12)
    axes[1].legend(frameon=False, ncol=3, loc="upper left")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=45, ha="right")

    fig.text(
        0.01,
        0.005,
        f"출처: OpenDART 연결 CFS, Phase 3 run {run_dir.name}. Q2=H1-Q1, Q3=9M-H1, Q4=FY-9M. 단위: 억원.",
        fontsize=8.5,
        color="#555555",
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    output = FIGURES / "03_phase3_historical_operating_working_capital.png"
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output


def render_contract_timeline(run_dir: Path) -> Path:
    evidence = read_json(run_dir / "contract_timing_evidence.json")
    contracts = evidence["contracts"]
    contracts = sorted(contracts, key=lambda row: (row["start_date"], row["contract_amount_krw"]))

    fig, ax = plt.subplots(figsize=(13.2, 6.0))
    fig.subplots_adjust(top=0.78, bottom=0.19, left=0.27, right=0.98)
    fig.suptitle("엑시콘 공시 계약기간 — 매출 인식 배분은 모두 U", fontsize=16, fontweight="bold", y=0.98)
    colors = {True: "#2F6B9A", False: "#9AA0A6"}
    labels = []
    for index, contract in enumerate(contracts):
        start = datetime.fromisoformat(contract["start_date"])
        end = datetime.fromisoformat(contract["end_date"])
        width = (end - start).days + 1
        ax.barh(index, width, left=mdates.date2num(start), height=0.55, color=colors[contract["is_new_2026_contract"]], alpha=0.9)
        amount_eok = contract["contract_amount_krw"] / 1e8
        amount_label = f"{amount_eok:,.4f}".rstrip("0").rstrip(".")
        ax.text(
            mdates.date2num(start) + width / 2,
            index,
            f"{amount_label}억원 · U",
            ha="center",
            va="center",
            color="white",
            fontsize=9,
            fontweight="bold",
        )
        source = "+".join(contract["source_ids"])
        labels.append(f"{source}  {contract['product']}")

    for boundary in (date(2025, 10, 1), date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 10, 1), date(2027, 1, 1)):
        ax.axvline(mdates.date2num(boundary), color="#777777", linewidth=0.7, linestyle="--", alpha=0.55)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", rotation=45)
    ax.set_xlim(mdates.date2num(date(2025, 9, 1)), mdates.date2num(date(2027, 1, 15)))
    ax.set_title("막대는 공시상 계약 시작일~종료일만 표시하며, 종료일·지급조건을 인식일·인식률로 간주하지 않음", loc="left", fontsize=11, pad=12)
    ax.legend(
        handles=[Patch(facecolor="#2F6B9A", label="2026년 신규계약"), Patch(facecolor="#9AA0A6", label="2025년 원계약의 2026년 정정")],
        frameon=False,
        loc="upper right",
        bbox_to_anchor=(1.0, 1.27),
        ncol=2,
    )
    fig.text(
        0.01,
        0.005,
        f"출처: OpenDART 계약 공시, Phase 3 run {run_dir.name}. U=검수·고객 수락·수익 인식 증거 미확인; 금액은 매출 또는 수주잔고가 아님.",
        fontsize=8.5,
        color="#555555",
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    output = FIGURES / "03_phase3_contract_timeline_U.png"
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> int:
    setup_style()
    run_dir = latest_run()
    outputs = [render_historical(run_dir), render_contract_timeline(run_dir)]
    print(json.dumps({"run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"), "figures": [str(path.relative_to(ROOT)).replace("\\", "/") for path in outputs]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
