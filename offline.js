/* Offline workspace: honest capability reporting and content-addressed result replay. */
(() => {
  'use strict';
  const VERSION = 'hybrid-5.0';
  let dbPromise;
  const open = () => dbPromise ||= new Promise((resolve, reject) => {
    const req = indexedDB.open('sylex-offline-results', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('results', { keyPath: 'key' });
    req.onsuccess = () => { req.result.onversionchange = () => { req.result.close(); dbPromise = null; }; resolve(req.result); };
    req.onerror = () => { dbPromise = null; reject(req.error); };
    req.onblocked = () => { dbPromise = null; reject(new Error('Offline storage is blocked by another tab.')); };
  });
  async function cached(key, value) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('results', value ? 'readwrite' : 'readonly');
      const store = tx.objectStore('results');
      const req = value ? store.put({ key, value, saved: Date.now() }) : store.get(key);
      if (value) {
        const all = store.getAll();
        all.onsuccess = () => all.result.sort((a, b) => b.saved - a.saved).slice(40).forEach(row => store.delete(row.key));
      }
      tx.oncomplete = () => resolve(value || req.result?.value);
      tx.onerror = tx.onabort = () => reject(tx.error || new Error('Offline storage failed'));
    });
  }
  async function fingerprint(form) {
    const file = form.get('pdf');
    if (!file || !crypto.subtle) return null;
    const hex = buffer => Array.from(new Uint8Array(buffer), b => b.toString(16).padStart(2, '0')).join('');
    const sha = hex(await crypto.subtle.digest('SHA-256', await file.arrayBuffer()));
    const fields = [...form.entries()].filter(([key]) => key !== 'pdf' && key !== 'api_key').sort(([a], [b]) => a.localeCompare(b));
    return hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify([VERSION, sha, file.name, fields]))));
  }
  async function extract(form, { signal } = {}) {
    signal?.throwIfAborted();
    let key;
    try { key = await fingerprint(form); } catch (_) { /* Extraction works without storage. */ }
    signal?.throwIfAborted();
    const requested = form.get('mode') || 'offline';
    const outgoing = new FormData();
    for (const [name, value] of form) outgoing.append(name, value);
    const localServer = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(new URL(window.STATE?.serverUrl || location.origin).hostname);
    const internetFallback = navigator.onLine === false && localServer && requested === 'online';
    if (internetFallback) outgoing.set('mode', 'offline');
    try {
      let data;
      try {
        data = await window.SylexAPI.request('extract', { body: outgoing, signal, timeout: 120000 });
      } catch (error) {
        // An HTTP server error can be retried locally; user cancellation and input
        // validation errors are never retried or replaced with previous data.
        if (requested !== 'online' || !(error.status >= 500) || signal?.aborted) throw error;
        outgoing.set('mode', 'offline');
        data = await window.SylexAPI.request('extract', { body: outgoing, signal, timeout: 120000 });
        data._processing = { ...data._processing, requested_mode: requested, fallback: true, reason: 'Cloud failed; processed with the local engine.' };
      }
      signal?.throwIfAborted();
      if (internetFallback) data._processing = { ...data._processing, requested_mode: requested, fallback: true, reason: 'Internet unavailable; processed with the local engine.' };
      if (!data || data.error || (!Array.isArray(data.courses) && !('course' in data))) throw new Error('The extraction service returned no valid result.');
      if (key) {
        try { await cached(key, data); }
        catch (_) { window.toast?.('Extraction succeeded, but an offline copy could not be saved. Export the result or save a project.', 'info'); }
      }
      signal?.throwIfAborted();
      return data;
    } catch (error) {
      if (signal?.aborted || error.name === 'AbortError' || (error.status && error.status < 500)) throw error;
      let saved;
      if (key) { try { saved = await cached(key); } catch (_) {} }
      signal?.throwIfAborted();
      if (saved) return { ...saved, _processing: { ...saved._processing, cached: true, reason: 'Service unavailable. Showing a saved extraction of this exact document and request.' } };
      throw new Error(`${error.message} For new extraction without internet, run python run.py on this computer and open http://localhost:7823. Saved Studio projects remain available.`);
    }
  }
  let shellReady = false;
  function updateStatus() {
    const panel = document.getElementById('offline-readiness');
    if (!panel) return;
    const local = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
    panel.textContent = `${navigator.onLine === false ? 'Internet connection lost. ' : ''}${shellReady ? 'Workspace cached for offline reopening. ' : 'Preparing offline workspace. '}${local ? 'Keep the local server running for new extraction. Projects, study plans and local chat work without internet.' : 'Saved projects work offline. New document extraction without internet requires the local app at localhost:7823.'}`;
  }
  window.SylexOffline = Object.freeze({ extract, fingerprint });
  window.addEventListener('online', () => { updateStatus(); window.checkServer?.(true); });
  window.addEventListener('offline', () => { updateStatus(); window.checkServer?.(true); });
  document.addEventListener('DOMContentLoaded', async () => {
    updateStatus();
    if ('serviceWorker' in navigator && window.isSecureContext) {
      try {
        await navigator.serviceWorker.register('./service-worker.js');
        await navigator.serviceWorker.ready;
        shellReady = true; updateStatus();
      } catch (_) {
        const panel = document.getElementById('offline-readiness');
        if (panel) panel.textContent = 'Offline page caching is unavailable. The local app still works without internet while its server is running.';
      }
    }
  });
})();
