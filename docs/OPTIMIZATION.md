# NEMA Optimization Notes

## Lanes Sweep (B3)

Use the lanes sweep command to explore `compile.schedule.synapseLanes` and
`compile.schedule.neuronLanes` while collecting per-run QoR fields from
`bench_report.json`.

```bash
python -m nema sweep lanes example_b3_kernel_302.json \
  --synapse 1,2,4,8 \
  --neuron 1,2,4 \
  --ticks 2 \
  --outdir sweep_out \
  --hw require
```

Outputs:

- `sweep_out/sweep_results.json`
- `sweep_out/sweep_results.csv`

Resume behavior:

- If `sweep_out/<combo>/<modelId>/bench_report.json` exists and `ok=true`,
  that combination is skipped and reused.

