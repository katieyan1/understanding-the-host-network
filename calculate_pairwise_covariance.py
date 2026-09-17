#!/usr/bin/env python3
"""Calculate pairwise metric covariance and correlation for each dataset.

Each input file is expected to be in long form, with one row per metric scope
and sample index.  Values are first grouped by experiment, metric, and
``sample_index``; scope values in each group are summed by default.  The
sample covariance and Pearson correlation for every pair of different metrics
are then calculated across the sample indices present for both metrics.
Results are sorted by correlation magnitude from strongest to weakest.

By default, each result is written beside its input as
``pairwise-covariance.csv``.  Run ``python3 calculate_pairwise_covariance.py
--help`` for other aggregation and output options.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable


INPUT_NAME = "dependable-metric-samples.csv"
OUTPUT_NAME = "pairwise-covariance.csv"
REQUIRED_COLUMNS = {"experiment", "metric", "sample_index", "value", "unit"}


@dataclass(frozen=True)
class CovarianceRow:
    experiment: str
    metric_a: str
    unit_a: str
    metric_b: str
    unit_b: str
    sample_count: int
    covariance: float
    correlation: float | None


def read_metric_series(
    path: Path, aggregation: str
) -> tuple[dict[str, dict[str, dict[str, float]]], dict[tuple[str, str], str]]:
    """Return values indexed by experiment, metric, and sample index."""

    totals: dict[tuple[str, str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    units: dict[tuple[str, str], str] = {}

    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing_columns = REQUIRED_COLUMNS.difference(reader.fieldnames or ())
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"{path}: missing required column(s): {missing}")

        for line_number, row in enumerate(reader, start=2):
            experiment = row["experiment"].strip()
            metric = row["metric"].strip()
            sample_index = row["sample_index"].strip()
            unit = row["unit"].strip()

            if not experiment or not metric or not sample_index:
                raise ValueError(
                    f"{path}:{line_number}: experiment, metric, and "
                    "sample_index must be non-empty"
                )

            try:
                value = float(row["value"])
            except ValueError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid numeric value {row['value']!r}"
                ) from error
            if not math.isfinite(value):
                raise ValueError(
                    f"{path}:{line_number}: value must be finite, got {row['value']!r}"
                )

            unit_key = (experiment, metric)
            previous_unit = units.setdefault(unit_key, unit)
            if previous_unit != unit:
                raise ValueError(
                    f"{path}:{line_number}: metric {metric!r} has inconsistent "
                    f"units {previous_unit!r} and {unit!r}"
                )

            value_key = (experiment, metric, sample_index)
            totals[value_key] += value
            counts[value_key] += 1

    series: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for (experiment, metric, sample_index), total in totals.items():
        value = (
            total
            if aggregation == "sum"
            else total / counts[(experiment, metric, sample_index)]
        )
        series[experiment][metric][sample_index] = value

    return {
        experiment: {metric: dict(values) for metric, values in metrics.items()}
        for experiment, metrics in series.items()
    }, units


def pair_statistics(
    left: dict[str, float], right: dict[str, float], ddof: int
) -> tuple[int, float, float | None] | None:
    """Calculate covariance and Pearson correlation on shared sample indices."""

    shared_indices = left.keys() & right.keys()
    sample_count = len(shared_indices)
    if sample_count <= ddof:
        return None

    left_mean = math.fsum(left[index] for index in shared_indices) / sample_count
    right_mean = math.fsum(right[index] for index in shared_indices) / sample_count
    deviations = [
        (left[index] - left_mean, right[index] - right_mean)
        for index in shared_indices
    ]
    cross_deviations = math.fsum(
        left_value * right_value
        for left_value, right_value in deviations
    )
    left_squared_deviations = math.fsum(
        left_value * left_value for left_value, _ in deviations
    )
    right_squared_deviations = math.fsum(
        right_value * right_value for _, right_value in deviations
    )
    correlation_denominator = math.sqrt(
        left_squared_deviations * right_squared_deviations
    )
    correlation = (
        cross_deviations / correlation_denominator
        if correlation_denominator != 0.0
        else None
    )
    if correlation is not None:
        correlation = max(-1.0, min(1.0, correlation))
    covariance = cross_deviations / (sample_count - ddof)
    return sample_count, covariance, correlation


def calculate_rows(
    series: dict[str, dict[str, dict[str, float]]],
    units: dict[tuple[str, str], str],
    ddof: int,
) -> tuple[list[CovarianceRow], dict[str, list[str]]]:
    """Calculate all non-zero metric pairs for every experiment."""

    rows: list[CovarianceRow] = []
    ignored_metrics: dict[str, list[str]] = {}

    for experiment in sorted(series):
        metrics = series[experiment]
        ignored_metrics[experiment] = sorted(
            metric
            for metric, values in metrics.items()
            if all(value == 0.0 for value in values.values())
        )
        retained_metrics = sorted(set(metrics).difference(ignored_metrics[experiment]))

        for metric_a, metric_b in combinations(retained_metrics, 2):
            result = pair_statistics(metrics[metric_a], metrics[metric_b], ddof)
            if result is None:
                continue
            sample_count, covariance, correlation = result
            rows.append(
                CovarianceRow(
                    experiment=experiment,
                    metric_a=metric_a,
                    unit_a=units[(experiment, metric_a)],
                    metric_b=metric_b,
                    unit_b=units[(experiment, metric_b)],
                    sample_count=sample_count,
                    covariance=covariance,
                    correlation=correlation,
                )
            )

    rows.sort(
        key=lambda row: (
            row.experiment,
            row.correlation is None,
            -abs(row.correlation) if row.correlation is not None else 0.0,
            row.metric_a,
            row.metric_b,
        )
    )
    return rows, ignored_metrics


def write_rows(path: Path, rows: Iterable[CovarianceRow]) -> None:
    """Write result rows atomically so a failed run cannot truncate output."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "experiment",
        "metric_a",
        "unit_a",
        "metric_b",
        "unit_b",
        "sample_count",
        "covariance",
        "correlation",
    ]

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as destination:
            temporary_name = destination.name
            writer = csv.DictWriter(destination, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "experiment": row.experiment,
                        "metric_a": row.metric_a,
                        "unit_a": row.unit_a,
                        "metric_b": row.metric_b,
                        "unit_b": row.unit_b,
                        "sample_count": row.sample_count,
                        "covariance": format(row.covariance, ".17g"),
                        "correlation": (
                            format(row.correlation, ".17g")
                            if row.correlation is not None
                            else ""
                        ),
                    }
                )
        os.replace(temporary_name, path)
    except BaseException:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def output_path(input_path: Path, output_dir: Path | None) -> Path:
    if output_dir is None:
        return input_path.with_name(OUTPUT_NAME)
    return output_dir / f"{input_path.parent.name}-{OUTPUT_NAME}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".correlation-data"),
        help="directory containing */dependable-metric-samples.csv (default: %(default)s)",
    )
    parser.add_argument(
        "--aggregation",
        choices=("sum", "mean"),
        default="sum",
        help="how to combine scopes for each metric and sample_index (default: %(default)s)",
    )
    parser.add_argument(
        "--ddof",
        type=int,
        choices=(0, 1),
        default=1,
        help="covariance delta degrees of freedom: 1=sample, 0=population (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "write all results to this directory with dataset-prefixed names; "
            "by default, write pairwise-covariance.csv beside each input"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inputs = sorted(args.data_dir.glob(f"*/{INPUT_NAME}"))
    if not inputs:
        raise SystemExit(
            f"no {INPUT_NAME} files found one directory below {args.data_dir}"
        )

    for input_path in inputs:
        series, units = read_metric_series(input_path, args.aggregation)
        rows, ignored = calculate_rows(series, units, args.ddof)
        destination = output_path(input_path, args.output_dir)
        write_rows(destination, rows)

        ignored_names = sorted(
            f"{experiment}:{metric}"
            for experiment, metrics in ignored.items()
            for metric in metrics
        )
        ignored_message = (
            f"; ignored all-zero metrics: {', '.join(ignored_names)}"
            if ignored_names
            else ""
        )
        print(f"{input_path} -> {destination} ({len(rows)} pairs){ignored_message}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
