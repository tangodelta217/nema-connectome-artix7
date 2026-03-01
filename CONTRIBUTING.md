# Contributing

## Workflow

1. Create a branch from `main` with a clear scope.
2. Keep changes minimal and deterministic.
3. Add or update tests for every semantic claim.
4. Open a PR with reproducible commands and expected outputs.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
pip install pytest
```

## Style and Quality Gates

- Follow the normative contract in `spec.md` and `nema_ir.proto`.
- Do not introduce nondeterministic behavior in CLI outputs or reports.
- Keep golden sim and HLS numerics aligned (same quantization/LUT policy).
- Prefer composable modules and explicit data flow.

## Tests

Run before opening a PR:

```bash
python -m pytest
python tools/audit_min.py --mode software
```

If touching hardware wrappers/scripts, include local evidence and command logs in the PR description, but do not require Vivado/Vitis in CI.

## Pull Request Checklist

- [ ] Scope is clear and limited.
- [ ] Tests added/updated and passing locally.
- [ ] No large generated binaries committed.
- [ ] Docs/readme/spec references updated when behavior changes.
- [ ] Reproduction commands included.
