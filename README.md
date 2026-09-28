# SYLEX v3.0 — Adaptive University Syllabus Extraction Engine

> **Problem Statement Compliance:** 21 September 2026 Evaluation Standard  
> **Architecture:** Pure Python Deterministic Extraction Engine (zero external AI calls for extraction)  
> **Standard:** Fully document-agnostic. No college-specific rules. Word-for-word extraction. Zero invented text.

---

## 1. Clean Machine Installation

Tested on Python 3.8+ (Windows, Linux, macOS). Only two dependencies.

```bash
# Clone the repository
git clone <your-repo-link>
cd "syllabus builder"

# Install dependencies
pip install -r requirements.txt
# — or equivalently —
pip install pdfplumber PyMuPDF
```

---

## 2. Command-Line Execution (Exact Evaluation Interface)

### Task 1 — List all courses in the document
```bash
python sylex.py --pdf <path to the pdf>
```
Writes JSON to **stdout**. Exit code `0` on success.

Example output:
```json
{
  "document": "SomeCollege-R2023-CSE.pdf",
  "course_count": 62,
  "courses": [
    { "code": "CS23301", "title": "DATA STRUCTURES", "page": 41 },
    { "code": "MA23101", "title": "ENGINEERING MATHEMATICS I", "page": 12 }
  ]
}
```

### Task 2 — Read one course in full
```bash
python sylex.py --pdf <path to the pdf> --course CS23301
```
Writes JSON to **stdout**. Exit code `0` on success, `3` if the course is not found.

Output contains:
- `course` — code, title, category, L-T-P-C, pages
- `units` — number, title, hours, text (word-for-word as printed), topics with Bloom level
- `course_outcomes` — id, text, bloom, bloom_source
- `programme_outcomes` — id, text
- `co_po_matrix` — only mapped cells (blanks omitted), preserving printed mapping scale (S/M/L or 1/2/3)
- `books` — text and reference books with title, author, publisher, edition, year
- `not_extracted` — honest list of anything the engine could not read (empty `[]` when everything was extracted)

### Additional CLI Flags
```bash
python sylex.py --pdf syllabus.pdf --out output.json         # Write JSON to file
python sylex.py --pdf syllabus.pdf --course CS23301 --debug  # Include debug diagnostics
python sylex.py --pdf syllabus.pdf --hints hints.json        # Provide manual overrides
```

### Exit Codes
| Code | Meaning |
|------|---------|
| `0`  | Success (valid JSON produced) |
| `2`  | PDF file missing or unreadable |
| `3`  | Requested course not found in document |
| `4`  | Parsing or extraction exception |

---

## 3. Web Dashboard & AI Chat Assistant (Optional)

```bash
python run.py
# — or —
python sylex_server.py --browser
# Opens http://localhost:7823
```

The web UI provides a visual dashboard for uploading PDFs, viewing extracted JSON, and an AI-powered curriculum advisor chat. It is entirely optional — the CLI is the primary evaluation interface.

---

## 4. Vercel Cloud Deployment (Production Ready)

This repository includes native Vercel Serverless configuration (`vercel.json` and `api/index.py`):

1. Push or import this repository to GitHub.
2. Go to [Vercel](https://vercel.com/new) and click **Import** on this repository.
3. Keep default settings (Framework Preset: **Other**, Root Directory: `./`).
4. Click **Deploy**.
   - **Static Frontend:** Global Edge CDN serving `index.html`, modern responsive UI, dark/light modes.
   - **Serverless API:** Python Serverless Functions in `api/index.py` handling `/api/extract`, `/api/status`, `/api/chat`, and `/api/curriculum-audit`.

---

## 4. Extraction Approach

1. **PDF Parsing**: Dual-backend reading via PyMuPDF (primary) and pdfplumber (fallback). Extracts text, tables, and word positions per page.
2. **Document Grammar Induction**: Learns the document's conventions at runtime — unit keyword (UNIT/MODULE/CHAPTER), dominant topic separator, TOC presence, matrix symbols.
3. **Course Detection**: Three-layer scan — (a) detailed syllabus pages, (b) curriculum overview tables, (c) explicit label matching. Merge + deduplication with alias tracking.
4. **Deep Extraction**: Evidence-first parsing for units, topics, outcomes, CO-PO matrix, and books within computed page boundaries.
5. **Bloom Taxonomy**: Detects printed markers (K1-K6, BT1-BT6, L1-L6, bracketed codes) as `"printed"`. Falls back to verb-lexicon inference as `"inferred"`.
6. **Schema Normalization**: CLI output is normalized to guarantee valid bloom values (`analyse` not `analyze`), valid sources, and no null fields.

---

## 5. Test Results

Tested against multi-college, multi-format syllabus PDFs:

| Document | Task 1 | Task 2 | Notes |
|----------|--------|--------|-------|
| BE_CSE_FT_R2021 (387 pages, autonomous engineering) | 189 courses detected | Full extraction tested on 4 courses | Handles mixed overview-table + detailed-syllabus layouts |
| Multi-department curriculum with reversed `TITLE - CODE` headers | ✅ | ✅ Units, COs, books extracted | Handles non-standard header formats |
| Syllabi with numeric-only codes (e.g. 34421002) | ✅ | ✅ | Supports 5-10 digit university codes |
| Documents with merged/borderless CO-PO matrix tables | ✅ | Partial — some cells missed | Logged in `not_extracted` |

### Repeatability
The engine is fully deterministic. Three runs on the same input produce byte-identical JSON output.

---

## 6. Honest List of Known Weaknesses

1. **Scanned/Image-only PDFs**: Pages without a text layer return empty strings. Logged in `not_extracted` with a note to install Tesseract. No OCR is attempted.
2. **CO-PO Matrix in Images**: If the matrix is rendered as an image/screenshot rather than table/text, it cannot be extracted. Reported honestly in `not_extracted`.
3. **Merged Table Cells**: Tables with irregular merged cells (especially across page boundaries) may lose some cell values. Blanks are omitted rather than guessed — Rule 3 compliance.
4. **Courses Without Codes**: If a document lists courses purely by title without any alphanumeric code, detection relies on syllabus page markers (PREAMBLE, COURSE OBJECTIVES, UNIT headings). Coverage is lower than for coded courses.
5. **Ambiguous Topic Separators**: When a unit body uses multiple separator styles (dashes AND semicolons AND commas), the dominant-separator heuristic may not split perfectly. Some topics may be merged or over-split.
6. **Book Author/Title Disambiguation**: Without standardized formatting (quoted titles, "by" keyword, known publishers), the heuristic may swap author and title fields.
7. **Programme Outcomes Across Documents**: POs are searched document-wide. If the document does not print them at all, an empty list is returned with a `not_extracted` entry.
