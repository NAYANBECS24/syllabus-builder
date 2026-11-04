const {test}=require('node:test');
const assert=require('node:assert/strict');
const assistant=require('../local-assistant.js');
const detail={course:{code:'BIO101',title:'Ecology',pages:[2,3],credits:null},units:[
 {number:1,title:'Habitats',hours:null,text:'Forest habitats support biodiversity.',topics:[{text:'Forest habitats',bloom:'understand',bloom_source:'inferred'}]},
 {number:12,title:'Populations',hours:2,text:'Population dynamics and migration.',topics:[{text:'Population dynamics'}]}
],course_outcomes:[]};
test('local retrieval finds partial topic matches with source excerpts',()=>{
 const hits=assistant.search('Explain forest biodiversity',detail);
 assert.equal(hits[0].label,'Unit 1: Habitats');
 assert.match(assistant.answer('explain forest biodiversity',{task2:detail}),/page range 2, 3/);
});
test('plans cover every topic without inventing hours',()=>{
 const answer=assistant.answer('make a lesson plan',{task2:detail});
 assert.match(answer,/hours not printed/); assert.match(answer,/Population dynamics/); assert.doesNotMatch(answer,/45-Hour|9 Hours/);
});
test('large and Roman unit numbers select only that unit',()=>{
 for(const query of ['explain unit 12','explain module XII']) {
  const answer=assistant.answer(query,{task2:detail}); assert.match(answer,/migration/); assert.doesNotMatch(answer,/Forest habitats/);
 }
});
test('unmatched questions and missing metadata never create facts',()=>{
 assert.match(assistant.answer('quantum gravity',{task2:detail}),/not find enough matching evidence/);
 assert.match(assistant.answer('course credits',{task2:detail}),/not printed/);
 assert.equal(assistant.answer('hello',{}),null);
});
