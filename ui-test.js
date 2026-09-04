const fs = require('fs');
function assert(condition, message) { if (!condition) throw new Error(message); }
const dashboard = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
const content = fs.readFileSync(__dirname + '/content.js', 'utf8');
const background = fs.readFileSync(__dirname + '/background.js', 'utf8');
const css = fs.readFileSync(__dirname + '/ui.css', 'utf8');
for (const label of ['Details</button>', 'Credit</button>', 'Reset & Refresh</button>']) assert(dashboard.includes(label), `dashboard must render fixed ${label.split('<')[0]} action`);
assert(dashboard.includes("type: 'ARL_RESET_REFRESH_ORDER'"), 'Reset & Refresh must request the authoritative rebuild path');
assert(background.includes('async function forceResetRefreshOrder'), 'background worker must implement authoritative reset-and-refresh recovery');
assert(background.includes("active: false"), 'forced refresh must use an inactive tab');
assert(content.includes('/\\/spr\\/returns\\/prep/i'), 'detail fetch must follow real return prep links');
assert(!dashboard.includes('return `https://www.amazon.com/your-orders/order-details?orderID='), 'dashboard must not synthesize canonical detail URLs');
assert(!background.includes('function syntheticDetailUrl'), 'background must not synthesize canonical detail URLs');
assert(css.includes('grid-template-columns: repeat(3, minmax(0, 1fr))'), 'actions must stay side-by-side in three fixed columns');
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

const parserSourceV0185 = fs.readFileSync(__dirname + '/parser.js', 'utf8');
assert(parserSourceV0185.includes("pageType === 'return' ? [] : extractAsins(container)"), 'broad return-page product identity must stay disabled');
assert(parserSourceV0185.includes('structuralHistoryContainerForOrder'), 'no-detail history cards must have structural scoping');
assert(fs.readFileSync(__dirname + '/storage.js', 'utf8').includes('itemAsinEvidenceSource'), 'identity conflicts must require bound ASIN evidence');


assert(fs.readFileSync(__dirname + '/dashboard.html', 'utf8').includes('item-model.js'), 'dashboard must load the pure per-product item model');
assert(dashboard.includes('orderProductStatusMarkup'), 'dashboard must render purchased products independently inside each order');
assert(dashboard.includes("'Not returned'"), 'non-returned purchased products must stay visible with Not returned state');
assert(dashboard.includes('returnedProductCount'), 'order summary must expose how many purchased products were returned');
assert(css.includes('v0.18.7 per-product order status'), 'per-product order rows must have responsive no-horizontal-scroll styling');

assert(dashboard.includes('row.strongUnmatchedReturnIdentity'), 'strong unmatched returned items must contribute canonical expected refund to Needs Review dollars');


const dashboardV0188 = fs.readFileSync(__dirname + '/dashboard.js','utf8');
const storageV0188 = fs.readFileSync(__dirname + '/storage.js','utf8');
const cssV0188 = fs.readFileSync(__dirname + '/ui.css','utf8');
assert(dashboardV0188.includes("['received', 'Return received'"), 'dashboard must render Return received as its own stage');
assert(dashboardV0188.includes('storage.isBankCreditConfirmed(ret)'), 'Bank credited must use bank evidence only');
assert(dashboardV0188.includes('Bank/Amazon conflict'), 'dashboard must expose bank/Amazon conflict');
assert(dashboardV0188.includes("statusLabel = 'Amazon credited'"), 'bank match must not promote Amazon row to credited');
assert(storageV0188.includes('function hasAmazonBankConflict'), 'storage must separate Amazon/bank states');
assert(cssV0188.includes('repeat(5, minmax(0, 1fr))'), 'lifecycle must use five Amazon stages');
console.log('v0.18.8 Amazon/bank separation UI regressions passed');


const dashboardHtmlV0189 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
const dashboardSourceV0189 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
assert(!dashboardHtmlV0189.includes('data-view="processing"') && dashboardHtmlV0189.includes('data-view="errors"'), 'Processing must remain internal while Errors remains user-facing');
for (const id of ['statusFilter','yearFilter','cardFilter','sortOrder']) assert(dashboardHtmlV0189.includes(`id="${id}"`), `dashboard must render ${id}`);
assert(dashboardSourceV0189.includes("currentView === 'all' && !row.dataComplete"), 'All orders must hide incomplete records');
assert(dashboardSourceV0189.includes('authoritativeReturnCapture === true'), 'completed orders with return links must prefer authoritative return records');
assert(dashboardSourceV0189.includes("currentView === 'errors' && !row.processingError"), 'Errors view must be driven by persisted processing errors');
assert(dashboardSourceV0189.includes("mode === 'order_high'") && dashboardSourceV0189.includes("mode === 'refund_low'"), 'sort controls must support monetary ordering');
assert(dashboardSourceV0189.includes('...(row.asins || [])'), 'text search must include ASIN evidence');
console.log('v0.18.9 complete-ledger query UI regressions passed');


const dashboardHtmlV01810 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
const dashboardSourceV01810 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
for (const view of ['all','returns','needs_review','errors']) assert(dashboardHtmlV01810.includes(`data-view="${view}"`), `v0.18.10 must retain ${view} navigation`);
assert(!dashboardHtmlV01810.includes('data-view="processing"'), 'Processing must remain internal and not be a user-facing tab');
assert(dashboardHtmlV01810.includes('>Orders <') && dashboardHtmlV01810.includes('>Return review <'), 'navigation labels must be Orders and Return review');
assert(!dashboardSourceV01810.includes("currentView === 'processing'"), 'dashboard must not expose a Processing view');
assert((dashboardSourceV01810.match(/<span>Complete orders<\/span>/g) || []).length === 1, 'dashboard must render exactly one Complete orders metric');
assert(!dashboardSourceV01810.includes('<span>Order details</span>'), 'redundant Order details metric must be removed');
assert(!dashboardSourceV01810.includes('<span>Processing</span>'), 'Processing top metric must be removed');
assert(dashboardSourceV01810.includes('captured order total · fully processed canonical orders'), 'Complete orders metric must combine count meaning and captured-dollar context');
assert(dashboardSourceV01810.includes('<span>Return review</span>'), 'review stat must use Return review label');
console.log('v0.18.10 consolidated dashboard metrics regressions passed');


const parserV01811 = fs.readFileSync(__dirname + '/parser.js', 'utf8');
const dashboardV01811 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
const htmlV01811 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
assert(parserV01811.includes("statusLinks.filter(link => link.replacementOnly === true)"), 'replacement-only management links must be separated from true return links');
assert(parserV01811.includes('replacementNoReturnRequired'), 'parser must retain explicit no-return-required replacement evidence');
assert(dashboardV01811.includes("stateKey = 'replacement'"), 'replacement-only orders must have replacement status rather than Return detected');
assert(dashboardV01811.includes("value === 'replacement'"), 'replacement orders must be filterable');
assert(htmlV01811.includes('<option value="replacement">Replacement</option>'), 'status filter must include Replacement');
assert(dashboardV01811.includes("item.replacementNoReturnRequired ? 'No return required'"), 'product UI must expose no-return-required replacement evidence');
console.log('v0.18.11 replacement UI regressions passed');


const dashboardHtmlV01813 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
const dashboardJsV01813 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
assert(!dashboardHtmlV01813.includes('AMAZON REFUND LEDGER · v0.16'), 'dashboard must not hard-code stale v0.16 text');
assert(dashboardHtmlV01813.includes('id="ledgerVersion"'), 'dashboard must expose a dynamic version host');
assert(dashboardJsV01813.includes('chrome.runtime.getManifest()') && dashboardJsV01813.includes('manifest.version_name || manifest.version'), 'dashboard version must come from the installed manifest');
assert(dashboardJsV01813.includes('data-reset-refresh-order') && dashboardJsV01813.includes('Reset & Refresh'), 'order row must expose one combined Reset & Refresh action');
assert(!dashboardJsV01813.includes('data-refresh-order=') && !dashboardJsV01813.includes('data-action="reset"'), 'separate Reset and Refresh controls must be removed');
assert(dashboardJsV01813.includes("type: 'ARL_RESET_REFRESH_ORDER'"), 'combined button must call the authoritative rebuild path');
console.log('v0.18.13 reset-refresh/version UI regressions passed');


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
