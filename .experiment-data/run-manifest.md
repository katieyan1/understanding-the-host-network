# Experiment run manifest

Date: 2026-09-08 UTC  
Repository base commit: `dc5b7f2e5ed93bed78010d71566676fe05e58ead` plus the
uncommitted Ice Lake preparation changes in the working tree.

## Host

- Linux 5.15.0-187-generic, x86-64
- Intel Xeon Silver 4314 at 2.40 GHz
- One socket, 16 physical cores, 32 logical CPUs, one NUMA node
- Eight DDR4 memory channels
- Four raw, unmounted 894.3 GB Samsung NVMe devices
- CPU governor `performance`; turbo disabled

## Software

- fio 3.28
- Redis 6.0.16
- memtier_benchmark 2.0.0
- Intel PCM source tag 202403
- GAPBS commit `2972aeb2703165bafd921222f4ed7196f542d3a8`
- Locally built repository STREAM*

All commands were run from the repository root. Full raw output is stored in
this directory under each command's first positional label.

## Commands

STREAM core scaling:

```bash
sudo python3 -m mio icl-stream-scale \
  --ant stream --ant_cpus 4,5,6,7,8,9,10,11,12,13,14,15 \
  --ant_num_cores 1,2,4,8,12 --ant_mem_numa 0 \
  --ant_inst_size 64 --ant_writefrac 0 --ant_duration 120 \
  --disable_prefetch --stats
```

The twelve-core point was repeated after correcting process cleanup; the files
on disk are from the successful replacement run.

STREAM plus fio:

```bash
sudo python3 -m mio icl-stream-fio-read \
  --ant stream --ant_cpus 4,5,6,7,8,9,10,11,12,13,14,15 \
  --ant_num_cores 1,2,4,8,12 --ant_mem_numa 0 \
  --ant_inst_size 64 --ant_writefrac 0 --ant_duration 120 \
  --fio --fio_mem_numa 0 --fio_cpus 1,2,3 --fio_writefrac 0 \
  --fio_iosize 8388608 --fio_iodepth 64 --fio_num_ssds 4 \
  --sync_durations --disable_prefetch --stats
```

Matched isolated fio control:

```bash
sudo python3 -m mio icl-fio-read-iso \
  --fio --fio_mem_numa 0 --fio_cpus 1,2,3 --fio_writefrac 0 \
  --fio_iosize 8388608 --fio_iodepth 64 --fio_num_ssds 4 \
  --fio_duration 140 --stats_membw
```

GAPBS PageRank scaling:

```bash
sudo python3 -m mio icl-gapbs-pr-scale \
  --ant gapbs --ant_cpus 4,5,6,7,8,9,10,11 \
  --ant_num_cores 1,2,4,8 --ant_mem_numa 0 \
  --ant_duration 120 --stats
```

Redis GET scaling:

```bash
sudo python3 -m mio icl-redis-get-scale \
  --ant redis --ant_cpus 4,5,6,7,8,9 \
  --ant_num_cores 2,4,6 --ant_mem_numa 0 \
  --ant_writefrac 0 --ant_duration 1000 --stats_membw
```

`RedisRunner` ignores `--ant_duration`; each server executes its configured 50
million requests. The fio commands use `--fio_writefrac 0`, which selects
`randread`; no NVMe writes were issued.
