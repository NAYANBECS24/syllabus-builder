/* Browser-local project storage. PDFs are Blobs, never localStorage strings. */
(() => {
  'use strict';
  let database;
  function open() {
    if (!database) database = new Promise((resolve, reject) => {
      const request = indexedDB.open('sylex-studio', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('projects', { keyPath: 'id' });
      request.onsuccess = () => {
        const db = request.result;
        db.onversionchange = () => { db.close(); database = null; };
        resolve(db);
      };
      request.onerror = () => { database = null; reject(new Error('Project storage is unavailable in this browser.')); };
      request.onblocked = () => { database = null; reject(new Error('Close other SYLEX tabs and try opening project storage again.')); };
    });
    return database;
  }
  async function transaction(mode, action) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('projects', mode);
      const request = action(tx.objectStore('projects'));
      tx.oncomplete = () => resolve(request?.result);
      tx.onabort = tx.onerror = () => reject(new Error(tx.error?.name === 'QuotaExceededError' ? 'Browser storage is full. Export a project before removing older copies.' : 'The project could not be stored. Please try again.'));
    });
  }
  window.SylexProjectStore = Object.freeze({
    list: async () => (await transaction('readonly', store => store.getAll())).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    get: id => transaction('readonly', store => store.get(id)),
    put: project => transaction('readwrite', store => store.put(project)),
    remove: id => transaction('readwrite', store => store.delete(id)),
  });
})();
