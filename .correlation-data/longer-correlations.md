# Strongest correlation magnitudes in the longer runs

Source: [`longer-correlations.csv`](./longer-correlations.csv)

This summary covers 91 metric pairs across `fio-randread`, `gapbs-bc`,
`gapbs-pr`, and `stream`. Correlations are Pearson coefficients.
`average_correlation` is the arithmetic mean of the four correlation
magnitudes:

`mean(abs(r_fio-randread), abs(r_gapbs-bc), abs(r_gapbs-pr), abs(r_stream))`

The average therefore measures relationship strength from 0 to 1. It does not
preserve direction; the individual workload values show whether each
relationship is positive or negative.

## Main findings

- Nine pairs have an average magnitude of at least 0.90 and remain above
  0.80 in every workload.
- Fourteen of the 91 pairs have an average magnitude of at least 0.50.
- The strongest results form three related groups: equivalent occupancy
  representations, DRD inserts and occupancy, and read activity with RPQ
  occupancy.
- The two perfect-correlation pairs compare aggregate occupancy with the
  corresponding time-based occupancy representation. They are effectively
  redundant signals, not independent observations.
- Some relationships vary substantially by workload. In particular,
  `memreadbw` and `memwritebw` range from -0.940 in `gapbs-pr` to 0.928 in
  `stream`. Their average magnitude is 0.536, which correctly captures the
  relationship's strength while the individual values expose its reversal in
  direction.

## Strongest consistently positive pairs

All nine pairs below have an average magnitude of at least 0.90 and a
correlation above 0.80 in every workload.

| Metric pair | fio-randread | gapbs-bc | gapbs-pr | stream | Average magnitude |
| --- | ---: | ---: | ---: | ---: | ---: |
| `drd_occ_agg` / `drd_occupancy` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `rpq_occ_agg` / `rpq_occupancy` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `drd_inserts` / `drd_occ_agg` | 0.9999 | 1.0000 | 1.0000 | 0.9989 | 0.9997 |
| `drd_inserts` / `drd_occupancy` | 0.9999 | 1.0000 | 1.0000 | 0.9989 | 0.9997 |
| `acts_read` / `read_activations` | 1.0000 | 0.9840 | 0.9931 | 0.9954 | 0.9931 |
| `read_activations` / `rpq_occupancy` | 0.9327 | 0.9143 | 0.9760 | 0.8351 | 0.9145 |
| `read_activations` / `rpq_occ_agg` | 0.9327 | 0.9143 | 0.9760 | 0.8351 | 0.9145 |
| `acts_read` / `rpq_occ_agg` | 0.9326 | 0.8512 | 0.9923 | 0.8619 | 0.9095 |
| `acts_read` / `rpq_occupancy` | 0.9326 | 0.8512 | 0.9923 | 0.8619 | 0.9095 |

The first two rows compare duplicated occupancy representations:
`drd_occ_agg` tracks `drd_occupancy`, and `rpq_occ_agg` tracks
`rpq_occupancy`. The next two rows repeat the same near-perfect relationship
between `drd_inserts` and the two equivalent DRD occupancy signals. After
accounting for those duplicates, the clearest distinct relationship is between
`acts_read` and `read_activations`, with correlations from 0.984 to 1.000
across all workloads.

Read activity also tracks RPQ occupancy consistently. The four combinations of
`acts_read` or `read_activations` with `rpq_occ_agg` or `rpq_occupancy` average
between 0.909 and 0.915 in magnitude. These relationships are strongest in
`gapbs-pr` and weakest in `stream`, but remain strongly positive in every
workload.

## Next strongest relationships

The correlation strength drops noticeably after the top nine pairs:

| Metric pair | Average magnitude | Signed workload range |
| --- | ---: | ---: |
| `acts_byp` / `read_activations` | 0.765 | 0.640 to 0.944 |
| `acts_byp` / `rpq_occupancy` | 0.734 | 0.348 to 0.935 |
| `acts_byp` / `rpq_occ_agg` | 0.734 | 0.348 to 0.935 |
| `acts_byp` / `acts_read` | 0.699 | 0.493 to 0.899 |
| `memreadbw` / `memwritebw` | 0.536 | -0.940 to 0.928 |

The `acts_byp` pairs are positive but less stable across workloads. The two
`acts_byp`/RPQ relationships are especially workload-sensitive because their
correlation falls to about 0.35 in `stream`.

## Direction and workload-specific relationships

Because the average uses magnitudes, opposite-signed correlations reinforce
the average instead of canceling out. The clearest example is `memreadbw`
versus `memwritebw`:

| fio-randread | gapbs-bc | gapbs-pr | stream | Average magnitude |
| ---: | ---: | ---: | ---: | ---: |
| 0.232 | -0.045 | -0.940 | 0.928 | 0.536 |

The pair is strongly negative in `gapbs-pr` and strongly positive in `stream`.
The magnitude average preserves that strength, but it must be read with the
signed workload columns to avoid implying a consistent direction.

The strongest mostly negative relationships are still workload-specific:

| Metric pair | fio-randread | gapbs-bc | gapbs-pr | stream | Average magnitude |
| --- | ---: | ---: | ---: | ---: | ---: |
| `drd_latency` / `l1_miss_latency` | -0.042 | -0.447 | 0.007 | -0.003 | 0.125 |
| `acts_read` / `drd_latency` | -0.000 | -0.470 | -0.022 | 0.002 | 0.124 |
| `drd_latency` / `read_activations` | -0.000 | -0.469 | -0.024 | -0.000 | 0.123 |

Their magnitude comes primarily from `gapbs-bc`; the relationships are near
zero in most other workloads, so they are not consistent inverse signals.

## Interpretation

Exact or near-exact correlations can identify redundant counters or metrics
derived from the same underlying quantity. They should not be counted as
independent signals in a model. The remaining strong positive relationships
show stable co-movement across the four workloads. For mixed-sign pairs, use
the magnitude average to rank strength and the workload columns to interpret
direction. Correlation alone does not establish causation.
