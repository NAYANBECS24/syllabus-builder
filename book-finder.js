'use strict';

const BOOK_FINDER_TIMEOUT_MS = 40000;
const FINDER_IMPORT_MAX_BYTES = 50 * 1024 * 1024;
const FINDER_IMPORT_TIMEOUT_MS = 90000;
const FINDER_SHELF_STORAGE_KEY = 'sylex.researchShelf.v1';
const FINDER_MAX_SHELF_BOOKS = 60;

const finderState = {
  abortController: null,
  references: [],
  shelf: [],
  comparisonIds: new Set(),
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
  const isbn = finderElement('finder-isbn');
  if (button) {
    button.disabled = isBusy;
    button.textContent = isBusy ? 'Searching catalogs…' : 'Run discovery agent';
  }
  if (title) title.disabled = isBusy;
  if (author) author.disabled = isBusy;
  if (isbn) isbn.disabled = isBusy;
}

function setFinderProviderStatus(message) {
  const status = finderElement('finder-provider-status');
  if (status) status.textContent = message;
}

function setFinderSummary(message) {
  const summary = finderElement('finder-results-summary');
  if (summary) summary.textContent = message;
}

function renderFinderTrace(agent) {
  const trace = finderElement('finder-agent-trace');
  if (!trace) return;
  const heading = document.createElement('strong');
  heading.textContent = agent?.strategy || 'Discovery crawler';
  const stages = Array.isArray(agent?.stages) ? agent.stages : [];
  const stageElements = stages.map(stage => {
    const item = document.createElement('span');
    item.className = 'finder-agent-stage';
    const name = document.createElement('b');
    name.textContent = stage?.name || 'Stage';
    const detail = document.createElement('small');
    detail.textContent = stage?.detail || '';
    item.append(name, detail);
    return item;
  });
  if (!stageElements.length) {
    const waiting = document.createElement('span');
    waiting.textContent = 'Waiting for a title, author, or ISBN.';
    stageElements.push(waiting);
  }
  trace.replaceChildren(heading, ...stageElements);
}

function renderFinderConfiguration(configuration) {
  const panel = finderElement('finder-provider-setup');
  if (!panel) return;
  const heading = document.createElement('strong');
  heading.textContent = 'Provider setup';
  const items = [];
  const keyless = Array.isArray(configuration?.keyless_sources) ? configuration.keyless_sources : [];
  if (keyless.length) {
    const item = document.createElement('span');
    item.className = 'configured';
    item.textContent = `${keyless.length} no-key sources active`;
    item.title = keyless.join(', ');
    items.push(item);
  }
  for (const [label, provider] of [
    ['Google Books', configuration?.google_books],
    ['Crossref', configuration?.crossref],
  ]) {
    if (!provider?.state) continue;
    const item = document.createElement('span');
    item.className = provider.state;
    item.textContent = `${label}: ${provider.state === 'configured' ? 'configured' : provider.state === 'required' ? 'setup required' : 'contact recommended'}`;
    item.title = provider.message || '';
    items.push(item);
  }
  if (!items.length) {
    const waiting = document.createElement('span');
    waiting.textContent = 'Configuration is checked when the discovery agent runs.';
    items.push(waiting);
  }
  panel.replaceChildren(heading, ...items);
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
  const discardedCount = Number(coverage?.low_confidence_discarded) || 0;
  const reportedHits = Number(coverage?.catalog_hits_reported) || 0;
  value.textContent = `${formatFinderNumber(candidateCount)} candidates scored`;
  const providersChecked = Number(coverage?.providers_checked) || 0;
  detail.textContent = `${formatFinderNumber(uniqueCount)} edition-aware matches${discardedCount ? ` · ${formatFinderNumber(discardedCount)} weak matches removed` : ''}${reportedHits ? ` · ${formatFinderNumber(reportedHits)} provider records reported` : ''}${providersChecked ? ` · ${providersChecked} sources checked` : ''}`;
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

function finderRecordDownloads(record) {
  const candidates = Array.isArray(record?.downloads) ? [...record.downloads] : [];
  if (record?.download_url) candidates.push({ format: 'PDF', label: 'PDF', url: record.download_url, can_preview: true, can_analyze: true });
  const seen = new Set();
  return candidates.map(download => {
    const url = finderSafeUrl(download?.url);
    const format = String(download?.format || '').toUpperCase();
    if (!url || !['PDF', 'EPUB', 'TXT', 'HTML'].includes(format) || seen.has(url)) return null;
    seen.add(url);
    return {
      format,
      label: String(download?.label || format).replace(/\s+/g, ' ').trim().slice(0, 70),
      url,
      canPreview: download?.can_preview === true || ['PDF', 'TXT', 'HTML'].includes(format),
      canAnalyze: download?.can_analyze === true || format === 'PDF',
    };
  }).filter(Boolean).slice(0, 6);
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

function finderShelfId(record) {
  const isbn = Array.isArray(record?.identifiers) ? record.identifiers.find(Boolean) : '';
  if (isbn) return `isbn:${String(isbn).replace(/[^0-9X]/gi, '').toUpperCase()}`;
  const identity = [record?.title, ...(Array.isArray(record?.authors) ? record.authors : []), record?.year]
    .filter(Boolean)
    .join('|')
    .toLocaleLowerCase()
    .replace(/[^a-z0-9|]+/g, '-')
    .slice(0, 220);
  return `book:${identity || Date.now()}`;
}

function normalizeShelfRecord(record) {
  if (!record || typeof record !== 'object') return null;
  const title = String(record.title || '').replace(/\s+/g, ' ').trim().slice(0, 240);
  if (!title) return null;
  const authors = (Array.isArray(record.authors) ? record.authors : [])
    .map(author => String(author || '').replace(/\s+/g, ' ').trim().slice(0, 140))
    .filter(Boolean)
    .slice(0, 12);
  const identifiers = (Array.isArray(record.identifiers) ? record.identifiers : [])
    .map(value => String(value || '').replace(/[^0-9X]/gi, '').toUpperCase())
    .filter(value => [10, 13].includes(value.length))
    .slice(0, 6);
  const normalized = {
    title,
    authors,
    year: String(record.year || '').replace(/[^0-9]/g, '').slice(0, 4),
    publisher: String(record.publisher || '').replace(/\s+/g, ' ').trim().slice(0, 180),
    identifiers,
    availability: String(record.availability || 'Catalog record').slice(0, 80),
    match_confidence: Math.max(0, Math.min(99, Number(record.match_confidence) || 0)),
    match_label: String(record.match_label || 'Catalog match').slice(0, 80),
    detail_url: finderSafeUrl(record.detail_url),
    view_url: finderSafeUrl(record.view_url),
    cover_url: finderSafeUrl(record.cover_url),
    source_names: (Array.isArray(record.source_names) ? record.source_names : (Array.isArray(record.sources) ? record.sources : []))
      .map(source => String(typeof source === 'string' ? source : (source?.name || '')).trim())
      .filter(Boolean)
      .slice(0, 8),
    saved_at: String(record.saved_at || new Date().toISOString()),
  };
  normalized.shelf_id = String(record.shelf_id || finderShelfId(normalized));
  return normalized;
}

function loadFinderShelf() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(FINDER_SHELF_STORAGE_KEY) || '[]');
    const seen = new Set();
    finderState.shelf = (Array.isArray(parsed) ? parsed : [])
      .map(normalizeShelfRecord)
      .filter(record => record && !seen.has(record.shelf_id) && seen.add(record.shelf_id))
      .slice(0, FINDER_MAX_SHELF_BOOKS);
  } catch {
    finderState.shelf = [];
  }
}

function persistFinderShelf() {
  try {
    window.localStorage.setItem(FINDER_SHELF_STORAGE_KEY, JSON.stringify(finderState.shelf));
    return true;
  } catch {
    finderToast('The browser could not save this research shelf', 'error');
    return false;
  }
}

function finderPersonApa(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length < 2) return parts[0] || '';
  const family = parts.pop();
  const initials = parts.map(part => `${part.charAt(0).toUpperCase()}.`).join(' ');
  return `${family}, ${initials}`;
}

function finderPeopleApa(authors) {
  const people = authors.map(finderPersonApa).filter(Boolean);
  if (people.length < 2) return people[0] || 'Unknown author';
  if (people.length === 2) return `${people[0]} & ${people[1]}`;
  return `${people.slice(0, -1).join(', ')}, & ${people[people.length - 1]}`;
}

function finderPersonMla(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length < 2) return parts[0] || '';
  const family = parts.pop();
  return `${family}, ${parts.join(' ')}`;
}

function finderCitation(record, style = 'apa') {
  const authors = Array.isArray(record.authors) ? record.authors : [];
  const year = record.year || 'n.d.';
  const publisher = record.publisher || 'Publisher not identified';
  const isbn = record.identifiers?.[0] || '';
  const url = record.detail_url || record.view_url || '';
  if (style === 'bibtex') {
    const firstFamily = (authors[0] || 'book').trim().split(/\s+/).pop().replace(/[^a-z0-9]/gi, '') || 'book';
    const firstTitle = record.title.split(/\s+/).find(word => word.length > 3)?.replace(/[^a-z0-9]/gi, '') || 'work';
    const key = `${firstFamily}${record.year || 'nd'}${firstTitle}`;
    const fields = [
      `  title = {${record.title.replace(/[{}]/g, '')}}`,
      authors.length ? `  author = {${authors.join(' and ').replace(/[{}]/g, '')}}` : '',
      record.year ? `  year = {${record.year}}` : '',
      record.publisher ? `  publisher = {${record.publisher.replace(/[{}]/g, '')}}` : '',
      isbn ? `  isbn = {${isbn}}` : '',
      url ? `  url = {${url}}` : '',
    ].filter(Boolean);
    return `@book{${key},\n${fields.join(',\n')}\n}`;
  }
  if (style === 'ris') {
    return [
      'TY  - BOOK',
      ...authors.map(author => `AU  - ${author}`),
      `TI  - ${record.title}`,
      record.year ? `PY  - ${record.year}` : '',
      record.publisher ? `PB  - ${record.publisher}` : '',
      isbn ? `SN  - ${isbn}` : '',
      url ? `UR  - ${url}` : '',
      'ER  -',
    ].filter(Boolean).join('\n');
  }
  if (style === 'mla') {
    let authorText = 'Unknown author';
    if (authors.length === 1) authorText = finderPersonMla(authors[0]);
    else if (authors.length === 2) authorText = `${finderPersonMla(authors[0])}, and ${authors[1]}`;
    else if (authors.length > 2) authorText = `${finderPersonMla(authors[0])}, et al.`;
    return `${authorText}. ${record.title}. ${publisher}${record.year ? `, ${record.year}` : ''}.${isbn ? ` ISBN ${isbn}.` : ''}`;
  }
  const authorText = finderPeopleApa(authors);
  return `${authorText} (${year}). ${record.title}. ${publisher}.${isbn ? ` ISBN ${isbn}.` : ''}`;
}

async function copyFinderCitation(record) {
  const style = finderElement('finder-citation-style')?.value || 'apa';
  const citation = finderCitation(record, style);
  try {
    await navigator.clipboard.writeText(citation);
  } catch {
    const input = document.createElement('textarea');
    input.value = citation;
    input.setAttribute('readonly', '');
    input.style.position = 'fixed';
    input.style.opacity = '0';
    document.body.append(input);
    input.select();
    document.execCommand('copy');
    input.remove();
  }
  finderToast(`${style.toUpperCase()} citation copied`, 'success');
}

function downloadFinderShelf() {
  if (!finderState.shelf.length) return;
  const style = finderElement('finder-citation-style')?.value || 'apa';
  const separator = style === 'ris' ? '\n\n' : '\n\n';
  const content = finderState.shelf.map(record => finderCitation(record, style)).join(separator);
  const extension = style === 'bibtex' ? 'bib' : style === 'ris' ? 'ris' : 'txt';
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `sylex-research-shelf-${style}.${extension}`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  finderToast(`${finderState.shelf.length} citation${finderState.shelf.length === 1 ? '' : 's'} exported`, 'success');
}

function syncFinderShelfButtons() {
  document.querySelectorAll('[data-shelf-id]').forEach(button => {
    const saved = finderState.shelf.some(record => record.shelf_id === button.dataset.shelfId);
    button.classList.toggle('saved', saved);
    button.textContent = saved ? 'Saved to shelf ✓' : 'Save to shelf';
    button.setAttribute('aria-pressed', String(saved));
  });
}

function toggleFinderShelfRecord(record) {
  const normalized = normalizeShelfRecord(record);
  if (!normalized) return;
  const existingIndex = finderState.shelf.findIndex(item => item.shelf_id === normalized.shelf_id);
  if (existingIndex >= 0) {
    finderState.shelf.splice(existingIndex, 1);
    finderState.comparisonIds.delete(normalized.shelf_id);
    finderToast('Edition removed from research shelf', 'info');
  } else {
    if (finderState.shelf.length >= FINDER_MAX_SHELF_BOOKS) {
      finderToast(`The research shelf supports up to ${FINDER_MAX_SHELF_BOOKS} editions`, 'error');
      return;
    }
    finderState.shelf.unshift(normalized);
    finderToast('Edition saved to research shelf', 'success');
  }
  persistFinderShelf();
  renderFinderShelf();
  syncFinderShelfButtons();
}

function useShelfRecord(record) {
  const title = finderElement('finder-title');
  const author = finderElement('finder-author');
  const isbn = finderElement('finder-isbn');
  if (title) title.value = record.title;
  if (author) author.value = record.authors?.[0] || '';
  if (isbn) isbn.value = record.identifiers?.[0] || '';
  finderElement('finder-search-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  window.setTimeout(() => searchFinder(), 250);
}

function createFinderShelfCard(record) {
  const card = document.createElement('article');
  card.className = 'finder-shelf-card';
  const select = document.createElement('label');
  select.className = 'finder-shelf-select';
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = finderState.comparisonIds.has(record.shelf_id);
  checkbox.setAttribute('aria-label', `Select ${record.title} for comparison`);
  checkbox.addEventListener('change', () => {
    if (checkbox.checked && finderState.comparisonIds.size >= 3) {
      checkbox.checked = false;
      finderToast('Compare up to three editions at a time', 'info');
      return;
    }
    if (checkbox.checked) finderState.comparisonIds.add(record.shelf_id);
    else finderState.comparisonIds.delete(record.shelf_id);
    renderFinderShelf();
  });
  const selectText = document.createElement('span');
  selectText.textContent = 'Compare';
  select.append(checkbox, selectText);
  const identity = document.createElement('div');
  identity.className = 'finder-shelf-identity';
  const title = document.createElement('strong');
  title.textContent = record.title;
  const details = document.createElement('span');
  const authors = record.authors?.length ? record.authors.join(', ') : 'Author not listed';
  details.textContent = [authors, record.year, record.publisher, record.identifiers?.[0] ? `ISBN ${record.identifiers[0]}` : ''].filter(Boolean).join(' · ');
  identity.append(title, details);
  const evidence = document.createElement('div');
  evidence.className = 'finder-shelf-evidence';
  evidence.textContent = `${record.match_confidence}% · ${record.availability} · ${record.source_names.length || 1} source${record.source_names.length === 1 ? '' : 's'}`;
  const actions = document.createElement('div');
  actions.className = 'finder-shelf-card-actions';
  actions.append(
    createFinderButton('Copy citation', 'finder-action', () => copyFinderCitation(record)),
    createFinderButton('Find again', 'finder-action', () => useShelfRecord(record)),
    createFinderButton('Remove', 'finder-action finder-action-danger', () => toggleFinderShelfRecord(record)),
  );
  card.append(select, identity, evidence, actions);
  return card;
}

function renderFinderComparison() {
  const panel = finderElement('finder-comparison');
  if (!panel) return;
  const selected = finderState.shelf.filter(record => finderState.comparisonIds.has(record.shelf_id));
  if (selected.length < 2) {
    panel.hidden = true;
    panel.replaceChildren();
    return;
  }
  const heading = document.createElement('div');
  heading.className = 'finder-comparison-heading';
  const title = document.createElement('strong');
  title.textContent = `Evidence comparison · ${selected.length} editions`;
  const close = createFinderButton('Close comparison', 'btn btn-sm btn-ghost', () => {
    finderState.comparisonIds.clear();
    renderFinderShelf();
  });
  heading.append(title, close);
  const tableWrap = document.createElement('div');
  tableWrap.className = 'finder-comparison-table-wrap';
  const table = document.createElement('table');
  const rows = [
    ['Title', record => record.title],
    ['Authors', record => record.authors.join(', ') || 'Not listed'],
    ['Year', record => record.year || '—'],
    ['Publisher', record => record.publisher || '—'],
    ['ISBN', record => record.identifiers[0] || '—'],
    ['Confidence', record => `${record.match_confidence}% · ${record.match_label}`],
    ['Access', record => record.availability],
    ['Catalog evidence', record => record.source_names.join(', ') || '1 catalog source'],
  ];
  rows.forEach(([label, value]) => {
    const row = document.createElement('tr');
    const header = document.createElement('th');
    header.scope = 'row';
    header.textContent = label;
    row.append(header, ...selected.map(record => {
      const cell = document.createElement('td');
      cell.textContent = value(record);
      return cell;
    }));
    table.append(row);
  });
  tableWrap.append(table);
  panel.replaceChildren(heading, tableWrap);
  panel.hidden = false;
}

function renderFinderShelf() {
  const shelf = finderElement('finder-shelf');
  const count = finderElement('finder-shelf-count');
  const compare = finderElement('finder-compare-shelf');
  const exportButton = finderElement('finder-export-shelf');
  const clear = finderElement('finder-clear-shelf');
  const validIds = new Set(finderState.shelf.map(record => record.shelf_id));
  finderState.comparisonIds.forEach(id => {
    if (!validIds.has(id)) finderState.comparisonIds.delete(id);
  });
  if (count) count.textContent = `${finderState.shelf.length} saved`;
  if (compare) {
    compare.disabled = finderState.comparisonIds.size < 2;
    compare.textContent = finderState.comparisonIds.size
      ? `Compare selected (${finderState.comparisonIds.size})`
      : 'Compare selected';
  }
  if (exportButton) exportButton.disabled = !finderState.shelf.length;
  if (clear) clear.disabled = !finderState.shelf.length;
  if (shelf) {
    if (finderState.shelf.length) shelf.replaceChildren(...finderState.shelf.map(createFinderShelfCard));
    else {
      const empty = document.createElement('div');
      empty.className = 'finder-shelf-empty';
      const heading = document.createElement('strong');
      heading.textContent = 'No saved editions yet.';
      const detail = document.createElement('span');
      detail.textContent = 'Use “Save to shelf” on a catalog result to build a durable research set.';
      empty.append(heading, detail);
      shelf.replaceChildren(empty);
    }
  }
  renderFinderComparison();
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
  if (label) label.textContent = title || 'Provider-authorized preview';
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

async function importFinderPdf(record, button, pdfUrl = record.download_url) {
  const safeUrl = finderSafeUrl(pdfUrl);
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
  const coverUrl = finderSafeUrl(record.cover_url);
  if (coverUrl) {
    const cover = document.createElement('img');
    cover.className = 'finder-result-cover';
    cover.src = coverUrl;
    cover.alt = '';
    cover.loading = 'lazy';
    cover.referrerPolicy = 'no-referrer';
    cover.addEventListener('error', () => cover.remove(), { once: true });
    top.append(cover);
  }
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
  match.className = `finder-match-label ${['Exact match', 'Exact ISBN'].includes(record.match_label) ? 'exact' : ''}`;
  match.textContent = record.match_label || 'Catalog match';
  const downloads = finderRecordDownloads(record);
  const access = document.createElement('span');
  access.className = `finder-access-label ${downloads.length ? 'download' : ''}`;
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
  const shelfId = normalizeShelfRecord(record)?.shelf_id || finderShelfId(record);
  const saved = finderState.shelf.some(item => item.shelf_id === shelfId);
  const save = createFinderButton(saved ? 'Saved to shelf ✓' : 'Save to shelf', `finder-action finder-action-save${saved ? ' saved' : ''}`, () => toggleFinderShelfRecord(record));
  save.dataset.shelfId = shelfId;
  save.setAttribute('aria-pressed', String(saved));
  const view = createFinderLink(record.availability === 'Preview available' ? 'Preview book ↗' : 'View / read ↗', record.view_url, 'finder-action finder-action-primary');
  const previewDownload = downloads.find(download => download.canPreview);
  const analyzablePdf = downloads.find(download => download.format === 'PDF' && download.canAnalyze);
  const workspacePreview = previewDownload
    ? createFinderButton(`Preview ${previewDownload.format} in workspace`, 'finder-action finder-action-preview', () => openFinderPreview(previewDownload.url, record.title))
    : null;
  const inspect = analyzablePdf
    ? createFinderButton('Analyze PDF in Book Explorer', 'finder-action finder-action-inspect', event => importFinderPdf(record, event.currentTarget, analyzablePdf.url))
    : null;
  const details = createFinderLink('Catalog details ↗', record.detail_url, 'finder-action');
  actions.append(save);
  if (view) actions.append(view);
  if (workspacePreview) actions.append(workspacePreview);
  if (inspect) actions.append(inspect);
  downloads.forEach((download, index) => {
    const duplicateFormat = downloads.some((other, otherIndex) => otherIndex !== index && other.format === download.format);
    const detail = duplicateFormat && download.label !== download.format ? ` · ${download.label.slice(0, 28)}` : '';
    const link = createFinderLink(`Download ${download.format}${detail} ↗`, download.url, 'finder-action finder-action-download');
    if (link) actions.append(link);
  });
  if (details) actions.append(details);

  card.append(top, confidenceBlock, sources, actions);
  return card;
}

function renderFinderResults(data) {
  const results = finderElement('finder-results');
  if (!results) return;
  const items = Array.isArray(data.results) ? data.results : [];
  const providerSummary = (Array.isArray(data.providers) ? data.providers : []).map(provider => {
    if (provider.status === 'available') return `${provider.name}: ${provider.matches} candidates`;
    if (provider.status === 'configuration_required') return `${provider.name}: setup required`;
    return `${provider.name}: unavailable${provider.detail ? ` (${provider.detail})` : ''}`;
  }).join(' · ');
  setFinderProviderStatus(providerSummary || 'Catalog search complete');
  setFinderCoverage(data.coverage);
  renderFinderTrace(data.agent);
  renderFinderConfiguration(data.configuration);
  const coverage = data.coverage || {};
  const candidateCount = Number(coverage.candidates_evaluated) || 0;
  const queryLabel = data.query?.title || data.query?.isbn || '';
  setFinderSummary(items.length
    ? `${candidateCount ? `${formatFinderNumber(candidateCount)} trusted catalog candidates scored; ` : ''}${items.length} best match${items.length === 1 ? '' : 'es'} shown for “${queryLabel}”. Confidence combines ISBN, title, author, edition, and catalog agreement.`
    : `No catalog matches found for “${queryLabel}”. Try a shorter title, remove the author, or enter the ISBN.`);
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
  const isbnValue = Array.isArray(book.isbn) ? book.isbn[0] : (book.isbn || book.isbn13 || book.isbn10 || '');
  const isbn = String(isbnValue).replace(/[^0-9Xx]/g, '').toUpperCase();
  return {
    id: `${index}-${title}-${author}`,
    title,
    author,
    isbn: [10, 13].includes(isbn.length) ? isbn : '',
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
  const isbn = finderElement('finder-isbn');
  if (title) title.value = reference.title;
  if (author) author.value = reference.author;
  if (isbn) isbn.value = reference.isbn;
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
  const isbn = finderElement('finder-isbn');
  if (title) title.value = reference.title;
  if (author) author.value = reference.author;
  if (isbn) isbn.value = reference.isbn;
  window.setTimeout(() => searchFinder(), 0);
}

async function searchFinder(event) {
  event?.preventDefault();
  const title = finderElement('finder-title')?.value.replace(/\s+/g, ' ').trim() || '';
  const author = finderElement('finder-author')?.value.replace(/\s+/g, ' ').trim() || '';
  const rawIsbn = finderElement('finder-isbn')?.value.trim() || '';
  const isbn = rawIsbn.replace(/[^0-9Xx]/g, '').toUpperCase();
  if (!title && !isbn) {
    finderToast('Enter a book title or ISBN', 'error');
    finderElement('finder-title')?.focus();
    return;
  }
  if (title && title.length < 2) {
    finderToast('Enter at least two characters of the book title', 'error');
    finderElement('finder-title')?.focus();
    return;
  }
  if (rawIsbn && ![10, 13].includes(isbn.length)) {
    finderToast('Enter a valid 10 or 13 character ISBN', 'error');
    finderElement('finder-isbn')?.focus();
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
  renderFinderTrace({
    strategy: isbn ? 'ISBN-first exact edition resolution' : 'Adaptive title and author discovery',
    stages: [{ name: 'Running', detail: 'Querying catalog APIs in parallel and validating candidates…' }],
  });
  try {
    const baseUrl = String(window.STATE.serverUrl || window.location.origin).replace(/\/$/, '');
    const response = await fetch(`${baseUrl}/api/book-discovery`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, author, isbn }),
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
  loadFinderShelf();
  renderFinderShelf();
  form.addEventListener('submit', searchFinder);
  finderElement('finder-load-references')?.addEventListener('click', loadFinderReferences);
  finderElement('finder-use-reference')?.addEventListener('click', useFinderReference);
  finderElement('finder-reference-select')?.addEventListener('change', () => {
    const selected = finderElement('finder-reference-select')?.value;
    finderElement('finder-use-reference').disabled = !selected;
  });
  finderElement('finder-preview-close')?.addEventListener('click', closeFinderPreview);
  finderElement('finder-compare-shelf')?.addEventListener('click', () => {
    renderFinderComparison();
    finderElement('finder-comparison')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  finderElement('finder-export-shelf')?.addEventListener('click', downloadFinderShelf);
  finderElement('finder-clear-shelf')?.addEventListener('click', () => {
    if (!finderState.shelf.length || !window.confirm('Clear every saved edition from this browser?')) return;
    finderState.shelf = [];
    finderState.comparisonIds.clear();
    persistFinderShelf();
    renderFinderShelf();
    syncFinderShelfButtons();
    finderToast('Research shelf cleared', 'info');
  });
}

window.openBookFinder = openBookFinder;
window.openFinderPreview = openFinderPreview;
document.addEventListener('DOMContentLoaded', initBookFinder);
