#!/bin/bash -eu

# Ensure runtime dependencies for python fuzz targets are available.
python3 -m pip install --no-cache-dir atheris
# Install project package in non-editable mode so PyInstaller bundles it.
python3 -m pip install --no-cache-dir "$SRC"

# Use the canonical OSS-Fuzz/ClusterFuzzLite python packaging helper so
# run_fuzzers can execute packaged targets with dependencies.
for fuzzer in $(find "$SRC/fuzz" -name '*_fuzzer.py'); do
  compile_python_fuzzer "$fuzzer"
done
