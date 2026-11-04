"""Optional browser regression: pip install playwright; playwright install chromium."""
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
import sylex_server as server


def main():
    with tempfile.TemporaryDirectory() as folder:
        os.environ['SYLEX_CACHE_DIR'] = str(Path(folder) / 'cache')
        http = server.SylexHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{http.server_port}'
        fixture = Path(folder) / 'offline-syllabus.txt'
        fixture.write_text('CS101 DATA STRUCTURES\nCOURSE OBJECTIVES:\nUnderstand data structures.\nUNIT I TREES 9\nBinary trees and traversal.\nUNIT II SORTING 6\nMerge sort and quick sort.\nCOURSE OUTCOMES:\nCO1 Explain tree traversal. K2', encoding='utf-8')
        try:
            with sync_playwright() as playwright:
                bundled = Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright'
                executables = sorted(bundled.glob('chromium-*/chrome-win64/chrome.exe'))
                browser = playwright.chromium.launch(headless=True, **({'executable_path': str(executables[-1])} if executables else {}))
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                # Block external network while allowing the loopback engine.
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin) else route.abort())
                page.goto(origin, wait_until='domcontentloaded')
                page.evaluate('(origin) => { window.STATE.serverUrl = origin; document.getElementById("server-url").value = origin; }', origin)
                page.evaluate('navigator.serviceWorker.ready')
                page.wait_for_function('navigator.serviceWorker.controller !== null')
                page.evaluate("navigate('extract')")
                page.locator('#file-input').set_input_files(str(fixture))
                page.locator('#btn-run').click()
                page.wait_for_function('window.STATE.task1Result?.course_count === 1')
                page.evaluate('loadTask2ForCourse(window.STATE.task1Result.courses[0])')
                page.wait_for_function('window.STATE.task2Result?.units.length === 2')
                assert page.evaluate('window.STATE.task2Result.course.code') == 'CS101'
                assert page.evaluate("window.SylexLocalAssistant.answer('explain binary trees', {task2:window.STATE.task2Result})").find('traversal') >= 0
                # Exercise the real HTTP online pipeline, using a deterministic
                # provider fixture to keep this regression independent of internet.
                with patch.object(server, 'DEFAULT_NVIDIA_API_KEY', 'test-only'), patch('cloud_models.CloudModels.complete', return_value=({'courses': []}, 'browser-fixture-model')):
                    page.evaluate("async () => { setMode('online'); window.STATE.courseCache = {}; await loadTask2ForCourse(window.STATE.task1Result.courses[0]); }")
                assert page.evaluate("window.STATE.task2Result._processing.used_mode") == 'online'
                assert page.locator('#online-review').is_visible()
                page.locator('#online-review-summary').click()
                assert 'browser-fixture-model' in page.locator('#online-review-content').inner_text()
                page.evaluate("navigate('studio')")
                page.locator('#studio-save-current').click()
                page.locator('#studio-project-name').fill('Offline regression project')
                page.locator('#studio-project-submit').click()
                page.wait_for_function("!document.getElementById('studio-project-dialog').open")
                # True browser-offline: even loopback fetches fail. Reopen the cached
                # shell, restore the saved Blob and replay this exact extraction.
                context.set_offline(True)
                page.reload(wait_until='domcontentloaded')
                page.evaluate('(origin) => { window.STATE.serverUrl = origin; document.getElementById("server-url").value = origin; }', origin)
                page.evaluate("navigate('studio')")
                page.get_by_role('button', name='Offline regression project', exact=True).click()
                page.wait_for_function("window.STATE.task2Result?.course.code === 'CS101'")
                assert page.evaluate('window.STATE.pdfFile.name') == fixture.name
                result = page.evaluate("""async () => {
                  const form = new FormData(); form.append('pdf', window.STATE.pdfFile); form.append('mode', 'offline');
                  return await window.SylexOffline.extract(form);
                }""")
                assert result['_processing']['cached'] is True
                assert result['course_count'] == 1
                awaitable = page.evaluate("""async () => {
                  const form = new FormData(); form.append('pdf', new File(['A different document'], 'different.txt')); form.append('mode','offline');
                  try { await window.SylexOffline.extract(form); return false; } catch (e) { return e.message.includes('localhost:7823'); }
                }""")
                assert awaitable, 'A new file must not receive another document\'s cached result'
                for width in [390, 1440]:
                    page.set_viewport_size({'width': width, 'height': 900})
                    for section in ['extract', 'results', 'studio', 'chat']:
                        page.evaluate('(section) => navigate(section)', section)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), f'{section} overflows at {width}'
                assert not errors, errors
                context.set_offline(False)
                page.evaluate("navigate('extract')")
                # Simulate OS internet loss while loopback remains reachable.
                page.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => false, configurable: true})")
                result = page.evaluate("""async () => {
                  const form = new FormData(); form.append('pdf', window.STATE.pdfFile); form.append('mode','online');
                  return await window.SylexOffline.extract(form);
                }""")
                assert result['_processing']['used_mode'] == 'offline'
                assert result['_processing']['fallback'] is True
                browser.close()
                print('PASS: local extraction; online HTTP pipeline and coverage UI; offline reload; saved project/source restoration; exact result replay; wrong-document rejection; mobile layout; automatic offline fallback.')
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    main()
