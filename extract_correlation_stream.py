#!/usr/bin/env python3
"""Export STREAM correlation logs as the CSVs in .correlation-data/stream."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from calculate_pairwise_covariance import (
    calculate_rows,
    read_metric_series,
    write_rows,
)
from mio.stats import StatStore


EXPERIMENT = "correlation-stream-cores1"
SAMPLES_NAME = "dependable-metric-samples.csv"
SUMMARY_NAME = "dependable-metric-summary.csv"
METADATA_NAME = "experiment-metadata.csv"
PAIRWISE_NAME = "pairwise-covariance.csv"
HIGH_CORRELATION_NAME = "high-correlation.csv"


@dataclass(frozen=True)
class Metric:
    name: str
    unit: str


@dataclass(frozen=True)
class SummaryMetric:
    name: str
    unit: str
    scope_selection: tuple[str, ...]
    space_aggregation: str


WINDOWS = {
    "pcm_memory": (
        Metric("memreadbw", "MB/s"),
        Metric("memwritebw", "MB/s"),
    ),
    "pcm_latency": (Metric("l1_miss_latency", "ns"),),
    "pcm_cha": (
        Metric("drd_occ_agg", "occupancy_cycles"),
        Metric("drd_inserts", "transactions"),
        Metric("drd_occupancy", "request_seconds"),
        Metric("drd_latency", "ns"),
    ),
    "pcm_imc": (
        Metric("rpq_occ_agg", "occupancy_cycles"),
        Metric("rpq_occupancy", "queue_entry_seconds"),
        Metric("wpq_full_cycles", "cycles"),
        Metric("acts_byp", "events"),
        Metric("acts_read", "events"),
        Metric("read_activations", "events"),
    ),
    "sar_concurrent": (Metric("cpu_util", "percent"),),
}


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", value)
    )


@contextmanager
def atomic_csv(path: Path, fieldnames: list[str]) -> Iterator[csv.DictWriter]:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            writer = csv.DictWriter(
                destination, fieldnames=fieldnames, lineterminator="\n"
            )
            writer.writeheader()
            yield writer
        os.replace(temporary_name, path)
    except BaseException:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"required raw log is missing: {path}")


def load_store(raw_dir: Path) -> StatStore:
    paths = {
        "memory": raw_dir / f"{EXPERIMENT}.pcm-memory.txt",
        "latency": raw_dir / f"{EXPERIMENT}.pcm-latency.txt",
        "cha": raw_dir / f"{EXPERIMENT}.pcm-cha2.txt",
        "imc": raw_dir / f"{EXPERIMENT}.pcm-imc.txt",
        "sar": raw_dir / f"{EXPERIMENT}.sar.txt",
        "stream": raw_dir / f"{EXPERIMENT}.stream.txt-core4",
    }
    for path in paths.values():
        require_file(path)

    store = StatStore()
    store.load_pcm_mem(paths["memory"])
    store.load_pcm_latency(paths["latency"])
    store.load_pcm_raw(paths["cha"])
    store.load_pcm_raw(paths["imc"])
    store.load_sar(paths["sar"], averages_only=False)
    store.load_stream(str(raw_dir / f"{EXPERIMENT}.stream.txt"))

    for metric in (
        "drd_occupancy",
        "drd_latency",
        "rpq_occupancy",
        "read_activations",
    ):
        store.compute_metric(metric)

    return store


def validate_store(store: StatStore, expected_samples: int) -> None:
    expected_scopes = {
        "memreadbw": 8,
        "memwritebw": 8,
        "l1_miss_latency": 32,
        "drd_occ_agg": 16,
        "drd_inserts": 16,
        "drd_occupancy": 16,
        "drd_latency": 16,
        "rpq_occ_agg": 8,
        "rpq_occupancy": 8,
        "wpq_full_cycles": 8,
        "acts_byp": 8,
        "acts_read": 8,
        "read_activations": 8,
        "cpu_util": 32,
    }

    for metric, scope_count in expected_scopes.items():
        scopes = store.d.get(metric, {})
        if len(scopes) != scope_count:
            raise ValueError(
                f"{metric}: expected {scope_count} scopes, found {len(scopes)}"
            )
        for scope, values in scopes.items():
            if len(values) != expected_samples:
                raise ValueError(
                    f"{metric}/{scope}: expected {expected_samples} samples, "
                    f"found {len(values)}"
                )
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"{metric}/{scope}: contains non-finite values")

    stream_values = store.d.get("stream_xput", {}).get("CORE4", [])
    if len(stream_values) != 1 or not math.isfinite(stream_values[0]):
        raise ValueError("stream_xput/CORE4: expected exactly one finite value")


def write_samples(store: StatStore, destination: Path) -> int:
    fieldnames = [
        "experiment",
        "collection_window",
        "metric",
        "scope",
        "sample_index",
        "value",
        "unit",
    ]
    row_count = 0
    with atomic_csv(destination, fieldnames) as writer:
        for window, metrics in WINDOWS.items():
            for metric in metrics:
                for scope in sorted(store.d[metric.name], key=natural_key):
                    for sample_index, value in enumerate(store.d[metric.name][scope]):
                        writer.writerow(
                            {
                                "experiment": EXPERIMENT,
                                "collection_window": window,
                                "metric": metric.name,
                                "scope": scope,
                                "sample_index": sample_index,
                                "value": str(value),
                                "unit": metric.unit,
                            }
                        )
                        row_count += 1
    return row_count


def mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def write_summary(store: StatStore, destination: Path) -> int:
    channels = tuple(f"SKT0CHAN{i}" for i in range(8))
    chas = tuple(f"SKT0C{i}" for i in range(16))
    specs = (
        SummaryMetric("memreadbw", "MB/s", channels, "sum"),
        SummaryMetric("memwritebw", "MB/s", channels, "sum"),
        SummaryMetric("l1_miss_latency", "ns", ("CORE4",), "avg"),
        SummaryMetric("drd_occ_agg", "occupancy_cycles", chas, "sum"),
        SummaryMetric("drd_inserts", "transactions", chas, "sum"),
        SummaryMetric("drd_occupancy", "request_seconds", chas, "sum"),
        SummaryMetric("drd_latency", "ns", chas, "avg"),
        SummaryMetric("rpq_occ_agg", "occupancy_cycles", channels, "sum"),
        SummaryMetric("rpq_occupancy", "queue_entry_seconds", channels, "avg"),
        SummaryMetric("wpq_full_cycles", "cycles", channels, "sum"),
        SummaryMetric("acts_byp", "events", channels, "sum"),
        SummaryMetric("acts_read", "events", channels, "sum"),
        SummaryMetric("read_activations", "events", channels, "sum"),
        SummaryMetric("cpu_util", "percent", ("CORE4",), "avg"),
        SummaryMetric("stream_xput", "MB/s", ("CORE4",), "avg"),
    )
    fieldnames = [
        "experiment",
        "metric",
        "scope_selection",
        "space_aggregation",
        "time_aggregation",
        "scope_count",
        "sample_count",
        "value",
        "unit",
    ]

    with atomic_csv(destination, fieldnames) as writer:
        for spec in specs:
            scope_means = [mean(store.d[spec.name][scope]) for scope in spec.scope_selection]
            if spec.space_aggregation == "sum":
                value = math.fsum(scope_means)
            else:
                value = mean(scope_means)
            writer.writerow(
                {
                    "experiment": EXPERIMENT,
                    "metric": spec.name,
                    "scope_selection": ";".join(spec.scope_selection),
                    "space_aggregation": spec.space_aggregation,
                    "time_aggregation": "avg",
                    "scope_count": len(spec.scope_selection),
                    "sample_count": sum(
                        len(store.d[spec.name][scope]) for scope in spec.scope_selection
                    ),
                    "value": str(value),
                    "unit": spec.unit,
                }
            )
    return len(specs)


def write_metadata(
    destination: Path,
    sample_count: int,
    sample_interval: int,
    workload_seconds: int,
) -> int:
    config_path = Path(__file__).resolve().parent / "config.json"
    with config_path.open(encoding="utf-8") as source:
        config = json.load(source)

    rows = (
        ("experiment", EXPERIMENT),
        ("architecture", config["ARCH"]),
        ("workload", "STREAM Read64"),
        ("workload_configuration", f"sequential reads; {workload_seconds} seconds"),
        ("workload_cpus", "4"),
        ("memory_numa_node", "0"),
        ("pcm_warmup_seconds", "10"),
        ("pcm_window_seconds", str(sample_count * sample_interval)),
        ("pcm_samples_per_scope", str(sample_count)),
        ("pcm_sample_interval_seconds", str(sample_interval)),
        ("cpu_util_sampling_seconds", str(sample_count * sample_interval)),
        ("cpu_util_samples_per_scope", str(sample_count)),
        ("cha_frequency_hz", str(config["CHA_FREQ"])),
        ("imc_frequency_hz", str(config["IMC_FREQ"])),
        ("raw_data_directory", ".experiment-data"),
    )
    with atomic_csv(destination, ["key", "value"]) as writer:
        for key, value in rows:
            writer.writerow({"key": key, "value": value})
    return len(rows)


def write_correlations(samples_path: Path, output_dir: Path) -> tuple[int, int]:
    series, units = read_metric_series(samples_path, "sum")
    rows, _ignored = calculate_rows(series, units, ddof=1)
    write_rows(output_dir / PAIRWISE_NAME, rows)
    high_rows = [
        row
        for row in rows
        if row.correlation is not None and abs(row.correlation) >= 0.6
    ]
    write_rows(output_dir / HIGH_CORRELATION_NAME, high_rows)
    return len(rows), len(high_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path(".experiment-data"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".correlation-data/stream")
    )
    parser.add_argument("--expected-samples", type=int, default=4500)
    parser.add_argument("--sample-interval", type=int, default=1)
    parser.add_argument("--workload-seconds", type=int, default=18030)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.expected_samples <= 1:
        raise SystemExit("--expected-samples must be greater than one")
    if args.sample_interval <= 0 or args.workload_seconds <= 0:
        raise SystemExit("sample interval and workload duration must be positive")

    store = load_store(args.raw_dir)
    validate_store(store, args.expected_samples)

    samples_path = args.output_dir / SAMPLES_NAME
    sample_rows = write_samples(store, samples_path)
    summary_rows = write_summary(store, args.output_dir / SUMMARY_NAME)
    metadata_rows = write_metadata(
        args.output_dir / METADATA_NAME,
        args.expected_samples,
        args.sample_interval,
        args.workload_seconds,
    )
    pair_rows, high_rows = write_correlations(samples_path, args.output_dir)

    print(f"{samples_path}: {sample_rows} sample rows")
    print(f"{args.output_dir / SUMMARY_NAME}: {summary_rows} summary rows")
    print(f"{args.output_dir / METADATA_NAME}: {metadata_rows} metadata rows")
    print(f"{args.output_dir / PAIRWISE_NAME}: {pair_rows} metric pairs")
    print(f"{args.output_dir / HIGH_CORRELATION_NAME}: {high_rows} high-correlation pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
