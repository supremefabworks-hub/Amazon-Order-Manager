const fs = require('fs');
function assert(condition, message) { if (!condition) throw new Error(message); }
const dashboard = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
const content = fs.readFileSync(__dirname + '/content.js', 'utf8');
const background = fs.readFileSync(__dirname + '/background.js', 'utf8');
const css = fs.readFileSync(__dirname + '/ui.css', 'utf8');
for (const label of ['Details</button>', 'Credit</button>', 'Reset</button>', 'Refresh</button>']) assert(dashboard.includes(label), `dashboard must render fixed ${label.split('<')[0]} action`);
assert(dashboard.includes("type: 'ARL_REFRESH_ORDER'"), 'Refresh button must request background-tab refresh');
assert(background.includes('async function forceRefreshOrder'), 'background worker must implement rendered forced refresh');
assert(background.includes("active: false"), 'forced refresh must use an inactive tab');
assert(content.includes('/\\/spr\\/returns\\/prep/i'), 'detail fetch must follow real return prep links');
assert(!dashboard.includes('return `https://www.amazon.com/your-orders/order-details?orderID='), 'dashboard must not synthesize canonical detail URLs');
assert(!background.includes('function syntheticDetailUrl'), 'background must not synthesize canonical detail URLs');
assert(css.includes('grid-template-columns: repeat(4, minmax(0, 1fr))'), 'actions must stay side-by-side in four fixed columns');
assert(css.includes('min-height: 36px'), 'actions must use enlarged click targets');
assert(css.includes('overflow-x: hidden'), 'ledger must continue forbidding horizontal order scrolling');
assert(dashboard.includes('groupReturnRecords'), 'dashboard must group child return records by Amazon return token');
assert(dashboard.includes('canonicalRefundTotal'), 'dashboard must prefer canonical Order Details Refund Total');
assert(!dashboard.includes('order?.detailScanComplete ? order?.refundAmount'), 'dashboard must never use generic order refund prose as canonical Refund Total');
assert(content.includes('applySingleReturnIdentityHint'), 'return-page refresh must preserve exact Order Details itemId identity across redirects');
assert(background.includes('returnItemId: link.returnItemId'), 'rendered per-order Refresh must pass exact return item identity to the worker scan');
assert(dashboard.includes("value === null || value === undefined || value === ''"), 'unknown money must render as unknown rather than $0.00');
assert(dashboard.includes('row.refundAmountMismatch || row.itemIdentityConflict || row.groupAmountConflict'), 'integrity-review orders must contribute their canonical expected refund to Needs Review totals');
assert(dashboard.includes('sourceExtensionVersion: chrome.runtime.getManifest()?.version'), 'bank bridge export must report the actual extension version');
assert(css.includes('v0.18.2 explicit multi-return child groups'), 'multi-return child status/amount metadata must have compact styling');
assert(dashboard.includes('refundAmountMismatch'), 'dashboard must flag child-return totals that exceed canonical refund total');
assert(dashboard.includes('Return ${index}'), 'dashboard must render distinct compact child return blocks');

assert(background.includes('gp\\/css\\/summary\\/edit\\.html'), 'background canonical validator must accept captured legacy Order Details route');
assert(content.includes('gp\\/css\\/summary\\/edit\\.html'), 'content detail fetch validator must accept captured legacy Order Details route');
assert(dashboard.includes('gp\\/css\\/summary\\/edit\\.html'), 'dashboard Details action must accept captured legacy Order Details route');
assert(background.includes("missingDetailUrls.join(', ')"), 'missing-detail hard stop must identify the exact missing Order IDs');
assert(dashboard.includes("itemIdentitySource === 'order-detail-return-link'"), 'return group display must prefer trusted Order Details identity');
assert(css.includes('.line-status .badge') && css.includes('white-space: normal'), 'long status badges must wrap instead of overlapping the order column');


assert(background.includes('terminalCancelledHistoryOrders'), 'background must have a narrow terminal cancelled-order gate');
assert(background.includes("historyTerminalState !== 'cancelled'"), 'background terminal gate must require explicit cancelled state');
assert(background.includes('Number(record.purchaseAmount) === 0'), 'background terminal gate must require exact zero-dollar total');
assert(dashboard.includes("stateKey = 'cancelled'"), 'dashboard must render terminal cancelled orders as Cancelled');
assert(dashboard.includes('Terminal history'), 'dashboard must distinguish terminal history capture from Detailed');
assert(dashboard.includes('orders complete'), 'dashboard checkpoint must include terminal-complete orders without calling them Detail captures');

console.log('ui regression tests passed');
