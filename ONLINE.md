# Online extraction: source evidence before model output

Online mode now reviews both catalogs and course details, including documents where the local detector finds no course. A local extraction is the baseline, not a reason to skip online processing. Offline mode remains entirely local.

## Pipeline

1. Validate the document and read all source pages locally. Preserve page numbers, source SHA-256, text/OCR method and review warnings. Recover clear two-column syllabus layouts from page geometry.
2. For unreadable PDF pages or low-confidence local OCR, try cloud vision. The NVIDIA default is `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`; override it with `SYLEX_VISION_MODEL`. Vision transcripts are explicitly labeled and require visual checking.
3. Divide readable text into page-addressed chunks with overlap. For a known course, use only its bounded text, including boundaries within shared pages.
4. Ask the selected text model for structured proposals, each with a page number and verbatim quote. Document text is treated as data, not executable instructions.
5. Check each quote against the exact submitted page segment. Verify proposed field values inside that quote. Reject invented courses, unsupported numbers, absent headings, wrong-page evidence, rewritten outcomes and ungrounded bibliography fields.
6. Fill supported gaps. Preserve existing values when a cloud proposal conflicts. Reject topic lists that omit part of the unit body. Bloom labels are derived locally rather than accepted from the model.
7. Return the extraction with `_online` coverage, `_evidence` source excerpts, `_source` reading diagnostics and `_processing` actual-mode reporting. The Results panel displays the coverage and evidence. Project exports preserve this metadata.

The vision payload follows NVIDIA's documented base64 image interface: [Nemotron 3 Nano Omni API](https://docs.api.nvidia.com/nim/re/reference/nvidia-nemotron-3-nano-omni-30b-a3b-reasoning-infer). Live testing caught HTTP 410 on the older Nano 12B VL endpoint, so the default was changed to an available model and tested again.

## Resource limits and long documents

Each request has a 48-second scheduling budget. Local OCR receives up to eight seconds of that budget. At most three vision pages and six text chunks are submitted, with up to three simultaneous provider calls and per-call timeouts of at most 16 seconds. Chunks hold approximately 12,000 source characters. CPU parsing and transport cleanup can add overhead; the browser keeps its existing two-minute cancellation deadline.

Nothing past the request limit is labeled reviewed. The complete local extraction remains available, while `_online.unreviewed_pages` identifies unfinished cloud work. Use **Cloud review from page / Through page** in Extract to review later pages. `_online.outside_review_pages` distinguishes pages deliberately outside that range. Catalog range passes retain the current document's prior catalog through hints; each coverage report describes the current pass, not accumulated certification.

On model/network failure, malformed JSON, truncated output or invalid schema, local results remain available. The UI reports fallback or partial review. Partial/fallback responses are not cached by the server as a completed cloud result. Browser offline replay remains fingerprinted to file bytes and extraction settings, including page ranges. Successful server caching is also scoped to the provider, endpoint, model and credential digest.

## Trust boundary and remaining limits

Source matching establishes that a proposal occurs in the readable page text. It does not prove that OCR interpreted an image correctly, that the local parser detected every section, or that a course definition is complete. Cloud vision and local OCR can both misread text; their outputs retain review warnings. Handwriting, blurred pages, complex merged tables and unsupported layouts still need human review. Clear two-column layouts are supported conservatively; ambiguous column arrangements are flagged.

The cloud is not allowed to invent CO–PO matrix alignments. Matrix extraction continues through the local table/text reader, with unresolved cells reported. Cloud-only printed headings in unfamiliar languages or formats may fail the conservative heading validator; their raw source remains available rather than silently becoming invented units. All formats supported by the local reader can receive text review; cloud image transcription is currently limited to PDF pages.

Online mode transmits the selected readable text and, when needed, rendered page images to the configured provider. Offline mode makes no model call. No raw model reasoning is presented as evidence. Provider error messages are sanitized, and external responses are size-limited. Endpoint validation remains at the HTTP boundary.

## Book Agent online enhancement

Book Explorer's online enhancement is opt-in. Local page search, reading-path creation and syllabus alignment finish first. When enabled, only derived title, author and validated ISBN metadata are sent to the existing public catalog discovery pipeline; uploaded PDF text and page excerpts are not sent to catalog providers. The returned edition and access candidates are kept separate from page evidence so a catalog match cannot be mistaken for proof that the book covers a syllabus topic.

If providers time out or the connection disappears, the local report remains usable. Book Finder then falls back to the browser's saved research shelf and active-syllabus books. Public availability is a provider claim and should be checked at the linked source; the app does not treat a search result as a guaranteed legal download.

NVIDIA text and vision requests were tested live with generated syllabi. OpenAI, Gemini and custom endpoint adapters remain available but were not live-tested with user credentials. Hosted operation also depends on the deployment platform's request-size/runtime limits and configured secrets; the code changes do not themselves redeploy the site.

## Verification

The standard suite covers fabricated fields, wrong-page quotes, conflicts, short-code recovery, empty local catalogs, cross-course boundaries, partial coverage, page-window continuation, no-credential fallback, vision without local OCR, truncated provider output and two-column native PDFs. The browser regression covers online HTTP processing and coverage display, project restore, offline replay and mobile layout.

```powershell
py -3.12 -m unittest discover -s tests -v
node --test tests/api-client.test.cjs tests/chat-context.test.cjs tests/studio-core.test.cjs tests/local-assistant.test.cjs tests/offline-transport.test.cjs
py -3.12 tests/browser_offline_check.py
```

Opt-in live checks send generated, non-user material to the configured NVIDIA endpoint:

```powershell
py -3.12 tests/live_online_check.py
py -3.12 tests/live_online_check.py --vision
```
