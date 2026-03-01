#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUTDIR="${1:-build/paperA_b3_vivado}"
TICKS="${TICKS:-2}"

mkdir -p "${OUTDIR}"

export PATH="$HOME/.local/bin:$PATH"

if [[ -f "tools/hw/activate_xilinx.sh" ]]; then
  # shellcheck disable=SC1091
  source "tools/hw/activate_xilinx.sh"
fi

if [[ -f "${OUTDIR}/B3_kernel_302_7500/bench_report.json" ]]; then
  export NEMA_B3_EXISTING_REPORT="${OUTDIR}/B3_kernel_302_7500/bench_report.json"
  if python - <<'PY'
import json
import os
from pathlib import Path

report_path = Path(os.environ["NEMA_B3_EXISTING_REPORT"])
obj = json.loads(report_path.read_text())
vivado = obj.get("hardware", {}).get("vivado", {})
wns = vivado.get("wns")
ok = bool(vivado.get("implOk") is True and isinstance(wns, (int, float)))
if ok:
    print(f"bench_report={report_path.resolve()}")
    print(f"vivado_attempted={vivado.get('attempted')}")
    print(f"vivado_implOk={vivado.get('implOk')}")
    print(f"vivado_wns={wns}")
    print(f"vivado_runLog={vivado.get('runLog')}")
raise SystemExit(0 if ok else 1)
PY
  then
    exit 0
  fi
fi

python -m nema hwtest example_b3_kernel_302.json \
  --ticks "${TICKS}" \
  --outdir "${OUTDIR}" \
  --hw require \
  --cosim off > "${OUTDIR}/hwtest.json"

export NEMA_B3_OUTDIR="${OUTDIR}"
python - <<'PY'
import json
import os
from pathlib import Path

outdir = Path(os.environ["NEMA_B3_OUTDIR"])
payload = json.loads((outdir / "hwtest.json").read_text())
bench_report = payload.get("bench_report")
if not isinstance(bench_report, str) or not bench_report:
    raise SystemExit("run_b3_vivado_impl: hwtest.json missing bench_report path")

bench_path = Path(bench_report)
if not bench_path.is_absolute():
    bench_path = (Path.cwd() / bench_path).resolve()
if not bench_path.exists():
    raise SystemExit(f"run_b3_vivado_impl: bench_report not found: {bench_path}")

report = json.loads(bench_path.read_text())
vivado = report.get("hardware", {}).get("vivado", {})
print(f"bench_report={bench_path}")
print(f"vivado_attempted={vivado.get('attempted')}")
print(f"vivado_implOk={vivado.get('implOk')}")
print(f"vivado_wns={vivado.get('wns')}")
print(f"vivado_runLog={vivado.get('runLog')}")
PY
