# Verification Contract (Normalized Path)

Status: normalized from existing canonical sources in this repository.

Canonical source(s):
- `spec/spec.md` (derived copy of root `spec.md`)
- `nema_ir.proto`
- `tools/audit_min.py`
- `tools/independent_check.py`
- `docs/ARTIX7_EXECUTION.md`

## Core verification surfaces

- Bit-exact semantics and digest contract: `spec/spec.md`.
- IR schema/version contract: `nema_ir.proto`.
- Gate-level evidence aggregation: `tools/audit_min.py`.
- Independent consistency checker: `tools/independent_check.py`.
- Boardless Artix-7 execution procedure: `docs/ARTIX7_EXECUTION.md`.

## Required distinction

- Boardless AMD evidence is verification evidence.
- Board measurement claims require explicit measured artifacts (`MEASURED_ON_BOARD`).

## Provenance

This file is a path-normalization adapter requested by contract prompts.
No new semantics were introduced here.
