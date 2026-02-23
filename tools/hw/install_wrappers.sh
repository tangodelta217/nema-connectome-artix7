#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

mkdir -p "${HOME}/.local/bin"

VITIS_TARGET="${HOME}/.local/bin/vitis_hls"
VITIS_SOURCE_WRAPPER="${REPO_ROOT}/tools/hw/vitis_hls_wrapper.sh"
VIVADO_TARGET="${HOME}/.local/bin/vivado"
VIVADO_SOURCE_WRAPPER="${REPO_ROOT}/tools/hw/vivado_wrapper.sh"

ln -sf "${VITIS_SOURCE_WRAPPER}" "${VITIS_TARGET}"
ln -sf "${VIVADO_SOURCE_WRAPPER}" "${VIVADO_TARGET}"

echo "Installed wrapper symlinks:"
echo "  ${VITIS_TARGET} -> ${VITIS_SOURCE_WRAPPER}"
echo "  ${VIVADO_TARGET} -> ${VIVADO_SOURCE_WRAPPER}"

case ":${PATH}:" in
  *":${HOME}/.local/bin:"*)
    echo "~/.local/bin is already in PATH."
    ;;
  *)
    echo "~/.local/bin is not in PATH."
    echo "Add it with:"
    echo "  export PATH=\"${HOME}/.local/bin:\$PATH\""
    ;;
esac
