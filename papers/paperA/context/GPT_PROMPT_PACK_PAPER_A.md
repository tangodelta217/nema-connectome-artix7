# GPT Prompt Pack — Paper A (A3..A7)

Instrucción inicial (usar una sola vez):
Adjuntá `papers/paperA/context/GPT_INPUT_PAPER_A.md` a ChatGPT o pegalo una vez al inicio. Luego ejecutá los prompts A3..A7.

## GPT-A3 — Abstract / Intro / Contributions
Usá EXCLUSIVAMENTE el bloque INPUT (`GPT_INPUT_PAPER_A.md`).
Generá:
- Abstract (150–180 palabras, claims verificables únicamente).
- Introduction (~1 página).
- Contributions (3–5 bullets, cada bullet con evidencia/ruta).
No inventes resultados ni métricas fuera del INPUT.

## GPT-A4 — Semantics
Usá EXCLUSIVAMENTE el bloque INPUT (`GPT_INPUT_PAPER_A.md`).
Escribí sección de semántica operacional:
- Tick semantics v0.1 (snapshot rule, LUT, accum, Euler).
- Fixed-point (RNE + SATURATE).
- Definición operacional de bit-exactness y digests.
Incluí referencias directas a las líneas de `spec.md` provistas en el INPUT.

## GPT-A5 — Implementation + Artifact
Usá EXCLUSIVAMENTE el bloque INPUT (`GPT_INPUT_PAPER_A.md`).
Escribí sección de implementación:
- DSL/IR validator/hwtest pipeline (solo módulos existentes).
- Artifact contract: scripts, salidas, rutas, JSON fields clave.
- Reproducibility gates (software/hardware) usando audit summaries del INPUT.

## GPT-A6 — Evaluation
Usá EXCLUSIVAMENTE el bloque INPUT (`GPT_INPUT_PAPER_A.md`).
Escribí evaluación con tablas compactas:
- B1/B3/B4/B2/B5/B6 presentes + estado observado en INPUT.
- Correctness (mismatch/digestMatch) solo si está en INPUT.
- Hardware QoR/timing solo si está en INPUT.
Terminá con una subsección “What is NOT claimed”.

## GPT-A7 — Threats / Limitations / Appendix
Usá EXCLUSIVAMENTE el bloque INPUT (`GPT_INPUT_PAPER_A.md`).
Escribí:
- Threats to validity (artifact-, toolchain-, benchmark-related).
- Limitations explícitas (boardless constraints, missing artifacts).
- Appendix checklist reproducible (comandos + expected outputs).
Incluí TODO markers solo para ítems listados como MISSING en el INPUT.
