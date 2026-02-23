#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

mkdir -p "${HOME}/.local/bin"

TARGET="${HOME}/.local/bin/vitis_hls"
SOURCE_WRAPPER="${REPO_ROOT}/tools/hw/vitis_hls_wrapper.sh"

ln -sf "${SOURCE_WRAPPER}" "${TARGET}"

echo "Installed wrapper symlink:"
echo "  ${TARGET} -> ${SOURCE_WRAPPER}"

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
