# CreditFile Studio

A local workspace for reviewing SME financing applications and financial statements. It combines PDF evidence, field corrections, deterministic comparisons, case-scoped questions and versioned preparation bulletins. The interface is in Greek; all supplied documents contain synthetic data.

[Online demo](https://creditfile-studio-review.web.app/) · The hosted application is maintained separately from this local repository.

## Run locally

Requirements: Python 3.11+, Node.js 20.19+ or 22.12+, and Arial on Windows or DejaVu Sans on Linux for Greek PDF output. Internet access is needed once to install dependencies.

On Windows, open PowerShell in the repository:

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

On Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python scripts/run.py
```

Open **http://127.0.0.1:8520**. No API key or configuration file is required. The first launch creates four independent examples:

| Company | Scenario |
| --- | --- |
| Σταφυλάκης Οινοποιητική Α.Ε. | Completed preparation and a saved bulletin |
| Attention Is All You Need Α.Ε. | Missing registry number and pending financial review |
| Ypnos Palace Ξενοδοχειακή Α.Ε. | A 300,000 EUR borrowing discrepancy |
| Aegean Foods | An unreadable requested amount and two discrepancies |

Select a field, inspect its highlighted PDF source, confirm or correct it, resolve comparisons, ask a ready-made question and save a preparation bulletin. Corrections without a supporting PDF source are saved but remain incomplete. Local changes are stored in `data/` and survive restarting the application. Stop with Ctrl+C. To try a separate workspace, run `python scripts/run.py --data-dir data-second` using the virtual environment.

The default mode uses recorded extraction results and local answers; it makes no AI calls. New PDF analysis and free-form AI questions require the optional live mode.

## Optional live AI

Use your own OpenRouter account:

```powershell
.\scripts\start.ps1 -Live
```

On Linux, run `.venv/bin/python scripts/run.py --live`. Enter your key at the hidden prompt. It stays in the running process and is not saved to a file. The default model is `google/gemini-2.5-flash`. Analysis and free-form questions send document excerpts to OpenRouter and consume your account quota. Use synthetic documents only.

## Design

| Component | Responsibility |
| --- | --- |
| React, TypeScript, PDF.js | Review interface and highlighted PDF evidence |
| FastAPI | Local API, background analysis and write commands |
| Extraction and validation | Structured model proposals, source checks and number normalization |
| Python/Decimal comparisons | Identity, currency, turnover, borrowing and accounting checks |
| Review store | Immutable original extraction with separate analyst decisions |
| Case-scoped Q&A | Retrieved PDF evidence and deterministic workflow answers |
| Bulletin renderer | Greek PDF previews and immutable saved versions |

Writes use request identifiers and workspace fingerprints. Relevant data changes reopen affected comparisons; confirming an unchanged value preserves its resolution. Document replacement preserves old PDF versions and requires reanalysis. The runner binds to loopback and permits one writer per data directory.

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

Browser tests start their own isolated fixture server and use Chromium. Install it once with `npx playwright install chromium`. Tests cover source navigation, corrections and reloads, comparison resolutions, bulletin versions, numeric integrity, stale writes and document replacement. Recorded examples and mocked providers make these repeatable workflow tests, not an AI accuracy benchmark.

## Scope

The application supports preparation and analyst review; it does not make lending decisions. It handles 24 extracted fields, a fixed set of comparisons and text-based PDFs. Scanned documents need OCR outside this workflow. Citation validation verifies source identity and quote presence, not every assertion in a free-form model answer. The local application is intended for one operator, without multi-user authentication.
