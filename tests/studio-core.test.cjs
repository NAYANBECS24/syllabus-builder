const { test } = require('node:test');
const assert = require('node:assert/strict');
const core = require('../studio-core.js');

const course = (topics = ['Binary search trees', 'Tree traversal'], code = 'CS101') => ({
  course: { code, title: 'Data structures', credits: 3, lecture: 3, tutorial: 0, practical: 0, pages: [1] },
  units: [{ number: 1, title: 'Trees', hours: 9, topics: topics.map((text, index) => ({ id: `u1t${index}`, text, bloom: 'understand' })) }],
  course_outcomes: [{ id: 'CO1', text: 'Explain tree operations', bloom: 'understand' }],
  books: [], programme_outcomes: [], not_extracted: [], co_po_matrix: {},
});
const snapshot = details => ({ task1: { document: 'test.pdf', course_count: details.length, courses: details.map(item => item.course) }, courseDetails: details, documentName: 'test.pdf', source: 'document' });

test('a saved snapshot deduplicates course aliases without retaining mutable state', () => {
  const detail = course();
  const state = { task1Result: { courses: [detail.course], course_count: 1 }, task2Result: detail, courseCache: { CS101: detail, 'DATA STRUCTURES': detail }, pdfFile: { name: 'source.pdf' } };
  const saved = core.snapshot(state);
  detail.units[0].topics[0].text = 'Changed later';
  assert.equal(saved.courseDetails.length, 1);
  assert.equal(saved.courseDetails[0].units[0].topics[0].text, 'Binary search trees');
  assert.equal(core.metrics(saved).topics, 2);
  assert.throws(() => core.snapshot({}), /Extract a syllabus/);
});

test('edition comparison matches course identity and exposes actual added/removed evidence', () => {
  const before = snapshot([course(['Binary search trees', 'Tree traversal'])]);
  const after = snapshot([course([' Binary  search trees ', 'AVL rotations']), course(['Hashing'], 'CS102')]);
  after.courseDetails[0].course.credits = 4;
  const report = core.compare(before, after);
  assert.equal(report.addedCourses[0].code, 'CS102');
  assert.deepEqual(report.courses[0].topics.added, ['AVL rotations']);
  assert.deepEqual(report.courses[0].topics.removed, ['Tree traversal']);
  assert.equal(report.courses[0].topics.unchanged, 1);
  assert.equal(report.courses[0].metadata[0].field, 'credits');
});

test('missing extraction details never become claims of removed topics', () => {
  const before = snapshot([course()]);
  const after = { ...snapshot([course()]), courseDetails: [] };
  const report = core.compare(before, after);
  assert.equal(report.comparedDetails, 0);
  assert.equal(report.missingDetails, 1);
  assert.equal(report.courses[0].topics, null);
});

test('planning preserves every source topic exactly once in order', () => {
  const source = course(['A', 'B', 'C', 'D', 'E']);
  const sessions = core.plan(source, 3);
  assert.equal(sessions.length, 3);
  assert.deepEqual(sessions.flatMap(session => session.topics.map(topic => topic.topic)), ['A', 'B', 'C', 'D', 'E']);
  assert.equal(core.plan(source, 60).length, 5);
  assert.throws(() => core.plan(source, 0), /between 1 and 60/);
  assert.throws(() => core.plan(course([]), 3), /no extracted topics/);
});

test('import validates render-sensitive fields and recomputes catalog counts', () => {
  const input = { format: 'sylex-project', version: 1, snapshot: snapshot([course()]), name: 'Edition A' };
  input.snapshot.task1.course_count = '<img src=x>';
  assert.equal(core.validateExport(input).snapshot.task1.course_count, 1);
  input.snapshot.courseDetails[0].units[0].topics[0].bloom = '" onclick="alert(1)';
  assert.throws(() => core.validateExport(input), /invalid Bloom/);
  assert.throws(() => core.validateExport({ format: 'something-else' }), /SYLEX project export/);
});

test('portable exports restore plan progress from verified source topics', () => {
  const source = course();
  const id = core.key(source.course);
  const sessions = core.plan(source, 2); sessions[0].completed = true;
  const input = { format: 'sylex-project', version: 1, snapshot: snapshot([source]), plans: { [id]: { signature: JSON.stringify(core.topicTexts(source)), sessions } } };
  const imported = core.validateExport(input);
  assert.equal(imported.plans[id].sessions[0].completed, true);
  input.plans[id].signature = 'stale';
  assert.deepEqual(core.validateExport(input).plans, {});
});
