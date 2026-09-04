const fs = require('fs');
const vm = require('vm');

const store = {};
const noop = () => {};
const chrome = {
  storage: {
    local: {
      get: async keys => {
        if (Array.isArray(keys)) return Object.fromEntries(keys.map(k => [k, store[k]]));
        return { ...store };
      },
      set: async obj => Object.assign(store, obj),
      remove: async keys => { for (const k of (Array.isArray(keys) ? keys : [keys])) delete store[k]; }
    },
    onChanged: { addListener: noop }
  },
  alarms: { create: noop, onAlarm: { addListener: noop } },
  tabs: { onRemoved: { addListener: noop }, onUpdated: { addListener: noop, removeListener: noop } },
  runtime: { getManifest: () => ({ version: '0.18.15' }), onMessage: { addListener: noop }, onStartup: { addListener: noop }, onInstalled: { addListener: noop } }
};
const sandbox = { chrome, URL, console, setTimeout: () => 0, clearTimeout: noop, Date, Math };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/background.js', 'utf8'), sandbox);
const assert = (cond, msg) => { if (!cond) throw new Error(msg); };

(async () => {
  await sandbox.startOrResumeFullScan({ restart: true, startYear: 2026 });
  let state = store.backgroundScanState;
  assert(state.crawl.active === true, 'full crawl should be active');
  assert(state.queue.length === 1 && state.queue[0].type === 'history', 'full crawl must start with one history page');
  assert(state.queue[0].url.includes('#time/2026/pagination/1/') && !state.queue[0].url.includes('startIndex='), 'first page must use the taught Amazon Business hash route');

  const ids = Array.from({length: 9}, (_,i) => `113-000000${i}-000000${i}`.replace('00000010','0000010'));
  const validIds = ['113-1000000-1000000','113-1000001-1000001','113-1000002-1000002','113-1000003-1000003','113-1000004-1000004','113-1000005-1000005','113-1000006-1000006','113-1000007-1000007','113-1000008-1000008'];
  await sandbox.queueManagedHistoryResult({
    scannedUrl: 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/1/',
    historySelectedYear: 2026,
    historyYears: [2026,2025,2024],
    detailLinks: validIds.map(orderId => ({ orderId, url: `https://www.amazon.com/your-orders/order-details?orderID=${orderId}` })),
    historyOrderIds: validIds
  }, { historyYear: 2026, historyPage: 1, crawlManaged: true });
  state = store.backgroundScanState;
  const details = state.queue.filter(j => j.type === 'detail');
  const advances = state.queue.filter(j => j.type === 'advance');
  assert(details.length === 9, 'every order on page must queue one Order Details job');
  assert(advances.length === 1, 'page must queue exactly one advance job');
  assert(Math.max(...details.map(j => j.priority)) < advances[0].priority, 'all details must run before page advance');
  assert(state.crawl.years.join(',') === '2026,2025,2024', 'years should be learned from Amazon year picker');
  assert(state.crawl.overlapCount === 0, 'first page must not count overlap');

  // Re-observing the same history page must not create false overlap counts or duplicate jobs.
  await sandbox.queueManagedHistoryResult({
    scannedUrl: 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/1/',
    historySelectedYear: 2026,
    historyYears: [2026,2025,2024],
    detailLinks: validIds.map(orderId => ({ orderId, url: `https://www.amazon.com/your-orders/order-details?orderID=${orderId}` })),
    historyOrderIds: validIds
  }, { historyYear: 2026, historyPage: 1, crawlManaged: true });
  state = store.backgroundScanState;
  assert(state.crawl.overlapCount === 0, 'same-page rescan must not be counted as overlap');
  assert(state.queue.filter(j => j.type === 'detail').length === 9, 'same-page rescan must not duplicate detail jobs');

  let missingLinkStopped = false;
  try {
    await sandbox.queueManagedHistoryResult({ scannedUrl:'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/2/', historySelectedYear:2026, historyYears:[2026,2025], historyOrderIds:['113-2000000-2000000'], detailLinks:[] }, { historyYear:2026, historyPage:2, crawlManaged:true });
  } catch (error) { missingLinkStopped = /Missing real View order details URL/.test(String(error.message || error)); }
  assert(missingLinkStopped, 'managed crawl must stop if a visible order lacks its real View order details URL');



  // A fully cancelled $0.00 order may legitimately have no Order Details link. Its own scoped
  // history card is terminal evidence and must not block the page, while normal orders still do.
  await sandbox.startOrResumeFullScan({ restart: true, startYear: 2026 });
  const cancelledId = '112-3886192-2097013';
  const normalId = '113-3000000-3000000';
  const page6Url = 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/6/';
  await sandbox.queueManagedHistoryResult({
    scannedUrl: page6Url,
    historySelectedYear: 2026,
    historyYears: [2026,2025],
    historyOrderIds: [cancelledId, normalId],
    detailLinks: [{ orderId: normalId, url: `https://www.amazon.com/your-orders/order-details?orderID=${normalId}` }],
    records: [{
      recordId: `order:${cancelledId}`, recordType: 'order', orderId: cancelledId,
      purchaseAmount: 0, statusText: 'Cancelled', historyTerminalComplete: true,
      historyTerminalState: 'cancelled', historyTerminalSource: 'order-history-card',
      orderDetailsUrl: null, sourceUrl: page6Url
    }]
  }, { historyYear: 2026, historyPage: 6, crawlManaged: true });
  state = store.backgroundScanState;
  assert(Boolean(state.crawl.completedOrders[cancelledId]), 'proven terminal cancelled order must count complete without Detail URL');
  assert(state.crawl.completedOrders[cancelledId].terminalState === 'cancelled', 'terminal completion must record cancelled state');
  assert(state.crawl.currentPageCompleted === 1, 'page completion count must include terminal cancelled order');
  assert(state.queue.filter(j => j.type === 'detail' && j.orderId === normalId).length === 1, 'normal order must still queue its real Detail URL');
  assert(state.queue.filter(j => j.type === 'detail' && j.orderId === cancelledId).length === 0, 'terminal cancelled order must not queue a nonexistent Detail URL');

  await sandbox.startOrResumeFullScan({ restart: true, startYear: 2026 });
  let nonzeroCancelledStopped = false;
  try {
    await sandbox.queueManagedHistoryResult({
      scannedUrl: page6Url, historySelectedYear: 2026, historyYears: [2026], historyOrderIds: [cancelledId], detailLinks: [],
      records: [{ recordId:`order:${cancelledId}`, recordType:'order', orderId:cancelledId, purchaseAmount:12.34, statusText:'Cancelled', historyTerminalComplete:true, historyTerminalState:'cancelled', orderDetailsUrl:null, sourceUrl:page6Url }]
    }, { historyYear:2026, historyPage:6, crawlManaged:true });
  } catch (error) { nonzeroCancelledStopped = /Missing real View order details URL/.test(String(error.message || error)); }
  assert(nonzeroCancelledStopped, 'nonzero/invalid cancelled record must not bypass strict missing-Detail stop');


  const resumeOrderId = '113-7262857-4669069';
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
  assert(store.installedExtensionVersion === '0.18.15', 'version migration should store v0.18.15');

  await sandbox.resumePersistedCrawl('test-version-update');
  state = store.backgroundScanState;
  assert(state.currentJob === null, 'resume must clear persisted interrupted currentJob after requeueing it');
  assert(state.queue.some(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeRecovered === true), 'resume must requeue the exact interrupted detail job');
  assert(!state.queue.some(j => j.type === 'history' && /pagination\/1\//.test(j.url || '')), 'interrupted-job recovery must not fall back to page 1');

  store.backgroundScanState = {
    running:false, paused:false, queue:[], currentJob:null,
    crawl:{ active:true, phase:'details', years:[2026,2025], currentYear:2026, currentPage:31, currentHistoryUrl:resumeUrl, currentPageOrderIds:[resumeOrderId], currentPageCompleted:1, ordersCompleted:1, completedOrders:{ [resumeOrderId]:{at:new Date().toISOString(),year:2026,page:31} }, seenOrders:{ [resumeOrderId]:{year:2026,page:31,pageKey:'2026:31'} }, seenPages:{'2026:31':resumeOrderId} }
  };
  await sandbox.startOrResumeFullScan({ restart:false, source:'manual-resume', startYear:2026 });
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

  // Ledger-backed recovery: completed canonical data is a secondary identity index when crawl
  // metadata is missing. It must be adopted without counting a new order, then refreshed once.
  store.ledger = [{ recordId:`order:${resumeOrderId}`, recordType:'order', orderId:resumeOrderId, orderDetailsUrl:resumeDetailUrl, detailScanComplete:true, orderDataComplete:true, lastScannedAt:new Date().toISOString() }];
  store.backgroundScanState = {
    running:false, paused:false, queue:[], currentJob:null,
    crawl:{ active:true, phase:'resume', years:[2026], currentYear:2026, currentPage:31, currentHistoryUrl:resumeUrl, currentPageOrderIds:[], completedOrders:{}, seenOrders:{}, seenPages:{}, overlapRefreshedOrders:{} }
  };
  await sandbox.queueManagedHistoryResult({
    scannedUrl:resumeUrl, historySelectedYear:2026, historyYears:[2026], historyOrderIds:[resumeOrderId], detailLinks:[], records:[]
  }, { historyYear:2026, historyPage:31, crawlManaged:true, resumeRecovery:true });
  state = store.backgroundScanState;
  assert(state.crawl.completedOrders[resumeOrderId]?.adoptedFromLedger === true, 'known canonical ledger order must be adopted when crawl completion metadata is missing');
  assert(state.crawl.ordersCompleted === 1, 'ledger adoption must derive unique completion count without double-counting');
  assert(state.queue.some(j => j.type === 'detail' && j.orderId === resumeOrderId && j.resumeOverlapRefresh === true), 'ledger-adopted order must receive one authoritative overlap refresh');
  assert(state.queue.filter(j => j.type === 'detail' && j.orderId === resumeOrderId && !j.resumeOverlapRefresh).length === 0, 'ledger-adopted order must not be treated as a new canonical detail job');

  delete store.installedExtensionVersion;
  store.ledger = [{ recordId:'order:legacy', recordType:'order', orderId:'113-1111111-1111111' }];
  store.backgroundScanState = { running:true, crawl:{active:true,currentYear:2025,currentPage:12,currentHistoryUrl:'https://www.amazon.com/gp/your-account/order-history#time/2025/pagination/12/'} };
  await sandbox.ensureDevelopmentVersionState('0.18.13');
  assert(store.ledger?.[0]?.orderId === '113-1111111-1111111' && store.backgroundScanState?.crawl?.currentPage === 12, 'previousVersion migration must preserve legacy ledger/checkpoint even before VERSION_KEY existed');
  assert(store.installedExtensionVersion === '0.18.15', 'previousVersion migration should persist v0.18.15 version key');

  console.log('strict crawl state-machine tests passed');
})().catch(err => { console.error(err); process.exit(1); });
