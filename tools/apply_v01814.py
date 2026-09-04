from pathlib import Path
import json

R = Path('.')
def read(path): return (R / path).read_text(encoding='utf-8')
def write(path, text): (R / path).write_text(text, encoding='utf-8')
def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)

# ---------------- background.js ----------------
b = read('background.js')
old_version_fn = """const DEV_RESET_ON_VERSION_CHANGE = true;
const MAX_WORKFLOW_EVENTS = 1600;
let workflowRecorderEnabled = false;

let processing = false;
let workerTabId = null;

async function ensureDevelopmentVersionState(previousVersionHint = null) {
  const version = chrome.runtime?.getManifest?.()?.version || null;
  if (!version) return { changed: false, version: null };
  const data = await chrome.storage.local.get([VERSION_KEY]);
  const prior = data[VERSION_KEY] || previousVersionHint || null;
  if (prior === version) return { changed: false, version };
  if (DEV_RESET_ON_VERSION_CHANGE && prior) {
    await chrome.storage.local.remove([
      LEDGER_KEY, STATE_KEY, WORKER_TAB_KEY, WORKFLOW_LOG_KEY,
      'lastBankVerificationRequest', 'lastBankVerificationImport'
    ]);
    workerTabId = null;
  }
  await chrome.storage.local.set({ [VERSION_KEY]: version });
  return { changed: Boolean(prior && prior !== version), previousVersion: prior, version };
}
"""
new_version_fn = """const MAX_WORKFLOW_EVENTS = 1600;
let workflowRecorderEnabled = false;

let processing = false;
let workerTabId = null;

async function ensureDevelopmentVersionState(previousVersionHint = null) {
  const version = chrome.runtime?.getManifest?.()?.version || null;
  if (!version) return { changed: false, version: null };
  const data = await chrome.storage.local.get([VERSION_KEY, STATE_KEY]);
  const prior = data[VERSION_KEY] || previousVersionHint || null;
  if (prior === version) return { changed: false, version };

  // v0.18.14 ends destructive development-version resets for canonical ledger/crawl state.
  // A version update may invalidate a transient Chrome tab ID, but it must not erase the exact
  // lifetime-crawl checkpoint or hundreds of already completed canonical orders.
  if (prior) {
    workerTabId = null;
    await chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
    if (data[STATE_KEY]) {
      const migrated = ensureCrawl({ ...defaultState(), ...data[STATE_KEY] });
      migrated.running = false;
      migrated.crawl.lastMigrationAt = nowIso();
      migrated.crawl.lastMigrationFrom = String(prior);
      migrated.crawl.lastMigrationTo = String(version);
      await chrome.storage.local.set({ [STATE_KEY]: migrated });
    }
  }
  await chrome.storage.local.set({ [VERSION_KEY]: version });
  return { changed: Boolean(prior && prior !== version), previousVersion: prior, version, preservedState: Boolean(prior) };
}
"""
b = once(b, old_version_fn, new_version_fn, 'version migration')

b = once(b,
"""      seenOrders: {}, seenPages: {}, completedOrders: {}, overlapCount: 0, overlapExamples: [],
      pagesCompleted: 0, ordersCompleted: 0, lastCompletedOrderId: null, lastCompletedAt: null,
      startedAt: null, completedAt: null
""",
"""      seenOrders: {}, seenPages: {}, completedOrders: {}, overlapCount: 0, overlapExamples: [], overlapRefreshedOrders: {},
      pagesCompleted: 0, ordersCompleted: 0, lastCompletedOrderId: null, lastCompletedAt: null,
      startedAt: null, completedAt: null,
      manualStop: false, lastResumeAt: null, lastResumeSource: null, resumeCount: 0,
      resumePageKey: null, resumeExpectedFingerprint: null, resumeObservedFingerprint: null,
      resumeFingerprintMatched: null, lastRecoveredJobKey: null, lastResumeOverlapError: null,
      lastMigrationAt: null, lastMigrationFrom: null, lastMigrationTo: null
""",
'default resume state')

b = once(b,
"""  state.crawl.completedOrders = state.crawl.completedOrders || {};
  state.crawl.overlapExamples = Array.isArray(state.crawl.overlapExamples) ? state.crawl.overlapExamples.slice(-50) : [];
  return state;
""",
"""  state.crawl.completedOrders = state.crawl.completedOrders || {};
  state.crawl.overlapRefreshedOrders = state.crawl.overlapRefreshedOrders || {};
  state.crawl.overlapExamples = Array.isArray(state.crawl.overlapExamples) ? state.crawl.overlapExamples.slice(-50) : [];
  state.crawl.manualStop = Boolean(state.crawl.manualStop);
  state.crawl.resumeCount = Number.isFinite(Number(state.crawl.resumeCount)) ? Number(state.crawl.resumeCount) : 0;
  return state;
""",
'ensure resume state')

b = once(b,
"""    autoHistoryCrawl: true,
    showUpdateToast: true,
    workflowRecorderEnabled: false,
""",
"""    autoHistoryCrawl: true,
    autoStartOnAmazon: false,
    showUpdateToast: true,
    workflowRecorderEnabled: false,
""",
'background auto-start default')

resume_helpers = r'''
function crawlCheckpointPageKey(crawl) {
  const year = Number(crawl?.currentYear);
  const page = Math.max(1, Number(crawl?.currentPage) || 1);
  return Number.isFinite(year) ? `${year}:${page}` : null;
}

function recoverInterruptedCurrentJob(state, source = 'resume') {
  const job = state?.currentJob || null;
  if (!job) return false;
  const key = jobKey(job);
  if (!state.queue.some(candidate => jobKey(candidate) === key)) {
    state.queue.unshift({ ...job, queuedAt: nowIso(), resumeRecovered: true, resumeSource: source });
  }
  state.currentJob = null;
  state.crawl.lastRecoveredJobKey = key;
  return true;
}

function reconstructActiveCrawl(state, source = 'manual-resume', { clearManualStop = true } = {}) {
  state = ensureCrawl(state);
  const crawl = state.crawl;
  if (!crawl.active) return state;
  if (clearManualStop) crawl.manualStop = false;
  if (crawl.manualStop) return state;

  const resumedAt = nowIso();
  const recoveredCurrent = recoverInterruptedCurrentJob(state, source);
  if (!state.queue.length) {
    const year = Number(crawl.currentYear);
    const page = Math.max(1, Number(crawl.currentPage) || 1);
    if (!Number.isFinite(year)) throw new Error('Active crawl checkpoint is missing its current year');
    const pageKey = `${year}:${page}`;
    const url = crawl.currentHistoryUrl || buildHistoryUrl('https://www.amazon.com/gp/your-account/order-history', year, page);
    const expectedFingerprint = crawl.seenPages?.[pageKey] || (crawl.currentPageOrderIds || []).join('|') || null;
    state.queue.push({
      type: 'history', url, historyYear: year, historyPage: page,
      crawlManaged: true, source: `resume:${source}`, priority: 1, queuedAt: resumedAt, attempts: 0,
      resumeRecovery: true, resumeExpectedFingerprint: expectedFingerprint, resumePageKey: pageKey
    });
    crawl.resumePageKey = pageKey;
    crawl.resumeExpectedFingerprint = expectedFingerprint;
    crawl.phase = 'resume';
  }
  crawl.lastResumeAt = resumedAt;
  crawl.lastResumeSource = source;
  crawl.resumeCount = Number(crawl.resumeCount || 0) + 1;
  if (recoveredCurrent && !crawl.resumePageKey) crawl.resumePageKey = crawlCheckpointPageKey(crawl);
  state.paused = false;
  state.running = state.queue.length > 0;
  sortQueue(state.queue);
  return state;
}

async function resumePersistedCrawl(source = 'browser-startup') {
  let state = ensureCrawl(await getState());
  if (!state.crawl.active || state.paused || state.crawl.manualStop) return state;
  state = reconstructActiveCrawl(state, source, { clearManualStop: false });
  await setState(state);
  if (state.queue.length) scheduleSoon(randomBetween(250, 700));
  return state;
}

async function handleAmazonUserPageReady(sender) {
  const tab = sender?.tab || null;
  if (!tab || !Number.isInteger(tab.id) || tab.active !== true) return { ok: true, ignored: 'inactive-tab' };
  if (tab.id === workerTabId) return { ok: true, ignored: 'worker-tab' };
  const settings = await getSettings();
  if (!settings.autoStartOnAmazon) return { ok: true, ignored: 'auto-start-disabled' };
  const state = ensureCrawl(await getState());
  if (state.crawl.manualStop) return { ok: true, ignored: 'manual-stop' };
  if (state.crawl.phase === 'done' && !state.crawl.active) return { ok: true, ignored: 'lifetime-scan-complete' };
  if (state.crawl.active && state.paused) return { ok: true, ignored: 'paused-error-or-user-stop' };
  const resumed = await startOrResumeFullScan({ restart: false, source: 'auto-amazon' });
  return { ok: true, autoStarted: true, state: resumed };
}

'''
b = once(b, 'async function startOrResumeFullScan({ restart = false, startYear = null } = {}) {', resume_helpers + "async function startOrResumeFullScan({ restart = false, startYear = null, source = 'manual' } = {}) {", 'insert resume helpers')

old_start = """  const state = ensureCrawl(await getState());
  if (!restart && state.crawl.active && (state.queue.length || state.currentJob)) {
    state.paused = false;
    state.running = true;
    await setState(state);
    scheduleSoon(randomBetween(500, 1200));
    return state;
  }

  const year = Number(startYear) || new Date().getFullYear();
"""
new_start = """  let state = ensureCrawl(await getState());
  if (!restart && state.crawl.active) {
    if (source === 'auto-amazon' && state.crawl.manualStop) return state;
    const alreadyRunning = !state.paused && state.running && !state.currentJob && state.queue.length > 0;
    if (source === 'auto-amazon' && alreadyRunning) return state;
    state = reconstructActiveCrawl(state, source, { clearManualStop: source !== 'auto-amazon' });
    await setState(state);
    if (state.queue.length) scheduleSoon(randomBetween(250, 700));
    return state;
  }
  if (!restart && source === 'auto-amazon' && state.crawl.phase === 'done') return state;

  const year = Number(startYear) || new Date().getFullYear();
"""
b = once(b, old_start, new_start, 'start resume branch')
b = once(b,
"""    startedAt: nowIso()
  };
""",
"""    startedAt: nowIso(),
    manualStop: false,
    lastResumeSource: source
  };
""",
'new crawl manual stop')

# Resume fingerprint diagnostics and overlap refresh.
b = once(b,
"""  const pageKey = `${year}:${page}`;
  const fingerprint = pageOrderIds.join('|');
  const previousFingerprint = crawl.seenPages[pageKey];
""",
"""  const pageKey = `${year}:${page}`;
  const fingerprint = pageOrderIds.join('|');
  const previousFingerprint = crawl.seenPages[pageKey];
  if (job?.resumeRecovery) {
    crawl.resumePageKey = pageKey;
    crawl.resumeObservedFingerprint = fingerprint;
    crawl.resumeFingerprintMatched = !job.resumeExpectedFingerprint || job.resumeExpectedFingerprint === fingerprint;
  }
""",
'resume fingerprint diagnostics')

old_detail_loop = """  const existingKeys = new Set(state.queue.map(jobKey));
  if (state.currentJob) existingKeys.add(jobKey(state.currentJob));
  let seq = 0;
  for (const link of orderedLinks) {
    seq += 1;
    // A duplicate order ID on a later history page is not detail-scanned again during the same
    // lifetime run. It is counted as overlap and the first capture remains authoritative.
    if (crawl.completedOrders[link.orderId]) continue;
    const detailJob = {
      type: 'detail', orderId: link.orderId, url: normalizeUrl(link.url) || link.url,
      source: `crawl ${pageKey}`, crawlManaged: true, crawlYear: year, crawlPage: page,
      crawlPageKey: pageKey, historyUrl: crawl.currentHistoryUrl, sequence: seq,
      priority: 5, queuedAt: nowIso(), attempts: 0
    };
    const key = jobKey(detailJob);
    if (!existingKeys.has(key)) { state.queue.push(detailJob); existingKeys.add(key); }
  }
"""
new_detail_loop = """  const existingKeys = new Set(state.queue.map(jobKey));
  if (state.currentJob) existingKeys.add(jobKey(state.currentJob));
  crawl.overlapRefreshedOrders = crawl.overlapRefreshedOrders || {};
  let seq = 0;
  for (const link of orderedLinks) {
    seq += 1;
    const firstSeen = crawl.seenOrders?.[link.orderId] || null;
    const alreadyComplete = Boolean(crawl.completedOrders[link.orderId]);
    const crossPageOverlap = Boolean(alreadyComplete && firstSeen?.pageKey && firstSeen.pageKey !== pageKey);
    const resumeDuplicate = Boolean(alreadyComplete && job?.resumeRecovery);
    if (alreadyComplete) {
      // A known Order ID is an anchor, not a reason to restart history. Refresh it once when it
      // proves the recovered/shifted page overlaps prior work, then continue without incrementing
      // lifetime completion or repeatedly hitting the same order during fallback navigation.
      if ((resumeDuplicate || crossPageOverlap) && !crawl.overlapRefreshedOrders[link.orderId]) {
        const refreshJob = {
          type: 'detail', orderId: link.orderId, url: normalizeUrl(link.url) || link.url,
          source: `resume-overlap ${pageKey}`, crawlManaged: true, resumeOverlapRefresh: true,
          crawlYear: year, crawlPage: page, crawlPageKey: pageKey, historyUrl: crawl.currentHistoryUrl,
          sequence: seq, priority: 5, queuedAt: nowIso(), attempts: 0
        };
        const refreshKey = jobKey(refreshJob);
        if (!existingKeys.has(refreshKey)) { state.queue.push(refreshJob); existingKeys.add(refreshKey); }
        crawl.overlapRefreshedOrders[link.orderId] = { queuedAt: nowIso(), pageKey };
      }
      continue;
    }
    const detailJob = {
      type: 'detail', orderId: link.orderId, url: normalizeUrl(link.url) || link.url,
      source: `crawl ${pageKey}`, crawlManaged: true, crawlYear: year, crawlPage: page,
      crawlPageKey: pageKey, historyUrl: crawl.currentHistoryUrl, sequence: seq,
      priority: 5, queuedAt: nowIso(), attempts: 0
    };
    const key = jobKey(detailJob);
    if (!existingKeys.has(key)) { state.queue.push(detailJob); existingKeys.add(key); }
  }
"""
b = once(b, old_detail_loop, new_detail_loop, 'overlap refresh loop')

b = once(b,
"""  if (job.type === 'detail') {
    await patchOrderProcessing(job.orderId, { processingState: 'processing', processingError: null, processingErrorAt: null });
""",
"""  if (job.type === 'detail') {
    if (!job.resumeOverlapRefresh) await patchOrderProcessing(job.orderId, { processingState: 'processing', processingError: null, processingErrorAt: null });
""",
'preserve overlap state')

# Self-heal interrupted current job and active empty queue inside processNextJob.
b = once(b,
"""    const settings = await getSettings();
    const state = ensureCooldownPlan(await getState());
    const coolingMs = cooldownRemainingMs(state);
""",
"""    const settings = await getSettings();
    let state = ensureCooldownPlan(await getState());
    if (state.currentJob) {
      state = reconstructActiveCrawl(state, 'worker-interruption', { clearManualStop: false });
      await setState(state);
    }
    const coolingMs = cooldownRemainingMs(state);
""",
'process interrupted job recovery')

old_empty = """    if (!state.queue.length) {
      state.running = false;
      state.currentJob = null;
      state.startedAt = null;
      await setState(state);
      if (workerTabId != null) {
        try { await chrome.tabs.remove(workerTabId); } catch (_) {}
        workerTabId = null;
        await chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
      }
      return;
    }
"""
new_empty = """    if (!state.queue.length) {
      if (state.crawl?.active && !state.paused && !state.crawl.manualStop) {
        state = reconstructActiveCrawl(state, 'active-empty-queue', { clearManualStop: false });
        await setState(state);
        if (state.queue.length) { scheduleSoon(randomBetween(100, 300)); return; }
      }
      state.running = false;
      state.currentJob = null;
      state.startedAt = null;
      await setState(state);
      if (workerTabId != null) {
        try { await chrome.tabs.remove(workerTabId); } catch (_) {}
        workerTabId = null;
        await chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
      }
      return;
    }
"""
b = once(b, old_empty, new_empty, 'active empty queue recovery')

old_detail_patch = """    if (job.type === 'detail' && job.orderId) {
      const nextAttempt = Number(job.attempts || 0) + (waitingForDetails ? 0 : 1);
      if (success) {
        await patchOrderProcessing(job.orderId, { processingState: 'complete', processingError: null, processingErrorAt: null, processingLastIssue: null });
      } else if (jobError && (blocked || (!rateLimited && !waitingForDetails && nextAttempt >= 3))) {
        await patchOrderProcessing(job.orderId, { processingState: 'error', processingError: jobError, processingErrorAt: nowIso(), processingLastIssue: jobError });
      } else if (jobError) {
        await patchOrderProcessing(job.orderId, { processingState: 'retrying', processingError: null, processingErrorAt: null, processingLastIssue: jobError });
      }
    }
    if (jobError && !waitingForDetails) {
      completionState.errors += 1;
      completionState.lastError = jobError;
    }

    const managedRetry = job.crawlManaged && !blocked && !rateLimited && !success && (job.type === 'detail' || job.type === 'advance' || job.type === 'history');
"""
new_detail_patch = """    if (job.type === 'detail' && job.orderId && !job.resumeOverlapRefresh) {
      const nextAttempt = Number(job.attempts || 0) + (waitingForDetails ? 0 : 1);
      if (success) {
        await patchOrderProcessing(job.orderId, { processingState: 'complete', processingError: null, processingErrorAt: null, processingLastIssue: null });
      } else if (jobError && (blocked || (!rateLimited && !waitingForDetails && nextAttempt >= 3))) {
        await patchOrderProcessing(job.orderId, { processingState: 'error', processingError: jobError, processingErrorAt: nowIso(), processingLastIssue: jobError });
      } else if (jobError) {
        await patchOrderProcessing(job.orderId, { processingState: 'retrying', processingError: null, processingErrorAt: null, processingLastIssue: jobError });
      }
    }
    if (jobError && !waitingForDetails && !job.resumeOverlapRefresh) {
      completionState.errors += 1;
      completionState.lastError = jobError;
    } else if (jobError && job.resumeOverlapRefresh) {
      completionState.crawl.lastResumeOverlapError = jobError;
    }

    const managedRetry = !job.resumeOverlapRefresh && job.crawlManaged && !blocked && !rateLimited && !success && (job.type === 'detail' || job.type === 'advance' || job.type === 'history');
"""
b = once(b, old_detail_patch, new_detail_patch, 'nonblocking overlap refresh')

# Stop latch + manual/auto message routing.
b = once(b,
"""      state.paused = true;
      state.running = false;
      state.crawl.phase = state.crawl.active ? 'paused' : state.crawl.phase;
""",
"""      state.paused = true;
      state.running = false;
      state.crawl.manualStop = true;
      state.crawl.phase = state.crawl.active ? 'paused' : state.crawl.phase;
""",
'manual stop latch')

b = once(b,
"""  if (message.type === 'ARL_START_FULL_SCAN') {
    startOrResumeFullScan({ restart: Boolean(message.restart), startYear: message.startYear || null })
""",
"""  if (message.type === 'ARL_START_FULL_SCAN') {
    startOrResumeFullScan({ restart: Boolean(message.restart), startYear: message.startYear || null, source: message.restart ? 'manual-restart' : 'manual-resume' })
""",
'manual start source')

amazon_ready_handler = """
  if (message.type === 'ARL_AMAZON_PAGE_READY') {
    handleAmazonUserPageReady(sender)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }

"""
b = once(b, "  if (message.type === 'ARL_DISCOVERED') {", amazon_ready_handler + "  if (message.type === 'ARL_DISCOVERED') {", 'amazon ready message')

# Settings message for Auto-start toggle.
auto_setting_handler = """
  if (message.type === 'ARL_SET_AUTO_START') {
    chrome.storage.local.get([SETTINGS_KEY]).then(async data => {
      const current = data[SETTINGS_KEY] || {};
      const enabled = Boolean(message.enabled);
      await chrome.storage.local.set({ [SETTINGS_KEY]: { ...current, autoStartOnAmazon: enabled } });
      sendResponse({ ok: true, enabled });
    }).catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }

"""
b = once(b, "  if (message.type === 'ARL_SET_BACKGROUND_PAUSED') {", auto_setting_handler + "  if (message.type === 'ARL_SET_BACKGROUND_PAUSED') {", 'auto setting message')

# Startup/update recovery.
old_startup = """chrome.runtime.onStartup.addListener(() => {
  ensureDevelopmentVersionState().then(() => getState()).then(state => { if (state.crawl?.active && !state.paused && state.queue?.length) scheduleSoon(randomBetween(1200, 3000)); }).catch(() => {});
});
chrome.runtime.onInstalled.addListener(details => { ensureDevelopmentVersionState(details?.previousVersion || null).catch(() => {}); });
"""
new_startup = """chrome.runtime.onStartup.addListener(() => {
  ensureDevelopmentVersionState().then(() => resumePersistedCrawl('browser-startup')).catch(() => {});
});
chrome.runtime.onInstalled.addListener(details => {
  ensureDevelopmentVersionState(details?.previousVersion || null)
    .then(() => resumePersistedCrawl('version-update'))
    .catch(() => {});
});
"""
b = once(b, old_startup, new_startup, 'startup resume')
write('background.js', b)

# ---------------- storage.js ----------------
s = read('storage.js')
s = once(s,
"""    autoHistoryCrawl: true,
    showUpdateToast: true,
""",
"""    autoHistoryCrawl: true,
    autoStartOnAmazon: false,
    showUpdateToast: true,
""",
'storage auto-start default')
write('storage.js', s)

# ---------------- content.js ----------------
c = read('content.js')
ready_ping = r'''

  // Tell the background worker that the USER has reached Amazon. The background checks sender.tab
  // activity/identity before acting, so the extension's own inactive worker tab cannot recursively
  // trigger Auto-start.
  try {
    chrome.runtime.sendMessage({ type: 'ARL_AMAZON_PAGE_READY', url: location.href }).catch(() => {});
  } catch (_) {}
'''
# Insert immediately before outer IIFE close.
marker = '\n})();\n'
if not c.endswith(marker):
    raise RuntimeError('content.js outer close marker not found')
c = c[:-len(marker)] + ready_ping + marker
write('content.js', c)

# ---------------- dashboard.html ----------------
h = read('dashboard.html')
h = once(h,
"""      <button id="restartScanner" class="secondary">Restart from current year</button>
""",
"""      <div class="scanner-actions">
        <button id="autoStartScanner" class="secondary" aria-pressed="false">Auto-start: Off</button>
        <button id="restartScanner" class="secondary">Restart from current year</button>
      </div>
""",
'auto start UI')
write('dashboard.html', h)

# ---------------- dashboard.js ----------------
d = read('dashboard.js')
d = once(d,
"""  const scannerCheckpoint = document.getElementById('scannerCheckpoint');
""",
"""  const scannerCheckpoint = document.getElementById('scannerCheckpoint');
  const autoStartScanner = document.getElementById('autoStartScanner');
""",
'dashboard auto control')

d = once(d,
"""  function render() { renderStats(); renderViewMenu(); renderTable(); }
""",
"""  function renderAutoStart() {
    if (!autoStartScanner) return;
    const enabled = Boolean(settings.autoStartOnAmazon);
    autoStartScanner.textContent = `Auto-start: ${enabled ? 'On' : 'Off'}`;
    autoStartScanner.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    autoStartScanner.classList.toggle('auto-start-enabled', enabled);
  }

  function render() { renderStats(); renderViewMenu(); renderTable(); renderAutoStart(); }
""",
'render auto start')

d = once(d,
"""      const yearsDone = (crawl.completedYears || []).length ? ` · completed years ${(crawl.completedYears || []).join(', ')}` : '';
      scannerCheckpoint.textContent = crawl.currentYear
        ? `Checkpoint: ${crawl.currentYear} page ${crawl.currentPage || 1} · ${doneOnPage}/${pageCount || '?'} details complete · ${crawl.ordersCompleted || 0} unique orders completed · ${crawl.overlapCount || 0} overlapping history hits${crawl.lastCompletedOrderId ? ` · last ${crawl.lastCompletedOrderId}` : ''}${yearsDone}`
""",
"""      const yearsDone = (crawl.completedYears || []).length ? ` · completed years ${(crawl.completedYears || []).join(', ')}` : '';
      const resumeInfo = crawl.lastResumeAt ? ` · resume #${crawl.resumeCount || 1} from ${crawl.resumePageKey || `${crawl.currentYear}:${crawl.currentPage || 1}`} (${crawl.lastResumeSource || 'resume'})` : '';
      scannerCheckpoint.textContent = crawl.currentYear
        ? `Checkpoint: ${crawl.currentYear} page ${crawl.currentPage || 1} · ${doneOnPage}/${pageCount || '?'} details complete · ${crawl.ordersCompleted || 0} unique orders completed · ${crawl.overlapCount || 0} overlapping history hits${crawl.lastCompletedOrderId ? ` · last ${crawl.lastCompletedOrderId}` : ''}${resumeInfo}${yearsDone}`
""",
'resume diagnostics UI')

auto_listener = """
  autoStartScanner?.addEventListener('click', async () => {
    const enabled = !Boolean(settings.autoStartOnAmazon);
    const response = await chrome.runtime.sendMessage({ type: 'ARL_SET_AUTO_START', enabled });
    if (!response?.ok) { alert(`Could not update Auto-start: ${response?.error || 'unknown error'}`); return; }
    settings = { ...settings, autoStartOnAmazon: enabled };
    renderAutoStart();
  });
"""
d = once(d,
"""  document.getElementById('startScanner').addEventListener('click', async () => {
""",
auto_listener + "\n  document.getElementById('startScanner').addEventListener('click', async () => {\n",
'auto listener')
write('dashboard.js', d)

# ---------------- ui.css ----------------
css = read('ui.css')
css += r'''

/* v0.18.14 durable resume / auto-start controls */
.scanner-actions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
#autoStartScanner.auto-start-enabled { font-weight:700; }
'''
write('ui.css', css)

# ---------------- tests ----------------
bt = read('background-test.js')
bt += r'''

const backgroundSourceV01814 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(!backgroundSourceV01814.includes('DEV_RESET_ON_VERSION_CHANGE'), 'v0.18.14 must not destructively wipe ledger/crawl state on version update');
assert(backgroundSourceV01814.includes('preservedState: Boolean(prior)'), 'version migration must explicitly preserve durable state');
assert(backgroundSourceV01814.includes('chrome.storage.local.remove([WORKER_TAB_KEY])'), 'version migration must clear stale transient worker tab identity');
assert(backgroundSourceV01814.includes('function recoverInterruptedCurrentJob'), 'resume must recover an interrupted persisted currentJob');
assert(backgroundSourceV01814.includes('function reconstructActiveCrawl'), 'resume must reconstruct active crawl work from checkpoint');
assert(backgroundSourceV01814.includes("source: `resume:${source}`") && backgroundSourceV01814.includes('crawl.currentHistoryUrl || buildHistoryUrl'), 'empty active queue must use saved current history checkpoint instead of page 1');
assert(backgroundSourceV01814.includes("'active-empty-queue'"), 'processNextJob must self-heal an active empty queue');
assert(backgroundSourceV01814.includes("resumeOverlapRefresh: true"), 'known Order IDs on recovered/overlap pages must receive one authoritative refresh');
assert(backgroundSourceV01814.includes('overlapRefreshedOrders[link.orderId]'), 'overlap refresh must be deduped across the lifetime crawl');
assert(backgroundSourceV01814.includes('!job.resumeOverlapRefresh && job.crawlManaged'), 'overlap refresh failure must not become a blocking managed retry');
assert(backgroundSourceV01814.includes("message.type === 'ARL_AMAZON_PAGE_READY'"), 'background must support Amazon page-ready Auto-start trigger');
assert(backgroundSourceV01814.includes("tab.active !== true") && backgroundSourceV01814.includes('tab.id === workerTabId'), 'Auto-start must ignore inactive/worker tabs');
assert(backgroundSourceV01814.includes('state.crawl.manualStop'), 'Auto-start must respect explicit manual Stop latch');
assert(backgroundSourceV01814.includes("resumePersistedCrawl('browser-startup')") && backgroundSourceV01814.includes("resumePersistedCrawl('version-update')"), 'browser/update startup must resume persisted active crawl');
assert(backgroundSourceV01814.includes('RATE_LIMIT_COOLDOWN_MIN_MS = 10 * 60 * 1000') && backgroundSourceV01814.includes('RATE_LIMIT_COOLDOWN_MAX_MS = 20 * 60 * 1000'), 'v0.18.14 must preserve rate-limit cooldown safety');
console.log('v0.18.14 durable resume/autostart background regressions passed');
'''
write('background-test.js', bt)

ut = read('ui-test.js')
ut += r'''

const dashboardHtmlV01814 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
const dashboardJsV01814 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
const storageV01814 = fs.readFileSync(__dirname + '/storage.js', 'utf8');
const contentV01814 = fs.readFileSync(__dirname + '/content.js', 'utf8');
assert(dashboardHtmlV01814.includes('id="autoStartScanner"') && dashboardHtmlV01814.includes('Auto-start: Off'), 'scanner panel must expose an Auto-start toggle');
assert(dashboardJsV01814.includes("type: 'ARL_SET_AUTO_START'") && dashboardJsV01814.includes('settings.autoStartOnAmazon'), 'dashboard Auto-start button must persist the setting');
assert(storageV01814.includes('autoStartOnAmazon: false'), 'Auto-start must default OFF');
assert(contentV01814.includes("type: 'ARL_AMAZON_PAGE_READY'"), 'Amazon content script must announce user-page readiness to Auto-start logic');
assert(dashboardJsV01814.includes('resume #${crawl.resumeCount || 1}'), 'scanner checkpoint UI must expose resume diagnostics');
console.log('v0.18.14 Auto-start/resume UI regressions passed');
'''
write('ui-test.js', ut)

# ---------------- version ----------------
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.14'
manifest['version_name'] = '0.18.14'
manifest['description'] = 'Amazon order/refund ledger with durable checkpoint resume, opt-in Amazon auto-start, authoritative return/replacement workflows, and verified development updates.'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
pkg = json.loads(read('package.json'))
pkg['version'] = '0.18.14'
pkg['description'] = 'Amazon / Amazon Business complete-order ledger with durable checkpoint resume, opt-in Amazon auto-start, adaptive serial crawling, authoritative return/replacement separation, and verified development updates'
write('package.json', json.dumps(pkg, indent=2) + '\n')

# ---------------- docs ----------------
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.13 candidate for Issue #37.**', '**Current source baseline: v0.18.14 candidate for Issue #39.**', 1)
if '- **#37 — v0.18.13 acceptance**' in readme:
    readme = readme.replace('- **#37 — v0.18.13 acceptance** for combined Reset & Refresh and live installed-version display.', '- **#37 — v0.18.13 acceptance** for combined Reset & Refresh and live installed-version display.\n- **#39 — v0.18.14 acceptance** for durable checkpoint resume, overlap self-healing, and opt-in Amazon Auto-start.', 1)
readme = readme.replace('2. Read Issues #7, #23, #25, #29, #31, #33, #35, and #37', '2. Read Issues #7, #23, #25, #29, #31, #33, #35, #37, and #39', 1)
readme = readme.replace('4. Root v0.18.13 is the active candidate.', '4. Root v0.18.14 is the active candidate.', 1)
readme += '''\n\n## v0.18.14 durable checkpoint resume and Amazon Auto-start\n\nAn active lifetime crawl now resumes from its persisted year/page/history URL and Order-ID checkpoint even if the MV3 worker, Chrome, or inactive Amazon worker tab disappears. An interrupted `currentJob` is requeued exactly once; an active empty queue is reconstructed from the saved checkpoint instead of starting current-year page 1. Visible duplicate Order IDs act as resume anchors: a completed overlap can be authoritatively refreshed once, but it is never counted as a new order or used to restart traversal.\n\n`Auto-start: On/Off` is opt-in and defaults OFF. When enabled, loading an active user Amazon tab starts or resumes incomplete lifetime work in a separate inactive worker tab. Worker/inactive tabs cannot recursively trigger Auto-start, explicit Stop latches until manual Start/Resume or Restart, and a completed lifetime scan is not automatically restarted on every Amazon navigation.\n\nv0.18.14 also replaces destructive development-version resets with migration-preserved ledger/crawl state. Version updates clear stale transient worker-tab identity but keep canonical orders, returns, bank verification, and the exact crawl checkpoint so the updater itself no longer destroys resume progress. Issue #39 tracks live acceptance.\n'''
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
handoff += '''\n\n## v0.18.14 durable resume / Auto-start candidate\n- Issue #39 tracks live acceptance.\n- `Start / resume`, browser startup, and version-update recovery use the persisted current year/page/history URL and Order-ID fingerprint; only explicit Restart resets traversal to current-year page 1.\n- Interrupted persisted `currentJob` is requeued once. Active empty queues self-reconstruct from the checkpoint.\n- Completed IDs encountered on a recovered/overlap page are refresh anchors, not new orders; refresh at most once per lifetime run and continue.\n- Auto-start defaults OFF and only reacts to active user Amazon tabs; inactive/worker tabs cannot recursively trigger it. Manual Stop latches until explicit manual resume/restart.\n- v0.18.14 preserves ledger/crawl state across development version updates and clears only transient worker-tab identity.\n'''
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
testing += '''\n\n## v0.18.14 durable resume / Auto-start live acceptance\n1. Upgrade an in-progress v0.18.13 scan to v0.18.14 and verify existing ledger totals plus the saved year/page checkpoint survive.\n2. Interrupt the inactive worker tab or close/reopen Chrome while a scan is running, then verify it resumes from the saved page/current job rather than current-year page 1.\n3. On the recovered page, verify already-completed Order IDs are recognized as overlaps, refreshed at most once, and do not increment unique-order completion; new/incomplete IDs still get canonical Order Details.\n4. Enable `Auto-start: On`, open an active Amazon user tab, and verify the extension starts/resumes using a separate inactive worker tab. Verify worker/inactive tabs do not recursively trigger it.\n5. Press Stop and navigate Amazon; verify Auto-start does not undo the explicit stop. Press Start / resume and verify the latch clears.\n6. Complete a lifetime scan and verify normal Amazon navigation does not automatically restart another full historical crawl.\n'''
write('TESTING.md', testing)

newchat = read('NEW_CHAT_PROMPT.md')
newchat += '''\n\n### Durable resume / Auto-start rule\nTreat the persisted crawl checkpoint (year, page, current history URL, Order-ID fingerprint, completed IDs, queued/current job) as authoritative. Resume must never silently fall back to page 1 unless the user explicitly chooses Restart. Auto-start is opt-in, reacts only to active user Amazon tabs, uses a separate inactive worker tab, respects manual Stop, and must not recursively trigger from extension-created worker tabs. Development upgrades preserve ledger/crawl state; transient tab IDs may be cleared.\n'''
write('NEW_CHAT_PROMPT.md', newchat)

print('v0.18.14 patch applied')
