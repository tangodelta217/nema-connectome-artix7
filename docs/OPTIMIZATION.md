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
  --outdir build/sweep_lanes \
  --hw require
```

Outputs:

- `build/sweep_lanes/sweep_results.json`
- `build/sweep_lanes/sweep_results.csv`

Resume behavior:

- If `build/sweep_lanes/<combo>/<modelId>/bench_report.json` exists and `ok=true`,
  that combination is skipped and reused.
