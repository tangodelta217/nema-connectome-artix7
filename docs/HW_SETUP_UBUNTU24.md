# NEMA HW Setup on Ubuntu 24.04

## Scope
This runbook is a practical baseline to prepare an Ubuntu 24.04 workstation for NEMA HW flows using Vivado/Vitis HLS.

## Recommended Toolchain
- Use the AMD Unified Installer release `2025.2`.
- This is recommended for NEMA HW lab setup because it includes Vivado and Vitis HLS in one installer flow.

## Capacity Planning (practical baseline)
- Disk:
  plan for about `200 GB` free for a full installation plus project outputs.
- RAM:
  use a high-memory workstation for synthesis and implementation workflows.
  (AMD documentation such as UG1742-style guidance generally recommends ample RAM for stable tool operation.)

## Manual Install Steps
1. Download the AMD Unified Installer package for the target release (2025.2).
2. Extract installer files.
3. Run the installer:
   - `./xsetup`
4. In component selection:
   - select only what is required for NEMA:
     - Vivado
     - Vitis HLS
5. Complete installation into your standard AMD tools path.

## Post-Install Checks
1. Activate Xilinx environment (standard step):
   - `source tools/hw/activate_xilinx.sh`
   - Optional pinning:
     - `export XILINX_ROOT=/tools/Xilinx`
     - `export XILINX_VERSION=2025.2`
     - `source tools/hw/activate_xilinx.sh`
   - After installing, find your actual `settings64.sh` and set:
     - `export XILINX_SETTINGS64=/absolute/path/to/settings64.sh`
     - `source tools/hw/activate_xilinx.sh`
2. Verify binaries:
   - `vivado -version`
   - `vitis_hls -version`
3. Run NEMA preflight:
   - `bash tools/hw/preflight_ubuntu24.sh`
4. Run HW gates runner:
   - `bash tools/run_hw_gates.sh`

## Cómo correr gates HW
1. Ejecuta el runner de gates HW:
   - `bash tools/run_hw_gates.sh`
2. Genera el checkpoint de evidencia:
   - `python tools/checkpoint_hw.py`
3. Revisa los outputs:
   - `checkpoint_hw_out/HW_STATUS.md`
   - `checkpoint_hw_out/nema_hw_checkpoint_bundle.tar.gz`

## Notes
- `tools/hw/preflight_ubuntu24.sh` is check-only and does not install or modify system packages.
- `tools/hw/install_checklist.sh` prints a manual installation checklist and post-install commands without installing anything.
- On Ubuntu 24.04, `libtinfo.so.5` may be missing by default; the preflight script prints suggested remediation commands without executing them.
- `tools/run_hw_gates.sh` requires a working toolchain activation and is intended for HW-capable lab machines.
