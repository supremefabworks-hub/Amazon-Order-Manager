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


const backgroundSourceV0187 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(backgroundSourceV0187.includes('const JOB_DELAY_MIN_MS = 175;') && backgroundSourceV0187.includes('const JOB_DELAY_MAX_MS = 455;'), 'v0.18.7 normal inter-job pacing should be about 30% faster');
assert(backgroundSourceV0187.includes('const LOAD_SETTLE_MIN_MS = 450;') && backgroundSourceV0187.includes('const LOAD_SETTLE_MAX_MS = 900;'), 'v0.18.7 page settle pacing should be about 30% faster');
assert(backgroundSourceV0187.includes('RATE_LIMIT_COOLDOWN_MIN_MS = 10 * 60 * 1000') && backgroundSourceV0187.includes('RATE_LIMIT_COOLDOWN_MAX_MS = 20 * 60 * 1000'), 'rate-limit cooldown safety must remain unchanged');
console.log('v0.18.7 pacing regression passed');
