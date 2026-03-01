===== BEGIN CLAIMS (OR TODO) =====
# Paper A Claims / No-Claims (Current)

Source of truth: `papers/paperA/context/gpt_a1_claims.md`

## Claims (current)
- C1: bit-exactness validation on B1/B3 via bench verify mismatch=0.
- C2: hardware pipeline evidence and QoR capture via hardware audit GO.
- C3: reproducible artifact + external bundle workflow (B4).

## No-Claims (current)
- No ML superiority claim (no SOTA/baseline accuracy claim).
- No full biological fidelity claim.
- No on-board power/latency measurement claim in current artifact.

## Full text
```md
A continuación te dejo una **propuesta “paper-ready”** (PLDI/OOPSLA‑style) que **solo incluye claims que se pueden verificar con comandos/scripts** del repo, y declara explícitamente lo que **no** prometemos.

---

## 1) Tres claims EXACTOS (verificables por scripts) + cómo verificarlos

### Claim C1 — Bit‑exactness (golden ↔ C++) en benchmarks base

**Claim (exacto):**
Para los benchmarks **B1** y **B3**, el comando de verificación de benches reporta **`ok=true`** y **`mismatches=[]`** (mismatch = 0), confirmando que la implementación “golden” y la implementación de referencia (C++ runner) son **bit‑exact** para la traza evaluada.

**Verificación (script/command):**

```bash
python -m nema bench verify benches/B1_small/manifest.json --outdir build/paper_verify/b1
python -m nema bench verify benches/B3_kernel_302_7500/manifest.json --outdir build/paper_verify/b3
```

**Criterio PASS (machine-checkable):**

* el JSON de salida de cada verify contiene:

  * `ok == true`
  * `mismatches` es lista vacía
  * (si el reporte lo expone) `digestMatchOk == true` o equivalente

Esto está alineado con la evidencia de auditoría donde B1/B3 “verify ok” y “digestMatch ok” figuran como alcanzados.  

---

### Claim C2 — Compilación reproducible a HW con captura de QoR (HLS) + timing (Vivado impl) en el bench_report

**Claim (exacto):**
En modo hardware, el gate `audit_min --mode hardware` retorna **`decision="GO"`** e implica que:

* la toolchain es detectable,
* hay evidencia de ejecución HW (G0b),
* hay evidencia/captura de reportes/QoR (G2),
* y existe evidencia de **Vivado implementation con WNS no nulo** (lo que el repo marca como G3).

**Verificación (script/command):**

```bash
python tools/audit_min.py --mode hardware
```

**Criterio PASS (machine-checkable):**

* exit code `0`
* JSON contiene `decision == "GO"`
* y en `criteria`:

  * `hardwareToolchainAvailable == true`
  * `hardwareEvidenceG0b == true`
  * `hardwareEvidenceG2 == true`
  * (si tu gate lo incluye) el item/flag asociado a Vivado impl/timing parse es `true`

Esto está explícitamente marcado como logrado en el “scoreboard” del estado AMP y en el maturity report (hardware GO; toolchain clean shell; presencia de artefactos HW en `build_hw/`).  

---

### Claim C3 — Artefacto auto‑auditado y reproducible (software + HW) con evidencia empaquetable

**Claim (exacto):**
El repositorio incluye una rutina de evaluación reproducible (software + hardware) que, en el estado actual, cumple:

* `pytest` pasa,
* `audit_min --mode software` = GO,
* `audit_min --mode hardware` = GO,
* existe evidencia de **reproducibilidad B1/B3** (run1 == run2 en digests) guardada en artefactos.

**Verificación (script/command):**

```bash
python -m pytest -q
python tools/audit_min.py --mode software
python tools/audit_min.py --mode hardware
# (opcional, para regenerar bundle/evidencia si lo tenés como script)
bash tools/checkpoint_full.sh
```

**Criterio PASS (machine-checkable):**

* `pytest` exit `0`
* ambos audits `decision="GO"` exit `0`
* el bundle/evidence existe y referencia repro (ej. `repro_summary.json`)

Esto coincide con el estado reportado como PASS en el maturity report (tabla “Current state”) y con el scoreboard AMP (ítems alcanzados).  

---

## 2) Tres “no-claims” explícitos (lo que NO prometemos)

1. **No claim de ventaja algorítmica/ML:**
   No afirmamos que NEMA (ni conectomas) supere a Transformers/GNNs/MLPs en accuracy, sample efficiency, etc. No hay evaluación comparativa de ML en el set mínimo.

2. **No claim de fidelidad biológica:**
   No afirmamos que el modelo sea biológicamente fiel (dinámica electrofisiológica, plasticidad realista, etc.). Lo que garantizamos es semántica determinista + ejecución bit‑exact según spec/IR.

3. **No claim de medición “on-board”:**
   No afirmamos potencia/latencia medida en placa real (power/latency “MEASURED_ON_BOARD”). De hecho, AMP+ v2 mantiene pendiente la parte de medición real sin hardware.  

---

## 3) Thesis statement (2 frases)

NEMA define una semántica **determinista** de ejecución por ticks para grafos neuronales dispersos y un IR diseñado para preservar **bit‑exactness** entre implementaciones de referencia y herramientas de validación. Además, NEMA compila esos programas a un flujo de hardware (HLS + Vivado) donde la evidencia de QoR/timing se captura en artefactos reproducibles y auto‑auditables mediante scripts.

---

## 4) Evaluación mínima (benchmarks + métricas exactas)

### Benchmarks a incluir (mínimo “paper core”)

* **B1**: sanity / micro‑graph (valida semántica y bit‑exactness)
* **B3**: escala conectome‑sized (302/7500) y evidencia HW/QoR
* **B4**: conectoma real en **bundle externo** con verify reproducible

Estos tres están alineados con el estado AMP actual y con los checks listados en el maturity report/scoreboard.  

### Benchmarks “si aplica” (apéndice o extensión)

* **B2/B5**: diversidad de dataset QoR para sanity/cost-model (si están en el artifact pack final)
* **B6**: delays (si existe `benches/B6_delay_small/manifest.json`; en tu roadmap aparece como siguiente paso boardless). 

### Métricas exactas (todas computables por scripts)

**Correctitud / bit‑exactness**

* `mismatch == 0` (equivalente a `mismatches=[]` en `bench verify`)
* `digestMatchOk == true` (si el reporte lo expone; o su equivalente en tu esquema)
* `bench_report.ok == true`

**Hardware / QoR**

* `hardware.qor.ii` (initiation interval)
* `hardware.qor.latencyCycles`
* Utilización: `hardware.qor.utilization.{lut,ff,bram,dsp}` (si están)
* **Timing Vivado (si existe):** `hardware.vivado.wns` no nulo (cuando haya implementación). El AMP+ v2 lo marca como PASS. 

**Criterios de gate (para paper, como “reproducibility contract”)**

* `python tools/audit_min.py --mode software` ⇒ `decision=GO`
* `python tools/audit_min.py --mode hardware` ⇒ `decision=GO`

---

## 5) Artifact story (qué scripts/paths deben existir en el artifact pack)

La historia de artefacto que te conviene contar (y que es verificable) es: **“un único entrypoint + gates reproducibles + evidencias en paths estables”**.

### Scripts/entrypoints obligatorios

1. **Gates**

* `tools/audit_min.py` (software/hardware) 

2. **HW pipeline**

* `tools/run_hw_gates.sh` (genera `build_hw/**/bench_report.json` + `hw_reports`) 

3. **Checkpoint/bundle**

* `tools/checkpoint_full.sh` (o equivalente) para producir `project_eval_out_v2/evidence/…` 

4. **Bench verify**

* CLI: `python -m nema bench verify …` (por manifest)

### Paths esperados (contrato del artefacto)

* `benches/B1_small/manifest.json`
* `benches/B3_kernel_302_7500/manifest.json`
* `benches/B4_real_connectome/manifest.json`
* IRs: `example_b1_small_subgraph.json`, `example_b3_kernel_302.json`, (B4 IR externo si aplica)
* `spec.md` + `nema_ir.proto` (contrato semántico + schema)
* `build_hw/` (generable) debe terminar conteniendo:

  * `**/bench_report.json`
  * `**/hw_reports/**/*.(rpt|xml|log)` (o lo que tu parser consume)
* `project_eval_out_v2/evidence/` (si lo empaquetás como evidencia precomputada) 

### “One‑shot” para evaluadores (recomendación)

Un script tipo:

* `bash tools/reproduce_paper_a.sh`
  que llame: `pytest`, `audit_min software`, `run_hw_gates`, `audit_min hardware`, `bench verify` B1/B3/B4, y deje resultados en `build/paper_a/`.

No es un claim; es ergonomía de artefacto.

---

## 6) Outline (≤12 headings) + figura/tabla que respalda cada heading

1. **Introduction**

   * *Figura:* “NEMA at a glance”: DSL/IR → verify → HLS/Vivado → bench_report (diagrama de pipeline).

2. **Problem Statement: Determinism & Reproducibility for Neural Graph Programs**

   * *Tabla:* “Failure modes we rule out” (nondeterminism, floating drift, mismatched tool outputs) y qué gate lo detecta.

3. **System Overview**

   * *Figura:* arquitectura por capas: DSL → IR → validator → sim → codegen → hwtest/audit.

4. **Deterministic Tick Semantics**

   * *Figura:* timeline de ticks + snapshotRule (qué se lee/escribe por tick).

5. **NEMA‑IR Contract and Validation**

   * *Tabla:* subset de campos IR usados en v0.1 y checks (qformat, schedule, graph external, etc.).

6. **Reference Implementations and Bit‑Exactness Strategy**

   * *Figura:* comparador golden vs C++ (digest pipeline: trace → hash → mismatch list).

7. **Hardware Compilation Pipeline**

   * *Figura:* HLS stages (csim/csynth/cosim si aplica) + Vivado impl + parsing a `bench_report`.

8. **Bench Suite and Methodology**

   * *Tabla:* suite: B1/B3/B4 (y B2/B5/B6 si aplica), con (N, E), ticks, y qué métricas produce.

9. **Evaluation: Correctness and Reproducibility Results**

   * *Tabla:* mismatch=0 y digestMatchOK para B1/B3/B4; repro run1==run2.

10. **Evaluation: Hardware Evidence (QoR/Timing)**

* *Tabla:* ii/latency/util + WNS (si existe) por benchmark y por part.

11. **Artifact and Self‑Audit Story**

* *Figura:* “artifact directory map” (scripts + outputs) +
* *Tabla:* comandos exactos y expected checks (exit code + JSON keys).

12. **Limitations and No‑Claims**

* *Tabla:* “What we do / do not claim” (incluye explícitamente “no on-board measurement” hasta tener placa). 

---

Si querés, el próximo paso “paper engineering” (sin escribir el paper todavía) es que definamos **un `tools/reproduce_paper_a.sh`** que produzca **todas las tablas del paper** como CSV/JSON (mismatch, digestMatch, ii/latency/util, WNS) y después recién pasamos a redacción. Esto convierte los claims en **artefacto‑driven** y te simplifica muchísimo PLDI/OOPSLA.
```
===== END CLAIMS =====

===== BEGIN ARTIFACT INDEX =====
Tablas:
- papers/paperA/artifacts/tables/gates_summary.csv
  preview:
    mode, ok, decision, toolchainHwAvailable, software_ok, hardware_ok, all_ok
    software, true, GO, True, True, True, True
    hardware, true, GO, True, True, True, True
- papers/paperA/artifacts/tables/gates_summary.md
  preview:
    | mode | ok | decision | toolchainHwAvailable | software_ok | hardware_ok | all_ok |
    |---|---|---|---|---|---|---|
    | software | true | GO | True | True | True | True |
    | hardware | true | GO | True | True | True | True |

Figuras:
- papers/paperA/artifacts/figures/gates_status.txt | caption: MISSING

Resumen audit_min:
- software: decision=GO path=papers/paperA/artifacts/evidence/audit_software.json
  - dslReady: True
  - digestMatchAll: True
  - benchVerifyOk: True
  - b3Evidence302_7500: True
  - graphCountsNormalized: True
- hardware: decision=GO path=papers/paperA/artifacts/evidence/audit_hardware.json
  - hardwareToolchainAvailable: True
  - hardwareEvidenceG0b: True
  - hardwareEvidenceG2: True
  - hardwareEvidenceG3: True
  - digestMatchAll: True

Benchmarks presentes + latest report paths:
- B1: manifest=YES (benches/B1_small/manifest.json)
  latest_report: build/audit_min/bench_verify/b1/example_b1_small_subgraph/bench_report.json ok=True modelId=example_b1_small_subgraph targetId=example_b1_small_subgraph/CE/2-1
- B3: manifest=YES (benches/B3_kernel_302_7500/manifest.json)
  latest_report: build/audit_min/bench_verify/b3/B3_kernel_302_7500/bench_report.json ok=True modelId=B3_kernel_302_7500 targetId=B3_kernel_302_7500/CE/302-7500
- B4: manifest=YES (benches/B4_real_connectome/manifest.json)
  latest_report: build/bench_verify_eqlozbf7/B4_celegans_external_bundle/bench_report.json ok=True modelId=B4_celegans_external_bundle targetId=B4_celegans_external_bundle/CE/8-12
- B2: manifest=YES (benches/B2_mid/manifest.json)
  latest_report: build/audit_min/bench_verify/b2/B2_mid_64_1024/bench_report.json ok=True modelId=B2_mid_64_1024 targetId=B2_mid_64_1024/CE/64-1024
- B5: manifest=NO (benches/B5_synthetic_family/manifest.json)
  latest_report: build/bench_verify_b5_family/B5_synth_96_1800_s503/bench_report.json ok=True modelId=B5_synth_96_1800_s503 targetId=B5_synth_96_1800_s503/CE/96-1800
- B6: manifest=YES (benches/B6_delay_small/manifest.json)
  latest_report: build_hw/b6/B6_delay_small/bench_report.json ok=True modelId=B6_delay_small targetId=B6_delay_small/CE/3-2
===== END ARTIFACT INDEX =====

===== BEGIN SPEC EXTRACTS =====
## rounding/overflow (SATURATE/RNE)
Lines 10-33:
   10: 
   11: ## 1. Scope
   12: 
   13: NEMA v0.1 defines:
   14: - IR contract (JSON shape mirrored by `nema_ir.proto`)
   15: - deterministic tick semantics (`nema.tick.v0.1`)
   16: - fixed-point behavior (RNE + saturation)
   17: - tanh LUT policy (`nema.tanh_lut.v0.1`)
   18: - bit-exact comparison criteria
   19: - G0 conformance checklist
   20: 
   21: ## 2. Numeric Model (Fixed-Point)
   22: 
   23: Overflow behavior:
   24: - `SATURATE` only.
   25: 
   26: Rounding behavior:
   27: - `RNE` (round to nearest, ties to even) only.
   28: 
   29: ### 2.1 Raw Domains
   30: 
   31: For signed fixed-point with `totalBits = T`:
   32: - raw min: `-(2^(T-1))`
   33: - raw max: `(2^(T-1)) - 1`

## tick semantics (snapshot/LUT/accum/Euler)
Lines 9-23:
    9: If implementation and this file disagree, update both plus regression tests in the same change.
   10: 
   11: ## 1. Scope
   12: 
   13: NEMA v0.1 defines:
   14: - IR contract (JSON shape mirrored by `nema_ir.proto`)
   15: - deterministic tick semantics (`nema.tick.v0.1`)
   16: - fixed-point behavior (RNE + saturation)
   17: - tanh LUT policy (`nema.tanh_lut.v0.1`)
   18: - bit-exact comparison criteria
   19: - G0 conformance checklist
   20: 
   21: ## 2. Numeric Model (Fixed-Point)
   22: 
   23: Overflow behavior:

Lines 56-70:
   56:   - logical right shift shifts bit-pattern
   57: - abs: if input is signed min value, saturate to signed max
   58: - cmp/mux/clip: deterministic with explicit ordering
   59: 
   60: Reference implementation: `nema/fixed.py`.
   61: 
   62: ## 3. Tanh LUT Policy (`nema.tanh_lut.v0.1`)
   63: 
   64: Generator: `tools/gen_tanh_lut.py`.
   65: 
   66: Input/Output type IDs:
   67: - accepted forms: `Q<int>.<frac>`, `UQ<int>.<frac>`
   68: - current simulator path requires `Q8.8 -> Q8.8`
   69: 
   70: Generation algorithm:

## bit-exact definition (digest)
Lines 12-24:
   12: 
   13: NEMA v0.1 defines:
   14: - IR contract (JSON shape mirrored by `nema_ir.proto`)
   15: - deterministic tick semantics (`nema.tick.v0.1`)
   16: - fixed-point behavior (RNE + saturation)
   17: - tanh LUT policy (`nema.tanh_lut.v0.1`)
   18: - bit-exact comparison criteria
   19: - G0 conformance checklist
   20: 
   21: ## 2. Numeric Model (Fixed-Point)
   22: 
   23: Overflow behavior:
   24: - `SATURATE` only.

Lines 133-145:
  133: - `graph.dt` optional; default `1.0` if missing
  134: - `tauM` must be positive (node-level if present, else graph-level default)
  135: 
  136: External references:
  137: - `graph.external` may be an object or array
  138: - referenced path/file must exist
  139: - if `sha256` is not a placeholder token, it must match file digest
  140: 
  141: ## 5. Tick Semantics (`nema.tick.v0.1`)
  142: 
  143: State format:
  144: - node voltage `V`: signed `Q8.8` (int16 raw)
  145: - activation `A`: signed `Q8.8`

Lines 169-183:
  169: Determinism requirements:
  170: - simulation node iteration is index-ordered
  171: - snapshot rule guarantees order-independent results for update ordering
  172: 
  173: Reference implementation: `nema/sim.py`.
  174: 
  175: ## 6. Bit-Exact Definition
  176: 
  177: Two executions are bit-exact equal when all per-tick digests match.
  178: 
  179: Digest computation:
  180: - collect `V` in node index order
  181: - pack each raw voltage as signed int16 little-endian
  182: - compute SHA-256 over packed byte array
  183:
===== END SPEC EXTRACTS =====

===== BEGIN IMPLEMENTATION SUMMARY =====
DSL v0.1/v0.2 modules present:
- nema/dsl/__init__.py: YES
- nema/dsl/lexer.py: YES
- nema/dsl/parser.py: YES
- nema/dsl/lower.py: YES
- nema/dsl/typecheck.py: YES
- nema/dsl/diagnostics.py: YES
- nema/dsl/catalog.py: YES
- nema/dsl/cli.py: YES

IR objects + invariants evidence:
- nema/ir_validate.py: YES
- nema_ir.proto: YES
- example_b1_small_subgraph.json: YES
- example_b3_kernel_302.json: YES
- Detected validator invariants:
  - unique node
  - unique edge
  - edge refs existing nodes
  - CHEMICAL directed / GAP symmetric
  - non-negative conductance
  - canonicalOrderId required
  - license.spdx in allowed list
  - graph.external verify file+sha256

hwtest pipeline evidence:
- nema/hwtest.py: YES
- nema/sim.py: YES
- nema/codegen/hls_gen.py: YES
- tools/bench_report_schema.json: YES
- tools/audit_min.py: YES
- Expected outputs (from repo conventions): bench_report.json, golden/digest.json, golden/trace.jsonl, hls/*, hw_reports/*
===== END IMPLEMENTATION SUMMARY =====

===== BEGIN MANIFEST SUMMARY =====
- git HEAD: bb17ac319debc7ee40a28f4502fe4189f0795ac5
- vivado: path=/home/tangodelta/.local/bin/vivado | version=vivado v2025.2 (64-bit)
- vitis_hls: path=/home/tangodelta/.local/bin/vitis_hls | version=Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2025.2 (64-bit)
- artifact_manifest.json sha256: 8d47388230839d28752477c2cdfa6acdfa609fd8989fe349d3c135d3a7ff0349 (papers/paperA/artifacts/artifact_manifest.json)
- counts.tables: 2
- counts.figures: 1
- counts.evidence: 2
===== END MANIFEST SUMMARY =====

MISSING:
- benches/B5_synthetic_family/manifest.json
