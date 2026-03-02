#!/usr/bin/env python3
"""Build final reviewer-proof release artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

RELEASE_DIR = ROOT / "release"
PAPER_DIR = ROOT / "paper"
PAPER_TEX = PAPER_DIR / "paper.tex"
PAPER_PDF = PAPER_DIR / "paper.pdf"
PAPER_REFS = PAPER_DIR / "refs.bib"

DOCS_DIR = ROOT / "docs"
DOC_GATE = DOCS_DIR / "GATE_STATUS.md"
DOC_POWER = DOCS_DIR / "POWER_METHODOLOGY.md"
DOC_REPRO = DOCS_DIR / "REPRODUCE.md"

TABLES_DIR = ROOT / "review_pack" / "tables"
QOR_CSV = TABLES_DIR / "artix7_qor_v6.csv"
POWER_CSV = TABLES_DIR / "artix7_power_v7_funcsaif.csv"
METRICS_CSV = TABLES_DIR / "artix7_metrics_final.csv"
QOR_TEX = TABLES_DIR / "artix7_qor_v6.tex"
POWER_TEX = TABLES_DIR / "artix7_power_v7_funcsaif.tex"
METRICS_TEX = TABLES_DIR / "artix7_metrics_final.tex"
HLS_TEX = TABLES_DIR / "artix7_hls_digest_summary_strict_v2.tex"
HLS_CSV = TABLES_DIR / "artix7_hls_digest_summary_strict_v2.csv"

VIVADO_ROOT = ROOT / "build" / "amd_vivado_artix7_v5"
VIVADO_SUMMARY = VIVADO_ROOT / "summary.json"
POWER_ROOT = ROOT / "build" / "amd_power_artix7_v7_funcsaif"
POWER_SUMMARY = POWER_ROOT / "summary.json"

B3_STATUS = ROOT / "build" / "handoff" / "B3_CANONICAL_STATUS.json"
DATASET_RAW = ROOT / "datasets" / "raw" / "varshney" / "NeuronConnectFormatted.xlsx"

ARTIFACT_BUNDLE = RELEASE_DIR / "artifact_bundle_final.tar.gz"
SHA_FILE = RELEASE_DIR / "SHA256SUMS.txt"
FINAL_STATUS_MD = RELEASE_DIR / "FINAL_STATUS.md"
FINAL_STATUS_JSON = RELEASE_DIR / "FINAL_STATUS.json"
REVIEWER_GUIDE = RELEASE_DIR / "REVIEWER_GUIDE.md"
DATASET_SHA_FILE = RELEASE_DIR / "DATASET_SHA256.txt"

FINAL_CHATGPT_TAR = ROOT / "handoff_final_for_chatgpt.tar.gz"
FINAL_CHATGPT_SHA = ROOT / "handoff_final_for_chatgpt.sha256"

TARGET_PART = "xc7a200tsbg484-1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def _must_exist(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path}")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _gate_status(md_text: str, gate_id: str) -> str:
    m = re.search(rf"\|\s*{re.escape(gate_id)}[^|]*\|\s*`([^`]+)`\s*\|", md_text)
    return m.group(1) if m else "UNKNOWN"


def _tool_version(cmd: list[str]) -> str:
    proc = _run(cmd)
    txt = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    first = ""
    for line in txt.splitlines():
        s = line.strip()
        if s:
            first = s
            break
    return first or f"UNAVAILABLE (rc={proc.returncode})"


def _write_paper_arxiv_style() -> None:
    _must_exist(QOR_TEX)
    _must_exist(POWER_TEX)
    _must_exist(METRICS_TEX)
    _must_exist(HLS_TEX)

    bib = "\n".join(
        [
            "@misc{xilinx_vivado_2025_2,",
            "  title        = {Vivado Design Suite 2025.2 Documentation},",
            "  author       = {{Advanced Micro Devices}},",
            "  year         = {2025},",
            "  note         = {Toolchain used for implementation and report\\_power evidence}",
            "}",
            "",
            "@misc{xilinx_vitis_hls_2025_2,",
            "  title        = {Vitis HLS 2025.2 Documentation},",
            "  author       = {{Advanced Micro Devices}},",
            "  year         = {2025},",
            "  note         = {Toolchain used for HLS synthesis/cosim evidence}",
            "}",
            "",
            "@misc{nema_spec_v01,",
            "  title        = {NEMA v0.1 Spec and IR Contract},",
            "  author       = {{NEMA Project}},",
            "  year         = {2026},",
            "  note         = {Repository-local normative files: spec.md and nema\\_ir.proto}",
            "}",
            "",
        ]
    )
    _write(PAPER_REFS, bib + "\n")

    tex = "\n".join(
        [
            "\\documentclass[11pt]{article}",
            "\\usepackage[margin=1in]{geometry}",
            "\\usepackage[T1]{fontenc}",
            "\\usepackage[utf8]{inputenc}",
            "\\usepackage{lmodern}",
            "\\usepackage{booktabs}",
            "\\usepackage{hyperref}",
            "\\title{NEMA v0.1: Reviewer-Proof Pre-Board Release (Round10b Functional-SAIF)}",
            "\\author{}",
            "\\date{\\today}",
            "",
            "\\begin{document}",
            "\\maketitle",
            "",
            "\\begin{abstract}",
            "This release documents deterministic NEMA v0.1 evidence from IR through HLS, Vivado post-route QoR, and SAIF-guided power estimates. ",
            "All quantitative values are consumed from generated CSV/JSON artifacts (no manual hardcoding). ",
            "Power and energy are explicitly \\texttt{ESTIMATED\\_PRE\\_BOARD\\_ONLY}; no board measurement claim is made.",
            "\\end{abstract}",
            "",
            "\\section{Semantics and Contract}",
            "Numerics and tick semantics follow repository-normative artifacts (\\texttt{spec.md}, \\texttt{nema\\_ir.proto}) \\cite{nema_spec_v01}. ",
            "Conformance claims in this release are bounded by those contracts and by generated evidence paths listed in \\texttt{release/FINAL\\_STATUS.json}.",
            "",
            "\\section{Compiler and Deterministic Toolchain}",
            "The pipeline is deterministic by construction: IR $\\rightarrow$ golden CPU simulator $\\rightarrow$ HLS kernel $\\rightarrow$ Vivado post-route reports. ",
            "Toolchain versions are captured in release manifests and aligned with Vivado/Vitis HLS 2025.2 \\cite{xilinx_vivado_2025_2,xilinx_vitis_hls_2025_2}.",
            "",
            "\\section{Hardware Flow (Artix-7)}",
            "Post-route QoR evidence is sourced from existing Round8 implementation reports on part \\texttt{xc7a200tsbg484-1}. ",
            "Canonical QoR reflects the verified post-route report set (Slice LUTs, Slice Registers, Block RAM Tile, DSPs).",
            "",
            "\\section{Verification and Conformance}",
            "Gate status and closure rationale are synchronized in \\texttt{docs/GATE\\_STATUS.md}. ",
            "Canonical B3 identity is traced via \\texttt{build/handoff/B3\\_CANONICAL\\_STATUS.json}.",
            "",
            "\\section{Evaluation (Pre-Board)}",
            "Tables below are generated from canonical Round10b functional-SAIF CSV artifacts.",
            "",
            "\\subsection{HLS Digest Parity}",
            "\\begin{table}[h]",
            "\\centering",
            "\\small",
            "\\input{../review_pack/tables/artix7_hls_digest_summary_strict_v2.tex}",
            "\\caption{Generated from strict digest summary CSV.}",
            "\\end{table}",
            "",
            "\\subsection{Post-Route QoR}",
            "\\begin{table}[h]",
            "\\centering",
            "\\small",
            "\\input{../review_pack/tables/artix7_qor_v6.tex}",
            "\\caption{Generated from \\texttt{review\\_pack/tables/artix7\\_qor\\_v6.csv}.}",
            "\\end{table}",
            "",
            "\\subsection{Power Sensitivity}",
            "\\begin{table}[h]",
            "\\centering",
            "\\small",
            "\\input{../review_pack/tables/artix7_power_v7_funcsaif.tex}",
            "\\caption{Generated from \\texttt{review\\_pack/tables/artix7\\_power\\_v7\\_funcsaif.csv}.}",
            "\\end{table}",
            "",
            "\\subsection{Derived Throughput and Energy}",
            "\\begin{table}[h]",
            "\\centering",
            "\\small",
            "\\input{../review_pack/tables/artix7_metrics_final.tex}",
            "\\caption{Generated from \\texttt{review\\_pack/tables/artix7\\_metrics\\_final.csv}.}",
            "\\end{table}",
            "",
            "\\paragraph{Pre-board disclaimer.}",
            "All power/energy values are \\texttt{ESTIMATED\\_PRE\\_BOARD\\_ONLY}.",
            "",
            "\\paragraph{Functional SAIF limitation.}",
            "SAIF activity is produced with a functional post-route harness using DUT scope capture (\\texttt{/tb\\_tick/dut/*}); values remain suitable for comparative pre-board estimation and not for board-measured claims.",
            "",
            "\\section{Threats to Validity}",
            "Key threats are (i) functional simulation stimulus representativity, (ii) absence of measured board telemetry, and (iii) dependence on host toolchain versions. ",
            "These are recorded explicitly in \\texttt{docs/POWER\\_METHODOLOGY.md} and release manifests.",
            "",
            "\\section{Reproducibility}",
            "Reproduction entry points:",
            "\\begin{itemize}",
            "\\item Verify hashes: \\texttt{sha256sum -c release/SHA256SUMS.txt}",
            "\\item Evidence navigation: \\texttt{release/REVIEWER\\_GUIDE.md}",
            "\\item Gate/status machine-readable manifest: \\texttt{release/FINAL\\_STATUS.json}",
            "\\end{itemize}",
            "",
            "\\bibliographystyle{plain}",
            "\\bibliography{refs}",
            "",
            "\\end{document}",
            "",
        ]
    )
    _write(PAPER_TEX, tex)


def _compile_paper() -> None:
    latexmk = shutil.which("latexmk")
    if latexmk is None:
        raise RuntimeError("latexmk not found")
    proc = _run([latexmk, "-pdf", "-interaction=nonstopmode", "paper.tex"], cwd=PAPER_DIR)
    _write(PAPER_DIR / "latexmk_final_release.stdout.log", proc.stdout)
    _write(PAPER_DIR / "latexmk_final_release.stderr.log", proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError("latexmk failed; see paper/latexmk_final_release.*.log")
    _must_exist(PAPER_PDF)


def _write_docs_reproduce() -> None:
    text = "\n".join(
        [
            "# Reproduce Round10b Functional-SAIF Release",
            "",
            "## Preconditions",
            "",
            "- Vivado 2025.2 and Vitis HLS 2025.2 available in PATH.",
            "- Existing canonical evidence directories present under `build/`.",
            "",
            "## One-command verification (integrity)",
            "",
            "```bash",
            "sha256sum -c release/SHA256SUMS.txt",
            "```",
            "",
            "## Reference artifacts",
            "",
            "- Gate status: `docs/GATE_STATUS.md`",
            "- Power methodology: `docs/POWER_METHODOLOGY.md`",
            "- Reviewer guide: `release/REVIEWER_GUIDE.md`",
            "",
        ]
    )
    _write(DOC_REPRO, text + "\n")


def _collect_vivado_evidence_paths() -> list[Path]:
    out = [VIVADO_SUMMARY]
    for rpt in sorted(VIVADO_ROOT.glob("*/post_route_timing.rpt")):
        out.append(rpt)
    for rpt in sorted(VIVADO_ROOT.glob("*/post_route_utilization.rpt")):
        out.append(rpt)
    return out


def _collect_power_evidence_paths() -> list[Path]:
    out = [POWER_SUMMARY]
    for bench_dir in sorted([p for p in POWER_ROOT.iterdir() if p.is_dir()]):
        for pat in (
            "activity_*.saif",
            "power_saif_*.rpt",
            "power_vectorless.rpt",
            "read_saif_*.log",
        ):
            out.extend(sorted(bench_dir.glob(pat)))
        logs = bench_dir / "logs"
        if logs.exists():
            out.append(logs)
    return out


def _build_artifact_bundle(dataset_included: bool) -> None:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    include: list[Path] = []
    include.append(PAPER_DIR)
    include.append(DOCS_DIR)
    include.append(TABLES_DIR)
    include.extend(_collect_vivado_evidence_paths())
    include.extend(_collect_power_evidence_paths())
    include.append(B3_STATUS)
    if dataset_included:
        include.append(DATASET_RAW)
        include.append(DATASET_SHA_FILE)

    with tarfile.open(ARTIFACT_BUNDLE, "w:gz") as tar:
        for p in include:
            if not p.exists():
                continue
            tar.add(p, arcname=_rel(p))


def _write_sha256s(dataset_included: bool) -> None:
    rows: list[tuple[str, str]] = []
    rows.append((_sha256(PAPER_PDF), _rel(PAPER_PDF)))
    rows.append((_sha256(ARTIFACT_BUNDLE), _rel(ARTIFACT_BUNDLE)))
    for csv_path in sorted(TABLES_DIR.glob("*.csv")):
        rows.append((_sha256(csv_path), _rel(csv_path)))
    if dataset_included:
        rows.append((_sha256(DATASET_RAW), _rel(DATASET_RAW)))

    lines = [f"{digest}  {rel}" for digest, rel in rows]
    _write(SHA_FILE, "\n".join(lines) + "\n")


def _write_final_status(dataset_included: bool, dataset_sha: str | None) -> None:
    gate_md = DOC_GATE.read_text(encoding="utf-8")
    gate_g1b = _gate_status(gate_md, "G1b")
    gate_g1c = _gate_status(gate_md, "G1c")
    gate_g1d = _gate_status(gate_md, "G1d")

    vivado_summary = _load_json(VIVADO_SUMMARY)
    power_summary = _load_json(POWER_SUMMARY)

    vivado_version = _tool_version(
        ["/media/tangodelta/Vivado/2025.2/Vivado/bin/vivado", "-version"]
    )
    vitis_hls_version = _tool_version(["vitis_hls", "-version"])

    status_json: dict[str, Any] = {
        "generatedAtUtc": _now(),
        "releaseProfile": {
            "id": "round10b_funcsaif",
            "canonical": True,
            "path": "release/profiles/round10b_funcsaif/profile.json",
        },
        "targetPart": vivado_summary.get("targetPart") or TARGET_PART,
        "gates": {
            "G1b": gate_g1b,
            "G1c": gate_g1c,
            "G1d": gate_g1d,
        },
        "toolVersions": {
            "vivado": vivado_version,
            "vitis_hls": vitis_hls_version,
        },
        "evidence": {
            "gateStatusDoc": _rel(DOC_GATE),
            "powerMethodologyDoc": _rel(DOC_POWER),
            "hlsDigestCsv": _rel(HLS_CSV),
            "hlsDigestTex": _rel(HLS_TEX),
            "qorCsv": _rel(QOR_CSV),
            "qorTex": _rel(QOR_TEX),
            "powerCsv": _rel(POWER_CSV),
            "powerTex": _rel(POWER_TEX),
            "metricsCsv": _rel(METRICS_CSV),
            "metricsTex": _rel(METRICS_TEX),
            "vivadoSummary": _rel(VIVADO_SUMMARY),
            "powerSummary": _rel(POWER_SUMMARY),
            "b3CanonicalStatus": _rel(B3_STATUS),
            "postRouteTimingReports": [
                _rel(p) for p in sorted(VIVADO_ROOT.glob("*/post_route_timing.rpt"))
            ],
            "postRouteUtilReports": [
                _rel(p) for p in sorted(VIVADO_ROOT.glob("*/post_route_utilization.rpt"))
            ],
            "saifFunctional": [_rel(p) for p in sorted(POWER_ROOT.glob("*/activity_func.saif"))],
            "powerSaifFunctionalReports": [
                _rel(p) for p in sorted(POWER_ROOT.glob("*/power_saif_func.rpt"))
            ],
        },
        "limits": [
            "No board measurement is claimed.",
            "Power/energy remain ESTIMATED_PRE_BOARD_ONLY.",
            "SAIF activity uses functional xsim harness (/tb_tick/dut/*) and is not board traffic.",
        ],
        "dataset": {
            "included": dataset_included,
            "path": _rel(DATASET_RAW) if dataset_included else None,
            "sha256": dataset_sha,
        },
        "releaseArtifacts": {
            "artifactBundle": _rel(ARTIFACT_BUNDLE),
            "sha256Sums": _rel(SHA_FILE),
            "paperPdf": _rel(PAPER_PDF),
        },
        "powerEstimatedOnly": bool(power_summary.get("estimatedOnly")),
        "powerMeasuredOnBoard": bool(power_summary.get("measuredOnBoard")),
    }

    _write(FINAL_STATUS_JSON, json.dumps(status_json, indent=2, ensure_ascii=False) + "\n")

    md = "\n".join(
        [
            "# Final Status (Reviewer-Proof)",
            "",
            f"- Generated at UTC: `{status_json['generatedAtUtc']}`",
            f"- Part: `{status_json['targetPart']}`",
            f"- Gates: `G1b={gate_g1b}`, `G1c={gate_g1c}`, `G1d={gate_g1d}`",
            f"- Vivado: `{vivado_version}`",
            f"- Vitis HLS: `{vitis_hls_version}`",
            "",
            "## Evidence anchors",
            "",
            f"- Gate status doc: `{_rel(DOC_GATE)}`",
            f"- Power methodology doc: `{_rel(DOC_POWER)}`",
            f"- QoR table: `{_rel(QOR_CSV)}`",
            f"- Power table: `{_rel(POWER_CSV)}`",
            f"- Metrics table: `{_rel(METRICS_CSV)}`",
            f"- Vivado summary: `{_rel(VIVADO_SUMMARY)}`",
            f"- Power summary: `{_rel(POWER_SUMMARY)}`",
            f"- B3 canonical status: `{_rel(B3_STATUS)}`",
            "",
            "## Limits",
            "",
            "- No board measurement is claimed.",
            "- All power/energy values are ESTIMATED_PRE_BOARD_ONLY.",
            "- SAIF evidence uses functional harness activity; interpret as pre-board estimate only.",
            "",
            "## Release files",
            "",
            f"- Artifact bundle: `{_rel(ARTIFACT_BUNDLE)}`",
            f"- Hash manifest: `{_rel(SHA_FILE)}`",
            f"- Machine-readable status: `{_rel(FINAL_STATUS_JSON)}`",
        ]
    )
    _write(FINAL_STATUS_MD, md + "\n")


def _write_reviewer_guide() -> None:
    guide = "\n".join(
        [
            "# Reviewer Guide (Final)",
            "",
            "## One command (integrity check)",
            "",
            "```bash",
            "sha256sum -c release/SHA256SUMS.txt",
            "```",
            "",
            "## Where to look",
            "",
            "- Gate closure rationale: `docs/GATE_STATUS.md`",
            "- Power assumptions/limits: `docs/POWER_METHODOLOGY.md`",
            "- HLS digest evidence (Table 1): `review_pack/tables/artix7_hls_digest_summary_strict_v2.csv`",
            "- QoR evidence (Table 2): `review_pack/tables/artix7_qor_v6.csv`",
            "- Power evidence (Table 3): `review_pack/tables/artix7_power_v7_funcsaif.csv`",
            "- Derived throughput/energy (Table 4): `review_pack/tables/artix7_metrics_final.csv`",
            "- Vivado raw reports: `build/amd_vivado_artix7_v5/*/post_route_{timing,utilization}.rpt`",
            "- SAIF raw reports: `build/amd_power_artix7_v7_funcsaif/*/activity_func.saif` and `power_saif_func.rpt`",
            "- Canonical B3 identity: `build/handoff/B3_CANONICAL_STATUS.json`",
            "- Release manifest: `release/FINAL_STATUS.json`",
        ]
    )
    _write(REVIEWER_GUIDE, guide + "\n")


def _build_final_chatgpt_handoff() -> None:
    include = [RELEASE_DIR, PAPER_DIR, DOCS_DIR, TABLES_DIR]
    with tarfile.open(FINAL_CHATGPT_TAR, "w:gz") as tar:
        for p in include:
            if p.exists():
                tar.add(p, arcname=_rel(p))
    digest = _sha256(FINAL_CHATGPT_TAR)
    _write(FINAL_CHATGPT_SHA, f"{digest}  {FINAL_CHATGPT_TAR.name}\n")


def main() -> int:
    # Required inputs
    for required in [
        HLS_CSV,
        HLS_TEX,
        QOR_CSV,
        QOR_TEX,
        POWER_CSV,
        POWER_TEX,
        METRICS_CSV,
        METRICS_TEX,
        DOC_GATE,
        DOC_POWER,
        B3_STATUS,
        VIVADO_SUMMARY,
        POWER_SUMMARY,
    ]:
        _must_exist(required)

    # Required report evidence
    if not sorted(VIVADO_ROOT.glob("*/post_route_timing.rpt")):
        raise FileNotFoundError("Missing post_route_timing.rpt under build/amd_vivado_artix7_v5/*")
    if not sorted(VIVADO_ROOT.glob("*/post_route_utilization.rpt")):
        raise FileNotFoundError(
            "Missing post_route_utilization.rpt under build/amd_vivado_artix7_v5/*"
        )
    if not sorted(POWER_ROOT.glob("*/activity_func.saif")):
        raise FileNotFoundError(
            "Missing activity_func.saif under build/amd_power_artix7_v7_funcsaif/*"
        )
    if not sorted(POWER_ROOT.glob("*/power_saif_func.rpt")):
        raise FileNotFoundError(
            "Missing power_saif_func.rpt under build/amd_power_artix7_v7_funcsaif/*"
        )

    _write_docs_reproduce()
    _write_paper_arxiv_style()
    _compile_paper()

    dataset_included = DATASET_RAW.exists()
    dataset_sha = _sha256(DATASET_RAW) if dataset_included else None
    if dataset_included and dataset_sha:
        _write(DATASET_SHA_FILE, f"{dataset_sha}  {_rel(DATASET_RAW)}\n")

    _build_artifact_bundle(dataset_included=dataset_included)
    _write_sha256s(dataset_included=dataset_included)
    _write_final_status(dataset_included=dataset_included, dataset_sha=dataset_sha)
    _write_reviewer_guide()
    _build_final_chatgpt_handoff()

    print(
        json.dumps(
            {
                "status": "OK",
                "artifactBundle": _rel(ARTIFACT_BUNDLE),
                "sha256Sums": _rel(SHA_FILE),
                "finalStatusMd": _rel(FINAL_STATUS_MD),
                "finalStatusJson": _rel(FINAL_STATUS_JSON),
                "reviewerGuide": _rel(REVIEWER_GUIDE),
                "chatgptTar": _rel(FINAL_CHATGPT_TAR),
                "chatgptSha": _rel(FINAL_CHATGPT_SHA),
                "datasetIncluded": dataset_included,
                "datasetSha256": dataset_sha,
                "paperPdf": _rel(PAPER_PDF),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
