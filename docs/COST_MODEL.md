# NEMA Cost Model v0

## Scope
`nema cost` provides a simple deterministic estimate layer to compare expected workload against measured HLS QoR.

## Commands
- `python -m nema cost estimate <ir.json>`
- `python -m nema cost compare <bench_report.json>`

Both commands emit JSON with stable key names.

## v0 Estimate
`cost estimate` resolves the IR graph and predicts:
- `opsPerTick`
- `bytesPerTick`
- `cyclesPerTick`

Inputs used by the model:
- resolved `nodeCount`, `chemicalEdgeCount`, `gapEdgeCount`
- `compile.schedule.synapseLanes` and `compile.schedule.neuronLanes` (default `1`)

Current v0 cycle approximation:
- `startup = 32`
- `synapseStage = ceil((chemical + gap) / (synapseLanes * 3))`
- `neuronStage = ceil(nodeCount / neuronLanes)`
- `perTick = startup + synapseStage + neuronStage`

## Compare Against Real QoR
`cost compare` reads:
- predicted cycles/tick from the v0 model
- measured QoR from `hardware.qor.ii` and/or `hardware.qor.latencyCycles`

It reports relative error for each metric when available.

## G2 Context
For audit usage, G2 hardware evidence is considered present when at least one is true:
- `hardware.reports.files` is non-empty
- `hardware.qor.utilization` contains at least one non-null resource value (`lut`, `ff`, `bram`, `dsp`)

`cost compare` exposes this as `g2Evidence`.

## audit_min Hardware Gate
`tools/audit_min.py --mode hardware` applies a quantitative sanity check using
`cost compare` over relevant bench reports.

G2 passes only if both are true:
- hardware reports/QoR evidence exists
- estimated cycles and measured QoR are within a ratio threshold

Threshold:
- `--cost-max-ratio <float>` (default `3.0`)
- check is based on `comparison.maxRatio` from `nema cost compare`
- condition: `maxRatio < cost-max-ratio`
