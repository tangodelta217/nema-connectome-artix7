# Changelog

All notable changes to this repository are documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning intent.

## [0.1.1] - Unreleased

### Changed
- Consolidated GitHub Actions to a single primary `CI` workflow to avoid duplicated runs.
- Hardened repository docs for OSS/enterprise readiness (README structure, architecture doc, release/policy navigation).

### Fixed
- CI fixture tracking for minimal Vivado `.rpt` test reports required by parser tests.
- Repository metadata alignment (homepage/topics/description audit path).

## [0.1.0] - 2026-03-01

### Added
- Deterministic NEMA v0.1 scaffold for IR validation, fixed-point simulation, HLS codegen, and hwtest harness.
- Benchmark manifests and verification flow for B1/B3 and related artifact checks.
- Initial OSS governance files (`LICENSE`, `CONTRIBUTING`, `SECURITY`, `CODE_OF_CONDUCT`, `CITATION.cff`).
- GitHub release packaging and checksum verification guidance.
