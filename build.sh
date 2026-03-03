#!/bin/bash
set -euo pipefail

# ClusterFuzzLite compile phase expects /src/build.sh.
# Delegate to the repository-owned script under .clusterfuzzlite/.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${ROOT_DIR}/.clusterfuzzlite/build.sh" "$@"
