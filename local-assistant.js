/* Evidence retrieval and planning without a server or model. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SylexLocalAssistant = api;
})(typeof window === 'undefined' ? globalThis : window, () => {
  'use strict';
  const stop = new Set('the a an is are of for to and in on me please explain describe what how does do about syllabus course topic topics'.split(' '));
  const tokens = text => [...new Set((String(text || '').toLowerCase().match(/[\p{L}\p{N}]+/gu) || []).filter(word => word.length > 1 && !stop.has(word)))];
  function search(query, detail) {
    const terms = tokens(query);
    if (!terms.length) return [];
    const entries = (detail?.units || []).map(unit => ({ label: `Unit ${unit.number}: ${unit.title}`, text: unit.text || (unit.topics || []).map(t => t.text).join('; '), title: unit.title }));
    entries.push(...(detail?.course_outcomes || []).map(outcome => ({ label: outcome.id, text: outcome.text, title: outcome.id })));
    const indexed = entries.map(entry => ({ ...entry, terms: new Set(tokens(`${entry.title} ${entry.text}`)) }));
    return indexed.map(entry => {
      let matched = 0;
      const score = terms.reduce((sum, term) => {
        if (!entry.terms.has(term)) return sum;
        matched++;
        const frequency = indexed.filter(other => other.terms.has(term)).length;
        return sum + Math.log(1 + indexed.length / (frequency + 1)) + (tokens(entry.title).includes(term) ? 1 : 0);
      }, 0);
      return { label: entry.label, text: entry.text, score, coverage: matched / terms.length };
    }).filter(entry => entry.score > 0 && entry.coverage >= .25).sort((a, b) => b.score - a.score).slice(0, 4);
  }
  function roman(value) {
    const values = { I:1, V:5, X:10, L:50, C:100 };
    return [...value.toUpperCase()].reduce((sum, letter, index, letters) => sum + ((values[letter] < values[letters[index+1]]) ? -values[letter] : values[letter]), 0);
  }
  function answer(question, context) {
    const detail = context?.task2;
    if (!detail?.course) return null;
    const q = String(question || '').toLowerCase();
    if (/hint|override|localhost|server|missing|not.extracted|accuracy|bloom|taxonomy|all courses|list.*course|book|reference|outcome|matrix/.test(q)) return null;
    const course = detail.course;
    const source = `Source: ${course.code || course.title}; course page range ${(course.pages || []).join(', ') || 'not recorded'}.`;
    const all = detail.units || [];
    const match = q.match(/\b(?:unit|module|week|chapter|session)\s*(\d+|[ivxlc]+)\b/i);
    const number = match ? (/^\d+$/.test(match[1]) ? Number(match[1]) : roman(match[1])) : null;
    const units = number === null ? all : all.filter(unit => unit.number === number);
    if (number !== null && !units.length) return `Unit ${number} was not found in the extracted course. Check the source and extraction warnings.`;
    if (/\b(plan|schedule|lesson|lecture|revise|revision)\b/.test(q)) {
      const rows = ['Suggested study sequence, based only on extracted topics. Session numbers are planning labels, not prescribed contact hours.', source];
      let session = 0;
      for (const unit of units) {
        rows.push(`\nUnit ${unit.number}: ${unit.title} — ${unit.hours == null ? 'hours not printed' : `${unit.hours} printed hours`}`);
        for (const topic of unit.topics || []) rows.push(`${++session}. ${topic.text}`);
      }
      if (!session) rows.push('No extracted topics are available for a study plan.');
      return rows.join('\n');
    }
    if (/\b(exam|question|quiz|test|assessment)\b/.test(q)) {
      const rows = ['Suggested practice questions — generated templates, not questions printed in the syllabus.', source];
      let number = 0;
      for (const unit of units) for (const topic of (unit.topics || []).slice(0, 3)) rows.push(`${++number}. Explain ${topic.text} (Unit ${unit.number}; topic Bloom: ${topic.bloom || 'unknown'}, ${topic.bloom_source || 'inferred'}).`);
      return rows.join('\n');
    }
    if (match || /\b(units|modules|weeks)\b/.test(q)) return [source, ...units.map(unit => `\nUnit ${unit.number}: ${unit.title}\nHours: ${unit.hours ?? 'not printed'}\n${unit.text || (unit.topics || []).map(t => t.text).join('\n')}`)].join('\n');
    if (/summar|overview|extract|result|credit|hour|structure/.test(q)) return `${course.code || ''} ${course.title}\nCredits: ${course.credits ?? 'not printed'}\nL–T–P: ${course.lecture ?? '?'}–${course.tutorial ?? '?'}–${course.practical ?? '?'}\n${all.length} units; ${(detail.course_outcomes || []).length} course outcomes.\n${source}`;
    const evidence = search(q, detail);
    if (evidence.length) return ['Matching source excerpts (local text search):', source, ...evidence.map(item => `\n${item.label}\n${item.text}`)].join('\n');
    return 'I could not find enough matching evidence in the extracted course to answer that locally. Ask for a printed topic, a unit, a study plan, or extraction gaps. The online assistant can help with broader explanations when internet is available.';
  }
  return Object.freeze({ answer, search });
});
