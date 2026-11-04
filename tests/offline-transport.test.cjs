const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const {webcrypto}=require('node:crypto');
function setup(request, online=true) {
 const context={window:{STATE:{serverUrl:'http://localhost:7823'},SylexAPI:{request},addEventListener:()=>{}},document:{addEventListener:()=>{}},navigator:{onLine:online},location:{origin:'http://localhost:7823'},crypto:webcrypto,URL,FormData,TextEncoder,Uint8Array,indexedDB:{open:()=>{throw new Error('Storage disabled')}},console};
 vm.runInNewContext(fs.readFileSync('offline.js','utf8'),context);
 return context.window.SylexOffline;
}
function form(mode='offline'){const f=new FormData();f.append('pdf',new File(['CS101 TEST SYLLABUS'],'test.txt'));f.append('mode',mode);return f;}
test('internet loss sends a local request and marks its actual processing mode',async()=>{
 const api=setup(async(path,{body})=>{assert.equal(body.get('mode'),'offline');return {courses:[],_processing:{used_mode:'offline'}}},false);
 const result=await api.extract(form('online'));assert.equal(result._processing.fallback,true);assert.match(result._processing.reason,/Internet unavailable/);
});
test('server failure retries cloud extraction locally with accurate provenance',async()=>{
 let calls=0;const api=setup(async(path,{body})=>{calls++;if(calls===1)throw Object.assign(new Error('Cloud failed'),{status:503});assert.equal(body.get('mode'),'offline');return {courses:[]}});
 const result=await api.extract(form('online'));assert.equal(calls,2);assert.match(result._processing.reason,/Cloud failed/);
});
test('validation errors and cancellation never become successful cached results',async()=>{
 let calls=0;const api=setup(async()=>{calls++;throw Object.assign(new Error('Invalid file'),{status:422})});
 await assert.rejects(api.extract(form('online')),e=>e.status===422);assert.equal(calls,1);
 const controller=new AbortController();controller.abort();await assert.rejects(api.extract(form(),{signal:controller.signal}),e=>e.name==='AbortError');assert.equal(calls,1);
});
test('document digest includes content and extraction settings',async()=>{
 const api=setup(()=>{});const first=form();const changed=form();changed.set('course','CS101');
 assert.notEqual(await api.fingerprint(first),await api.fingerprint(changed));
 changed.delete('course');changed.set('pdf',new File(['different contents'],'test.txt'));
 assert.notEqual(await api.fingerprint(first),await api.fingerprint(changed));
});
