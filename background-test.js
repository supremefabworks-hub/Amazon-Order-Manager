const fs = require('fs');
const vm = require('vm');

const noop = () => {};
const chrome = {
  storage: { local: { get: async () => ({}), set: async () => {}, remove: async () => {} }, onChanged: { addListener: noop } },
  alarms: { create: noop, onAlarm: { addListener: noop } },
  tabs: { onRemoved: { addListener: noop }, onUpdated: { addListener: noop, removeListener: noop } },
  runtime: { onMessage: { addListener: noop }, onStartup: { addListener: noop }, onInstalled: { addListener: noop } }
};
const sandbox = { chrome, URL, console, setTimeout: () => 0, clearTimeout: noop, Date, Math };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/background.js', 'utf8'), sandbox);

function assert(condition, message) { if (!condition) throw new Error(message); }

assert(
  sandbox.urlMatchesNavigationTarget(
    'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2026',
    'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2026&startIndex=10'
  ) === false,
  'old completed page must not satisfy a requested page-2 offset'
);
assert(
  sandbox.urlMatchesNavigationTarget(
    'https://www.amazon.com/your-orders/orders?orderFilter=year-2025&startIndex=10',
    'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2025&startIndex=10'
  ) === true,
  'Amazon may canonicalize the pathname while preserving requested filter/offset'
);
assert(
  sandbox.urlMatchesNavigationTarget(
    'https://www.amazon.com/your-orders/orders?orderFilter=year-2026&startIndex=10',
    'https://www.amazon.com/your-orders/orders?orderFilter=year-2025&startIndex=10'
  ) === false,
  'wrong year must not satisfy requested history navigation'
);
assert(
  sandbox.urlMatchesNavigationTarget(
    'https://www.amazon.com/your-orders/order-details?orderID=113-5152372-1721051',
    'https://www.amazon.com/your-orders/order-details?orderID=113-5152372-1721051&ref=foo'
  ) === true,
  'detail page must match by authoritative orderID'
);
assert(
  sandbox.historyPageChanged(
    { historyOrderIds: ['113-0000000-0000001','113-0000000-0000002'] },
    { historyOrderIds: ['113-0000000-0000001','113-0000000-0000002'] }
  ) === false,
  'same Order IDs must not count as pagination progress'
);
assert(
  sandbox.historyPageChanged(
    { historyOrderIds: ['113-0000000-0000001'] },
    { historyOrderIds: ['113-0000000-0000002'] }
  ) === true,
  'different Order IDs must count as pagination progress'
);
console.log('background navigation tests passed');

assert(
  sandbox.urlMatchesNavigationTarget(
    'https://www.amazon.com/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/1/',
    'https://www.amazon.com/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/2/'
  ) === false,
  'taught page 1 hash must not satisfy requested page 2 hash'
);
assert(
  sandbox.urlMatchesNavigationTarget(
    'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/2/',
    'https://www.amazon.com/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/2/'
  ) === true,
  'same taught year/page hash should match despite ref query differences'
);
assert(
  sandbox.historyYearFromUrl('https://www.amazon.com/gp/your-account/order-history#time/2025/pagination/3/') === 2025,
  'history year should parse from taught hash route'
);
assert(
  sandbox.historyPageIndexFromUrl('https://www.amazon.com/gp/your-account/order-history#time/2025/pagination/3/') === 3,
  'history page should parse from taught hash route'
);
assert(
  sandbox.normalizeUrl('https://www.amazon.com/gp/your-account/order-history?ref_=foo#time/2026/pagination/1/') !==
  sandbox.normalizeUrl('https://www.amazon.com/gp/your-account/order-history?ref_=bar#time/2026/pagination/2/'),
  'normalized history URLs must preserve page hash identity'
);
console.log('taught hash-route background tests passed');


const businessPage2 = sandbox.buildHistoryUrl('https://www.amazon.com/gp/your-account/order-history?ref_=foo#time/2026/pagination/1/', 2026, 2);
assert(businessPage2.includes('#time/2026/pagination/2/'), 'Business pagination must preserve the taught year/page hash route');
assert(!businessPage2.includes('startIndex='), 'Business pagination must not synthesize startIndex offsets');
assert(!businessPage2.includes('timeFilter=year-2026'), 'Business pagination must not switch to the legacy query contract');
assert(
  sandbox.urlMatchesNavigationTarget(
    'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/2/',
    businessPage2
  ) === true,
  'taught Business year/page URL should verify as the requested history page'
);
const legacyPage2 = sandbox.buildLegacyServerHistoryUrl('https://www.amazon.com/gp/your-account/order-history', 2026, 2);
assert(legacyPage2.includes('timeFilter=year-2026') && legacyPage2.includes('startIndex=10'), 'legacy server pagination remains available only for query-routed Amazon pages');
console.log('business-first pagination tests passed');


assert(sandbox.historyPageChanged(
  { scannedUrl:'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/1/', historyOrderIds:[] },
  { scannedUrl:'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/2/', historyOrderIds:[] }
) === false, 'URL change without visible Order-ID fingerprint must not count as pagination progress');
assert(typeof sandbox.syntheticDetailUrl === 'undefined', 'v0.17 must not expose a synthetic Order Details URL fallback');
console.log('v0.17 background regressions passed');


const backgroundSourceV01812 = fs.readFileSync(__dirname + '/background.js', 'utf8');
const contentSourceV01812 = fs.readFileSync(__dirname + '/content.js', 'utf8');
assert(backgroundSourceV01812.includes('const JOB_DELAY_MIN_MS = 75;') && backgroundSourceV01812.includes('const JOB_DELAY_MAX_MS = 250;'), 'v0.18.12 must use the approved smart-fast inter-job pacing');
assert(backgroundSourceV01812.includes('const READY_INITIAL_MIN_MS = 100;') && backgroundSourceV01812.includes('const READY_INITIAL_MAX_MS = 150;'), 'v0.18.12 readiness polling must start after a short 100-150 ms delay');
assert(backgroundSourceV01812.includes('const READY_POLL_MIN_MS = 75;') && backgroundSourceV01812.includes('const READY_POLL_MAX_MS = 125;') && backgroundSourceV01812.includes('const READY_TIMEOUT_MS = 700;'), 'v0.18.12 readiness polling bounds must stay explicit');
assert(backgroundSourceV01812.includes('const BURST_MIN_JOBS = 60;') && backgroundSourceV01812.includes('const BURST_MAX_JOBS = 90;'), 'normal burst size must be 60-90 serial jobs');
assert(backgroundSourceV01812.includes('const COOLDOWN_MIN_MS = 8000;') && backgroundSourceV01812.includes('const COOLDOWN_MAX_MS = 15000;'), 'normal cooldown must be 8-15 seconds');
assert(backgroundSourceV01812.includes('RATE_LIMIT_COOLDOWN_MIN_MS = 10 * 60 * 1000') && backgroundSourceV01812.includes('RATE_LIMIT_COOLDOWN_MAX_MS = 20 * 60 * 1000'), 'rate-limit cooldown safety must remain unchanged');
assert(backgroundSourceV01812.includes('const LOAD_TIMEOUT_MS = 45000;'), '45-second navigation timeout must remain unchanged');
assert(backgroundSourceV01812.includes('async function waitForWorkerReady') && backgroundSourceV01812.includes("type: 'ARL_WORKER_READY'"), 'rendered worker scans must use adaptive readiness polling');
assert(backgroundSourceV01812.includes('return { ready: false, timedOut: true, state: lastState };') && backgroundSourceV01812.includes("type: 'ARL_WORKER_SCAN'"), 'readiness timeout must fall through to the authoritative scan rather than accepting incomplete data');
assert(backgroundSourceV01812.includes('let processing = false;') && backgroundSourceV01812.includes('if (processing) return;'), 'crawler must remain single-job serial');
assert(contentSourceV01812.includes("message.type === 'ARL_WORKER_READY'") && contentSourceV01812.includes('canonical-detail-evidence') && contentSourceV01812.includes('history-order-fingerprint'), 'content script must expose job-specific readiness evidence');
assert(contentSourceV01812.includes('nextFingerprint === fingerprint') && contentSourceV01812.includes('stable >= 3'), 'history lazy-load stabilization must require repeated stable height and Order-ID fingerprint');
console.log('v0.18.12 adaptive smart-fast pacing regressions passed');


const backgroundSourceV0189 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(backgroundSourceV0189.includes("r?.orderDataComplete === true"), 'page completion must require fully processed order data');
assert(backgroundSourceV0189.includes('patchOrderProcessing'), 'background must persist order processing/error state');
assert(backgroundSourceV0189.includes("processingState: 'error'"), 'terminal detail failures must enter the Errors view state');
assert(backgroundSourceV0189.includes("processingState: 'retrying'"), 'transient detail failures must remain Processing while retrying');
console.log('v0.18.9 completion/error background regressions passed');


const backgroundSourceV01813 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(backgroundSourceV01813.includes('async function resetOrderForAuthoritativeRefresh(orderId)'), 'combined recovery must clear order-scoped derived data first');
assert(backgroundSourceV01813.includes("ledger.filter(record => record?.orderId !== id)"), 'reset must remove every stored record for the selected order ID');
assert(backgroundSourceV01813.includes("statusText: 'Reset for authoritative refresh'") && backgroundSourceV01813.includes("processingState: 'processing'"), 'reset must leave a minimal processing shell with the real route');
assert(backgroundSourceV01813.includes('previousCrawlCompletion') && backgroundSourceV01813.includes('restoreCrawlCompletionAfterAuthoritativeRefresh'), 'crawl completion must be removed during rebuild and restored only after success');
assert(backgroundSourceV01813.includes("message.type === 'ARL_RESET_REFRESH_ORDER'"), 'background must expose one combined reset-refresh message');
assert(!backgroundSourceV01813.includes("message.type === 'ARL_REFRESH_ORDER'"), 'old standalone refresh message path must be removed');
assert(backgroundSourceV01813.includes('while (processing && Date.now() < waitDeadline)') && backgroundSourceV01813.includes('processing = true'), 'manual rebuild must share the serial crawler lock');
assert(backgroundSourceV01813.includes("processingError: `reset-refresh:"), 'failed rebuild must retain an Errors-view shell');
assert(backgroundSourceV01813.includes('await chrome.tabs.remove(tabId)'), 'Reset & Refresh must close its temporary inactive Amazon tab before releasing the lock');
console.log('v0.18.13 reset-refresh background regressions passed');


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
