# Validation record — 2 November 2026

- Automated checks: 36 Python tests and 6 JavaScript tests passed.
- Browser: all seven navigation pages checked at 1440px and 390px; no horizontal overflow on those pages or runtime exceptions. Ctrl+K opened the command menu and navigated to Extract. Reduced-motion mode produced zero running page animations.
- Real document workflow: generated PDF → one detected course → two extracted units; local provenance recorded. Book search returned the correct source page. Local assistant used the loaded units and returned an empty-context explanation after changing documents. Extraction cancellation restored the controls.
- Live cloud: NVIDIA Nemotron 3.5 Bolt verification returned HTTP 200 in 3.2 seconds; contextual chat endpoint returned HTTP 200 in 8.6 seconds. Older model choices timed out during investigation. The default and fallback model configuration were updated; availability remains dependent on the provider.
- Live discovery: 24 editions returned for a public sample title. Open Library, Google Books, Internet Archive, Project Gutenberg, and Crossref responded. DOAB returned HTTP 403; partial results remain available and Settings reports the provider failure.
- PDF preview, curriculum audit, dossier export, malformed input rejection, static allowlist, and duplicate-server binding covered by HTTP integration tests.

Tests used generated documents and an isolated browser profile. No user document was sent to a model during validation. Local service left running at http://localhost:7823.

## Curriculum Studio expansion

- Added pure curriculum operations, transactional IndexedDB storage, and a separate Studio interface.
- Project creation, notes, JSON import, PDF storage, project restoration after reload, and automatic course-detail saving verified in an isolated browser profile.
- Study plans built from actual extracted topics, with completion progress preserved after reload.
- Edition comparison displayed the deliberately changed topic and credits while marking unextracted shared courses as missing detail coverage.
- Project library, comparison, planner, and project dialog checked at 390px with no horizontal overflow or runtime exceptions.
- Automated suite now contains 36 Python checks and 12 JavaScript checks, including snapshot isolation, edition differences, missing-detail handling, complete topic allocation, import validation, and plan progress import.
