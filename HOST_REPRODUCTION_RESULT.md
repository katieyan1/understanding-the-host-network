# Host reproduction result

Validated on 2026-09-27 by following `HOST_REPRODUCTION.md` from repository
commit `506ff9cf1e591bf6bb89b03f1b70e21a85b9c65e` (`master`). This checkout was
kept at its current, newer commit rather than detached at the historical
`9d2ae09ae049c9f0b3a3a15f5ac3ca0544a86a95` snapshot.

## Host inventory

| Item | Observed value |
|---|---|
| OS | Ubuntu 22.04.2 LTS (Jammy) |
| Kernel | `5.15.0-187-generic` x86-64 |
| CPU | Intel Xeon Silver 4314, family 6, model 106, stepping 6 |
| Topology | 1 socket, 16 physical cores, 2 threads/core, 32 logical CPUs |
| CPU allocation | NUMA node 0 contains CPUs 0-31; CPUs 0-15 are distinct physical cores and CPUs 16-31 are their SMT siblings |
| Memory | 128415 MiB, 1 NUMA node, eight 16 GB Micron DDR4 DIMMs, configured at 2666 MT/s |
| OS device | `/dev/sda`, Intel SSDSC2KG960G8, serial `PHYG126103QC960CGN` |
| RDMA | ConnectX devices `mlx5_0` through `mlx5_3`; `mlx5_2`/`ens1f0np0` was active |

The four configured raw experiment drives were unmounted and had no filesystem
or partition signatures when inspected:

| Path | Model | Serial | Size |
|---|---|---|---|
| `/dev/nvme0n1` | Samsung MZQL2960HCJR-00A07 | `S64FNE0RA02712` | 894.3 GB |
| `/dev/nvme1n1` | Samsung MZQL2960HCJR-00A07 | `S64FNE0RA02751` | 894.3 GB |
| `/dev/nvme2n1` | Samsung MZQL2960HCJR-00A07 | `S64FNE0RA02009` | 894.3 GB |
| `/dev/nvme3n1` | Samsung MZQL2960HCJR-00A07 | `S64FNE0RA02708` | 894.3 GB |

## Installation and runtime state

- All requested Ubuntu packages were already installed. Their versions matched
  the reference record except `msr-tools`, which was the patched Ubuntu package
  `1.3-4ubuntu0.1` rather than `1.3-4`.
- The distribution `redis-server` service is `disabled` and `inactive`.
- PCM, memtier_benchmark, and GAPBS were checked out at the required revisions
  `9b3e4a1688869a8a88f0ea17d0be1c5283f0b3bb`,
  `d5ac1f4167e01f0b76b0ea095640747ec3670c1d`, and
  `2972aeb2703165bafd921222f4ed7196f542d3a8`, respectively. All required
  binaries, including STREAM, built successfully.
- The `msr` module is loaded, all 32 CPU policies use the `performance`
  governor, turbo is disabled (`intel_pstate/no_turbo=1`), and MSR `0x1a4` is
  `0` on all 32 logical CPUs.
- PCM detected 8 memory channels (`SKT0CHAN0`-`SKT0CHAN7`), 16 CHAs
  (`SKT0C0`-`SKT0C15`), and 6 IRPs (`SKT0IRP0`-`SKT0IRP5`), matching
  `config.json`.
- Transparent huge pages and `vm.overcommit_memory` were not changed. No raw
  drive was partitioned, formatted, or mounted.

## Validation

- JSON, Python compilation/import, shell syntax, Git whitespace, and executable
  presence checks passed.
- STREAM `Read64 8` on CPU 4 passed at 16067 MB/s.
- GAPBS PageRank `-g 10 -n 1` on CPU 4 passed.
- Redis 6.0.16 and memtier_benchmark 2.0.0 version checks passed.
- A five-second 8 MiB random-read fio test on `/dev/nvme0n1` passed at about
  5641 MB/s. fio reported 75,765 reads and zero writes.
- The STREAM-plus-PCM CHA test produced nonzero `drd_inserts` on all 16 CHAs in
  every captured interval.

The documented fio spelling `--readonly=1` is rejected by the installed fio
3.28 because `--readonly` is a flag. The validation used `--readonly` with all
other documented options unchanged.
