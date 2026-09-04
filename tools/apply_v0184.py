from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding='utf-8')

def write(path, text):
    (ROOT / path).write_text(text, encoding='utf-8')

def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)

# Version bump.
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.4'
manifest['version_name'] = '0.18.4'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
package = json.loads(read('package.json'))
package['version'] = '0.18.4'
write('package.json', json.dumps(package, indent=2) + '\n')

# Parser: introduce a narrow, evidence-based terminal cancellation state for Order History cards.
p = read('parser.js')
helper = r'''
  function findHistoryCardTotal(text) {
    const normalized = normalizeText(text);
    const match = normalized.match(/(?:^|\n)\s*Total\s*(?:\n\s*)?\$\s*([0-9,]+(?:\.\d{2})?)\s*(?:$|\n)/im);
    if (!match) return null;
    const value = Number(match[1].replace(/,/g, ''));
    return Number.isFinite(value) ? value : null;
  }

  function terminalCancelledHistoryEvidence(text, orderId) {
    const normalized = normalizeText(text);
    const ids = extractOrderIds(normalized);
    const exactOrder = ids.length === 1 && ids[0] === String(orderId || '');
    const cancelled = /(?:^|\n)\s*cancel(?:led|ed)\s*(?:$|\n)/im.test(normalized);
    const total = findHistoryCardTotal(normalized);
    return {
      complete: Boolean(exactOrder && cancelled && total === 0),
      cancelled,
      exactOrder,
      total
    };
  }
'''
p = once(p, "\n  function findOrderRefundTotal(text) {", helper + "\n  function findOrderRefundTotal(text) {", 'insert terminal cancellation helpers')
p = once(
    p,
    "    const detailPage = isOrderDetailPage(url);\n    const extractedOrderIds = extractOrderIds(bodyText);",
    "    const detailPage = isOrderDetailPage(url);\n    const historyPage = isOrderHistoryPage(doc, url);\n    const extractedOrderIds = extractOrderIds(bodyText);",
    'cache history page classification'
)
p = once(
    p,
    "      let container = isOrderHistoryPage(doc, url) ? historyContainerForOrder(doc, orderId) : closestContainerForOrder(doc, orderId);",
    "      let container = historyPage ? historyContainerForOrder(doc, orderId) : closestContainerForOrder(doc, orderId);",
    'history container uses cached page flag'
)
p = once(
    p,
    "      if (domNames.length && !(pageType === 'return' && record.itemNames?.length)) record.itemNames = domNames;\n      record.asins = asins;\n\n      if (detailPage && record.recordType === 'order') {",
    "      if (domNames.length && !(pageType === 'return' && record.itemNames?.length)) record.itemNames = domNames;\n      record.asins = asins;\n\n      if (historyPage && record.recordType === 'order' && !detailByOrder.get(orderId)) {\n        const terminal = terminalCancelledHistoryEvidence(context, orderId);\n        if (record.purchaseAmount == null && terminal.total != null) record.purchaseAmount = terminal.total;\n        if (terminal.complete) {\n          record.historyTerminalComplete = true;\n          record.historyTerminalState = 'cancelled';\n          record.historyTerminalSource = 'order-history-card';\n          record.statusText = 'Cancelled';\n        }\n      }\n\n      if (detailPage && record.recordType === 'order') {",
    'mark terminal cancelled history records'
)
p = once(
    p,
    "    findOrderTotal,\n    findRefundAmount,",
    "    findOrderTotal,\n    findHistoryCardTotal,\n    terminalCancelledHistoryEvidence,\n    findRefundAmount,",
    'export cancellation helpers'
)
write('parser.js', p)

# Background crawler: a proven terminal cancellation can satisfy the page gate without pretending
# that an Order Details page was captured.
b = read('background.js')
terminal_helper = r'''
function terminalCancelledHistoryOrders(result) {
  const out = new Map();
  const pageUrl = String(result?.scannedUrl || '');
  if (!isOrderHistoryUrl(pageUrl)) return out;
  for (const record of result?.records || []) {
    const orderId = String(record?.orderId || '').trim();
    const sourceUrl = String(record?.sourceUrl || pageUrl);
    const exactCancelled = /^(?:cancelled|canceled)$/i.test(String(record?.statusText || '').trim());
    const zeroTotal = record?.purchaseAmount !== null && record?.purchaseAmount !== undefined && record?.purchaseAmount !== '' && Number(record.purchaseAmount) === 0;
    if (!/^\d{3}-\d{7}-\d{7}$/.test(orderId)) continue;
    if (!isOrderHistoryUrl(sourceUrl)) continue;
    if (record?.recordType !== 'order' || record?.historyTerminalComplete !== true || record?.historyTerminalState !== 'cancelled') continue;
    if (!exactCancelled || !zeroTotal || record?.orderDetailsUrl) continue;
    out.set(orderId, record);
  }
  return out;
}
'''
b = once(b, "\nasync function queueManagedHistoryResult(result, job) {", terminal_helper + "\nasync function queueManagedHistoryResult(result, job) {", 'insert terminal order gate helper')
b = once(
    b,
    "  const links = uniqueDetailLinks(result);\n  const pageOrderIds = historyOrderIdSet(result);\n  if (!pageOrderIds.length) throw new Error(`No visible Amazon Order IDs were found on ${year} page ${page}`);\n  const linkByOrder = new Map(links.map(link => [link.orderId, link]));\n  const missingDetailUrls = pageOrderIds.filter(orderId => !linkByOrder.has(orderId));\n  if (missingDetailUrls.length) throw new Error(`Missing real View order details URL for ${missingDetailUrls.length} order(s) on ${year} page ${page}: ${missingDetailUrls.join(', ')}. The crawler stopped rather than inventing canonical URLs.`);\n  const orderedLinks = pageOrderIds.map(orderId => linkByOrder.get(orderId));\n  crawl.currentPageOrderIds = pageOrderIds;\n  crawl.currentPageCompleted = 0;",
    "  const links = uniqueDetailLinks(result);\n  const terminalByOrder = terminalCancelledHistoryOrders(result);\n  const pageOrderIds = historyOrderIdSet(result);\n  if (!pageOrderIds.length) throw new Error(`No visible Amazon Order IDs were found on ${year} page ${page}`);\n  const linkByOrder = new Map(links.map(link => [link.orderId, link]));\n  const missingDetailUrls = pageOrderIds.filter(orderId => !linkByOrder.has(orderId) && !terminalByOrder.has(orderId));\n  if (missingDetailUrls.length) throw new Error(`Missing real View order details URL for ${missingDetailUrls.length} order(s) on ${year} page ${page}: ${missingDetailUrls.join(', ')}. The crawler stopped rather than inventing canonical URLs.`);\n  const orderedLinks = pageOrderIds.map(orderId => linkByOrder.get(orderId)).filter(Boolean);\n  crawl.currentPageOrderIds = pageOrderIds;\n  crawl.currentPageCompleted = 0;",
    'allow only proven terminal cancellations through missing-detail gate'
)
b = once(
    b,
    "    crawl.seenPages[pageKey] = fingerprint;\n  }\n\n  const existingKeys = new Set(state.queue.map(jobKey));",
    "    crawl.seenPages[pageKey] = fingerprint;\n  }\n\n  for (const orderId of pageOrderIds) {\n    if (!terminalByOrder.has(orderId) || crawl.completedOrders[orderId]) continue;\n    crawl.completedOrders[orderId] = { at: nowIso(), year, page, terminalState: 'cancelled', source: 'order-history-card' };\n    crawl.ordersCompleted = (crawl.ordersCompleted || 0) + 1;\n    crawl.lastCompletedOrderId = orderId;\n    crawl.lastCompletedAt = nowIso();\n  }\n  crawl.currentPageCompleted = pageOrderIds.filter(orderId => crawl.completedOrders[orderId]).length;\n\n  const existingKeys = new Set(state.queue.map(jobKey));",
    'count terminal cancellation as managed crawl completion'
)
b = once(
    b,
    "  if (job.type === 'history' && job.crawlManaged) {\n    const links = uniqueDetailLinks(result);\n    if (!links.length) throw new Error(`No orders were found on ${job.historyYear || ''} page ${job.historyPage || ''}`.trim());\n    await queueManagedHistoryResult(result, job);",
    "  if (job.type === 'history' && job.crawlManaged) {\n    const pageOrderIds = historyOrderIdSet(result);\n    if (!pageOrderIds.length) throw new Error(`No orders were found on ${job.historyYear || ''} page ${job.historyPage || ''}`.trim());\n    await queueManagedHistoryResult(result, job);",
    'all-terminal history page remains a valid page'
)
b = b.replace('    // Page is complete only after every order on it has a Detail page capture.\n', '    // Page is complete only after every order has either a Detail capture or proven terminal cancellation.\n', 1)
write('background.js', b)

# Dashboard: terminal cancellation is not "Detail queued" and cannot expose Details/Refresh when no
# canonical URL exists.
d = read('dashboard.js')
d = once(
    d,
    "      const hasReturn = returnRecords.length > 0;\n      const allCredited = hasReturn && returnRecords.every(r => storage.isCreditConfirmed(r));",
    "      const hasReturn = returnRecords.length > 0;\n      const terminalCancelled = Boolean(order?.historyTerminalComplete === true && order?.historyTerminalState === 'cancelled');\n      const allCredited = hasReturn && returnRecords.every(r => storage.isCreditConfirmed(r));",
    'dashboard terminal cancellation flag'
)
d = once(
    d,
    "      if (manualReconciled) { stateKey = 'reconciled'; statusLabel = 'Reconciled'; }\n      else if (needsReview) {",
    "      if (terminalCancelled && !hasReturn) { stateKey = 'cancelled'; statusLabel = 'Cancelled'; }\n      else if (manualReconciled) { stateKey = 'reconciled'; statusLabel = 'Reconciled'; }\n      else if (needsReview) {",
    'dashboard cancelled state'
)
d = once(
    d,
    "        orderId, order, returns: returnRecords, returnGroups, hasReturn, needsReview, stateKey, statusLabel,",
    "        orderId, order, returns: returnRecords, returnGroups, hasReturn, needsReview, terminalCancelled, stateKey, statusLabel,",
    'include terminal flag in row'
)
d = once(
    d,
    "    if (row.stateKey === 'purchase') return row.detailComplete ? 'Order' : 'Order queued';\n    if (row.stateKey === 'needs_review') return row.statusLabel || 'Needs review';",
    "    if (row.stateKey === 'purchase') return row.detailComplete ? 'Order' : 'Order queued';\n    if (row.stateKey === 'cancelled') return 'Cancelled';\n    if (row.stateKey === 'needs_review') return row.statusLabel || 'Needs review';",
    'cancelled badge label'
)
d = once(
    d,
    "      const detailBadge = row.detailComplete\n        ? `<span class=\"badge badge-reconciled\">Detailed</span>`\n        : '<span class=\"badge\">Detail queued</span>';",
    "      const detailBadge = row.terminalCancelled\n        ? `<span class=\"badge\">Terminal history</span>`\n        : row.detailComplete\n          ? `<span class=\"badge badge-reconciled\">Detailed</span>`\n          : '<span class=\"badge\">Detail queued</span>';",
    'terminal cancellation detail badge'
)
d = d.replace('`${doneOnPage}/${pageCount || \'?\'} details complete', '`${doneOnPage}/${pageCount || \'?\'} orders complete', 1)
write('dashboard.js', d)

# Popup checkpoint wording must include terminal-complete orders rather than claiming all were Detail captures.
pop = read('popup.js')
pop = once(pop, "`${crawl.currentPageCompleted || 0}/${pageOrders || '?'} order details", "`${crawl.currentPageCompleted || 0}/${pageOrders || '?'} orders complete", 'popup terminal-aware checkpoint label')
write('popup.js', pop)

# Parser regressions: exact cancelled + exact zero total is terminal; nonzero/ambiguous cases are not.
t = read('parser-test.js')
parser_tests = r'''

// v0.18.4 terminal cancelled-order regressions
const cancelledOrderId = '112-3886192-2097013';
const cancelledCardText = `Order placed\nJune 10, 2026\nTotal\n$0.00\nPlaced by\nVadya\nOrder # ${cancelledOrderId}\nCancelled\nHHZL Rubber Edge Trim T Molding Seal Strip`;
const cancelledEvidence = p.terminalCancelledHistoryEvidence(cancelledCardText, cancelledOrderId);
assert(cancelledEvidence.complete === true, 'exact Cancelled + $0.00 + same Order ID must be a terminal history order');
assert(cancelledEvidence.total === 0, 'terminal cancellation must preserve exact $0.00 order total');
assert(p.terminalCancelledHistoryEvidence(cancelledCardText.replace('$0.00', '$12.34'), cancelledOrderId).complete === false, 'nonzero cancelled order must still require Order Details');
assert(p.terminalCancelledHistoryEvidence(cancelledCardText.replace('\nCancelled\n', '\nCancellation requested\n'), cancelledOrderId).complete === false, 'ambiguous cancellation prose must not satisfy terminal gate');
assert(p.terminalCancelledHistoryEvidence(cancelledCardText.replace(cancelledOrderId, '112-0000000-0000000'), cancelledOrderId).complete === false, 'terminal evidence must be bound to the same visible Order ID');
console.log('v0.18.4 terminal cancellation parser regressions passed');
'''
if 'v0.18.4 terminal cancellation parser regressions passed' not in t:
    t += parser_tests
write('parser-test.js', t)

# Managed crawl state-machine regression with the live cancelled-order shape.
st = read('state-machine-test.js')
needle = "  store.ledger = [{ recordId:'order:test', orderId:'113-0000000-0000000' }];"
state_tests = r'''

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
'''
if 'proven terminal cancelled order must count complete' not in st:
    st = once(st, needle, state_tests + '\n\n' + needle, 'insert terminal cancellation state-machine tests')
write('state-machine-test.js', st)

# Static UI/runtime invariants.
u = read('ui-test.js')
ui_tests = r'''
assert(background.includes('terminalCancelledHistoryOrders'), 'background must have a narrow terminal cancelled-order gate');
assert(background.includes("historyTerminalState !== 'cancelled'"), 'background terminal gate must require explicit cancelled state');
assert(background.includes('Number(record.purchaseAmount) === 0'), 'background terminal gate must require exact zero-dollar total');
assert(dashboard.includes("stateKey = 'cancelled'"), 'dashboard must render terminal cancelled orders as Cancelled');
assert(dashboard.includes('Terminal history'), 'dashboard must distinguish terminal history capture from Detailed');
assert(dashboard.includes('orders complete'), 'dashboard checkpoint must include terminal-complete orders without calling them Detail captures');
'''
if "background.includes('terminalCancelledHistoryOrders')" not in u:
    u = u.replace("\nconsole.log('ui regression tests passed');", "\n" + ui_tests + "\nconsole.log('ui regression tests passed');")
write('ui-test.js', u)

# Durable docs/handoff.
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.3 candidate for Issue #17.**', '**Current source baseline: v0.18.4 candidate for Issue #19.**', 1)
readme = readme.replace('4. Root v0.18.2 is the active source after PR #16 merges.', '4. Root v0.18.4 is the active candidate for the terminal-cancelled-order live fix.', 1)
section = r'''

## v0.18.4 terminal cancelled-order handling

Amazon can render a fully cancelled `$0.00` order in Order History without any `View order details` URL. v0.18.4 adds a narrow terminal-history exception: only a scoped history card proving the same Order ID, an exact `Cancelled`/`Canceled` state, an exact `$0.00` total, and no real Order Details link may satisfy the managed crawl page gate. It is saved with `historyTerminalComplete=true` / `historyTerminalState=cancelled`, remains `detailScanComplete=false`, counts toward lifetime unique-order completion, and renders as `Cancelled` / `Terminal history` with Details and Refresh disabled. Any normal, ambiguous, nonzero, or unknown-total missing-link order still hard-stops the crawler rather than inventing a URL.

Issue #19 tracks live acceptance using order `112-3886192-2097013` as the observed case. This release is also intended as the automatic updater test from a fresh v0.18.3 installation on the second Windows PC.
'''
if '## v0.18.4 terminal cancelled-order handling' not in readme:
    readme += section
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
if 'v0.18.4 terminal cancelled-order handling' not in handoff:
    handoff += '\n\n## v0.18.4 terminal cancelled-order handling\n\nLive v0.18.3 stopped on 2026 page 6 because order `112-3886192-2097013` is explicitly Cancelled, totals `$0.00`, and has no real Order Details link. v0.18.4 treats only that strongly proven terminal history-card shape as complete for the crawl gate without setting `detailScanComplete`. Normal missing-detail orders still stop. Issue #19 is the live tracker. The second PC should test unattended `0.18.3 -> 0.18.4` update; do not reinstall or manually Reload for that proof.\n'
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
if 'v0.18.4 terminal cancelled order' not in testing:
    testing += '\n\n## v0.18.4 terminal cancelled order\n\n1. Start from a clean v0.18.4 development ledger and run the lifetime scan.\n2. On 2026 page 6, order `112-3886192-2097013` must be accepted from its own history card only when it shows the same Order ID, exact Cancelled/Canceled state, and `$0.00` Total with no Detail URL.\n3. The row must show `Cancelled`, `$0.00`, `Terminal history`; `Detailed` must not appear and Details/Refresh must be disabled.\n4. The crawler must continue to the next page/year instead of stopping on that order.\n5. A synthetic/nonzero/ambiguous cancellation fixture without a Detail URL must still stop with the exact missing Order ID.\n6. For updater acceptance on the second PC, start at v0.18.3 and do not reinstall/reload; confirm `current\\manifest.json` and Chrome both move to 0.18.4 automatically.\n'
write('TESTING.md', testing)

chat = read('NEW_CHAT_PROMPT.md')
if 'v0.18.4 terminal cancelled-order handling' not in chat:
    chat += '\n\n### v0.18.4 terminal cancelled-order handling\nTreat a scoped Order History card as terminal-complete without a Detail URL only when it proves the same Order ID, exact Cancelled/Canceled status, exact `$0.00` Total, and no real Detail link. Persist `historyTerminalComplete=true` / `historyTerminalState=cancelled`; never set `detailScanComplete` for this path. All other visible orders still require real captured Order Details URLs. Issue #19 tracks live acceptance.\n'
write('NEW_CHAT_PROMPT.md', chat)

print('v0.18.4 terminal cancelled-order patch applied')
