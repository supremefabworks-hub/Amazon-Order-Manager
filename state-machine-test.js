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
  runtime: { getManifest: () => ({ version: '0.17.0' }), onMessage: { addListener: noop }, onStartup: { addListener: noop }, onInstalled: { addListener: noop } }
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


  store.ledger = [{ recordId:'order:test', orderId:'113-0000000-0000000' }];
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
})().catch(err => { console.error(err); process.exit(1); });
