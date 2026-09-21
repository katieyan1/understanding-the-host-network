# fio-randread metric descriptions

This file documents only the metrics captured in
`.correlation-data/fio-randread/dependable-metric-samples.csv`.

An **occupancy-cycle** means one occupied queue entry for one hardware clock
cycle. For example, two occupied entries held for three cycles contribute six
occupancy-cycles. The derived occupancy values below convert those totals to
entry-seconds; divide by the collection-window duration to obtain average queue
depth.

| Metric | Scope and unit | Brief description |
| --- | --- | --- |
| `acts_byp` | Memory channel; events | DRAM activate commands for qualifying reads that used the memory controller's optimized bypass path. |
| `acts_read` | Memory channel; events | DRAM activate commands issued because of read requests through the normal path. An activate opens a DRAM row before access. |
| `cpu_util` | CPU core; percent | Core CPU use reported by `sar`, calculated by mio as `%user + %system`. |
| `drd_inserts` | CHA; transactions | Local DDR data-read requests from CPU cores that missed the LLC and were inserted into the CHA's Table of Requests (TOR). |
| `drd_latency` | CHA; ns | Average time a matching data-read request spent in the TOR: `drd_occupancy * 1e9 / drd_inserts`. It is unavailable when the insert count is zero. |
| `drd_occ_agg` | CHA; occupancy-cycles | Sum, over CHA clock cycles, of matching data-read requests occupying TOR entries. |
| `drd_occupancy` | CHA; request-seconds | Time-integrated TOR occupancy: `drd_occ_agg / CHA_FREQ`. This is not average queue depth unless divided by the collection-window duration. |
| `l1_miss_latency` | CPU core; ns | Average L1 data-cache miss latency reported by Intel PCM's latency collector. |
| `memreadbw` | Memory channel; MB/s | DRAM read bandwidth reported by Intel PCM for the channel. |
| `memwritebw` | Memory channel; MB/s | DRAM write bandwidth reported by Intel PCM for the channel. |
| `read_activations` | Memory channel; events | Total read-related DRAM activates, derived as `acts_read + acts_byp`. |
| `rpq_occ_agg` | Memory channel; occupancy-cycles | Sum, over memory-controller clock cycles, of occupied entries in the Read Pending Queue (RPQ). |
| `rpq_occupancy` | Memory channel; queue-entry-seconds | Time-integrated RPQ occupancy: `rpq_occ_agg / IMC_FREQ`. Divide by the collection-window duration for average RPQ depth. |
| `wpq_full_cycles` | Memory channel; cycles | Memory-controller cycles during which the Write Pending Queue (WPQ) was full, indicating write-queue pressure. |

## Scope labels

- `CORE<n>` identifies a logical CPU core.
- `SKT0CHAN<n>` identifies a memory channel on socket 0.
- `SKT0C<n>` identifies a caching/home agent (CHA) on socket 0.

## Sources

- The captured metric names, scopes, and units come from
  [`dependable-metric-samples.csv`](../.correlation-data/fio-randread/dependable-metric-samples.csv).
- Derived formulas and the `sar` calculation come from [`stats.py`](stats.py).
- Raw PMU event encodings come from [`app.py`](app.py).
- Hardware-event semantics follow Intel's
  [Ice Lake Xeon uncore event reference](https://perfmon-events.intel.com/platforms/icelakex/uncore-events/uncore/)
  and [Cascade Lake Xeon uncore event reference](https://perfmon-events.intel.com/platforms/cascadelakex/uncore-events/uncore/).
- PCM metric semantics follow the [Intel PCM documentation](https://github.com/intel/pcm).

