# Host reproduction record

This document records the software installs, repository changes, and host-level
settings used for the single-host Ice Lake experiments in this checkout. It is
written as a handoff to another Codex session preparing a comparable bare-metal
host.

The recorded repository state before this document was added is commit
`9d2ae09ae049c9f0b3a3a15f5ac3ca0544a86a95` on `master`. The Ice Lake runner
changes are in `c722636`, raw experiment data and analysis are in `fad4a36`, and
figures are in `9d2ae09`. The dependency source trees under `.deps/` are local
build products and are intentionally ignored by Git.

## 1. Reference host

The measurements in `.experiment-data/` came from this machine:

| Item | Recorded value |
|---|---|
| OS | Ubuntu 22.04.2 LTS (Jammy) |
| Kernel | `5.15.0-187-generic` x86-64 |
| CPU | Intel Xeon Silver 4314, family 6, model 106, stepping 6 (Ice Lake-SP) |
| Topology | 1 socket, 16 physical cores, 2 threads/core, 32 logical CPUs |
| CPU allocation | NUMA node 0 contains CPUs 0-31; experiments use CPUs 0-15, one hardware thread per core |
| Memory | 128415 MiB, 1 NUMA node, 8 DDR4 channels, DDR4-2666 |
| CPU/CHA frequency used by analysis | 2.4 GHz (`CHA_FREQ=2400000000`) |
| IMC frequency used by analysis | 1.333 GHz (`IMC_FREQ=1333000000`, half the DDR4-2666 transfer rate) |
| Data devices | Four raw, unmounted 894.3 GB Samsung MZQL2960HCJR-00A07 NVMe drives |
| OS device | Intel SSDSC2KG960G8 SATA SSD (`/dev/sda`) |
| Uncore topology reported by PCM | 8 memory channels, 16 CHAs, 6 IRP/IIO units |

The raw NVMe identifiers were:

| Path | Serial |
|---|---|
| `/dev/nvme0n1` | `S64FNE0RA02709` |
| `/dev/nvme1n1` | `S64FNE0RA01905` |
| `/dev/nvme2n1` | `S64FNE0RA02002` |
| `/dev/nvme3n1` | `S64FNE0RA02879` |

These device names and CPU numbers are host-specific. Discover them again on a
replacement host. Do not copy them merely because the replacement has the same
CPU model.

## 2. Install the operating-system packages

Run on Ubuntu 22.04:

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential cmake pkg-config git numactl libnuma-dev \
  msr-tools sysstat fio redis-server redis-tools \
  perftest rdma-core ibverbs-utils \
  libpci-dev libevent-dev autoconf automake libpcre3-dev \
  zlib1g-dev libssl-dev python3-scipy
```

The installed package snapshot on the reference host was:

| Package | Version |
|---|---|
| `autoconf` | `2.71-2` |
| `automake` | `1:1.16.5-1.3` |
| `build-essential` | `12.9ubuntu3` |
| `cmake` | `3.22.1-1ubuntu1.22.04.2` |
| `fio` | `3.28-1` |
| `git` | `1:2.34.1-1ubuntu1.17` |
| `ibverbs-utils` | `39.0-1` |
| `libevent-dev` | `2.1.12-stable-1ubuntu0.1` |
| `libnuma-dev` | `2.0.14-3ubuntu2` |
| `libpci-dev` | `1:3.7.0-6` |
| `libpcre3-dev` | `2:8.39-13ubuntu0.22.04.1` |
| `libssl-dev` | `3.0.2-0ubuntu1.29` |
| `msr-tools` | `1.3-4` |
| `numactl` | `2.0.14-3ubuntu2` |
| `perftest` | `4.4+0.37-1` |
| `pkg-config` | `0.29.2-1ubuntu3` |
| `python3-scipy` | `1.8.0-1exp2ubuntu1` |
| `rdma-core` | `39.0-1` |
| `redis-server`, `redis-tools` | `5:6.0.16-1ubuntu1.1` |
| `sysstat` | `12.5.2-2ubuntu0.2` |
| `zlib1g-dev` | `1:1.2.11.dfsg-2ubuntu9.2` |

The exact apt versions are a provenance record, not an instruction to force old
packages from an arbitrary mirror. Start with the distribution versions above;
pin or archive packages only if bit-for-bit software reconstruction is required.

Package installation starts the distribution Redis service on Ubuntu. The
experiment runner creates its own CPU-pinned Redis instances over Unix sockets,
so stop and persistently disable the package service:

```bash
sudo systemctl disable --now redis-server
systemctl is-enabled redis-server || true
systemctl is-active redis-server || true
```

The expected states are `disabled` and `inactive`.

## 3. Check out and build the software

Use HTTPS if the replacement host does not have this account's SSH key:

```bash
git clone https://github.com/katieyan1/understanding-the-host-network.git
cd understanding-the-host-network
git checkout 9d2ae09ae049c9f0b3a3a15f5ac3ca0544a86a95
mkdir -p .deps .experiment-data
```

Build the three external source dependencies at the exact revisions used on the
reference host:

```bash
git clone https://github.com/intel/pcm.git .deps/pcm
git -C .deps/pcm checkout 9b3e4a1688869a8a88f0ea17d0be1c5283f0b3bb
cmake -S .deps/pcm -B .deps/pcm/build -DCMAKE_BUILD_TYPE=Release
cmake --build .deps/pcm/build -j "$(nproc)"

git clone https://github.com/redis/memtier_benchmark.git .deps/memtier_benchmark
git -C .deps/memtier_benchmark checkout d5ac1f4167e01f0b76b0ea095640747ec3670c1d
(
  cd .deps/memtier_benchmark
  autoreconf -ivf
  ./configure
  make -j "$(nproc)"
)

git clone https://github.com/sbeamer/gapbs.git .deps/gapbs
git -C .deps/gapbs checkout 2972aeb2703165bafd921222f4ed7196f542d3a8
make -C .deps/gapbs -j "$(nproc)" pr bc

make -C stream -j "$(nproc)"
```

The revisions correspond to Intel PCM tag `202403`, memtier_benchmark tag
`2.0.0`, and GAPBS `v1.5-1-g2972aeb`. STREAM* is part of this repository and
uses AVX-512; confirm `avx512f` exists before running it.

Expected executables are:

```text
.deps/pcm/build/bin/pcm-memory
.deps/pcm/build/bin/pcm-latency
.deps/pcm/build/bin/pcm-raw
.deps/memtier_benchmark/memtier_benchmark
.deps/gapbs/pr
.deps/gapbs/bc
stream/stream
```

MLC and `mmapbench` were not installed or configured for this host. They are not
needed for the recorded Redis, GAPBS, STREAM core-scaling, or STREAM+fio runs.

## 4. Discover the replacement host before editing `config.json`

Collect a host inventory:

```bash
lscpu
lscpu -e=CPU,CORE,SOCKET,NODE,ONLINE
numactl --hardware
lsblk -d -o NAME,MODEL,SERIAL,SIZE,TYPE,ROTA,MOUNTPOINTS
sudo dmidecode --type memory
sudo rdma link
ibv_devices
```

Select one logical CPU from each physical core for `NUMA_CORES`. On the
reference host CPUs 0-15 were the first threads and CPUs 16-31 were their SMT
siblings. Verify the `CORE` column instead of assuming every host uses this
numbering.

Load the MSR module, then use PCM to discover the uncore names visible on the
new CPU:

```bash
sudo modprobe msr
sudo timeout 4 .deps/pcm/build/bin/pcm-memory 1 -csv
sudo timeout 4 .deps/pcm/build/bin/pcm-raw 1 \
  -e imc/config=0x400080,name=rpq_occ_agg -f
```

On the reference Ice Lake host PCM exposed `SKT0CHAN0` through `SKT0CHAN7`,
`SKT0C0` through `SKT0C15`, and `SKT0IRP0` through `SKT0IRP5`. The replacement
must use the names PCM actually prints.

Before adding a block device to `SSDS`, confirm that it is the intended
experiment drive, is unmounted, and does not contain data that must be kept.
The recorded fio workloads are read-only (`--fio_writefrac 0`), but other mio
options can write directly to these raw devices.

## 5. Configure this checkout

`config.json` is intentionally a concrete host profile. On a replacement host,
update every absolute path and all hardware-derived fields. The reference file
contains:

```json
{
    "ARCH": "icelake",
    "PCM_PATH": "/users/katieyan/understanding-the-host-network/.deps/pcm/build/bin",
    "STATS_PATH": "/users/katieyan/understanding-the-host-network/.experiment-data",
    "FIO_PATH": "/usr/bin",
    "STREAM_PATH": "/users/katieyan/understanding-the-host-network/stream",
    "REDIS_PATH": "/usr/bin",
    "MEMTIER_PATH": "/users/katieyan/understanding-the-host-network/.deps/memtier_benchmark",
    "GAPBS_PATH": "/users/katieyan/understanding-the-host-network/.deps/gapbs",
    "NUMA_CORES": ["0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15"],
    "NUMA_ORDER": "0",
    "SSDS": ["/dev/nvme0n1", "/dev/nvme1n1", "/dev/nvme2n1", "/dev/nvme3n1"],
    "MEM_CHANNELS": ["SKT0CHAN0", "SKT0CHAN1", "SKT0CHAN2", "SKT0CHAN3", "SKT0CHAN4", "SKT0CHAN5", "SKT0CHAN6", "SKT0CHAN7"],
    "CHAS": ["SKT0C0", "SKT0C1", "SKT0C2", "SKT0C3", "SKT0C4", "SKT0C5", "SKT0C6", "SKT0C7", "SKT0C8", "SKT0C9", "SKT0C10", "SKT0C11", "SKT0C12", "SKT0C13", "SKT0C14", "SKT0C15"],
    "IRPS": ["SKT0IRP0", "SKT0IRP1", "SKT0IRP2", "SKT0IRP3", "SKT0IRP4", "SKT0IRP5"],
    "CHA_FREQ": 2400000000,
    "IMC_FREQ": 1333000000
}
```

`ARCH=icelake` selects the validated Ice Lake counter path. The code also keeps
a Cascade Lake path. Treat any other architecture as unsupported until its PCM
events are validated. The analytical models in `collect_stats.py` are calibrated
for Cascade Lake and intentionally reject Ice Lake data.

## 6. Apply the runtime host settings

Run these steps after every reboot and before collecting comparable data:

```bash
sudo modprobe msr
sudo ./disable-scaling.sh
```

`disable-scaling.sh` writes `performance` to every available
`/sys/devices/system/cpu/cpufreq/policy*/scaling_governor` and writes `1` to
`/sys/devices/system/cpu/intel_pstate/no_turbo`. On the reference host there
were 32 policy directories. Both the MSR module load and these sysfs settings
are volatile across reboot.

Verify them with:

```bash
lsmod | grep '^msr '
cat /sys/devices/system/cpu/intel_pstate/no_turbo
awk '{print FILENAME ":" $0}' \
  /sys/devices/system/cpu/cpufreq/policy*/scaling_governor
```

Expected values are `no_turbo=1` and `performance` for every policy.

The mio runner also writes MSR `0x1a4` on all CPUs at the beginning of each
measurement unless `--notouch_prefetch` is supplied:

| Runner option | Write performed |
|---|---|
| default | `wrmsr -a 0x1a4 0` (enable prefetchers) |
| `--disable_prefetch` | first `0`, then `15` (disable all four controlled prefetchers) |
| `--disable_prefetch_l1` | first `0`, then `12` (disable the two L1 prefetchers) |

This setting is not restored at process exit. The final recorded Redis run used
the default behavior, so the intended final state is `0`. Read it with
`sudo rdmsr -a 0x1a4`; restore it with `sudo wrmsr -a 0x1a4 0`.

The following state was observed but deliberately left unchanged:

- DDIO remained enabled. The repository's DDIO control method is specific to
  Cascade Lake and was not applied to Ice Lake.
- Transparent huge pages remained `always [madvise] never`.
- `vm.overcommit_memory` remained `0`. Redis prints a warning, but persistence
  is disabled and this setting was not changed.
- The raw NVMe drives were not partitioned, formatted, or mounted.
- No BIOS, firmware, bootloader, or persistent kernel-command-line settings
  were changed.
- No 1 GiB huge pages or memory cgroups were configured because the executed
  workloads did not request them.

## 7. Validate the installation

Run the static checks:

```bash
python3 -m json.tool config.json >/dev/null
python3 -m compileall -q collect_stats.py mio
python3 -m mio --help >/dev/null
bash -n collect_fio.sh disable-scaling.sh
git diff --check
test -x stream/stream
test -x .deps/pcm/build/bin/pcm-memory
test -x .deps/memtier_benchmark/memtier_benchmark
test -x .deps/gapbs/pr
test -x .deps/gapbs/bc
```

Then perform short, isolated smoke tests. Keep fio read-only:

```bash
numactl --membind 0 --physcpubind 4 stream/stream Read64 8
numactl --membind 0 --physcpubind 4 .deps/gapbs/pr -g 10 -n 1
redis-server --version
.deps/memtier_benchmark/memtier_benchmark --version
fio --name=read-smoke --filename=/dev/nvme0n1 --readonly=1 \
  --rw=randread --direct=1 --ioengine=libaio --bs=8M \
  --iodepth=1 --numjobs=1 --runtime=5 --time_based=1
```

Validate the Ice Lake local-memory demand-read CHA events while STREAM is
active:

```bash
sudo bash -c '
  numactl --membind 0 --physcpubind 4 stream/stream Read64 8 \
    >/tmp/icl-cha-stream.log &
  workload_pid=$!
  timeout 6 .deps/pcm/build/bin/pcm-raw 1 \
    -e cha/config=0x00c8168600400136,name=drd_occ_agg \
    -e cha/config=0x00c8168600400135,name=drd_inserts -f
  wait "$workload_pid"
'
```

All present CHAs produced nonzero insert counts on the reference host. These
Ice Lake encodings must not be treated as Cascade Lake C2M/P2M filter encodings.

For RDMA visibility, the reference host had ConnectX-6 devices `mlx5_0` through
`mlx5_3`; `mlx5_2` on `ens1f0np0` was the active port during inspection. RDMA
benchmarking was not part of the recorded single-host experiment set and needs
a configured peer before perftest can be used.

## 8. Repository modifications already included in the checkout

Commit `c722636` contains the host-enablement changes. A fresh checkout of the
recorded repository state already has them; do not reapply them manually.

- `.gitignore` ignores local `.deps/` builds. Experiment data was later made
  tracked in commit `9d2ae09`.
- `config.json` was replaced with the reference Ice Lake host profile above.
- `mio/env.py` gained the `ARCH` setting and stopped trying to load `msr` as an
  import-time side effect. MSR loading is now an explicit privileged setup step.
- `mio/app.py` selects architecture-specific PCM events. Ice Lake records the
  validated local-memory DRd occupancy/insert pair and IMC occupancy; it omits
  Cascade Lake-only CHA, memory-mode, CAS, precharge, and IRP event groups.
- `mio/app.py` removes prior output files safely and kills child processes by
  exact executable name. This fixed the old `pkill -f stream` behavior that
  could kill the parent mio command and produce exit status 137.
- `mio/stats.py` resolves paths from the repository root, uses configured IMC
  frequency, handles zero CHA inserts as NaN, passes the stats directory to the
  fio collector, and parses the Redis 6 `requests per second` output format.
- `collect_fio.sh` now takes the stats directory as argument 4 instead of using
  a developer-specific path.
- `collect_stats.py` reads `STATS_PATH` from `config.json`, serializes the default
  SSD filter correctly, and rejects the Cascade Lake analytical model on other
  architectures.
- `disable-scaling.sh` now sets all cpufreq policies instead of policy 0 only.

## 9. Run the recorded experiments and find their outputs

The exact commands for STREAM core scaling, colocated STREAM+fio, isolated fio,
GAPBS PageRank scaling, and Redis GET scaling are in
`.experiment-data/run-manifest.md`. Run them from the repository root with
`sudo`; their first positional argument is the output label.

The raw measurements, normalized CSV tables, plots, and interpretation are
already tracked under `.experiment-data/`. In particular:

- `.experiment-data/run-manifest.md` records the commands and workload caveats.
- `.experiment-data/analysis.md` explains the results and known limits.
- `.experiment-data/analysis-summary.csv` is the combined summary table.
- `.experiment-data/figures/` contains the generated figures.

Redis ignores `--ant_duration` in the current implementation and instead runs
50 million requests per server. The recorded fio commands use
`--fio_writefrac 0`, selecting `randread`; no NVMe writes were issued.

## 10. Completion checklist for another Codex session

Before declaring a replacement host ready:

1. Record OS, kernel, CPU model, sockets, SMT topology, NUMA layout, DIMM speed,
   and disk serial numbers.
2. Install the apt packages and disable the distribution Redis service.
3. Check out the recorded repository commit and build every pinned dependency.
4. Rewrite all absolute paths and hardware fields in `config.json`.
5. Confirm experiment CPUs represent distinct physical cores and do not overlap
   fio CPUs unless the experiment calls for overlap.
6. Confirm every configured raw SSD is the intended disposable experiment
   device and is unmounted.
7. Load `msr`, set all governors to `performance`, and disable turbo.
8. Validate PCM memory-channel, CHA, and IRP names on that exact CPU.
9. Run the read-only smoke tests and the Ice Lake CHA counter test.
10. Record any departure from this hardware, package set, source revision,
    frequency assumption, or runtime setting alongside the new results.
