from pathlib import Path

def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)

p = Path('background.js')
s = p.read_text(encoding='utf-8')

s = once(s,
"""  const data = await chrome.storage.local.get([VERSION_KEY, STATE_KEY]);
  const prior = data[VERSION_KEY] || previousVersionHint || null;
""",
"""  const data = await chrome.storage.local.get([VERSION_KEY, STATE_KEY, WORKER_TAB_KEY]);
  const prior = data[VERSION_KEY] || previousVersionHint || null;
""",
'version state read')

s = once(s,
"""  if (prior) {
    workerTabId = null;
    await chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
""",
"""  if (prior) {
    const staleWorkerTabId = data[WORKER_TAB_KEY];
    if (Number.isInteger(staleWorkerTabId)) {
      try { await chrome.tabs.remove(staleWorkerTabId); } catch (_) {}
    }
    workerTabId = null;
    await chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
""",
'close stale worker tab')

s = once(s,
"""  if (tab.id === workerTabId) return { ok: true, ignored: 'worker-tab' };
  const settings = await getSettings();
""",
"""  if (tab.id === workerTabId) return { ok: true, ignored: 'worker-tab' };
  // A page-ready signal from the user's active Amazon tab can arrive while this service worker is
  // already executing a crawl job. That currentJob is live, not interrupted, so never reconstruct
  // or requeue it from Auto-start while the in-memory serial lock is held.
  if (processing) return { ok: true, ignored: 'crawler-already-processing' };
  const settings = await getSettings();
""",
'auto-start in-flight guard')

s = once(s,
"""  if (!restart && state.crawl.active) {
    if (source === 'auto-amazon' && state.crawl.manualStop) return state;
    const alreadyRunning = !state.paused && state.running && !state.currentJob && state.queue.length > 0;
""",
"""  if (!restart && state.crawl.active) {
    if (source === 'auto-amazon' && state.crawl.manualStop) return state;
    // In the same live service worker, an in-memory processing=true means currentJob is genuinely
    // in flight. Resume must not reinterpret it as stale. After a browser/service-worker restart
    // processing is false, so persisted currentJob recovery still works exactly as intended.
    if (processing && !state.paused) return state;
    const alreadyRunning = !state.paused && state.running && !state.currentJob && state.queue.length > 0;
""",
'manual resume in-flight guard')

p.write_text(s, encoding='utf-8')

# Strengthen static regressions.
t = Path('background-test.js')
x = t.read_text(encoding='utf-8')
marker = "console.log('v0.18.14 durable resume/autostart background regressions passed');"
insert = """assert(backgroundSourceV01814.includes("ignored: 'crawler-already-processing'") && backgroundSourceV01814.includes('if (processing && !state.paused) return state;'), 'Auto-start/manual resume must not requeue an in-flight currentJob in the same service worker');
assert(backgroundSourceV01814.includes('const staleWorkerTabId = data[WORKER_TAB_KEY]') && backgroundSourceV01814.includes('await chrome.tabs.remove(staleWorkerTabId)'), 'version migration must close an orphaned old worker tab before clearing its transient identity');
"""
if marker not in x:
    raise RuntimeError('v0.18.14 background test marker not found')
x = x.replace(marker, insert + marker, 1)
t.write_text(x, encoding='utf-8')

print('v0.18.14 resume race hardening applied')
