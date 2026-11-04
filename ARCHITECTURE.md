# SYLEX architecture

SYLEX is a local-first document workspace. Run `py -3.12 run.py` to start the Python API and open the browser. The existing JavaScript application is retained so PDF extraction, exports, and book workflows share the same data without a second UI stack.

See [OFFLINE.md](OFFLINE.md) for the expanded offline architecture: document adapters, bounded OCR, persistent page caching, a versioned browser shell, exact-request result recovery and local source-text retrieval. The same reader handles PDF, DOCX, text and image syllabi. Hosted operation remains available with explicit actual-mode reporting.

See [ONLINE.md](ONLINE.md) for the cloud review pipeline. `cloud_models.py` bounds provider requests and response parsing; `online_pipeline.py` selects source pages, recovers unreadable PDFs through vision, validates model proposals and merges supported additions with the local baseline. Results expose reviewed/unreviewed pages, source excerpts, conflicts and fallback status.

## Boundaries

- `app.js`: navigation, document session, extraction, evidence views, and exports. It emits document and result events for connected tools.
- `studio-core.js`: pure snapshot, metrics, edition comparison, study-session allocation, and import validation. These operations have no DOM or network dependencies and run directly in Node tests.
- `studio-store.js`: IndexedDB transactions for project records and PDF Blobs. Write completion is acknowledged only after the transaction commits.
- `studio.js` / `studio.css`: the project library, notes, import/export, resume actions, comparison reports, and study-progress interface. Writes are serialized; updates load the latest record before merging changes.
- `api-client.js`: shared JSON transport for the assistant, book search, discovery, and connection diagnostics. It normalizes HTTP errors, propagates cancellation, and enforces deadlines. It never retries uploads or model requests automatically.
- `book.js`: local PDF selection, search results, and source-page reading.
- `book-finder.js`: six catalog adapters through the API, edition comparison, saved reading shelf, and book details. Shelf metadata persists in browser local storage.
- `chat.js`: contextual assistant with explicit local fallback and plain-text conversation history. An empty document session stays empty; sample data requires the demo action.
- `cinematic.js` / `cinematic.css`: cinematic homepage, responsive navigation, and bookshelf presentation.
- `workspace.js` / `workspace.css`: page motion, keyboard command menu, and downloadable service diagnostics. Reduced-motion preferences disable ambient animation; hidden tabs pause it.
- `sylex_server.py`: HTTP validation, PDF indexing, extraction orchestration, catalog normalization, cloud model fallback, and dossier generation.
- `sylex.py`: deterministic PDF parsing and curriculum extraction.
- `api/*.py`: deployment entry points reuse the production handler, including status checks.

## Request and document lifecycle

Document uploads remain in memory in the browser until sent to the selected API. Server upload limits and format validation precede processing. Extraction exposes requested and actual processing modes in `_processing`; cloud failure preserves local extraction and is reported in the UI. Both catalog and detail tasks use page-based cloud review in online mode, retaining the whole-document local baseline and reporting incomplete review coverage.

Extraction has a cancel control and a two-minute browser deadline. Cancellation stops the browser waiting; an already-running server operation may finish. Book search, discovery, and chat protect state with controller or request identity checks so an older response cannot overwrite a newer session. Model fallback attempts share a bounded time budget.

The local server binds to loopback by default. Windows uses exclusive port binding to prevent two app versions from answering the same port. Static files use an explicit allowlist; environment files are never static assets. Credentials remain on the server and are excluded from diagnostic exports.

## Persistent projects

The Studio stores each project in IndexedDB with a unique ID, timestamps, name, notes, source PDF when available, extracted catalog, deduplicated course details, and study plans. Opening a project restores the source and extraction session. Selecting another document starts a fresh project association. Extracting additional details in a saved project updates that record automatically.

Project JSON exports are versioned (`sylex-project`, version 1). They include notes, analysis data, and study progress; PDF bytes stay separate. Imports validate render-sensitive fields, recompute catalog counts, and rebuild plans from verified topic text. The library offers source-PDF attachment for imported projects. Browser storage errors are surfaced without claiming a successful save.

Edition comparison matches normalized course codes, falling back to titles when a code is absent. Topic and outcome differences compare normalized text, preserving original source text for display. Missing course details are explicitly reported as coverage gaps. Study sessions preserve topic order and cover each source topic exactly once; session counts are user planning preferences rather than document contact hours. Changed topic text invalidates an older plan until it is rebuilt.

The command menu includes saved projects. The homepage offers a resume action for the active or most recently updated project. Records remain local to the browser and site origin; clearing browser data removes them.

## Service availability

Settings → Check all connections checks the local engine, makes a small live model request, and queries six catalogs using a public sample title. Configuration presence does not imply provider availability. Each catalog can fail independently; available results remain usable. The diagnostic report captures the result of that check, without credentials or document content.

## Validation

`py -3.12 -m unittest discover -s tests -v` exercises generated-PDF extraction, book search, page preview, dossier export, validation failures, catalog ranking/access rules, cloud fallback, static asset serving, and safe launcher behavior. `node --test tests/api-client.test.cjs tests/chat-context.test.cjs tests/studio-core.test.cjs` checks transport errors and cancellation. Browser validation covers all eight pages at desktop and mobile widths, keyboard search, and reduced motion.

## Remaining architectural limits

The local application has one active document session per tab, browser-local project persistence, no account system, and process-local server caches. It is intended for a local workspace, not multi-tenant hosting. Browser cancellation is not a server job queue. OCR availability depends on locally installed dependencies. Cloud models and third-party catalog availability cannot be guaranteed by the application.
