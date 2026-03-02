# Zenodo Status

Status: **BLOCKED**

Reason:
- Zenodo activation + DOI minting requires manual UI actions in Zenodo/GitHub OAuth.
- No DOI has been minted yet; repository files must not be updated with invented DOI values.

## Current state

- Repository: `https://github.com/tangodelta217/nema-connectome-artix7`
- Release available: `v0.1.0`
- `.zenodo.json`: present in repository root
- DOI fields in metadata/paper: pending (blocked on Zenodo)

## Pending manual actions (owner)

1. Connect Zenodo to GitHub account.
2. Enable repository `tangodelta217/nema-connectome-artix7` in Zenodo.
3. Publish a new GitHub release after activation (recommended: `v0.1.1`) to trigger ingestion.
4. Capture minted DOI values:
   - Version DOI: `<TO_FILL_AFTER_MINT>`
   - Concept DOI: `<TO_FILL_AFTER_MINT>`

## Pending repository updates after DOI mint

1. Update `CITATION.cff` with real DOI.
2. Update artifact availability/reproducibility DOI text in:
   - `paper/paper.tex`
   - `papers/paperA/text/sections/03_impl.tex`
3. Rebuild PDFs with `latexmk`.
4. Mark this file as `READY` and record DOI values + date.
