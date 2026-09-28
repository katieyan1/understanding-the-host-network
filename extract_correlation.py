#!/usr/bin/env python3
"""Export one correlation experiment's raw logs to .correlation-data CSVs."""

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
from typing import Iterator, Sequence

from calculate_pairwise_covariance import (
    calculate_rows,
    read_metric_series,
    write_aggregated_correlations,
    write_rows,
)
from mio.stats import StatStore


SAMPLES_NAME = "dependable-metric-samples.csv"
SUMMARY_NAME = "dependable-metric-summary.csv"
METADATA_NAME = "experiment-metadata.csv"
PAIRWISE_NAME = "pairwise-covariance.csv"
HIGH_CORRELATION_NAME = "high-correlation.csv"
ALL_CORRELATIONS_NAME = "all-correlations.csv"
ALL_HIGH_CORRELATIONS_NAME = "all-high-correlations.csv"
FIO_IO_SIZE = 8 * 1024 * 1024
EXPECTED_CPU_SCOPES = {f"CORE{index}" for index in range(32)}


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


@dataclass(frozen=True)
class ExperimentSpec:
    group: str
    experiment: str
    output_subdirectory: str
    workload: str
    workload_configuration: str
    workload_cpus: tuple[str, ...]
    workload_kind: str
    workload_suffix: str
    workload_metrics: tuple[SummaryMetric, ...]


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


EXPERIMENTS = {
    "stream": ExperimentSpec(
        group="stream",
        experiment="correlation-stream-cores1",
        output_subdirectory="stream",
        workload="STREAM Read64",
        workload_configuration="sequential reads; {workload_seconds} seconds",
        workload_cpus=("CORE4",),
        workload_kind="stream",
        workload_suffix=".stream.txt",
        workload_metrics=(
            SummaryMetric("stream_xput", "MB/s", ("CORE4",), "avg"),
        ),
    ),
    "gapbs-pr": ExperimentSpec(
        group="gapbs-pr",
        experiment="correlation-gapbs-pr-cores1",
        output_subdirectory="gapbs-pr",
        workload="GAPBS PageRank",
        workload_configuration="scale-25 graph; 500 trials",
        workload_cpus=("CORE4",),
        workload_kind="gapbs",
        workload_suffix=".gapbs.txt",
        workload_metrics=(
            SummaryMetric("gapbs_time", "seconds", ("ALL",), "avg"),
        ),
    ),
    "gapbs-bc": ExperimentSpec(
        group="gapbs-bc",
        experiment="correlation-gapbs-bc-cores1",
        output_subdirectory="gapbs-bc",
        workload="GAPBS Betweenness Centrality",
        workload_configuration="scale-25 graph; 370 trials",
        workload_cpus=("CORE4",),
        workload_kind="gapbs",
        workload_suffix=".gapbs-bc.txt",
        workload_metrics=(
            SummaryMetric("gapbs_time", "seconds", ("ALL",), "avg"),
        ),
    ),
    "redis-get": ExperimentSpec(
        group="redis-get",
        experiment="correlation-redis-get-cores2",
        output_subdirectory="redis-get",
        workload="Redis GET",
        workload_configuration=(
            "1 server; 1 client; 27 billion requests; 1 KiB values; pipeline 32"
        ),
        workload_cpus=("CORE4", "CORE5"),
        workload_kind="redis",
        workload_suffix=".redis.txt",
        workload_metrics=(
            SummaryMetric("redis_xput", "requests/s", ("CORE4",), "sum"),
        ),
    ),
    "redis-set": ExperimentSpec(
        group="redis-set",
        experiment="correlation-redis-set-cores2",
        output_subdirectory="redis-set",
        workload="Redis SET",
        workload_configuration=(
            "1 server; 1 client; 10.3 billion requests; 1 KiB values; pipeline 32"
        ),
        workload_cpus=("CORE4", "CORE5"),
        workload_kind="redis",
        workload_suffix=".redis.txt",
        workload_metrics=(
            SummaryMetric("redis_xput", "requests/s", ("CORE4",), "sum"),
        ),
    ),
    "fio-randread": ExperimentSpec(
        group="fio-randread",
        experiment="correlation-fio-randread-cores1",
        output_subdirectory="fio-randread",
        workload="fio random read",
        workload_configuration=(
            "1 NVMe; 8 MiB I/O; queue depth 64; {workload_seconds} seconds"
        ),
        workload_cpus=("CORE4",),
        workload_kind="fio",
        workload_suffix=".fio0.txt",
        workload_metrics=(
            SummaryMetric("fio_xput", "Gbit/s", ("SSD0",), "sum"),
            SummaryMetric("io_xput", "GB/s", ("SSD0",), "sum"),
        ),
    ),
    "fio-randwrite": ExperimentSpec(
        group="fio-randwrite",
        experiment="correlation-fio-randwrite-cores1",
        output_subdirectory="fio-randwrite",
        workload="fio random write",
        workload_configuration=(
            "1 NVMe; 8 MiB I/O; queue depth 64; {workload_seconds} seconds"
        ),
        workload_cpus=("CORE4",),
        workload_kind="fio",
        workload_suffix=".fio0.txt",
        workload_metrics=(
            SummaryMetric("fio_xput", "Gbit/s", ("SSD0",), "sum"),
            SummaryMetric("io_xput", "GB/s", ("SSD0",), "sum"),
        ),
    ),
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


def load_fio(store: StatStore, path: Path) -> None:
    """Load fio's reported average IOPS using collect_fio.sh's calculation."""

    average_iops: list[float] = []
    pattern = re.compile(r"^\s*iops\s+:.*?\bavg=\s*([0-9.]+)")
    with path.open(encoding="utf-8") as source:
        for line in source:
            match = pattern.search(line)
            if match:
                average_iops.append(float(match.group(1)))
    if not average_iops:
        raise ValueError(f"{path}: no fio average IOPS result found")

    throughput = math.fsum(average_iops) * FIO_IO_SIZE * 8 / 1e9
    # collect_fio.sh, which the rest of the repository uses, emits awk's
    # default six-significant-digit representation before StatStore loads it.
    store.d["fio_xput"] = {"SSD0": [float(format(throughput, ".6g"))]}
    store.compute_metric("io_xput")


def load_store(raw_dir: Path, spec: ExperimentSpec) -> StatStore:
    base = raw_dir / spec.experiment
    workload_path = Path(f"{base}{spec.workload_suffix}")
    if spec.workload_kind in {"stream", "redis"}:
        workload_path = Path(f"{workload_path}-core4")
    paths = {
        "memory": Path(f"{base}.pcm-memory.txt"),
        "latency": Path(f"{base}.pcm-latency.txt"),
        "cha": Path(f"{base}.pcm-cha2.txt"),
        "imc": Path(f"{base}.pcm-imc.txt"),
        "sar": Path(f"{base}.sar.txt"),
        "workload": workload_path,
    }
    for path in paths.values():
        require_file(path)

    store = StatStore()
    store.load_pcm_mem(paths["memory"])
    store.load_pcm_latency(paths["latency"])
    store.load_pcm_raw(paths["cha"])
    store.load_pcm_raw(paths["imc"])
    store.load_sar(paths["sar"], averages_only=False)

    if spec.workload_kind == "stream":
        store.load_stream(str(base) + spec.workload_suffix)
    elif spec.workload_kind == "gapbs":
        store.load_gapbs(paths["workload"])
    elif spec.workload_kind == "redis":
        store.load_redis(str(base) + spec.workload_suffix)
    elif spec.workload_kind == "fio":
        load_fio(store, paths["workload"])
    else:  # pragma: no cover - all static specifications use a known loader
        raise ValueError(f"unknown workload kind: {spec.workload_kind}")

    for metric in (
        "drd_occupancy",
        "drd_latency",
        "rpq_occupancy",
        "read_activations",
    ):
        store.compute_metric(metric)

    return store


def validate_metric(
    store: StatStore,
    metric: str,
    expected_scopes: set[str],
    expected_samples: int,
) -> None:
    scopes = store.d.get(metric, {})
    actual_scopes = set(scopes)
    if actual_scopes != expected_scopes:
        missing = sorted(expected_scopes - actual_scopes, key=natural_key)
        extra = sorted(actual_scopes - expected_scopes, key=natural_key)
        raise ValueError(f"{metric}: scope mismatch; missing={missing}, extra={extra}")
    for scope, values in scopes.items():
        if len(values) != expected_samples:
            raise ValueError(
                f"{metric}/{scope}: expected {expected_samples} samples, "
                f"found {len(values)}"
            )
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{metric}/{scope}: contains non-finite values")


def validate_store(
    store: StatStore,
    spec: ExperimentSpec,
    config: dict[str, object],
    expected_samples: int,
) -> None:
    channels = set(config["MEM_CHANNELS"])
    chas = set(config["CHAS"])
    core_scopes = EXPECTED_CPU_SCOPES
    for core in spec.workload_cpus:
        if core not in core_scopes:
            raise ValueError(f"l1_miss_latency: workload scope {core} is missing")

    expected_scopes = {
        "memreadbw": channels,
        "memwritebw": channels,
        "l1_miss_latency": core_scopes,
        "drd_occ_agg": chas,
        "drd_inserts": chas,
        "drd_occupancy": chas,
        "drd_latency": chas,
        "rpq_occ_agg": channels,
        "rpq_occupancy": channels,
        "wpq_full_cycles": channels,
        "acts_byp": channels,
        "acts_read": channels,
        "read_activations": channels,
        "cpu_util": core_scopes,
    }
    for metric, scopes in expected_scopes.items():
        validate_metric(store, metric, scopes, expected_samples)

    for metric in spec.workload_metrics:
        scopes = store.d.get(metric.name, {})
        expected_workload_scopes = set(metric.scope_selection)
        if set(scopes) != expected_workload_scopes:
            raise ValueError(
                f"{metric.name}: expected scopes "
                f"{sorted(expected_workload_scopes, key=natural_key)}, found "
                f"{sorted(scopes, key=natural_key)}"
            )
        for scope, values in scopes.items():
            if not values:
                raise ValueError(f"{metric.name}/{scope}: no workload result found")
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"{metric.name}/{scope}: contains non-finite values")


def write_samples(
    store: StatStore, spec: ExperimentSpec, destination: Path
) -> int:
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
                                "experiment": spec.experiment,
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


def mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def write_summary(
    store: StatStore,
    spec: ExperimentSpec,
    config: dict[str, object],
    destination: Path,
) -> int:
    channels = tuple(config["MEM_CHANNELS"])
    chas = tuple(config["CHAS"])
    specs = (
        SummaryMetric("memreadbw", "MB/s", channels, "sum"),
        SummaryMetric("memwritebw", "MB/s", channels, "sum"),
        SummaryMetric("l1_miss_latency", "ns", spec.workload_cpus, "avg"),
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
        SummaryMetric("cpu_util", "percent", spec.workload_cpus, "avg"),
        *spec.workload_metrics,
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
        for metric in specs:
            scope_means = [
                mean(store.d[metric.name][scope])
                for scope in metric.scope_selection
            ]
            value = (
                math.fsum(scope_means)
                if metric.space_aggregation == "sum"
                else mean(scope_means)
            )
            writer.writerow(
                {
                    "experiment": spec.experiment,
                    "metric": metric.name,
                    "scope_selection": ";".join(metric.scope_selection),
                    "space_aggregation": metric.space_aggregation,
                    "time_aggregation": "avg",
                    "scope_count": len(metric.scope_selection),
                    "sample_count": sum(
                        len(store.d[metric.name][scope])
                        for scope in metric.scope_selection
                    ),
                    "value": str(value),
                    "unit": metric.unit,
                }
            )
    return len(specs)


def write_metadata(
    spec: ExperimentSpec,
    config: dict[str, object],
    destination: Path,
    raw_dir: Path,
    sample_count: int,
    sample_interval: int,
    workload_seconds: int,
) -> int:
    workload_configuration = spec.workload_configuration.format(
        workload_seconds=workload_seconds
    )
    workload_cpus = ",".join(core.removeprefix("CORE") for core in spec.workload_cpus)
    rows = (
        ("experiment", spec.experiment),
        ("architecture", str(config["ARCH"])),
        ("workload", spec.workload),
        ("workload_configuration", workload_configuration),
        ("workload_cpus", workload_cpus),
        ("memory_numa_node", "0"),
        ("pcm_warmup_seconds", "10"),
        ("pcm_window_seconds", str(sample_count * sample_interval)),
        ("pcm_samples_per_scope", str(sample_count)),
        ("pcm_sample_interval_seconds", str(sample_interval)),
        ("cpu_util_sampling_seconds", str(sample_count * sample_interval)),
        ("cpu_util_samples_per_scope", str(sample_count)),
        ("cha_frequency_hz", str(config["CHA_FREQ"])),
        ("imc_frequency_hz", str(config["IMC_FREQ"])),
        ("raw_data_directory", str(raw_dir)),
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


def pairwise_has_sample_count(path: Path, expected_samples: int) -> bool:
    if not path.is_file():
        return False
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if "sample_count" not in (reader.fieldnames or ()):
            return False
        rows = list(reader)
    return bool(rows) and all(
        row["sample_count"].strip() == str(expected_samples) for row in rows
    )


def write_aggregate_csvs(
    data_dir: Path, expected_samples: int
) -> tuple[int, int] | None:
    pairwise_paths = [
        data_dir / spec.output_subdirectory / PAIRWISE_NAME
        for spec in EXPERIMENTS.values()
    ]
    high_paths = [
        data_dir / spec.output_subdirectory / HIGH_CORRELATION_NAME
        for spec in EXPERIMENTS.values()
    ]
    if not all(
        pairwise_has_sample_count(path, expected_samples)
        for path in pairwise_paths
    ) or not all(path.is_file() for path in high_paths):
        return None

    pair_count, _experiments = write_aggregated_correlations(
        pairwise_paths, data_dir / ALL_CORRELATIONS_NAME
    )
    high_pair_count, _experiments = write_aggregated_correlations(
        high_paths, data_dir / ALL_HIGH_CORRELATIONS_NAME
    )
    return pair_count, high_pair_count


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=tuple(EXPERIMENTS))
    parser.add_argument("--raw-dir", type=Path, default=Path(".experiment-data"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="destination directory (default: .correlation-data/<group>)",
    )
    parser.add_argument("--expected-samples", type=int, default=4500)
    parser.add_argument("--sample-interval", type=int, default=1)
    parser.add_argument("--workload-seconds", type=int, default=18030)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.expected_samples <= 1:
        raise SystemExit("--expected-samples must be greater than one")
    if args.sample_interval <= 0 or args.workload_seconds <= 0:
        raise SystemExit("sample interval and workload duration must be positive")

    spec = EXPERIMENTS[args.group]
    output_dir = args.output_dir or Path(".correlation-data") / spec.output_subdirectory
    config_path = Path(__file__).resolve().parent / "config.json"
    with config_path.open(encoding="utf-8") as source:
        config = json.load(source)

    store = load_store(args.raw_dir, spec)
    validate_store(store, spec, config, args.expected_samples)

    samples_path = output_dir / SAMPLES_NAME
    sample_rows = write_samples(store, spec, samples_path)
    summary_rows = write_summary(store, spec, config, output_dir / SUMMARY_NAME)
    metadata_rows = write_metadata(
        spec,
        config,
        output_dir / METADATA_NAME,
        args.raw_dir,
        args.expected_samples,
        args.sample_interval,
        args.workload_seconds,
    )
    pair_rows, high_rows = write_correlations(samples_path, output_dir)
    aggregate_counts = write_aggregate_csvs(output_dir.parent, args.expected_samples)

    print(f"{samples_path}: {sample_rows} sample rows")
    print(f"{output_dir / SUMMARY_NAME}: {summary_rows} summary rows")
    print(f"{output_dir / METADATA_NAME}: {metadata_rows} metadata rows")
    print(f"{output_dir / PAIRWISE_NAME}: {pair_rows} metric pairs")
    print(f"{output_dir / HIGH_CORRELATION_NAME}: {high_rows} high-correlation pairs")
    if aggregate_counts is None:
        print(
            "aggregate CSVs not refreshed: waiting for all seven groups to "
            f"contain {args.expected_samples}-sample pairwise results"
        )
    else:
        pair_count, high_pair_count = aggregate_counts
        print(f"{output_dir.parent / ALL_CORRELATIONS_NAME}: {pair_count} metric pairs")
        print(
            f"{output_dir.parent / ALL_HIGH_CORRELATIONS_NAME}: "
            f"{high_pair_count} high-correlation metric pairs"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
