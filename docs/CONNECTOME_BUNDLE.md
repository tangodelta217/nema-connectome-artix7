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

Ingest CSV into deterministic JSON bundle:

```bash
python -m nema connectome ingest \
  --nodes nodes.csv \
  --edges edges.csv \
  --out connectomes/test_bundle.json \
  --subgraph-id test_subgraph \
  --license-spdx MIT \
  --source-url "https://example.org/dataset" \
  --source-sha256 "sha256:<source_digest>" \
  --retrieved-at "2026-02-24T00:00:00Z"
```

Verify JSON bundle or directory bundle:

```bash
python -m nema connectome verify connectomes/test_bundle.json
python -m nema connectome verify connectome_bundle/
```

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

## JSON Bundle Schema (ingest output)

`connectome ingest` emits a single JSON artifact with:
- `schemaVersion` (`"0.1"`)
- `formatId` (`"nema.connectome.bundle.v0.1"`)
- `subgraphId`
- `license.spdxId`
- `provenance`:
  - `sourceUrls[]`
  - `sourceSha256` (optional)
  - `retrievedAt`
- `graph`:
  - `nodes[]`
  - `edges[]`
- `counts`
- `checksums`:
  - `algorithm`
  - `sections.nodes|edges|graph|metadata`
  - `bundle`

Verifier checks:
- node/edge ID uniqueness and edge referential integrity
- non-negative conductance
- canonical GAP encoding (`directed=false`, `source<=target`, no duplicate canonical pairs)
- counts + checksums consistency

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
