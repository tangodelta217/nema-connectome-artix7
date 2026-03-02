#!/bin/bash -eu

python3 -m pip install --no-cache-dir .
python3 -m pip install --no-cache-dir pyinstaller

for fuzzer in $(find "$SRC/fuzz" -name '*_fuzzer.py'); do
  fuzzer_basename=$(basename -s .py "$fuzzer")
  fuzzer_package="${fuzzer_basename}.pkg"

  pyinstaller --distpath "$OUT" --onefile --name "$fuzzer_package" "$fuzzer"

  cat > "$OUT/$fuzzer_basename" << EOF
#!/bin/sh
# LLVMFuzzerTestOneInput for fuzzer detection.
this_dir=\$(dirname "\$0")
\$this_dir/$fuzzer_package "\$@"
EOF
  chmod +x "$OUT/$fuzzer_basename"
done
