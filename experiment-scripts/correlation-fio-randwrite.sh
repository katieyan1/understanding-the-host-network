#!/usr/bin/env bash
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/_common.bash"

prepare_experiment
require_raw_write_opt_in

label=correlation-fio-randwrite
run_mio_with_sar "$label" 1 \
    python3 -m mio "$label" \
    --fio --fio_mem_numa 0 --fio_cpus 4 --fio_writefrac 100 \
    --fio_iosize 8388608 --fio_iodepth 64 --fio_num_ssds 1 \
    --fio_duration "$WORKLOAD_DURATION" \
    --stats --stats_samples "$PCM_SAMPLES" --stats_gran "$PCM_GRANULARITY"

export_correlation_csvs fio-randwrite
