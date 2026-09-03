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
  runtime: { onMessage: { addListener: noop }, onStartup: { addListener: noop }, onInstalled: { addListener: noop } }
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

  console.log('strict crawl state-machine tests passed');
})().catch(err => { console.error(err); process.exit(1); });
