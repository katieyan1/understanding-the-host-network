#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_common.bash"

prepare_experiment

label=correlation-stream
run_mio_with_sar "$label" 1 \
    python3 -m mio "$label" \
    --ant stream --ant_cpus 4 --ant_num_cores 1 --ant_mem_numa 0 \
    --ant_inst_size 64 --ant_writefrac 0 --ant_duration "$WORKLOAD_DURATION" \
    --stats --stats_samples "$PCM_SAMPLES" --stats_gran "$PCM_GRANULARITY"

export_correlation_csvs stream
