# Zenodo DOI Integration (NEMA v0.1)

This repository is prepared for Zenodo DOI minting via GitHub releases.

## Preconditions

- GitHub repository exists and is public:
  - `https://github.com/tangodelta217/nema-connectome-artix7`
- A release tag exists (currently `v0.1.0`).
- Root `.zenodo.json` is present and committed.

## 1) Connect Zenodo to GitHub (UI steps)

The automation assistant cannot perform UI clicks. Follow these exact steps manually:

1. Open `https://zenodo.org` and sign in (or create account).
2. In Zenodo, open profile menu -> `GitHub`.
3. Click `Connect` to authorize Zenodo with GitHub.
4. Complete GitHub OAuth authorization and return to Zenodo.

Recommended dry run first:
- Repeat same flow at `https://sandbox.zenodo.org` to validate metadata before production.

## 2) Activate this repository in Zenodo

1. In Zenodo `GitHub` tab, locate `tangodelta217/nema-connectome-artix7`.
2. Toggle the repo to `ON` (enabled for archiving).
3. Confirm Zenodo detects `.zenodo.json` metadata.

## 3) Mint DOI from a GitHub release

Zenodo mints DOI when a new GitHub release is published after activation.

Option A (recommended): create patch release in GitHub
1. Create a new GitHub release tag (for example `v0.1.1`).
2. Publish release assets as usual.
3. Wait for Zenodo to ingest the release (can take a few minutes).

Option B (if supported by your Zenodo state): re-run/archive existing release
- If Zenodo did not ingest `v0.1.0` because activation happened later, create `v0.1.1` to force a clean ingest.

## 4) Retrieve DOI and record values

From Zenodo record page, copy both:
- Version DOI (example shape: `10.5281/zenodo.12345678`)
- Concept DOI (example shape: `10.5281/zenodo.1234567`)

Store them in `docs/ZENODO_STATUS.md`.

## 5) Update repository metadata once DOI exists

Do not invent values. Use real DOI from Zenodo record.

### 5.1 Update `CITATION.cff`

Add DOI fields:

- Top-level DOI:
  - `doi: "<VERSION_DOI>"`
- Preferred citation DOI identifier:
  - under `preferred-citation.identifiers`, add:
    - `type: doi`
    - `value: "<VERSION_DOI>"`

Suggested edit target:
- `CITATION.cff`

### 5.2 Update paper artifact availability section

Update DOI references in:
- `paper/paper.tex` (`Reproducibility` section)
- `papers/paperA/text/sections/03_impl.tex` (`Artifact and Reproducibility` subsection)

Recommended sentence pattern:
- "Zenodo archive DOI: `<VERSION_DOI>` (concept DOI: `<CONCEPT_DOI>`)."

### 5.3 Rebuild PDFs after DOI update

```bash
cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error paper.tex
cd ../papers/paperA/text && latexmk -pdf -interaction=nonstopmode -halt-on-error paper.tex
```

## 6) Optional: badge in README

After DOI exists, add Zenodo badge with real DOI:

- Badge URL:
  - `https://zenodo.org/badge/DOI/<DOI>.svg`
- Target URL:
  - `https://doi.org/<DOI>`
