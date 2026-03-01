#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def _as_pdf_token(value: str) -> str:
    token = value.strip()
    if token == "":
        return "-"
    return token


def _normalize_text(text: str) -> str:
    # Keep line breaks for line-based fallback; reduce repeated spaces.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _sequence_regex(tokens: Iterable[str]) -> re.Pattern[str]:
    cleaned = [t for t in tokens if t]
    # Allow wrapped rows / page boundaries while preventing unbounded accidental matches.
    pattern = r"[\s\S]{0,200}".join(re.escape(t) for t in cleaned)
    return re.compile(pattern)


@dataclass(frozen=True)
class CheckResult:
    table_name: str
    bench_id: str
    ok: bool
    detail: str


def _check_bitexact_rows(pdf_text: str, rows: list[dict[str, str]]) -> list[CheckResult]:
    out: list[CheckResult] = []
    for row in rows:
        bench = row.get("benchmarkId", "")
        if not bench:
            continue
        ir_sha = row.get("ir_sha256", "")
        tokens = [
            bench,
            row.get("modelId", ""),
            _as_pdf_token(row.get("verify_ok", "")),
            _as_pdf_token(row.get("mismatches_len", "")),
            _as_pdf_token(row.get("digestMatchOk", "")),
            _as_pdf_token(row.get("ticks", "")),
            ir_sha[:12] if ir_sha else "",
        ]
        rx = _sequence_regex(tokens)
        ok = bool(rx.search(pdf_text))
        detail = f"tokens={tokens}" if not ok else "matched"
        out.append(CheckResult("Table1_bitexact", bench, ok, detail))
    return out


def _check_qor_rows(pdf_text: str, rows: list[dict[str, str]]) -> list[CheckResult]:
    out: list[CheckResult] = []
    for row in rows:
        bench = row.get("benchmarkId", "")
        if not bench:
            continue
        reason = row.get("vivado_impl_reason", "")
        reason_hint = ""
        if reason:
            # Keep short hint robust to wrapping (e.g., "vitis_hls unavailable", "vivado impl failed").
            reason_hint = reason.split()[0]
        tokens = [
            bench,
            _as_pdf_token(row.get("ii", "")),
            _as_pdf_token(row.get("latencyCycles", "")),
            _as_pdf_token(row.get("wns", "")),
            _as_pdf_token(row.get("csim_ok", "")),
            _as_pdf_token(row.get("csynth_ok", "")),
            _as_pdf_token(row.get("cosim_ok", "")),
            _as_pdf_token(row.get("vivado_impl_ok", "")),
            _as_pdf_token(row.get("vivado_impl_status", "")),
            reason_hint,
        ]
        rx = _sequence_regex(tokens)
        ok = bool(rx.search(pdf_text))
        detail = f"tokens={tokens}" if not ok else "matched"
        out.append(CheckResult("Table2_qor", bench, ok, detail))
    return out


def _check_throughput_rows(pdf_text: str, rows: list[dict[str, str]]) -> list[CheckResult]:
    out: list[CheckResult] = []
    for row in rows:
        bench = row.get("benchmarkId", "")
        if not bench:
            continue
        tokens = [
            bench,
            _as_pdf_token(row.get("cpuTicksPerSecond", "")),
            _as_pdf_token(row.get("hwIiCyclesPerTick", "")),
            _as_pdf_token(row.get("fmaxMhzEstimated", "")),
            _as_pdf_token(row.get("hwTicksPerSecondEstimated", "")),
            _as_pdf_token(row.get("speedupEstimated", "")),
            _as_pdf_token(row.get("vivadoImplStatus", "")),
        ]
        rx = _sequence_regex(tokens)
        ok = bool(rx.search(pdf_text))
        detail = f"tokens={tokens}" if not ok else "matched"
        out.append(CheckResult("Table3_throughput", bench, ok, detail))
    return out


def _render_report(
    report_path: Path,
    pdf_path: Path,
    bit_csv: Path,
    qor_csv: Path,
    thr_csv: Path,
    results: list[CheckResult],
) -> None:
    total = len(results)
    failures = [r for r in results if not r.ok]
    status = "PASS" if not failures else "FAIL"

    lines: list[str] = []
    lines.append("# PDF vs Tables Consistency Report")
    lines.append("")
    lines.append(f"- Status: **{status}**")
    lines.append(f"- Total checks: {total}")
    lines.append(f"- Failed checks: {len(failures)}")
    lines.append(f"- PDF: `{pdf_path}`")
    lines.append(f"- Table 1 CSV: `{bit_csv}`")
    lines.append(f"- Table 2 CSV: `{qor_csv}`")
    lines.append(f"- Table 3 CSV: `{thr_csv}`")
    lines.append("")
    lines.append("| table | bench | status | detail |")
    lines.append("|---|---|---|---|")
    for r in results:
        lines.append(f"| {r.table_name} | {r.bench_id} | {'PASS' if r.ok else 'FAIL'} | {r.detail} |")

    if failures:
        lines.append("")
        lines.append("## Failures")
        for f in failures:
            lines.append(f"- {f.table_name} {f.bench_id}: {f.detail}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that Paper A PDF table rows match generated CSV tables.")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path("papers/paperA/submission/paperA.pdf"),
        help="Paper PDF to inspect via pdftotext.",
    )
    parser.add_argument(
        "--bitexact-csv",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_bitexact.csv"),
    )
    parser.add_argument(
        "--qor-csv",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_qor.csv"),
    )
    parser.add_argument(
        "--throughput-csv",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_throughput.csv"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("papers/paperA/submission/CONSISTENCY_REPORT.md"),
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    pdf_path = (repo_root / args.pdf).resolve() if not args.pdf.is_absolute() else args.pdf.resolve()
    bit_csv = (repo_root / args.bitexact_csv).resolve() if not args.bitexact_csv.is_absolute() else args.bitexact_csv.resolve()
    qor_csv = (repo_root / args.qor_csv).resolve() if not args.qor_csv.is_absolute() else args.qor_csv.resolve()
    thr_csv = (repo_root / args.throughput_csv).resolve() if not args.throughput_csv.is_absolute() else args.throughput_csv.resolve()
    report_path = (repo_root / args.report).resolve() if not args.report.is_absolute() else args.report.resolve()

    for req in (pdf_path, bit_csv, qor_csv, thr_csv):
        if not req.exists():
            print(f"ERROR: missing required file: {req}", file=sys.stderr)
            return 2

    if subprocess.run(["bash", "-lc", "command -v pdftotext >/dev/null 2>&1"]).returncode != 0:
        print("ERROR: pdftotext not found in PATH.", file=sys.stderr)
        return 3

    txt_path = report_path.with_suffix(".pdf.txt")
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
        check=True,
    )
    pdf_text = _normalize_text(txt_path.read_text(encoding="utf-8", errors="ignore"))

    bit_rows = _read_csv_rows(bit_csv)
    qor_rows = _read_csv_rows(qor_csv)
    thr_rows = _read_csv_rows(thr_csv)

    results: list[CheckResult] = []
    results.extend(_check_bitexact_rows(pdf_text, bit_rows))
    results.extend(_check_qor_rows(pdf_text, qor_rows))
    results.extend(_check_throughput_rows(pdf_text, thr_rows))

    _render_report(
        report_path=report_path,
        pdf_path=pdf_path,
        bit_csv=bit_csv,
        qor_csv=qor_csv,
        thr_csv=thr_csv,
        results=results,
    )

    failed = [r for r in results if not r.ok]
    if failed:
        print(f"Wrote {report_path} with {len(failed)} failure(s).", file=sys.stderr)
        return 1
    print(f"Wrote {report_path} (PASS).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
