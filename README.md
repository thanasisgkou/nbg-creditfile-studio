# NBG | CreditFile Studio

**Evidence-led preparation of SME financing files.**

CreditFile Studio is a proof-of-concept workspace for credit analysts reviewing an SME financing application together with its financial statements. It extracts a defined set of fields, links values to the source PDFs, highlights cross-document differences, supports analyst review, and produces versioned preparation outputs.

The product is designed to **support preparation and review**. It does not make lending, scoring, KYC/AML, approval or rejection decisions.

## Hosted demo

**Live product:** https://creditfile-studio-review.web.app/

The hosted demo contains the latest UI and case-assistant iteration used in the final assessment demonstration. This repository is the **local reference implementation** and is intentionally described separately from the hosted release rather than implying that both are the same build.

All bundled demo documents and companies are synthetic.

## Core workflow

1. Create or reopen a financing case.
2. Review one financing application and one financial-statements PDF.
3. Extract 24 defined fields with source evidence.
4. Open the exact PDF page or passage behind a proposed value.
5. Run deterministic cross-document checks for identity, amounts and accounting consistency.
6. Confirm, correct or leave values unresolved while preserving the original extraction and review history.
7. Ask case-scoped questions or use explicit preset actions.
8. Issue a versioned preparation bulletin.
9. Download an editable clarification draft when company input is required.

A key product principle is:

> **The model proposes. The product checks. The analyst decides.**

## Local reference edition

Requirements:

- Python 3.11+
- Node.js 20.19+ or 22.12+
- Arial on Windows or DejaVu Sans on Linux for Greek PDF output
- Internet access once for dependency installation

### Windows

Open PowerShell in the repository:

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

### Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python scripts/run.py
```

Open **http://127.0.0.1:8520**.

The local reference edition starts with four independent synthetic cases:

| Company | Scenario |
| --- | --- |
| Σταφυλάκης Οινοποιητική Α.Ε. | Completed preparation and saved bulletin |
| Attention Is All You Need Α.Ε. | Missing registry number and pending review |
| Ypnos Palace Ξενοδοχειακή Α.Ε. | EUR 300,000 borrowing discrepancy |
| Aegean Foods | Unreadable requested amount plus turnover and borrowing discrepancies |

Local review changes are stored under `data/` and survive restarts. To use a separate workspace:

```sh
python scripts/run.py --data-dir data-second
```

## Optional live AI

The default local experience can use recorded demo analysis for repeatable review flows. New PDF analysis and free-form AI questions require live mode.

### Windows

```powershell
.\scripts\start.ps1 -Live
```

### Linux

```sh
.venv/bin/python scripts/run.py --live
```

Enter an OpenRouter key at the hidden prompt. The key remains in the running process and is not written to a configuration file. The default model is `google/gemini-2.5-flash`.

Use synthetic documents only.

## Architecture

| Component | Responsibility |
| --- | --- |
| React, TypeScript, PDF.js | Analyst workspace and highlighted PDF evidence |
| FastAPI | Local API, analysis jobs and write operations |
| Extraction and validation | Structured proposals, source checks and number normalization |
| Python / Decimal checks | Deterministic comparisons for identity, currency, turnover, borrowing and accounting logic |
| Review store | Original extraction plus separate analyst decisions and history |
| Case assistant | Case-scoped questions and workflow-aware answers |
| Bulletin renderer | Preview and immutable saved preparation-bulletin versions |
| Clarification export | Editable Word draft for missing or inconsistent information |

The implementation keeps source documents, original extraction, analyst review events and saved versions separate. Relevant data changes can reopen affected comparisons, and replacing a PDF requires reanalysis before new review decisions use that document.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check creditfile scripts tests
.\.venv\Scripts\python.exe -m ruff format --check creditfile scripts tests
cd frontend
npm test
npm run build
npx playwright test
```

Browser tests use Chromium and isolated fixtures. The local test suite covers source navigation, corrections, reloads, comparison resolutions, bulletin versions, numeric integrity, stale writes and document replacement.

These repository tests validate implementation behaviour. They are **not** a substitute for the separate product evaluation used in the assessment.

## Scope and limitations

- 24 defined extracted fields across the two supported document types.
- Fixed deterministic comparison set rather than general credit analysis.
- Text-based PDFs only; scanned documents require OCR outside this workflow.
- Human review remains required for uncertain, inconsistent or customer-facing outputs.
- The local reference edition is intended for one operator and does not represent production authentication, authorization, load or bank deployment controls.
- The clarification draft is editable and must be reviewed before sending; no email is sent automatically.

## Submission note

The final assessment document and video describe the complete product story, including the newer hosted assistant iteration and its targeted follow-up validation. The original baseline evaluation remains a separate historical record of the earlier evaluated snapshot rather than being rewritten after later product changes.
