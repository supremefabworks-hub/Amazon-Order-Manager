from pathlib import Path
import re

ROOT = Path('.')

def read(name):
    return (ROOT / name).read_text(encoding='utf-8')

def write(name, text):
    (ROOT / name).write_text(text, encoding='utf-8')

def rep(text, old, new, label):
    if old not in text:
        raise RuntimeError(f'missing anchor: {label}')
    return text.replace(old, new, 1)

def rx(text, pattern, repl, label):
    out, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 replacement, got {count}')
    return out

# parser.js
p = read('parser.js')
p = rx(p, r"  function findCardLast4\(text\) \{.*?\n  \}\n\n  function extractOrderIds", r'''  function findCardLast4(text) {
    const normalized = normalizeText(text);
    if (!normalized) return null;
    const semantic = /(?:payment\s+(?:method|information)|\bcard\b|visa|master\s*card|mastercard|american express|amex|discover|amazon business card|ending in|last four|last 4)/i;
    if (!semantic.test(normalized)) return null;
    const patterns = [
      /(?:visa|master\s*card|mastercard|american express|amex|discover|amazon business card)[^\d\n]{0,100}?(?:ending in|ending|last four|last 4|\*{2,}|[•·xX]{2,})\s*[:#-]?\s*(\d{4})\b/i,
      /(?:payment\s+(?:method|information)|\bcard\b)[^\n]{0,150}?(?:ending in|ending|last four|last 4|\*{2,}|[•·xX]{2,})\s*[:#-]?\s*(\d{4})\b/i,
      /(?:ending in|last four|last 4)\s*[:#-]?\s*(\d{4})\b/i
    ];
    for (const pattern of patterns) {
      const match = normalized.match(pattern);
      if (match) return match[1];
    }
    return null;
  }

  function extractPaymentEvidenceText(container) {
    if (!container?.querySelectorAll) return '';
    const chunks = [];
    const seen = new Set();
    const add = raw => {
      const text = normalizeText(raw);
      if (!text || !/(?:payment|card|visa|master\s*card|mastercard|american express|amex|discover|ending in|last four|last 4)/i.test(text)) return;
      const key = text.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      chunks.push(text);
    };
    for (const selector of [
      '[id*="payment" i]', '[class*="payment" i]', '[data-testid*="payment" i]', '[aria-label*="payment" i]',
      '[id*="card" i]', '[class*="card" i]', '[data-testid*="card" i]'
    ]) {
      try {
        for (const el of Array.from(container.querySelectorAll(selector))) add(el.innerText || el.textContent || '');
      } catch (_) {}
    }
    return chunks.join('\n');
  }

  function extractOrderIds''', 'strict card parsing')
p = rep(p, "    const cardLast4 = findCardLast4(text);", "    const cardLast4 = findCardLast4(options.paymentText || text);", 'paymentText option')

helper = r'''
  function extractReturnItemEntries(container) {
    if (!container?.querySelectorAll) return [];
    const candidates = [];
    const seenElements = new Set();
    for (const selector of ['[data-asin]', '[data-item-index]', '[class*="return-item" i]', '[class*="returnItem"]', '.a-box', '.a-section']) {
      let nodes = [];
      try { nodes = Array.from(container.querySelectorAll(selector)); } catch (_) {}
      for (const el of nodes) {
        if (!el || seenElements.has(el)) continue;
        seenElements.add(el);
        const text = normalizeText(el.innerText || el.textContent || '');
        if (text.length < 8 || text.length > 3600) continue;
        if (!/(?:quantity\s*:|return item|item\(s\) in your return request|refund (?:amount|subtotal)|estimated refund)/i.test(text)) continue;
        const names = extractItemNamesFromContainer(el);
        const fallback = names.length ? names : extractItemNamesFromText(text);
        const itemName = fallback[0] || null;
        const asin = extractAsins(el)[0] || null;
        if (!itemName && !asin) continue;
        const refundAmount = findLabeledMoney(text, ['Item refund', 'Refund amount', 'Estimated refund', 'Refund subtotal']);
        candidates.push({ itemName, asin, refundAmount, textLength: text.length });
      }
    }
    const byKey = new Map();
    for (const entry of candidates) {
      const key = entry.asin || String(entry.itemName || '').toLowerCase();
      const prior = byKey.get(key);
      if (!prior || entry.textLength < prior.textLength) byKey.set(key, entry);
    }
    return Array.from(byKey.values()).map(({ textLength, ...entry }) => entry).slice(0, 30);
  }

  function isCompleteCanonicalDetail(record, url) {
    if (!record || record.recordType !== 'order' || !isOrderDetailPage(url)) return false;
    const urlId = orderIdFromUrl(url);
    if (!urlId || urlId !== record.orderId) return false;
    if (!record.orderDetailsUrl || !isOrderDetailPage(record.orderDetailsUrl)) return false;
    return Boolean(record.orderDate && Number.isFinite(Number(record.purchaseAmount)) && Array.isArray(record.itemNames) && record.itemNames.length);
  }

'''
p = rep(p, "  function extractReturnToken(url) {", helper + "  function extractReturnToken(url) {", 'return helpers')
p = rx(p, r"  function makeRecordId\(record\) \{.*?\n  \}\n\n  function parseTextRecord", r'''  function makeRecordId(record) {
    if (record.recordType === 'order') return `order:${record.orderId}`;
    const tokenKey = slug(record.returnToken || record.returnStatusUrl || '') || 'return';
    const itemKey = record.provisionalReturn
      ? 'pending'
      : (record.asins?.[0] || slug(record.itemNames?.[0] || '') || String(record.refundAmount ?? record.refundSubtotal ?? 'unknown'));
    return `return:${record.orderId}:${tokenKey}:${itemKey}`;
  }

  function parseTextRecord''', 'item-level return IDs')
p = rx(p, r"\n  function synthesizeOrderDetailUrl\(baseUrl, orderId\) \{.*?\n  \}\n\n  function extractOrderDetailLinks", "\n  function extractOrderDetailLinks", 'remove detail synthesizer')
p = rx(p, r"\n    // Every order card on a history page must eventually be detail-scanned\..*?\n    \}\n\n    return Array\.from\(byOrder\.values\(\)\);", "\n    return Array.from(byOrder.values());", 'remove synthesized link fallback')
p = rep(p, "      const container = closestContainerForOrder(doc, orderId);\n      results.push({\n        orderId,\n        url,\n        returnToken: extractReturnToken(url),\n        itemNames: extractItemNamesFromContainer(container),\n        asins: extractAsins(container)\n      });", "      const container = closestContainerForOrder(doc, orderId);\n      const containerText = normalizeText(container?.innerText || container?.textContent || '');\n      const itemScoped = /(?:item\\(s\\) in your return request|return item|quantity\\s*:|refund subtotal|estimated refund)/i.test(containerText);\n      results.push({\n        orderId,\n        url,\n        returnToken: extractReturnToken(url),\n        itemNames: itemScoped ? extractItemNamesFromContainer(container) : [],\n        asins: itemScoped ? extractAsins(container) : []\n      });", 'return link item scope')
p = rep(p, "      const record = parseTextRecord(context, orderId, {\n        pageType,", "      const paymentEvidenceText = extractPaymentEvidenceText(container || doc?.body);\n      const record = parseTextRecord(context, orderId, {\n        pageType,\n        paymentText: paymentEvidenceText || context,", 'payment DOM evidence')
p = rep(p, "        detailScanComplete: detailPage,", "        detailScanComplete: false,", 'detail completeness initial false')
old = """      const domNames = extractItemNamesFromContainer(container);\n      const asins = extractAsins(container);\n      if (domNames.length && !(pageType === 'return' && record.itemNames?.length)) record.itemNames = domNames;\n      record.asins = asins;\n      record.recordId = makeRecordId(record);\n      records.push(record);\n"""
new = """      const domNames = extractItemNamesFromContainer(container);\n      const asins = extractAsins(container);\n      if (domNames.length && !(pageType === 'return' && record.itemNames?.length)) record.itemNames = domNames;\n      record.asins = asins;\n\n      if (detailPage && record.recordType === 'order') {\n        record.detailScanComplete = isCompleteCanonicalDetail(record, url);\n        record.detailScannedAt = record.detailScanComplete ? new Date().toISOString() : null;\n      }\n\n      if (pageType === 'return') {\n        const returnItems = extractReturnItemEntries(container || doc?.body);\n        if (returnItems.length) {\n          for (const item of returnItems) {\n            const itemRecord = {\n              ...record,\n              itemNames: item.itemName ? [item.itemName] : [],\n              asins: item.asin ? [item.asin] : [],\n              refundAmount: Number.isFinite(Number(item.refundAmount)) ? Number(item.refundAmount) : (returnItems.length === 1 ? record.refundAmount : null),\n              refundSubtotal: Number.isFinite(Number(item.refundAmount)) ? Number(item.refundAmount) : (returnItems.length === 1 ? record.refundSubtotal : null),\n              refundAmountScope: 'item',\n              provisionalReturn: false,\n              authoritativeReturnCapture: true\n            };\n            itemRecord.recordId = makeRecordId(itemRecord);\n            records.push(itemRecord);\n          }\n        } else {\n          record.provisionalReturn = false;\n          record.authoritativeReturnCapture = true;\n          record.refundAmountScope = (record.itemNames || []).length === 1 ? 'item' : 'return';\n          record.recordId = makeRecordId(record);\n          records.push(record);\n        }\n      } else {\n        record.recordId = makeRecordId(record);\n        records.push(record);\n      }\n"""
p = rep(p, old, new, 'authoritative detail and return items')
p = rep(p, "          recordType: 'return', orderId,\n          itemNames: domNames.length ? domNames : record.itemNames || [], asins,", "          recordType: 'return', orderId,\n          itemNames: linked?.itemNames || [], asins: linked?.asins || [],", 'strong provisional does not claim bundle items')
p = rep(p, "          orderDetailsUrl: detailPage ? url : (detailByOrder.get(orderId) || null), detailScanComplete: false, detailScannedAt: null\n        };", "          orderDetailsUrl: detailPage ? url : (detailByOrder.get(orderId) || null), detailScanComplete: false, detailScannedAt: null,\n          provisionalReturn: true, authoritativeReturnCapture: false\n        };", 'strong provisional marker')
p = rep(p, "          detailScanComplete: false,\n          detailScannedAt: null\n        };", "          detailScanComplete: false,\n          detailScannedAt: null,\n          provisionalReturn: true,\n          authoritativeReturnCapture: false\n        };", 'link provisional marker')
p = rep(p, "      historyOrderIds: isOrderHistoryPage(doc, url) ? detailLinks.map(x => x.orderId).filter(Boolean) : [],\n      historyVisibleCount: isOrderHistoryPage(doc, url) ? detailLinks.length : 0,", "      historyOrderIds: isOrderHistoryPage(doc, url) ? extractOrderIds(bodyText) : [],\n      historyVisibleCount: isOrderHistoryPage(doc, url) ? extractOrderIds(bodyText).length : 0,", 'visible fingerprint')
p = rep(p, "    findCardLast4,", "    findCardLast4,\n    extractPaymentEvidenceText,\n    extractReturnItemEntries,\n    isCompleteCanonicalDetail,", 'parser exports')
p = rep(p, "    synthesizeOrderDetailUrl,\n", "", 'remove synthesizer export')
write('parser.js', p)

# storage.js
s = read('storage.js')
s = rep(s, "      if (Array.isArray(value)) merged[key] = mergeArray(existing?.[key], value);", "      if (Array.isArray(value)) {\n        if (incoming?.recordType === 'return' && incoming?.authoritativeReturnCapture && ['itemNames', 'asins'].includes(key)) merged[key] = mergeArray([], value);\n        else merged[key] = mergeArray(existing?.[key], value);\n      }", 'authoritative return arrays')
s = rep(s, "    let unchanged = 0;\n    const changedRecordIds = [];\n\n    for (const incoming of records || []) {", "    let unchanged = 0;\n    let removed = 0;\n    const changedRecordIds = [];\n\n    const authoritativeGroups = new Map();\n    for (const record of (records || []).filter(r => r?.recordType === 'return' && r?.authoritativeReturnCapture && r?.orderId && r?.returnToken)) {\n      const key = `${record.orderId}:${record.returnToken}`;\n      if (!authoritativeGroups.has(key)) authoritativeGroups.set(key, new Set());\n      authoritativeGroups.get(key).add(record.recordId);\n    }\n    for (const [recordId, existing] of Array.from(byId.entries())) {\n      if (existing?.recordType !== 'return' || !existing?.returnToken) continue;\n      const keepIds = authoritativeGroups.get(`${existing.orderId}:${existing.returnToken}`);\n      if (!keepIds || keepIds.has(recordId)) continue;\n      if (!existing.provisionalReturn && !existing.authoritativeReturnCapture) continue;\n      byId.delete(recordId);\n      removed += 1;\n      changedRecordIds.push(recordId);\n    }\n\n    for (const incoming of records || []) {", 'replace provisional/old authoritative return group')
s = rep(s, "    const changed = inserted > 0 || updated > 0;", "    const changed = inserted > 0 || updated > 0 || removed > 0;", 'removed is change')
s = rep(s, "    return { inserted, updated, unchanged, changed, total: nextLedger.length, changedRecordIds, beforeSummary, afterSummary };", "    return { inserted, updated, removed, unchanged, changed, total: nextLedger.length, changedRecordIds, beforeSummary, afterSummary };", 'return removed count')
write('storage.js', s)

# background.js
b = read('background.js')
b = rep(b, "const WORKFLOW_LOG_KEY = 'workflowLog';\nconst MAX_WORKFLOW_EVENTS = 1600;", "const WORKFLOW_LOG_KEY = 'workflowLog';\nconst VERSION_KEY = 'installedExtensionVersion';\nconst DEV_RESET_ON_VERSION_CHANGE = true;\nconst MAX_WORKFLOW_EVENTS = 1600;", 'version constants')
version_fn = r'''async function ensureDevelopmentVersionState() {
  const version = chrome.runtime?.getManifest?.()?.version || null;
  if (!version) return { changed: false, version: null };
  const data = await chrome.storage.local.get([VERSION_KEY]);
  const prior = data[VERSION_KEY] || null;
  if (prior === version) return { changed: false, version };
  if (DEV_RESET_ON_VERSION_CHANGE && prior) {
    await chrome.storage.local.remove([
      LEDGER_KEY, STATE_KEY, WORKER_TAB_KEY, WORKFLOW_LOG_KEY,
      'lastBankVerificationRequest', 'lastBankVerificationImport'
    ]);
    workerTabId = null;
  }
  await chrome.storage.local.set({ [VERSION_KEY]: version });
  return { changed: Boolean(prior && prior !== version), previousVersion: prior, version };
}

'''
b = rep(b, "function randomBetween(min, max) {", version_fn + "function randomBetween(min, max) {", 'version function')
b = rx(b, r"\nfunction syntheticDetailUrl\(record\) \{.*?\n\}\n", "\n", 'remove synthetic detail URL')
b = b.replace("r.orderDetailsUrl || syntheticDetailUrl(r)", "r.orderDetailsUrl || null")
b = rx(b, r"function uniqueDetailLinks\(result\) \{.*?\n\}\n\nasync function queueManagedHistoryResult", r'''function uniqueDetailLinks(result) {
  const byId = new Map();
  for (const link of result?.detailLinks || []) {
    const orderId = String(link?.orderId || '').trim();
    const url = normalizeUrl(link?.url) || link?.url || null;
    if (!/^\d{3}-\d{7}-\d{7}$/.test(orderId) || !url || byId.has(orderId)) continue;
    if (!/(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|order-details)/i.test(url)) continue;
    byId.set(orderId, { orderId, url });
  }
  return Array.from(byId.values());
}

async function queueManagedHistoryResult''', 'real detail links')
b = rep(b, "  const links = uniqueDetailLinks(result);\n  const pageOrderIds = links.map(x => x.orderId);", "  const links = uniqueDetailLinks(result);\n  const pageOrderIds = historyOrderIdSet(result);\n  if (!pageOrderIds.length) throw new Error(`No visible Amazon Order IDs were found on ${year} page ${page}`);\n  const linkByOrder = new Map(links.map(link => [link.orderId, link]));\n  const missingDetailUrls = pageOrderIds.filter(orderId => !linkByOrder.has(orderId));\n  if (missingDetailUrls.length) throw new Error(`Missing real View order details URL for ${missingDetailUrls.length} order(s) on ${year} page ${page}. The crawler stopped rather than inventing canonical URLs.`);\n  const orderedLinks = pageOrderIds.map(orderId => linkByOrder.get(orderId));", 'managed crawl requires real detail URLs')
b = rep(b, "  for (const link of links) {\n    seq += 1;", "  for (const link of orderedLinks) {\n    seq += 1;", 'ordered real links')
b = rx(b, r"function historyPageChanged\(before, after\) \{.*?\n\}", r'''function historyPageChanged(before, after) {
  const a = historyOrderIdSet(before);
  const b = historyOrderIdSet(after);
  if (!a.length || !b.length) return false;
  return a.join('|') !== b.join('|');
}''', 'fingerprint-only progress')
b = rep(b, "    const hostUrl = job.historyUrl || state.crawl.currentHistoryUrl || 'https://www.amazon.com/gp/your-account/order-history';", "    if (!job.url) throw new Error('Canonical Order Details URL is missing; crawler will not synthesize one.');\n    const hostUrl = job.historyUrl || state.crawl.currentHistoryUrl || 'https://www.amazon.com/gp/your-account/order-history';", 'detail URL guard')
b = rep(b, "        url: job.url || syntheticDetailUrl({ orderId: job.orderId }),", "        url: job.url,", 'fetch real URL only')

force_refresh = r'''async function forceRefreshOrder(orderId) {
  const id = String(orderId || '').trim();
  if (!/^\d{3}-\d{7}-\d{7}$/.test(id)) throw new Error('Invalid Amazon order ID.');
  const data = await chrome.storage.local.get([LEDGER_KEY]);
  const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
  const order = ledger.find(r => r?.recordType === 'order' && r?.orderId === id) || null;
  const detailUrl = order?.orderDetailsUrl || null;
  if (!detailUrl || !/(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|order-details)/i.test(detailUrl)) {
    throw new Error('This order has no real captured View order details URL. Refresh cannot invent one.');
  }
  const tab = await chrome.tabs.create({ url: detailUrl, active: false });
  const tabId = tab?.id;
  if (!Number.isInteger(tabId)) throw new Error('Could not create the inactive Amazon refresh tab.');
  try {
    await waitForTabComplete(tabId, detailUrl);
    const detailResult = await scanWorkerTab(tabId, { type: 'detail', manualRefresh: true, orderId: id, url: detailUrl });
    const complete = (detailResult.records || []).some(r => r?.recordType === 'order' && r?.orderId === id && r?.detailScanComplete);
    if (!complete) throw new Error('Rendered Order Details did not produce a complete canonical capture.');
    let returnsRefreshed = 0;
    for (const link of (detailResult.returnLinks || []).filter(link => link?.orderId === id && link?.url && /\/spr\/returns\/prep/i.test(link.url))) {
      await navigateExistingWorkerTab(tabId, link.url);
      const returnResult = await scanWorkerTab(tabId, { type: 'return', manualRefresh: true, orderId: id, url: link.url });
      const matched = (returnResult.records || []).some(r => r?.recordType === 'return' && r?.orderId === id && r?.authoritativeReturnCapture);
      if (!matched) throw new Error('Amazon return-status page did not produce an authoritative return record.');
      returnsRefreshed += 1;
    }
    return { ok: true, orderId: id, detailScannedAt: nowIso(), returnsRefreshed };
  } finally {
    try { await chrome.tabs.remove(tabId); } catch (_) {}
  }
}

'''
b = rep(b, "async function broadcastLedgerUpdate(save) {", force_refresh + "async function broadcastLedgerUpdate(save) {", 'rendered force refresh')
handler = r'''  if (message.type === 'ARL_REFRESH_ORDER') {
    forceRefreshOrder(message.orderId)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }

'''
b = rep(b, "  if (message.type === 'ARL_RESCAN_ALL_DETAILS') {", handler + "  if (message.type === 'ARL_RESCAN_ALL_DETAILS') {", 'refresh message')
b = rep(b, "chrome.runtime.onStartup.addListener(() => {\n  getState().then(state => { if (state.crawl?.active && !state.paused && state.queue?.length) scheduleSoon(randomBetween(1200, 3000)); }).catch(() => {});\n});\nchrome.runtime.onInstalled.addListener(() => {});", "chrome.runtime.onStartup.addListener(() => {\n  ensureDevelopmentVersionState().then(() => getState()).then(state => { if (state.crawl?.active && !state.paused && state.queue?.length) scheduleSoon(randomBetween(1200, 3000)); }).catch(() => {});\n});\nchrome.runtime.onInstalled.addListener(() => { ensureDevelopmentVersionState().catch(() => {}); });", 'version lifecycle')
write('background.js', b)

# content.js
c = read('content.js')
c = rep(c, "    const expectedCredit = !progress.credited ? (record.expectedCreditDate || record?.returnMilestones?.expectedCreditDate || '') : '';", "    const expectedCredit = !progress.credited ? (record.expectedCreditDate || record?.returnMilestones?.expectedCreditDate || '') : '';\n    const orderDetailsUrl = record.orderDetailsUrl && /(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|order-details)/i.test(record.orderDetailsUrl) ? record.orderDetailsUrl : '';", 'inline real detail URL')
c = rep(c, "      <a href=\"https://www.amazon.com/your-orders/order-details?orderID=${esc(record.orderId)}\" target=\"_blank\" rel=\"noopener\">Open order details</a>", "      ${orderDetailsUrl ? `<a href=\"${esc(orderDetailsUrl)}\" target=\"_blank\" rel=\"noopener\">Open order details</a>` : ''}", 'inline no synthesized detail link')
c = rep(c, "        let url;\n        try {\n          url = new URL(rawUrl || `/your-orders/order-details?orderID=${encodeURIComponent(orderId)}`, location.origin);", "        if (!rawUrl) return { ok: false, error: 'Missing real Order Details URL.' };\n        let url;\n        try {\n          url = new URL(rawUrl, location.origin);", 'fetch requires real URL')
c = rep(c, "          const matching = (parsed.records || []).filter(record => record?.recordType === 'order' && record?.orderId === orderId);", "          const matching = (parsed.records || []).filter(record => record?.recordType === 'order' && record?.orderId === orderId && record?.detailScanComplete);", 'fetch requires complete detail')
c = rep(c, "            return { ok: false, error: `Order Details HTML did not contain order ${orderId}.`, scannedUrl: finalUrl };", "            return { ok: false, error: `Order Details HTML for ${orderId} was incomplete or did not match the canonical order.`, scannedUrl: finalUrl };", 'detail incomplete error')
old = """          let save = null;\n          if (parsed.records?.length) save = await storage.upsertRecords(parsed.records);\n          return { ok: true, ...parsed, save, scannedUrl: finalUrl, fetchedOrderDetails: true };\n"""
new = """          let save = null;\n          if (parsed.records?.length) save = await storage.upsertRecords(parsed.records);\n          const returnRefreshes = [];\n          for (const link of (parsed.returnLinks || []).filter(link => link?.orderId === orderId && link?.url)) {\n            const returnUrl = new URL(link.url, finalUrl);\n            if (!/(^|\\.)amazon\\.com$/i.test(returnUrl.hostname) || !/\\/spr\\/returns\\/prep/i.test(returnUrl.pathname)) continue;\n            const returnResponse = await fetch(returnUrl.toString(), { credentials: 'include', cache: 'no-store', redirect: 'follow' });\n            if (!returnResponse.ok) {\n              const returnRateLimited = returnResponse.status === 429 || returnResponse.status === 503;\n              return { ok: false, rateLimited: returnRateLimited, error: returnRateLimited ? 'Amazon throttled the return-status refresh.' : `Amazon return status returned HTTP ${returnResponse.status}.` };\n            }\n            const returnHtml = await returnResponse.text();\n            const returnProbe = String(returnHtml || '').replace(/<script[\\s\\S]*?<\\/script>/gi, ' ').replace(/<style[\\s\\S]*?<\\/style>/gi, ' ');\n            const returnBlocked = /sorry,? we just need to make sure|not a robot|enter the characters you see below|type the characters you see|captcha/i.test(returnProbe);\n            const returnSignIn = /email or mobile phone number|enter your password|<title>\\s*amazon sign-in/i.test(returnProbe);\n            if (returnBlocked || returnSignIn) return { ok: false, blocked: true, error: returnBlocked ? 'Amazon requested human verification during return refresh.' : 'Amazon requires sign-in during return refresh.' };\n            const returnDoc = new DOMParser().parseFromString(returnHtml, 'text/html');\n            const returnFinalUrl = returnResponse.url || returnUrl.toString();\n            const returnParsed = parser.parseDocument(returnDoc, returnFinalUrl);\n            const returnRecords = (returnParsed.records || []).filter(record => record?.recordType === 'return' && record?.orderId === orderId && record?.authoritativeReturnCapture);\n            if (!returnRecords.length) return { ok: false, error: `Return status for ${orderId} did not contain an authoritative return record.` };\n            const returnSave = await storage.upsertRecords(returnRecords);\n            returnRefreshes.push({ url: returnFinalUrl, records: returnRecords.length, save: returnSave });\n          }\n          return { ok: true, ...parsed, save, scannedUrl: finalUrl, fetchedOrderDetails: true, returnRefreshes };\n"""
c = rep(c, old, new, 'fetch return lifecycle enrichment')
write('content.js', c)

# dashboard.js
d = read('dashboard.js')
d = rx(d, r"  function canonicalDetailUrl\(orderId, order\) \{.*?\n  \}", r'''  function canonicalDetailUrl(orderId, order) {
    const url = order?.orderDetailsUrl || '';
    if (url && /(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|order-details)/i.test(url)) return url;
    return '';
  }''', 'dashboard real detail URL')
old = """        <div class=\"line-actions\">\n          <button class=\"mini\" data-open-url=\"${esc(row.openUrl)}\">Details</button>\n          ${row.hasReturn ? `<button class=\"mini\" data-action=\"reconcile\" data-order=\"${esc(row.orderId)}\">Credit</button><button class=\"mini\" data-action=\"reset\" data-order=\"${esc(row.orderId)}\">Reset</button>` : ''}\n        </div>\n"""
new = """        <div class=\"line-actions\">\n          <button class=\"mini action-large\" data-open-url=\"${esc(row.openUrl)}\" ${row.openUrl ? '' : 'disabled'}>Details</button>\n          <button class=\"mini action-large\" data-action=\"reconcile\" data-order=\"${esc(row.orderId)}\" ${row.hasReturn ? '' : 'disabled'}>Credit</button>\n          <button class=\"mini action-large\" data-action=\"reset\" data-order=\"${esc(row.orderId)}\" ${row.hasReturn ? '' : 'disabled'}>Reset</button>\n          <button class=\"mini action-large\" data-refresh-order=\"${esc(row.orderId)}\" ${row.openUrl ? '' : 'disabled'}>Refresh</button>\n        </div>\n"""
d = rep(d, old, new, 'fixed four actions')
old = """  body.addEventListener('click', async event => {\n    const open = event.target.closest('[data-open-url]');\n    if (open) { await chrome.tabs.create({ url: open.dataset.openUrl }); return; }\n    const action = event.target.closest('button[data-action]');\n"""
new = """  body.addEventListener('click', async event => {\n    const refresh = event.target.closest('button[data-refresh-order]');\n    if (refresh && !refresh.disabled) {\n      const original = refresh.textContent;\n      refresh.disabled = true;\n      refresh.textContent = 'Refreshing…';\n      try {\n        const response = await chrome.runtime.sendMessage({ type: 'ARL_REFRESH_ORDER', orderId: refresh.dataset.refreshOrder });\n        if (!response?.ok) throw new Error(response?.error || 'Refresh failed');\n        await reload();\n      } catch (error) {\n        alert(`Order refresh failed: ${error?.message || error}`);\n      } finally {\n        refresh.disabled = false;\n        refresh.textContent = original;\n      }\n      return;\n    }\n    const open = event.target.closest('[data-open-url]');\n    if (open && open.dataset.openUrl) { await chrome.tabs.create({ url: open.dataset.openUrl }); return; }\n    const action = event.target.closest('button[data-action]');\n"""
d = rep(d, old, new, 'refresh button handler')
d = d.replace("sourceExtensionVersion: '0.16.0'", "sourceExtensionVersion: '0.17.0'")
write('dashboard.js', d)

# ui.css
u = read('ui.css')
u = rep(u, "  grid-template-columns: 105px minmax(220px, 2fr) 82px 86px 78px minmax(310px, 1.45fr) auto;", "  grid-template-columns: 105px minmax(220px, 2fr) 82px 86px 78px minmax(280px, 1.35fr) 360px;", 'desktop action width')
u = rep(u, ".line-actions { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; align-items: center; max-width: 125px; }\n.line-actions .mini { padding: 4px 6px; font-size: 9px; white-space: nowrap; }", ".line-actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; align-items: stretch; width: 100%; max-width: none; }\n.line-actions .mini { padding: 10px 8px; min-height: 36px; font-size: 10px; white-space: nowrap; }", 'large four actions')
u = rep(u, "    grid-template-columns: 92px minmax(180px, 1.8fr) 70px 74px 66px minmax(250px, 1.35fr) 106px;", "    grid-template-columns: 92px minmax(180px, 1.8fr) 70px 74px 66px minmax(220px, 1.2fr) 320px;", '1450 action width')
u = u.replace("  .line-actions { grid-column: 1; grid-row: 2; justify-content: flex-start; max-width: none; }", "  .line-actions { grid-column: 1 / -1; grid-row: 2; max-width: none; }")
write('ui.css', u)

# version/package
m = read('manifest.json').replace('"version": "0.16.0"', '"version": "0.17.0"').replace('"version_name": "0.16.0"', '"version_name": "0.17.0"')
m = m.replace('direct authenticated Order Details fetching, proven Amazon pagination patterns, strict lifetime crawling, responsive dashboard, and secure bank-credit reconciliation bridge.', 'authoritative Order Details capture, evidence-based return refresh, fingerprint-verified lifetime crawling, per-order background Refresh, and secure bank-credit reconciliation bridge.')
write('manifest.json', m)
pkg = read('package.json').replace('"version": "0.16.0"', '"version": "0.17.0"')
pkg = pkg.replace('node reconciliation-test.js', 'node reconciliation-test.js && node ui-test.js')
write('package.json', pkg)

# tests
pt = read('parser-test.js')
pt += r'''

// v0.17 regressions
const unrelatedDigits = p.parseTextRecord('Order # 114-1234567-7654321 Tracking XXXX 4821 Invoice 2026', '114-1234567-7654321', { pageType: 'order' });
assert(unrelatedDigits.cardLast4 === null, 'arbitrary four-digit page text must never become a payment card');
const semanticPayment = p.parseTextRecord('Payment information\nVisa ending in 4821\nOrder total $19.99', '114-1234567-7654321', { pageType: 'order' });
assert(semanticPayment.cardLast4 === '4821', 'semantic payment evidence should capture card last four');

const noDetailAnchorDoc = {
  body: { innerText: 'Your Orders\nOrder placed\nOrder # 114-8888888-9999999', textContent: '' },
  querySelectorAll() { return []; },
  querySelector() { return null; }
};
assert(p.extractOrderDetailLinks(noDetailAnchorDoc, 'https://www.amazon.com/gp/your-account/order-history').length === 0, 'history parser must not synthesize missing Order Details URLs');
const noAnchorParsed = p.parseDocument(noDetailAnchorDoc, 'https://www.amazon.com/gp/your-account/order-history');
assert(noAnchorParsed.historyOrderIds.includes('114-8888888-9999999'), 'visible Order IDs must remain in pagination fingerprint even if canonical link is missing');

const staticTimelineOnly = p.parseTextRecord('Initiated Aug 30\nDropped off Aug 31\nRefund issued\nRefund credited Sep 7\n$75.00 will be credited by Sep 7', '114-2222222-3333333', { pageType: 'return' });
assert(staticTimelineOnly.returnStage !== 'refund_issued' && staticTimelineOnly.returnStage !== 'credited', 'static timeline labels and future ETA must not prove refund issuance');

const itemA = { recordType:'return', orderId:'114-3333333-4444444', returnToken:'RMA-ITEMS', itemNames:['Widget A'], asins:['B000000001'], refundAmount:10, provisionalReturn:false };
const itemB = { ...itemA, itemNames:['Widget B'], asins:['B000000002'], refundAmount:20 };
assert(p.makeRecordId(itemA) !== p.makeRecordId(itemB), 'multiple returned items under one return token need distinct item-level record IDs');
assert(p.isCompleteCanonicalDetail({ recordType:'order', orderId:'114-3333333-4444444', orderDetailsUrl:'https://www.amazon.com/your-orders/order-details?orderID=114-3333333-4444444', orderDate:'Sep 1, 2026', purchaseAmount:20, itemNames:['Widget'] }, 'https://www.amazon.com/your-orders/order-details?orderID=114-3333333-4444444') === true, 'complete canonical detail should require real URL/date/total/item');
assert(p.isCompleteCanonicalDetail({ recordType:'order', orderId:'114-3333333-4444444', orderDetailsUrl:'https://www.amazon.com/your-orders/order-details?orderID=114-3333333-4444444', orderDate:'Sep 1, 2026', purchaseAmount:20, itemNames:[] }, 'https://www.amazon.com/your-orders/order-details?orderID=114-3333333-4444444') === false, 'detail page without item capture must not be Detailed');
console.log('v0.17 parser regressions passed');
'''
write('parser-test.js', pt)

bt = read('background-test.js')
bt += r'''

assert(sandbox.historyPageChanged(
  { scannedUrl:'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/1/', historyOrderIds:[] },
  { scannedUrl:'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/2/', historyOrderIds:[] }
) === false, 'URL change without visible Order-ID fingerprint must not count as pagination progress');
assert(typeof sandbox.syntheticDetailUrl === 'undefined', 'v0.17 must not expose a synthetic Order Details URL fallback');
console.log('v0.17 background regressions passed');
'''
write('background-test.js', bt)

st = read('storage-test.js')
st = rep(st, "    recordId: 'return:114-9999999-1111111:RMAABC123', recordType: 'return', orderId: '114-9999999-1111111',\n    itemNames: [], returnToken: 'RMAABC123', returnStatusUrl: 'https://amazon.com/spr/returns/prep?orderId=114-9999999-1111111&rmaId=RMAABC123',\n    status: 'return_in_progress', returnStage: 'started', statusText: 'Amazon return status link detected'", "    recordId: 'return:114-9999999-1111111:rmaabc123:pending', recordType: 'return', orderId: '114-9999999-1111111',\n    itemNames: ['Wrong bundled sibling'], returnToken: 'RMAABC123', returnStatusUrl: 'https://amazon.com/spr/returns/prep?orderId=114-9999999-1111111&rmaId=RMAABC123',\n    status: 'return_in_progress', returnStage: 'started', statusText: 'Amazon return status link detected', provisionalReturn: true, authoritativeReturnCapture: false", 'storage provisional fixture')
st = rep(st, "  await s.upsertRecords([{ ...prov, itemNames: ['Returned Widget'], refundAmount: 88.50, status: 'refunded', returnStage: 'refund_issued', statusText: 'We have issued your refund' }]);", "  await s.upsertRecords([{ ...prov, recordId: 'return:114-9999999-1111111:rmaabc123:returned-widget', itemNames: ['Returned Widget'], refundAmount: 88.50, status: 'refunded', returnStage: 'refund_issued', statusText: 'We have issued your refund', provisionalReturn: false, authoritativeReturnCapture: true }]);", 'authoritative return fixture')
st = rep(st, "  assert(sameReturnRows[0].itemNames.includes('Returned Widget'), 'return-page item should upgrade provisional return');", "  assert(sameReturnRows[0].itemNames.length === 1 && sameReturnRows[0].itemNames[0] === 'Returned Widget', 'authoritative return page must replace provisional bundled item names');\n\n  await s.upsertRecords([\n    { ...sameReturnRows[0], recordId:'return:114-9999999-1111111:rmaabc123:item-a', itemNames:['Item A'], asins:['B000000001'], refundAmount:20, authoritativeReturnCapture:true, provisionalReturn:false },\n    { ...sameReturnRows[0], recordId:'return:114-9999999-1111111:rmaabc123:item-b', itemNames:['Item B'], asins:['B000000002'], refundAmount:30, authoritativeReturnCapture:true, provisionalReturn:false }\n  ]);\n  const itemLevelRows = (await s.getLedger()).filter(r => r.orderId === prov.orderId && r.recordType === 'return');\n  assert(itemLevelRows.some(r => r.itemNames[0] === 'Item A' && r.refundAmount === 20), 'first returned item must retain its own expected refund');\n  assert(itemLevelRows.some(r => r.itemNames[0] === 'Item B' && r.refundAmount === 30), 'second returned item must retain its own expected refund');", 'item return storage')
write('storage-test.js', st)

sm = read('state-machine-test.js')
sm = rep(sm, "  runtime: { onMessage: { addListener: noop }, onStartup: { addListener: noop }, onInstalled: { addListener: noop } }", "  runtime: { getManifest: () => ({ version: '0.17.0' }), onMessage: { addListener: noop }, onStartup: { addListener: noop }, onInstalled: { addListener: noop } }", 'manifest mock')
sm = rep(sm, "  assert(state.queue.filter(j => j.type === 'detail').length === 9, 'same-page rescan must not duplicate detail jobs');\n\n  console.log('strict crawl state-machine tests passed');", "  assert(state.queue.filter(j => j.type === 'detail').length === 9, 'same-page rescan must not duplicate detail jobs');\n\n  let missingLinkStopped = false;\n  try {\n    await sandbox.queueManagedHistoryResult({ scannedUrl:'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/2/', historySelectedYear:2026, historyYears:[2026,2025], historyOrderIds:['113-2000000-2000000'], detailLinks:[] }, { historyYear:2026, historyPage:2, crawlManaged:true });\n  } catch (error) { missingLinkStopped = /Missing real View order details URL/.test(String(error.message || error)); }\n  assert(missingLinkStopped, 'managed crawl must stop if a visible order lacks its real View order details URL');\n\n  store.ledger = [{ recordId:'order:test', orderId:'113-0000000-0000000' }];\n  store.backgroundScanState = { running:true };\n  store.installedExtensionVersion = '0.16.0';\n  await sandbox.ensureDevelopmentVersionState();\n  assert(store.ledger === undefined, 'version change should wipe development ledger state');\n  assert(store.backgroundScanState === undefined, 'version change should wipe crawl checkpoint state');\n  assert(store.installedExtensionVersion === '0.17.0', 'version reset should store new manifest version');\n\n  console.log('strict crawl state-machine tests passed');", 'state regressions')
write('state-machine-test.js', sm)

ui = r'''const fs = require('fs');
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
console.log('ui regression tests passed');
'''
write('ui-test.js', ui)

print('v0.17 patch applied')
