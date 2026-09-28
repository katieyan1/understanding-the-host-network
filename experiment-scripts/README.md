# Correlation experiment scripts

These seven scripts reproduce the raw `correlation-*` groups in
`.experiment-data` and then generate the corresponding CSVs under
`.correlation-data/<group>`. Each script starts a 4,500-sample `sar` collection
alongside `mio`; `mio` then records 4,500 one-second samples for each of the four
Ice Lake PCM scopes. The PCM scopes are collected sequentially, so a complete
run takes about five hours rather than 75 minutes. Run only one experiment at a
time from an otherwise idle host.

The scripts resolve the repository root themselves, require root privileges,
and verify that `config.json` writes statistics to this checkout's
`.experiment-data` directory. Existing outputs are protected by default. To
replace a checked-in group, explicitly opt in:

```bash
sudo OVERWRITE_EXPERIMENT_DATA=1 \
  ./experiment-scripts/correlation-stream.sh
```

The available entry points are:

- `correlation-stream.sh`: one CPU running STREAM Read64 for 18,030 seconds.
- `correlation-gapbs-pr.sh`: one CPU, scale-25 PageRank, 500 trials.
- `correlation-gapbs-bc.sh`: one CPU, scale-25 betweenness centrality, 370 trials.
- `correlation-redis-get.sh`: one server/client pair and 27 billion GETs.
- `correlation-redis-set.sh`: one server/client pair and 10.3 billion SETs.
- `correlation-fio-randread.sh`: one NVMe, 8 MiB random reads, queue depth 64,
  for 18,030 seconds.
- `correlation-fio-randwrite.sh`: one NVMe, 8 MiB random writes, queue depth 64,
  for 18,030 seconds.

The GAPBS and Redis runners do not stop based on `--ant_duration`. Their trial
and request counts are therefore sized from the checked-in host's observed
rates, with roughly five percent headroom, so the workloads remain active for
all four PCM windows. These scripts may continue briefly after the final PCM
sample while the remaining work completes.

The fio write experiment is destructive: at the checked-in throughput, the
18,030-second run writes roughly 25 TiB directly to `/dev/nvme0n1`. In addition
to the overwrite opt-in, it requires the configured first SSD to be unmounted
and signature-free and requires an exact device opt-in:

```bash
sudo OVERWRITE_EXPERIMENT_DATA=1 \
  ALLOW_RAW_NVME_WRITE=/dev/nvme0n1 \
  ./experiment-scripts/correlation-fio-randwrite.sh
```

Redis scripts terminate pre-existing `redis-server` processes because that is
how the repository's Redis runner isolates its Unix-socket instances.

To inspect a command without running it or replacing output, use `DRY_RUN=1`:

```bash
DRY_RUN=1 ./experiment-scripts/correlation-gapbs-pr.sh
```

## CSV export

After its workload and all collectors finish successfully, each experiment
script runs `extract_correlation.py` for its group. The exporter validates that
every expected PCM and CPU scope contains exactly 4,500 samples, then writes:

- `dependable-metric-samples.csv`
- `dependable-metric-summary.csv`
- `experiment-metadata.csv`
- `pairwise-covariance.csv`
- `high-correlation.csv`

Once all seven group directories contain 4,500-sample pairwise results, the
exporter also refreshes `.correlation-data/all-correlations.csv` and
`.correlation-data/all-high-correlations.csv`. Until then, it reports that the
aggregate refresh was skipped, so old and new sample lengths are not mixed.

If a required raw log is missing or incomplete, the script exits nonzero rather
than exporting it. To rerun an export without rerunning the workload, specify
one of the seven group names shown by `--help`; for example:

```bash
python3 extract_correlation.py stream
```

The earlier STREAM-only command remains available as
`python3 extract_correlation_stream.py`.
