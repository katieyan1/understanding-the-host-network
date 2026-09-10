#!/usr/bin/env python3
"""Generate SVG figures from the result tables in analysis.md."""

from __future__ import annotations

import html
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "analysis.md"
OUTPUT_DIR = ROOT / "figures"

COLORS = ("#2563eb", "#dc2626", "#059669", "#7c3aed")
TEXT = "#172033"
MUTED = "#526075"
GRID = "#d9e0ea"
PANEL = "#f8fafc"


def parse_number(value: str) -> float:
    value = value.strip().replace(",", "")
    value = re.sub(r"[%x]$", "", value)
    return float(value.lstrip("+"))


def read_tables(path: Path) -> dict[str, list[dict[str, float]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    tables: dict[str, list[dict[str, float]]] = {}
    section = ""
    i = 0
    while i < len(lines):
        if lines[i].startswith("## "):
            section = lines[i][3:].strip()
        if (
            lines[i].startswith("|")
            and i + 1 < len(lines)
            and re.fullmatch(r"\|[|:\- ]+\|", lines[i + 1])
        ):
            columns = [cell.strip() for cell in lines[i].strip("|").split("|")]
            rows: list[dict[str, float]] = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [cell.strip() for cell in lines[i].strip("|").split("|")]
                rows.append({name: parse_number(value) for name, value in zip(columns, cells)})
                i += 1
            tables[section] = rows
            continue
        i += 1
    return tables


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def compact(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:g}M"
    if absolute >= 1_000:
        return f"{value / 1_000:g}k"
    if absolute >= 10:
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def nice_ceiling(value: float) -> float:
    if value <= 0:
        return 1
    rough_step = value / 5
    magnitude = 10 ** math.floor(math.log10(rough_step))
    normalized = rough_step / magnitude
    step = 1 if normalized <= 1 else 2 if normalized <= 2 else 2.5 if normalized <= 2.5 else 5 if normalized <= 5 else 10
    step *= magnitude
    return math.ceil(value / step) * step


def svg_text(
    chunks: list[str],
    x: float,
    y: float,
    value: object,
    *,
    size: int = 14,
    weight: int = 400,
    anchor: str = "start",
    fill: str = TEXT,
    rotate: int | None = None,
) -> None:
    transform = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate is not None else ""
    chunks.append(
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}" fill="{fill}"{transform}>{esc(value)}</text>'
    )


def draw_panel(
    chunks: list[str],
    rows: list[dict[str, float]],
    x_column: str,
    panel: dict[str, object],
    panel_x: int,
    panel_y: int,
    panel_w: int,
    panel_h: int,
) -> None:
    chunks.append(
        f'<rect x="{panel_x}" y="{panel_y}" width="{panel_w}" height="{panel_h}" '
        f'rx="12" fill="{PANEL}" stroke="{GRID}"/>'
    )
    svg_text(chunks, panel_x + 24, panel_y + 32, panel["title"], size=17, weight=700)

    series = panel["series"]
    assert isinstance(series, list)
    plot_x = panel_x + 78
    plot_y = panel_y + 70
    plot_w = panel_w - 106
    plot_h = panel_h - 135
    x_values = [row[x_column] for row in rows]
    all_y = [row[column] for column, _ in series for row in rows]
    y_max = nice_ceiling(max(all_y) * 1.03)

    tick_count = 5
    for tick in range(tick_count + 1):
        value = y_max * tick / tick_count
        y = plot_y + plot_h - plot_h * tick / tick_count
        chunks.append(
            f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        svg_text(chunks, plot_x - 10, y + 5, compact(value), anchor="end", fill=MUTED, size=12)

    x_min, x_max = min(x_values), max(x_values)

    def sx(value: float) -> float:
        if x_min == x_max:
            return plot_x + plot_w / 2
        return plot_x + (value - x_min) / (x_max - x_min) * plot_w

    def sy(value: float) -> float:
        return plot_y + plot_h - value / y_max * plot_h

    for value in x_values:
        x = sx(value)
        chunks.append(
            f'<line x1="{x:.1f}" y1="{plot_y + plot_h}" x2="{x:.1f}" y2="{plot_y + plot_h + 5}" '
            f'stroke="{MUTED}"/>'
        )
        svg_text(chunks, x, plot_y + plot_h + 23, compact(value), anchor="middle", fill=MUTED, size=12)

    chunks.append(
        f'<line x1="{plot_x}" y1="{plot_y}" x2="{plot_x}" y2="{plot_y + plot_h}" stroke="{MUTED}"/>'
    )
    chunks.append(
        f'<line x1="{plot_x}" y1="{plot_y + plot_h}" x2="{plot_x + plot_w}" y2="{plot_y + plot_h}" stroke="{MUTED}"/>'
    )

    for index, (column, label) in enumerate(series):
        color = COLORS[index]
        points = " ".join(f"{sx(row[x_column]):.1f},{sy(row[column]):.1f}" for row in rows)
        chunks.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for row in rows:
            chunks.append(
                f'<circle cx="{sx(row[x_column]):.1f}" cy="{sy(row[column]):.1f}" r="4.5" '
                f'fill="white" stroke="{color}" stroke-width="3"/>'
            )

        legend_x = plot_x + plot_w - 12
        legend_y = panel_y + 28 + index * 21
        chunks.append(
            f'<line x1="{legend_x - 128}" y1="{legend_y - 4}" x2="{legend_x - 106}" y2="{legend_y - 4}" '
            f'stroke="{color}" stroke-width="3"/>'
        )
        svg_text(chunks, legend_x - 100, legend_y, label, fill=MUTED, size=12)

    svg_text(chunks, plot_x + plot_w / 2, panel_y + panel_h - 16, "Number of cores", anchor="middle", size=13)
    svg_text(
        chunks,
        panel_x + 19,
        plot_y + plot_h / 2,
        panel["ylabel"],
        anchor="middle",
        size=13,
        rotate=-90,
    )


def render_figure(
    rows: list[dict[str, float]],
    x_column: str,
    title: str,
    panels: list[dict[str, object]],
    destination: Path,
) -> None:
    columns = 2
    panel_w, panel_h = 560, 330
    gap_x, gap_y = 24, 24
    outer_x, top = 28, 76
    panel_rows = math.ceil(len(panels) / columns)
    width = outer_x * 2 + panel_w * columns + gap_x
    height = top + panel_h * panel_rows + gap_y * (panel_rows - 1) + 30
    chunks = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f'<title>{esc(title)}</title>',
        f'<desc>Line charts generated from {esc(SOURCE.name)}. Every x-axis is number of cores.</desc>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g font-family="Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">',
    ]
    svg_text(chunks, outer_x, 40, title, size=25, weight=700)
    svg_text(chunks, width - outer_x, 39, "Source: analysis.md", anchor="end", fill=MUTED, size=12)
    for index, panel in enumerate(panels):
        row, column = divmod(index, columns)
        draw_panel(
            chunks,
            rows,
            x_column,
            panel,
            outer_x + column * (panel_w + gap_x),
            top + row * (panel_h + gap_y),
            panel_w,
            panel_h,
        )
    chunks.extend(("</g>", "</svg>"))
    destination.write_text("\n".join(chunks) + "\n", encoding="utf-8")


FIGURES = {
    "STREAM core scaling": {
        "file": "stream-core-scaling.svg",
        "x": "Cores",
        "panels": [
            {"title": "Memory bandwidth", "ylabel": "GB/s", "series": [("STREAM (GB/s)", "STREAM"), ("DRAM read (GB/s)", "DRAM read")]},
            {"title": "Application speedup", "ylabel": "Speedup (×)", "series": [("Speedup", "Measured")]},
            {"title": "Scaling efficiency", "ylabel": "Percent (%)", "series": [("Scaling efficiency", "Efficiency")]},
            {"title": "Memory latency", "ylabel": "Nanoseconds", "series": [("L1 miss latency (ns)", "L1 miss"), ("DRd latency (ns)", "DRd")]},
            {"title": "Read-pending queue occupancy", "ylabel": "Entries/channel", "series": [("RPQ occupancy/channel", "RPQ occupancy")]},
        ],
    },
    "STREAM plus four-NVMe colocation": {
        "file": "stream-fio-colocation.svg",
        "x": "STREAM cores",
        "panels": [
            {"title": "STREAM throughput", "ylabel": "GB/s", "series": [("Isolated STREAM (GB/s)", "Isolated"), ("Colocated STREAM (GB/s)", "Colocated")]},
            {"title": "Colocated fio throughput", "ylabel": "GB/s", "series": [("Colocated fio (GB/s)", "fio")]},
            {"title": "Throughput impact", "ylabel": "Percent (%)", "series": [("STREAM loss", "STREAM loss"), ("fio change", "fio change")]},
            {"title": "L1 miss latency", "ylabel": "Nanoseconds", "series": [("Isolated L1 latency (ns)", "Isolated"), ("Colocated L1 latency (ns)", "Colocated")]},
        ],
    },
    "GAPBS PageRank scaling": {
        "file": "gapbs-pagerank-scaling.svg",
        "x": "Cores",
        "panels": [
            {"title": "Mean trial time", "ylabel": "Seconds", "series": [("Mean trial time (s)", "Trial time")]},
            {"title": "Application speedup", "ylabel": "Speedup (×)", "series": [("Speedup", "Measured")]},
            {"title": "Parallel efficiency", "ylabel": "Percent (%)", "series": [("Parallel efficiency", "Efficiency")]},
            {"title": "DRAM read bandwidth", "ylabel": "GB/s", "series": [("DRAM read (GB/s)", "DRAM read")]},
        ],
    },
    "Redis GET scaling": {
        "file": "redis-get-scaling.svg",
        "x": "Total cores",
        "panels": [
            {"title": "Server-client pairs", "ylabel": "Pairs", "series": [("Server-client pairs", "Pairs")]},
            {"title": "Aggregate throughput", "ylabel": "GET/s", "series": [("Aggregate GET/s", "GET/s")]},
            {"title": "Application speedup", "ylabel": "Speedup (×)", "series": [("Speedup", "Measured")]},
            {"title": "Pair-scaling efficiency", "ylabel": "Percent (%)", "series": [("Pair-scaling efficiency", "Efficiency")]},
            {"title": "DRAM read bandwidth", "ylabel": "GB/s", "series": [("DRAM read (GB/s)", "DRAM read")]},
        ],
    },
}


def main() -> None:
    tables = read_tables(SOURCE)
    OUTPUT_DIR.mkdir(exist_ok=True)
    for section, figure in FIGURES.items():
        render_figure(
            tables[section],
            figure["x"],
            section,
            figure["panels"],
            OUTPUT_DIR / figure["file"],
        )
        print(OUTPUT_DIR / figure["file"])


if __name__ == "__main__":
    main()
