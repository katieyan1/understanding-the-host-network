# Recorded experiment results

Recorded on 2026-09-08 on one Intel Xeon Silver 4314 socket with 16 physical
cores, eight DDR4 channels, and four Samsung NVMe devices. CPU frequency scaling
and turbo were disabled. Every fio workload in this report was read-only.

Raw logs and the generated `stream-fio-results.csv` and
`application-results.csv` files are in this directory.

## STREAM core scaling

| Cores | STREAM (GB/s) | Speedup | Scaling efficiency | L1 miss latency (ns) | DRAM read (GB/s) | RPQ occupancy/channel | DRd latency (ns) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 16.554 | 1.00x | 100.0% | 42.33 | 16.829 | 0.131 | 30.04 |
| 2 | 31.059 | 1.88x | 93.8% | 45.22 | 32.373 | 0.318 | 30.78 |
| 4 | 56.704 | 3.43x | 85.6% | 49.86 | 59.754 | 0.819 | 32.06 |
| 8 | 96.137 | 5.81x | 72.6% | 59.58 | 100.165 | 2.174 | 33.78 |
| 12 | 123.240 | 7.44x | 62.0% | 70.27 | 125.859 | 3.864 | 36.09 |

Bandwidth continues to increase through twelve cores, but efficiency declines as
the memory system approaches saturation. From one to twelve cores, L1 miss
latency rises 66.0%, mean RPQ occupancy rises from 0.131 to 3.864 entries per
channel, and local DRd latency rises 20.1%. These independent counters all show
growing memory-path contention.

## STREAM plus four-NVMe colocation

The fio control and every colocated point used 8 MiB random reads, queue depth
64, four raw NVMe devices, and a 140-second fio interval. The isolated aggregate
fio baseline was 28.086 GB/s.

| STREAM cores | Isolated STREAM (GB/s) | Colocated STREAM (GB/s) | STREAM loss | Colocated fio (GB/s) | fio change | Isolated L1 latency (ns) | Colocated L1 latency (ns) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 16.554 | 14.294 | 13.65% | 28.114 | +0.10% | 42.33 | 49.28 |
| 2 | 31.059 | 26.636 | 14.24% | 28.114 | +0.10% | 45.22 | 53.26 |
| 4 | 56.704 | 47.566 | 16.12% | 28.115 | +0.10% | 49.86 | 60.22 |
| 8 | 96.137 | 78.203 | 18.65% | 28.103 | +0.06% | 59.58 | 74.13 |
| 12 | 123.240 | 95.600 | 22.43% | 28.105 | +0.07% | 70.27 | 91.47 |

The observed interference is asymmetric. fio retains its isolated throughput
within 0.10%, while STREAM loses progressively more throughput as its core count
increases. At twelve cores, isolated DRAM traffic is about 125.87 GB/s. Under
colocation, PCM reports about 97.57 GB/s of reads plus 28.81 GB/s of writes, or
126.38 GB/s total. The total is nearly unchanged, but device DMA displaces CPU
read traffic. The simultaneous 30.2% L1-miss-latency increase explains part of
the application slowdown.

All 24 fio logs (four isolated and twenty colocated) report `randread`, `err=0`,
and the intended duration. No NVMe data was written.

## GAPBS PageRank scaling

Each point used a scale-25 graph. The runner recorded three iterations per core,
giving 3, 6, 12, and 24 timing observations.

| Cores | Mean trial time (s) | Speedup | Parallel efficiency | DRAM read (GB/s) |
|---:|---:|---:|---:|---:|
| 1 | 37.778 | 1.00x | 100.0% | 6.746 |
| 2 | 19.130 | 1.97x | 98.7% | 13.407 |
| 4 | 9.709 | 3.89x | 97.3% | 25.881 |
| 8 | 4.996 | 7.56x | 94.5% | 48.071 |

PageRank scales very well through eight cores. Its 94.5% eight-core efficiency
and sub-50 GB/s DRAM rate show that this sweep has not yet reached the socket's
STREAM bandwidth ceiling.

## Redis GET scaling

Each Redis server held one million 1 KiB values and processed 50 million
pipelined GET operations. One server core was paired with one client core.

| Total cores | Server-client pairs | Aggregate GET/s | Speedup | Pair-scaling efficiency | DRAM read (GB/s) |
|---:|---:|---:|---:|---:|---:|
| 2 | 1 | 1,405,047 | 1.00x | 100.0% | 0.242 |
| 4 | 2 | 2,662,079 | 1.89x | 94.7% | 0.550 |
| 6 | 3 | 3,840,250 | 2.73x | 91.1% | 0.867 |

Redis also scales well, with a modest fall in efficiency as instances compete
for shared resources. Redis emitted its standard `overcommit_memory=0` warning,
but persistence was disabled and every request stream completed normally.

## Scope and limitations

- These are single trials at each configuration. They establish trends but do
  not provide confidence intervals; repeat each point at least three times for
  publication-quality comparisons.
- The STREAM/fio result covers read-only CPU traffic plus device-to-host reads.
  Write quadrants were not run because raw-device writes are destructive.
- Redis and GAPBS were measured in isolation. Their slowdown under fio or NIC
  traffic requires matched colocated runs.
- TCP and RDMA still require a configured peer host.
- Cascade Lake analytical-model, bank-distribution, and DDIO-toggle experiments
  remain unavailable on this Ice Lake machine.
