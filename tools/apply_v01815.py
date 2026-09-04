from pathlib import Path
import json, re
R=Path('.')
def read(p): return (R/p).read_text(encoding='utf-8')
def write(p,s): (R/p).write_text(s,encoding='utf-8')
def once(s,old,new,label):
    n=s.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected 1 match got {n}')
    return s.replace(old,new,1)

# background.js
b=read('background.js')
b=once(b,
"      manualStop: false, lastResumeAt: null, lastResumeSource: null, resumeCount: 0,\n      resumePageKey: null, resumeExpectedFingerprint: null, resumeObservedFingerprint: null,\n      resumeFingerprintMatched: null, lastRecoveredJobKey: null, lastResumeOverlapError: null,\n      lastMigrationAt: null, lastMigrationFrom: null, lastMigrationTo: null",
"      manualStop: false, lastResumeAt: null, lastResumeSource: null, resumeCount: 0,\n      resumePageKey: null, resumeExpectedFingerprint: null, resumeObservedFingerprint: null,\n      resumeFingerprintMatched: null, lastRecoveredJobKey: null, lastResumeOverlapError: null,\n      sessionId: null, sessionStartedAt: null, sessionSource: null, sessionKnownRefreshCount: 0, sessionKnownRefreshFailures: 0,\n      sessionSeenPages: {}, priorFrontier: null,\n      lastMigrationAt: null, lastMigrationFrom: null, lastMigrationTo: null",
'default session fields')
b=once(b,
"  state.crawl.overlapRefreshedOrders = state.crawl.overlapRefreshedOrders || {};\n  state.crawl.overlapExamples = Array.isArray(state.crawl.overlapExamples) ? state.crawl.overlapExamples.slice(-50) : [];\n  state.crawl.manualStop = Boolean(state.crawl.manualStop);\n  state.crawl.resumeCount = Number.isFinite(Number(state.crawl.resumeCount)) ? Number(state.crawl.resumeCount) : 0;",
"  state.crawl.overlapRefreshedOrders = state.crawl.overlapRefreshedOrders || {};\n  state.crawl.sessionSeenPages = state.crawl.sessionSeenPages || {};\n  state.crawl.overlapExamples = Array.isArray(state.crawl.overlapExamples) ? state.crawl.overlapExamples.slice(-50) : [];\n  state.crawl.manualStop = Boolean(state.crawl.manualStop);\n  state.crawl.resumeCount = Number.isFinite(Number(state.crawl.resumeCount)) ? Number(state.crawl.resumeCount) : 0;\n  state.crawl.sessionKnownRefreshCount = Number.isFinite(Number(state.crawl.sessionKnownRefreshCount)) ? Number(state.crawl.sessionKnownRefreshCount) : 0;\n  state.crawl.sessionKnownRefreshFailures = Number.isFinite(Number(state.crawl.sessionKnownRefreshFailures)) ? Number(state.crawl.sessionKnownRefreshFailures) : 0;",
'normalize session fields')

# Per-session page accounting.
b=once(b,
"  const pageKey = `${year}:${page}`;\n  const fingerprint = pageOrderIds.join('|');\n  const previousFingerprint = crawl.seenPages[pageKey];",
"  const pageKey = `${year}:${page}`;\n  const fingerprint = pageOrderIds.join('|');\n  crawl.sessionSeenPages = crawl.sessionSeenPages || {};\n  if (crawl.sessionId && crawl.sessionSeenPages[pageKey] !== fingerprint) crawl.sessionSeenPages[pageKey] = fingerprint;\n  const previousFingerprint = crawl.seenPages[pageKey];",
'session page accounting')

# Every known completed order encountered in the pass gets one non-destructive refresh.
old="""    const firstSeen = crawl.seenOrders?.[link.orderId] || null;
    const alreadyComplete = Boolean(crawl.completedOrders[link.orderId]);
    const crossPageOverlap = Boolean(alreadyComplete && firstSeen?.pageKey && firstSeen.pageKey !== pageKey);
    const resumeDuplicate = Boolean(alreadyComplete && job?.resumeRecovery);
    const ledgerAdopted = Boolean(alreadyComplete && crawl.completedOrders[link.orderId]?.adoptedFromLedger);
    if (alreadyComplete) {
      // A known Order ID is an anchor, not a reason to restart history. Refresh it once when it
      // proves the recovered/shifted page overlaps prior work, then continue without incrementing
      // lifetime completion or repeatedly hitting the same order during fallback navigation.
      if ((resumeDuplicate || crossPageOverlap || ledgerAdopted) && !crawl.overlapRefreshedOrders[link.orderId]) {
        const refreshJob = {
          type: 'detail', orderId: link.orderId, url: normalizeUrl(link.url) || link.url,
          source: `resume-overlap ${pageKey}`, crawlManaged: true, resumeOverlapRefresh: true,
          crawlYear: year, crawlPage: page, crawlPageKey: pageKey, historyUrl: crawl.currentHistoryUrl,
          sequence: seq, priority: 5, queuedAt: nowIso(), attempts: 0
        };
"""
new="""    const firstSeen = crawl.seenOrders?.[link.orderId] || null;
    const alreadyComplete = Boolean(crawl.completedOrders[link.orderId]);
    if (alreadyComplete) {
      // Every new scanner session deliberately starts from the newest order. Known complete IDs are
      // refreshed exactly once in that session so returns/replacements/refund state can advance,
      // but the global unique-order completion set is never incremented again.
      if (!crawl.overlapRefreshedOrders[link.orderId]) {
        const refreshJob = {
          type: 'detail', orderId: link.orderId, url: normalizeUrl(link.url) || link.url,
          source: `session-known-refresh ${pageKey}`, crawlManaged: true, resumeOverlapRefresh: true,
          scanSessionId: crawl.sessionId || job?.scanSessionId || null,
          crawlYear: year, crawlPage: page, crawlPageKey: pageKey, historyUrl: crawl.currentHistoryUrl,
          sequence: seq, priority: 5, queuedAt: nowIso(), attempts: 0
        };
"""
b=once(b,old,new,'known order session refresh')
# Propagate session to new canonical jobs.
b=once(b,
"      type: 'detail', orderId: link.orderId, url: normalizeUrl(link.url) || link.url,\n      source: `crawl ${pageKey}`, crawlManaged: true, crawlYear: year, crawlPage: page,",
"      type: 'detail', orderId: link.orderId, url: normalizeUrl(link.url) || link.url,\n      source: `crawl ${pageKey}`, crawlManaged: true, scanSessionId: crawl.sessionId || job?.scanSessionId || null, crawlYear: year, crawlPage: page,",
'normal detail session propagation')
b=once(b,
"    type: 'advance', url: crawl.currentHistoryUrl, source: `crawl ${pageKey}`, crawlManaged: true,\n    crawlYear: year, crawlPage: page, crawlPageKey: pageKey, pageOrderIds,",
"    type: 'advance', url: crawl.currentHistoryUrl, source: `crawl ${pageKey}`, crawlManaged: true,\n    scanSessionId: crawl.sessionId || job?.scanSessionId || null, crawlYear: year, crawlPage: page, crawlPageKey: pageKey, pageOrderIds,",
'advance session propagation')

# Insert newest-session helpers before checkpoint recovery helpers.
marker='function crawlCheckpointPageKey(crawl) {'
idx=b.index(marker)
helpers=r'''function makeScanSessionId() {
  return `scan-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function snapshotHistoricalFrontier(crawl) {
  if (!crawl?.currentYear) return crawl?.priorFrontier || null;
  return {
    capturedAt: nowIso(),
    year: Number(crawl.currentYear),
    page: Math.max(1, Number(crawl.currentPage) || 1),
    pageKey: `${Number(crawl.currentYear)}:${Math.max(1, Number(crawl.currentPage) || 1)}`,
    historyUrl: crawl.currentHistoryUrl || null,
    ordersCompleted: Object.keys(crawl.completedOrders || {}).length,
    lastCompletedOrderId: crawl.lastCompletedOrderId || null
  };
}

function beginNewestScanSession(state, source = 'manual-resume', startYear = null) {
  state = ensureCrawl(state);
  const prior = state.crawl;
  const now = nowIso();
  const year = Number(startYear) || new Date().getFullYear();
  const sessionId = makeScanSessionId();
  const priorFrontier = snapshotHistoricalFrontier(prior);
  const years = Array.from(new Set([year, ...(prior.years || [])].map(Number).filter(Number.isFinite))).sort((a,b) => b-a);

  state.queue = [];
  state.currentJob = null;
  state.paused = false;
  state.running = true;
  state.lastError = null;
  state.lastHistoryAdvanceError = null;
  state.crawl = {
    ...prior,
    active: true,
    phase: 'history',
    years,
    completedYears: [],
    currentYear: year,
    currentPage: 1,
    currentHistoryUrl: buildHistoryUrl('https://www.amazon.com/gp/your-account/order-history', year, 1),
    currentPageOrderIds: [],
    currentPageCompleted: 0,
    completedAt: null,
    manualStop: false,
    overlapRefreshedOrders: {},
    sessionSeenPages: {},
    sessionId,
    sessionStartedAt: now,
    sessionSource: source,
    sessionKnownRefreshCount: 0,
    sessionKnownRefreshFailures: 0,
    priorFrontier,
    startedAt: prior.startedAt || now
  };
  state.crawl.ordersCompleted = Object.keys(state.crawl.completedOrders || {}).length;
  state.queue.push({
    type: 'history', url: state.crawl.currentHistoryUrl, historyYear: year, historyPage: 1,
    crawlManaged: true, scanSessionId: sessionId, sessionPass: true,
    source: `newest-session:${source}`, priority: 1, queuedAt: now, attempts: 0
  });
  return state;
}

'''
b=b[:idx]+helpers+b[idx:]

# Replace manual/new start logic. Internal persisted recovery remains checkpoint-based.
start=b.index('async function startOrResumeFullScan(')
end=b.index('\nasync function queueNextYear',start)
new_start=r'''async function startOrResumeFullScan({ restart = false, startYear = null, source = 'manual' } = {}) {
  let state = ensureCrawl(await getState());
  if (source === 'auto-amazon' && state.crawl.manualStop) return state;

  // Start while an existing pass is genuinely running is a no-op. A user Stop followed by Start,
  // an inactive completed/idle scanner, Auto-start beginning new work, or explicit Restart all
  // create a NEW pass from the newest order. Service-worker/browser recovery uses
  // resumePersistedCrawl() instead and therefore does not rewind the same live pass repeatedly.
  const livePass = state.crawl.active && !state.paused && (processing || state.running || Boolean(state.currentJob) || state.queue.length > 0);
  if (!restart && livePass) return state;
  if (processing) return state;

  state = beginNewestScanSession(state, source, startYear);
  await setState(state);
  scheduleSoon(randomBetween(300, 900));
  return state;
}
'''
b=b[:start]+new_start+b[end:]

# queueNextYear carries the same session.
b=once(b,
"    type: 'history', url: crawl.currentHistoryUrl, historyYear: nextYear, historyPage: 1,\n    crawlManaged: true, source: 'next-year', priority: 1, queuedAt: nowIso(), attempts: 0",
"    type: 'history', url: crawl.currentHistoryUrl, historyYear: nextYear, historyPage: 1,\n    crawlManaged: true, scanSessionId: crawl.sessionId || null, sessionPass: true, source: 'next-year', priority: 1, queuedAt: nowIso(), attempts: 0",
'next year session propagation')

# Propagate session between history pages after verified advance.
b=b.replace("      crawlManaged: true,\n      source: 'verified-next-page'", "      crawlManaged: true,\n      scanSessionId: job.scanSessionId || null, sessionPass: true,\n      source: 'verified-next-page'", 1)

# Per-session successful/failed known refresh counts.
b=once(b,
"    } else if (jobError && job.resumeOverlapRefresh) {\n      completionState.crawl.lastResumeOverlapError = jobError;\n    }",
"    } else if (jobError && job.resumeOverlapRefresh) {\n      completionState.crawl.lastResumeOverlapError = jobError;\n      completionState.crawl.sessionKnownRefreshFailures = Number(completionState.crawl.sessionKnownRefreshFailures || 0) + 1;\n    }",
'refresh failure count')
b=once(b,
"    if (success && job.type === 'detail') {\n      completionState.detailProcessed += 1;\n      if (job.crawlManaged) {\n        const crawl = completionState.crawl;",
"    if (success && job.type === 'detail') {\n      completionState.detailProcessed += 1;\n      if (job.crawlManaged) {\n        const crawl = completionState.crawl;\n        if (job.resumeOverlapRefresh) crawl.sessionKnownRefreshCount = Number(crawl.sessionKnownRefreshCount || 0) + 1;",
'refresh success count')
write('background.js',b)

# dashboard UI
dh=read('dashboard.html')
dh=dh.replace('<button id="startScanner" class="secondary">Start / resume</button>','<button id="startScanner" class="secondary">Start newest scan</button>',1)
dh=dh.replace('<button id="restartScanner" class="secondary">Restart from current year</button>','<button id="restartScanner" class="secondary">Restart newest now</button>',1)
dh=dh.replace('<strong>Lifetime history scanner</strong>','<strong>Lifetime history scanner</strong>\n        <div class="muted tiny">Each new scan starts at the newest order, refreshes known overlaps once, then continues backward past the previous frontier.</div>',1)
write('dashboard.html',dh)

d=read('dashboard.js')
old="""      const resumeInfo = crawl.lastResumeAt ? ` · resume #${crawl.resumeCount || 1} from ${crawl.resumePageKey || `${crawl.currentYear}:${crawl.currentPage || 1}`} (${crawl.lastResumeSource || 'resume'})` : '';
      scannerCheckpoint.textContent = crawl.currentYear
        ? `Checkpoint: ${crawl.currentYear} page ${crawl.currentPage || 1} · ${doneOnPage}/${pageCount || '?'} details complete · ${crawl.ordersCompleted || 0} unique orders completed · ${crawl.overlapCount || 0} overlapping history hits${crawl.lastCompletedOrderId ? ` · last ${crawl.lastCompletedOrderId}` : ''}${resumeInfo}${yearsDone}`
"""
new="""      const recoveryInfo = crawl.lastResumeAt ? ` · worker recovery #${crawl.resumeCount || 1} (${crawl.lastResumeSource || 'recovery'})` : '';
      const sessionInfo = crawl.sessionStartedAt ? ` · session ${crawl.sessionSource || 'scan'} · ${crawl.sessionKnownRefreshCount || 0} known orders refreshed${crawl.sessionKnownRefreshFailures ? ` · ${crawl.sessionKnownRefreshFailures} refresh failures` : ''}` : '';
      const frontierInfo = crawl.priorFrontier?.pageKey ? ` · previous frontier ${crawl.priorFrontier.pageKey}` : '';
      scannerCheckpoint.textContent = crawl.currentYear
        ? `Current pass: ${crawl.currentYear} page ${crawl.currentPage || 1} · ${doneOnPage}/${pageCount || '?'} details complete · ${crawl.ordersCompleted || 0} unique orders stored · ${crawl.overlapCount || 0} overlapping history hits${crawl.lastCompletedOrderId ? ` · last ${crawl.lastCompletedOrderId}` : ''}${sessionInfo}${frontierInfo}${recoveryInfo}${yearsDone}`
"""
d=once(d,old,new,'dashboard session status')
d=d.replace("if (!confirm('Restart the lifetime history scan from the current year? Existing ledger data will be kept.')) return;","if (!confirm('Start a fresh pass from the newest Amazon order now? Existing ledger and historical progress will be kept.')) return;",1)
write('dashboard.js',d)

# popup wording
p=read('popup.js')
p=p.replace("else if (crawl.active && state.paused) scanToggleButton.textContent = 'Resume lifetime scan';\n    else scanToggleButton.textContent = 'Start lifetime scan';","else if (crawl.active && state.paused) scanToggleButton.textContent = 'Start newest pass';\n    else scanToggleButton.textContent = 'Start newest pass';",1)
write('popup.js',p)

# Tests: state-machine version + v0.18.15 newest session expectations.
st=read('state-machine-test.js')
st=st.replace("version: '0.18.14'","version: '0.18.15'",1)
st=st.replace("store.installedExtensionVersion === '0.18.14'","store.installedExtensionVersion === '0.18.15'")
st=st.replace("'version migration should store new manifest version'","'version migration should store v0.18.15'",1)
st=st.replace("'previousVersion migration should persist v0.18.14 version key'","'previousVersion migration should persist v0.18.15 version key'",1)
old_block="""  await sandbox.startOrResumeFullScan({ restart:false, source:'manual-resume' });
  state = store.backgroundScanState;
  assert(state.queue.length === 1 && state.queue[0].type === 'history' && state.queue[0].resumeRecovery === true, 'active empty queue must reconstruct one managed history checkpoint job');
  assert(state.queue[0].historyPage === 31 && state.queue[0].url.includes('/pagination/31/'), 'checkpoint reconstruction must resume saved page 31');
  assert(!state.queue[0].url.includes('/pagination/1/'), 'checkpoint reconstruction must not silently restart page 1');

  await sandbox.queueManagedHistoryResult({
    scannedUrl: resumeUrl, historySelectedYear:2026, historyYears:[2026,2025], historyOrderIds:[resumeOrderId],
    detailLinks:[{orderId:resumeOrderId,url:resumeDetailUrl}], records:[]
  }, state.queue[0]);
  state = store.backgroundScanState;
  const overlapRefreshes = state.queue.filter(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeOverlapRefresh === true);
  assert(overlapRefreshes.length === 1, 'known Order ID on recovered page must queue one authoritative overlap refresh');
  assert(state.crawl.ordersCompleted === 1, 'overlap refresh must preserve the existing unique-order completion count without adding a second completion');
  await sandbox.queueManagedHistoryResult({
    scannedUrl: resumeUrl, historySelectedYear:2026, historyYears:[2026,2025], historyOrderIds:[resumeOrderId],
    detailLinks:[{orderId:resumeOrderId,url:resumeDetailUrl}], records:[]
  }, { historyYear:2026, historyPage:31, crawlManaged:true, resumeRecovery:true, resumeExpectedFingerprint:resumeOrderId });
  state = store.backgroundScanState;
  assert(state.queue.filter(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeOverlapRefresh === true).length === 1, 'same overlap must not be refreshed repeatedly in one lifetime crawl');
"""
new_block="""  await sandbox.startOrResumeFullScan({ restart:false, source:'manual-resume', startYear:2026 });
  state = store.backgroundScanState;
  const firstSessionId = state.crawl.sessionId;
  assert(Boolean(firstSessionId), 'new scanner pass must persist a session identity');
  assert(state.queue.length === 1 && state.queue[0].type === 'history', 'manual Start must create one newest history job');
  assert(state.queue[0].historyPage === 1 && state.queue[0].url.includes('/pagination/1/'), 'manual Start must always begin at newest page 1');
  assert(state.crawl.priorFrontier?.pageKey === '2026:31', 'old checkpoint must be preserved as a historical frontier, not used as the start page');
  assert(state.crawl.ordersCompleted === 1, 'starting a new pass must preserve global unique-order completion count');

  const newestUrl = 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/1/';
  await sandbox.queueManagedHistoryResult({
    scannedUrl:newestUrl, historySelectedYear:2026, historyYears:[2026,2025], historyOrderIds:[resumeOrderId],
    detailLinks:[{orderId:resumeOrderId,url:resumeDetailUrl}], records:[]
  }, state.queue[0]);
  state = store.backgroundScanState;
  let overlapRefreshes = state.queue.filter(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeOverlapRefresh === true);
  assert(overlapRefreshes.length === 1, 'known Order ID encountered from newest must queue one authoritative refresh in the session');
  assert(state.crawl.ordersCompleted === 1, 'known-order refresh must not increment the global unique-order completion count');
  await sandbox.queueManagedHistoryResult({
    scannedUrl:newestUrl, historySelectedYear:2026, historyYears:[2026,2025], historyOrderIds:[resumeOrderId],
    detailLinks:[{orderId:resumeOrderId,url:resumeDetailUrl}], records:[]
  }, { historyYear:2026, historyPage:1, crawlManaged:true, scanSessionId:firstSessionId, sessionPass:true });
  state = store.backgroundScanState;
  assert(state.queue.filter(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeOverlapRefresh === true).length === 1, 'same known order must not refresh more than once in one session');

  // A later explicit Start is a new session: refresh markers reset and the same known order is
  // intentionally checked once again from the newest page.
  state.paused = true; state.running = false; state.crawl.manualStop = true; store.backgroundScanState = state;
  await sandbox.startOrResumeFullScan({ restart:false, source:'manual-resume', startYear:2026 });
  state = store.backgroundScanState;
  const secondSessionId = state.crawl.sessionId;
  assert(secondSessionId && secondSessionId !== firstSessionId, 'second Start must create a new scan session');
  assert(state.queue[0].historyPage === 1 && state.queue[0].url.includes('/pagination/1/'), 'every new session must start at newest page 1');
  assert(Object.keys(state.crawl.overlapRefreshedOrders || {}).length === 0, 'per-session known-order refresh markers must reset on new Start');
  await sandbox.queueManagedHistoryResult({
    scannedUrl:newestUrl, historySelectedYear:2026, historyYears:[2026,2025], historyOrderIds:[resumeOrderId],
    detailLinks:[{orderId:resumeOrderId,url:resumeDetailUrl}], records:[]
  }, state.queue[0]);
  state = store.backgroundScanState;
  overlapRefreshes = state.queue.filter(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeOverlapRefresh === true);
  assert(overlapRefreshes.length === 1, 'same known order must be eligible for one refresh again in a new session');
  assert(state.crawl.ordersCompleted === 1, 'repeat sessions must never double-count the known order');
"""
st=once(st,old_block,new_block,'state machine newest session contract')
write('state-machine-test.js',st)

# Background static regression coverage.
bgt=read('background-test.js')
bgt += r'''

const backgroundV01815 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(backgroundV01815.includes('function beginNewestScanSession'), 'v0.18.15 must have a dedicated newest-session initializer');
assert(backgroundV01815.includes("currentPage: 1") && backgroundV01815.includes('priorFrontier'), 'new sessions must begin page 1 while preserving prior frontier');
assert(backgroundV01815.includes('overlapRefreshedOrders: {}'), 'new sessions must reset only per-session known-order refresh markers');
assert(backgroundV01815.includes('sessionKnownRefreshCount'), 'known-order refresh progress must be observable per session');
assert(backgroundV01815.includes('resumePersistedCrawl'), 'same-session service-worker recovery must remain checkpoint-based');
console.log('v0.18.15 newest-session background regressions passed');
'''
write('background-test.js',bgt)

ui=read('ui-test.js')
ui += r'''

const htmlV01815 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
const dashboardV01815 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
assert(htmlV01815.includes('Start newest scan'), 'scanner primary action must state that a new pass starts newest');
assert(htmlV01815.includes('Restart newest now'), 'explicit restart action must also state newest-first behavior');
assert(htmlV01815.includes('refreshes known overlaps once'), 'scanner UI must explain newest-first overlap refresh behavior');
assert(dashboardV01815.includes('previous frontier') && dashboardV01815.includes('known orders refreshed'), 'scanner status must expose frontier and per-session refresh progress');
console.log('v0.18.15 newest-session UI regressions passed');
'''
write('ui-test.js',ui)

# Version bump.
manifest=json.loads(read('manifest.json')); manifest['version']='0.18.15'; manifest['version_name']='0.18.15'; write('manifest.json',json.dumps(manifest,indent=2)+'\n')
pkg=json.loads(read('package.json')); pkg['version']='0.18.15'; pkg['description']='Amazon / Amazon Business complete-order ledger with newest-first refresh sessions, persistent historical frontier, opt-in Amazon auto-start, adaptive serial crawling, and authoritative return/replacement tracking'; write('package.json',json.dumps(pkg,indent=2)+'\n')

# Durable docs.
readme=read('README.md')
readme=readme.replace('**Current source baseline: v0.18.14 candidate for Issue #39.**','**Current source baseline: v0.18.15 candidate for Issue #41.**',1)
readme=readme.replace('4. Root v0.18.14 is the active candidate.','4. Root v0.18.15 is the active candidate.',1)
readme += '''\n\n## v0.18.15 newest-first scan sessions\nEvery newly started scanner session begins at the newest Amazon order (current year page 1), while the prior year/page checkpoint is retained as a historical frontier. The pass walks backward through every page, refreshes each already-complete Order ID exactly once in that session using its real canonical Order Details route, captures new/incomplete IDs normally, and continues beyond the prior frontier into older unscanned history. Known-order refreshes are non-destructive on ordinary failure and never increment the global unique-order count. A transient MV3 service-worker recovery inside the same running session still resumes its in-flight/checkpoint work so browser internals cannot force repeated page-1 rewinds. Issue #41 tracks live acceptance.\n'''
write('README.md',readme)

handoff=read('PROJECT_HANDOFF.md')
handoff += '''\n\n## v0.18.15 newest-first session contract\n- Issue #41 supersedes the manual-start entry behavior from #39.\n- Every NEW scan session starts current year page 1/newest order. The prior checkpoint is retained only as the historical frontier.\n- Known complete Order IDs are authoritatively refreshed once per session without increasing unique-order completion; new/incomplete orders follow the normal strict canonical path.\n- The pass does not stop at the old frontier; it continues backward into older/unscanned history.\n- Internal MV3/service-worker recovery of the SAME session remains checkpoint-based to avoid repeated rewinds caused by Chrome suspension.\n'''
write('PROJECT_HANDOFF.md',handoff)

testing=read('TESTING.md')
testing += '''\n\n## v0.18.15 live newest-first session acceptance\n1. Let an existing scan reach a deep checkpoint and note the year/page and unique-order count.\n2. Stop, then press Start newest scan. Verify the new session opens current year page 1/newest orders, while the prior deep page remains visible as the previous frontier.\n3. Verify known completed Order IDs are refreshed once in the session, return/replacement status updates if Amazon changed, and the unique-order count does not increase for overlaps.\n4. Verify the pass continues through the previous frontier into older/unscanned pages instead of stopping there.\n5. Interrupt only the MV3 worker/worker tab during a running session and verify internal recovery continues that same session rather than repeatedly rewinding to page 1.\n'''
write('TESTING.md',testing)

newchat=read('NEW_CHAT_PROMPT.md')
newchat += '''\n\n### v0.18.15 scanner entry rule\nEvery newly started scan session begins at the newest Amazon order/current-year page 1. Preserve the old checkpoint as a frontier, refresh each known complete overlap exactly once per session, capture new/incomplete orders normally, and continue beyond the old frontier. Only an internal recovery of the same already-running session resumes its persisted in-flight/checkpoint job.\n'''
write('NEW_CHAT_PROMPT.md',newchat)

print('v0.18.15 patch applied')
