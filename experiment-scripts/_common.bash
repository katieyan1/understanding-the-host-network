#!/usr/bin/env bash

# Shared support for the seven correlation experiment scripts. This file is
# sourced; run one of the correlation-*.sh entry points instead.

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
EXPECTED_STATS_DIR="$REPO_ROOT/.experiment-data"
PCM_SAMPLES=4500
PCM_GRANULARITY=1
PCM_GROUPS=4
PCM_WARMUP_SECONDS=10
WORKLOAD_DURATION=$((
    PCM_WARMUP_SECONDS + PCM_SAMPLES * PCM_GROUPS + 20
))

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

prepare_experiment() {
    cd -- "$REPO_ROOT"

    if [[ ${DRY_RUN:-0} != 1 && $EUID -ne 0 ]]; then
        die "run this script with sudo (or use DRY_RUN=1 to inspect it)"
    fi

    python3 -m json.tool config.json >/dev/null

    local configured_stats_dir
    configured_stats_dir=$(
        python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["STATS_PATH"])' \
            "$REPO_ROOT/config.json"
    )
    configured_stats_dir=$(realpath -m -- "$configured_stats_dir")

    [[ $configured_stats_dir == "$EXPECTED_STATS_DIR" ]] ||
        die "config.json STATS_PATH must resolve to $EXPECTED_STATS_DIR (got $configured_stats_dir)"
    [[ -d $EXPECTED_STATS_DIR ]] || die "$EXPECTED_STATS_DIR does not exist"
}

guard_existing_outputs() {
    local label=$1
    local cores=$2
    local -a existing=()

    shopt -s nullglob
    existing=("$EXPECTED_STATS_DIR/${label}-cores${cores}."*)
    shopt -u nullglob

    if (( ${#existing[@]} > 0 )) &&
        [[ ${DRY_RUN:-0} != 1 ]] &&
        [[ ${OVERWRITE_EXPERIMENT_DATA:-0} != 1 ]]; then
        die "outputs for $label already exist; set OVERWRITE_EXPERIMENT_DATA=1 to replace them"
    fi
}

first_configured_ssd() {
    python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["SSDS"][0])' \
        "$REPO_ROOT/config.json"
}

require_unmounted_first_ssd() {
    local device
    device=$(first_configured_ssd)

    [[ ${DRY_RUN:-0} == 1 ]] && return 0

    [[ -b $device ]] || die "$device is not a block device"
    if lsblk -nrpo MOUNTPOINT "$device" | grep -q '[^[:space:]]'; then
        die "$device or one of its children is mounted"
    fi
}

require_raw_write_opt_in() {
    local device
    device=$(first_configured_ssd)

    [[ ${DRY_RUN:-0} == 1 ]] && return 0

    require_unmounted_first_ssd
    [[ ${ALLOW_RAW_NVME_WRITE:-} == "$device" ]] ||
        die "raw writes require ALLOW_RAW_NVME_WRITE=$device"
    [[ -z $(wipefs -n "$device") ]] ||
        die "$device has a filesystem or partition signature; refusing raw writes"
}

run_mio_with_sar() {
    local label=$1
    local cores=$2
    shift 2

    guard_existing_outputs "$label" "$cores"

    local sar_output="$EXPECTED_STATS_DIR/${label}-cores${cores}.sar.txt"

    if [[ ${DRY_RUN:-0} == 1 ]]; then
        printf 'sar -u 1 %q -P ALL > %q &\n' "$PCM_SAMPLES" "$sar_output"
        printf '%q ' "$@"
        printf '\n'
        return 0
    fi

    local sar_pid=
    cleanup_sar() {
        if [[ -n $sar_pid ]] && kill -0 "$sar_pid" 2>/dev/null; then
            kill "$sar_pid" 2>/dev/null || true
            wait "$sar_pid" 2>/dev/null || true
        fi
    }
    trap cleanup_sar EXIT INT TERM

    sar -u 1 "$PCM_SAMPLES" -P ALL >"$sar_output" &
    sar_pid=$!

    "$@"
    wait "$sar_pid"
    sar_pid=
    trap - EXIT INT TERM
}
