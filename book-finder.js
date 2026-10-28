'use strict';

const BOOK_FINDER_TIMEOUT_MS = 40000;
const FINDER_IMPORT_MAX_BYTES = 50 * 1024 * 1024;
const FINDER_IMPORT_TIMEOUT_MS = 90000;

const finderState = {
  abortController: null,
  references: [],
};

const finderElement = id => document.getElementById(id);

function finderToast(message, type = 'info') {
  if (typeof window.toast === 'function') window.toast(message, type);
}

function finderEmptyState(title, detail) {
  const wrap = document.createElement('div');
  wrap.className = 'finder-empty-state';
  const icon = document.createElement('div');
  icon.className = 'finder-empty-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = '⌕';
  const heading = document.createElement('strong');
  heading.textContent = title;
  const description = document.createElement('span');
  description.textContent = detail;
  wrap.append(icon, heading, description);
  return wrap;
}

function setFinderBusy(isBusy) {
  const button = finderElement('finder-search-button');
  const title = finderElement('finder-title');
  const author = finderElement('finder-author');
  if (button) {
    button.disabled = isBusy;
    button.textContent = isBusy ? 'Searching catalogs…' : 'Run discovery agent';
  }
  if (title) title.disabled = isBusy;
  if (author) author.disabled = isBusy;
}

function setFinderProviderStatus(message) {
  const status = finderElement('finder-provider-status');
  if (status) status.textContent = message;
}

function setFinderSummary(message) {
  const summary = finderElement('finder-results-summary');
  if (summary) summary.textContent = message;
}

function formatFinderNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat().format(number) : '0';
}

function setFinderCoverage(coverage) {
  const panel = finderElement('finder-coverage');
  const value = finderElement('finder-coverage-value');
  const detail = finderElement('finder-coverage-detail');
  const candidateCount = Number(coverage?.candidates_evaluated);
  if (!panel || !value || !detail) return;
  if (!Number.isFinite(candidateCount) || candidateCount < 1) {
    panel.hidden = true;
    return;
  }
  const uniqueCount = Number(coverage?.unique_books_ranked) || 0;
  const reportedHits = Number(coverage?.catalog_hits_reported) || 0;
  value.textContent = `${formatFinderNumber(candidateCount)} candidates scored`;
  const providersChecked = Number(coverage?.providers_checked) || 0;
  detail.textContent = `${formatFinderNumber(uniqueCount)} edition-aware matches${reportedHits ? ` · ${formatFinderNumber(reportedHits)} provider records reported` : ''}${providersChecked ? ` · ${providersChecked} sources checked` : ''}`;
  panel.hidden = false;
}

function finderSafeUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.href : '';
  } catch {
    return '';
  }
}

function createFinderLink(label, url, className = 'finder-action') {
  const safeUrl = finderSafeUrl(url);
  if (!safeUrl) return null;
  const link = document.createElement('a');
  link.className = className;
  link.href = safeUrl;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = label;
  return link;
}

function createFinderButton(label, className, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = className;
  button.textContent = label;
  button.addEventListener('click', onClick);
  return button;
}

function closeFinderPreview() {
  const panel = finderElement('finder-preview-panel');
  const viewer = finderElement('finder-preview-viewer');
  const source = finderElement('finder-preview-source');
  if (viewer) viewer.removeAttribute('src');
  if (source) {
    source.hidden = true;
    source.removeAttribute('href');
  }
  if (panel) panel.hidden = true;
}

function openFinderPreview(url, title) {
  const safeUrl = finderSafeUrl(url);
  if (!safeUrl) {
    finderToast('This provider did not supply a secure PDF preview link', 'error');
    return;
  }
  const panel = finderElement('finder-preview-panel');
  const viewer = finderElement('finder-preview-viewer');
  const label = finderElement('finder-preview-title');
  const source = finderElement('finder-preview-source');
  if (!panel || !viewer) return;
  if (label) label.textContent = title || 'Provider-authorized PDF preview';
  if (source) {
    source.href = safeUrl;
    source.hidden = false;
  }
  viewer.removeAttribute('src');
  viewer.src = safeUrl;
  panel.hidden = false;
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function finderPdfFilename(title) {
  const name = String(title || 'authorized-book')
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 100) || 'authorized-book';
  return `${name}.pdf`;
}

async function importFinderPdf(record, button) {
  const safeUrl = finderSafeUrl(record.download_url);
  if (!safeUrl || typeof window.loadBookFile !== 'function') {
    finderToast('This PDF cannot be sent to Book Explorer right now', 'error');
    return;
  }
  const originalLabel = button.textContent;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), FINDER_IMPORT_TIMEOUT_MS);
  button.disabled = true;
  button.textContent = 'Preparing PDF…';
  try {
    const response = await fetch(safeUrl, { signal: controller.signal, credentials: 'omit' });
    if (!response.ok) throw new Error(`The provider returned ${response.status}`);
    const advertisedSize = Number(response.headers.get('content-length'));
    if (Number.isFinite(advertisedSize) && advertisedSize > FINDER_IMPORT_MAX_BYTES) {
      throw new Error('The provider PDF is larger than the 50 MB local analysis limit');
    }
    if (!response.body) throw new Error('The provider did not return a readable PDF stream');
    const reader = response.body.getReader();
    const chunks = [];
    let received = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > FINDER_IMPORT_MAX_BYTES) {
        controller.abort();
        throw new Error('The provider PDF is larger than the 50 MB local analysis limit');
      }
      chunks.push(value);
    }
    const pdf = new Blob(chunks, { type: 'application/pdf' });
    const signature = new TextDecoder().decode(await pdf.slice(0, 1024).arrayBuffer());
    if (!signature.includes('%PDF-')) throw new Error('The provider did not return a PDF file');
    const file = new File([pdf], finderPdfFilename(record.title), { type: 'application/pdf' });
    window.navigate?.('books');
    window.loadBookFile(file);
    finderToast('Authorized PDF loaded in Book Explorer', 'success');
  } catch (error) {
    const message = error?.name === 'AbortError'
      ? 'PDF import timed out. Download it from the provider, then upload it in Book Explorer.'
      : `${error.message || 'The provider blocked browser import.'} Download it from the provider, then upload it in Book Explorer.`;
    finderToast(message, 'error');
  } finally {
    window.clearTimeout(timeout);
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

function createFinderResult(record) {
  const card = document.createElement('article');
  card.className = `finder-result-card${record.is_best_match ? ' best-match' : ''}`;

  const top = document.createElement('div');
  top.className = 'finder-result-top';
  const identity = document.createElement('div');
  identity.className = 'finder-result-identity';
  const title = document.createElement('h3');
  title.textContent = record.title || 'Untitled book';
  const byline = document.createElement('p');
  const authorList = Array.isArray(record.authors) && record.authors.length ? record.authors.join(', ') : 'Author not listed';
  const identifiers = Array.isArray(record.identifiers) ? record.identifiers.filter(Boolean) : [];
  const metadata = [record.year, record.publisher, record.edition_note, identifiers.length ? `ISBN ${identifiers[0]}` : ''].filter(Boolean).join(' · ');
  byline.textContent = metadata ? `${authorList} · ${metadata}` : authorList;
  identity.append(title, byline);
  const labels = document.createElement('div');
  labels.className = 'finder-result-labels';
  const match = document.createElement('span');
  match.className = `finder-match-label ${record.match_label === 'Exact match' ? 'exact' : ''}`;
  match.textContent = record.match_label || 'Catalog match';
  const access = document.createElement('span');
  access.className = `finder-access-label ${record.download_url ? 'download' : ''}`;
  access.textContent = record.availability || 'Catalog record';
  labels.append(match, access);
  if (record.is_best_match) {
    const best = document.createElement('span');
    best.className = 'finder-best-label';
    best.textContent = 'Best match';
    labels.prepend(best);
  }
  top.append(identity, labels);

  const confidence = Math.max(0, Math.min(99, Number(record.match_confidence) || 0));
  const confidenceBlock = document.createElement('div');
  confidenceBlock.className = 'finder-confidence';
  const confidenceHeader = document.createElement('div');
  confidenceHeader.className = 'finder-confidence-header';
  const confidenceLabel = document.createElement('span');
  confidenceLabel.textContent = record.match_reason || 'Match confidence';
  const confidenceValue = document.createElement('strong');
  confidenceValue.textContent = `${confidence}% confidence`;
  confidenceHeader.append(confidenceLabel, confidenceValue);
  const confidenceTrack = document.createElement('div');
  confidenceTrack.className = 'finder-confidence-track';
  confidenceTrack.setAttribute('role', 'progressbar');
  confidenceTrack.setAttribute('aria-label', `Match confidence: ${confidence}%`);
  confidenceTrack.setAttribute('aria-valuemin', '0');
  confidenceTrack.setAttribute('aria-valuemax', '100');
  confidenceTrack.setAttribute('aria-valuenow', String(confidence));
  const confidenceFill = document.createElement('span');
  confidenceFill.style.width = `${confidence}%`;
  confidenceTrack.append(confidenceFill);
  const signals = document.createElement('div');
  signals.className = 'finder-confidence-signals';
  (Array.isArray(record.match_signals) ? record.match_signals : []).forEach(signal => {
    const item = document.createElement('span');
    item.textContent = signal;
    signals.append(item);
  });
  confidenceBlock.append(confidenceHeader, confidenceTrack, signals);

  const sources = document.createElement('div');
  sources.className = 'finder-sources';
  const sourceLabel = document.createElement('span');
  sourceLabel.textContent = 'Listed by';
  sources.append(sourceLabel);
  const knownSources = Array.isArray(record.sources) ? record.sources : [];
  knownSources.forEach(source => {
    if (!source || !source.name) return;
    const sourceLink = createFinderLink(source.name, source.url, 'finder-source-link');
    if (sourceLink) sources.append(sourceLink);
    else {
      const sourceName = document.createElement('span');
      sourceName.className = 'finder-source-link';
      sourceName.textContent = source.name;
      sources.append(sourceName);
    }
  });

  const actions = document.createElement('div');
  actions.className = 'finder-actions';
  const view = createFinderLink(record.availability === 'Preview available' ? 'Preview book ↗' : 'View / read ↗', record.view_url, 'finder-action finder-action-primary');
  const download = createFinderLink('Download legal PDF ↗', record.download_url, 'finder-action finder-action-download');
  const workspacePreview = record.download_url
    ? createFinderButton('Preview in workspace', 'finder-action finder-action-preview', () => openFinderPreview(record.download_url, record.title))
    : null;
  const inspect = record.download_url
    ? createFinderButton('Analyze in Book Explorer', 'finder-action finder-action-inspect', event => importFinderPdf(record, event.currentTarget))
    : null;
  const details = createFinderLink('Catalog details ↗', record.detail_url, 'finder-action');
  if (view) actions.append(view);
  if (workspacePreview) actions.append(workspacePreview);
  if (inspect) actions.append(inspect);
  if (download) actions.append(download);
  if (details) actions.append(details);

  card.append(top, confidenceBlock, sources, actions);
  return card;
}

function renderFinderResults(data) {
  const results = finderElement('finder-results');
  if (!results) return;
  const items = Array.isArray(data.results) ? data.results : [];
  const providerSummary = (Array.isArray(data.providers) ? data.providers : []).map(provider => {
    if (provider.status === 'available') return `${provider.name}: ${provider.matches} scored`;
    return `${provider.name}: unavailable${provider.detail ? ` (${provider.detail})` : ''}`;
  }).join(' · ');
  setFinderProviderStatus(providerSummary || 'Catalog search complete');
  setFinderCoverage(data.coverage);
  const coverage = data.coverage || {};
  const candidateCount = Number(coverage.candidates_evaluated) || 0;
  setFinderSummary(items.length
    ? `${candidateCount ? `${formatFinderNumber(candidateCount)} lawful catalog candidates scored; ` : ''}${items.length} best match${items.length === 1 ? '' : 'es'} shown for “${data.query?.title || ''}”. Confidence combines title, author, and catalog agreement.`
    : `No catalog matches found for “${data.query?.title || ''}”. Try a shorter title or remove the author.`);
  const legalNote = finderElement('finder-legal-note');
  if (legalNote && data.legal_notice) legalNote.textContent = data.legal_notice;
  if (!items.length) {
    const empty = finderEmptyState(
      'No matching public catalog record found.',
      providerSummary.includes('unavailable')
        ? 'One or more catalog services are busy. You can continue with a provider search while this service recovers.'
        : 'Try a shorter title, an alternate spelling, or search without the author name.'
    );
    const fallbackLinks = Array.isArray(data.fallback_links) ? data.fallback_links : [];
    if (fallbackLinks.length) {
      const actions = document.createElement('div');
      actions.className = 'finder-actions finder-fallback-actions';
      fallbackLinks.forEach(link => {
        const action = createFinderLink(`${link.name} ↗`, link.url, 'finder-action finder-action-primary');
        if (action) actions.append(action);
      });
      empty.append(actions);
    }
    results.replaceChildren(empty);
    return;
  }
  results.replaceChildren(...items.map(createFinderResult));
}

function normalizeReference(book, index) {
  if (!book || typeof book !== 'object') return null;
  const title = String(book.title || book.name || '').replace(/\s+/g, ' ').trim();
  if (!title) return null;
  const author = String(book.author || book.authors || '').replace(/\s+/g, ' ').trim();
  const publisher = String(book.publisher || '').replace(/\s+/g, ' ').trim();
  const year = String(book.year || '').replace(/\s+/g, ' ').trim();
  return {
    id: `${index}-${title}-${author}`,
    title,
    author,
    label: [title, author, publisher, year].filter(Boolean).join(' — '),
  };
}

function loadFinderReferences() {
  const sourceBooks = Array.isArray(window.STATE?.task2Result?.books) ? window.STATE.task2Result.books : [];
  const references = sourceBooks.map(normalizeReference).filter(Boolean);
  finderState.references = references;
  const select = finderElement('finder-reference-select');
  const useButton = finderElement('finder-use-reference');
  const status = finderElement('finder-import-status');
  if (!select || !useButton || !status) return;
  select.replaceChildren();
  if (!references.length) {
    const option = new Option('No extracted references available', '');
    select.append(option);
    select.disabled = true;
    useButton.disabled = true;
    status.textContent = 'No references are available yet. Extract a course in Deep View, then return here.';
    finderToast('No active Deep View references to import', 'info');
    return;
  }
  const prompt = new Option('Choose a detected textbook or reference…', '');
  select.append(prompt);
  references.forEach(reference => select.append(new Option(reference.label, reference.id)));
  select.disabled = false;
  useButton.disabled = false;
  status.textContent = `${references.length} reference${references.length === 1 ? '' : 's'} loaded from the active Deep View.`;
  finderToast('Syllabus references loaded', 'success');
}

function useFinderReference() {
  const selected = finderElement('finder-reference-select')?.value;
  const reference = finderState.references.find(item => item.id === selected);
  if (!reference) {
    finderToast('Choose a reference first', 'info');
    return;
  }
  const title = finderElement('finder-title');
  const author = finderElement('finder-author');
  if (title) title.value = reference.title;
  if (author) author.value = reference.author;
  title?.focus();
  setFinderSummary(`Reference imported: “${reference.title}”. Run the discovery agent to search trusted public catalogs.`);
}

function openBookFinder(book) {
  const reference = normalizeReference(book, 'direct');
  if (!reference) {
    finderToast('This reference does not include a searchable book title', 'error');
    return;
  }
  window.navigate?.('finder');
  const title = finderElement('finder-title');
  const author = finderElement('finder-author');
  if (title) title.value = reference.title;
  if (author) author.value = reference.author;
  window.setTimeout(() => searchFinder(), 0);
}

async function searchFinder(event) {
  event?.preventDefault();
  const title = finderElement('finder-title')?.value.replace(/\s+/g, ' ').trim() || '';
  const author = finderElement('finder-author')?.value.replace(/\s+/g, ' ').trim() || '';
  if (title.length < 2) {
    finderToast('Enter at least two characters of the book title', 'error');
    finderElement('finder-title')?.focus();
    return;
  }
  if (!window.STATE?.serverOnline && typeof window.checkServer === 'function') await window.checkServer(true);
  if (!window.STATE?.serverOnline) {
    finderToast('Connect the SYLEX server to search public catalogs', 'error');
    setFinderProviderStatus('Server connection required');
    return;
  }
  finderState.abortController?.abort();
  const controller = new AbortController();
  finderState.abortController = controller;
  const timeout = window.setTimeout(() => controller.abort(), BOOK_FINDER_TIMEOUT_MS);
  setFinderBusy(true);
  closeFinderPreview();
  setFinderProviderStatus('Searching trusted public catalogs…');
  setFinderSummary('Finding the closest title and author match, then checking alternatives and provider-authorized access.');
  try {
    const baseUrl = String(window.STATE.serverUrl || window.location.origin).replace(/\/$/, '');
    const response = await fetch(`${baseUrl}/api/book-discovery`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, author }),
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Catalog search failed (${response.status})`);
    renderFinderResults(data);
    finderToast(data.results?.length ? 'Catalog matches updated' : 'No catalog matches found', data.results?.length ? 'success' : 'info');
  } catch (error) {
    const timedOut = error?.name === 'AbortError';
    setFinderProviderStatus(timedOut ? 'Catalog search timed out' : 'Catalog search failed');
    setFinderSummary(timedOut ? 'The public catalog request took too long. Please try again.' : (error.message || 'Unable to search public catalogs right now.'));
    finderElement('finder-results')?.replaceChildren(finderEmptyState(
      timedOut ? 'The catalog search timed out.' : 'Unable to search public catalogs.',
      timedOut ? 'Try again in a moment or search with a shorter title.' : (error.message || 'Please try again shortly.')
    ));
    finderToast(timedOut ? 'Catalog search timed out' : (error.message || 'Catalog search failed'), 'error');
  } finally {
    window.clearTimeout(timeout);
    if (finderState.abortController === controller) finderState.abortController = null;
    setFinderBusy(false);
  }
}

function initBookFinder() {
  const form = finderElement('finder-search-form');
  if (!form) return;
  form.addEventListener('submit', searchFinder);
  finderElement('finder-load-references')?.addEventListener('click', loadFinderReferences);
  finderElement('finder-use-reference')?.addEventListener('click', useFinderReference);
  finderElement('finder-reference-select')?.addEventListener('change', () => {
    const selected = finderElement('finder-reference-select')?.value;
    finderElement('finder-use-reference').disabled = !selected;
  });
  finderElement('finder-preview-close')?.addEventListener('click', closeFinderPreview);
}

window.openBookFinder = openBookFinder;
window.openFinderPreview = openFinderPreview;
document.addEventListener('DOMContentLoaded', initBookFinder);
