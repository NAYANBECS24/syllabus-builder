'use strict';

const BOOK_MAX_BYTES = 50 * 1024 * 1024;
const BOOK_SEARCH_TIMEOUT_MS = 120000;

const bookState = {
  objectUrl: null,
  activePage: null,
  searchAbortController: null,
  viewerRequestId: 0,
};

const bookElement = id => document.getElementById(id);

function bookToast(message, type = 'info') {
  if (typeof window.toast === 'function') {
    window.toast(message, type);
  }
}

function formatBookBytes(bytes) {
  if (!Number.isFinite(bytes)) return 'Unknown size';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setBookSearchStatus(message = '') {
  const status = bookElement('book-search-status');
  if (status) status.textContent = message;
}

function createBookEmptyState(title, description) {
  const wrapper = document.createElement('div');
  wrapper.className = 'book-results-empty';
  const heading = document.createElement('strong');
  heading.textContent = title;
  const detail = document.createElement('span');
  detail.textContent = description;
  wrapper.append(heading, detail);
  return wrapper;
}

function setBookResultsEmpty(title, description) {
  const results = bookElement('book-search-results');
  if (results) results.replaceChildren(createBookEmptyState(title, description));
}

function setBookOutlineEmpty(message) {
  const list = bookElement('book-outline-list');
  if (list) {
    const empty = document.createElement('div');
    empty.className = 'book-outline-empty';
    empty.textContent = message;
    list.replaceChildren(empty);
  }
}

function resetBookSearch() {
  bookState.activePage = null;
  setBookSearchStatus('');
  const count = bookElement('book-results-count');
  if (count) count.textContent = 'Ready for a topic search';
  setBookResultsEmpty('Search results will appear here.', 'Enter a topic or lesson name to find matching pages.');
  const outlineCount = bookElement('book-outline-count');
  if (outlineCount) outlineCount.textContent = 'Search a book to detect headings';
  setBookOutlineEmpty('Detected chapters, units, lessons, and numbered sections appear here.');
}

function setBookViewerLoading(isLoading, message = 'Opening full book…') {
  const loading = bookElement('book-viewer-loading');
  if (!loading) return;
  const label = loading.querySelector('strong');
  if (label) label.textContent = message;
  loading.hidden = !isLoading;
}

function showBookViewerEmpty() {
  bookState.viewerRequestId += 1;
  const empty = bookElement('book-viewer-empty');
  const stage = bookElement('book-viewer-stage');
  const pageLabel = bookElement('book-active-page');
  const viewer = bookElement('book-pdf-viewer');
  const fullBookLink = bookElement('book-open-full-book');
  if (viewer) viewer.removeAttribute('src');
  if (empty) empty.hidden = false;
  if (stage) stage.hidden = true;
  if (pageLabel) pageLabel.textContent = 'No page selected';
  if (fullBookLink) {
    fullBookLink.hidden = true;
    fullBookLink.removeAttribute('href');
  }
  setBookViewerLoading(false);
}

function updateBookFileSummary(file) {
  const fileChosen = bookElement('book-file-chosen');
  const fileName = bookElement('book-file-name');
  const fileMeta = bookElement('book-file-meta');
  if (fileChosen) fileChosen.hidden = false;
  if (fileName) fileName.textContent = file.name;
  if (fileMeta) fileMeta.textContent = `${formatBookBytes(file.size)} · ready to search`;
}

function handleBookFile(file) {
  if (!file) return;
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
  if (!isPdf) {
    bookToast('Please choose a PDF book', 'error');
    return;
  }
  if (file.size === 0) {
    bookToast('This PDF is empty', 'error');
    return;
  }
  if (file.size > BOOK_MAX_BYTES) {
    bookToast('Book PDF exceeds the 50 MB upload limit', 'error');
    return;
  }

  if (bookState.searchAbortController) {
    bookState.searchAbortController.abort();
    bookState.searchAbortController = null;
  }
  if (bookState.objectUrl) URL.revokeObjectURL(bookState.objectUrl);

  bookState.objectUrl = URL.createObjectURL(file);
  window.STATE.bookFile = file;
  window.STATE.bookObjectUrl = bookState.objectUrl;
  updateBookFileSummary(file);
  bookElement('book-query').disabled = false;
  bookElement('book-search-button').disabled = false;
  resetBookSearch();
  showBookViewerEmpty();
  bookToast(`${file.name} is ready to search`, 'success');
  bookElement('book-query').focus();
}

function clearBookFile() {
  if (bookState.searchAbortController) {
    bookState.searchAbortController.abort();
    bookState.searchAbortController = null;
  }
  if (bookState.objectUrl) URL.revokeObjectURL(bookState.objectUrl);
  bookState.objectUrl = null;
  bookState.activePage = null;
  delete window.STATE.bookFile;
  delete window.STATE.bookObjectUrl;

  const input = bookElement('book-file-input');
  if (input) input.value = '';
  const fileChosen = bookElement('book-file-chosen');
  if (fileChosen) fileChosen.hidden = true;
  const query = bookElement('book-query');
  if (query) {
    query.value = '';
    query.disabled = true;
  }
  const button = bookElement('book-search-button');
  if (button) button.disabled = true;
  const count = bookElement('book-results-count');
  if (count) count.textContent = 'Upload a book to begin';
  setBookSearchStatus('');
  setBookResultsEmpty('Search results will appear here.', 'Select a book PDF before searching for a topic.');
  const outlineCount = bookElement('book-outline-count');
  if (outlineCount) outlineCount.textContent = 'Upload a book to begin';
  setBookOutlineEmpty('Select a book PDF before viewing its contents.');
  showBookViewerEmpty();
}

function setBookSearchBusy(isBusy) {
  const button = bookElement('book-search-button');
  const query = bookElement('book-query');
  if (button) {
    button.disabled = isBusy || !window.STATE.bookFile;
    button.textContent = isBusy ? 'Searching…' : 'Search';
  }
  if (query) query.setAttribute('aria-busy', String(isBusy));
}

async function ensureBookSearchService() {
  if (window.STATE?.serverOnline) return true;
  if (typeof window.checkServer === 'function') {
    return window.checkServer(true);
  }
  return false;
}

function createBookResult(result) {
  const item = document.createElement('button');
  item.type = 'button';
  item.className = 'book-result';
  item.dataset.page = String(result.page);
  item.setAttribute('aria-label', `Open PDF page ${result.page}`);

  const top = document.createElement('span');
  top.className = 'book-result-top';
  const page = document.createElement('span');
  page.className = 'book-page-pill';
  page.textContent = `Page ${result.page}`;
  const confidence = document.createElement('span');
  confidence.className = `book-match-badge${result.exact_match ? ' exact' : ''}`;
  confidence.textContent = result.exact_match ? 'Exact phrase' : 'All terms';
  top.append(page, confidence);

  const snippet = document.createElement('span');
  snippet.className = 'book-result-snippet';
  snippet.textContent = result.snippet || 'Topic match found on this page.';

  const section = document.createElement('span');
  section.className = 'book-result-section';
  section.textContent = result.section || `Source PDF page ${result.page}`;

  const terms = document.createElement('span');
  terms.className = 'book-result-terms';
  const matchedTerms = Array.isArray(result.matched_terms) ? result.matched_terms : [];
  terms.textContent = matchedTerms.length ? `Matched: ${matchedTerms.join(' · ')}` : 'Topic match';

  item.append(top, section, snippet, terms);
  item.addEventListener('click', () => openBookPage(result.page, item, true));
  return item;
}

function createBookOutlineItem(entry) {
  const item = document.createElement('button');
  item.type = 'button';
  item.className = 'book-outline-item';
  item.dataset.page = String(entry.page);
  item.setAttribute('aria-label', `Open ${entry.label || entry.kind || 'heading'} on PDF page ${entry.page}`);

  const page = document.createElement('span');
  page.className = 'book-outline-page';
  page.textContent = `p. ${entry.page}`;
  const details = document.createElement('span');
  details.className = 'book-outline-details';
  const label = document.createElement('strong');
  label.textContent = entry.label || entry.kind || 'Heading';
  const title = document.createElement('span');
  title.textContent = entry.title || 'Untitled section';
  details.append(label, title);
  item.append(page, details);
  item.addEventListener('click', () => openBookPage(entry.page, item, true));
  return item;
}

function renderBookOutline(outline) {
  const list = bookElement('book-outline-list');
  const count = bookElement('book-outline-count');
  const entries = Array.isArray(outline)
    ? outline.filter(entry => Number.isInteger(Number(entry?.page)) && Number(entry.page) > 0)
    : [];
  if (count) {
    count.textContent = entries.length
      ? `${entries.length} detected ${entries.length === 1 ? 'heading' : 'headings'}`
      : 'No printed headings detected';
  }
  if (!list) return;
  if (!entries.length) {
    setBookOutlineEmpty('No printed chapter or lesson headings were detected. You can still search any topic and read the complete PDF.');
    return;
  }
  list.replaceChildren(...entries.map(createBookOutlineItem));
}

function renderBookResults(data) {
  const results = Array.isArray(data.results) ? data.results : [];
  const list = bookElement('book-search-results');
  const count = bookElement('book-results-count');
  const status = bookElement('book-search-status');
  const totalMatches = Number(data.total_matches) || 0;

  if (count) {
    count.textContent = totalMatches
      ? `${totalMatches} matching ${totalMatches === 1 ? 'page' : 'pages'}${totalMatches > results.length ? ` · showing top ${results.length}` : ''}`
      : 'No matching pages';
  }
  if (status) {
    const indexed = `${data.searchable_pages || 0} of ${data.total_pages || 0} pages searchable`;
    status.textContent = data.cached ? `Index reused · ${indexed}` : indexed;
  }
  renderBookOutline(data.outline);

  if (!list) return;
  if (!results.length) {
    list.replaceChildren(createBookEmptyState('No exact page match found.', 'Try a shorter topic, a chapter title, or another distinctive keyword.'));
    return;
  }
  list.replaceChildren(...results.map(createBookResult));
  openBookPage(results[0].page, list.querySelector('.book-result'), false);
}

function openBookPage(pageNumber, trigger, shouldScroll) {
  const page = Number(pageNumber);
  if (!window.STATE?.bookFile || !bookState.objectUrl || !Number.isInteger(page) || page < 1) return;

  bookState.viewerRequestId += 1;
  const requestId = bookState.viewerRequestId;
  bookState.activePage = page;
  const viewer = bookElement('book-pdf-viewer');
  const empty = bookElement('book-viewer-empty');
  const stage = bookElement('book-viewer-stage');
  const pageLabel = bookElement('book-active-page');
  const fullBookLink = bookElement('book-open-full-book');
  if (viewer) viewer.removeAttribute('src');
  if (empty) empty.hidden = true;
  if (stage) stage.hidden = false;
  if (pageLabel) pageLabel.textContent = `Full PDF · page ${page}`;
  if (fullBookLink) {
    fullBookLink.href = `${bookState.objectUrl}#page=${page}&zoom=page-width`;
    fullBookLink.hidden = false;
  }
  setBookViewerLoading(true, `Opening full book at page ${page}…`);

  document.querySelectorAll('.book-result, .book-outline-item').forEach(item => {
    const active = item === trigger || Number(item.dataset.page) === page;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'true');
    else item.removeAttribute('aria-current');
  });
  if (shouldScroll) bookElement('book-viewer-title')?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  if (viewer) {
    viewer.onload = () => {
      if (bookState.viewerRequestId === requestId) setBookViewerLoading(false);
    };
    viewer.src = `${bookState.objectUrl}#page=${page}&zoom=page-width`;
  }
  window.setTimeout(() => {
    if (bookState.viewerRequestId === requestId) setBookViewerLoading(false);
  }, 3500);
}

async function searchBook(event) {
  event?.preventDefault();
  const file = window.STATE?.bookFile;
  const query = bookElement('book-query')?.value.trim() || '';
  if (!file) {
    bookToast('Upload a book PDF before searching', 'error');
    return;
  }
  if (query.length < 2) {
    bookToast('Enter at least two characters to search', 'error');
    bookElement('book-query')?.focus();
    return;
  }
  if (!(await ensureBookSearchService())) {
    setBookSearchStatus('Search service unavailable');
    bookToast('Start or connect the SYLEX server to search this book', 'error');
    return;
  }

  if (bookState.searchAbortController) bookState.searchAbortController.abort();
  const controller = new AbortController();
  bookState.searchAbortController = controller;
  const timeoutId = window.setTimeout(() => controller.abort(), BOOK_SEARCH_TIMEOUT_MS);
  const formData = new FormData();
  formData.append('book', file, file.name);
  formData.append('query', query);
  setBookSearchBusy(true);
  setBookSearchStatus('Searching pages…');

  try {
    const baseUrl = String(window.STATE.serverUrl || window.location.origin).replace(/\/$/, '');
    const response = await fetch(`${baseUrl}/api/book-search`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Search failed (${response.status})`);
    renderBookResults(data);
    bookToast(data.total_matches ? `Found ${data.total_matches} matching page${data.total_matches === 1 ? '' : 's'}` : 'No matching pages found', data.total_matches ? 'success' : 'info');
  } catch (error) {
    if (error.name === 'AbortError') {
      setBookSearchStatus('Search timed out');
      bookToast('Book search timed out. Try a smaller PDF or start the service again.', 'error');
    } else {
      setBookSearchStatus('Search failed');
      setBookResultsEmpty('Unable to search this book.', error.message || 'Please retry with a text-based PDF.');
      bookToast(error.message || 'Book search failed', 'error');
    }
  } finally {
    window.clearTimeout(timeoutId);
    if (bookState.searchAbortController === controller) bookState.searchAbortController = null;
    setBookSearchBusy(false);
  }
}

function initBookExplorer() {
  const zone = bookElement('book-drop-zone');
  const input = bookElement('book-file-input');
  const form = bookElement('book-search-form');
  if (!zone || !input || !form) return;

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      input.click();
    }
  });
  zone.addEventListener('dragover', event => {
    event.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', event => {
    event.preventDefault();
    zone.classList.remove('drag-over');
    handleBookFile(event.dataTransfer.files[0]);
  });
  input.addEventListener('change', () => handleBookFile(input.files[0]));
  form.addEventListener('submit', searchBook);
  bookElement('book-clear-file')?.addEventListener('click', clearBookFile);
  document.querySelectorAll('[data-book-query]').forEach(button => {
    button.addEventListener('click', () => {
      const query = bookElement('book-query');
      if (!query || query.disabled) return;
      query.value = button.dataset.bookQuery || '';
      query.focus();
    });
  });
  window.addEventListener('beforeunload', () => {
    if (bookState.objectUrl) URL.revokeObjectURL(bookState.objectUrl);
  });
}

window.openBookPage = openBookPage;
document.addEventListener('DOMContentLoaded', initBookExplorer);
