# Validation record — 2 November 2026

## Universal layout hardening — 6 November 2026

- 92 Python tests and 21 JavaScript tests passed on the complete repository.
- Added generated layout cases for multi-page syllabus tables, blank continuation rows, reordered L/T/P/C columns, fractional workload values, numbered course outlines, bracketed course headers, courses sharing one page, and sentence-case or non-Latin unit titles.
- Course objectives are no longer converted into course outcomes. Outcome sections stop at unit/content boundaries, and numbered or bulleted outcomes retain provenance for generated identifiers.
- CO-PO tables are combined across pages. Conflicting duplicate cells retain the first printed value and enter the review ledger.
- The source audit now checks missing recognizable units/outcomes, topic coverage of unit bodies, Unicode text, identifier boundaries, book fields, and course-scope evidence after online review. The response also lists checks that still require visual or structural review.
- UTF-8 TXT/Markdown input normalizes Windows, Unix, and legacy carriage-return line endings before parsing, so anchored headings behave consistently.
- These tests cover many materially different layouts; they do not claim that every possible visual design, damaged scan, handwritten syllabus, or ambiguous table can be extracted automatically. Such pages remain marked for review.

- Automated checks: 36 Python tests and 6 JavaScript tests passed.
- Browser: all seven navigation pages checked at 1440px and 390px; no horizontal overflow on those pages or runtime exceptions. Ctrl+K opened the command menu and navigated to Extract. Reduced-motion mode produced zero running page animations.
- Real document workflow: generated PDF → one detected course → two extracted units; local provenance recorded. Book search returned the correct source page. Local assistant used the loaded units and returned an empty-context explanation after changing documents. Extraction cancellation restored the controls.
- Live cloud: NVIDIA Nemotron 3.5 Bolt verification returned HTTP 200 in 3.2 seconds; contextual chat endpoint returned HTTP 200 in 8.6 seconds. Older model choices timed out during investigation. The default and fallback model configuration were updated; availability remains dependent on the provider.
- Live discovery: 24 editions returned for a public sample title. Open Library, Google Books, Internet Archive, Project Gutenberg, and Crossref responded. DOAB returned HTTP 403; partial results remain available and Settings reports the provider failure.
- PDF preview, curriculum audit, dossier export, malformed input rejection, static allowlist, and duplicate-server binding covered by HTTP integration tests.

Tests used generated documents and an isolated browser profile. No user document was sent to a model during validation. Local service left running at http://localhost:7823.

## Online evidence pipeline — 4 November 2026

- 74 Python tests and 21 JavaScript tests passed. Added tests cover grounded cloud proposals, fabricated/wrong-page evidence, metadata conflicts, short-code recovery, no-credential/provider fallback, partial coverage, page-range continuation, topic completeness, two-column PDFs, vision without local OCR, response truncation, project evidence validation, and safe recovery of unmarked local server listeners.
- Live NVIDIA text review recovered a synthetic CS50 syllabus missed by the local code detector, preserving both units and fractional credits. Unsupported model output was rejected and reported.
- The initial vision endpoint returned HTTP 410. After checking current provider availability, the default was changed to Nemotron 3 Nano Omni. Live image-only PDF extraction then passed with local OCR deliberately disabled; the course and both units were recovered and labeled for visual review.
- Browser regression passed for the real online HTTP pipeline with a deterministic provider fixture, coverage UI, saved evidence/project restoration, offline shell/result recovery, document mismatch rejection, automatic local fallback and 390px/1440px layouts without page errors.
- OpenAI/Gemini/custom adapters were retained, but not live-verified with credentials. No user document was sent in these checks. See [ONLINE.md](ONLINE.md) for remaining limits and reproducible checks.

## Offline upgrade — 4 November 2026

- 53 Python checks and 20 JavaScript checks passed on Python 3.12 / Node 24. Real Tesseract OCR tests ran successfully on generated scanned PDFs and PNG images.
- Regression coverage includes course continuation pages with catalog hints, eight-page courses, two courses sharing a page, dotted/spaced/numeric codes, uncoded titles, DOCX tables and Unicode text, Markdown, sparse/encrypted PDFs, missing OCR, cache reuse/clear, fractional credits, invalid hints, local chat and cloud-outage fallback.
- Isolated Chromium check passed with external networking blocked for new local extraction. With all browser networking disabled, the cached page reopened, the saved project/source restored, and the exact prior extraction replayed. A different document was rejected rather than receiving cached data. Mobile/desktop layouts and automatic local fallback were checked without page errors.
- Live configured NVIDIA cloud model returned a successful synthetic connection reply. Book discovery for a public sample returned 14 results; Open Library, Google Books, Internet Archive, Project Gutenberg and Crossref responded. DOAB returned HTTP 403, correctly exposed as unavailable.
- These checks use synthetic/public data. They do not establish universal extraction accuracy or future provider availability. See [OFFLINE.md](OFFLINE.md) for setup, supported formats and remaining limits.

## Curriculum Studio expansion

- Added pure curriculum operations, transactional IndexedDB storage, and a separate Studio interface.
- Project creation, notes, JSON import, PDF storage, project restoration after reload, and automatic course-detail saving verified in an isolated browser profile.
- Study plans built from actual extracted topics, with completion progress preserved after reload.
- Edition comparison displayed the deliberately changed topic and credits while marking unextracted shared courses as missing detail coverage.
- Project library, comparison, planner, and project dialog checked at 390px with no horizontal overflow or runtime exceptions.
- Automated suite now contains 36 Python checks and 12 JavaScript checks, including snapshot isolation, edition differences, missing-detail handling, complete topic allocation, import validation, and plan progress import.
