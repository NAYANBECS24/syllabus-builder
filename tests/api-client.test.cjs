const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function client(fetch){const context={window:{STATE:{serverUrl:'http://localhost:7823/'}},location:{origin:'http://localhost:7823'},fetch,AbortController,DOMException,setTimeout,clearTimeout};vm.runInNewContext(fs.readFileSync('api-client.js','utf8'),context);return context.window.SylexAPI;}
test('posts JSON and preserves server validation errors',async()=>{
 const api=client(async(url,options)=>{assert.equal(url,'http://localhost:7823/api/chat');assert.equal(JSON.parse(options.body).message,'hello');return {ok:false,status:400,json:async()=>({error:'Context is invalid'})}});
 await assert.rejects(api.request('chat',{json:{message:'hello'}}),e=>e.status===400&&e.message==='Context is invalid');
});
test('reports non-JSON responses without hiding their HTTP status',async()=>{
 const api=client(async()=>({ok:false,status:502,json:async()=>{throw new SyntaxError('html')}}));
 await assert.rejects(api.request('status'),e=>e.status===502);
});
test('caller cancellation reaches the underlying request',async()=>{
 const api=client(async(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason))));
 const controller=new AbortController();const pending=api.request('chat',{signal:controller.signal});controller.abort();
 await assert.rejects(pending,e=>e.name==='AbortError');
});
test('deadline aborts a stalled request',async()=>{
 const api=client(async(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason))));
 await assert.rejects(api.request('status',{timeout:10}),e=>e.name==='TimeoutError');
});
