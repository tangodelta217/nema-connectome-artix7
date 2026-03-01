OBJETIVO
========
Generar un handoff limpio para GPT-A2 creando:
  - papers/paperA/artifacts/index_for_gpt.md
  - papers/paperA/artifacts/manifest_summary.json
y al final imprimir SOLO:
  - cat papers/paperA/artifacts/index_for_gpt.md
  - cat papers/paperA/artifacts/manifest_summary.json

REGLAS
======
- No imprimir nada más (ni banners, ni logs). Si algo falta, fallar con error claro.
- Usar el estado del repo (git hash actual) y los artefactos existentes.
- Incluir en index_for_gpt.md: git hash, scope, tablas, figuras, resumen audit_min (decision + 5 criterios clave por modo), warnings/limitaciones si existen.
- En manifest_summary.json: toolchain versions (vivado/vitis_hls), sha256 del artifact_manifest.json, conteo de archivos en evidence/tables/figures.
- Toolchain versions: usar PATH con $HOME/.local/bin primero (wrappers), sin imprimir logs.

EJECUCIÓN (desde repo root)
===========================
Ejecutá estos comandos exactamente:

set -euo pipefail

# 0) Ir al repo root (silencioso)
cd "$(git rev-parse --show-toplevel)"

# 1) Directorios del artifact pack
mkdir -p papers/paperA/artifacts/{evidence,tables,figures}

# 2) Asegurar evidencia mínima de audit en el artifact pack (copiar si existe)
#    (No imprime nada si no existe; el Python de abajo valida que haya al menos uno por modo.)
for src in \
  project_eval_out_v2/evidence/audit_mode_software.json \
  project_eval_out_v2/evidence/audit_mode_hardware.json \
  project_eval_out/evidence/audit_mode_software.json \
  project_eval_out/evidence/audit_mode_hardware.json \
  build_hw/audit_min_hardware.json \
  build/audit_min_software.json \
; do
  if [[ -f "$src" ]]; then
    bn="$(basename "$src")"
    # normalizar nombres esperados dentro del pack si vienen con nombres distintos
    if [[ "$bn" == "audit_min_software.json" ]]; then bn="audit_mode_software.json"; fi
    if [[ "$bn" == "audit_min_hardware.json" ]]; then bn="audit_mode_hardware.json"; fi
    cp -f "$src" "papers/paperA/artifacts/evidence/$bn"
  fi
done

# 3) Generar index_for_gpt.md + manifest_summary.json (sin stdout)
python3 - <<'PY'
from __future__ import annotations
import hashlib, json, os, subprocess
from pathlib import Path
from datetime import datetime, timezone

root = Path(subprocess.check_output(["git","rev-parse","--show-toplevel"], text=True).strip())
os.chdir(root)

art_dir = root / "papers/paperA/artifacts"
ev_dir  = art_dir / "evidence"
tb_dir  = art_dir / "tables"
fg_dir  = art_dir / "figures"

index_md = art_dir / "index_for_gpt.md"
manifest_summary = art_dir / "manifest_summary.json"
artifact_manifest = art_dir / "artifact_manifest.json"

def rel(p: Path) -> str:
    return p.relative_to(root).as_posix()

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def list_files(d: Path) -> list[Path]:
    if not d.exists():
        return []
    return sorted([p for p in d.rglob("*") if p.is_file()])

def run_clean(cmd: str) -> tuple[int, str]:
    # clean-ish shell: prioriza wrappers en ~/.local/bin
    full = f'export PATH="$HOME/.local/bin:$PATH"; {cmd}'
    p = subprocess.run(["bash","-lc", full], capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out.strip()

def tool_info(tool: str) -> dict:
    rc, path_out = run_clean(f"command -v {tool} || true")
    tool_path = path_out.splitlines()[-1].strip() if path_out.strip() else None
    version_line = None
    if tool_path:
        rc2, ver_out = run_clean(f'{tool} -version || true')
        lines = [ln.strip() for ln in ver_out.splitlines() if ln.strip()]
        # elegir primera línea "real" que no sea "command not found"
        if lines:
            version_line = lines[0]
            if "command not found" in version_line.lower():
                version_line = None
    return {"path": tool_path, "version": version_line}

def load_json(p: Path) -> dict:
    return json.loads(p.read_text())

def pick_5(criteria: dict, preferred: list[str]) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    used = set()
    for k in preferred:
        if k in criteria and k not in used:
            out.append((k, criteria[k]))
            used.add(k)
        if len(out) == 5:
            return out
    # completar con otras keys ordenadas
    for k in sorted(criteria.keys()):
        if k not in used:
            out.append((k, criteria[k]))
            used.add(k)
        if len(out) == 5:
            break
    return out

# --- Validaciones mínimas ---
if not artifact_manifest.exists():
    raise SystemExit(f"FATAL: falta {rel(artifact_manifest)} (se requiere para sha256).")

# Audit paths dentro del pack
sw_audit = ev_dir / "audit_mode_software.json"
hw_audit = ev_dir / "audit_mode_hardware.json"
if not sw_audit.exists():
    raise SystemExit(f"FATAL: falta {rel(sw_audit)}. Copiá/creá audit_min software dentro de papers/paperA/artifacts/evidence/.")
if not hw_audit.exists():
    raise SystemExit(f"FATAL: falta {rel(hw_audit)}. Copiá/creá audit_min hardware dentro de papers/paperA/artifacts/evidence/.")

sw = load_json(sw_audit)
hw = load_json(hw_audit)

git_hash = subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip()

# toolchain versions
vivado = tool_info("vivado")
vitis_hls = tool_info("vitis_hls")

# sha256 manifest
manifest_sha = sha256_file(artifact_manifest)

# counts
counts = {
    "evidence": len(list_files(ev_dir)),
    "tables":   len(list_files(tb_dir)),
    "figures":  len(list_files(fg_dir)),
}

# tables/figures lists
tables = [rel(p) for p in list_files(tb_dir)]
figures = [rel(p) for p in list_files(fg_dir)]

# audit summary: decision + 5 criterios clave
sw_criteria = sw.get("criteria", {}) if isinstance(sw.get("criteria", {}), dict) else {}
hw_criteria = hw.get("criteria", {}) if isinstance(hw.get("criteria", {}), dict) else {}

sw_pref = ["dslReady","digestMatchAll","benchVerifyOk","b3Evidence302_7500","graphCountsNormalized"]
hw_pref = ["hardwareToolchainAvailable","hardwareEvidenceG0b","hardwareEvidenceG2","hardwareEvidenceG3","digestMatchAll"]

sw_top5 = pick_5(sw_criteria, sw_pref)
hw_top5 = pick_5(hw_criteria, hw_pref)

# warnings/limitaciones (audit)
warnings = []
for src in (sw, hw):
    for k in ("warnings","reasons","loadErrors","ignoredReports"):
        v = src.get(k)
        if v:
            warnings.append({k: v})

# scope (hardcodeado por decisión editorial; esto es handoff de Paper A)
scope_lines = [
    "- Core:",
    "    - B1 -> benches/B1_small/manifest.json",
    "    - B3 -> benches/B3_kernel_302_7500/manifest.json",
    "    - B4 -> benches/B4_real_connectome/manifest.json",
    "- Extensión:",
    "    - B2/B5 (QoR diversity) y B6 (delays) como extensión/apéndice",
]

# index_for_gpt.md
md = []
md.append("# Paper A -> GPT-A2 Handoff Index")
md.append("")
md.append("## Git hash")
md.append("")
md.append(git_hash)
md.append("")
md.append("## Scope decisions (benchmarks incluidos)")
md.append("")
md.extend(scope_lines)
md.append("")
md.append("## Tablas generadas")
md.append("")
if tables:
    for p in tables:
        md.append(f"- {p}")
else:
    md.append("- (none found under papers/paperA/artifacts/tables/)")
md.append("")
md.append("## Figuras generadas")
md.append("")
if figures:
    for p in figures:
        md.append(f"- {p}")
else:
    md.append("- (none found under papers/paperA/artifacts/figures/)")
md.append("")
md.append("## audit_min summary")
md.append("")
md.append(f"- software.decision: {sw.get('decision')}")
for k,v in sw_top5:
    md.append(f"    - software.criteria.{k}: {v}")
md.append(f"- hardware.decision: {hw.get('decision')}")
for k,v in hw_top5:
    md.append(f"    - hardware.criteria.{k}: {v}")
md.append("")
md.append("## Warnings / limitaciones")
md.append("")
if warnings:
    md.append("- Warnings/notes detectadas en audit JSON:")
    for item in warnings:
        md.append(f"    - {json.dumps(item, ensure_ascii=False)[:2000]}")
else:
    md.append("- No warnings/reasons reported by current audit outputs.")
md.append("")

index_md.write_text("\n".join(md), encoding="utf-8")

# manifest_summary.json
summary = {
    "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
    "git": {"head": git_hash},
    "artifactManifest": {
        "path": rel(artifact_manifest),
        "sha256": manifest_sha,
    },
    "counts": counts,
    "toolchainVersions": {
        "vitis_hls": vitis_hls,
        "vivado": vivado,
    },
}

manifest_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

# 4) IMPRIMIR SOLO lo pedido
cat papers/paperA/artifacts/index_for_gpt.md
cat papers/paperA/artifacts/manifest_summary.json
