# NEMA Specification v0.1 (Draft Normative)

Provenance note:
- This `spec/spec.md` is a canonicalized path copy of the root-level `spec.md`.
- No semantic deltas are introduced here relative to `spec.md`.

This document is a **draft normative specification** for the current NEMA v0.1 implementation in this repository.

Normative artifacts:
- `./spec.md` (this file)
- `./nema_ir.proto`

If implementation and this file disagree, update both plus regression tests in the same change.

## 1. Scope

NEMA v0.1 defines:
- IR contract (JSON shape mirrored by `nema_ir.proto`)
- deterministic tick semantics (`nema.tick.v0.1`)
- fixed-point behavior (RNE + saturation)
- tanh LUT policy (`nema.tanh_lut.v0.1`)
- bit-exact comparison criteria
- G0 conformance checklist

## 2. Numeric Model (Fixed-Point)

Overflow behavior:
- `SATURATE` only.

Rounding behavior:
- `RNE` (round to nearest, ties to even) only.

### 2.1 Raw Domains

For signed fixed-point with `totalBits = T`:
- raw min: `-(2^(T-1))`
- raw max: `(2^(T-1)) - 1`

For unsigned fixed-point with `totalBits = T`:
- raw min: `0`
- raw max: `(2^T) - 1`

### 2.2 RNE Definition

When quantizing from rational value `x` to integer raw:
1. choose nearest integer
2. if exactly halfway, choose the even integer
3. apply saturation to target raw domain

For right-shift by `k` bits with rounding:
- equivalent to division by `2^k` with the same RNE rule above.

### 2.3 Required Operation Behavior

Operations used by v0.1 must obey RNE + saturation:
- add/sub: saturating
- mul/mac: widened intermediate precision, final quantization by RNE to target type
- shifts:
  - arithmetic right shift preserves sign
  - logical right shift shifts bit-pattern
- abs: if input is signed min value, saturate to signed max
- cmp/mux/clip: deterministic with explicit ordering

Reference implementation: `nema/fixed.py`.

## 3. Tanh LUT Policy (`nema.tanh_lut.v0.1`)

Generator: `tools/gen_tanh_lut.py`.

Input/Output type IDs:
- accepted forms: `Q<int>.<frac>`, `UQ<int>.<frac>`
- current simulator path requires `Q8.8 -> Q8.8`

Generation algorithm:
1. enumerate every raw input in the full input type range
2. compute `tanh(x)` at high precision (Decimal)
3. quantize output with RNE + saturation to output type raw domain

Artifacts:
- binary: packed signed `int16` little-endian (`.bin`)
- debug: JSON array of signed raw values (`.json`)

Canonical Q8.8 artifact:
- path: `artifacts/luts/tanh_q8_8.bin`
- expected SHA-256:
  - `7d21f56cc692fadb62283328037b0319745d1a08b4369d4fbffe8dc6cb260d88`

## 4. IR Contract (v0.1)

Canonical schema is versioned in `./nema_ir.proto`.

### 4.1 Top-Level Required Objects

Required:
- `constraints`
- `license`
- `graph`
- `tanhLut`

Common optional metadata:
- `name`
- `modelId`
- `kernelId`

### 4.2 Constraints and License

- `constraints.allowedSpdx` must be a non-empty list of SPDX IDs.
- `license.spdxId` must be one of `constraints.allowedSpdx`.

### 4.3 Graph

`graph.nodes`:
- required fields per node:
  - `id` (string, unique)
  - `index` (non-negative integer, unique)
  - `canonicalOrderId` (non-negative integer)
- optional node fields used by simulation/codegen:
  - `vInitRaw` (aliases accepted in code: `v0Raw`, `vRaw`, `initialVRaw`)
  - `tauM` (alias accepted: `tau_m`)

`graph.edges`:
- required fields per edge:
  - `id` (string, unique)
  - `kind` (or alias `type`): `CHEMICAL` or `GAP`
  - endpoints: canonical `source`/`target` (aliases accepted in code)
  - `conductance` (numeric, non-negative)
- `CHEMICAL` must be directed
- `GAP` must be symmetric if represented as directed pairs

Edge coefficients:
- chemical coefficient source:
  - `weight` if present, else `conductance`
- gap coefficient source:
  - `conductance`

Graph timing:
- `graph.dt` optional; default `1.0` if missing
- `tauM` must be positive (node-level if present, else graph-level default)

External references:
- `graph.external` may be an object or array
- referenced path/file must exist
- if `sha256` is not a placeholder token, it must match file digest

## 5. Tick Semantics (`nema.tick.v0.1`)

State format:
- node voltage `V`: signed `Q8.8` (int16 raw)
- activation `A`: signed `Q8.8`
- accumulators `I_chem`, `I_gap`: signed `Q12.8` (20-bit raw domain)

Per tick:
1. snapshot all node voltages: `V_snapshot`
2. lookup activations from LUT:
   - `A_i = tanh_lut[V_snapshot_i]`
3. accumulate currents into `Q12.8`:
   - chemical (`chemical_current_v0`):
     - for each edge `pre -> post`:
       - `msg = quantize_Q12.8( coeff_chem * A_pre )`
       - `I_chem[post] += msg` (saturating)
   - gap (`gap_conductance_v0`):
     - operate once per undirected pair `(a,b)` with coefficient `g`
       - `msg = quantize_Q12.8( g * (Vb - Va) )`
       - `I_gap[a] += msg`
       - `I_gap[b] -= msg`
       - all saturating
4. Euler update with snapshot rule:
   - `I_total = I_chem + I_gap` (Q12.8, saturating)
   - `inv_tau = dt / tau_m`
   - `delta_v = quantize_Q8.8( inv_tau * I_total )`
   - `V_next = saturate_Q8.8( V_snapshot + delta_v )`

Determinism requirements:
- simulation node iteration is index-ordered
- snapshot rule guarantees order-independent results for update ordering

Reference implementation: `nema/sim.py`.

## 6. Bit-Exact Definition

Two executions are bit-exact equal when all per-tick digests match.

Digest computation:
- collect `V` in node index order
- pack each raw voltage as signed int16 little-endian
- compute SHA-256 over packed byte array

Reference outputs:
- `tickDigestsSha256` list in simulator/harness outputs
- `trace.jsonl` contains `vRawByIndex` and per-tick digest

## 7. G0 Conformance Checklist

Stage G0 is considered complete only if all are true:
1. A.1 fixed-point ISA tests pass (`tests/test_fixed.py`)
2. A.2 LUT generation/checksum tests pass (`tests/test_tanh_lut.py`)
3. A.3 tick micrograph tests pass (`tests/test_tick_micrographs.py`)
4. B1 benchmark:
   - golden and C++ reference digests exist and match
   - bench report exists and marks correctness pass
5. B3 benchmark:
   - same conditions as B1 for target config `302/7500`
6. when HW toolchain is available:
   - include csim/cosim/synthesis report artifacts in benchmark output

## 8. Implementation References

- IR validation: `nema/ir_validate.py`
- simulation: `nema/sim.py`
- fixed-point core: `nema/fixed.py`
- LUT generator: `tools/gen_tanh_lut.py`
- CSR lowering: `nema/lowering/csr.py`
- HLS/C++ codegen: `nema/codegen/hls_gen.py`

---
Provenance: canonical copy derived from repository root `spec.md`.
Generated by Codex structural normalization step (STEP_03B).
