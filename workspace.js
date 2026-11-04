'use strict';

// Shared motion and navigation. All content stays visible without this module.
(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const chapters = {
    studio: ['00', 'DOCUMENTS → A BODY OF WORK', 'Save · Compare · Plan', '#c7b8ef'],
    extract: ['01', 'SOURCE → STRUCTURE', 'Upload · Extract · Review', '#89a8ff'],
    results: ['02', 'STRUCTURE → EVIDENCE', 'Inspect · Audit · Export', '#83cfbf'],
    books: ['03', 'A QUESTION → A PAGE', 'Upload · Search · Read', '#d5ba83'],
    finder: ['04', 'REFERENCE → DISCOVERY', 'Discover · Compare · Collect', '#b2a2ee'],
    chat: ['05', 'EVIDENCE → PERSPECTIVE', 'Ask · Explore · Develop', '#83cbd5'],
    settings: ['06', 'YOUR WORKSPACE, CONNECTED', 'Connect · Verify · Configure', '#9cbbdd'],
  };
  let ambient = [];
  const revealSelector = '.course-card,.stat-card,.book-result,.finder-result-card,.finder-shelf-card,.chat-msg,.studio-project-card,.studio-session,.settings-group,.mode-card,.home-flow article,.capability-card';
  const seen = new WeakSet();

  function reveal(element, delay = 0) {
    if (!element || reduced.matches || !element.getClientRects().length) return;
    element.animate([
      { transform: 'translateY(18px)', clipPath: 'inset(0 0 100% 0)' },
      { transform: 'translateY(0)', clipPath: 'inset(0 0 0 0)' },
    ], { duration: 620, delay, easing: 'cubic-bezier(.2,.8,.2,1)' });
  }

  function decorateHeaders() {
    Object.entries(chapters).forEach(([name, [number, label, steps, color]]) => {
      const header = document.querySelector(`#section-${name} .page-header`);
      if (!header) return;
      header.classList.add('chapter-header');
      header.style.setProperty('--chapter-color', color);
      const art = document.createElement('div');
      art.className = 'chapter-art';
      art.setAttribute('aria-hidden', 'true');
      art.innerHTML = `<svg viewBox="0 0 240 210" fill="none"><g class="chapter-orbit"><circle cx="120" cy="105" r="95" stroke="currentColor" stroke-opacity=".18"/><circle cx="120" cy="105" r="76" stroke="currentColor" stroke-opacity=".3" stroke-dasharray="2 9"/><circle cx="120" cy="10" r="4" fill="currentColor"/><circle cx="25" cy="105" r="3" fill="currentColor"/></g><g class="chapter-document"><path d="M77 49h62l25 25v88H77z" fill="currentColor" fill-opacity=".06" stroke="currentColor" stroke-opacity=".7"/><path d="M139 49v25h25M94 91h52M94 106h41M94 121h52M94 136h28" stroke="currentColor" stroke-opacity=".8"/><path class="chapter-scan" d="M63 105h114" stroke="currentColor" stroke-width="2"/></g></svg><span class="chapter-number">${number}</span>`;
      const foot = document.createElement('div');
      foot.className = 'chapter-foot';
      const caption = document.createElement('span');
      caption.textContent = label;
      const path = document.createElement('span');
      path.textContent = steps;
      foot.append(caption, path);
      header.append(art, foot);
    });
  }

  function enterPage(section) {
    ambient.forEach(animation => animation.cancel());
    ambient = [];
    const root = document.getElementById(`section-${section}`);
    if (!root || reduced.matches) return;
    const header = root.querySelector('.page-header,.hero-copy');
    if (header) {
      header.querySelectorAll('.eyebrow-label,.hero-eyebrow,h1,.section-sub,.hero-sub,.hero-command,.hero-cta,.chapter-foot').forEach((element, index) => reveal(element, index * 65));
    }
    const orbit = root.querySelector('.chapter-orbit');
    const scan = root.querySelector('.chapter-scan');
    if (orbit) ambient.push(orbit.animate([{ transform: 'rotate(0deg)' }, { transform: 'rotate(360deg)' }], { duration: 42000, iterations: Infinity }));
    if (scan) ambient.push(scan.animate([{ transform: 'translateY(-25px)' }, { transform: 'translateY(36px)' }], { duration: 3400, iterations: Infinity, direction: 'alternate', easing: 'ease-in-out' }));
    root.querySelectorAll('.drop-zone,.book-search-panel,.finder-search-panel,.chat-context,.chat-main,.service-console,.empty-state').forEach((element, index) => reveal(element, 130 + index * 70));
  }

  function initMotion() {
    decorateHeaders();
    const observer = new IntersectionObserver(entries => {
      entries.filter(entry => entry.isIntersecting).forEach((entry, index) => {
        reveal(entry.target, Math.min(index, 5) * 45);
        observer.unobserve(entry.target);
      });
    }, { threshold: .08 });
    const watch = root => {
      if (!(root instanceof Element)) return;
      const elements = root.matches(revealSelector) ? [root] : [];
      elements.push(...root.querySelectorAll(revealSelector));
      elements.forEach(element => {
        if (seen.has(element)) return;
        seen.add(element);
        observer.observe(element);
      });
    };
    watch(document.getElementById('app'));
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(watch)))
      .observe(document.getElementById('app'), { childList: true, subtree: true });
    document.addEventListener('sylex:navigate', event => enterPage(event.detail.section));
    document.addEventListener('sylex:tab', event => reveal(event.detail.element));
    document.addEventListener('visibilitychange', () => ambient.forEach(animation => document.hidden ? animation.pause() : animation.play()));
    reduced.addEventListener('change', () => enterPage(window.STATE?.section || 'home'));
    document.addEventListener('pointermove', event => {
      if (reduced.matches || event.pointerType === 'touch') return;
      const card = event.target.closest('.settings-group,.mode-card,.course-card,.finder-result-card,.service-card');
      if (!card) return;
      const box = card.getBoundingClientRect();
      card.style.setProperty('--pointer-x', `${event.clientX - box.left}px`);
      card.style.setProperty('--pointer-y', `${event.clientY - box.top}px`);
    });
    enterPage(window.STATE?.section || 'home');
  }

  function initSearch() {
    const dialog = document.getElementById('workspace-search');
    const input = document.getElementById('workspace-query');
    const results = document.getElementById('workspace-matches');
    const items = [
      ['Overview', 'Home · introduction', () => navigate('home')],
      ['Extract a syllabus', 'Upload a PDF · course catalog', () => navigate('extract')],
      ['Review results', 'Courses · audit · exports', () => navigate('results')],
      ['Search inside a book', 'PDF · topics · chapters', () => navigate('books')],
      ['Discover books', 'Catalogs · editions · research shelf', () => navigate('finder')],
      ['Curriculum assistant', 'Questions · outcomes · lesson planning', () => navigate('chat')],
      ['Workspace settings', 'Connections · model · configuration', () => navigate('settings')],
      ['Open sample analysis', 'Load the clearly labeled sample dataset', () => loadDemo()],
    ];
    function render() {
      const query = input.value.trim().toLowerCase();
      const courses = (window.STATE?.task1Result?.courses || []).map(course => [
        `${course.code || 'Course'} · ${course.title}`, `Extracted course · page ${course.page || '—'}`,
        () => { navigate('results'); loadTask2ForCourse(course); },
      ]);
      const projects = window.SylexStudio?.commands() || [];
      const matches = [...items, ...projects, ...courses].filter(item => `${item[0]} ${item[1]}`.toLowerCase().includes(query)).slice(0, 18);
      results.replaceChildren(...matches.map(([title, description, action]) => {
        const button = document.createElement('button');
        button.type = 'button';
        const name = document.createElement('strong');
        name.textContent = title;
        const detail = document.createElement('span');
        detail.textContent = description;
        button.append(name, detail);
        button.addEventListener('click', () => { dialog.close(); action(); });
        return button;
      }));
      if (!matches.length) {
        const empty = document.createElement('p');
        empty.className = 'workspace-no-matches';
        empty.textContent = 'No matching pages or extracted courses.';
        results.append(empty);
      }
    }
    window.openWorkspaceSearch = () => {
      if (dialog.open) return;
      input.value = '';
      render();
      dialog.showModal();
      reveal(dialog);
      input.focus();
    };
    input.addEventListener('input', render);
    dialog.querySelector('.workspace-search-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener('keydown', event => {
      const buttons = [...results.querySelectorAll('button')];
      if (event.key === 'Enter' && document.activeElement === input) { event.preventDefault(); buttons[0]?.click(); }
      if (['ArrowDown', 'ArrowUp'].includes(event.key) && buttons.length) {
        event.preventDefault();
        const current = buttons.indexOf(document.activeElement);
        const next = event.key === 'ArrowDown' ? (current + 1) % buttons.length : (current - 1 + buttons.length) % buttons.length;
        buttons[next].focus();
      }
    });
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (dialog.open) dialog.close(); else window.openWorkspaceSearch();
      }
    });
  }

  function initHealth() {
    const results = document.getElementById('service-results');
    const check = document.getElementById('service-check');
    const download = document.getElementById('service-report');
    let report = null;
    const show = (id, title, state, detail) => {
      let card = document.getElementById(`service-${id}`);
      if (!card) { card = document.createElement('article'); card.id = `service-${id}`; results.append(card); }
      card.className = `service-card service-card--${state}`;
      card.replaceChildren();
      const label = document.createElement('span');
      label.className = 'service-state';
      label.textContent = ({ ready: 'Connected', checking: 'Checking', warning: 'Needs attention', error: 'Unavailable' })[state];
      const heading = document.createElement('h3'); heading.textContent = title;
      const text = document.createElement('p'); text.textContent = detail;
      card.append(label, heading, text);
      if (report) report.services[id] = { title, state, detail };
    };
    async function request(path, payload, timeout) {
      return window.SylexAPI.request(path, { ...(payload ? { json: payload } : {}), timeout });
    }
    check.addEventListener('click', async () => {
      check.disabled = true; check.textContent = 'Checking connections…'; download.disabled = true;
      report = { checked_at: new Date().toISOString(), services: {} };
      results.replaceChildren();
      show('engine', 'Extraction engine', 'checking', 'Checking the API and PDF libraries.');
      show('cloud', 'Cloud assistant', 'checking', 'Sending a small verification request to the selected model.');
      show('catalogs', 'Book catalogs', 'checking', 'Checking six providers with “Pride and Prejudice”.');
      await Promise.allSettled([
        (async () => {
          try {
            const start = performance.now();
            const data = await request('status', null, 6000);
            const dependencies = data.capabilities?.pdf;
            const ready = dependencies ? dependencies.pymupdf && dependencies.pdfplumber : data.status === 'online';
            show('engine', 'Extraction engine', ready ? 'ready' : 'warning', ready ? `API responding in ${Math.round(performance.now() - start)} ms. PDF extraction is available.` : 'API is online; a required PDF library is missing.');
          } catch (error) { show('engine', 'Extraction engine', 'error', error.message); }
        })(),
        (async () => {
          try {
            const data = await request('test-key', { provider: 'nvidia', model: window.getSylexCloudModel() }, 35000);
            show('cloud', 'Cloud assistant', 'ready', `${data.model} responded in ${data.latency_ms} ms.`);
          } catch (error) { show('cloud', 'Cloud assistant', 'error', error.name === 'TimeoutError' ? 'The model did not respond before the connection timeout. Local rules remain available.' : error.message); }
        })(),
        (async () => {
          try {
            const data = await request('book-discovery', { title: 'Pride and Prejudice', author: 'Jane Austen' }, 60000);
            const available = (data.providers || []).filter(provider => provider.status === 'available').length;
            show('catalogs', 'Book catalogs', available ? (available === 6 ? 'ready' : 'warning') : 'error', `${available} of 6 providers responding · ${data.results?.length || 0} editions found.`);
            (data.providers || []).forEach((provider, index) => show(`catalog-${index}`, provider.name, provider.status === 'available' ? 'ready' : 'warning', provider.status === 'available' ? `${provider.matches} candidate records returned.` : provider.detail || 'This provider is unavailable.'));
          } catch (error) { show('catalogs', 'Book catalogs', 'error', error.message); }
        })(),
      ]);
      check.disabled = false; check.textContent = 'Check all connections ↗'; download.disabled = false;
      document.getElementById('service-checked-at').textContent = `Checked ${new Date(report.checked_at).toLocaleString()} · Availability reflects this check.`;
    });
    download.addEventListener('click', () => {
      if (!report) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = 'sylex-connection-report.json'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }

  document.addEventListener('DOMContentLoaded', () => { initMotion(); initSearch(); initHealth(); });
})();
