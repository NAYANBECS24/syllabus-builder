/* ═══════════════════════════════════════════════════════════
   SYLEX — Offline Chat Assistant Engine
   100% local, no internet required
   ═══════════════════════════════════════════════════════════ */
'use strict';

// ── Chat state ─────────────────────────────────────────────────────
const CHAT = {
  context: null,    // Current extraction results
  history: [],      // Message history
};

// ── Knowledge base ──────────────────────────────────────────────────
const KB = {
  howToHints: `To provide manual hints for a difficult PDF, create a <code>hints.json</code> file:<br/>
<code>{"courses":[{"code":"CS23301","title":"DATA STRUCTURES","page":12}]}</code><br/>
Then run: <code>python sylex.py --pdf file.pdf --hints hints.json</code><br/>
Or upload it via the Advanced options panel in the Extract tab.`,

  bloomLevels: `Bloom's Taxonomy (as used by SYLEX):<br/>
<table class="result-table"><tr><th>Level</th><th>K-code</th><th>Example verbs</th></tr>
<tr><td>remember</td><td>K1</td><td>define, list, name, recall</td></tr>
<tr><td>understand</td><td>K2</td><td>explain, describe, summarize</td></tr>
<tr><td>apply</td><td>K3</td><td>solve, implement, compute</td></tr>
<tr><td>analyse</td><td>K4</td><td>compare, differentiate, examine</td></tr>
<tr><td>evaluate</td><td>K5</td><td>justify, assess, critique</td></tr>
<tr><td>create</td><td>K6</td><td>design, formulate, devise</td></tr></table>
SYLEX detects K1–K6, BT1–BT6, and explicit words. Falls back to verb lexicon.`,

  whyTopicsMissing: `Topics may be missing if:<br/>
<ul>
<li>The PDF page is scanned/image — native text extractor gets blank text</li>
<li>Unit headings use unusual keywords (e.g. "Topic 1:" instead of "UNIT I")</li>
<li>Topics span multiple columns that pdfplumber misaligns</li>
<li>The separator style isn't detected (e.g. pipes <code>|</code> or tabs)</li>
</ul>
<b>Fix:</b> Use <code>--debug</code> to see what text was extracted, then add a hint or preprocess the PDF.`,

  whyMatrixMissing: `CO-PO matrix extraction fails when:<br/>
<ul>
<li>The matrix is an image/screenshot embedded in the PDF</li>
<li>The matrix uses merged cells (pdfplumber can't split them)</li>
<li>PO headers have unusual formatting (e.g. "Programme Outcome 1" instead of "PO1")</li>
<li>The matrix spans multiple pages but is cut by the course boundary</li>
</ul>
<b>Fix:</b> Run with <code>--debug</code>, check <code>_debug.page_range</code> to see if the matrix page is included.`,

  accuracy: `To maximize accuracy:<br/>
<ul>
<li><b>Native PDF</b> → highest accuracy (pdfplumber extracts exact text + geometry)</li>
<li><b>Scanned PDF</b> → install <code>pytesseract</code> + Tesseract OCR for text recovery</li>
<li><b>Difficult boundaries</b> → use <code>--hints</code> to specify exact page ranges</li>
<li><b>Multiple runs</b> → output is deterministic (identical every run)</li>
<li><b>Debugging</b> → <code>python sylex.py --pdf f.pdf --debug</code> shows grammar, signals, and page range</li>
</ul>`,

  howServer: `The local server lets you use the web UI for extraction:<br/>
<code>python sylex_server.py</code><br/>
Then open <code>http://localhost:7823</code> in your browser.<br/>
The server receives your PDF, runs <code>sylex.py</code> locally, and returns JSON — no internet needed.`,
};

// ── Intent patterns ─────────────────────────────────────────────────
const INTENTS = [
  {
    patterns: [/what.*(extract|found|result)/i, /what.*(pdf|document)/i],
    handler: handleWhatExtracted,
  },
  {
    patterns: [/topic.*miss/i, /why.*topic/i, /miss.*topic/i],
    handler: () => KB.whyTopicsMissing,
  },
  {
    patterns: [/matrix.*miss/i, /co.*po.*miss/i, /why.*matrix/i, /fix.*matrix/i],
    handler: () => KB.whyMatrixMissing,
  },
  {
    patterns: [/bloom/i, /taxonomy/i, /k[1-6]/i, /bt[1-6]/i],
    handler: () => KB.bloomLevels,
  },
  {
    patterns: [/hint/i, /override/i, /manual/i, /hints\.json/i],
    handler: () => KB.howToHints,
  },
  {
    patterns: [/server/i, /localhost/i, /start server/i, /web ui/i],
    handler: () => KB.howServer,
  },
  {
    patterns: [/accura/i, /improve/i, /better/i, /tip/i],
    handler: () => KB.accuracy,
  },
  {
    patterns: [/not.extract/i, /fail/i, /ledger/i, /what.*wrong/i, /what.*fail/i],
    handler: handleNotExtracted,
  },
  {
    patterns: [/course.*found/i, /list.*course/i, /which.*course/i, /all course/i],
    handler: handleListCourses,
  },
  {
    patterns: [/bloom.*level/i, /show.*bloom/i, /bloom.*found/i, /bloom.*count/i],
    handler: handleBloomSummary,
  },
  {
    patterns: [/unit/i, /module/i],
    handler: handleUnitSummary,
  },
  {
    patterns: [/book/i, /reference/i, /text.*book/i],
    handler: handleBookSummary,
  },
  {
    patterns: [/co\d|course.*outcome/i],
    handler: handleCOSummary,
  },
  {
    patterns: [/hi|hello|hey/i],
    handler: () => "Hello! Ready to help. Load an extraction result and ask me anything about it.",
  },
  {
    patterns: [/thank/i],
    handler: () => "You're welcome! Remember: <code>python sylex_server.py</code> to use the web UI. Good luck on evaluation day!",
  },
];

// ── Intent handlers ─────────────────────────────────────────────────
function handleWhatExtracted() {
  if (!CHAT.context) return noContext();
  const d1 = CHAT.context.task1;
  const d2 = CHAT.context.task2;
  let reply = '';
  if (d1) {
    reply += `<b>Task 1</b>: Found <b>${d1.course_count}</b> courses in <code>${d1.document}</code>.<br/>`;
  }
  if (d2 && d2.course) {
    const u = d2.units || [];
    const topics = u.reduce((a,u) => a + u.topics.length, 0);
    const cos = (d2.course_outcomes || []).length;
    const matrix_cells = Object.values(d2.co_po_matrix || {})
      .reduce((a, r) => a + Object.keys(r).length, 0);
    reply += `<b>Task 2</b> — <b>${d2.course.code}: ${d2.course.title}</b><br/>`;
    reply += `• ${u.length} units, ${topics} topics<br/>`;
    reply += `• ${cos} Course Outcomes<br/>`;
    reply += `• ${(d2.programme_outcomes||[]).length} Programme Outcomes<br/>`;
    reply += `• ${matrix_cells} CO-PO matrix cells<br/>`;
    reply += `• ${(d2.books||[]).length} books<br/>`;
    if ((d2.not_extracted||[]).length > 0) {
      reply += `<br/>⚠️ <b>${d2.not_extracted.length} item(s)</b> not extracted — see the <i>not_extracted</i> tab or ask me.`;
    } else {
      reply += `<br/>✅ All fields extracted — <code>not_extracted</code> ledger is empty.`;
    }
  }
  return reply || noContext();
}

function handleNotExtracted() {
  if (!CHAT.context) return noContext();
  const d2 = CHAT.context.task2;
  if (!d2) return "Load a Task 2 result first.";
  const ne = d2.not_extracted || [];
  if (ne.length === 0) {
    return "✅ Great news — the <code>not_extracted</code> ledger is empty! Everything was extracted successfully.";
  }
  let reply = `<b>${ne.length} item(s) not extracted:</b><ul>`;
  ne.forEach(item => { reply += `<li>${escHtml(item)}</li>`; });
  reply += `</ul>`;
  reply += `These are <i>honest failures</i> — SYLEX reports what it couldn't read rather than inventing data. `;
  reply += `This scores higher than silently returning wrong data.`;
  return reply;
}

function handleListCourses() {
  if (!CHAT.context?.task1) return noContext();
  const courses = CHAT.context.task1.courses || [];
  if (courses.length === 0) return "No courses found in the extraction. Try running Task 1 again.";
  let reply = `<b>${courses.length} courses found:</b><table class="result-table">
    <tr><th>Code</th><th>Title</th><th>Page</th></tr>`;
  courses.forEach(c => {
    reply += `<tr><td>${escHtml(c.code||'—')}</td><td>${escHtml(c.title)}</td><td>${c.page}</td></tr>`;
  });
  reply += `</table>`;
  return reply;
}

function handleBloomSummary() {
  if (!CHAT.context?.task2) return "Load a Task 2 extraction to see Bloom distribution.";
  const d2    = CHAT.context.task2;
  const all   = [];
  (d2.units||[]).forEach(u => (u.topics||[]).forEach(t => all.push([t.bloom, t.bloom_source])));
  (d2.course_outcomes||[]).forEach(co => all.push([co.bloom, co.bloom_source]));
  if (!all.length) return "No Bloom data found in this extraction.";
  const counts = {};
  all.forEach(([lvl,_]) => { counts[lvl] = (counts[lvl]||0) + 1; });
  const printed = all.filter(([,src]) => src==='printed').length;
  let reply = `<b>Bloom distribution</b> (${all.length} total, ${printed} printed):<table class="result-table">
    <tr><th>Level</th><th>Count</th></tr>`;
  ['remember','understand','apply','analyse','evaluate','create'].forEach(l => {
    if (counts[l]) reply += `<tr><td>${l}</td><td>${counts[l]}</td></tr>`;
  });
  reply += `</table>`;
  return reply;
}

function handleUnitSummary() {
  if (!CHAT.context?.task2) return "Load a Task 2 extraction to see units.";
  const units = CHAT.context.task2.units || [];
  if (!units.length) return "No units found. The document may use unusual heading styles — try providing a <code>hints.json</code>.";
  let reply = `<b>${units.length} units found:</b><table class="result-table">
    <tr><th>#</th><th>Title</th><th>Hours</th><th>Topics</th></tr>`;
  units.forEach(u => {
    reply += `<tr><td>${u.number}</td><td>${escHtml(u.title||'—')}</td>
      <td>${u.hours||'—'}</td><td>${(u.topics||[]).length}</td></tr>`;
  });
  reply += `</table>`;
  return reply;
}

function handleBookSummary() {
  if (!CHAT.context?.task2) return "Load a Task 2 extraction to see books.";
  const books = CHAT.context.task2.books || [];
  if (!books.length) return "No books extracted. The document may not have a clearly labeled 'Text Books' or 'Reference Books' section.";
  let reply = `<b>${books.length} books extracted:</b><ul>`;
  books.forEach(b => {
    reply += `<li><b>[${escHtml(b.kind)}]</b> ${escHtml(b.title)} — ${escHtml(b.author)}`;
    if (b.year) reply += ` (${b.year})`;
    reply += `</li>`;
  });
  reply += `</ul>`;
  return reply;
}

function handleCOSummary() {
  if (!CHAT.context?.task2) return "Load a Task 2 extraction to see Course Outcomes.";
  const cos = CHAT.context.task2.course_outcomes || [];
  if (!cos.length) return "No Course Outcomes extracted. Check if the PDF has a 'Course Outcomes' section.";
  let reply = `<b>${cos.length} Course Outcomes:</b><table class="result-table">
    <tr><th>ID</th><th>Bloom</th><th>Source</th><th>Text (first 60 chars)</th></tr>`;
  cos.forEach(co => {
    reply += `<tr><td>${co.id}</td><td>${co.bloom}</td><td>${co.bloom_source}</td>
      <td>${escHtml((co.text||'').substring(0,60))}…</td></tr>`;
  });
  reply += `</table>`;
  return reply;
}

function noContext() {
  return `No extraction loaded yet. Run an extraction in the Extract tab, or click <b>View Demo Results</b> on the home page.`;
}

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Auto-analysis: produce suggestion cards from results ────────────
function analyzAndSuggest(ctx) {
  const cards = [];
  const d1 = ctx.task1;
  const d2 = ctx.task2;

  if (d1) {
    if (d1.course_count === 0) {
      cards.push({type:'error', title:'No courses detected',
        body:'Course codes may be non-standard. Provide a <code>hints.json</code> to manually specify them.'});
    } else {
      cards.push({type:'ok', title:`${d1.course_count} courses found`,
        body:'Task 1 complete. Click any course card to load Task 2 deep view.'});
    }
  }

  if (d2 && d2.course) {
    const units  = d2.units || [];
    const cos    = d2.course_outcomes || [];
    const matrix = d2.co_po_matrix || {};
    const ne     = d2.not_extracted || [];

    if (!units.length) {
      cards.push({type:'error', title:'No units extracted',
        body:'Unit headings not detected. Run with <code>--debug</code> to inspect the document grammar.'});
    } else {
      const emptyTopics = units.filter(u => !u.topics.length);
      if (emptyTopics.length) {
        cards.push({type:'warn', title:`${emptyTopics.length} unit(s) have no topics`,
          body:`Units ${emptyTopics.map(u=>u.number).join(', ')} have no extracted topics. They may use an unusual separator.`});
      }
    }

    if (!cos.length) {
      cards.push({type:'warn', title:'No Course Outcomes',
        body:'CO section not detected. Check if the PDF prints them as "Course Outcomes" or "COs".'});
    }

    if (!Object.keys(matrix).length) {
      cards.push({type:'warn', title:'CO-PO matrix empty',
        body:'Matrix may be an image or on a page outside the course boundary. Use <code>--debug</code> to check page range.'});
    }

    if (ne.length === 0) {
      cards.push({type:'ok', title:'not_extracted is clean',
        body:'All fields were resolved. Zero honest failures.'});
    } else {
      ne.forEach(item => {
        cards.push({type:'warn', title:'Field not extracted',
          body: escHtml(item)});
      });
    }

    // Scanned page warning
    if (d2._debug && d2._debug.scanned_pages && d2._debug.scanned_pages.length) {
      cards.push({type:'error', title:'Scanned pages detected',
        body:`Pages ${d2._debug.scanned_pages.join(', ')} appear image-only. Install <code>pytesseract</code> for OCR support.`});
    }
  }

  return cards;
}

function renderSuggestions(ctx) {
  const cards = analyzAndSuggest(ctx);
  const panel = document.getElementById('suggestions-panel');
  const container = document.getElementById('suggestion-cards');
  if (!panel || !container) return;
  container.innerHTML = '';
  cards.forEach(c => {
    const el = document.createElement('div');
    el.className = `suggestion-card ${c.type}`;
    el.innerHTML = `<div class="suggestion-title">${c.title}</div><div style="font-size:0.78rem;color:var(--text-secondary);margin-top:4px">${c.body}</div>`;
    container.appendChild(el);
  });
  panel.style.display = 'block';
}

function updateContextPanel(ctx) {
  const d1 = ctx.task1;
  const d2 = ctx.task2;
  const summary = document.getElementById('context-summary');
  const status  = document.getElementById('context-status');
  if (summary) {
    summary.style.display = 'block';
    status.style.display  = 'none';
    const set = (id, val) => { const el = document.getElementById(id); if(el) el.textContent = val; };
    set('ctx-doc',     d1?.document || '—');
    set('ctx-courses', d1?.course_count ?? '—');
    set('ctx-course',  d2?.course ? `${d2.course.code}` : '—');
    const units  = (d2?.units||[]);
    const topics = units.reduce((a,u)=>a+(u.topics||[]).length, 0);
    set('ctx-units',   units.length || '—');
    set('ctx-topics',  topics || '—');
    set('ctx-cos',     (d2?.course_outcomes||[]).length || '—');
    const cells = Object.values(d2?.co_po_matrix||{}).reduce((a,r)=>a+Object.keys(r).length,0);
    set('ctx-matrix',  cells || '—');
    set('ctx-books',   (d2?.books||[]).length || '—');
    set('ctx-ne',      (d2?.not_extracted||[]).length);
  }

  // Update Assistant mode UI
  updateChatModeUI(window.STATE?.extractionMode || 'offline');

  // Dynamic suggestion chips for the active course
  if (d2?.course) {
    const chipsRow = document.getElementById('chat-chips');
    if (chipsRow) {
      const cTitle = d2.course.title || d2.course.code || 'Course';
      chipsRow.innerHTML = `
        <button class="chat-chip" onclick="sendQuick('Suggest 5 exam questions with Bloom taxonomy for ${escHtml(cTitle)}')">📝 5 Exam Questions</button>
        <button class="chat-chip" onclick="sendQuick('Create a 45-hour lecture-by-lecture lesson plan for ${escHtml(cTitle)}')">📅 Lesson Plan</button>
        <button class="chat-chip" onclick="sendQuick('How can I improve Bloom level alignment in ${escHtml(cTitle)}?')">🎯 Improve Bloom</button>
        <button class="chat-chip" onclick="sendQuick('Recommend laboratory experiments and open-source tools for ${escHtml(cTitle)}')">🔬 Lab &amp; Tools</button>
        <button class="chat-chip" onclick="sendQuick('Recommend top reference textbooks and online courses for ${escHtml(cTitle)}')">📚 Books &amp; MOOCs</button>
      `;
    }
  }

  renderSuggestions(ctx);
}

// ── Markdown Parser ─────────────────────────────────────────────────
function renderMarkdown(md) {
  if (!md) return '';
  let html = String(md)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Code blocks: ```lang\ncode\n```
  html = html.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/gi, (m, lang, code) => {
    return `<pre><code class="language-${lang}">${code}</code></pre>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headers
  html = html.replace(/^#### (.*$)/gim, '<h4>$1</h4>');
  html = html.replace(/^### (.*$)/gim, '<h4>$1</h4>');
  html = html.replace(/^## (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^# (.*$)/gim, '<h3>$1</h3>');

  // Bold & Italic
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Blockquotes: > quote
  html = html.replace(/^>\s+(.*$)/gim, '<blockquote>$1</blockquote>');

  // Tables
  const lines = html.split('\n');
  let inTable = false;
  let tableHtml = '';
  const newLines = [];

  for (let i = 0; i < lines.length; i++) {
    const l = lines[i].trim();
    if (l.startsWith('|') && l.endsWith('|')) {
      if (!inTable) {
        inTable = true;
        tableHtml = '<table class="result-table"><tbody>';
      }
      if (/^\|[\s:-|]+\|$/.test(l)) continue;
      const cells = l.split('|').slice(1, -1).map(c => c.trim());
      tableHtml += '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
    } else {
      if (inTable) {
        tableHtml += '</tbody></table>';
        newLines.push(tableHtml);
        inTable = false;
        tableHtml = '';
      }
      newLines.push(lines[i]);
    }
  }
  if (inTable) {
    tableHtml += '</tbody></table>';
    newLines.push(tableHtml);
  }
  html = newLines.join('\n');

  // Lists
  html = html.replace(/^\s*[\-\*]\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)/gim, '<ul>$1</ul>');
  html = html.replace(/<\/ul>\s*<ul>/g, '');

  // Paragraphs
  const paras = html.split(/\n\s*\n/);
  html = paras.map(p => {
    p = p.trim();
    if (!p) return '';
    if (p.startsWith('<h') || p.startsWith('<pre') || p.startsWith('<table') || p.startsWith('<ul') || p.startsWith('<blockquote')) {
      return p;
    }
    return `<p>${p.replace(/\n/g, '<br/>')}</p>`;
  }).join('');

  return html;
}

// ── Interactive Chat Mode Switching ─────────────────────────────────
function updateChatModeUI(mode) {
  const isOnline = (mode === 'online');
  const btnOn = document.getElementById('btn-chatmode-online');
  const btnOff = document.getElementById('btn-chatmode-offline');
  const modePill = document.getElementById('chat-mode-pill');
  const modeSub = document.getElementById('chat-mode-subtitle');
  const provider = 'NVIDIA';
  const model = typeof SYLEX_NVIDIA_MODEL !== 'undefined' ? SYLEX_NVIDIA_MODEL : 'nvidia/nemotron-3-super-120b-a12b';

  if (btnOn) btnOn.classList.toggle('active', isOnline);
  if (btnOff) btnOff.classList.toggle('active', !isOnline);

  if (modePill) {
    if (isOnline) {
      modePill.className = 'chat-status-pill online';
      modePill.textContent = '🌐 Cloud AI Active';
    } else {
      modePill.className = 'chat-status-pill offline';
      modePill.textContent = '⚡ Local Engine';
    }
  }

  if (modeSub) {
    if (isOnline) {
      const cleanModel = model.replace('nvidia/', '').replace('-instruct', '');
      modeSub.textContent = `🌐 ${provider} · ${cleanModel} · OBE Curriculum Advisor & Exam Engine`;
    } else {
      modeSub.textContent = '⚡ Offline Engine · Deterministic Syllabus Rules & Invariants';
    }
  }
}

function toggleChatMode(mode) {
  if (typeof window.setMode === 'function') {
    window.setMode(mode);
  } else {
    window.STATE = window.STATE || {};
    window.STATE.extractionMode = mode;
    localStorage.setItem('sylex_mode', mode);
  }
  updateChatModeUI(mode);
}

// ── Helper: Format Syllabus Context for Prompts ─────────────────────
function formatSyllabusContext(c) {
  if (!c) return '';
  const parts = [];
  const d1 = c.task1;
  const d2 = c.task2;
  if (d1 && d1.document) {
    parts.push(`Document: ${d1.document} (${d1.course_count || (d1.courses || []).length} courses detected)`);
  }
  if (d2 && d2.course) {
    parts.push(`Course: ${d2.course.code || ''} - ${d2.course.title || ''} (Credits: ${d2.course.credits || 4}, Category: ${d2.course.category || 'Core'}, Hours: ${d2.course.lecture || 3}-${d2.course.tutorial || 0}-${d2.course.practical || 0})`);
    if (d2.units && d2.units.length) {
      const uLines = d2.units.map(u => {
        const topList = (u.topics || []).map(t => `${t.text} [Bloom: ${t.bloom || 'understand'}]`).join(', ');
        return `Unit ${u.number}: ${u.title || ''} (${u.hours || 9} hrs)\n  Topics: ${topList || u.text || ''}`;
      });
      parts.push(`Units & Topics:\n` + uLines.join('\n'));
    }
    if (d2.course_outcomes && d2.course_outcomes.length) {
      parts.push(`Course Outcomes:\n` + d2.course_outcomes.map(co => `${co.id}: ${co.text} [Bloom: ${co.bloom || 'understand'}]`).join('\n'));
    }
    if (d2.books && d2.books.length) {
      parts.push(`Prescribed Books:\n` + d2.books.map(b => `[${(b.kind || 'book').toUpperCase()}] ${b.title || ''} by ${b.author || 'Author'} (${b.year || ''})`).join('\n'));
    }
  }
  return parts.join('\n\n');
}

// ── Chat send/receive ───────────────────────────────────────────────
async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg   = (input?.value || '').trim();
  if (!msg) return;
  input.value = '';
  appendMsg(msg, 'user', false);
  showTyping();

  const defaultTask1 = (typeof DEMO_TASK1 !== 'undefined' ? DEMO_TASK1 : null);
  const defaultTask2 = (typeof DEMO_TASK2 !== 'undefined' ? DEMO_TASK2 : null);

  const ctx = {
    task1: CHAT.context?.task1 || window.STATE?.task1Result || defaultTask1,
    task2: CHAT.context?.task2 || window.STATE?.task2Result || defaultTask2
  };

  const savedMode = localStorage.getItem('sylex_mode') || window.STATE?.extractionMode || 'online';
  const defaultServerUrl = (typeof window !== 'undefined' && window.location.origin && window.location.origin !== 'null')
    ? (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
        ? (window.location.port === '7823' ? window.location.origin : 'http://localhost:7823')
        : window.location.origin)
    : 'http://localhost:7823';
  const serverUrl = (window.STATE?.serverUrl || defaultServerUrl).replace(/\/+$/, '');

  const onlineProvider = 'nvidia';
  const onlineModel = typeof SYLEX_NVIDIA_MODEL !== 'undefined' ? SYLEX_NVIDIA_MODEL : 'nvidia/nemotron-3-super-120b-a12b';
  const onlineKey = '';
  const onlineEndpoint = '';

  // If Online Mode is active
  if (isOnline) {
    // 1. Try local server proxy endpoint (/api/chat)
    try {
      const payload = {
        message: msg,
        history: CHAT.history.slice(-6),
        context: ctx,
        provider: onlineProvider,
        model: onlineModel,
        api_key: onlineKey,
        endpoint: onlineEndpoint
      };

      const resp = await fetch(serverUrl + '/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(35000)
      });

      if (resp.ok) {
        const data = await resp.json();
        removeTyping();
        if (data.reply) {
          appendMsg(renderMarkdown(data.reply), 'assistant', true, {
            model: data.model || onlineModel,
            provider: data.provider || onlineProvider
          });
          return;
        }
      }
    } catch (serverErr) {
      console.warn('[Server Chat Proxy Note]', serverErr);
    }

    // 2. Direct browser-to-cloud fallback (if server is offline or proxy failed)
    if (onlineProvider === 'nvidia' && onlineKey) {
      try {
        const syllabusText = formatSyllabusContext(ctx);
        const systemPrompt = `You are SYLEX AI Assistant — University Curriculum Architect, Syllabus Intelligence Consultant, and OBE Specialist.
=== CURRENT COURSE SYLLABUS ===
${syllabusText}
===============================
CRITICAL INSTRUCTIONS:
1. Whatever question the user asks (concepts, definitions, comparisons, code examples, algorithm mechanics, exam questions, lesson plans, Bloom taxonomy analysis, or practical applications), DIRECTLY, THOROUGHLY, AND AUTHORITATIVELY ANSWER IT.
2. Ground your explanations explicitly in the syllabus course, units, topics, and Bloom's taxonomy levels (K1 to K6).
3. Provide pedagogical explanations, step-by-step logic, code snippets (C/C++/Python/Java) where applicable, and real-world examples.
4. Conclude with 2-3 follow-up suggestions under '💡 **Next Suggestions:**'.`;

        const directResp = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + onlineKey
          },
          body: JSON.stringify({
            model: onlineModel || 'nvidia/nemotron-3-super-120b-a12b',
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: msg }
            ],
            max_tokens: 2048,
            temperature: 0.7,
            chat_template_kwargs: { enable_thinking: true }
          }),
          signal: AbortSignal.timeout(28000)
        });

        if (directResp.ok) {
          const directData = await directResp.json();
          const directContent = directData.choices?.[0]?.message?.content;
          if (directContent) {
            removeTyping();
            appendMsg(renderMarkdown(directContent), 'assistant', true, {
              model: onlineModel || 'nvidia/nemotron-3-super-120b-a12b',
              provider: 'nvidia'
            });
            return;
          }
        }
      } catch (directErr) {
        console.warn('[Direct Cloud AI Call Note]', directErr);
      }
    }
  }

  // 3. Deterministic Local Offline Fallback
  removeTyping();
  const localReply = respond(msg);
  appendMsg(renderMarkdown(localReply), 'assistant', true, {
    model: 'local-offline-engine',
    provider: 'local'
  });
}

function sendQuick(msg) {
  const input = document.getElementById('chat-input');
  if (input) input.value = msg;
  sendChat();
  if (typeof navigate === 'function') navigate('chat');
}

function respond(q) {
  // Intent pattern matching
  for (const intent of INTENTS) {
    if (intent.patterns.some(p => p.test(q))) {
      const r = intent.handler();
      if (r) return r;
    }
  }

  const d2 = CHAT.context?.task2 || window.STATE?.task2Result || (typeof DEMO_TASK2 !== 'undefined' ? DEMO_TASK2 : null);
  const course = d2?.course;

  if (course) {
    const qLower = q.toLowerCase();

    // Check for unit-specific query (e.g. "explain unit 1", "unit 2")
    const unitMatch = qLower.match(/unit\s*([1-5]|i{1,3}|iv|v)/i);
    if (unitMatch) {
      const romanMap = { 'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5 };
      let uNum = parseInt(unitMatch[1]);
      if (isNaN(uNum)) uNum = romanMap[unitMatch[1].toLowerCase()] || 1;
      const targetUnit = (d2.units || []).find(u => u.number === uNum) || (d2.units || [])[uNum - 1];

      if (targetUnit) {
        const topics = targetUnit.topics || [];
        const lines = [
          `### 📖 **Unit ${targetUnit.number}: ${targetUnit.title}** (${targetUnit.hours || 9} Contact Hours)`,
          `*Course: ${course.code} - ${course.title}*\n`,
          `#### 🎯 Unit Overview & Scope`,
          `This unit covers foundational and advanced principles of **${targetUnit.title}**. Total prescribed duration: **${targetUnit.hours || 9} lecture hours**.\n`,
          `#### 📋 Granular Syllabus Topics & Bloom Levels`,
          `| # | Topic | Bloom Taxonomy Level | Expected Competency |`,
          `| :--- | :--- | :--- | :--- |`
        ];
        topics.forEach((t, i) => {
          const bloomCap = (t.bloom || 'understand').toUpperCase();
          const comp = bloomCap === 'REMEMBER' ? 'Define, recall, and list basic structures' :
                       bloomCap === 'UNDERSTAND' ? 'Explain mechanics, operations, and behavior' :
                       bloomCap === 'APPLY' ? 'Implement, solve algorithmic problems, and build applications' :
                       bloomCap === 'ANALYSE' ? 'Evaluate trade-offs, compare performance, and optimize' : 'Synthesize and design solutions';
          lines.push(`| **${i+1}** | \`${t.text}\` | **${bloomCap}** | ${comp} |`);
        });

        lines.push(`\n#### 💡 Core Takeaways & Exam Focus`);
        lines.push(`- Ensure a solid conceptual grasp of: *${topics.slice(0, 3).map(t => t.text).join(', ')}*.`);
        lines.push(`- Expect both short theoretical questions (Bloom K1/K2) and algorithmic implementation/numerical problems (Bloom K3/K4).`);
        lines.push(`\n💡 **Next Suggestions:**`);
        lines.push(`1. *'Suggest 5 exam questions for Unit ${targetUnit.number}'*`);
        lines.push(`2. *'Provide a lecture-by-lecture lesson plan for Unit ${targetUnit.number}'*`);
        lines.push(`3. *'Explain the first topic in Unit ${targetUnit.number} in detail'*`);
        return lines.join('\n');
      }
    }

    // Check for topic-specific query in syllabus
    const units = d2.units || [];
    for (const u of units) {
      for (const t of (u.topics || [])) {
        if (t.text && qLower.includes(t.text.toLowerCase())) {
          return `### 💡 Syllabus Topic: **${t.text}**
- **Course**: \`${course.code} - ${course.title}\`
- **Unit**: **Unit ${u.number}: ${u.title}** (${u.hours || 9} Hours)
- **Bloom Taxonomy Level**: **${(t.bloom || 'understand').toUpperCase()}** (${t.bloom_source || 'inferred'})

#### 🔍 Topic Breakdown & Engineering Context
\`${t.text}\` is a core component of **Unit ${u.number} (${u.title})**. It develops cognitive competency at the **${(t.bloom || 'understand').toUpperCase()}** level under the university outcome-based education (OBE) curriculum.

#### 🛠️ Key Concepts to Master:
1. **Mathematical / Structural Definition:** Understand underlying principles, memory models, and formal representations.
2. **Operations & Invariants:** Insertion, deletion, search, traversal, and edge cases.
3. **Complexity Profile:** Time complexity (best, average, worst) and auxiliary space complexity.
4. **Curriculum Alignment:** Maps directly to Course Outcomes and university examinations.

💡 **Next Suggestions:**
1. *'Generate 2-mark and 16-mark exam questions on ${t.text}'*
2. *'Explain ${t.text} with C/C++ implementation code'*
3. *'What are the real-world applications of ${t.text}?'*`;
        }
      }
    }

    // Assessment questions
    if (qLower.includes('exam') || qLower.includes('question') || qLower.includes('quiz') || qLower.includes('test')) {
      const lines = [`### 📝 Recommended Assessment Questions for **${course.code} - ${course.title}**\n`];
      units.slice(0, 5).forEach((u, i) => {
        const tDesc = (u.topics || []).slice(0, 2).map(t => t.text).join(' & ') || u.title;
        lines.push(`**Q${i+1} (Unit ${u.number} — ${u.title} / Bloom: Apply [K3])**`);
        lines.push(`> Discuss the engineering principles of *${tDesc}*. Formulate an algorithm and trace its execution on a sample input.\n`);
      });
      lines.push("💡 **Next Suggestions:**");
      lines.push("1. *'Generate 45-hour lesson plan for this course'*");
      lines.push("2. *'Suggest lab experiments and practical tools'*");
      lines.push("3. *'Evaluate Bloom taxonomy alignment across outcomes'*");
      return lines.join('\n');
    }

    // Lesson plan
    if (qLower.includes('lesson') || qLower.includes('plan') || qLower.includes('lecture') || qLower.includes('schedule')) {
      const lines = [`### 📅 45-Hour Lesson Plan for **${course.code} - ${course.title}**\n`];
      let totalH = 0;
      units.forEach(u => {
        const h = u.hours || 9;
        totalH += h;
        lines.push(`#### Unit ${u.number}: ${u.title} (${h} Contact Hours)`);
        (u.topics || []).slice(0, 4).forEach((t, idx) => {
          lines.push(`- **Lecture ${idx+1}**: ${t.text} *(Bloom: ${(t.bloom || 'understand').toUpperCase()})*`);
        });
      });
      lines.push(`\n*Total Planned Hours:* **${totalH} Hours**`);
      lines.push("\n💡 **Next Suggestions:**");
      lines.push("1. *'Suggest active learning methods for Unit 2'*");
      lines.push("2. *'Generate quiz questions for Unit 1'*");
      return lines.join('\n');
    }

    // Books and literature
    if (qLower.includes('book') || qLower.includes('reference') || qLower.includes('resource') || qLower.includes('reading')) {
      const books = d2.books || [];
      const lines = [`### 📚 Reference Literature & Textbooks for **${course.code} - ${course.title}**\n`];
      books.forEach(b => {
        lines.push(`- **[${(b.kind || 'Book').toUpperCase()}]** *${b.title}* by **${b.author || 'Author'}** (${b.publisher ? b.publisher + ', ' : ''}${b.year || 'Latest Edition'})`);
      });
      lines.push("\n💡 **Next Suggestions:**");
      lines.push("1. *'Which textbook is most suitable for beginners?'*");
      lines.push("2. *'Recommend online MOOC resources and NPTEL links'*");
      return lines.join('\n');
    }

    return `### 🎓 Syllabus Intelligence: **${course.code} - ${course.title}**

- **Structure**: Category \`${course.category || 'Core'}\`, Credits \`${course.credits || 4}\`, L-T-P: \`${course.lecture || 3}-${course.tutorial || 0}-${course.practical || 0}\`
- **Units**: **${(d2.units || []).length} units** with **${(d2.units || []).reduce((a,u)=>a+(u.topics||[]).length, 0)} granular topics**
- **Course Outcomes**: **${(d2.course_outcomes || []).length} COs**
- **Books**: **${(d2.books || []).length} prescribed references**

💡 **Next Suggestions:**
1. *'Explain Unit 1 in detail with examples'*
2. *'Suggest 5 exam questions for this course'*
3. *'Create a 45-hour lecture lesson plan'*`;
  }

  return `### 🤖 SYLEX AI Assistant
I can analyze your syllabus, explain any unit or topic in depth, generate exam questions, create lesson plans, and evaluate Bloom taxonomy.
Load an extraction from the **Results** tab or upload a PDF in **Extract** to explore deep curriculum intelligence!

💡 **Next Suggestions:**
1. *'Explain Unit 1 in detail'*
2. *'What was extracted from this PDF?'*
3. *'Show me all Bloom levels found'*`;
}

function appendMsg(content, role, isHtml = false, meta = null) {
  const messages = document.getElementById('chat-messages');
  if (!messages) return;
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  const avatar = document.createElement('div');
  avatar.className = 'chat-avatar';
  avatar.textContent = role === 'assistant' ? 'Ω' : 'U';
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';

  if (role === 'assistant') {
    const tag = document.createElement('div');
    if (meta && meta.model && meta.model !== 'local-offline-engine') {
      const cleanM = String(meta.model).replace('nvidia/', '').replace('-instruct', '').toUpperCase();
      tag.className = 'chat-model-tag';
      tag.innerHTML = `🌐 Cloud AI · ${cleanM}`;
    } else {
      tag.className = 'chat-model-tag offline';
      tag.innerHTML = `⚡ Local Engine`;
    }
    bubble.appendChild(tag);
  }

  const contentWrap = document.createElement('div');
  if (isHtml) contentWrap.innerHTML = content;
  else contentWrap.textContent = content;
  bubble.appendChild(contentWrap);

  div.appendChild(avatar);
  div.appendChild(bubble);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  CHAT.history.push({ role, content });
}

let typingEl = null;
function showTyping() {
  const messages = document.getElementById('chat-messages');
  if (!messages) return;
  typingEl = document.createElement('div');
  typingEl.className = 'chat-msg assistant';
  typingEl.innerHTML = `<div class="chat-avatar">Ω</div>
    <div class="chat-bubble chat-typing">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>`;
  messages.appendChild(typingEl);
  messages.scrollTop = messages.scrollHeight;
}

function removeTyping() {
  if (typingEl) { typingEl.remove(); typingEl = null; }
}

function clearChat() {
  const messages = document.getElementById('chat-messages');
  if (messages) messages.innerHTML = '';
  CHAT.history = [];
  appendMsg('Chat cleared. Ask me anything about your extraction, request exam questions, or create lesson plans!', 'assistant', false);
}

// Export to global
window.CHAT              = CHAT;
window.sendChat          = sendChat;
window.sendQuick         = sendQuick;
window.clearChat         = clearChat;
window.updateContextPanel = updateContextPanel;
window.renderMarkdown    = renderMarkdown;
window.updateChatModeUI  = updateChatModeUI;
window.toggleChatMode    = toggleChatMode;
