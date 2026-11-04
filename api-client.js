/* Shared JSON transport. No automatic retries of document uploads or model calls. */
(() => {
  'use strict';
  class APIError extends Error {
    constructor(message, status = 0) { super(message); this.name = 'APIError'; this.status = status; }
  }
  async function request(path, { json, body, signal, timeout = 30000, method, base } = {}) {
    const controller = new AbortController();
    const cancel = () => controller.abort(signal.reason);
    if (signal?.aborted) cancel();
    else signal?.addEventListener('abort', cancel, { once: true });
    const timer = setTimeout(() => controller.abort(new DOMException('The service took too long to respond.', 'TimeoutError')), timeout);
    const origin = String(base || window.STATE?.serverUrl || location.origin).replace(/\/+$/, '');
    try {
      const response = await fetch(`${origin}/api/${path.replace(/^\/api\//, '')}`, {
        method: method || (json !== undefined || body ? 'POST' : 'GET'),
        ...(json !== undefined ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(json) } : { body }),
        signal: controller.signal,
      });
      let data;
      try { data = await response.json(); }
      catch (error) {
        if (controller.signal.aborted) throw controller.signal.reason;
        throw new APIError(`The service returned an unreadable response (HTTP ${response.status}).`, response.status);
      }
      if (!response.ok) throw new APIError(data.error || `Request failed (HTTP ${response.status}).`, response.status);
      return data;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancel);
    }
  }
  window.SylexAPI = Object.freeze({ request, APIError });
})();
