# Compile Report A4

## Build Status
- command: `make -C papers/paperA paper`
- make exit code: `0`
- PDF present: `false`
- status: `FAIL`

## Build Output (last 80 lines)
```text
make: Entering directory '/home/tangodelta/Escritorio/NEMA/papers/paperA'
latexmk not found in PATH.
Install TeX tooling, then run:
  latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=/home/tangodelta/Escritorio/NEMA/papers/paperA/text /home/tangodelta/Escritorio/NEMA/papers/paperA/text/paper.tex
make: Leaving directory '/home/tangodelta/Escritorio/NEMA/papers/paperA'
```

## Minimal Fix (LaTeX-only, no technical content changes)
- Missing dependency: `latexmk` not found in PATH.
- Suggested commands (not executed):
  - `sudo apt update`
  - `sudo apt install -y latexmk texlive-latex-extra texlive-publishers texlive-fonts-recommended`
  - `make -C papers/paperA paper`

## Sanity
- undefined refs/autorefs: 0
- undefined cites: 0
- figures referenced but missing: 0
- tables/inputs referenced but missing: 0
- TODO markers: 4
  - papers/paperA/text/sections/03_impl.tex:2: % @TODO: Describir ejecución técnica (sin texto final).
  - papers/paperA/text/sections/04_eval.tex:2: % @TODO: Evaluación de artefactos generados.
  - papers/paperA/text/sections/05_threats.tex:2: % @TODO: Riesgos y límites.
  - papers/paperA/text/sections/06_appendix.tex:3: % @TODO: Incluir comandos exactos del blueprint.

## Overall
- PASS: `false`
