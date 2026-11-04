/* Pure curriculum operations shared by the studio UI and its tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SylexStudioCore = api;
})(typeof window === 'undefined' ? globalThis : window, () => {
  'use strict';
  const text = value => String(value ?? '').trim();
  const normalize = value => text(value).toLowerCase().replace(/\s+/g, ' ');
  const key = course => normalize(course?.code || course?.title);
  const copy = value => JSON.parse(JSON.stringify(value));
  const details = snapshot => snapshot.courseDetails || [];
  const catalog = snapshot => snapshot.task1?.courses || details(snapshot).map(item => item.course);
  const topicTexts = course => (course?.units || []).flatMap(unit => (unit.topics || []).map(topic => text(topic.text))).filter(Boolean);

  function snapshot(state) {
    if (!state.task1Result && !state.task2Result) throw new Error('Extract a syllabus or open the sample analysis first.');
    const courses = new Map();
    [...Object.values(state.courseCache || {}), state.task2Result].filter(item => item?.course).forEach(item => courses.set(key(item.course), copy(item)));
    return {
      task1: state.task1Result ? copy(state.task1Result) : null,
      courseDetails: [...courses.values()],
      activeCourse: key(state.task2Result?.course),
      source: state.dataSource === 'sample' ? 'sample' : 'document',
      documentName: state.pdfFile?.name || state.task1Result?.document || 'Curriculum workspace',
    };
  }

  function metrics(data) {
    const courses = details(data);
    return {
      courses: catalog(data).length,
      analyzed: courses.length,
      topics: courses.reduce((count, item) => count + topicTexts(item).length, 0),
      outcomes: courses.reduce((count, item) => count + (item.course_outcomes || []).length, 0),
      review: courses.reduce((count, item) => count + (item.not_extracted || []).length, 0),
    };
  }

  function changes(before, after) {
    const left = new Map(before.map(value => [normalize(value), value]));
    const right = new Map(after.map(value => [normalize(value), value]));
    return {
      added: [...right].filter(([id]) => !left.has(id)).map(([, value]) => value),
      removed: [...left].filter(([id]) => !right.has(id)).map(([, value]) => value),
      unchanged: [...right.keys()].filter(id => left.has(id)).length,
    };
  }

  function compare(before, after) {
    const left = new Map(catalog(before).map(course => [key(course), course]));
    const right = new Map(catalog(after).map(course => [key(course), course]));
    const leftDetails = new Map(details(before).map(item => [key(item.course), item]));
    const rightDetails = new Map(details(after).map(item => [key(item.course), item]));
    const common = [...right.keys()].filter(id => left.has(id));
    const compared = common.map(id => {
      const previous = leftDetails.get(id);
      const current = rightDetails.get(id);
      return {
        code: right.get(id).code || '', title: right.get(id).title || '',
        available: Boolean(previous && current),
        metadata: ['title', 'credits', 'lecture', 'tutorial', 'practical'].filter(field => text((previous?.course || left.get(id))[field]) !== text((current?.course || right.get(id))[field])).map(field => ({ field, before: (previous?.course || left.get(id))[field] ?? null, after: (current?.course || right.get(id))[field] ?? null })),
        topics: previous && current ? changes(topicTexts(previous), topicTexts(current)) : null,
        outcomes: previous && current ? changes((previous.course_outcomes || []).map(item => item.text), (current.course_outcomes || []).map(item => item.text)) : null,
      };
    });
    return {
      addedCourses: [...right].filter(([id]) => !left.has(id)).map(([, item]) => item),
      removedCourses: [...left].filter(([id]) => !right.has(id)).map(([, item]) => item),
      courses: compared,
      comparedDetails: compared.filter(item => item.available).length,
      missingDetails: compared.filter(item => !item.available).length,
    };
  }

  // Allocate review sessions from actual topics. Entered session counts are planning
  // preferences; they never become claims about the source document's contact hours.
  function plan(course, count) {
    if (!Number.isInteger(count) || count < 1 || count > 60) throw new Error('Choose between 1 and 60 study sessions.');
    const topics = (course?.units || []).flatMap(unit => (unit.topics || []).filter(topic => text(topic.text)).map(topic => ({ unit: text(unit.title) || `Unit ${unit.number}`, unitNumber: unit.number, topic: text(topic.text), bloom: text(topic.bloom) || 'not specified' })));
    if (!topics.length) throw new Error('This course has no extracted topics. Open a course with topic details first.');
    const size = Math.min(count, topics.length);
    return Array.from({ length: size }, (_, index) => ({
      number: index + 1,
      topics: topics.slice(Math.floor(index * topics.length / size), Math.floor((index + 1) * topics.length / size)),
      completed: false,
    }));
  }

  function validateExport(input) {
    if (!input || input.format !== 'sylex-project' || input.version !== 1) throw new Error('Choose a SYLEX project export (version 1).');
    const data = input.snapshot;
    if (!data || (!data.task1 && !data.courseDetails?.length)) throw new Error('The project has no extracted curriculum data.');
    if (!Array.isArray(data.courseDetails) || data.courseDetails.length > 2000 || (data.task1 && !Array.isArray(data.task1.courses))) throw new Error('The project contains an invalid course catalog.');
    const numeric = value => value === undefined || value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0);
    const reasoningShape = value => {
      if (value._reasoning_summary != null && typeof value._reasoning_summary !== 'string') throw new Error('The project has invalid analysis notes.');
      if (value._debug?.reasoning != null && typeof value._debug.reasoning !== 'string') throw new Error('The project has invalid reasoning metadata.');
      if (value._debug?.scanned_pages && (!Array.isArray(value._debug.scanned_pages) || value._debug.scanned_pages.some(page => !Number.isInteger(page) || page < 1))) throw new Error('The project has invalid source-page metadata.');
    };
    const courseShape = course => {
      if (!course || typeof course !== 'object' || (!text(course.code) && !text(course.title))) throw new Error('A course is missing its identity.');
      if (['code','title','category'].some(field => course[field] != null && typeof course[field] !== 'string')) throw new Error('Course names and codes must be text.');
      if (['lecture','tutorial','practical','credits'].some(field => !numeric(course[field]))) throw new Error('A course has invalid contact hours or credits.');
      if (course.pages && (!Array.isArray(course.pages) || course.pages.some(page => !Number.isInteger(page) || page < 1))) throw new Error('A course contains an invalid source page.');
    };
    catalog(data).forEach(courseShape);
    if (data.task1) {
      reasoningShape(data.task1);
      if (data.task1.document != null && typeof data.task1.document !== 'string') throw new Error('The document name must be text.');
    }
    const blooms = new Set(['remember','understand','apply','analyse','analyze','evaluate','create','unknown','unclassified','']);
    for (const detail of data.courseDetails) {
      courseShape(detail.course);
      reasoningShape(detail);
      for (const field of ['units','course_outcomes','programme_outcomes','books','not_extracted']) {
        if (detail[field] !== undefined && !Array.isArray(detail[field])) throw new Error(`Invalid ${field} data.`);
      }
      for (const unit of detail.units || []) {
        if (!numeric(unit.number) || !numeric(unit.hours) || !Array.isArray(unit.topics)) throw new Error('A unit contains invalid topic or hour data.');
        for (const topic of unit.topics) {
          if (!topic || typeof topic.text !== 'string') throw new Error('A topic is missing its source text.');
          if (!blooms.has(text(topic.bloom))) throw new Error('A topic contains an invalid Bloom level.');
        }
      }
      for (const outcome of detail.course_outcomes || []) if (!blooms.has(text(outcome.bloom))) throw new Error('An outcome contains an invalid Bloom level.');
      for (const book of detail.books || []) {
        if (book.year != null && !/^\d{0,4}$/.test(String(book.year))) throw new Error('A book contains an invalid publication year.');
        if (book.kind != null && !/^[a-z_-]{0,30}$/i.test(book.kind)) throw new Error('A book contains an invalid reference type.');
      }
      for (const row of Object.values(detail.co_po_matrix || {})) {
        if (!row || typeof row !== 'object' || Array.isArray(row) || Object.values(row).some(value => !['1','2','3','S','M','L','H','0',''].includes(String(value)))) throw new Error('The project contains an invalid outcome matrix.');
      }
    }
    const normalized = copy(data);
    if (normalized.task1) normalized.task1.course_count = normalized.task1.courses.length;
    normalized.source = normalized.source === 'sample' ? 'sample' : 'document';
    normalized.documentName = text(normalized.documentName).slice(0, 240) || 'Imported curriculum';
    const plans = {};
    for (const [id, saved] of Object.entries(input.plans || {})) {
      const course = normalized.courseDetails.find(item => key(item.course) === id);
      if (!course || !Array.isArray(saved.sessions) || !saved.sessions.length || saved.sessions.length > 60) continue;
      if (saved.signature !== JSON.stringify(topicTexts(course))) continue;
      plans[id] = {
        title: `${course.course.code || ''} ${course.course.title}`.trim(),
        signature: saved.signature,
        sessions: plan(course, saved.sessions.length).map((session, index) => ({ ...session, completed: saved.sessions[index]?.completed === true })),
        createdAt: new Date().toISOString(),
      };
    }
    return { snapshot: normalized, plans, name: text(input.name).slice(0, 120) || 'Imported curriculum', notes: text(input.notes).slice(0, 20000) };
  }

  return Object.freeze({ snapshot, metrics, compare, plan, validateExport, key, catalog, topicTexts });
});
