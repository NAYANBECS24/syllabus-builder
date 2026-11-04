const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function context(){const c={window:{STATE:{}},document:{getElementById:()=>null,addEventListener:()=>{}},localStorage:{getItem:()=>null},console};vm.createContext(c);vm.runInContext(fs.readFileSync('chat.js','utf8'),c);return c;}
test('clearing document context produces no course suggestions',()=>{const c=context();assert.equal(vm.runInContext('analyzAndSuggest(null).length',c),0);assert.doesNotThrow(()=>vm.runInContext('updateContextPanel(null)',c));});
test('local assistant never invents a sample course in an empty session',()=>{const c=context();const answer=vm.runInContext("respond('List all courses')",c);assert.match(answer,/No extraction loaded/);assert.doesNotMatch(answer,/CS23301/);});
