from pathlib import Path
p = Path('state-machine-test.js')
s = p.read_text(encoding='utf-8')
s = s.replace("runtime: { getManifest: () => ({ version: '0.17.0' })", "runtime: { getManifest: () => ({ version: '0.18.14' })", 1)
old = """  store.ledger = [{ recordId:'order:test', orderId:'113-0000000-0000000' }];
  store.backgroundScanState = { running:true };
  store.installedExtensionVersion = '0.16.0';
  await sandbox.ensureDevelopmentVersionState();
  assert(store.ledger === undefined, 'version change should wipe development ledger state');
  assert(store.backgroundScanState === undefined, 'version change should wipe crawl checkpoint state');
  assert(store.installedExtensionVersion === '0.17.0', 'version reset should store new manifest version');

  delete store.installedExtensionVersion;
  store.ledger = [{ recordId:'order:legacy', orderId:'113-1111111-1111111' }];
  store.backgroundScanState = { running:true };
  await sandbox.ensureDevelopmentVersionState('0.16.0');
  assert(store.ledger === undefined && store.backgroundScanState === undefined, 'upgrade previousVersion must wipe legacy state even before VERSION_KEY existed');
  assert(store.installedExtensionVersion === '0.17.0', 'legacy upgrade reset should persist v0.17 version key');

  console.log('strict crawl state-machine tests passed');
"""
new = """  const resumeOrderId = '113-7262857-4669069';
  const resumeUrl = 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/31/';
  const resumeDetailUrl = `https://www.amazon.com/your-orders/order-details?orderID=${resumeOrderId}`;
  store.ledger = [{ recordId:`order:${resumeOrderId}`, recordType:'order', orderId:resumeOrderId, orderDetailsUrl:resumeDetailUrl, detailScanComplete:true, orderDataComplete:true }];
  store.backgroundScanState = {
    running:true, paused:false, queue:[],
    currentJob:{ type:'detail', orderId:resumeOrderId, url:resumeDetailUrl, crawlManaged:true, crawlYear:2026, crawlPage:31, crawlPageKey:'2026:31', historyUrl:resumeUrl, priority:5 },
    crawl:{ active:true, phase:'details', years:[2026,2025], currentYear:2026, currentPage:31, currentHistoryUrl:resumeUrl, currentPageOrderIds:[resumeOrderId], currentPageCompleted:0, completedOrders:{}, seenOrders:{ [resumeOrderId]:{year:2026,page:31,pageKey:'2026:31'} }, seenPages:{'2026:31':resumeOrderId} }
  };
  store.arlWorkerTabId = 999;
  store.installedExtensionVersion = '0.18.13';
  await sandbox.ensureDevelopmentVersionState();
  assert(Array.isArray(store.ledger) && store.ledger[0].orderId === resumeOrderId, 'version migration must preserve development ledger state');
  assert(store.backgroundScanState?.crawl?.currentPage === 31, 'version migration must preserve crawl checkpoint page');
  assert(store.backgroundScanState?.currentJob?.orderId === resumeOrderId, 'version migration must preserve interrupted current job for recovery');
  assert(store.arlWorkerTabId === undefined, 'version migration must clear stale transient worker tab ID');
  assert(store.installedExtensionVersion === '0.18.14', 'version migration should store new manifest version');

  await sandbox.resumePersistedCrawl('test-version-update');
  state = store.backgroundScanState;
  assert(state.currentJob === null, 'resume must clear persisted interrupted currentJob after requeueing it');
  assert(state.queue.some(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeRecovered === true), 'resume must requeue the exact interrupted detail job');
  assert(!state.queue.some(j => j.type === 'history' && /pagination\\/1\\//.test(j.url || '')), 'interrupted-job recovery must not fall back to page 1');

  store.backgroundScanState = {
    running:false, paused:false, queue:[], currentJob:null,
    crawl:{ active:true, phase:'details', years:[2026,2025], currentYear:2026, currentPage:31, currentHistoryUrl:resumeUrl, currentPageOrderIds:[resumeOrderId], currentPageCompleted:1, completedOrders:{ [resumeOrderId]:{at:new Date().toISOString(),year:2026,page:31} }, seenOrders:{ [resumeOrderId]:{year:2026,page:31,pageKey:'2026:31'} }, seenPages:{'2026:31':resumeOrderId} }
  };
  await sandbox.startOrResumeFullScan({ restart:false, source:'manual-resume' });
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
  assert(state.crawl.ordersCompleted === 0, 'overlap refresh must not increment unique-order completion count');
  await sandbox.queueManagedHistoryResult({
    scannedUrl: resumeUrl, historySelectedYear:2026, historyYears:[2026,2025], historyOrderIds:[resumeOrderId],
    detailLinks:[{orderId:resumeOrderId,url:resumeDetailUrl}], records:[]
  }, { historyYear:2026, historyPage:31, crawlManaged:true, resumeRecovery:true, resumeExpectedFingerprint:resumeOrderId });
  state = store.backgroundScanState;
  assert(state.queue.filter(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeOverlapRefresh === true).length === 1, 'same overlap must not be refreshed repeatedly in one lifetime crawl');

  delete store.installedExtensionVersion;
  store.ledger = [{ recordId:'order:legacy', recordType:'order', orderId:'113-1111111-1111111' }];
  store.backgroundScanState = { running:true, crawl:{active:true,currentYear:2025,currentPage:12,currentHistoryUrl:'https://www.amazon.com/gp/your-account/order-history#time/2025/pagination/12/'} };
  await sandbox.ensureDevelopmentVersionState('0.18.13');
  assert(store.ledger?.[0]?.orderId === '113-1111111-1111111' && store.backgroundScanState?.crawl?.currentPage === 12, 'previousVersion migration must preserve legacy ledger/checkpoint even before VERSION_KEY existed');
  assert(store.installedExtensionVersion === '0.18.14', 'previousVersion migration should persist v0.18.14 version key');

  console.log('strict crawl state-machine tests passed');
"""
if old not in s:
    raise SystemExit('old destructive reset block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('v0.18.14 state-machine tests updated')
