from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle
from matplotlib.text import Text
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "raw" / "dart" / "normalized" / "phase5" / "runs"
FIGURES = ROOT / "figures"

NAVY = "#17365D"
BLUE = "#2F6F9F"
BLUE_LIGHT = "#DCEAF5"
TEAL = "#15806F"
TEAL_LIGHT = "#DDF1EC"
AMBER = "#E49A2F"
AMBER_LIGHT = "#FBE8C6"
RED = "#B85450"
PURPLE = "#745191"
GRAY = "#6B7280"
GRAY_LIGHT = "#E5E7EB"
GRAY_PALE = "#F5F6F8"
DARK = "#20242A"
WHITE = "#FFFFFF"
GRID = "#D9DEE6"
FIGURE_DPI = 180
FOOTER_X = 0.025
FOOTER_Y = 0.020
RUN_ID_FORMAT = "%Y%m%dT%H%M%S%z"
A4_CONTENT_WIDTH_MM = 178.0
A4_CORE_FONT_MIN_PT = 7.8
A4_SOURCE_FONT_MIN_PT = 6.7
FONT_SCALE = 1.55
LAYOUT_AUDIT: dict[str, dict] = {}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes())
    return digest.hexdigest()


def parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp for {label}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp for {label} must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def run_timestamp(run_dir: Path) -> datetime:
    chart_path = run_dir / "phase5_chart_data.json"
    if chart_path.is_file():
        generated_at = read_json(chart_path).get("generated_at")
        if generated_at:
            return parse_timestamp(generated_at, str(chart_path))
    try:
        return datetime.strptime(run_dir.name, RUN_ID_FORMAT).astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Run directory has no parseable timestamp: {run_dir}") from exc


def latest_run() -> Path:
    candidates = [path.parent for path in RUNS.glob("*/phase5_chart_data.json") if path.is_file()]
    if not candidates:
        raise FileNotFoundError("No Phase 5 chart-data run")
    return max(candidates, key=run_timestamp)


def resolve_path(value: str, *, base: Path = ROOT) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_input_run(value: str | None) -> Path:
    if value is None:
        return latest_run()
    direct = resolve_path(value)
    run_dir = direct if direct.is_dir() else (RUNS / value).resolve()
    if not (run_dir / "phase5_chart_data.json").is_file():
        raise FileNotFoundError(f"Phase 5 input run is missing phase5_chart_data.json: {run_dir}")
    return run_dir


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def compact_source_ids(source_ids: list[str]) -> str:
    numeric_ids = sorted({int(value[1:]) for value in source_ids if re.fullmatch(r"R\d+", value)})
    other_ids = [value for value in source_ids if not re.fullmatch(r"R\d+", value)]
    groups: list[str] = []
    if numeric_ids:
        start = previous = numeric_ids[0]
        for value in numeric_ids[1:] + [None]:
            if value is not None and value == previous + 1:
                previous = value
                continue
            groups.append(f"R{start:02d}" if start == previous else f"R{start:02d}–R{previous:02d}")
            if value is not None:
                start = previous = value
    groups.extend(other_ids)
    return "·".join(groups)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a verified Phase 5 chart-data run.")
    parser.add_argument(
        "--input-run",
        help="Phase 5 run directory or run id. Defaults to the newest run by parsed chart-data timestamp.",
    )
    parser.add_argument("--output-dir", help="Explicit figure directory; its render manifest is written there too.")
    parser.add_argument("--max-input-age-hours", type=float, default=24.0, help="Maximum disclosure-gate age (default: 24).")
    parser.add_argument("--allow-stale-inputs", action="store_true", help="Allow old but lineage-consistent input for historical reproduction.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of files in an explicit output directory.")
    return parser.parse_args()


def validate_input_freshness(
    run_dir: Path,
    data: dict,
    *,
    max_input_age_hours: float,
    allow_stale_inputs: bool,
) -> None:
    if max_input_age_hours <= 0:
        raise ValueError("--max-input-age-hours must be positive")
    generated_at = parse_timestamp(data["generated_at"], "phase5_chart_data.generated_at")
    cutoff = parse_timestamp(data["project_cutoff"], "phase5_chart_data.project_cutoff")
    gate_info = data["latest_disclosure_gate"]
    retrieved_at = parse_timestamp(gate_info["retrieved_at"], "latest_disclosure_gate.retrieved_at")
    if cutoff > retrieved_at:
        raise ValueError("Chart-data cutoff is later than the disclosure-gate retrieval")
    if generated_at < retrieved_at:
        raise ValueError("Chart data predates its disclosure gate")
    now = datetime.now().astimezone(timezone.utc)
    if generated_at > now + timedelta(minutes=5):
        raise ValueError("Chart data is implausibly newer than the render clock")
    input_age = now - retrieved_at
    if input_age > timedelta(hours=max_input_age_hours) and not allow_stale_inputs:
        raise ValueError(
            f"Phase 5 disclosure gate is stale ({input_age.total_seconds() / 3600:.1f}h old); "
            "refresh inputs or pass --allow-stale-inputs for historical reproduction"
        )

    gate_path = resolve_path(gate_info["source_file"])
    if not gate_path.is_file():
        raise FileNotFoundError(f"Chart-data disclosure gate is missing: {gate_path}")
    gate = read_json(gate_path)
    if gate.get("retrieved_at") != gate_info.get("retrieved_at") or gate.get("project_cutoff") != data.get("project_cutoff"):
        raise ValueError("Chart data and disclosure gate timestamps do not match")
    lineage = {row["file"]: row.get("sha256") for row in data.get("input_lineage", [])}
    lineage_hash = lineage.get(gate_info["source_file"])
    if not lineage_hash or sha256(gate_path) != lineage_hash:
        raise ValueError("Chart-data disclosure gate is absent from lineage or has a hash mismatch")

    run_manifest_path = run_dir / "phase5_run_manifest.json"
    if run_manifest_path.is_file():
        run_manifest = read_json(run_manifest_path)
        if run_manifest.get("run_id") != run_dir.name:
            raise ValueError("Phase 5 manifest run_id does not match its directory")
        if run_manifest.get("project_cutoff") != data.get("project_cutoff"):
            raise ValueError("Phase 5 manifest and chart-data cutoff do not match")
        chart_record = next(
            (row for row in run_manifest.get("output_files", []) if row.get("file", "").endswith("/phase5_chart_data.json")),
            None,
        )
        if chart_record and chart_record.get("sha256") != sha256(run_dir / "phase5_chart_data.json"):
            raise ValueError("Phase 5 chart-data hash does not match its run manifest")


def preserved_manual_qa(previous_manifest: dict | None, figures: list[dict]) -> dict | str:
    if not previous_manifest:
        return "pending"
    previous_qa = previous_manifest.get("manual_visual_qa", "pending")
    if not isinstance(previous_qa, dict) or previous_qa.get("status") != "passed":
        return "pending"
    previous_hashes = {Path(row["file"]).name: row.get("sha256") for row in previous_manifest.get("figures", [])}
    current_hashes = {Path(row["file"]).name: row.get("sha256") for row in figures}
    return previous_qa if previous_hashes == current_hashes else "pending"


def wrap_figure_text(value: str, width: int) -> str:
    lines: list[str] = []
    for line in value.splitlines() or [value]:
        lines.extend(textwrap.wrap(line, width=width, break_long_words=False, break_on_hyphens=False) or [line])
    return "\n".join(lines)


def prepare_for_a4(fig) -> None:
    # Materialize auto-generated tick/offset texts before applying the export scale.
    fig.canvas.draw()
    a4_scale = A4_CONTENT_WIDTH_MM / (fig.get_figwidth() * 25.4)
    required_core = A4_CORE_FONT_MIN_PT / a4_scale
    required_source = A4_SOURCE_FONT_MIN_PT / a4_scale
    max_figure_chars = max(48, int(fig.get_figwidth() * 4.5))
    for text in fig.findobj(match=Text):
        if not text.get_visible() or not text.get_text().strip():
            continue
        is_source = text.get_gid() == "source-footer"
        required = required_source if is_source else required_core
        text.set_fontsize(max(text.get_fontsize() * FONT_SCALE, required))
        if text in fig.texts and not is_source and max(map(len, text.get_text().splitlines())) > max_figure_chars:
            text.set_text(wrap_figure_text(text.get_text(), max_figure_chars))


def figure_layout_audit(fig) -> dict:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    figure_bbox = fig.bbox
    visible_texts = [
        text
        for text in fig.findobj(match=Text)
        if text.get_visible() and text.get_text().strip()
    ]
    core_sizes = []
    source_sizes = []
    clipped = []
    owner_by_id = {
        id(text): axis
        for axis in fig.axes
        for text in axis.findobj(match=Text)
    }
    text_boxes: list[tuple[Text, object, object | None]] = []
    a4_scale = A4_CONTENT_WIDTH_MM / (fig.get_figwidth() * 25.4)
    for text in visible_texts:
        bbox = text.get_window_extent(renderer=renderer)
        effective_size = text.get_fontsize() * a4_scale
        if text.get_gid() == "source-footer":
            source_sizes.append(float(effective_size))
        else:
            core_sizes.append(float(effective_size))
        if bbox.x0 < figure_bbox.x0 - 2 or bbox.y0 < figure_bbox.y0 - 2 or bbox.x1 > figure_bbox.x1 + 2 or bbox.y1 > figure_bbox.y1 + 2:
            clipped.append(text.get_text().replace("\n", " / ")[:80])
        text_boxes.append((text, bbox, owner_by_id.get(id(text))))

    overlaps = []
    for index, (left_text, left_bbox, left_owner) in enumerate(text_boxes):
        for right_text, right_bbox, right_owner in text_boxes[index + 1 :]:
            if left_owner is not right_owner and left_owner is not None and right_owner is not None:
                continue
            intersection = left_bbox.intersection(left_bbox, right_bbox)
            if intersection is None:
                continue
            smaller_area = min(left_bbox.width * left_bbox.height, right_bbox.width * right_bbox.height)
            if smaller_area <= 0 or intersection.width * intersection.height / smaller_area < 0.30:
                continue
            overlaps.append(
                f"{left_text.get_text().replace(chr(10), ' / ')[:45]} <> "
                f"{right_text.get_text().replace(chr(10), ' / ')[:45]}"
            )
    return {
        "a4_scale": float(a4_scale),
        "min_core_font_pt_at_178mm": float(min(core_sizes)) if core_sizes else None,
        "min_source_font_pt_at_178mm": float(min(source_sizes)) if source_sizes else None,
        "clipped_text_count": len(clipped),
        "clipped_text": clipped,
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
    }


def setup_style() -> dict[str, str | None]:
    candidates = [
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/malgunbd.ttf"),
        Path("C:/Windows/Fonts/NotoSansKR-Regular.otf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    ]
    selected: Path | None = next((path for path in candidates if path.exists()), None)
    family = "DejaVu Sans"
    if selected:
        font_manager.fontManager.addfont(str(selected))
        family = font_manager.FontProperties(fname=str(selected)).get_name()
    plt.rcParams.update(
        {
            "font.family": family,
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": GRID,
            "axes.labelcolor": DARK,
            "xtick.color": DARK,
            "ytick.color": DARK,
            "text.color": DARK,
            "axes.titleweight": "bold",
            "savefig.facecolor": "white",
        }
    )
    return {"family": family, "path": str(selected) if selected else None}


def header(fig, title: str, subtitle: str) -> None:
    fig.suptitle(title, fontsize=20, fontweight="bold", x=0.5, y=0.985)
    fig.text(
        0.5,
        0.915,
        "\n".join(textwrap.wrap(subtitle, width=max(54, int(fig.get_figwidth() * 4.5)), break_long_words=False)),
        ha="center",
        va="top",
        fontsize=11.5,
        color=GRAY,
        linespacing=1.25,
    )


def footer(fig, source: str, cutoff: str, run_id: str, extra: str | None = None) -> None:
    cutoff_display = cutoff.replace("T", " ")
    max_chars = max(84, int(fig.get_figwidth() * 7.0))
    parts = [f"공시 컷오프 {cutoff_display} | {source} | Phase 5 run {run_id}"]
    if extra:
        parts.append(extra)
    lines: list[str] = []
    for part in parts:
        lines.extend(textwrap.wrap(part, width=max_chars, break_long_words=False, break_on_hyphens=False) or [part])
    footer_text = fig.text(
        FOOTER_X,
        FOOTER_Y,
        "\n".join(lines),
        ha="left",
        va="bottom",
        fontsize=8.2,
        color=GRAY,
        linespacing=1.25,
    )
    footer_text.set_gid("source-footer")


def add_box(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    *,
    facecolor: str = WHITE,
    edgecolor: str = GRID,
    textcolor: str = DARK,
    fontsize: float = 11,
    linewidth: float = 1.2,
    hatch: str | None = None,
    radius: float = 0.015,
    zorder: int = 2,
    fontweight: str = "normal",
) -> FancyBboxPatch:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.008,rounding_size={radius}",
        transform=ax.transAxes,
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=linewidth,
        hatch=hatch,
        zorder=zorder,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=fontsize,
        color=textcolor,
        fontweight=fontweight,
        zorder=zorder + 1,
    )
    return patch


def save_figure(fig, name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    output = FIGURES / name
    fig.patch.set_facecolor(WHITE)
    prepare_for_a4(fig)
    LAYOUT_AUDIT[name] = figure_layout_audit(fig)
    fig.savefig(output, dpi=FIGURE_DPI, bbox_inches=None, pad_inches=0.0, facecolor=WHITE)
    plt.close(fig)
    return output


def fmt_eok(value: int | float, decimals: int = 1) -> str:
    return f"{value / 1e8:,.{decimals}f}억원"


def render_v1(data: dict, meta: dict, run_id: str) -> Path:
    fig, ax = plt.subplots(figsize=(16, 7.1))
    header(fig, data["title"], data["message"])
    ax.set_axis_off()
    nodes = data["nodes"]
    left, right = 0.025, 0.975
    width = min(0.112, (right - left) / max(len(nodes) * 1.22, 1))
    gap = (right - left - width * len(nodes)) / max(len(nodes) - 1, 1)
    xs = [left + i * (width + gap) for i in range(len(nodes))]
    y, height = 0.42, 0.25
    state_style = {
        "F": (BLUE_LIGHT, BLUE, NAVY),
        "C": (GRAY_PALE, GRAY, GRAY),
        "U": (GRAY_LIGHT, GRAY, DARK),
        "F/U": (AMBER_LIGHT, AMBER, DARK),
    }
    compact_labels = {
        "industry_demand": "AI·HPC\n고성능 메모리\n테스트 수요",
        "customer_investment": "고객 테스트 투자\n· 설비 필요",
        "contract": "엑시콘\n장비 계약",
        "production_delivery": "제작·납품\n설치·테스트",
        "cash": "채권·현금\n회수",
    }
    for x, node in zip(xs, nodes):
        face, edge, textcolor = state_style[node["state"]]
        add_box(
            ax,
            x,
            y,
            width,
            height,
            compact_labels.get(node["id"], node["label"]),
            facecolor=face,
            edgecolor=edge,
            textcolor=textcolor,
            fontsize=11.5,
            linewidth=1.8,
            fontweight="bold",
        )
        ax.text(
            x + width / 2,
            y + height + 0.045,
            node["state"],
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=10,
            fontweight="bold",
            color=edge,
        )
        source_ids = compact_source_ids(node["source_ids"])
        ax.text(
            x + width / 2,
            y - 0.052,
            source_ids,
            ha="center",
            va="top",
            transform=ax.transAxes,
            fontsize=8.5,
            color=GRAY,
        )
    for i, edge in enumerate(data["edges"]):
        x1 = xs[i] + width
        x2 = xs[i + 1]
        linestyle = "--" if edge["style"] == "dashed" else "-"
        color = AMBER if edge["state"] in {"U-link", "U-contract"} else GRAY
        arrow = FancyArrowPatch(
            (x1 + 0.006, y + height / 2),
            (x2 - 0.006, y + height / 2),
            transform=ax.transAxes,
            arrowstyle="-|>",
            mutation_scale=15,
            linewidth=1.8,
            linestyle=linestyle,
            color=color,
            zorder=1,
        )
        ax.add_patch(arrow)
    state_handles = [
        Patch(facecolor=state_style["F"][0], edgecolor=state_style["F"][1], label="F  공식 확인 사실"),
        Patch(facecolor=state_style["C"][0], edgecolor=state_style["C"][1], label="C  맥락·진술"),
        Patch(facecolor=state_style["U"][0], edgecolor=state_style["U"][1], label="U  미확인(0 아님)"),
        Patch(facecolor=state_style["F/U"][0], edgecolor=state_style["F/U"][1], label="F/U  사실·미확인 혼재"),
        Line2D([0], [0], color=GRAY, linewidth=1.8, linestyle="-", label="실선  공식 공정·회계 게이트"),
        Line2D([0], [0], color=AMBER, linewidth=1.8, linestyle="--", label="점선  맥락·연결 미확인"),
    ]
    ax.legend(
        handles=state_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.985),
        ncol=3,
        frameon=False,
        fontsize=9.2,
        handlelength=2.0,
        columnspacing=1.8,
    )
    ax.text(
        0.238,
        0.79,
        "산업 맥락 C",
        transform=ax.transAxes,
        ha="center",
        fontsize=10.5,
        color=GRAY,
        fontweight="bold",
    )
    ax.text(
        0.64,
        0.79,
        "엑시콘 공식 사실과 회계 게이트",
        transform=ax.transAxes,
        ha="center",
        fontsize=10.5,
        color=NAVY,
        fontweight="bold",
    )
    add_box(
        ax,
        0.36,
        0.18,
        0.28,
        0.105,
        "금지되는 지름길  ×  AI·HPC 수요 → 엑시콘 매출",
        facecolor=AMBER_LIGHT,
        edgecolor=AMBER,
        fontsize=11,
        fontweight="bold",
    )
    ax.text(
        0.5,
        0.105,
        "계약 종료일·지급조건은 매출 인식일·인식률이 아니다.",
        ha="center",
        transform=ax.transAxes,
        fontsize=10.5,
        color=RED,
        fontweight="bold",
    )
    footer(fig, data["source_note"], meta["project_cutoff"], run_id)
    fig.subplots_adjust(top=0.87, bottom=0.14, left=0.025, right=0.98)
    return save_figure(fig, "05_v01_demand_to_revenue_evidence_path.png")


def render_v2(data: dict, meta: dict, run_id: str) -> Path:
    fig, ax = plt.subplots(figsize=(16, 7.4))
    header(fig, data["title"], data["message"])
    ax.set_axis_off()
    stages = data["stages"]
    left, right = 0.025, 0.975
    width = min(0.14, (right - left) / max(len(stages) * 1.15, 1))
    gap = (right - left - width * len(stages)) / max(len(stages) - 1, 1)
    xs = [left + i * (width + gap) for i in range(len(stages))]
    stage_y = 0.57
    for x, stage in zip(xs, stages):
        active = bool(stage["exicon"])
        display_label = stage["label"]
        if stage.get("id") == "package_test":
            display_label = "웨이퍼 테스트\n(패키징 전)\n패키지·최종 테스트\n(패키징 후)"
        add_box(
            ax,
            x,
            stage_y,
            width,
            0.23,
            display_label,
            facecolor=BLUE_LIGHT if active else GRAY_PALE,
            edgecolor=BLUE if active else GRID,
            textcolor=NAVY if active else GRAY,
            fontsize=10.5,
            fontweight="bold",
        )
        for j, product in enumerate(stage["exicon"]):
            add_box(
                ax,
                x + 0.008,
                0.40 - j * 0.115,
                width - 0.016,
                0.085,
                product,
                facecolor=WHITE,
                edgecolor=TEAL,
                textcolor=TEAL,
                fontsize=9.8,
                fontweight="bold",
            )
    ax.text(
        0.5,
        0.83,
        "비순차 기능 영역 지도 · 좌→우가 단일 공정 순서나 제품 흐름을 뜻하지 않음",
        ha="center",
        transform=ax.transAxes,
        fontsize=10.5,
        color=RED,
        fontweight="bold",
    )
    ax.text(
        0.5,
        0.515,
        "웨이퍼 테스트는 패키징 전, 패키지·최종 테스트는 패키징 후에 놓일 수 있다. 파랑=공시상 용도 확인 영역 · 청록=엑시콘 제품",
        ha="center",
        transform=ax.transAxes,
        fontsize=9.6,
        color=GRAY,
    )
    ax.text(
        0.5,
        0.15,
        "\n".join(data["notes"]),
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=9.5,
        color=GRAY,
        linespacing=1.5,
    )
    footer(fig, data["source_note"], meta["project_cutoff"], run_id)
    fig.subplots_adjust(top=0.87, bottom=0.15, left=0.02, right=0.98)
    return save_figure(fig, "05_v02_test_value_chain_position.png")


def render_v3(data: dict, meta: dict, run_id: str) -> Path:
    annual = [row for row in data["periods"] if row.get("period_type") == "annual"]
    interim = [row for row in data["periods"] if row.get("period_type") != "annual"]
    panels = [("연간 구성", annual), ("분기·반기 구성", interim)]
    panels = [(title, periods) for title, periods in panels if periods]
    if not panels:
        raise ValueError("V3 has no product-mix periods")
    fig, axes = plt.subplots(1, len(panels), figsize=(max(8.5, 7.6 * len(panels)), 7.8), sharex=True, squeeze=False)
    axes = axes.ravel()
    header(fig, data["title"], data["message"])
    preferred_order = ["Memory Tester", "SSD Tester", "SoC Tester"]
    observed_products = list(dict.fromkeys(item["product"] for period in data["periods"] for item in period["products"]))
    products = [name for name in preferred_order if name in observed_products]
    products.extend(name for name in observed_products if name not in products)
    fallback_colors = [BLUE, TEAL, PURPLE, AMBER, RED]
    product_colors = {name: fallback_colors[i % len(fallback_colors)] for i, name in enumerate(products)}
    for ax, (panel_title, periods) in zip(axes, panels):
        y = np.arange(len(periods))
        lefts = np.zeros(len(periods))
        small_labels: list[list[str]] = [[] for _ in periods]
        for product in products:
            shares = []
            amounts = []
            for period in periods:
                item = next((row for row in period["products"] if row["product"] == product), None)
                amount = item["amount_krw"] if item else 0
                share = item["share"] * 100 if item else 0.0
                if amount and share <= 0 and period.get("total_krw"):
                    share = amount / period["total_krw"] * 100
                shares.append(share)
                amounts.append(amount)
            bars = ax.barh(y, shares, left=lefts, color=product_colors[product], height=0.52, label=product)
            for row_index, (bar, share, amount, left) in enumerate(zip(bars, shares, amounts, lefts)):
                if share >= 7:
                    ax.text(
                        left + share / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{share:.1f}%\n{amount / 1e8:.1f}억",
                        ha="center",
                        va="center",
                        fontsize=9,
                        color=WHITE,
                        fontweight="bold",
                    )
                else:
                    if amount == 0:
                        share_text = "0.0%"
                        amount_text = "0.0억"
                    else:
                        share_text = "<0.1%" if share < 0.1 else f"{share:.1f}%"
                        amount_eok = amount / 1e8
                        amount_text = f"{amount_eok:.2f}억" if abs(amount_eok) < 0.1 else f"{amount_eok:.1f}억"
                    short_name = product.replace(" Tester", "")
                    small_labels[row_index].append(f"{short_name} {share_text}\n{amount_text}")
            lefts += np.array(shares)
        ax.axvspan(100, 140, color=GRAY_PALE, zorder=0)
        ax.axvline(100, color=GRID, linewidth=0.9)
        for row_index, labels in enumerate(small_labels):
            for label_index, label in enumerate(labels):
                offset = (label_index - (len(labels) - 1) / 2) * 0.18
                ax.text(102, y[row_index] + offset, label, ha="left", va="center", fontsize=8.3, color=DARK)
        ax.set_yticks(y, [period["period"] for period in periods])
        ax.invert_yaxis()
        ax.set_xlim(0, 140)
        ax.set_xticks(np.arange(0, 101, 20))
        ax.set_xlabel("제품매출 구성비 (%)")
        ax.set_title(panel_title, fontsize=13, pad=15)
        ax.grid(axis="x", color=GRID, linewidth=0.7, alpha=0.7)
        ax.spines[["top", "right", "left"]].set_visible(False)
    handles = [Patch(facecolor=product_colors[name], label=name) for name in products]
    handles.append(Patch(facecolor=GRAY_PALE, edgecolor=GRID, label="0·미미값 라벨 영역"))
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.82), ncol=min(4, len(handles)), frameon=False)
    fig.text(
        0.5,
        0.125,
        "OFS(별도) 제품표만 사용. CLT·CIB·Board는 Memory Tester에 포함. 연간과 1분기 총액은 서로 비교하지 않음.",
        ha="center",
        fontsize=9.5,
        color=RED,
        fontweight="bold",
    )
    footer(fig, data["source_note"], meta["project_cutoff"], run_id)
    fig.subplots_adjust(top=0.70, bottom=0.28, left=0.10, right=0.98, wspace=0.28)
    return save_figure(fig, "05_v03_product_mix_ofs.png")


def render_v4(data: dict, meta: dict, run_id: str) -> Path:
    fig, (ax_value, ax_opm) = plt.subplots(
        2,
        1,
        figsize=(16, 10.5),
        sharex=True,
        gridspec_kw={"height_ratios": [1.45, 0.75]},
    )
    header(fig, data["title"], data["message"])
    rows = data["rows"]
    quarters = [row["quarter"] for row in rows]
    x = np.arange(len(rows))
    revenue = np.array([row["revenue_krw"] / 1e8 for row in rows])
    operating_income = np.array([row["operating_income_krw"] / 1e8 for row in rows])
    opm = np.array([row["operating_margin"] * 100 for row in rows])
    width = 0.38
    ax_value.bar(x - width / 2, revenue, width=width, color=BLUE_LIGHT, edgecolor=BLUE, linewidth=1.0, label="매출 (억원)")
    op_colors = [TEAL if value >= 0 else AMBER for value in operating_income]
    ax_value.bar(x + width / 2, operating_income, width=width, color=op_colors, label="영업이익 (억원)")
    ax_value.axhline(0, color=DARK, linewidth=0.9)
    ax_value.set_ylabel("억원")
    ax_value.set_title("매출·영업이익", fontsize=12.5, loc="left", pad=8)
    ax_value.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.7)
    ax_value.spines[["top", "right"]].set_visible(False)
    positive_patch = Patch(facecolor=TEAL, label="영업이익 흑자")
    negative_patch = Patch(facecolor=AMBER, label="영업손실")
    revenue_patch = Patch(facecolor=BLUE_LIGHT, edgecolor=BLUE, label="매출")
    ax_value.legend(
        handles=[revenue_patch, positive_patch, negative_patch],
        loc="upper left",
        ncol=3,
        frameon=False,
    )
    ax_opm.plot(x, opm, color=RED, marker="o", linewidth=2.0, markersize=5, label="OPM")
    ax_opm.axhline(0, color=DARK, linewidth=0.9)
    ax_opm.set_ylabel("OPM (%)")
    ax_opm.set_title("영업이익률 — 별도 축·별도 패널", fontsize=12.5, loc="left", pad=8)
    ax_opm.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.7)
    ax_opm.spines[["top", "right"]].set_visible(False)
    ax_opm.legend(loc="upper left", frameon=False)
    ax_opm.set_xticks(x, quarters, rotation=45, ha="right")
    ax_opm.tick_params(axis="x", labelsize=max(7.5, 10.0 - max(0, len(rows) - 13) * 0.15))
    ax_opm.margins(x=0.02)
    footer(fig, data["source_note"], meta["project_cutoff"], run_id, "독립 분기 계산은 누계 차감이며 원 단위 검산 후 억원으로 표시.")
    fig.subplots_adjust(top=0.76, bottom=0.32, left=0.075, right=0.98, hspace=0.28)
    return save_figure(fig, "05_v04_quarterly_revenue_opm_cfs.png")


def render_v5(data: dict, meta: dict, run_id: str) -> Path:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10.5), sharex=True, gridspec_kw={"height_ratios": [1.2, 0.8]})
    header(fig, data["title"], data["message"])
    rows = data["rows"]
    quarters = [row["quarter"] for row in rows]
    x = np.arange(len(rows))
    inventory = np.array([row["inventory_krw"] / 1e8 for row in rows])
    receivables = np.array([row["trade_and_other_current_receivables_krw"] / 1e8 for row in rows])
    ocf = np.array([row["operating_cash_flow_krw"] / 1e8 for row in rows])
    ax1.plot(x, inventory, color=TEAL, marker="o", linewidth=2.3, label="기말 재고")
    ax1.plot(x, receivables, color=BLUE, marker="s", linewidth=2.1, label="기말 매출채권·기타유동채권")
    ax1.set_ylabel("기말 잔액 (억원)")
    ax1.set_title("기말 잔액(stock)", fontsize=12.5, loc="left", pad=8)
    ax1.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.7)
    ax1.legend(loc="upper left", ncol=2, frameon=False)
    ax1.spines[["top", "right"]].set_visible(False)
    for index in range(max(0, len(rows) - 2), len(rows)):
        ax1.annotate(
            f"{quarters[index]}\n재고 {inventory[index]:,.1f}",
            xy=(x[index], inventory[index]),
            xytext=(0, 12),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9.2,
            color=TEAL,
            fontweight="bold",
        )
        ax1.annotate(
            f"채권 {receivables[index]:,.1f}",
            xy=(x[index], receivables[index]),
            xytext=(0, -15),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=9.2,
            color=BLUE,
            fontweight="bold",
        )
    colors = [BLUE if value >= 0 else AMBER for value in ocf]
    ax2.bar(x, ocf, color=colors, width=0.62)
    ax2.axhline(0, color=DARK, linewidth=0.9)
    ax2.set_ylabel("OCF (억원)")
    ax2.set_title("독립 분기 흐름(flow)", fontsize=12.5, loc="left", pad=8)
    ax2.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.7)
    ax2.set_xticks(x, quarters, rotation=45, ha="right")
    ax2.spines[["top", "right"]].set_visible(False)
    legend = [Patch(facecolor=BLUE, label="OCF 유입"), Patch(facecolor=AMBER, label="OCF 유출")]
    ax2.legend(handles=legend, loc="upper left", ncol=2, frameon=False)
    for index in range(max(0, len(rows) - 2), len(rows)):
        ax2.annotate(
            f"OCF {ocf[index]:,.1f}",
            xy=(x[index], ocf[index]),
            xytext=(0, 10 if ocf[index] >= 0 else -14),
            textcoords="offset points",
            ha="center",
            va="bottom" if ocf[index] >= 0 else "top",
            fontsize=9.2,
            color=BLUE if ocf[index] >= 0 else AMBER,
            fontweight="bold",
        )
    fig.text(
        0.5,
        0.125,
        "잔액과 흐름은 성격이 다르며, 동행은 특정 계약의 인과·진행률 증거가 아니다.",
        ha="center",
        fontsize=9.5,
        color=RED,
        fontweight="bold",
    )
    footer(fig, data["source_note"], meta["project_cutoff"], run_id)
    fig.subplots_adjust(top=0.82, bottom=0.34, left=0.07, right=0.98, hspace=0.42)
    return save_figure(fig, "05_v05_working_capital_ocf_cfs.png")


def render_v6(data: dict, meta: dict, run_id: str) -> Path:
    contracts = data["contracts"]
    fig, ax = plt.subplots(figsize=(16, max(10.5, 6.2 + 0.72 * len(contracts))))
    header(fig, data["title"], data["message"])
    labels = []
    for row in contracts:
        contract_id = row["contract_id"]
        if contract_id == "P2025-CORR-01":
            label = "2025 원계약 정정\nCLT Interface Board"
        else:
            label = f"{contract_id}\n{row['product']}"
        labels.append(label)
    y = np.arange(len(contracts))[::-1]
    for yi, row in zip(y, contracts):
        start = datetime.fromisoformat(row["start"])
        end = datetime.fromisoformat(row["end"])
        left = mdates.date2num(start)
        width = mdates.date2num(end) - left
        color = GRAY if "P2025-CORR-01" in row.get("source_ids", []) else BLUE
        ax.barh(yi, width, left=left, height=0.46, color=color, alpha=0.88)
        ax.text(
            left + width / 2,
            yi,
            "인식 U",
            ha="center",
            va="center",
            color=WHITE,
            fontsize=9.2,
            fontweight="bold",
        )
        if row.get("original_end"):
            original_date = datetime.fromisoformat(row["original_end"])
            original = mdates.date2num(original_date)
            ax.plot(original, yi, marker="x", markersize=10, markeredgewidth=2.2, color=AMBER)
    ax.set_yticks(y, labels)
    ax.set_ylim(-0.75, max(len(contracts) - 0.02, 0.75))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", rotation=45)
    ax.set_xlabel("공시된 계약기간 (막대 길이는 금액이 아님)")
    ax.grid(axis="x", color=GRID, linewidth=0.7, alpha=0.7)
    ax.spines[["top", "right", "left"]].set_visible(False)
    legend = [
        Patch(facecolor=BLUE, label="2026 신규계약"),
        Patch(facecolor=GRAY, label="2025 원계약의 2026 정정"),
        Line2D(
            [0],
            [0],
            color=AMBER,
            marker="x",
            linestyle="None",
            markersize=9,
            markeredgewidth=2.2,
            label="최초 종료일 X\nR04+R07  2026-07-31",
        ),
        Patch(facecolor=GRAY_LIGHT, label="U = 검수·수락·인식 증거 미확인"),
    ]
    fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.61, 0.80), ncol=2, frameon=False)
    fig.text(
        0.5,
        0.125,
        "종료일·지급조건을 분기 매출 배분에 사용하지 않으며, 기납품 표기도 매출로 보지 않는다.",
        ha="center",
        fontsize=9.5,
        color=RED,
        fontweight="bold",
    )
    footer(fig, data["source_note"], meta["project_cutoff"], run_id)
    fig.subplots_adjust(top=0.70, bottom=0.38, left=0.30, right=0.98)
    return save_figure(fig, "05_v06_contract_timeline_recognition_U.png")


def render_v7(data: dict, meta: dict, run_id: str) -> Path:
    fig, ax = plt.subplots(figsize=(16, 8.2))
    header(fig, data["title"], data["message"])
    ax.set_axis_off()
    lane_y = [0.66, 0.41, 0.16]
    lane_titles = ["공시 실제 (독립)", "공식 계약가치 맥락 (독립)", "인식증거·연간 결과 게이트 (독립)"]
    for y, title in zip(lane_y, lane_titles):
        ax.add_patch(
            FancyBboxPatch(
                (0.012, y - 0.038),
                0.976,
                0.215,
                boxstyle="round,pad=0.004,rounding_size=0.012",
                transform=ax.transAxes,
                facecolor=GRAY_PALE,
                edgecolor=GRID,
                linewidth=0.8,
                zorder=0,
            )
        )
        ax.text(0.02, y + 0.095, title, transform=ax.transAxes, fontsize=11.5, fontweight="bold", color=NAVY)
    ax.text(
        0.98,
        0.86,
        "비가산 맥락 보드 · 레인 사이 합계·흐름·브리지 없음",
        transform=ax.transAxes,
        ha="right",
        fontsize=10.2,
        color=RED,
        fontweight="bold",
    )
    actuals = data["reported_actuals"]
    actual_gap = 0.018
    actual_width = max(0.07, min(0.18, (0.52 - actual_gap * max(len(actuals) - 1, 0)) / max(len(actuals), 1)))
    actual_xs = np.linspace(0.19, 0.71 - actual_width, len(actuals)) if actuals else []
    for x_pos, actual in zip(actual_xs, actuals):
        add_box(
            ax,
            float(x_pos),
            lane_y[0],
            actual_width,
            0.13,
            f"{actual['period']} A/F\n연결 매출 {fmt_eok(actual['revenue_krw'], decimals=1)}",
            facecolor=BLUE_LIGHT,
            edgecolor=BLUE,
            textcolor=NAVY,
            fontsize=max(8.5, 10.8 - max(0, len(actuals) - 3) * 0.35),
            fontweight="bold",
        )
    ax.text(0.75, lane_y[0] + 0.065, "기간이 달라 증감 bridge가 아님", transform=ax.transAxes, color=GRAY, fontsize=10.2, va="center")
    contracts = data["contract_value_context"]["contracts"]
    contract_gap = 0.012
    chip_width = max(0.045, min(0.12, (0.61 - contract_gap * max(len(contracts) - 1, 0)) / max(len(contracts), 1)))
    chip_xs = np.linspace(0.18, 0.79 - chip_width, len(contracts)) if contracts else []
    for x, contract in zip(chip_xs, contracts):
        add_box(
            ax,
            float(x),
            lane_y[1],
            chip_width,
            0.105,
            f"{contract['contract_id']}\n{fmt_eok(contract['contract_value_krw'], decimals=1)}",
            facecolor=GRAY_PALE,
            edgecolor=GRAY,
            fontsize=max(7.2, 9.5 - max(0, len(contracts) - 4) * 0.35),
            hatch="//",
        )
    add_box(
        ax,
        0.84,
        lane_y[1],
        0.13,
        0.105,
        f"{len(contracts)}건 합계\n{fmt_eok(data['contract_value_context']['new_2026_contract_value_krw'], decimals=1)}",
        facecolor=AMBER_LIGHT,
        edgecolor=AMBER,
        fontsize=9.5,
        fontweight="bold",
    )
    ax.text(0.5, lane_y[1] - 0.062, "계약가치 F · 매출/수주잔고/인식액 아님 · 실제 매출에 더하지 않음", transform=ax.transAxes, ha="center", fontsize=9.5, color=RED, fontweight="bold")
    add_box(
        ax,
        0.20,
        lane_y[2],
        0.24,
        0.13,
        "계약별 검수·고객 수락\n인식 금액·기간  U",
        facecolor=GRAY_LIGHT,
        edgecolor=GRAY,
        fontsize=10.8,
        fontweight="bold",
    )
    add_box(
        ax,
        0.47,
        lane_y[2] + 0.012,
        0.10,
        0.106,
        "별도 확인\n산식 연결 불가",
        facecolor=WHITE,
        edgecolor=GRAY,
        textcolor=GRAY,
        fontsize=9.0,
        linewidth=1.0,
    )
    add_box(
        ax,
        0.60,
        lane_y[2],
        0.20,
        0.13,
        "2026FY 연결 매출\nU · 숫자 미산출",
        facecolor=GRAY_LIGHT,
        edgecolor=GRAY,
        fontsize=11.2,
        fontweight="bold",
    )
    ax.text(0.91, lane_y[2] + 0.065, "0이 아님", transform=ax.transAxes, ha="center", va="center", color=RED, fontsize=10.5, fontweight="bold")
    footer(fig, data["source_note"], meta["project_cutoff"], run_id, "세 레인은 서로 가산하거나 순차 흐름으로 연결하지 않는다. 표시 금액은 최소 소수점 한 자리 억원.")
    fig.subplots_adjust(top=0.87, bottom=0.15, left=0.02, right=0.98)
    return save_figure(fig, "05_v07_actual_contract_recognition_bridge.png")


def render_v8(data: dict, meta: dict, run_id: str) -> Path:
    scenarios = data["scenarios"]
    fig, ax = plt.subplots(figsize=(15.5, max(7.5, 4.8 + 0.65 * len(scenarios))))
    header(fig, data["title"], data["message"])
    ax.set_axis_off()
    status_display = {
        "CURRENT_UNRESOLVED": ("미해결", GRAY, GRAY_PALE, "계약은 유효하지만 검수·수익인식은 미확인"),
        "BASE_EVIDENCE_GATE": ("증거 대기", GRAY, GRAY_LIGHT, "계약별 수락·인식 금액과 기간 공식 확인 필요"),
        "BULL_EVIDENCE_GATE": ("증거 대기", GRAY, GRAY_LIGHT, "기준 증거 + 신규 양산·실제 마진·OCF 개선 필요"),
        "BEAR_EVIDENCE_GATE": ("부분 경고", AMBER, AMBER_LIGHT, "R04+R07 일정 정정 + 재고·OCF 경고, 회사 전체 영향은 U"),
    }
    y_positions = np.linspace(0.70, 0.14, len(scenarios)) if scenarios else []
    for scenario, y in zip(scenarios, y_positions):
        status, edge, face, evidence = status_display.get(
            scenario["scenario_id"],
            ("미해결", GRAY, GRAY_PALE, "공식 전환 증거 미확인"),
        )
        ax.text(0.05, y + 0.055, scenario["display_label"], transform=ax.transAxes, ha="left", va="center", fontsize=12, fontweight="bold")
        add_box(ax, 0.27, y, 0.18, 0.11, status, facecolor=face, edgecolor=edge, textcolor=edge if edge != GRAY else DARK, fontsize=11, fontweight="bold")
        ax.text(
            0.50,
            y + 0.055,
            "\n".join(textwrap.wrap(evidence, width=28, break_long_words=False)),
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=10.4,
            color=DARK,
        )
    ax.text(0.5, 0.84, "확률 없음 · 임의 인식률 없음 · 숫자형 실적 막대 없음", transform=ax.transAxes, ha="center", fontsize=11, color=RED, fontweight="bold")
    footer(fig, data["source_note"], meta["project_cutoff"], run_id)
    fig.subplots_adjust(top=0.87, bottom=0.14, left=0.02, right=0.98)
    return save_figure(fig, "05_v08_evidence_scenario_state.png")


def render_v9(data: dict, meta: dict, run_id: str) -> Path:
    cases = data["contract_cases"]
    anchors = data["margin_anchors"]
    fig, ax = plt.subplots(figsize=(15.5, max(8.3, 5.5 + 0.72 * len(cases))))
    header(fig, data["title"], data["message"])
    lookup = {(row["contract_case_id"], row["margin_anchor_id"]): row for row in data["rows"]}
    matrix = np.array(
        [
            [lookup[(case["case_id"], anchor["anchor_id"])]["counterfactual_operating_result_krw"] / 1e8 for anchor in anchors]
            for case in cases
        ]
    )
    max_abs = float(np.max(np.abs(matrix)))
    color_scale = max(max_abs, 1.0)
    image = ax.imshow(matrix, cmap="RdYlBu", norm=TwoSlopeNorm(vmin=-color_scale, vcenter=0, vmax=color_scale), aspect="auto")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            color = WHITE if abs(value) > color_scale * 0.55 else DARK
            label = f"{value:,.1f}억원" if 0 < abs(value) < 1 else f"{value:,.0f}억원"
            ax.text(j, i, label, ha="center", va="center", fontsize=11, color=color, fontweight="bold")
    xlabels = [f"{anchor['period']}\n실제 OPM\n{anchor['observed_operating_margin'] * 100:.1f}%" for anchor in anchors]
    ylabels = [f"{case['case_id']}  {case['label']}\n계약가치 {case['contract_value_krw'] / 1e8:,.1f}억원" for case in cases]
    ax.set_xticks(np.arange(len(anchors)), xlabels)
    ax.set_yticks(np.arange(len(cases)), ylabels)
    ax.tick_params(axis="x", length=0, pad=12)
    ax.tick_params(axis="y", length=0)
    cbar = fig.colorbar(image, ax=ax, fraction=0.025, pad=0.025)
    cbar.set_ticks(np.linspace(-color_scale, color_scale, 7)[1:-1])
    cbar.set_label("반사실 영업손익(억원)", labelpad=12)
    fig.text(0.5, 0.105, "각 행은 독립 사례이며 합산하지 않는다. 계약가치 전액·동일 전사 OPM이라는 극단 가정이고 제품마진·인식액·확률이 아니다.", ha="center", fontsize=9.5, color=RED, fontweight="bold")
    footer(fig, data["source_note"], meta["project_cutoff"], run_id)
    fig.subplots_adjust(top=0.80, bottom=0.25, left=0.28, right=0.84)
    return save_figure(fig, "05_v09_counterfactual_contract_opm.png")


def render_v10(data: dict, meta: dict, run_id: str) -> Path:
    fig = plt.figure(figsize=(16, 9.5))
    header(fig, data["title"], data["message"])
    ax1 = fig.add_axes([0.07, 0.32, 0.43, 0.46])
    ax2 = fig.add_axes([0.55, 0.26, 0.40, 0.54])
    valuation = data["valuation"]
    market_cap = valuation["market_cap_krw"] / 1e8
    net_cash = valuation["net_cash_bridge"]["net_cash_krw"] / 1e8
    ev = valuation["enterprise_value_krw"] / 1e8
    bridge_adjustment = -net_cash
    label_pad = max(abs(market_cap), abs(ev), abs(net_cash), 1.0) * 0.025
    ax1.bar(0, market_cap, color=BLUE, width=0.56)
    ax1.bar(1, bridge_adjustment, bottom=market_cap, color=TEAL_LIGHT, edgecolor=TEAL, hatch="//", width=0.56)
    ax1.bar(2, ev, color=NAVY, width=0.56)
    ax1.plot([0.28, 0.72], [market_cap, market_cap], color=GRAY, linestyle="--", linewidth=1)
    ax1.plot([1.28, 1.72], [ev, ev], color=GRAY, linestyle="--", linewidth=1)
    ax1.text(0, market_cap + label_pad, f"{market_cap:,.1f}", ha="center", fontsize=11, fontweight="bold")
    ax1.text(1, market_cap + bridge_adjustment / 2, f"{bridge_adjustment:+,.1f}", ha="center", va="center", fontsize=10.5, color=TEAL, fontweight="bold")
    ax1.text(2, ev + label_pad, f"{ev:,.1f}", ha="center", fontsize=11, fontweight="bold")
    market_date = valuation["market_date"]
    balance_sheet_date = valuation["balance_sheet_date"]
    ax1.set_xticks(
        [0, 1, 2],
        [f"시가총액\n{market_date}", f"순현금 차감\n{balance_sheet_date}", "기업가치 EV\n시점 혼합"],
    )
    ax1.set_ylabel("억원")
    ax1.set_title("시장가치 브리지", fontsize=13, pad=12)
    ax1.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.7)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.margins(y=0.12)
    ax2.set_axis_off()
    ax2.text(0.5, 0.96, "내재 기대 산출 게이트", transform=ax2.transAxes, ha="center", va="top", fontsize=13, fontweight="bold")
    add_box(ax2, 0.05, 0.70, 0.90, 0.14, "기업가치 ÷ 동일 기준 Peer EV/Sales (U)\n= 요구 매출 U", facecolor=GRAY_LIGHT, edgecolor=GRAY, fontsize=11, fontweight="bold")
    add_box(ax2, 0.05, 0.48, 0.90, 0.14, "기업가치 ÷ 동일 기준 Peer EV/영업이익 (U)\n= 요구 영업이익 U", facecolor=GRAY_LIGHT, edgecolor=GRAY, fontsize=11, fontweight="bold")
    add_box(ax2, 0.05, 0.26, 0.90, 0.14, "목표가격  =  U · 미산출", facecolor=AMBER_LIGHT, edgecolor=AMBER, fontsize=12, fontweight="bold")
    diagnostics = valuation["self_diagnostic_multiples"]
    ax2.text(0.5, 0.10, f"현재가격 자기진단: EV/LTM Sales {diagnostics['ev_to_ltm_sales']:.1f}x\n적정가치·목표배수가 아님", transform=ax2.transAxes, ha="center", va="center", fontsize=10, color=RED, fontweight="bold")
    footer(fig, data["source_note"], meta["project_cutoff"], run_id, data["warning"])
    return save_figure(fig, "05_v10_market_value_expectation_gate.png")


def wrap_text(value: str, width: int) -> str:
    return "\n".join(textwrap.wrap(value, width=width, break_long_words=False, break_on_hyphens=False))


def render_v11(data: dict, meta: dict, run_id: str) -> Path:
    rows = data["rows"]
    fig, ax = plt.subplots(figsize=(17, max(15.5, 7.0 + 1.0 * len(rows))))
    header(fig, data["title"], data["message"])
    ax.set_axis_off()
    columns = [
        ("확인 사건", 0.02, 0.20),
        ("현재", 0.22, 0.09),
        ("현재 공식 근거", 0.31, 0.27),
        ("객관적 전이 조건", 0.58, 0.27),
        ("변경 차트", 0.85, 0.13),
    ]
    top = 0.82
    row_h = min(0.078, 0.65 / max(len(rows), 1))
    header_h = 0.065
    for label, x, w in columns:
        ax.add_patch(Rectangle((x, top), w, header_h, transform=ax.transAxes, facecolor=NAVY, edgecolor=WHITE, linewidth=1))
        ax.text(x + w / 2, top + header_h / 2, label, transform=ax.transAxes, ha="center", va="center", color=WHITE, fontsize=10.3, fontweight="bold")
    state_style = {
        "확인": (BLUE_LIGHT, BLUE, NAVY),
        "경고": (AMBER_LIGHT, AMBER, DARK),
        "U": (GRAY_LIGHT, GRAY, DARK),
    }
    for i, row in enumerate(rows):
        y = top - (i + 1) * row_h
        background = WHITE if i % 2 == 0 else GRAY_PALE
        for _, x, w in columns:
            ax.add_patch(Rectangle((x, y), w, row_h, transform=ax.transAxes, facecolor=background, edgecolor=GRID, linewidth=0.7))
        ax.text(0.03, y + row_h / 2, wrap_text(row["item"], 11), transform=ax.transAxes, ha="left", va="center", fontsize=9.2, fontweight="bold")
        face, edge, textcolor = state_style[row["state"]]
        state_pad = min(0.016, row_h * 0.20)
        add_box(ax, 0.235, y + state_pad, 0.06, row_h - 2 * state_pad, row["state"], facecolor=face, edgecolor=edge, textcolor=textcolor, fontsize=9.5, fontweight="bold", radius=0.008)
        ax.text(0.32, y + row_h / 2, wrap_text(row["current_evidence"], 16), transform=ax.transAxes, ha="left", va="center", fontsize=8.8)
        ax.text(0.59, y + row_h / 2, wrap_text(row["transition"], 16), transform=ax.transAxes, ha="left", va="center", fontsize=8.8)
        ax.text(0.915, y + row_h / 2, row["changes"], transform=ax.transAxes, ha="center", va="center", fontsize=8.5, color=NAVY)
    ax.text(0.02, 0.095, "U는 실패나 0이 아니라 공식 증거 미확인이다. 일정 경고는 해당 계약에만, 재고·OCF 경고는 회사 전체 현금전환에만 적용한다.", transform=ax.transAxes, fontsize=9.5, color=RED, fontweight="bold")
    footer(fig, data["source_note"], meta["project_cutoff"], run_id, f"최신 공시 조회 {data['latest_retrieval']}")
    fig.subplots_adjust(top=0.88, bottom=0.14, left=0.01, right=0.99)
    return save_figure(fig, "05_v11_risk_monitoring_matrix.png")


def main() -> int:
    global FIGURES
    LAYOUT_AUDIT.clear()
    args = parse_args()
    run_dir = resolve_input_run(args.input_run)
    data_path = run_dir / "phase5_chart_data.json"
    data = read_json(data_path)
    validate_input_freshness(
        run_dir,
        data,
        max_input_age_hours=args.max_input_age_hours,
        allow_stale_inputs=args.allow_stale_inputs,
    )
    explicit_output = args.output_dir is not None
    if explicit_output:
        FIGURES = resolve_path(args.output_dir)
    manifest_path = FIGURES / "phase5_render_manifest.json" if explicit_output else run_dir / "phase5_render_manifest.json"
    output_names = [
        "05_v01_demand_to_revenue_evidence_path.png",
        "05_v02_test_value_chain_position.png",
        "05_v03_product_mix_ofs.png",
        "05_v04_quarterly_revenue_opm_cfs.png",
        "05_v05_working_capital_ocf_cfs.png",
        "05_v06_contract_timeline_recognition_U.png",
        "05_v07_actual_contract_recognition_bridge.png",
        "05_v08_evidence_scenario_state.png",
        "05_v09_counterfactual_contract_opm.png",
        "05_v10_market_value_expectation_gate.png",
        "05_v11_risk_monitoring_matrix.png",
    ]
    if explicit_output and not args.overwrite:
        existing_outputs = [FIGURES / name for name in [*output_names, manifest_path.name] if (FIGURES / name).exists()]
        if existing_outputs:
            raise FileExistsError(f"Explicit output files already exist; pass --overwrite to replace them: {existing_outputs}")
    previous_manifest = read_json(manifest_path) if manifest_path.is_file() else None

    font = setup_style()
    run_id = run_dir.name
    visualizations = data["visualizations"]
    outputs = [
        render_v1(visualizations["V1"], data, run_id),
        render_v2(visualizations["V2"], data, run_id),
        render_v3(visualizations["V3"], data, run_id),
        render_v4(visualizations["V4"], data, run_id),
        render_v5(visualizations["V5"], data, run_id),
        render_v6(visualizations["V6"], data, run_id),
        render_v7(visualizations["V7"], data, run_id),
        render_v8(visualizations["V8"], data, run_id),
        render_v9(visualizations["V9"], data, run_id),
        render_v10(visualizations["V10"], data, run_id),
        render_v11(visualizations["V11"], data, run_id),
    ]
    figures = []
    automated_checks = []
    for path in outputs:
        with Image.open(path) as image:
            width, height = image.size
        size = path.stat().st_size
        layout_audit = LAYOUT_AUDIT[path.name]
        figures.append(
            {
                "file": display_path(path),
                "sha256": sha256(path),
                "width": width,
                "height": height,
                "bytes": size,
                "layout_audit": layout_audit,
            }
        )
        automated_checks.extend(
            [
                {"check": f"{path.name}-width", "passed": width >= 1800, "actual": width, "expected_min": 1800},
                {"check": f"{path.name}-height", "passed": height >= 850, "actual": height, "expected_min": 850},
                {"check": f"{path.name}-bytes", "passed": size >= 50_000, "actual": size, "expected_min": 50_000},
                {
                    "check": f"{path.name}-a4-core-font",
                    "passed": layout_audit["min_core_font_pt_at_178mm"] + 1e-9 >= A4_CORE_FONT_MIN_PT,
                    "actual": layout_audit["min_core_font_pt_at_178mm"],
                    "expected_min": A4_CORE_FONT_MIN_PT,
                },
                {
                    "check": f"{path.name}-a4-source-font",
                    "passed": layout_audit["min_source_font_pt_at_178mm"] + 1e-9 >= A4_SOURCE_FONT_MIN_PT,
                    "actual": layout_audit["min_source_font_pt_at_178mm"],
                    "expected_min": A4_SOURCE_FONT_MIN_PT,
                },
                {
                    "check": f"{path.name}-text-clipping",
                    "passed": layout_audit["clipped_text_count"] == 0,
                    "actual": layout_audit["clipped_text_count"],
                    "expected": 0,
                },
                {
                    "check": f"{path.name}-text-overlap",
                    "passed": layout_audit["overlap_count"] == 0,
                    "actual": layout_audit["overlap_count"],
                    "expected": 0,
                },
            ]
        )
    failed = [row for row in automated_checks if not row["passed"]]
    if failed:
        raise RuntimeError(f"Automated render checks failed: {failed}")
    manifest = {
        "title": "Phase 5 render manifest",
        "run_id": run_id,
        "rendered_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "input_run": display_path(run_dir),
        "input_chart_sha256": sha256(data_path),
        "output_dir": display_path(FIGURES),
        "font": font,
        "figure_count": len(figures),
        "figures": figures,
        "automated_checks": {
            "total": len(automated_checks),
            "passed": sum(row["passed"] for row in automated_checks),
            "failed": len(failed),
            "rows": automated_checks,
        },
        "manual_visual_qa": preserved_manual_qa(previous_manifest, figures),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "run_dir": display_path(run_dir),
                "manifest": display_path(manifest_path),
                "figures": [display_path(path) for path in outputs],
                "checks_passed": len(automated_checks),
                "font": font,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
