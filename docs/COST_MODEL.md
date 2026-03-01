# NEMA Cost Model v0

## Scope
`nema cost` provides a simple deterministic estimate layer to compare expected workload against measured HLS QoR.

## Commands
- `python -m nema cost estimate <ir.json>`
- `python -m nema cost compare <bench_report.json>`
- `python tools/qor_dataset.py --root <bench_root> --out build/qor_dataset.csv`
- `python tools/cost_model_fit.py --csv build/qor_dataset.csv`

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

## QoR Dataset + Fit Baseline
`tools/qor_dataset.py` scans bench reports and emits a stable CSV:
- columns: `N,E,qformat,P_N,P_S,ii,latency,lut,ff,bram,dsp`
- sorted deterministically by report path

`tools/cost_model_fit.py` fits a baseline linear model:
- `cycles ~= bias + a*(N/P_N) + b*(E/P_S)`
- reports `meanRelativeError`, `maxRelativeError`, `pointsWithActualQor`

## G2 Context
For audit usage, G2 hardware evidence is considered present when at least one is true:
- `hardware.reports.files` is non-empty
- `hardware.qor.utilization` contains at least one non-null resource value (`lut`, `ff`, `bram`, `dsp`)

`cost compare` exposes this as `g2Evidence`.

## audit_min Hardware Gate (G2)
`tools/audit_min.py --mode hardware` applies G2 sanity over relevant bench reports.

G2 passes only if all are true:
- hardware reports/QoR evidence exists
- there are at least `K` usable QoR points (`K >= 3`)
- fitted model mean relative error is below threshold

Parameters:
- `--cost-min-points <int>` (default `3`, must be `>= 3`)
- `--cost-mean-rel-error-max <float>` (default `1.0`)
