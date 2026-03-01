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
