'use strict';

const isLocal = typeof window !== 'undefined' && 
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

// ── Provider defaults ────────────────────────────────────────────────
const SYLEX_NVIDIA_MODEL = 'z-ai/glm-5.3';
const SYLEX_CLOUD_PROVIDER = 'nvidia';
const SYLEX_CLOUD_AUTOFALLBACK = true;
if (typeof window !== 'undefined') {
  window.SYLEX_NVIDIA_MODEL = SYLEX_NVIDIA_MODEL;
}

const defaultServerUrl = (typeof window !== 'undefined' && window.location.origin && window.location.origin !== 'null')
  ? (isLocal && window.location.port !== '7823' && window.location.port !== '' ? 'http://localhost:7823' : window.location.origin)
  : 'http://localhost:7823';

const STATE = {
  section:        'home',
  task1Result:    (typeof DEMO_TASK1 !== 'undefined' ? DEMO_TASK1 : null),
  task2Result:    (typeof DEMO_TASK2 !== 'undefined' ? DEMO_TASK2 : null),
  serverOnline:   false,
  serverUrl:      defaultServerUrl,
  extractionMode: localStorage.getItem('sylex_mode') || 'online',
};
window.STATE = STATE;

// ── DOM helpers ─────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const esc = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

function getCloudModel() {
  const selector = $('cloud-model-select');
  const savedModel = localStorage.getItem('sylex_cloud_model');
  const availableModels = selector ? [...selector.options].map(option => option.value) : [];
  const model = selector?.value || savedModel || SYLEX_NVIDIA_MODEL;
  return !availableModels.length || availableModels.includes(model) ? model : SYLEX_NVIDIA_MODEL;
}

function saveCloudModelSetting() {
  localStorage.setItem('sylex_cloud_model', getCloudModel());
  if (typeof window.updateChatModeUI === 'function') {
    window.updateChatModeUI(STATE.extractionMode);
  }
  toast('Cloud model updated', 'success');
}

window.getSylexCloudModel = getCloudModel;
window.saveCloudModelSetting = saveCloudModelSetting;

// ── Navigation ──────────────────────────────────────────────────────
function navigate(section) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  const target = $(`section-${section}`);
  const link   = document.querySelector(`[data-nav="${section}"]`);
  if (target) target.classList.add('active');
  if (link)   link.classList.add('active');
  STATE.section = section;
}
window.navigate = navigate;

// ── Upload ──────────────────────────────────────────────────────────
function initUpload() {
  const zone  = $('drop-zone');
  const input = $('file-input');
  zone.addEventListener('click',      () => input.click());
  zone.addEventListener('dragover',   e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave',  () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop',       e => {
    e.preventDefault(); zone.classList.remove('drag-over');
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  });
  input.addEventListener('change', () => { if (input.files[0]) handleFile(input.files[0]); });
  $('btn-remove-file')?.addEventListener('click', clearFile);
  $('btn-run')?.addEventListener('click', runExtraction);
}

function handleFile(f) {
  if (!f.name.toLowerCase().endsWith('.pdf')) {
    toast('⚠ Please select a PDF file', 'error'); return;
  }
  STATE.pdfFile = f;
  $('chosen-name').textContent = f.name;
  $('chosen-size').textContent = fmtBytes(f.size);
  $('file-chosen').classList.add('visible');
  $('btn-run').disabled = false;
  toast('📄 ' + f.name + ' loaded', 'success');
}

function clearFile() {
  STATE.pdfFile = null;
  $('file-chosen').classList.remove('visible');
  $('file-input').value = '';
  $('btn-run').disabled = true;
}

function fmtBytes(b) {
  if (b < 1024) return b + ' B';
  if (b < 1<<20) return (b/1024).toFixed(1) + ' KB';
  return (b/(1<<20)).toFixed(2) + ' MB';
}

// ── Server check ────────────────────────────────────────────────────
async function checkServer() {
  let url = ($('server-url')?.value || STATE.serverUrl || defaultServerUrl).trim();
  if (!isLocal && $('server-url') && $('server-url').value.includes('localhost:7823')) {
    url = window.location.origin;
    $('server-url').value = url;
  }
  STATE.serverUrl = url;
  const badge = $('server-badge');
  const label = $('server-label');
  const bar   = $('server-status-bar');
  const barText = $('server-status-text');
  const connRes = $('conn-result');

  try {
    const fetchUrl = url.replace(/\/+$/, '');
    const resp = await fetch(fetchUrl + '/api/status', { signal: AbortSignal.timeout(4000) });
    if (resp.ok) {
      const data = await resp.json();
      STATE.serverOnline = true;
      badge.className = 'nav-badge online';
      if (label) label.textContent = 'Server Online';
      if (bar) { bar.className = 'server-bar online'; barText.innerHTML = `✅ SYLEX server running at <code>${fetchUrl}</code>`; }
      if (connRes) connRes.innerHTML = `<span style="color:var(--accent-green)">✓ Connected — Python ${data.python || ''}</span>`;
      toast('✅ Server connected', 'success');
      return true;
    }
  } catch (_) {}
  STATE.serverOnline = false;
  badge.className = 'nav-badge offline';
  if (label) label.textContent = 'Offline Mode';
  if (bar) { bar.className = 'server-bar offline'; barText.innerHTML = `⚡ Demo mode — run <code>python sylex_server.py</code> for live extraction`; }
  if (connRes) connRes.innerHTML = `<span style="color:var(--accent-amber)">⚠ No server — run python sylex_server.py</span>`;
  return false;
}
window.checkServer = checkServer;

// ── Mode Handling (Online vs Offline) ────────────────────────────────
function setMode(mode) {
  STATE.extractionMode = mode;
  localStorage.setItem('sylex_mode', mode);

  const cardOff = $('mode-card-offline');
  const cardOn  = $('mode-card-online');
  const drawer  = $('online-config-drawer');
  const badge   = $('mode-badge');
  const label   = $('mode-nav-label');
  const btnRun  = $('btn-run');

  if (mode === 'online') {
    cardOff?.classList.remove('active');
    cardOn?.classList.add('active');
    if (drawer) drawer.style.display = 'block';
    if (badge) { badge.className = 'mode-nav-badge online'; }
    if (label) { label.textContent = '🌐 Online Mode'; }
    if (btnRun) { btnRun.innerHTML = '🌐 Extract with Cloud AI'; }
    toast('🌐 Online Mode active — Cloud AI enabled', 'info');
  } else {
    cardOn?.classList.remove('active');
    cardOff?.classList.add('active');
    if (drawer) drawer.style.display = 'none';
    if (badge) { badge.className = 'mode-nav-badge offline'; }
    if (label) { label.textContent = '⚡ Offline Engine'; }
    if (btnRun) { btnRun.innerHTML = '⚡ Extract (Offline)'; }
    toast('⚡ Offline Mode active — 100% local engine', 'success');
  }
  if (typeof window.updateChatModeUI === 'function') {
    window.updateChatModeUI(mode);
  }
}
window.setMode = setMode;

function loadOnlineSettings() {
  const selector = $('cloud-model-select');
  let savedModel = localStorage.getItem('sylex_cloud_model');
  const available = selector ? [...selector.options].map(o => o.value) : [];
  if (savedModel && (!available.includes(savedModel) || savedModel.includes('nemotron'))) {
    savedModel = SYLEX_NVIDIA_MODEL;
    localStorage.setItem('sylex_cloud_model', savedModel);
  }
  if (selector && savedModel && available.includes(savedModel)) {
    selector.value = savedModel;
  }
  const savedMode = localStorage.getItem('sylex_mode') || 'online';
  setMode(savedMode);
}

async function testOnlineKey() {
  const provider = SYLEX_CLOUD_PROVIDER;
  const model = getCloudModel();
  const statusMsg = $('key-status-msg');
  const btn = $('btn-test-key');

  if (btn) btn.disabled = true;
  if (statusMsg) { statusMsg.style.color = 'var(--accent-cyan)'; statusMsg.textContent = 'Testing connection...'; }

  try {
    const fetchBase = (!isLocal && typeof window !== 'undefined' ? window.location.origin : STATE.serverUrl).replace(/\/+$/, '');
    const resp = await fetch(fetchBase + '/api/test-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, model }),
      signal: AbortSignal.timeout(25000)
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.status !== 'ok') {
      throw new Error(data.error || `Vercel function returned HTTP ${resp.status}`);
    }
    if (statusMsg) {
      statusMsg.style.color = 'var(--accent-green)';
      statusMsg.textContent = `Connected (${data.latency_ms || 0}ms)`;
    }
    toast('Connection verified', 'success');
    STATE.serverOnline = true;
  } catch (e) {
    const message = e.name === 'TimeoutError' ? 'Connection timed out' : e.message;
    if (statusMsg) { statusMsg.style.color = 'var(--accent-red)'; statusMsg.textContent = message; }
    toast('Connection failed: ' + message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}
window.testOnlineKey = testOnlineKey;

// ── Extraction ──────────────────────────────────────────────────────
async function runExtraction() {
  if (!STATE.pdfFile) { toast('Select a PDF first', 'error'); return; }

  const task   = $('task-select')?.value || '1';
  const course = $('course-input')?.value?.trim() || '';
  const debug  = $('debug-toggle')?.classList.contains('on');
  const hintsFile = $('hints-input')?.files?.[0] || null;
  const mode = STATE.extractionMode || 'offline';

  if (task === '2' && !course) {
    toast('⚠️ Enter a Course Code for Task 2, or choose Task 1 to list all courses', 'error');
    $('course-input')?.focus();
    return;
  }

  // Show progress
  $('extract-progress').style.display = 'block';
  $('btn-run').disabled = true;
  setProgress(5, mode === 'online' ? 'Contacting Cloud AI...' : 'Uploading PDF to engine...');

  if (!STATE.serverOnline) {
    // Simulate with demo data
    setProgress(30, 'Parsing document...');
    await sleep(400);
    setProgress(60, 'Extracting courses...');
    await sleep(500);
    setProgress(90, 'Finalizing...');
    await sleep(400);
    setProgress(100, 'Done');
    STATE.task1Result = DEMO_TASK1;
    STATE.task2Result = DEMO_TASK2;
    renderAll();
    navigate('results');
    if (task === '2') switchResultsTab('deep');
    else switchResultsTab('courses');
    toast('Demo results loaded (server offline)', 'success');
    $('extract-progress').style.display = 'none';
    $('btn-run').disabled = false;
    return;
  }

  try {
    const form = new FormData();
    form.append('pdf', STATE.pdfFile);
    if (task === '2' && course) form.append('course', course);
    if (debug) form.append('debug', '1');
    if (hintsFile) form.append('hints', await hintsFile.text());
    else if (STATE.hintsData) form.append('hints', JSON.stringify(STATE.hintsData));

    form.append('mode', mode);
    if (mode === 'online') {
      form.append('provider', SYLEX_CLOUD_PROVIDER);
      form.append('model', getCloudModel());
    }

    setProgress(20, mode === 'online' ? 'Running Cloud AI Extraction...' : 'Sending to offline engine...');
    const resp = await fetch(STATE.serverUrl + '/api/extract', {
      method: 'POST', body: form,
      signal: AbortSignal.timeout(120000),
    });

    setProgress(70, 'Processing response...');
    let data = await resp.json();

    if (data.error) {
      if (mode === 'online' && SYLEX_CLOUD_AUTOFALLBACK) {
        toast(`⚠️ Cloud AI failed: ${data.error}. Auto-falling back to Offline Engine...`, 'error');
        setProgress(30, 'Running local offline engine...');
        form.set('mode', 'offline');
        const fallbackResp = await fetch(STATE.serverUrl + '/api/extract', {
          method: 'POST', body: form,
          signal: AbortSignal.timeout(120000),
        });
        data = await fallbackResp.json();
        if (data.error) {
          toast('❌ ' + data.error, 'error');
          $('extract-progress').style.display = 'none';
          $('btn-run').disabled = false;
          return;
        }
      } else {
        toast('❌ ' + data.error, 'error');
        $('extract-progress').style.display = 'none';
        $('btn-run').disabled = false;
        return;
      }
    }

    setProgress(100, 'Complete!');
    if (task === '1') {
      STATE.task1Result = data;
      renderAll();
      navigate('results');
      switchResultsTab('courses');
    } else {
      STATE.task2Result = data;
      renderAll();
      navigate('results');
      switchResultsTab('deep');
    }
    toast(`✅ ${mode === 'online' ? 'Cloud AI' : 'Offline'} extraction complete`, 'success');

    // Update chat context
    const ctx = { task1: STATE.task1Result, task2: STATE.task2Result };
    CHAT.context = ctx;
    updateContextPanel(ctx);

  } catch (e) {
    toast('❌ ' + e.message, 'error');
  } finally {
    $('extract-progress').style.display = 'none';
    $('btn-run').disabled = false;
  }
}

function setProgress(pct, label) {
  const fill = $('prog-fill');
  const lbl  = $('prog-label');
  if (fill) fill.style.width = pct + '%';
  if (lbl)  lbl.textContent  = label;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Demo loader ─────────────────────────────────────────────────────
function loadDemo() {
  STATE.task1Result = DEMO_TASK1;
  STATE.task2Result = DEMO_TASK2;
  renderAll();
  navigate('results');
  const ctx = { task1: DEMO_TASK1, task2: DEMO_TASK2 };
  CHAT.context = ctx;
  updateContextPanel(ctx);
  toast('🎯 Demo results loaded', 'success');
}
window.loadDemo = loadDemo;

// ── Render all results ──────────────────────────────────────────────
function renderAll() {
  renderStatsBar();
  renderCourseCards();
  renderTask2();
  renderCurriculumAudit();
  renderBloom();
  renderLedger();
  renderJSON();
  renderAIReasoning();
}

// Stats bar
function renderStatsBar() {
  const d1 = STATE.task1Result;
  const d2 = STATE.task2Result;
  const totalTopics = (d2?.units||[]).reduce((a,u)=>a+(u.topics||[]).length, 0);
  const totalHours  = (d2?.units||[]).reduce((a,u)=>a+(u.hours||0), 0);
  const matrixCells = Object.values(d2?.co_po_matrix||{})
    .reduce((a,r)=>a+Object.keys(r).length, 0);
  const banner = $('stats-banner');
  if (!banner) return;
  banner.innerHTML = [
    ['Courses',      d1?.course_count ?? '—'],
    ['Topics',       totalTopics || '—'],
    ['Hours',        totalHours  || '—'],
    ['Matrix Cells', matrixCells || '—'],
  ].map(([label, val]) =>
    `<div class="stat-card"><div class="stat-val">${val}</div><div class="stat-label">${label}</div></div>`
  ).join('');
}

// Course cards (Task 1) with search filter
function renderCourseCards(filterText = '') {
  const grid = $('courses-grid');
  if (!grid) return;
  const d1 = STATE.task1Result;
  if (!d1?.courses?.length) {
    grid.innerHTML = '<div style="color:var(--text-muted);padding:2rem">No courses extracted.</div>';
    return;
  }

  const query = (filterText || '').trim().toLowerCase();
  const filtered = query
    ? d1.courses.filter(c => (c.code || '').toLowerCase().includes(query) || (c.title || '').toLowerCase().includes(query))
    : d1.courses;

  const summary = $('t1-summary');
  if (summary) {
    const countLabel = query ? `<b style="color:var(--accent-cyan)">${filtered.length}</b> of ${d1.course_count}` : `<b style="color:var(--accent-cyan)">${d1.course_count}</b>`;
    summary.innerHTML = `${countLabel} courses in <span class="mono">${esc(d1.document)}</span>`;
  }

  grid.innerHTML = '';
  if (!filtered.length) {
    grid.innerHTML = `<div style="color:var(--text-muted);padding:2rem">No courses match "${esc(filterText)}".</div>`;
    return;
  }

  filtered.forEach(c => {
    const card = document.createElement('div');
    card.className = 'course-card animate-in';
    card.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div class="course-card-code">${esc(c.code || '⊘ No Code')}</div>
        <div class="course-card-page">📄 p. ${c.page}</div>
      </div>
      <div class="course-card-title">${esc(c.title)}</div>
      <div style="margin-top:10px;display:flex;justify-content:flex-end">
        <span style="font-size:0.75rem;color:var(--accent-cyan);font-weight:600">Deep Extract ⚡</span>
      </div>`;
    card.addEventListener('click', () => {
      loadTask2ForCourse(c);
    });
    grid.appendChild(card);
  });
}
window.renderCourseCards = renderCourseCards;

function renderTask2Error(course, message) {
  const codeOrTitle = course.code || course.title || '';
  const metaCard = $('meta-card');
  if (metaCard) {
    metaCard.innerHTML = `
      <div style="padding:1.5rem;text-align:center">
        <div style="font-size:1.75rem;margin-bottom:0.5rem">⚠️</div>
        <div style="font-weight:700;color:var(--accent-red);font-size:1.05rem;margin-bottom:0.25rem">Extraction Issue</div>
        <div class="course-meta-title" style="font-size:0.95rem;color:var(--text-main);margin-bottom:0.25rem">${esc(course.title || codeOrTitle)}</div>
        <div class="course-meta-code" style="font-size:0.8rem;margin-bottom:0.75rem">${esc(course.code || '')}</div>
        <div style="font-size:0.78rem;color:var(--text-muted);margin:0 auto 1.25rem;max-width:340px;line-height:1.4">${esc(message || 'The server could not extract details for this course.')}</div>
        <div style="display:flex;gap:8px;justify-content:center">
          <button class="btn btn-sm btn-primary" onclick="loadTask2ForCourse(${JSON.stringify(course).replace(/"/g, '&quot;')})">⚡ Try Again</button>
          <button class="btn btn-sm btn-secondary" onclick="switchResultsTab('courses')">← Back to Courses</button>
        </div>
      </div>
    `;
  }
  if ($('t2-units')) $('t2-units').innerHTML = `<div class="empty-pane">No units available. Click "Try Again" to retry.</div>`;
  if ($('t2-outcomes')) $('t2-outcomes').innerHTML = '<div class="empty-pane">No course outcomes extracted.</div>';
  if ($('t2-po')) $('t2-po').innerHTML = '<div class="empty-pane">No programme outcomes extracted.</div>';
  if ($('t2-matrix')) $('t2-matrix').innerHTML = '<div class="empty-pane">No CO-PO matrix available.</div>';
  if ($('t2-books')) $('t2-books').innerHTML = '<div class="empty-pane">No books extracted.</div>';
}

async function loadTask2ForCourse(course) {
  const codeOrTitle = course.code || course.title || '';
  if ($('course-input')) $('course-input').value = codeOrTitle;
  if ($('task-select')) $('task-select').value = '2';

  // 1. In-memory Course Cache: Instant 0ms return if already extracted in this session
  STATE.courseCache = STATE.courseCache || {};
  const cacheKey = (course.code || course.title || '').trim().toUpperCase();
  if (cacheKey && STATE.courseCache[cacheKey]) {
    STATE.task2Result = STATE.courseCache[cacheKey];
    renderTask2();
    renderCurriculumAudit();
    switchResultsTab('deep');
    toast(`⚡ Instant loaded ${codeOrTitle}`, 'success');
    return;
  }

  // 2. Abort any previous pending task2 request so multiple clicks don't collide or hang
  if (STATE.activeTask2AbortController) {
    try { STATE.activeTask2AbortController.abort(); } catch(_) {}
    STATE.activeTask2AbortController = null;
  }
  const abortCtrl = new AbortController();
  STATE.activeTask2AbortController = abortCtrl;

  if (STATE.pdfFile && STATE.serverOnline) {
    switchResultsTab('deep');
    const metaCard = $('meta-card');
    if (metaCard) {
      metaCard.innerHTML = `
        <div style="padding:2rem;text-align:center">
          <div style="font-size:2rem;margin-bottom:0.75rem">⚡</div>
          <div style="font-weight:700;color:var(--accent-cyan);font-size:1.05rem;margin-bottom:0.25rem">Deep Extracting ${esc(codeOrTitle)}</div>
          <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:1rem">Targeting course syllabus — rapid extraction active</div>
          <div class="pipeline-progress-bar" style="max-width:260px;margin:0 auto"><div class="pipeline-progress-fill" style="width:75%"></div></div>
        </div>
      `;
    }
    if ($('t2-units')) $('t2-units').innerHTML = '<div class="empty-pane">Extracting units &amp; topics...</div>';
    if ($('t2-outcomes')) $('t2-outcomes').innerHTML = '<div class="empty-pane">Extracting Course Outcomes...</div>';
    if ($('t2-po')) $('t2-po').innerHTML = '<div class="empty-pane">Extracting Programme Outcomes...</div>';
    if ($('t2-matrix')) $('t2-matrix').innerHTML = '<div class="empty-pane">Stitching CO-PO matrix...</div>';
    if ($('t2-books')) $('t2-books').innerHTML = '<div class="empty-pane">Parsing books &amp; references...</div>';

    const timeoutId = setTimeout(() => {
      try { abortCtrl.abort(); } catch(_) {}
    }, 25000);

    try {
      const form = new FormData();
      form.append('pdf', STATE.pdfFile);
      form.append('course', codeOrTitle);

      // Pass target course identity AND complete course catalog from Task 1
      const hintsPayload = {
        target: { code: course.code, title: course.title, page: course.page },
        courses: STATE.task1Result?.courses || []
      };
      form.append('hints', JSON.stringify(hintsPayload));

      form.append('mode', STATE.extractionMode || 'offline');
      if (STATE.extractionMode === 'online') {
        form.append('provider', SYLEX_CLOUD_PROVIDER);
        form.append('model', getCloudModel());
      }
      const resp = await fetch(STATE.serverUrl + '/api/extract', {
        method: 'POST', body: form,
        signal: abortCtrl.signal,
      });
      clearTimeout(timeoutId);
      const data = await resp.json();
      if (data.error) {
        toast('❌ ' + data.error, 'error');
        renderTask2Error(course, data.error);
        return;
      }
      STATE.task2Result = data;
      // Cache both by code and title for instant subsequent clicks
      if (cacheKey) STATE.courseCache[cacheKey] = data;
      if (course.code) STATE.courseCache[course.code.trim().toUpperCase()] = data;
      if (course.title) STATE.courseCache[course.title.trim().toUpperCase()] = data;

      renderAll();
      switchResultsTab('deep');
      toast(`✅ Extracted ${codeOrTitle}`, 'success');
      const ctx = { task1: STATE.task1Result, task2: STATE.task2Result };
      CHAT.context = ctx;
      updateContextPanel(ctx);
    } catch (e) {
      clearTimeout(timeoutId);
      if (e.name === 'AbortError') {
        if (STATE.activeTask2AbortController === abortCtrl) {
          toast('⏱️ Extraction timed out for ' + codeOrTitle, 'error');
          renderTask2Error(course, 'Request timed out after 25s. You can click Try Again or switch to Offline mode.');
        }
      } else {
        toast('❌ Extraction error: ' + e.message, 'error');
        renderTask2Error(course, e.message);
      }
    } finally {
      clearTimeout(timeoutId);
      if (STATE.activeTask2AbortController === abortCtrl) {
        STATE.activeTask2AbortController = null;
      }
    }
  } else if (STATE.task2Result && (STATE.task2Result.course?.code === course.code || STATE.task2Result.course?.title === course.title)) {
    renderTask2();
    switchResultsTab('deep');
  } else {
    switchResultsTab('deep');
    $('meta-card').innerHTML = `
      <div style="padding:1.5rem;text-align:center">
        <div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px">Selected Course</div>
        <div class="course-meta-title">${esc(course.title)}</div>
        <div class="course-meta-code">${esc(course.code || '⊘ No Code')}</div>
        <div style="margin-top:1.25rem">
          <button class="btn btn-sm btn-primary" onclick="runExtraction()">⚡ Run Deep Extraction</button>
        </div>
      </div>
    `;
    $('t2-units').innerHTML    = `<div class="empty-pane">Upload a syllabus PDF or connect to server to extract deep details for <b>${esc(codeOrTitle)}</b>.</div>`;
    $('t2-outcomes').innerHTML = '<div class="empty-pane">Awaiting extraction</div>';
    $('t2-po').innerHTML       = '<div class="empty-pane">Awaiting extraction</div>';
    $('t2-matrix').innerHTML   = '<div class="empty-pane">Awaiting extraction</div>';
    $('t2-books').innerHTML    = '<div class="empty-pane">Awaiting extraction</div>';
  }
}

// Task 2 deep view
function renderTask2() {
  const d2 = STATE.task2Result;
  if (!d2) return;

  const metaCard = $('meta-card');
  if (!d2.course) {
    const reason = (d2.not_extracted && d2.not_extracted.length)
      ? (typeof d2.not_extracted[0] === 'object' ? d2.not_extracted[0].reason : d2.not_extracted[0])
      : 'Course not found in document';
    if (metaCard) {
      metaCard.innerHTML = `
        <div style="padding:1.5rem;text-align:center">
          <div style="font-size:2.2rem;margin-bottom:0.5rem">⚠️</div>
          <div style="font-weight:700;color:var(--accent-amber);font-size:1.1rem;margin-bottom:0.5rem">Course Not Found</div>
          <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:1rem">${esc(reason)}</div>
          <div style="font-size:0.8rem;color:var(--text-muted)">Check the course code or switch to the <b>Courses</b> tab to see all extracted courses.</div>
        </div>
      `;
    }
    if ($('t2-units')) $('t2-units').innerHTML = `<div class="empty-pane">⚠️ ${esc(reason)}</div>`;
    if ($('t2-outcomes')) $('t2-outcomes').innerHTML = '<div class="empty-pane">No data</div>';
    if ($('t2-po')) $('t2-po').innerHTML = '<div class="empty-pane">No data</div>';
    if ($('t2-matrix')) $('t2-matrix').innerHTML = '<div class="empty-pane">No data</div>';
    if ($('t2-books')) $('t2-books').innerHTML = '<div class="empty-pane">No data</div>';
    return;
  }

  // Meta card
  if (metaCard) {
    const c = d2.course;
    metaCard.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.08em">Course</span>
        <button class="btn btn-xs btn-outline" onclick="switchResultsTab('courses')" style="padding:2px 8px;font-size:0.75rem;cursor:pointer">← Catalog</button>
      </div>
      <div class="course-meta-title">${esc(c.title)}</div>
      <div class="course-meta-code">${esc(c.code)}</div>
      <div class="ltpc-row">
        <div class="ltpc-cell"><div class="ltpc-val">${c.lecture ?? '—'}</div><div class="ltpc-key">L</div></div>
        <div class="ltpc-cell"><div class="ltpc-val">${c.tutorial ?? '—'}</div><div class="ltpc-key">T</div></div>
        <div class="ltpc-cell"><div class="ltpc-val">${c.practical ?? '—'}</div><div class="ltpc-key">P</div></div>
        <div class="ltpc-cell"><div class="ltpc-val">${c.credits ?? '—'}</div><div class="ltpc-key">C</div></div>
      </div>
      <div class="meta-row"><span class="meta-key">Category</span><span class="meta-val"><span class="category-badge">${esc(c.category||'—')}</span></span></div>
      <div class="meta-row"><span class="meta-key">Pages</span><span class="meta-val pages-list">pp. ${(c.pages||[]).join(', ')}</span></div>
      <div class="meta-row"><span class="meta-key">Units</span><span class="meta-val">${(d2.units||[]).length}</span></div>
      <div class="meta-row"><span class="meta-key">COs</span><span class="meta-val">${(d2.course_outcomes||[]).length}</span></div>
      <div class="meta-row"><span class="meta-key">Books</span><span class="meta-val">${(d2.books||[]).length}</span></div>
    `;
  }

  // Units accordion
  const unitsEl = $('t2-units');
  if (unitsEl) {
    unitsEl.innerHTML = '';
    (d2.units||[]).forEach(unit => {
      const acc    = document.createElement('div');
      acc.className = 'unit-accordion';
      const header = document.createElement('div');
      header.className = 'unit-accordion-header';
      header.innerHTML = `
        <div class="unit-number">${unit.number}</div>
        <div class="unit-title">${esc(unit.title)}</div>
        <div class="unit-hours">${unit.hours || '—'} hrs</div>
        <div class="unit-chevron">▼</div>`;
      const body = document.createElement('div');
      body.className = 'unit-accordion-body';
      body.innerHTML = `<div class="unit-text-block">${esc(unit.text || '')}</div>`;
      const grid = document.createElement('div');
      grid.className = 'topics-grid';
      (unit.topics||[]).forEach(t => {
        const row = document.createElement('div');
        row.className = 'topic-row';
        row.innerHTML = `
          <span class="topic-id">${esc(t.id)}</span>
          <span class="topic-text">${esc(t.text)}</span>
          <span class="bloom-badge bloom-${t.bloom}">
            <span class="bs-dot"></span>${t.bloom}
            <span class="bloom-source-tag">${t.bloom_source==='printed'?'🖨️':'🔍'}</span>
          </span>`;
        grid.appendChild(row);
      });
      body.appendChild(grid);
      header.addEventListener('click', () => acc.classList.toggle('open'));
      acc.appendChild(header);
      acc.appendChild(body);
      unitsEl.appendChild(acc);
    });
  }

  // Course Outcomes
  const coEl = $('t2-outcomes');
  if (coEl) {
    coEl.innerHTML = '';
    const cos = d2.course_outcomes || [];
    if (!cos.length) { coEl.innerHTML = '<div class="empty-pane">No COs extracted</div>'; }
    cos.forEach(co => {
      const item = document.createElement('div');
      item.className = 'co-item';
      item.innerHTML = `
        <div class="co-id">${esc(co.id)}</div>
        <div class="co-text">${esc(co.text)}</div>
        <div class="co-bloom"><span class="bloom-badge bloom-${co.bloom}"><span class="bs-dot"></span>${co.bloom} <small style="opacity:0.6">${co.bloom_source==='printed'?'🖨️':'🔍'}</small></span></div>`;
      coEl.appendChild(item);
    });
  }

  // Programme Outcomes
  const poEl = $('t2-po');
  if (poEl) {
    poEl.innerHTML = '';
    const pos = d2.programme_outcomes || [];
    if (!pos.length) { poEl.innerHTML = '<div class="empty-pane">No POs extracted (or not in document)</div>'; }
    pos.forEach(po => {
      const item = document.createElement('div');
      item.className = 'po-item';
      item.innerHTML = `<div class="po-id">${esc(po.id)}</div><div class="po-text">${esc(po.text)}</div>`;
      poEl.appendChild(item);
    });
  }

  // CO-PO Matrix
  const matrixEl = $('t2-matrix');
  if (matrixEl) {
    matrixEl.innerHTML = '';
    const matrix = d2.co_po_matrix || {};
    const cos = Object.keys(matrix);
    if (!cos.length) {
      matrixEl.innerHTML = '<div class="empty-pane">No CO-PO matrix extracted</div>';
    } else {
      const posSet = new Set();
      cos.forEach(co => Object.keys(matrix[co]).forEach(p => posSet.add(p)));
      const pos = Array.from(posSet).sort((a,b) => {
        const n = x => parseInt(x.replace(/\D/g,'')) || 0;
        return n(a) - n(b);
      });
      const wrap = document.createElement('div');
      wrap.style.overflowX = 'auto';
      const table = document.createElement('table');
      table.className = 'matrix-table';
      const thead = document.createElement('thead');
      const hrow  = document.createElement('tr');
      hrow.innerHTML = `<th>CO \\ PO</th>` + pos.map(p => `<th>${esc(p)}</th>`).join('');
      thead.appendChild(hrow);
      table.appendChild(thead);
      const tbody = document.createElement('tbody');
      cos.forEach(co => {
        const row = document.createElement('tr');
        row.innerHTML = `<td><strong>${esc(co)}</strong></td>` +
          pos.map(p => {
            const val = matrix[co][p];
            return val
              ? `<td><span class="matrix-cell-${val}" title="${co}↔${p}: ${val}">${val}</span></td>`
              : `<td><span class="matrix-cell-empty">·</span></td>`;
          }).join('');
        tbody.appendChild(row);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      matrixEl.appendChild(wrap);
      const legend = document.createElement('div');
      legend.className = 'matrix-legend';
      legend.innerHTML = `
        <div class="legend-item"><div class="legend-dot" style="background:var(--accent-green)"></div>S — Strong</div>
        <div class="legend-item"><div class="legend-dot" style="background:var(--accent-amber)"></div>M — Moderate</div>
        <div class="legend-item"><div class="legend-dot" style="background:var(--text-muted)"></div>L — Low</div>`;
      matrixEl.appendChild(legend);
    }
  }

  // Books
  const booksEl = $('t2-books');
  if (booksEl) {
    booksEl.innerHTML = '';
    const books = d2.books || [];
    if (!books.length) { booksEl.innerHTML = '<div class="empty-pane">No books extracted</div>'; }
    else {
      const wrap = document.createElement('div');
      wrap.style.overflowX = 'auto';
      const table = document.createElement('table');
      table.className = 'books-table';
      table.innerHTML = `<thead><tr><th>#</th><th>Kind</th><th>Title / Author</th><th>Publisher</th><th>Ed.</th><th>Year</th></tr></thead>`;
      const tbody = document.createElement('tbody');
      books.forEach((b,i) => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td class="mono text-muted">${i+1}</td>
          <td><span class="book-kind-tag book-kind-${b.kind}">${esc(b.kind||'—')}</span></td>
          <td><div class="book-title">${esc(b.title||'—')}</div><div class="book-author">${esc(b.author||'—')}</div></td>
          <td>${esc(b.publisher||'—')}</td>
          <td class="mono text-sm">${esc(b.edition||'—')}</td>
          <td class="mono text-sm">${b.year||'—'}</td>`;
        tbody.appendChild(row);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      booksEl.appendChild(wrap);
    }
  }
}

// Bloom chart
function renderBloom() {
  const d2  = STATE.task2Result;
  const wrap = $('bloom-bars');
  if (!wrap) return;
  wrap.innerHTML = '';
  if (!d2) return;
  const all = [];
  (d2.units||[]).forEach(u => (u.topics||[]).forEach(t => all.push(t.bloom)));
  (d2.course_outcomes||[]).forEach(co => all.push(co.bloom));
  const levels = ['remember','understand','apply','analyse','evaluate','create'];
  const colors = {
    remember:'var(--bloom-remember)', understand:'var(--bloom-understand)',
    apply:'var(--bloom-apply)', analyse:'var(--bloom-analyse)',
    evaluate:'var(--bloom-evaluate)', create:'var(--bloom-create)'
  };
  const counts = {};
  levels.forEach(l => counts[l] = 0);
  all.forEach(b => { if (counts[b] !== undefined) counts[b]++; });
  const max = Math.max(1, ...Object.values(counts));
  levels.forEach(l => {
    const row = document.createElement('div');
    row.className = 'bloom-bar-row';
    row.innerHTML = `
      <span class="bloom-bar-label" style="color:${colors[l]}">${l}</span>
      <div class="bloom-bar-track"><div class="bloom-bar-fill" style="background:${colors[l]};width:0%"></div></div>
      <span class="bloom-bar-count">${counts[l]}</span>`;
    wrap.appendChild(row);
    setTimeout(() => {
      row.querySelector('.bloom-bar-fill').style.width = (counts[l]/max*100) + '%';
    }, 80);
  });
}

// Ledger
function renderLedger() {
  const d2  = STATE.task2Result;
  const el  = $('ledger-list');
  if (!el) return;
  el.innerHTML = '';
  const ne = d2?.not_extracted || [];
  if (!ne.length) {
    el.innerHTML = `<div class="ledger-item-ui ok">
      <span>✅</span>
      <span>All fields resolved — <code>not_extracted</code> ledger is empty. Zero honest failures.</span>
    </div>`;
    return;
  }
  ne.forEach(item => {
    const div = document.createElement('div');
    div.className = 'ledger-item-ui';
    let text = '';
    if (typeof item === 'object' && item !== null) {
      text = item.field ? `<strong>${esc(item.field)}:</strong> ${esc(item.reason || '')}` : esc(JSON.stringify(item));
    } else {
      text = esc(String(item));
    }
    div.innerHTML = `<span>⚠️</span><span>${text}</span>`;
    el.appendChild(div);
  });
}

// JSON viewers
function renderJSON() {
  const t1 = $('json-t1-pre');
  const t2 = $('json-t2-pre');
  if (t1 && STATE.task1Result)
    t1.innerHTML = syntaxHL(JSON.stringify(STATE.task1Result, null, 2));
  if (t2 && STATE.task2Result)
    t2.innerHTML = syntaxHL(JSON.stringify(STATE.task2Result, null, 2));
}

// ── JSON syntax highlighter ─────────────────────────────────────────
function syntaxHL(json) {
  return json
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(
      /("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      m => {
        let cls = 'json-num';
        if (/^"/.test(m))      cls = /:$/.test(m) ? 'json-key' : 'json-str';
        else if (/true|false/.test(m)) cls = 'json-bool';
        else if (/null/.test(m))       cls = 'json-null';
        return `<span class="${cls}">${m}</span>`;
      }
    );
}

// ── Tab switching ────────────────────────────────────────────────────
function switchResultsTab(tab) {
  document.querySelectorAll('.results-tab:not(.t2-tab)').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector(`[data-tab="${tab}"]`)?.classList.add('active');
  $(`tab-${tab}`)?.classList.add('active');
  if (tab === 'audit') {
    renderCurriculumAudit();
  }
}

function switchT2Tab(tab) {
  document.querySelectorAll('.t2-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.t2-pane').forEach(p => { p.classList.remove('active'); p.style.display='none'; });
  document.querySelector(`[data-t2="${tab}"]`)?.classList.add('active');
  const pane = $(`t2-${tab}`);
  if (pane) { pane.classList.add('active'); pane.style.display='block'; }
}

// ── Copy / download ──────────────────────────────────────────────────
function copyJSON(elId) {
  const el = $(elId);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent || '').then(() => toast('📋 Copied', 'success'));
}
window.copyJSON = copyJSON;

function downloadResult(task) {
  const data = task === 1 ? STATE.task1Result : STATE.task2Result;
  if (!data) { toast('No data to download', 'error'); return; }
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const a    = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: `task${task}_output.json`,
  });
  a.click();
  toast(`⬇ task${task}_output.json downloaded`, 'success');
}
window.downloadResult = downloadResult;

// ── AI Reasoning & Thinking Trace ─────────────────────────────────────
function renderAIReasoning() {
  const card = $('ai-thinking-card');
  const content = $('ai-thinking-content');
  const badge = $('ai-latency-badge');
  if (!card || !content) return;

  const reasoning = STATE.task2Result?._reasoning_summary ||
                    STATE.task1Result?._reasoning_summary ||
                    STATE.task2Result?._debug?.reasoning ||
                    STATE.task1Result?._debug?.reasoning || '';

  if (reasoning && reasoning.trim()) {
    card.style.display = 'block';
    content.textContent = reasoning;
    if (badge) badge.textContent = `NVIDIA Cloud AI · Active Reasoning (${reasoning.length} chars)`;
  } else {
    card.style.display = 'none';
  }
}
window.renderAIReasoning = renderAIReasoning;

// ── Export Hub (Markdown, Matrix CSV, Courses CSV, Print) ──────────────
function copyMarkdownSyllabus() {
  const d2 = STATE.task2Result;
  if (!d2 || !d2.course) {
    toast('No deep course extraction available to export', 'error');
    return;
  }
  const c = d2.course;
  let md = `# ${c.code || 'COURSE'}: ${c.title || 'Untitled'}\n\n`;
  md += `**Category:** ${c.category || 'N/A'} | **Credits:** ${c.credits ?? '—'} (L: ${c.lecture ?? 0}, T: ${c.tutorial ?? 0}, P: ${c.practical ?? 0}) | **Pages:** ${(c.pages || []).join(', ')}\n\n`;
  md += `---\n\n`;

  // Units
  md += `## 📚 Units & Topics\n\n`;
  (d2.units || []).forEach(u => {
    md += `### Unit ${u.number}: ${u.title || 'Untitled'} (${u.hours || 0} Hours)\n`;
    if (u.text && u.text.trim()) {
      md += `*${u.text.trim()}*\n\n`;
    }
    (u.topics || []).forEach(t => {
      md += `- **${t.id}:** ${t.text} \`[Bloom: ${t.bloom || 'understand'} (${t.bloom_source || 'inferred'})]\`\n`;
    });
    md += `\n`;
  });

  // Course Outcomes
  if (d2.course_outcomes && d2.course_outcomes.length) {
    md += `---\n\n## 🎯 Course Outcomes (COs)\n\n`;
    d2.course_outcomes.forEach(co => {
      md += `- **${co.id}:** ${co.text} \`[Bloom: ${co.bloom || 'understand'} (${co.bloom_source || 'inferred'})]\`\n`;
    });
    md += `\n`;
  }

  // Programme Outcomes
  if (d2.programme_outcomes && d2.programme_outcomes.length) {
    md += `---\n\n## 🎓 Programme Outcomes (POs)\n\n`;
    d2.programme_outcomes.forEach(po => {
      md += `- **${po.id}:** ${po.text}\n`;
    });
    md += `\n`;
  }

  // CO-PO Matrix
  const matrix = d2.co_po_matrix || {};
  const cos = Object.keys(matrix);
  if (cos.length) {
    const posSet = new Set();
    cos.forEach(co => Object.keys(matrix[co]).forEach(p => posSet.add(p)));
    const pos = Array.from(posSet).sort((a,b) => {
      const n = x => parseInt(x.replace(/\D/g,'')) || 0;
      return n(a) - n(b);
    });
    md += `---\n\n## 📊 CO-PO Articulation Matrix\n\n`;
    md += `| CO \\ PO | ` + pos.join(' | ') + ` |\n`;
    md += `| :--- | ` + pos.map(() => ':---:').join(' | ') + ` |\n`;
    cos.forEach(co => {
      md += `| **${co}** | ` + pos.map(p => matrix[co][p] || '-').join(' | ') + ` |\n`;
    });
    md += `\n`;
  }

  // Books
  if (d2.books && d2.books.length) {
    md += `---\n\n## 📖 Books & References\n\n`;
    d2.books.forEach((b, idx) => {
      const kind = b.kind === 'text' ? 'Textbook' : 'Reference';
      md += `${idx + 1}. **[${kind}]** *${b.author || 'Author Unknown'}*, **${b.title || 'Title Unknown'}**, ${b.publisher || 'Publisher Unknown'}${b.edition ? ', ' + b.edition : ''}${b.year ? ' (' + b.year + ')' : ''}.\n`;
    });
    md += `\n`;
  }

  navigator.clipboard.writeText(md).then(() => {
    toast(`📋 Markdown syllabus for ${c.code || c.title} copied!`, 'success');
  });
}
window.copyMarkdownSyllabus = copyMarkdownSyllabus;

function exportMatrixCSV() {
  const d2 = STATE.task2Result;
  const matrix = d2?.co_po_matrix || {};
  const cos = Object.keys(matrix);
  if (!cos.length) {
    toast('No CO-PO matrix available to export', 'error');
    return;
  }
  const posSet = new Set();
  cos.forEach(co => Object.keys(matrix[co]).forEach(p => posSet.add(p)));
  const pos = Array.from(posSet).sort((a,b) => (parseInt(a.replace(/\D/g,''))||0) - (parseInt(b.replace(/\D/g,''))||0));

  let csv = 'CO,' + pos.join(',') + '\n';
  cos.forEach(co => {
    const row = [co, ...pos.map(p => matrix[co][p] || '')];
    csv += row.map(v => `"${v}"`).join(',') + '\n';
  });

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: `${d2.course?.code || 'CO_PO'}_Articulation_Matrix.csv`
  });
  a.click();
  toast('📊 CO-PO Matrix CSV downloaded!', 'success');
}
window.exportMatrixCSV = exportMatrixCSV;

function exportCoursesCSV() {
  const d1 = STATE.task1Result;
  const courses = d1?.courses || [];
  if (!courses.length) {
    toast('No courses available to export', 'error');
    return;
  }
  let csv = 'Code,Title,Page\n';
  courses.forEach(c => {
    csv += `"${(c.code||'').replace(/"/g,'""')}","${(c.title||'').replace(/"/g,'""')}",${c.page || 1}\n`;
  });
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: `${(d1.document || 'Courses').replace(/\.[^/.]+$/, '')}_Courses_List.csv`
  });
  a.click();
  toast('📊 Courses list CSV downloaded!', 'success');
}
window.exportCoursesCSV = exportCoursesCSV;

function printSyllabus() {
  if (!STATE.task2Result?.course) {
    toast('Please select a course in Deep View first', 'error');
    return;
  }
  switchResultsTab('deep');
  setTimeout(() => window.print(), 200);
}
window.printSyllabus = printSyllabus;

// Hints template download
function downloadHintsTemplate() {
  const tmpl = JSON.stringify({
    courses: [{ code: "CS23301", title: "DATA STRUCTURES", page: 12 }]
  }, null, 2);
  const a = Object.assign(document.createElement('a'), {
    href: 'data:application/json,' + encodeURIComponent(tmpl),
    download: 'hints.json',
  });
  a.click();
}
window.downloadHintsTemplate = downloadHintsTemplate;

// Advanced toggle
function toggleAdvanced() {
  const panel  = $('adv-panel');
  const toggle = $('adv-toggle');
  if (!panel) return;
  const open = panel.style.display === 'block';
  panel.style.display = open ? 'none' : 'block';
  if (toggle) toggle.innerHTML = `⚙ Advanced options ${open ? '▼' : '▲'}`;
}
window.toggleAdvanced = toggleAdvanced;

// ── Curriculum Audit & OBE Accreditation ─────────────────────────────
async function renderCurriculumAudit() {
  const d2 = STATE.task2Result;
  const courseTitleEl = $('audit-course-title');
  if (!courseTitleEl) return;

  if (!d2 || !d2.course) {
    courseTitleEl.textContent = 'No course selected for audit';
    if ($('audit-health-score')) $('audit-health-score').textContent = '—';
    if ($('audit-hour-val')) $('audit-hour-val').innerHTML = '—';
    if ($('audit-bloom-val')) $('audit-bloom-val').innerHTML = '—';
    if ($('audit-matrix-val')) $('audit-matrix-val').innerHTML = '—';
    if ($('audit-heatmap-table-wrap')) {
      $('audit-heatmap-table-wrap').innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-muted)">Please extract or select a course to view accreditation audit.</div>';
    }
    return;
  }

  const c = d2.course || {};
  courseTitleEl.textContent = `${c.code || 'NO-CODE'} — ${c.title || 'Course'}`;

  // Try fetching audit from server if online, else calculate locally
  let audit = null;
  if (STATE.serverOnline) {
    try {
      const resp = await fetch(STATE.serverUrl + '/api/curriculum-audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(d2),
        signal: AbortSignal.timeout(4000)
      });
      if (resp.ok) {
        audit = await resp.json();
      }
    } catch (_) {}
  }

  if (!audit || audit.status !== 'ok') {
    // Client-side computation fallback
    const units = d2.units || [];
    const cos = d2.course_outcomes || [];
    const pos = d2.programme_outcomes || [];
    const matrix = d2.co_po_matrix || {};
    const books = d2.books || [];

    const totalHours = units.reduce((a, u) => a + (u.hours || 0), 0);
    const lec = c.lecture || 0;
    const tut = c.tutorial || 0;
    const prac = c.practical || 0;
    const credits = c.credits;
    const expected = (lec > 0) ? (lec * 15) : null;

    let hourStatus = 'DOCUMENTED';
    let hourMsg = `Total contact hours allocated: ${totalHours} hrs across ${units.length} units.`;
    if (totalHours > 0 && expected) {
      if (Math.abs(totalHours - expected) <= 5) {
        hourStatus = 'VERIFIED_ACCURATE';
        hourMsg = `Unit contact hours (${totalHours} hrs) perfectly align with ${credits} credits (${lec}L x 15 weeks).`;
      } else {
        hourStatus = 'DISCREPANCY_FLAGGED';
        hourMsg = `Unit contact hours (${totalHours} hrs) differ from expected ${expected} hrs (${lec}L x 15 weeks).`;
      }
    }

    let lots = 0, hots = 0;
    units.forEach(u => (u.topics || []).forEach(t => {
      const b = (t.bloom || 'understand').toLowerCase();
      if (['remember', 'understand'].includes(b)) lots++;
      else hots++;
    }));
    cos.forEach(co => {
      const b = (co.bloom || 'understand').toLowerCase();
      if (['remember', 'understand'].includes(b)) lots++;
      else hots++;
    });
    const totalBlooms = Math.max(1, lots + hots);
    const hotsPct = Math.round((hots / totalBlooms) * 100);

    const allPos = pos.length ? pos.map(p => p.id) : Array.from({length: 12}, (_, i) => `PO${i+1}`);
    const mappedPos = new Set();
    let mappedCells = 0;
    Object.values(matrix).forEach(row => {
      if (row && typeof row === 'object') {
        Object.entries(row).forEach(([p, v]) => {
          if (v && String(v).trim()) {
            mappedPos.add(p);
            mappedCells++;
          }
        });
      }
    });
    const totalPossible = Math.max(1, (cos.length || 1) * allPos.length);
    const densityPct = Math.round((mappedCells / totalPossible) * 100);
    const unmappedPos = allPos.filter(p => !mappedPos.has(p));

    let score = 100;
    if (!units.length) score -= 30;
    if (!cos.length) score -= 20;
    if (!Object.keys(matrix).length) score -= 20;
    if (!books.length) score -= 15;
    if (hotsPct < 40) score -= 10;
    score = Math.max(0, Math.min(100, score));

    audit = {
      curriculum_score: score,
      hour_integrity: { status: hourStatus, message: hourMsg, total_unit_hours: totalHours, credits, l_t_p: `${lec}-${tut}-${prac}` },
      bloom_analytics: {
        lots_count: lots, hots_count: hots, hots_percentage: hotsPct,
        nba_status: hotsPct >= 50 ? 'COMPLIANT_HIGH_RIGOR' : 'LOTS_HEAVY_REVIEW_NEEDED',
        nba_message: hotsPct >= 50 ? `Higher-Order Cognitive Rigor is ${hotsPct}% (>=50% Washington Accord benchmark).` : `Lower-Order Thinking dominates. Elevate more topics to Apply/Analyse.`
      },
      co_po_coverage: {
        total_mapped_cells: mappedCells,
        matrix_density_pct: densityPct,
        mapped_pos: Array.from(mappedPos),
        unmapped_pos: unmappedPos
      }
    };
  }

  // Populate UI
  const score = audit.curriculum_score || 0;
  const scoreEl = $('audit-health-score');
  if (scoreEl) {
    scoreEl.textContent = `${score}/100`;
    scoreEl.style.color = score >= 85 ? 'var(--accent-green)' : (score >= 60 ? 'var(--accent-amber)' : 'var(--accent-red)');
  }

  // Contact Hours
  const hi = audit.hour_integrity || {};
  if ($('audit-hour-val')) $('audit-hour-val').innerHTML = `${hi.total_unit_hours || 0} <span style="font-size:1rem;font-weight:500;color:var(--text-secondary)">hrs (${hi.l_t_p || '—'} LTP)</span>`;
  if ($('audit-hour-msg')) $('audit-hour-msg').textContent = hi.message || 'Hour analysis complete';
  const hourPill = $('audit-hour-pill');
  if (hourPill) {
    if (hi.status === 'VERIFIED_ACCURATE') {
      hourPill.className = 'audit-score-pill pill-green';
      hourPill.textContent = 'Accurate';
    } else if (hi.status === 'DISCREPANCY_FLAGGED') {
      hourPill.className = 'audit-score-pill pill-amber';
      hourPill.textContent = 'Discrepancy';
    } else {
      hourPill.className = 'audit-score-pill pill-blue';
      hourPill.textContent = 'Documented';
    }
  }

  // Bloom HOTS
  const ba = audit.bloom_analytics || {};
  const hotsPct = ba.hots_percentage || 0;
  if ($('audit-bloom-val')) $('audit-bloom-val').innerHTML = `${hotsPct}% <span style="font-size:1rem;font-weight:500;color:var(--text-secondary)">HOTS</span>`;
  if ($('audit-bloom-msg')) $('audit-bloom-msg').textContent = ba.nba_message || '';
  const bloomPill = $('audit-bloom-pill');
  if (bloomPill) {
    if (ba.nba_status === 'COMPLIANT_HIGH_RIGOR') {
      bloomPill.className = 'audit-score-pill pill-green';
      bloomPill.textContent = 'Compliant';
    } else {
      bloomPill.className = 'audit-score-pill pill-amber';
      bloomPill.textContent = 'Review';
    }
  }
  const lotsW = Math.max(5, Math.min(95, 100 - hotsPct));
  const hotsW = Math.max(5, Math.min(95, hotsPct));
  if ($('audit-rigor-lots')) $('audit-rigor-lots').style.width = lotsW + '%';
  if ($('audit-rigor-hots')) $('audit-rigor-hots').style.width = hotsW + '%';
  if ($('audit-lots-label')) $('audit-lots-label').textContent = `LOTS (K1–K2): ${ba.lots_count || 0}`;
  if ($('audit-hots-label')) $('audit-hots-label').textContent = `HOTS (K3–K6): ${ba.hots_count || 0}`;

  // Matrix Density
  const mc = audit.co_po_coverage || {};
  if ($('audit-matrix-val')) $('audit-matrix-val').innerHTML = `${mc.matrix_density_pct || 0}% <span style="font-size:1rem;font-weight:500;color:var(--text-secondary)">(${mc.total_mapped_cells || 0} cells)</span>`;
  if ($('audit-matrix-msg')) $('audit-matrix-msg').textContent = `${(mc.mapped_pos || []).length} Programme Outcomes targeted by Course Outcomes.`;
  const matPill = $('audit-matrix-pill');
  if (matPill) {
    matPill.className = (mc.matrix_density_pct >= 25) ? 'audit-score-pill pill-green' : 'audit-score-pill pill-amber';
    matPill.textContent = (mc.matrix_density_pct >= 25) ? 'Balanced' : 'Low Density';
  }

  // Unmapped PO Alert
  const unmappedEl = $('unmapped-pos-alert');
  if (unmappedEl) {
    if (mc.unmapped_pos && mc.unmapped_pos.length > 0) {
      unmappedEl.style.display = 'block';
      unmappedEl.textContent = `⚠️ Unaddressed POs: ${mc.unmapped_pos.join(', ')}`;
    } else {
      unmappedEl.style.display = 'none';
    }
  }

  // Render Interactive Heatmap Table
  renderHeatmapTable(d2);

  // Quality Checklist Update
  const chkHours = $('chk-hours');
  if (chkHours) {
    chkHours.className = (hi.status === 'DISCREPANCY_FLAGGED') ? 'checklist-item warn' : 'checklist-item pass';
    chkHours.querySelector('.check-icon').textContent = (hi.status === 'DISCREPANCY_FLAGGED') ? '⚠' : '✓';
  }
  const chkBloom = $('chk-bloom');
  if (chkBloom) {
    chkBloom.className = (ba.nba_status === 'COMPLIANT_HIGH_RIGOR') ? 'checklist-item pass' : 'checklist-item warn';
    chkBloom.querySelector('.check-icon').textContent = (ba.nba_status === 'COMPLIANT_HIGH_RIGOR') ? '✓' : '⚠';
  }
  const chkMatrix = $('chk-matrix');
  if (chkMatrix) {
    chkMatrix.className = (mc.total_mapped_cells > 0) ? 'checklist-item pass' : 'checklist-item warn';
    chkMatrix.querySelector('.check-icon').textContent = (mc.total_mapped_cells > 0) ? '✓' : '⚠';
  }
  const chkBooks = $('chk-books');
  if (chkBooks) {
    const hasBooks = (d2.books || []).length > 0;
    chkBooks.className = hasBooks ? 'checklist-item pass' : 'checklist-item warn';
    chkBooks.querySelector('.check-icon').textContent = hasBooks ? '✓' : '⚠';
  }
  const chkLedger = $('chk-ledger');
  if (chkLedger) {
    const cleanLedger = (d2.not_extracted || []).length === 0;
    chkLedger.className = cleanLedger ? 'checklist-item pass' : 'checklist-item warn';
    chkLedger.querySelector('.check-icon').textContent = cleanLedger ? '✓' : '⚠';
  }
}

function renderHeatmapTable(d2) {
  const wrap = $('audit-heatmap-table-wrap');
  if (!wrap) return;

  const matrix = d2.co_po_matrix || {};
  const cos = d2.course_outcomes || [];
  const pos = d2.programme_outcomes || [];

  // Collect all unique PO keys
  const poSet = new Set();
  pos.forEach(p => { if (p.id) poSet.add(p.id); });
  Object.values(matrix).forEach(row => {
    if (row && typeof row === 'object') {
      Object.keys(row).forEach(k => poSet.add(k));
    }
  });

  let poList = Array.from(poSet);
  if (!poList.length) {
    poList = Array.from({length: 12}, (_, i) => `PO${i+1}`);
  } else {
    poList.sort((a, b) => {
      const numA = parseInt(a.replace(/\D/g, '') || 0);
      const numB = parseInt(b.replace(/\D/g, '') || 0);
      const preA = a.replace(/\d/g, '');
      const preB = b.replace(/\d/g, '');
      if (preA !== preB) return preA.localeCompare(preB);
      return numA - numB;
    });
  }

  let coKeys = Object.keys(matrix);
  if (!coKeys.length && cos.length) {
    coKeys = cos.map(c => c.id || 'CO');
  }
  if (!coKeys.length) {
    coKeys = ['CO1', 'CO2', 'CO3', 'CO4', 'CO5'];
  }

  let html = '<table class="heatmap-table"><thead><tr><th class="co-col">Course Outcome</th>';
  poList.forEach(po => {
    html += `<th>${esc(po)}</th>`;
  });
  html += '</tr></thead><tbody>';

  coKeys.forEach(co => {
    const row = matrix[co] || {};
    html += `<tr><th class="co-col">${esc(co)}</th>`;
    poList.forEach(po => {
      const val = row[po] !== undefined && row[po] !== null ? String(row[po]).trim() : '';
      let cls = 'heatmap-cell level-0';
      const uVal = val.toUpperCase();
      if (['3', 'S', 'H', 'HIGH', 'STRONG'].includes(uVal)) cls = 'heatmap-cell level-3';
      else if (['2', 'M', 'MED', 'MEDIUM'].includes(uVal)) cls = 'heatmap-cell level-2';
      else if (['1', 'L', 'LOW', 'WEAK'].includes(uVal)) cls = 'heatmap-cell level-1';
      html += `<td class="${cls}" title="${esc(co)} → ${esc(po)}: ${val || 'Unmapped'}">${val ? esc(val) : '—'}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  wrap.innerHTML = html;
}

// ── Dossier Modal & Export ───────────────────────────────────────────
let currentDossierHtml = '';

async function openDossierModal() {
  const d2 = STATE.task2Result;
  if (!d2 || !d2.course) {
    toast('⚠️ Please select or extract a course first', 'error');
    return;
  }
  const modal = $('dossier-modal');
  const frame = $('dossier-preview-frame');
  if (modal) modal.classList.add('open');

  if (frame) {
    frame.srcdoc = '<!DOCTYPE html><html><body style="font-family:sans-serif;padding:2rem;text-align:center;color:#64748b;background:#fff">Generating comprehensive NBA Course Dossier...</body></html>';
  }

  try {
    if (STATE.serverOnline) {
      const resp = await fetch(STATE.serverUrl + '/api/export-dossier', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ course_code: d2.course?.code, d2: d2 }),
        signal: AbortSignal.timeout(10000)
      });
      if (resp.ok) {
        const data = await resp.json();
        currentDossierHtml = data.html || '';
        if (frame) frame.srcdoc = currentDossierHtml;
        return;
      }
    }
  } catch (_) {}

  // Local fallback if offline
  currentDossierHtml = buildClientDossierHtml(d2);
  if (frame) frame.srcdoc = currentDossierHtml;
}

function closeDossierModal() {
  $('dossier-modal')?.classList.remove('open');
  const frame = $('dossier-preview-frame');
  if (frame) frame.srcdoc = '';
}

function printDossier() {
  if (!currentDossierHtml) return;
  const pWin = window.open('', '_blank');
  if (!pWin) {
    toast('⚠️ Pop-up blocked, please allow pop-ups to print', 'error');
    return;
  }
  pWin.document.write(currentDossierHtml);
  pWin.document.close();
  pWin.focus();
  setTimeout(() => { pWin.print(); }, 400);
}

function downloadDossierHtml() {
  if (!currentDossierHtml) return;
  const code = STATE.task2Result?.course?.code || 'Course';
  const blob = new Blob([currentDossierHtml], { type: 'text/html;charset=utf-8' });
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: `Course_Dossier_${code}.html`,
  });
  a.click();
  toast(`⬇ Course_Dossier_${code}.html downloaded`, 'success');
}

function buildClientDossierHtml(d2) {
  const c = d2.course || {};
  const units = d2.units || [];
  const cos = d2.course_outcomes || [];
  const pos = d2.programme_outcomes || [];
  const matrix = d2.co_po_matrix || {};
  const books = d2.books || [];

  return `
    <div style="font-family:'Times New Roman',serif;max-width:850px;margin:0 auto;color:#111">
      <div style="text-align:center;border-bottom:2px solid #333;padding-bottom:12px;margin-bottom:20px">
        <h2 style="margin:0;font-size:18pt;text-transform:uppercase">Course Master File &amp; Dossier</h2>
        <div style="font-size:11pt;color:#555">Outcome-Based Education (OBE) &amp; NBA Accreditation Compliance Record</div>
      </div>
      <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
        <tr><td style="padding:6px;border:1px solid #ccc;font-weight:bold;width:25%">Course Code:</td><td style="padding:6px;border:1px solid #ccc">${esc(c.code||'N/A')}</td><td style="padding:6px;border:1px solid #ccc;font-weight:bold;width:25%">Credits:</td><td style="padding:6px;border:1px solid #ccc">${c.credits||'N/A'}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ccc;font-weight:bold">Course Title:</td><td style="padding:6px;border:1px solid #ccc" colspan="3">${esc(c.title||'Course')}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ccc;font-weight:bold">L-T-P Distribution:</td><td style="padding:6px;border:1px solid #ccc">${c.lecture||0}-${c.tutorial||0}-${c.practical||0}</td><td style="padding:6px;border:1px solid #ccc;font-weight:bold">Total Contact Hours:</td><td style="padding:6px;border:1px solid #ccc">${units.reduce((a,u)=>a+(u.hours||0),0)} hrs</td></tr>
      </table>
      <h3 style="border-bottom:1px solid #666;padding-bottom:4px;margin-top:20px">1. Course Outcomes (COs)</h3>
      <table style="width:100%;border-collapse:collapse;margin-bottom:15px">
        <thead><tr style="background:#f0f0f0"><th style="padding:6px;border:1px solid #ccc;width:12%">CO ID</th><th style="padding:6px;border:1px solid #ccc">Outcome Statement</th><th style="padding:6px;border:1px solid #ccc;width:18%">Bloom's Level</th></tr></thead>
        <tbody>
          ${cos.map(co=>`<tr><td style="padding:6px;border:1px solid #ccc;font-weight:bold">${esc(co.id)}</td><td style="padding:6px;border:1px solid #ccc">${esc(co.text)}</td><td style="padding:6px;border:1px solid #ccc;text-transform:capitalize">${esc(co.bloom||'understand')}</td></tr>`).join('')}
        </tbody>
      </table>
      <h3 style="border-bottom:1px solid #666;padding-bottom:4px;margin-top:20px">2. Course Syllabus &amp; Topic Plan</h3>
      ${units.map(u=>`
        <div style="margin-bottom:14px">
          <div style="font-weight:bold;background:#fafafa;padding:6px;border:1px solid #eee">Unit ${u.unit}: ${esc(u.title)} (${u.hours||0} Hours)</div>
          <ul style="margin:6px 0 0 20px;padding:0">
            ${(u.topics||[]).map(t=>`<li style="font-size:10pt;margin-bottom:3px">${esc(t.text)} <i style="color:#666">(${esc(t.bloom||'understand')})</i></li>`).join('')}
          </ul>
        </div>
      `).join('')}
      <h3 style="border-bottom:1px solid #666;padding-bottom:4px;margin-top:20px">3. Prescribed Textbooks &amp; References</h3>
      <ol style="margin-left:20px;padding:0">
        ${books.map(b=>`<li style="margin-bottom:5px;font-size:10pt"><b>[${esc(b.kind==='text'?'Textbook':'Reference')}]</b> ${esc(b.author?b.author+': ': '')}<i>${esc(b.title)}</i>, ${esc(b.publisher||'')}${b.edition?', '+esc(b.edition)+' Ed.':''}${b.year?', '+b.year:''}.</li>`).join('')}
      </ol>
    </div>
  `;
}

// ── Hints Studio Modal ───────────────────────────────────────────────
function openHintsStudio() {
  const modal = $('hints-modal');
  const tbody = $('hints-table-body');
  if (!modal || !tbody) return;

  tbody.innerHTML = '';
  const d1 = STATE.task1Result;
  const courses = (d1?.courses && d1.courses.length) ? d1.courses : [{ code: 'CS23301', title: 'DATA STRUCTURES', page: 12 }];

  courses.forEach(c => {
    addHintRow({
      code: c.code || '',
      title: c.title || '',
      start_page: c.page || 1,
      end_page: (c.page ? c.page + 2 : 3)
    });
  });

  modal.classList.add('open');
}

function closeHintsStudio() {
  $('hints-modal')?.classList.remove('open');
}

function addHintRow(hint = {}) {
  const tbody = $('hints-table-body');
  if (!tbody) return;
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><input type="text" class="hint-code" value="${esc(hint.code || '')}" placeholder="e.g. CS23301"/></td>
    <td><input type="text" class="hint-title" value="${esc(hint.title || '')}" placeholder="e.g. DATA STRUCTURES"/></td>
    <td><input type="number" class="hint-start" value="${hint.start_page || 1}" min="1"/></td>
    <td><input type="number" class="hint-end" value="${hint.end_page || 2}" min="1"/></td>
    <td style="text-align:center"><button class="btn btn-sm btn-ghost" style="color:var(--accent-red);padding:2px 6px" onclick="this.closest('tr').remove()">✕</button></td>
  `;
  tbody.appendChild(tr);
}

function getHintsFromTable() {
  const rows = document.querySelectorAll('#hints-table-body tr');
  const courses = [];
  rows.forEach(r => {
    const code = r.querySelector('.hint-code')?.value.trim();
    const title = r.querySelector('.hint-title')?.value.trim();
    const start_page = parseInt(r.querySelector('.hint-start')?.value || 1);
    const end_page = parseInt(r.querySelector('.hint-end')?.value || 2);
    if (code || title) {
      courses.push({ code, title, start_page, end_page });
    }
  });
  return { courses };
}

function downloadHintsJSON() {
  const hints = getHintsFromTable();
  const blob = new Blob([JSON.stringify(hints, null, 2)], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: 'hints.json',
  });
  a.click();
  toast('⬇ hints.json downloaded', 'success');
}

async function applyHintsAndRun() {
  const hints = getHintsFromTable();
  STATE.hintsData = hints;
  closeHintsStudio();
  toast('⚙ Hints applied to session. Ready for extraction.', 'success');
  runExtraction();
}

window.openDossierModal = openDossierModal;
window.closeDossierModal = closeDossierModal;
window.printDossier = printDossier;
window.downloadDossierHtml = downloadDossierHtml;
window.openHintsStudio = openHintsStudio;
window.closeHintsStudio = closeHintsStudio;
window.addHintRow = addHintRow;
window.downloadHintsJSON = downloadHintsJSON;
window.applyHintsAndRun = applyHintsAndRun;
window.renderCurriculumAudit = renderCurriculumAudit;

// ── Toast ─────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, type='success') {
  const el = $('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = `show toast-${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, 3200);
}

// ── Init ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Nav links
  document.querySelectorAll('.nav-link[data-nav]').forEach(link => {
    link.addEventListener('click', () => navigate(link.dataset.nav));
  });

  // Results tabs
  document.querySelectorAll('.results-tab[data-tab]').forEach(t => {
    t.addEventListener('click', () => switchResultsTab(t.dataset.tab));
  });

  // Task-2 sub-tabs
  document.querySelectorAll('.t2-tab[data-t2]').forEach(t => {
    t.addEventListener('click', () => switchT2Tab(t.dataset.t2));
  });

  // Toggles
  document.querySelectorAll('.toggle').forEach(toggle => {
    toggle.addEventListener('click', () => toggle.classList.toggle('on'));
  });

  initUpload();

  // Load online settings & mode
  loadOnlineSettings();

  // Auto check server
  checkServer();

  // Show first t2 pane
  const firstPane = document.querySelector('.t2-pane');
  if (firstPane) { firstPane.classList.add('active'); firstPane.style.display = 'block'; }

  // Initialize chat context with active syllabus
  const initCtx = {
    task1: STATE.task1Result,
    task2: STATE.task2Result
  };
  if (typeof CHAT !== 'undefined') CHAT.context = initCtx;
  if (typeof updateContextPanel === 'function') updateContextPanel(initCtx);

  navigate('home');
});
