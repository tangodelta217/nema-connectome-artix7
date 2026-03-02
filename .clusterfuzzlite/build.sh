#!/bin/bash -eu

for fuzzer in $(find "$SRC/fuzz" -name '*_fuzzer.py'); do
  fuzzer_basename=$(basename -s .py "$fuzzer")
  cp "$fuzzer" "$OUT/${fuzzer_basename}.py"
  cat > "$OUT/$fuzzer_basename" << EOF
#!/bin/sh
# LLVMFuzzerTestOneInput for fuzzer detection.
PYTHONPATH="$SRC" python3 "$OUT/${fuzzer_basename}.py" "\$@"
EOF
  chmod +x "$OUT/$fuzzer_basename"
done
