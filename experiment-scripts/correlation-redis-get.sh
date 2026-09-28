#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_common.bash"

prepare_experiment

label=correlation-redis-get
run_mio_with_sar "$label" 2 \
    python3 -m mio "$label" \
    --ant redis --ant_cpus 4,5 --ant_num_cores 2 --ant_mem_numa 0 \
    --ant_writefrac 0 --ant_num_requests 27000000000 \
    --ant_duration "$WORKLOAD_DURATION" \
    --stats --stats_samples "$PCM_SAMPLES" --stats_gran "$PCM_GRANULARITY"

export_correlation_csvs redis-get
