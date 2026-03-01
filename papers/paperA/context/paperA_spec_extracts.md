# Paper A Spec Extracts

Source: `spec.md`

## Rounding / Overflow (Fixed-Point)
- `spec.md:23-27`: overflow = `SATURATE`, rounding = `RNE`
- `spec.md:41-47`: RNE definition and right-shift rounding equivalence
- `spec.md:51-58`: required behavior for add/sub, mul/mac, shifts, abs, cmp/mux/clip

```text
Overflow behavior: SATURATE only. Rounding behavior: RNE only.
When quantizing: nearest; ties to even; then saturate to target raw domain.
```

## Tick Semantics (`nema.tick.v0.1`)
- `spec.md:148-167`: per-tick steps (snapshot, LUT activation, chemical/gap accumulation, Euler update)
- `spec.md:169-171`: determinism requirements (index-ordered iteration + snapshot rule)

```text
Per tick: snapshot V(t) -> A=tanh_lut(V_snapshot) -> accumulate I_chem/I_gap in Q12.8 ->
Euler update with inv_tau=dt/tau_m and saturating Q8.8 update.
```

## Bit-Exact Definition
- `spec.md:177-183`: bit-exact iff all per-tick digests match
- Digest = SHA-256 over packed int16 little-endian V array in node index order

```text
Two executions are bit-exact equal when all per-tick digests match.
Digest: pack V raw as signed int16 LE in index order, then SHA-256.
```
