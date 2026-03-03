#!/bin/bash -eu

# Ensure runtime dependencies for python fuzz targets are available.
python3 -m pip install --no-cache-dir "atheris==3.0.0"

# Use the canonical OSS-Fuzz/ClusterFuzzLite python packaging helper so
# run_fuzzers can execute packaged targets with dependencies.
for fuzzer in $(find "$SRC/fuzz" -name '*_fuzzer.py'); do
  compile_python_fuzzer \
    "$fuzzer" \
    --paths "$SRC" \
    --hidden-import nema \
    --hidden-import nema.dsl \
    --hidden-import nema.dsl.parser
done
