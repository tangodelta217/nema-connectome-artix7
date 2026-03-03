# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities privately via email to:
`marmilfer@alum.us.es`

Include as much detail as possible:

- Affected component/file and commit hash (if known)
- Reproduction steps or proof-of-concept
- Impact assessment (confidentiality/integrity/availability)
- Suggested mitigation (optional)

Please do not open public issues for unpatched vulnerabilities.

## Response Targets

- Initial acknowledgment: within 5 business days
- Triage outcome: within 10 business days
- Mitigation plan or workaround: as soon as practical after triage

## Scope

This policy covers source code, scripts, and CI definitions in this repository.
Hardware lab/board infrastructure is out-of-scope unless directly controlled by
this repository.

## Secure Development Governance

The default branch `main` is protected with mandatory security controls:

- Pull request required for merge.
- At least 1 approving human review.
- Last push to a PR must be approved before merge.
- Required status checks: `unit-tests (3.11)`, `unit-tests (3.12)`, `quality (3.11)`, `quality (3.12)`, `CodeQL Analyze (python)`, `Scorecard analysis`.
- Linear history and required conversation resolution.

## Code Scanning Triage Policy

Code scanning findings are handled with the following rule:

- Findings with direct code/workflow remediation are fixed in-repo before merge.
- Findings that are governance-temporal (for example repository age thresholds, historical scoring windows, or external program enrollment state) may be dismissed as `won't fix` only with a written justification in GitHub Security.
- Dismissals are compensating-control based and must reference active protections (branch protection + required CI/SAST checks).

Reference status at March 3, 2026: open code scanning alerts count is zero.
