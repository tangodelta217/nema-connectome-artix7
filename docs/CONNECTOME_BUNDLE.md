# Connectome Bundle v0.1

`connectome_bundle/` is a directory-based format for reproducible external graph inputs.

Required files:
- `nodes.csv`
- `edges.csv`
- `metadata.json`

## CSV Layout

`nodes.csv` (minimum):
- `id`
- optional: `index`, `canonicalOrderId`, `vInitRaw`, `tauM`, `name`, `role`, `params`

`edges.csv` (minimum):
- `src`
- `dst`
- `type` (`CHEMICAL` or `GAP`)
- `conductance` (or `weight`, used as fallback for conductance)
- optional: `id`, `directed`, `weight`, `modelId`

## Metadata

`metadata.json` must include:
- `source`
- `license`
- `formatId` (expected: `nema.connectome.bundle.v0.1`)
- `sha256`:
  - `nodesCsv`
  - `edgesCsv`
  - `bundle` (deterministic digest derived from `nodesCsv` + `edgesCsv` digests)
- `counts`:
  - `nodeCount`
  - `chemicalEdgeCount`
  - `gapEdgeCount`
  - `edgeCountTotal`
  - `gapDirectedCount`

## CLI

Build bundle directory:

```bash
python -m nema connectome bundle build \
  --nodes nodes.csv \
  --edges edges.csv \
  --out connectome_bundle/ \
  --source "dataset label" \
  --license "MIT" \
  --subgraph-id "celegans_subset_v0"
```

Verify bundle (`sha256` + counts):

```bash
python -m nema connectome bundle verify connectome_bundle/
```

## IR Integration (`graph.external`)

`graph.external` may reference a bundle directory by path:

```json
{
  "uri": "connectomes/celegans_subset_bundle",
  "path": "connectomes/celegans_subset_bundle",
  "formatId": "nema.connectome.bundle.v0.1",
  "subgraphId": "celegans_subset_v0",
  "sha256": "sha256:<bundle_digest>"
}
```

`sha256` is validated against the bundle digest computed from `nodes.csv` + `edges.csv`.

Reference benchmark:
- `example_b4_celegans_external_bundle.json`

