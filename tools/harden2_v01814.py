from pathlib import Path

def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)

p = Path('background.js')
s = p.read_text(encoding='utf-8')

# Let the durable ledger act as a secondary recovery index if crawl metadata was partially lost.
old = """  const links = uniqueDetailLinks(result);
  const terminalByOrder = terminalCancelledHistoryOrders(result);
  const pageOrderIds = historyOrderIdSet(result);
  if (!pageOrderIds.length) throw new Error(`No visible Amazon Order IDs were found on ${year} page ${page}`);
  const linkByOrder = new Map(links.map(link => [link.orderId, link]));
  const missingDetailUrls = pageOrderIds.filter(orderId => !linkByOrder.has(orderId) && !terminalByOrder.has(orderId));
"""
new = """  const links = uniqueDetailLinks(result);
  const terminalByOrder = terminalCancelledHistoryOrders(result);
  const pageOrderIds = historyOrderIdSet(result);
  if (!pageOrderIds.length) throw new Error(`No visible Amazon Order IDs were found on ${year} page ${page}`);

  const ledgerData = await chrome.storage.local.get([LEDGER_KEY]);
  const ledger = Array.isArray(ledgerData[LEDGER_KEY]) ? ledgerData[LEDGER_KEY] : [];
  const ledgerOrders = new Map();
  for (const record of ledger) {
    if (record?.recordType !== 'order' || !record?.orderId) continue;
    const prior = ledgerOrders.get(record.orderId);
    if (!prior || (record.orderDataComplete && !prior.orderDataComplete) || String(record.lastScannedAt || '') > String(prior.lastScannedAt || '')) {
      ledgerOrders.set(record.orderId, record);
    }
  }
  const ledgerCompleteIds = new Set(Array.from(ledgerOrders.values())
    .filter(record => record?.orderDataComplete === true || (record?.historyTerminalComplete === true && record?.historyTerminalState === 'cancelled'))
    .map(record => record.orderId));

  const linkByOrder = new Map(links.map(link => [link.orderId, link]));
  // A previously captured canonical Detail URL remains real Amazon evidence. If a recovered
  // history card temporarily omits its Detail action, reuse that stored real URL rather than
  // synthesizing one or stopping on an already-known order.
  for (const orderId of pageOrderIds) {
    if (linkByOrder.has(orderId)) continue;
    const storedUrl = ledgerOrders.get(orderId)?.orderDetailsUrl || null;
    if (storedUrl && /(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|\\/gp\\/css\\/summary\\/edit\\.html|order-details)/i.test(storedUrl)) {
      linkByOrder.set(orderId, { orderId, url: normalizeUrl(storedUrl) || storedUrl, source: 'stored-canonical-detail-url' });
    }
  }
  const missingDetailUrls = pageOrderIds.filter(orderId => !linkByOrder.has(orderId) && !terminalByOrder.has(orderId));
"""
s = once(s, old, new, 'ledger recovery index')

# orderedLinks must use the supplemented map rather than only current-page extraction.
s = once(s,
"""  const orderedLinks = pageOrderIds.map(orderId => linkByOrder.get(orderId)).filter(Boolean);
  crawl.currentPageOrderIds = pageOrderIds;
""",
"""  const orderedLinks = pageOrderIds.map(orderId => linkByOrder.get(orderId)).filter(Boolean);
  crawl.currentPageOrderIds = pageOrderIds;
""",
'ordered links marker')

# Adopt canonical ledger completions before deciding what is genuinely new.
old = """  for (const orderId of pageOrderIds) {
    if (!terminalByOrder.has(orderId) || crawl.completedOrders[orderId]) continue;
    crawl.completedOrders[orderId] = { at: nowIso(), year, page, terminalState: 'cancelled', source: 'order-history-card' };
    crawl.ordersCompleted = (crawl.ordersCompleted || 0) + 1;
    crawl.lastCompletedOrderId = orderId;
    crawl.lastCompletedAt = nowIso();
  }
  crawl.currentPageCompleted = pageOrderIds.filter(orderId => crawl.completedOrders[orderId]).length;
"""
new = """  for (const orderId of pageOrderIds) {
    if (crawl.completedOrders[orderId]) continue;
    if (terminalByOrder.has(orderId)) {
      crawl.completedOrders[orderId] = { at: nowIso(), year, page, terminalState: 'cancelled', source: 'order-history-card' };
      crawl.lastCompletedOrderId = orderId;
      crawl.lastCompletedAt = nowIso();
      continue;
    }
    if (ledgerCompleteIds.has(orderId)) {
      crawl.completedOrders[orderId] = { at: nowIso(), year, page, source: 'existing-ledger', adoptedFromLedger: true };
    }
  }
  // Completion count is derived from the durable identity set so metadata recovery cannot double
  // count adopted/overlapping IDs or undercount after a lost in-memory queue.
  crawl.ordersCompleted = Object.keys(crawl.completedOrders).length;
  crawl.currentPageCompleted = pageOrderIds.filter(orderId => crawl.completedOrders[orderId]).length;
"""
s = once(s, old, new, 'adopt ledger completions')

# A ledger-adopted order deserves the same one-time authoritative refresh as a resume overlap.
s = once(s,
"""    const crossPageOverlap = Boolean(alreadyComplete && firstSeen?.pageKey && firstSeen.pageKey !== pageKey);
    const resumeDuplicate = Boolean(alreadyComplete && job?.resumeRecovery);
    if (alreadyComplete) {
""",
"""    const crossPageOverlap = Boolean(alreadyComplete && firstSeen?.pageKey && firstSeen.pageKey !== pageKey);
    const resumeDuplicate = Boolean(alreadyComplete && job?.resumeRecovery);
    const ledgerAdopted = Boolean(alreadyComplete && crawl.completedOrders[link.orderId]?.adoptedFromLedger);
    if (alreadyComplete) {
""",
'ledger adopted flag')
s = once(s,
"""      if ((resumeDuplicate || crossPageOverlap) && !crawl.overlapRefreshedOrders[link.orderId]) {
""",
"""      if ((resumeDuplicate || crossPageOverlap || ledgerAdopted) && !crawl.overlapRefreshedOrders[link.orderId]) {
""",
'ledger adopted refresh')

# If the user presses Resume immediately after Stop while a job is still physically in flight,
# clear the stop latch but do not reconstruct/requeue that live currentJob.
old = """    // In the same live service worker, an in-memory processing=true means currentJob is genuinely
    // in flight. Resume must not reinterpret it as stale. After a browser/service-worker restart
    // processing is false, so persisted currentJob recovery still works exactly as intended.
    if (processing && !state.paused) return state;
    const alreadyRunning = !state.paused && state.running && !state.currentJob && state.queue.length > 0;
"""
new = """    // In the same live service worker, an in-memory processing=true means currentJob is genuinely
    // in flight. Resume must not reinterpret it as stale. If the user manually resumes immediately
    // after Stop, clear the latch and let that live job finish; its normal completion will schedule
    // the next job. After a browser/service-worker restart processing is false, so persisted
    // currentJob recovery still works exactly as intended.
    if (processing) {
      if (source !== 'auto-amazon') {
        state.paused = false;
        state.running = true;
        state.crawl.manualStop = false;
        state.crawl.lastResumeAt = nowIso();
        state.crawl.lastResumeSource = source;
        state.crawl.resumeCount = Number(state.crawl.resumeCount || 0) + 1;
        await setState(state);
      }
      return state;
    }
    const alreadyRunning = !state.paused && state.running && !state.currentJob && state.queue.length > 0;
"""
s = once(s, old, new, 'inflight manual resume')

p.write_text(s, encoding='utf-8')

# Dynamic state-machine test: if crawl completion metadata is lost but ledger data remains, adopt
# the known complete ID and refresh once instead of treating it as a new order.
t = Path('state-machine-test.js')
x = t.read_text(encoding='utf-8')
marker = "  delete store.installedExtensionVersion;\n"
insert = """  // Ledger-backed recovery: completed canonical data is a secondary identity index when crawl\n  // metadata is missing. It must be adopted without counting a new order, then refreshed once.\n  store.ledger = [{ recordId:`order:${resumeOrderId}`, recordType:'order', orderId:resumeOrderId, orderDetailsUrl:resumeDetailUrl, detailScanComplete:true, orderDataComplete:true, lastScannedAt:new Date().toISOString() }];\n  store.backgroundScanState = {\n    running:false, paused:false, queue:[], currentJob:null,\n    crawl:{ active:true, phase:'resume', years:[2026], currentYear:2026, currentPage:31, currentHistoryUrl:resumeUrl, currentPageOrderIds:[], completedOrders:{}, seenOrders:{}, seenPages:{}, overlapRefreshedOrders:{} }\n  };\n  await sandbox.queueManagedHistoryResult({\n    scannedUrl:resumeUrl, historySelectedYear:2026, historyYears:[2026], historyOrderIds:[resumeOrderId], detailLinks:[], records:[]\n  }, { historyYear:2026, historyPage:31, crawlManaged:true, resumeRecovery:true });\n  state = store.backgroundScanState;\n  assert(state.crawl.completedOrders[resumeOrderId]?.adoptedFromLedger === true, 'known canonical ledger order must be adopted when crawl completion metadata is missing');\n  assert(state.crawl.ordersCompleted === 1, 'ledger adoption must derive unique completion count without double-counting');\n  assert(state.queue.some(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeOverlapRefresh === true), 'ledger-adopted order must receive one authoritative overlap refresh');\n  assert(state.queue.filter(j => j.type === 'detail' && j.orderId === resumeOrderId && !j.resumeOverlapRefresh).length === 0, 'ledger-adopted order must not be treated as a new canonical detail job');\n\n"""
if marker not in x:
    raise RuntimeError('state-machine insertion marker missing')
x = x.replace(marker, insert + marker, 1)
t.write_text(x, encoding='utf-8')

# Static assertions for fallback index and in-flight resume handling.
bt = Path('background-test.js')
y = bt.read_text(encoding='utf-8')
marker2 = "console.log('v0.18.14 durable resume/autostart background regressions passed');"
insert2 = """assert(backgroundSourceV01814.includes('adoptedFromLedger: true') && backgroundSourceV01814.includes("source: 'stored-canonical-detail-url'"), 'durable ledger must serve as a secondary completion/detail-URL recovery index');\nassert(backgroundSourceV01814.includes("if (processing) {") && backgroundSourceV01814.includes("if (source !== 'auto-amazon')"), 'manual Resume during an in-flight job must clear Stop without requeueing the live currentJob');\n"""
if marker2 not in y:
    raise RuntimeError('background test insertion marker missing')
y = y.replace(marker2, insert2 + marker2, 1)
bt.write_text(y, encoding='utf-8')

print('v0.18.14 ledger recovery hardening applied')
