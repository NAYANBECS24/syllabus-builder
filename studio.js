/* Persistent project library, edition comparison, and source-grounded study plans. */
(() => {
  'use strict';
  const core = window.SylexStudioCore;
  const store = window.SylexProjectStore;
  const $ = id => document.getElementById(id);
  let projects = [];
  let activeId = null;
  let plans = {};
  let restoring = false;
  let dialogState = null;
  let saveTimer;
  let queue = Promise.resolve();
  let lastComparison = null;
  const uuid = () => crypto.randomUUID();
  const notify = (message, type = 'success') => window.toast?.(message, type);
  const date = value => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };
  function button(label, action, className = 'btn btn-secondary') {
    const element = node('button', className, label);
    element.type = 'button';
    element.addEventListener('click', () => Promise.resolve().then(action).catch(error => notify(error.message, 'error')));
    return element;
  }
  function empty(title, description, action) {
    const box = node('div', 'studio-empty');
    box.append(node('span', 'studio-empty-symbol', '↗'), node('h3', '', title), node('p', '', description));
    if (action) box.append(button(action[0], action[1], 'btn btn-primary'));
    return box;
  }
  function download(data, name, type = 'application/json') {
    const url = URL.createObjectURL(new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], { type }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = name.replace(/[^a-zA-Z0-9_.-]+/g, '_'); anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function status(message) { $('studio-storage-status').textContent = message; }
  async function refresh() {
    projects = await store.list();
    renderLibrary();
    renderOverview();
    renderCompareOptions();
    status(`${projects.length} saved ${projects.length === 1 ? 'project' : 'projects'} · Stored in this browser`);
  }
  function write(action) {
    const result = queue.catch(() => {}).then(action);
    queue = result;
    return result;
  }
  function update(id, action) {
    return write(async () => {
      const current = await store.get(id);
      if (!current) throw new Error('This project was removed. Save the current analysis as a new project.');
      const next = action(current);
      next.updatedAt = new Date().toISOString();
      await store.put(next);
      await refresh();
      return next;
    });
  }
  function renderOverview() {
    const totals = projects.reduce((all, project) => {
      const values = core.metrics(project.snapshot);
      all.courses += values.courses; all.analyzed += values.analyzed; all.topics += values.topics;
      return all;
    }, { courses: 0, analyzed: 0, topics: 0 });
    $('studio-overview').replaceChildren(...[
      [projects.length, 'Saved projects', 'A library that grows with your work'],
      [totals.courses, 'Catalog entries', 'Across your saved projects'],
      [totals.analyzed, 'Course analyses', 'Extracted details ready to explore'],
      [totals.topics, 'Extracted topics', 'Source material for your next session'],
    ].map(([value, label, detail]) => {
      const card = node('article', 'studio-stat');
      card.append(node('span', 'studio-stat-value', value), node('strong', '', label), node('span', '', detail));
      return card;
    }));
    let resume = $('studio-home-resume');
    if (!resume) {
      resume = node('div', 'studio-home-resume'); resume.id = 'studio-home-resume';
      document.querySelector('.home-editorial')?.prepend(resume);
    }
    resume.hidden = !projects.length;
    if (projects.length) {
      const project = projects.find(item => item.id === activeId) || projects[0];
      const detail = node('div');
      detail.append(node('span', 'eyebrow-label', 'Continue your work'), node('h3', '', project.name), node('p', '', `${core.metrics(project.snapshot).courses} courses · Updated ${date(project.updatedAt)} · Saved in this browser`));
      const actions = node('div', 'studio-home-resume-actions');
      actions.append(button('Resume project ↗', () => openProject(project.id), 'btn btn-primary'), button('Open the studio', () => navigate('studio'), 'btn studio-hero-button'));
      resume.replaceChildren(detail, actions);
    }
  }
  function renderLibrary() {
    const search = $('studio-search').value.trim().toLowerCase();
    const filtered = projects.filter(project => `${project.name} ${project.snapshot.documentName} ${core.catalog(project.snapshot).map(course => `${course.code} ${course.title}`).join(' ')}`.toLowerCase().includes(search));
    const sort = $('studio-sort').value;
    if (sort === 'name') filtered.sort((a, b) => a.name.localeCompare(b.name));
    if (sort === 'courses') filtered.sort((a, b) => core.metrics(b.snapshot).courses - core.metrics(a.snapshot).courses);
    const grid = $('studio-projects');
    if (!filtered.length) {
      grid.replaceChildren(empty(projects.length ? 'No project matches that search.' : 'Your next chapter starts here.', projects.length ? 'Try a course code, project name, or document title.' : 'Extract a syllabus, then save your analysis. Your PDF, course details, and notes will be ready when you return.', ['Start an extraction', () => navigate('extract')]));
      return;
    }
    grid.replaceChildren(...filtered.map((project, index) => {
      const data = core.metrics(project.snapshot);
      const card = node('article', 'studio-project-card');
      if (project.id === activeId) card.classList.add('is-active');
      card.style.setProperty('--project-hue', String(205 + index % 4 * 22));
      const cover = node('div', 'studio-project-cover');
      const labels = node('div', 'studio-project-labels');
      labels.append(node('span', '', project.snapshot.source === 'sample' ? 'SAMPLE ANALYSIS' : 'CURRICULUM PROJECT'), node('span', '', project.id === activeId ? '● ACTIVE' : String(index + 1).padStart(2, '0')));
      const title = node('h3', '', project.name);
      const openTitle = button(project.name, () => openProject(project.id), 'studio-project-title');
      title.replaceChildren(openTitle);
      cover.append(labels, title, node('span', 'studio-project-document', project.snapshot.documentName));
      const body = node('div', 'studio-project-body');
      const numbers = node('div', 'studio-project-metrics');
      [[data.courses, 'courses'], [data.analyzed, 'analyzed'], [data.topics, 'topics']].forEach(([value, label]) => numbers.append(node('span', '', `${value} ${label}`)));
      const progress = node('div', 'studio-project-progress');
      const fill = node('span'); fill.style.width = `${Math.min(100, data.courses ? data.analyzed / data.courses * 100 : 0)}%`; progress.append(fill);
      body.append(numbers, progress, node('p', 'studio-project-date', `Updated ${date(project.updatedAt)} · ${project.pdf ? 'Source PDF saved' : 'Analysis data only'}`));
      if (project.notes) body.append(node('p', 'studio-project-notes', project.notes));
      const actions = node('div', 'studio-project-actions');
      actions.append(button('Open project ↗', () => openProject(project.id), 'btn btn-primary'), button('Notes', () => editProject(project)), button('Export', () => exportProject(project)));
      const more = node('details', 'studio-project-more');
      more.append(node('summary', '', 'More actions'));
      const menu = node('div');
      menu.append(button('Create a copy', () => duplicate(project)), button('Delete project', () => remove(project), 'btn studio-delete-button'));
      if (!project.pdf) menu.prepend(button('Attach source PDF', () => attachSource(project)));
      more.append(menu); body.append(actions, more); card.append(cover, body);
      return card;
    }));
  }
  async function openProject(id) {
    if (window.STATE.extractionBusy) throw new Error('Cancel the current extraction before opening a project.');
    await queue.catch(() => {});
    const project = await store.get(id);
    if (!project) throw new Error('This saved project is no longer available.');
    restoring = true;
    try {
      clearTimeout(saveTimer);
      window.STATE.activeTask2AbortController?.abort();
      window.STATE.activeTask2AbortController = null;
      window.clearChat?.();
      activeId = id;
      plans = structuredClone(project.plans || {});
      const data = project.snapshot;
      const file = project.pdf ? new File([project.pdf], data.documentName, { type: 'application/pdf' }) : null;
      Object.assign(window.STATE, { pdfFile: file, task1Result: structuredClone(data.task1), task2Result: structuredClone(data.courseDetails.find(item => core.key(item.course) === data.activeCourse) || data.courseDetails[0] || null), dataSource: data.source, courseCache: {}, hintsData: null });
      data.courseDetails.forEach(item => {
        [item.course.code, item.course.title].filter(Boolean).forEach(value => { window.STATE.courseCache[String(value).trim().toUpperCase()] = structuredClone(item); });
      });
      $('file-input').value = '';
      $('file-chosen').classList.toggle('visible', Boolean(file));
      if (file) { $('chosen-name').textContent = file.name; $('chosen-size').textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`; }
      $('btn-run').disabled = !file;
      window.CHAT.context = { task1: window.STATE.task1Result, task2: window.STATE.task2Result };
      window.updateContextPanel(window.CHAT.context);
      renderAll();
      navigate('results');
      switchResultsTab(data.task1 ? 'courses' : 'deep');
      renderLibrary(); renderPlanCourses();
      notify(`${project.name} is ready to resume${file ? '' : ' · source PDF not included'}`);
    } finally { restoring = false; }
  }
  function showDialog(state, name, notes) {
    dialogState = state;
    $('studio-project-name').value = name;
    $('studio-project-notes').value = notes || '';
    $('studio-dialog-title').textContent = state.mode === 'notes' ? 'Keep your thinking close.' : 'Save this chapter.';
    $('studio-dialog-description').textContent = state.mode === 'notes' ? 'Update the project name and research notes. Changes are saved in this browser.' : 'Keep your extracted data and source PDF together in this browser.';
    $('studio-dialog-error').textContent = '';
    $('studio-project-dialog').showModal();
    $('studio-project-name').focus();
  }
  function save() {
    try {
      if (window.STATE.extractionBusy) throw new Error('Wait for extraction to finish before saving its results.');
      const data = core.snapshot(window.STATE);
      const existing = projects.find(project => project.id === activeId);
      showDialog({ mode: 'snapshot', id: activeId, snapshot: data, pdf: window.STATE.pdfFile || null, plans: structuredClone(plans) }, existing?.name || data.documentName.replace(/\.pdf$/i, ''), existing?.notes || '');
    } catch (error) { notify(error.message, 'info'); navigate('studio'); }
  }
  function editProject(project) { showDialog({ mode: 'notes', id: project.id }, project.name, project.notes); }
  async function submitProject(event) {
    event.preventDefault();
    const name = $('studio-project-name').value.trim();
    if (!name) return;
    const draft = dialogState;
    const notes = $('studio-project-notes').value.trim();
    $('studio-project-submit').disabled = true;
    try {
      let saved;
      if (draft.id) saved = await update(draft.id, project => ({ ...project, name, notes, ...(draft.mode === 'snapshot' ? { snapshot: draft.snapshot, pdf: draft.pdf, plans: draft.plans } : {}) }));
      else saved = await write(async () => {
        const project = { id: uuid(), name, notes, snapshot: draft.snapshot, pdf: draft.pdf, plans: draft.plans, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
        await store.put(project); return project;
      });
      if (draft.mode === 'snapshot') activeId = saved.id;
      await refresh();
      $('studio-project-dialog').close();
      notify('Project saved in this browser');
    } catch (error) { $('studio-dialog-error').textContent = error.message; }
    finally { $('studio-project-submit').disabled = false; }
  }
  function exportProject(project) {
    download({ format: 'sylex-project', version: 1, exportedAt: new Date().toISOString(), name: project.name, notes: project.notes, snapshot: project.snapshot, plans: project.plans || {} }, `${project.name}.sylex.json`);
  }
  function attachSource(project) {
    const picker = document.createElement('input'); picker.type = 'file'; picker.accept = 'application/pdf,.pdf';
    picker.addEventListener('change', async () => {
      try {
        const file = picker.files[0]; if (!file) return;
        if (file.size > 50 * 1024 * 1024 || !file.size) throw new Error('Choose a source PDF between 1 byte and 50 MB.');
        if (!(await file.slice(0, 5).text()).startsWith('%PDF-')) throw new Error('This file does not contain a valid PDF header.');
        if (file.name !== project.snapshot.documentName && !confirm(`This project references “${project.snapshot.documentName}”. Attach “${file.name}” as its source? Existing extracted results will be kept.`)) return;
        await update(project.id, current => ({ ...current, pdf: file, snapshot: { ...current.snapshot, documentName: file.name } }));
        if (activeId === project.id) await openProject(project.id);
        notify('Source PDF attached to the saved project');
      } catch (error) { notify(error.message, 'error'); }
    });
    picker.click();
  }
  async function duplicate(project) {
    await write(() => store.put({ ...project, id: uuid(), name: `${project.name} — copy`.slice(0, 120), createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }));
    await refresh(); notify('Project copy created');
  }
  async function remove(project) {
    if (!confirm(`Delete “${project.name}” from this browser? Export it first if you need a backup.`)) return;
    await write(() => store.remove(project.id));
    if (activeId === project.id) activeId = null;
    await refresh(); notify('Saved project removed');
  }
  async function importProject(file) {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) throw new Error('Project JSON must be smaller than 10 MB.');
    const input = JSON.parse(await file.text());
    const normalized = core.validateExport(input);
    await write(() => store.put({ ...normalized, id: uuid(), pdf: null, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }));
    await refresh(); tab('library'); notify('Project imported · PDF can be supplied separately');
  }
  function renderCompareOptions() {
    for (const [id, offset] of [['studio-compare-before', 1], ['studio-compare-after', 0]]) {
      const select = $(id), previous = select.value;
      select.replaceChildren(...projects.map(project => { const option = node('option', '', project.name); option.value = project.id; return option; }));
      select.value = projects.some(project => project.id === previous) ? previous : projects[Math.min(offset, projects.length - 1)]?.id || '';
    }
    if (projects.length > 1 && $('studio-compare-before').value === $('studio-compare-after').value) {
      $('studio-compare-before').value = projects[1].id;
      $('studio-compare-after').value = projects[0].id;
    }
  }
  function differenceList(title, data) {
    const section = node('div', 'studio-difference');
    section.append(node('h4', '', title));
    const list = node('ul');
    data.forEach(item => list.append(node('li', '', typeof item === 'string' ? item : `${item.code || 'Course'} · ${item.title}`)));
    section.append(list); return section;
  }
  function compare(event) {
    event?.preventDefault();
    const left = projects.find(project => project.id === $('studio-compare-before').value);
    const right = projects.find(project => project.id === $('studio-compare-after').value);
    if (!left || !right || left.id === right.id) { notify('Choose two different saved projects to compare.', 'info'); return; }
    const data = core.compare(left.snapshot, right.snapshot);
    lastComparison = { before: left.name, after: right.name, comparedAt: new Date().toISOString(), ...data };
    const output = $('studio-comparison');
    const summary = node('div', 'studio-comparison-summary');
    const heading = node('div');
    heading.append(node('span', 'eyebrow-label', 'Comparison report'), node('h3', '', `${left.name} → ${right.name}`), node('p', '', `${data.addedCourses.length} courses added · ${data.removedCourses.length} removed · ${data.comparedDetails} details compared`));
    summary.append(heading, button('Export comparison', () => download(lastComparison, 'sylex-comparison.json')));
    output.replaceChildren(summary);
    if (data.missingDetails) output.append(node('p', 'studio-evidence-note', `${data.missingDetails} shared courses have incomplete detail coverage. Extract those courses in both projects to compare topics and outcomes.`));
    if (data.addedCourses.length) output.append(differenceList('Courses added', data.addedCourses));
    if (data.removedCourses.length) output.append(differenceList('Courses removed', data.removedCourses));
    for (const course of data.courses) {
      const card = node('details', 'studio-course-diff');
      const summary = node('summary');
      const changeCount = (course.topics?.added.length || 0) + (course.topics?.removed.length || 0) + (course.outcomes?.added.length || 0) + (course.outcomes?.removed.length || 0) + course.metadata.length;
      summary.append(node('strong', '', `${course.code} · ${course.title}`), node('span', '', course.available ? `${changeCount} changes` : 'Catalog comparison'));
      card.append(summary); card.open = changeCount > 0;
      const content = node('div', 'studio-course-diff-body');
      course.metadata.forEach(item => content.append(node('p', '', `${item.field}: ${item.before ?? 'Not extracted'} → ${item.after ?? 'Not extracted'}`)));
      if (course.available) {
        [['Topics added', course.topics.added], ['Topics removed', course.topics.removed], ['Outcomes added', course.outcomes.added], ['Outcomes removed', course.outcomes.removed]].filter(([, values]) => values.length).forEach(([label, values]) => content.append(differenceList(label, values)));
        if (!changeCount) content.append(node('p', '', 'No changes in the compared metadata, topic text, or course outcomes.'));
      } else content.append(node('p', '', 'Course detail is missing from one or both projects. No claim is made about topic or outcome changes.'));
      card.append(content); output.append(card);
    }
    if (!data.courses.length && !data.addedCourses.length && !data.removedCourses.length) output.append(empty('No course identities to compare.', 'These projects do not contain a course catalog.'));
  }
  function currentCourses() {
    try { return core.snapshot(window.STATE).courseDetails; } catch (_) { return []; }
  }
  function renderPlanCourses() {
    const select = $('studio-plan-course');
    const previous = select.value;
    const courses = currentCourses();
    select.replaceChildren(...courses.map(item => { const option = node('option', '', `${item.course.code || 'Course'} · ${item.course.title}`); option.value = core.key(item.course); return option; }));
    if (!courses.length) { const option = node('option', '', 'Extract or open a course first'); option.value = ''; select.append(option); }
    if (courses.some(item => core.key(item.course) === previous)) select.value = previous;
    renderPlan();
  }
  function signature(course) { return JSON.stringify(core.topicTexts(course)); }
  function selectedCourse() { return currentCourses().find(item => core.key(item.course) === $('studio-plan-course').value); }
  async function persistPlans() {
    if (!activeId) return;
    const savedPlans = structuredClone(plans);
    await update(activeId, project => ({ ...project, plans: savedPlans }));
  }
  async function buildPlan(event) {
    event.preventDefault();
    try {
      const course = selectedCourse();
      const id = core.key(course?.course);
      const sessions = core.plan(course, Number($('studio-plan-count').value));
      if (plans[id]?.sessions.some(session => session.completed) && !confirm('Replace this course’s current study plan and its completion progress?')) return;
      plans[id] = { title: `${course.course.code || ''} ${course.course.title}`.trim(), signature: signature(course), sessions, createdAt: new Date().toISOString() };
      renderPlan();
      await persistPlans();
      notify(activeId ? 'Study plan saved to the active project' : 'Study plan ready · save the project to keep it');
    } catch (error) { notify(error.message, 'error'); }
  }
  function renderPlan() {
    const output = $('studio-plan-output');
    const course = selectedCourse();
    const plan = plans[core.key(course?.course)];
    if (!plan) { output.replaceChildren(empty('Give every topic a place.', 'Select an extracted course and choose your study sessions. The plan uses source topics in their printed order.')); return; }
    if (plan.signature !== signature(course)) { output.replaceChildren(empty('This course has changed.', 'Build a fresh plan to use the updated extracted topics. The previous plan remains saved until you replace it.')); return; }
    const done = plan.sessions.filter(session => session.completed).length;
    const summary = node('div', 'studio-plan-summary');
    const heading = node('div'); heading.append(node('span', 'eyebrow-label', 'Your study rhythm'), node('h3', '', plan.title), node('p', '', `${done} of ${plan.sessions.length} sessions complete · ${core.topicTexts(course).length} source topics`));
    const actions = node('div', 'studio-plan-actions');
    actions.append(button('Export Markdown', () => {
      const lines = [`# ${plan.title}`, '', 'Study plan generated from extracted syllabus topics. Session counts are planning choices.', '', ...plan.sessions.flatMap(session => [`## ${session.completed ? '[x]' : '[ ]'} Session ${session.number}`, ...session.topics.map(topic => `- ${topic.unit}: ${topic.topic} (${topic.bloom})`), ''])];
      download(lines.join('\n'), 'sylex-study-plan.md', 'text/markdown');
    }));
    if (!activeId) actions.append(button('Save project to keep progress', save, 'btn btn-primary'));
    summary.append(heading, actions);
    const progress = node('progress', 'studio-plan-progress'); progress.max = plan.sessions.length; progress.value = done; progress.setAttribute('aria-label', 'Study sessions completed');
    output.replaceChildren(summary, progress, node('p', 'studio-evidence-note', 'Sessions are study groups, not the contact hours printed in your syllabus. Fewer topics produce fewer sessions.'));
    const grid = node('div', 'studio-session-grid');
    plan.sessions.forEach(session => {
      const card = node('article', `studio-session${session.completed ? ' is-complete' : ''}`);
      const header = node('label', 'studio-session-header');
      const checkbox = node('input'); checkbox.type = 'checkbox'; checkbox.checked = session.completed; checkbox.setAttribute('aria-label', `Complete session ${session.number}`);
      header.append(node('span', '', `SESSION ${String(session.number).padStart(2, '0')}`), checkbox);
      checkbox.addEventListener('change', async () => {
        const previous = session.completed; session.completed = checkbox.checked; renderPlan();
        try { await persistPlans(); }
        catch (error) { session.completed = previous; renderPlan(); notify(error.message, 'error'); }
      });
      card.append(header);
      const list = node('ul');
      session.topics.forEach(topic => {
        const item = node('li'); item.append(node('span', 'studio-session-unit', topic.unit), node('p', '', topic.topic), node('span', 'bloom-badge', topic.bloom)); list.append(item);
      });
      card.append(list); grid.append(card);
    });
    output.append(grid);
  }
  function tab(name) {
    document.querySelectorAll('[data-studio-tab]').forEach(button => {
      const selected = button.dataset.studioTab === name;
      button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
      $(`studio-${button.dataset.studioTab}`).hidden = !selected;
    });
    if (name === 'planner') renderPlanCourses();
    document.dispatchEvent(new CustomEvent('sylex:tab', { detail: { element: $(`studio-${name}`) } }));
  }
  function onResults() {
    renderPlanCourses();
    if (restoring || !activeId) return;
    clearTimeout(saveTimer);
    const id = activeId;
    const data = core.snapshot(window.STATE);
    const file = window.STATE.pdfFile || null;
    status('Saving active project…');
    saveTimer = setTimeout(() => update(id, project => ({ ...project, snapshot: data, pdf: file })).catch(error => { status('Changes are not saved'); notify(error.message, 'error'); }), 500);
  }
  window.SylexStudio = Object.freeze({ save, open: openProject, tab, refresh,
    commands: () => projects.slice(0, 8).map(project => [project.name, `Saved project · ${project.snapshot.documentName}`, () => openProject(project.id).catch(error => notify(error.message, 'error'))]),
  });
  document.addEventListener('DOMContentLoaded', () => {
    $('studio-save-current').addEventListener('click', save);
    $('studio-project-form').addEventListener('submit', submitProject);
    document.querySelectorAll('.studio-close-dialog').forEach(button => button.addEventListener('click', () => $('studio-project-dialog').close()));
    $('studio-project-dialog').addEventListener('click', event => { if (event.target === event.currentTarget) event.currentTarget.close(); });
    $('studio-search').addEventListener('input', renderLibrary);
    $('studio-sort').addEventListener('change', renderLibrary);
    $('studio-compare-form').addEventListener('submit', compare);
    $('studio-plan-form').addEventListener('submit', buildPlan);
    $('studio-plan-course').addEventListener('change', renderPlan);
    $('studio-import').addEventListener('click', () => $('studio-import-file').click());
    $('studio-import-file').addEventListener('change', event => {
      importProject(event.target.files[0]).catch(error => notify(error instanceof SyntaxError ? 'This file is not valid project JSON.' : error.message, 'error')).finally(() => { event.target.value = ''; });
    });
    const tabs = [...document.querySelectorAll('[data-studio-tab]')];
    tabs.forEach((button, index) => {
      button.addEventListener('click', () => tab(button.dataset.studioTab));
      button.addEventListener('keydown', event => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        tabs[next].focus(); tab(tabs[next].dataset.studioTab);
      });
    });
    document.addEventListener('sylex:document', () => { clearTimeout(saveTimer); activeId = null; plans = {}; renderLibrary(); });
    document.addEventListener('sylex:results', onResults);
    document.addEventListener('sylex:navigate', event => { if (event.detail.section === 'studio') { refresh().catch(error => status(error.message)); renderPlanCourses(); } });
    refresh().catch(error => { status(error.message); $('studio-projects').replaceChildren(empty('Your browser could not open project storage.', error.message)); });
    renderPlanCourses();
  });
})();
