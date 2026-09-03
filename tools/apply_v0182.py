from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def write(path, text):
    (ROOT / path).write_text(text, encoding='utf-8')


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise RuntimeError(f'{label}: expected exactly one match, found {text.count(old)}')
    return text.replace(old, new, 1)


def replace_between(text, start, end, new, label):
    i = text.find(start)
    if i < 0:
        raise RuntimeError(f'{label}: start marker missing')
    j = text.find(end, i)
    if j < 0:
        raise RuntimeError(f'{label}: end marker missing')
    return text[:i] + new + text[j:]

# ---------------- parser.js ----------------
p = read('parser.js')
old_make = '''  function makeRecordId(record) {
    if (record.recordType === 'order') return `order:${record.orderId}`;
    const tokenKey = slug(record.returnToken || record.returnStatusUrl || '') || 'return';
    const itemKey = record.provisionalReturn
      ? 'pending'
      : (record.asins?.[0] || slug(record.itemNames?.[0] || '') || String(record.refundAmount ?? record.refundSubtotal ?? 'unknown'));
    return `return:${record.orderId}:${tokenKey}:${itemKey}`;
  }
'''
new_make = '''  function makeRecordId(record) {
    if (record.recordType === 'order') return `order:${record.orderId}`;
    const tokenKey = slug(record.returnToken || record.returnStatusUrl || '') || 'return';
    // Amazon's return-status URL gives us a stable child identity. Prefer itemId so the
    // provisional Order Details record and later authoritative return-page capture merge into
    // the same row instead of being re-keyed by whichever title the page parser happened to see.
    const itemKey = record.returnItemId
      ? `item-${slug(record.returnItemId)}`
      : (record.asins?.[0] || slug(record.itemNames?.[0] || '') || (record.provisionalReturn ? 'pending' : String(record.refundAmount ?? record.refundSubtotal ?? 'unknown')));
    return `return:${record.orderId}:${tokenKey}:${itemKey}`;
  }
'''
p = replace_once(p, old_make, new_make, 'parser makeRecordId')

# Parse stable return URL metadata into every return record.
p = replace_once(
    p,
    "    const pageType = options.pageType || inferPageType(text, options.url);\n    const refundAmount = findRefundAmount(text);",
    "    const pageType = options.pageType || inferPageType(text, options.url);\n    const returnMeta = returnUrlMetadata(options.returnStatusUrl || options.url || '');\n    const refundAmount = findRefundAmount(text);",
    'parser parseTextRecord metadata')
p = replace_once(
    p,
    "      returnToken: options.returnToken || null,\n      returnStatusUrl: options.returnStatusUrl || (recordType === 'return' ? options.url || null : null),",
    "      returnToken: options.returnToken || returnMeta.returnToken || null,\n      returnItemId: options.returnItemId || returnMeta.returnItemId || null,\n      returnContractId: options.returnContractId || returnMeta.returnContractId || null,\n      returnRmaId: options.returnRmaId || returnMeta.returnRmaId || null,\n      itemIdentitySource: options.itemIdentitySource || null,\n      returnStatusUrl: options.returnStatusUrl || (recordType === 'return' ? options.url || null : null),",
    'parser parseTextRecord fields')

helpers = '''  function returnUrlMetadata(url) {
    const out = { returnToken: extractReturnToken(url), returnItemId: null, returnContractId: null, returnRmaId: null };
    try {
      const u = new URL(url);
      out.returnItemId = u.searchParams.get('itemId') || null;
      out.returnContractId = u.searchParams.get('contractId') || null;
      out.returnRmaId = u.searchParams.get('rmaId') || null;
    } catch (_) {}
    return out;
  }

  function nearestReturnItemEvidence(anchor) {
    let current = anchor?.parentElement || null;
    let fallback = null;
    for (let depth = 0; current && depth < 10; depth += 1, current = current.parentElement) {
      let anchors = [];
      try { anchors = Array.from(current.querySelectorAll?.('a[href]') || []); } catch (_) {}
      const byAsin = new Map();
      for (const a of anchors) {
        const href = String(a.getAttribute?.('href') || a.href || '');
        const match = href.match(/\/dp\/([A-Z0-9]{10})(?:[/?#]|$)/i) || href.match(/[?&]asin=([A-Z0-9]{10})(?:&|$)/i);
        if (!match) continue;
        const asin = match[1].toUpperCase();
        let itemName = normalizeText(a.innerText || a.textContent || a.getAttribute?.('aria-label') || a.getAttribute?.('title') || '');
        if (/^(?:view your item|buy it again|write a product review|ask product question)$/i.test(itemName)) itemName = '';
        const existing = byAsin.get(asin);
        if (!existing || (!existing.itemName && itemName)) byAsin.set(asin, { asin, itemName });
      }
      if (!byAsin.size) continue;
      const entries = Array.from(byAsin.values());
      const evidence = {
        itemNames: entries.map(entry => entry.itemName).filter(Boolean),
        asins: entries.map(entry => entry.asin).filter(Boolean)
      };
      if (!fallback) fallback = evidence;
      // A duplicated image/title anchor for one ASIN still counts as one product. The smallest
      // ancestor with one unique product is the item-specific return block we want.
      if (entries.length === 1) return evidence;
    }
    return fallback || { itemNames: [], asins: [] };
  }

'''
marker = '  function extractReturnStatusLinks(doc, baseUrl) {'
if marker not in p:
    raise RuntimeError('parser return link marker missing')
p = p.replace(marker, helpers + marker, 1)

new_extract_links = '''  function extractReturnStatusLinks(doc, baseUrl) {
    if (!doc?.querySelectorAll) return [];
    const results = [];
    const seen = new Set();
    const statusTextRe = /(?:view|check|track|see|print|share)?\s*(?:your\s*)?(?:return\s*(?:&|and|\/)\s*refund|return|refund)\s*(?:status|details|label)|check return\s*(?:&|and)\s*refund status|return label/i;
    const genericActionRe = /return or replace|return items?|replace items?|start a return/i;

    for (const a of Array.from(doc.querySelectorAll('a[href]'))) {
      const href = String(a.getAttribute('href') || a.href || '');
      const text = normalizeText(a.innerText || a.textContent || '');
      if (!href || genericActionRe.test(text)) continue;
      const url = absoluteAmazonUrl(href, baseUrl);
      if (!url) continue;
      let explicitUrl = false;
      try {
        const u = new URL(url);
        explicitUrl = Boolean(u.searchParams.get('rmaId') || u.searchParams.get('contractId') || u.searchParams.get('returnId')) ||
          /\/spr\/returns\/(?:prep|label)|\/returns?\/(?:status|details)|return-status/i.test(u.pathname);
      } catch (_) {}
      if (!explicitUrl && !statusTextRe.test(text)) continue;
      const orderId = orderIdFromUrl(url) || nearestOrderId(a);
      if (!orderId) continue;
      const meta = returnUrlMetadata(url);
      const token = meta.returnToken || slug(url);
      const itemKey = meta.returnItemId || '';
      const key = `${orderId}:${token}:${itemKey}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const evidence = nearestReturnItemEvidence(a);
      results.push({
        orderId,
        url,
        returnToken: token,
        returnItemId: meta.returnItemId,
        returnContractId: meta.returnContractId,
        returnRmaId: meta.returnRmaId,
        itemNames: evidence.itemNames,
        asins: evidence.asins,
        itemIdentitySource: (evidence.itemNames.length || evidence.asins.length) ? 'order-detail-return-link' : null
      });
    }
    return results;
  }

'''
p = replace_between(p, '  function extractReturnStatusLinks(doc, baseUrl) {', '  function historyRouteFromUrl(url) {', new_extract_links, 'parser extractReturnStatusLinks')

p = replace_once(
    p,
    "    const returnToken = extractReturnToken(url);\n    const detailPage = isOrderDetailPage(url);",
    "    const returnMeta = returnUrlMetadata(url);\n    const returnToken = returnMeta.returnToken;\n    const detailPage = isOrderDetailPage(url);",
    'parser document return metadata')

p = replace_once(
    p,
    "        returnToken,\n        returnStatusUrl: pageType === 'return' ? url : null,",
    "        returnToken,\n        returnItemId: returnMeta.returnItemId,\n        returnContractId: returnMeta.returnContractId,\n        returnRmaId: returnMeta.returnRmaId,\n        returnStatusUrl: pageType === 'return' ? url : null,",
    'parser document options metadata')

old_detail = '''      if (detailPage && record.recordType === 'order') {
        record.detailScanComplete = isCompleteCanonicalDetail(record, url);
        record.detailScannedAt = record.detailScanComplete ? new Date().toISOString() : null;
      }
'''
new_detail = '''      if (detailPage && record.recordType === 'order') {
        record.detailScanComplete = isCompleteCanonicalDetail(record, url);
        record.detailScannedAt = record.detailScanComplete ? new Date().toISOString() : null;
        // Order Details' Refund Total is the canonical order-level refund figure. Keep it separate
        // from child-return amounts so the dashboard can never inflate the order by summing
        // duplicated return-page totals.
        record.canonicalRefundTotal = Number.isFinite(Number(record.refundAmount)) ? Number(record.refundAmount) : null;
      }
'''
p = replace_once(p, old_detail, new_detail, 'parser canonical refund total')

new_return_block = '''      if (pageType === 'return') {
        const returnItems = extractReturnItemEntries(container || doc?.body);
        const groupRefundAmount = Number.isFinite(Number(record.refundAmount ?? record.refundSubtotal))
          ? Number(record.refundAmount ?? record.refundSubtotal)
          : null;
        if (returnItems.length) {
          for (const item of returnItems) {
            const itemRefund = Number.isFinite(Number(item.refundAmount)) ? Number(item.refundAmount) : null;
            const singleItemGroup = returnItems.length === 1;
            const scopedRefund = itemRefund ?? (singleItemGroup ? groupRefundAmount : null);
            const itemRecord = {
              ...record,
              itemNames: item.itemName ? [item.itemName] : [],
              asins: item.asin ? [item.asin] : [],
              returnItemId: singleItemGroup ? record.returnItemId : null,
              refundAmount: scopedRefund,
              refundSubtotal: scopedRefund,
              returnGroupRefundAmount: groupRefundAmount,
              refundAmountScope: itemRefund != null || (singleItemGroup && groupRefundAmount != null) ? 'item' : (groupRefundAmount != null ? 'return' : null),
              itemIdentitySource: (item.itemName || item.asin) ? 'return-page-item' : null,
              provisionalReturn: false,
              authoritativeReturnCapture: true
            };
            itemRecord.recordId = makeRecordId(itemRecord);
            records.push(itemRecord);
          }
        } else {
          record.provisionalReturn = false;
          record.authoritativeReturnCapture = true;
          record.returnGroupRefundAmount = groupRefundAmount;
          record.refundAmountScope = (record.itemNames || []).length === 1 ? 'item' : (groupRefundAmount != null ? 'return' : null);
          record.itemIdentitySource = (record.itemNames || []).length ? 'return-page-item' : null;
          record.recordId = makeRecordId(record);
          records.push(record);
        }
      } else {
        record.recordId = makeRecordId(record);
        records.push(record);
      }

'''
p = replace_between(p, "      if (pageType === 'return') {", "      // Amazon Business sometimes shows a return-status sentence", new_return_block, 'parser return page block')

p = replace_once(
    p,
    "      if (pageType !== 'return' && strongReturnEvidence(context)) {",
    "      if (pageType !== 'return' && strongReturnEvidence(context) && !(detailPage && returnLinks.some(link => link.orderId === orderId))) {",
    'parser suppress broad detail provisional')

old_prov_fields = '''          returnToken: token,
          returnStatusUrl: link.url,
          sourceUrl: url,'''
new_prov_fields = '''          returnToken: token,
          returnItemId: link.returnItemId || null,
          returnContractId: link.returnContractId || null,
          returnRmaId: link.returnRmaId || null,
          itemIdentitySource: link.itemIdentitySource || null,
          returnStatusUrl: link.url,
          sourceUrl: url,'''
p = replace_once(p, old_prov_fields, new_prov_fields, 'parser explicit provisional identity')

# Export helpers for focused regression tests.
p = replace_once(
    p,
    "    extractReturnStatusLinks,\n    extractOrderHistoryLinks,",
    "    extractReturnStatusLinks,\n    returnUrlMetadata,\n    nearestReturnItemEvidence,\n    extractOrderHistoryLinks,",
    'parser helper exports')
write('parser.js', p)

# ---------------- storage.js ----------------
s = read('storage.js')
s = replace_once(
    s,
    "    if (!record || record.recordType !== 'return') return false;\n    if (record.manualState === 'reconciled' || isCreditConfirmed(record)) return false;",
    "    if (!record || record.recordType !== 'return') return false;\n    if (record.itemIdentityConflict) return true;\n    if (record.manualState === 'reconciled' || isCreditConfirmed(record)) return false;",
    'storage identity conflict review')

storage_helpers = '''  function trustedReturnIdentityShouldWin(existing, incoming) {
    if (existing?.recordType !== 'return' || incoming?.recordType !== 'return') return false;
    if (existing.itemIdentitySource !== 'order-detail-return-link') return false;
    if (!existing.returnItemId || !incoming.returnItemId || existing.returnItemId !== incoming.returnItemId) return false;
    const existingAsins = new Set((existing.asins || []).map(value => String(value || '').toUpperCase()).filter(Boolean));
    const incomingAsins = new Set((incoming.asins || []).map(value => String(value || '').toUpperCase()).filter(Boolean));
    if (!existingAsins.size) return false;
    if (!incomingAsins.size) return true;
    for (const asin of existingAsins) if (incomingAsins.has(asin)) return false;
    return true;
  }

'''
marker = '  function mergeRecord(existing, incoming, scannedAt) {'
if marker not in s:
    raise RuntimeError('storage merge marker missing')
s = s.replace(marker, storage_helpers + marker, 1)
s = replace_once(
    s,
    "    const incomingStatusRank = STATUS_RANK[incoming?.status] ?? 0;\n\n    for (const [key, value] of Object.entries(incoming)) {",
    "    const incomingStatusRank = STATUS_RANK[incoming?.status] ?? 0;\n    const preserveTrustedItemIdentity = trustedReturnIdentityShouldWin(existing, incoming);\n\n    for (const [key, value] of Object.entries(incoming)) {",
    'storage merge flag')
s = replace_once(
    s,
    "      if (Array.isArray(value)) {\n        if (incoming?.recordType === 'return' && incoming?.authoritativeReturnCapture && ['itemNames', 'asins'].includes(key)) merged[key] = mergeArray([], value);\n        else merged[key] = mergeArray(existing?.[key], value);\n      }",
    "      if (Array.isArray(value)) {\n        if (preserveTrustedItemIdentity && ['itemNames', 'asins'].includes(key)) {\n          merged[key] = mergeArray([], existing?.[key] || []);\n        } else if (incoming?.recordType === 'return' && incoming?.authoritativeReturnCapture && ['itemNames', 'asins'].includes(key)) merged[key] = mergeArray([], value);\n        else merged[key] = mergeArray(existing?.[key], value);\n      }",
    'storage trusted arrays')
s = replace_once(
    s,
    "      else if (key === 'detailScanComplete') merged[key] = Boolean(existing?.[key] || value);\n      else merged[key] = value;\n    }\n\n    if (merged.recordType === 'return') {",
    "      else if (key === 'detailScanComplete') merged[key] = Boolean(existing?.[key] || value);\n      else if (preserveTrustedItemIdentity && key === 'itemIdentitySource') merged[key] = existing.itemIdentitySource;\n      else merged[key] = value;\n    }\n\n    if (preserveTrustedItemIdentity) {\n      merged.itemIdentityConflict = true;\n      merged.itemIdentityConflictIncoming = {\n        itemNames: mergeArray([], incoming.itemNames || []),\n        asins: mergeArray([], incoming.asins || []),\n        source: incoming.itemIdentitySource || null\n      };\n    }\n\n    if (merged.recordType === 'return') {",
    'storage conflict marker')
write('storage.js', s)

# ---------------- dashboard.js ----------------
d = read('dashboard.js')
new_return_helpers = '''  function returnRecordIdentity(record) {
    const token = String(record?.returnToken || record?.returnStatusUrl || record?.recordId || 'return').toLowerCase();
    const item = String(record?.returnItemId || record?.asins?.[0] || record?.itemNames?.[0] || record?.recordId || 'item').toLowerCase();
    return `${token}:${item}`;
  }
  function dedupeReturns(records) {
    const byKey = new Map();
    for (const r of records || []) {
      const key = returnRecordIdentity(r);
      const existing = byKey.get(key);
      if (!existing || storage.returnStageRank(r) > storage.returnStageRank(existing) || String(r.lastScannedAt || '') > String(existing.lastScannedAt || '')) byKey.set(key, r);
    }
    return Array.from(byKey.values());
  }
  function returnGroupAmount(records) {
    const ordered = (records || []).slice().sort((a,b) => String(b.lastScannedAt || '').localeCompare(String(a.lastScannedAt || '')));
    const explicitGroupValues = [];
    for (const r of ordered) {
      const groupValue = Number(r.returnGroupRefundAmount);
      const scopedValue = r.refundAmountScope === 'return' ? Number(r.refundAmount ?? r.refundSubtotal) : NaN;
      const value = Number.isFinite(groupValue) ? groupValue : scopedValue;
      if (Number.isFinite(value)) explicitGroupValues.push(value);
    }
    if (explicitGroupValues.length) {
      const cents = new Set(explicitGroupValues.map(value => value.toFixed(2)));
      return { amount: explicitGroupValues[0], conflict: cents.size > 1 };
    }
    const itemValues = new Map();
    for (const r of ordered) {
      const value = Number(r.refundAmount ?? r.refundSubtotal);
      if (!Number.isFinite(value)) continue;
      if (r.refundAmountScope === 'item') itemValues.set(returnRecordIdentity(r), value);
    }
    if (itemValues.size) return { amount: Array.from(itemValues.values()).reduce((a,b)=>a+b,0), conflict: false };
    // Legacy records did not mark scope. Treat one amount per return group, never once per child.
    const legacy = ordered.map(r => Number(r.refundAmount ?? r.refundSubtotal)).find(Number.isFinite);
    return { amount: Number.isFinite(legacy) ? legacy : null, conflict: false };
  }
  function groupReturnRecords(records) {
    const groups = new Map();
    for (const record of records || []) {
      const key = String(record.returnToken || record.returnStatusUrl || record.recordId || 'return');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(record);
    }
    return Array.from(groups.entries()).map(([key, groupRecords]) => {
      const representative = groupRecords.slice().sort((a,b) => {
        const rank = storage.returnStageRank(b) - storage.returnStageRank(a);
        if (rank) return rank;
        return String(b.lastScannedAt || '').localeCompare(String(a.lastScannedAt || ''));
      })[0];
      const amountState = returnGroupAmount(groupRecords);
      return {
        key,
        records: groupRecords,
        representative,
        itemNames: uniqueStrings(groupRecords.flatMap(r => r.itemNames || [])),
        asins: uniqueStrings(groupRecords.flatMap(r => r.asins || [])),
        amount: amountState.amount,
        amountConflict: amountState.conflict,
        itemIdentityConflict: groupRecords.some(r => r.itemIdentityConflict)
      };
    });
  }

'''
d = replace_between(d, '  function dedupeReturns(records) {', '  function buildRows() {', new_return_helpers, 'dashboard return helpers')

# Replace the order-row aggregation loop body up to sorting.
start = "    for (const orderId of ids) {\n      const order = orders.get(orderId) || null;"
end = "    return rows.sort((a,b) => {"
new_loop = '''    for (const orderId of ids) {
      const order = orders.get(orderId) || null;
      const returnRecords = dedupeReturns(returns.get(orderId) || []);
      const returnGroups = groupReturnRecords(returnRecords);
      const manualReconciled = returnRecords.some(r => r.manualState === 'reconciled');
      const ranks = returnRecords.map(r => storage.returnStageRank(r));
      const hasReturn = returnRecords.length > 0;
      const allCredited = hasReturn && returnRecords.every(r => storage.isCreditConfirmed(r));
      const allIssued = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.refund_issued);

      const orderItemNames = uniqueStrings(order?.itemNames || []);
      const returnedItemNames = uniqueStrings(returnRecords.flatMap(r => r.itemNames || []));
      const childRefundAmount = returnGroups.reduce((total, group) => total + (Number.isFinite(Number(group.amount)) ? Number(group.amount) : 0), 0);
      const canonicalRefundCandidate = order?.canonicalRefundTotal ?? (order?.detailScanComplete ? order?.refundAmount : null);
      const canonicalRefundTotal = Number.isFinite(Number(canonicalRefundCandidate)) ? Number(canonicalRefundCandidate) : null;
      const refundAmount = canonicalRefundTotal != null ? canonicalRefundTotal : (returnGroups.some(g => Number.isFinite(Number(g.amount))) ? childRefundAmount : null);
      const refundAmountMismatch = canonicalRefundTotal != null && childRefundAmount > canonicalRefundTotal + 0.011;
      const itemIdentityConflict = returnGroups.some(group => group.itemIdentityConflict);
      const groupAmountConflict = returnGroups.some(group => group.amountConflict);
      const needsReview = hasReturn && !manualReconciled && (
        returnRecords.some(r => storage.needsCreditReview(r)) || refundAmountMismatch || itemIdentityConflict || groupAmountConflict
      );

      let stateKey = 'purchase';
      let statusLabel = order?.statusText || (order?.detailScanComplete ? 'Order details captured' : 'Order discovered');
      if (manualReconciled) { stateKey = 'reconciled'; statusLabel = 'Reconciled'; }
      else if (needsReview) {
        stateKey = 'needs_review';
        if (refundAmountMismatch) statusLabel = 'Refund amount mismatch';
        else if (itemIdentityConflict) statusLabel = 'Return item needs review';
        else if (groupAmountConflict) statusLabel = 'Return refund needs review';
        else {
          const lowest = returnRecords.slice().sort((a,b) => storage.returnStageRank(a)-storage.returnStageRank(b))[0];
          statusLabel = stageLabel(storage.getReturnStage(lowest));
        }
      } else if (allCredited) { stateKey = 'credited'; statusLabel = 'Credited'; }
      else if (allIssued) { stateKey = 'refund_issued'; statusLabel = 'Refund issued'; }
      else if (hasReturn) { stateKey = 'return'; statusLabel = stageLabel(storage.getReturnStage(returnRecords[0])); }

      const statusTexts = uniqueStrings(returnRecords.map(r => r.statusText).filter(Boolean));
      const lastScannedAt = [order?.lastScannedAt, ...returnRecords.map(r => r.lastScannedAt)].filter(Boolean).sort().at(-1) || null;
      const itemNames = hasReturn ? returnedItemNames : orderItemNames;
      rows.push({
        orderId, order, returns: returnRecords, returnGroups, hasReturn, needsReview, stateKey, statusLabel,
        itemNames, orderItemNames, returnedItemNames, searchItemNames: uniqueStrings([...orderItemNames, ...returnedItemNames]),
        orderTotal: order?.purchaseAmount ?? null, refundAmount, canonicalRefundTotal, childRefundAmount,
        refundAmountMismatch, itemIdentityConflict, groupAmountConflict,
        cardLast4: order?.cardLast4 || returnRecords.find(r => r.cardLast4)?.cardLast4 || null,
        amazonStatus: statusTexts.length ? statusTexts.join(' · ') : (order?.statusText || order?.status || '—'),
        detailComplete: Boolean(order?.detailScanComplete), detailScannedAt: order?.detailScannedAt || null,
        lastScannedAt, openUrl: canonicalDetailUrl(orderId, order)
      });
    }
'''
d = replace_between(d, start, end, new_loop, 'dashboard row aggregation')

new_lifecycle = '''  function lifecycleMarkup(group, index, totalGroups) {
    const record = group.representative;
    const progress = storage.returnProgress(record);
    const expectedCredit = !progress.credited ? storage.expectedCreditDate(record) || '' : '';
    const verificationRecord = group.records.find(r => r.bankVerification) || record;
    const verification = verificationRecord.bankVerification || null;
    const creditDate = progress.bankCreditConfirmed
      ? (verification?.postedDate || verification?.verifiedAt || '')
      : progress.amazonCredited
        ? milestoneDate(record, 'credited')
        : '';
    const steps = [
      ['started', 'Initiated', progress.started, milestoneDate(record, 'started')],
      ['shipped', 'Dropped off', progress.shippedOrReceived, milestoneDate(record, 'shipped')],
      ['refundIssued', 'Refund issued', progress.refundIssued, milestoneDate(record, 'refundIssued')],
      ['credited', progress.credited ? 'Bank credited' : (expectedCredit ? `Expected ${expectedCredit}` : 'Credit pending'), progress.credited, creditDate]
    ];
    const items = group.itemNames.length ? group.itemNames.join(' · ') : 'Returned item pending authoritative scan';
    let verificationMarkup = '';
    if (verification) {
      if (verification.status === 'confirmed') {
        const details = [verification.matchedAmount != null ? money(verification.matchedAmount) : '', verification.postedDate || '', verification.accountLast4 ? `•••• ${verification.accountLast4}` : ''].filter(Boolean).join(' · ');
        verificationMarkup = `<div class="bank-match bank-match-confirmed"><strong>Bank confirmed</strong>${details ? `<span>${esc(details)}</span>` : ''}</div>`;
      } else if (verification.status === 'ambiguous' || verification.status === 'needs_review') {
        verificationMarkup = `<div class="bank-match bank-match-review"><strong>Bank match needs review</strong><span>${esc(verification.reason || 'Multiple plausible credits.')}</span></div>`;
      }
    }
    const warnings = [group.itemIdentityConflict ? 'Item identity conflict' : '', group.amountConflict ? 'Refund amount conflict' : ''].filter(Boolean).join(' · ');
    return `<div class="return-track-item compact-return-track">
      <div class="return-track-title">Return ${index}${totalGroups > 1 ? ` of ${totalGroups}` : ''} · ${esc(items)}</div>
      <div class="return-track-meta"><span>${esc(stageLabel(storage.getReturnStage(record)))}</span><strong>${money(group.amount)}</strong></div>
      ${warnings ? `<div class="muted tiny">${esc(warnings)}</div>` : ''}
      <div class="lifecycle lifecycle-lineitem">
        <div class="lifecycle-line"><span style="width:${progress.percent}%"></span></div>
        ${steps.map(step => `<div class="life-step ${step[2] ? 'done' : ''}"><small>${esc(step[3] || '')}</small><i>${step[2] ? '✓' : ''}</i><span>${esc(step[1])}</span></div>`).join('')}
      </div>
      ${verificationMarkup}
    </div>`;
  }
  function returnProgressMarkup(row) {
    if (!row.returnGroups.length) return '<span class="muted">—</span>';
    return `<div class="return-track-stack compact-return-stack">${row.returnGroups.map((group, index) => lifecycleMarkup(group, index + 1, row.returnGroups.length)).join('')}</div>`;
  }

'''
d = replace_between(d, '  function lifecycleMarkup(record, showItemTitle = false) {', '  function filteredRows() {', new_lifecycle, 'dashboard lifecycle grouping')

d = replace_once(
    d,
    "        const hay = [row.orderId, ...row.itemNames, row.cardLast4, row.statusLabel, row.amazonStatus, row.orderTotal, row.refundAmount].join(' ').toLowerCase();",
    "        const hay = [row.orderId, ...(row.searchItemNames || row.itemNames), row.cardLast4, row.statusLabel, row.amazonStatus, row.orderTotal, row.refundAmount].join(' ').toLowerCase();",
    'dashboard search items')

old_amount_fn = '''  function returnRecordAmountTotal(records) {
    const values = new Map();
    for (const r of records || []) {
      const amount = Number(r.refundAmount ?? r.refundSubtotal);
      if (!Number.isFinite(amount)) continue;
      const key = r.returnToken || `${amount.toFixed(2)}:${uniqueStrings([...(r.asins || []), ...(r.itemNames || [])]).join('|').toLowerCase()}`;
      if (!values.has(key)) values.set(key, amount);
    }
    return Array.from(values.values()).reduce((a,b) => a + b, 0);
  }
'''
new_amount_fn = '''  function returnRecordAmountTotal(records) {
    return groupReturnRecords(dedupeReturns(records || [])).reduce((total, group) => total + (Number.isFinite(Number(group.amount)) ? Number(group.amount) : 0), 0);
  }
'''
d = replace_once(d, old_amount_fn, new_amount_fn, 'dashboard group-aware amount total')

d = replace_once(
    d,
    "      const items = row.itemNames.length ? row.itemNames.join(' · ') : 'Item title pending Order Details scan';",
    "      const items = row.itemNames.length ? row.itemNames.join(' · ') : (row.hasReturn ? `${row.returnGroups.length} return${row.returnGroups.length === 1 ? '' : 's'} pending item identity` : 'Item title pending Order Details scan');",
    'dashboard compact returned items')
write('dashboard.js', d)

# ---------------- content.js ----------------
c = read('content.js')
c = replace_once(
    c,
    "      const key = record.returnToken || `${record.refundAmount ?? record.refundSubtotal ?? ''}:${(record.itemNames || []).join('|')}:${record.returnStage || ''}`;",
    "      const key = `${record.returnToken || record.returnStatusUrl || 'return'}:${record.returnItemId || record.asins?.[0] || record.itemNames?.[0] || record.recordId || 'item'}`;",
    'content return decoration identity')
write('content.js', c)

# ---------------- background.js ----------------
b = read('background.js')
old_refresh_loop = '''    let returnsRefreshed = 0;
    for (const link of (detailResult.returnLinks || []).filter(link => link?.orderId === id && link?.url && /\/spr\/returns\/prep/i.test(link.url))) {
      await navigateExistingWorkerTab(tabId, link.url);
      const returnResult = await scanWorkerTab(tabId, { type: 'return', manualRefresh: true, orderId: id, url: link.url });
      const matched = (returnResult.records || []).some(r => r?.recordType === 'return' && r?.orderId === id && r?.authoritativeReturnCapture);
      if (!matched) throw new Error('Amazon return-status page did not produce an authoritative return record.');
      returnsRefreshed += 1;
    }
'''
new_refresh_loop = '''    let returnsRefreshed = 0;
    const uniqueReturnLinks = new Map();
    for (const link of (detailResult.returnLinks || []).filter(link => link?.orderId === id && link?.url && /\/spr\/returns\/prep/i.test(link.url))) {
      const key = `${link.returnToken || link.url}:${link.returnItemId || ''}`;
      if (!uniqueReturnLinks.has(key)) uniqueReturnLinks.set(key, link);
    }
    for (const link of uniqueReturnLinks.values()) {
      await navigateExistingWorkerTab(tabId, link.url);
      const returnResult = await scanWorkerTab(tabId, { type: 'return', manualRefresh: true, orderId: id, url: link.url });
      const matched = (returnResult.records || []).some(r =>
        r?.recordType === 'return' && r?.orderId === id && r?.authoritativeReturnCapture &&
        (!link.returnToken || r.returnToken === link.returnToken) &&
        (!link.returnItemId || !r.returnItemId || r.returnItemId === link.returnItemId)
      );
      if (!matched) throw new Error('Amazon return-status page did not produce the expected authoritative return child.');
      returnsRefreshed += 1;
    }
'''
b = replace_once(b, old_refresh_loop, new_refresh_loop, 'background unique return refresh')
write('background.js', b)

# ---------------- dev-updater.js ----------------
new_dev_updater = r'''\'use strict\';

const DEV_UPDATE_HOST_NAME = 'com.supremefabworks.amazon_order_manager_updater';
const DEV_UPDATE_PROTOCOL = 'arl-dev-updater-v1';
const DEV_UPDATE_ALARM_NAME = 'arl-dev-auto-update';
const DEV_UPDATE_STATUS_KEY = 'devUpdateStatus';
const DEV_UPDATE_PERIOD_MINUTES = 15;
const DEV_UPDATE_INITIAL_DELAY_MINUTES = 0.5;
const DEV_UPDATE_BOOT_THROTTLE_MS = 5 * 60 * 1000;
const DEV_AUTO_UPDATE_ENABLED = true;

let devUpdateCheckInFlight = null;

function extensionVersionParts(value) {
  const text = String(value || '').trim();
  if (!/^\d+(?:\.\d+){0,3}$/.test(text)) return null;
  const parts = text.split('.').map(Number);
  if (parts.some(part => !Number.isInteger(part) || part < 0 || part > 65535)) return null;
  while (parts.length < 4) parts.push(0);
  return parts;
}

function compareExtensionVersions(a, b) {
  const left = extensionVersionParts(a);
  const right = extensionVersionParts(b);
  if (!left || !right) return null;
  for (let i = 0; i < 4; i += 1) {
    if (left[i] > right[i]) return 1;
    if (left[i] < right[i]) return -1;
  }
  return 0;
}

async function readDevUpdateStatus() {
  try {
    const data = await chrome.storage.local.get([DEV_UPDATE_STATUS_KEY]);
    return data?.[DEV_UPDATE_STATUS_KEY] || null;
  } catch (_) { return null; }
}

async function writeDevUpdateStatus(status) {
  try {
    const previous = await readDevUpdateStatus() || {};
    await chrome.storage.local.set({
      [DEV_UPDATE_STATUS_KEY]: {
        ...previous,
        ...status,
        updatedAt: new Date().toISOString()
      }
    });
  } catch (_) {}
}

async function ensureDevUpdateAlarm() {
  if (!DEV_AUTO_UPDATE_ENABLED) return { ok: true, enabled: false };
  try {
    let existing = null;
    try { existing = await chrome.alarms.get(DEV_UPDATE_ALARM_NAME); } catch (_) {}
    if (!existing || Number(existing.periodInMinutes) !== DEV_UPDATE_PERIOD_MINUTES) {
      const options = {
        delayInMinutes: DEV_UPDATE_INITIAL_DELAY_MINUTES,
        periodInMinutes: DEV_UPDATE_PERIOD_MINUTES,
        persistAcrossSessions: true
      };
      try {
        await chrome.alarms.create(DEV_UPDATE_ALARM_NAME, options);
      } catch (_) {
        delete options.persistAcrossSessions;
        await chrome.alarms.create(DEV_UPDATE_ALARM_NAME, options);
      }
    }
    return { ok: true, enabled: true };
  } catch (error) {
    const message = error?.message || String(error);
    await writeDevUpdateStatus({ alarmOk: false, error: `Update alarm: ${message}` });
    return { ok: false, error: message };
  }
}

async function performDevUpdateCheck(reason = 'scheduled') {
  if (!DEV_AUTO_UPDATE_ENABLED) return { ok: true, enabled: false, updated: false };

  const currentVersion = chrome.runtime.getManifest()?.version || null;
  if (!currentVersion || !extensionVersionParts(currentVersion)) {
    return { ok: false, updated: false, error: 'Current extension version is invalid.' };
  }

  await writeDevUpdateStatus({
    ok: null,
    checking: true,
    reason,
    currentVersion,
    lastCheckStartedAt: new Date().toISOString(),
    error: null
  });

  const request = {
    protocol: DEV_UPDATE_PROTOCOL,
    action: 'check_update',
    currentVersion,
    extensionId: chrome.runtime.id || null,
    reason
  };

  let response;
  try {
    response = await chrome.runtime.sendNativeMessage(DEV_UPDATE_HOST_NAME, request);
  } catch (error) {
    const message = error?.message || String(error);
    await writeDevUpdateStatus({
      ok: false,
      checking: false,
      hostAvailable: false,
      reason,
      currentVersion,
      error: message,
      lastCheckedAt: new Date().toISOString()
    });
    return { ok: false, updated: false, hostAvailable: false, currentVersion, error: message };
  }

  if (!response || response.protocol !== DEV_UPDATE_PROTOCOL) {
    const error = 'Native updater returned an invalid protocol response.';
    await writeDevUpdateStatus({ ok: false, checking: false, hostAvailable: true, reason, currentVersion, error, lastCheckedAt: new Date().toISOString() });
    return { ok: false, updated: false, hostAvailable: true, currentVersion, error };
  }

  if (response.ok !== true) {
    const error = response.error || 'Native updater reported an error.';
    await writeDevUpdateStatus({
      ok: false, checking: false, hostAvailable: true, reason, currentVersion,
      latestVersion: response.latestVersion || null, error, lastCheckedAt: new Date().toISOString()
    });
    return { ok: false, updated: false, hostAvailable: true, currentVersion, latestVersion: response.latestVersion || null, error };
  }

  const installedVersion = response.installedVersion || response.latestVersion || null;
  const comparison = installedVersion ? compareExtensionVersions(installedVersion, currentVersion) : null;
  const shouldReload = response.updated === true && comparison === 1;
  const now = new Date().toISOString();
  const result = {
    ok: true,
    updated: shouldReload,
    hostAvailable: true,
    currentVersion,
    latestVersion: response.latestVersion || installedVersion || currentVersion,
    installedVersion: installedVersion || currentVersion,
    status: response.status || (shouldReload ? 'updated' : 'up_to_date')
  };

  await writeDevUpdateStatus({
    ...result,
    checking: false,
    reason,
    error: null,
    lastCheckedAt: now,
    ...(shouldReload ? { lastInstalledAt: now, lastReloadRequestedAt: now } : {})
  });

  // MV3 service workers may be suspended before a timer callback runs. Reload synchronously after
  // the verified install instead of relying on a setTimeout that may never fire.
  if (shouldReload) {
    try { chrome.runtime.reload(); }
    catch (error) {
      await writeDevUpdateStatus({ ok: false, checking: false, error: `Reload failed: ${error?.message || error}` });
      return { ...result, ok: false, updated: false, error: error?.message || String(error) };
    }
  }

  return result;
}

function checkForDevUpdate(reason = 'scheduled') {
  if (devUpdateCheckInFlight) return devUpdateCheckInFlight;
  devUpdateCheckInFlight = performDevUpdateCheck(reason)
    .finally(() => { devUpdateCheckInFlight = null; });
  return devUpdateCheckInFlight;
}

async function initializeDevUpdater(reason = 'worker-start', force = false) {
  await ensureDevUpdateAlarm();
  if (!force) {
    const status = await readDevUpdateStatus();
    const last = status?.lastCheckedAt ? new Date(status.lastCheckedAt).getTime() : 0;
    if (Number.isFinite(last) && Date.now() - last < DEV_UPDATE_BOOT_THROTTLE_MS) {
      return { ok: true, skipped: true, reason: 'recently-checked', currentVersion: chrome.runtime.getManifest()?.version || null };
    }
  }
  return checkForDevUpdate(reason);
}

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm?.name === DEV_UPDATE_ALARM_NAME) checkForDevUpdate('alarm').catch(() => {});
});

chrome.runtime.onStartup.addListener(() => {
  initializeDevUpdater('startup', true).catch(() => {});
});

chrome.runtime.onInstalled.addListener(() => {
  ensureDevUpdateAlarm().catch(() => {});
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'ARL_CHECK_DEV_UPDATE') {
    initializeDevUpdater('manual', true)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ ok: false, updated: false, error: error?.message || String(error) }));
    return true;
  }

  if (message?.type === 'ARL_GET_DEV_UPDATE_STATUS') {
    readDevUpdateStatus()
      .then(status => sendResponse({ ok: true, status }))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
});

// Important update checks must exist whenever the MV3 worker starts. Chrome explicitly recommends
// recreating important alarms at worker startup because alarm persistence can vary across versions.
initializeDevUpdater('worker-start').catch(() => {});
'''
new_dev_updater = new_dev_updater.replace("\\'use strict\\';", "'use strict';", 1)
write('dev-updater.js', new_dev_updater)

# ---------------- popup UI ----------------
ph = read('popup.html')
ph = replace_once(ph, '<div class="eyebrow">AMAZON REFUND LEDGER · v0.16</div>', '<div class="eyebrow" id="versionLabel">AMAZON REFUND LEDGER</div>', 'popup dynamic version')
ph = replace_once(
    ph,
    '    <button id="dashboardButton" class="secondary">Open dashboard</button>\n\n    <div id="result" class="result hidden"></div>',
    '    <button id="dashboardButton" class="secondary">Open dashboard</button>\n\n    <div id="devUpdateStatus" class="result">Checking development update status…</div>\n    <button id="checkUpdateButton" class="secondary">Check development update now</button>\n\n    <div id="result" class="result hidden"></div>',
    'popup updater controls')
write('popup.html', ph)

pj = read('popup.js')
pj = replace_once(
    pj,
    "  const result = document.getElementById('result');\n  let scannerState = null;",
    "  const result = document.getElementById('result');\n  const versionLabel = document.getElementById('versionLabel');\n  const devUpdateStatus = document.getElementById('devUpdateStatus');\n  const checkUpdateButton = document.getElementById('checkUpdateButton');\n  let scannerState = null;\n  versionLabel.textContent = `AMAZON REFUND LEDGER · v${chrome.runtime.getManifest()?.version || '—'}`;",
    'popup updater refs')
# Canonical order refund total in popup.
old_popup_return = "        returnCount += 1;\n        returnTotal += refundTotal(rs);"
new_popup_return = "        returnCount += 1;\n        const canonical = Number(order?.canonicalRefundTotal ?? (order?.detailScanComplete ? order?.refundAmount : null));\n        returnTotal += Number.isFinite(canonical) ? canonical : refundTotal(rs);"
pj = replace_once(pj, old_popup_return, new_popup_return, 'popup canonical refund')

popup_update_functions = '''  async function renderDevUpdateStatus() {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'ARL_GET_DEV_UPDATE_STATUS' });
      const status = response?.status || null;
      const current = chrome.runtime.getManifest()?.version || '—';
      if (!status) {
        devUpdateStatus.textContent = `Development updater · current ${current} · no check recorded yet`;
        devUpdateStatus.className = 'result warn';
        return;
      }
      const latest = status.latestVersion || status.installedVersion || current;
      const checked = status.lastCheckedAt || status.lastCheckStartedAt || '';
      const suffix = status.error ? ` · ${status.error}` : status.checking ? ' · checking…' : status.hostAvailable === false ? ' · native host unavailable' : '';
      devUpdateStatus.textContent = `Development updater · current ${current} · latest ${latest}${checked ? ` · checked ${new Date(checked).toLocaleTimeString()}` : ''}${suffix}`;
      devUpdateStatus.className = `result ${status.error || status.hostAvailable === false ? 'warn' : 'ok'}`;
    } catch (error) {
      devUpdateStatus.textContent = `Development updater status unavailable · ${error?.message || error}`;
      devUpdateStatus.className = 'result warn';
    }
  }
'''
insert_marker = '  function formatRemaining(ms) {'
if insert_marker not in pj:
    raise RuntimeError('popup format marker missing')
pj = pj.replace(insert_marker, popup_update_functions + insert_marker, 1)

pj = replace_once(
    pj,
    "  dashboardButton.addEventListener('click', () => openDashboard('all'));\n  scanToggleButton.addEventListener('click', async () => {",
    "  dashboardButton.addEventListener('click', () => openDashboard('all'));\n  checkUpdateButton.addEventListener('click', async () => {\n    checkUpdateButton.disabled = true;\n    checkUpdateButton.textContent = 'Checking…';\n    try {\n      const response = await chrome.runtime.sendMessage({ type: 'ARL_CHECK_DEV_UPDATE' });\n      if (!response?.ok) throw new Error(response?.error || 'Update check failed');\n      await renderDevUpdateStatus();\n    } catch (error) {\n      devUpdateStatus.textContent = `Development update failed · ${error?.message || error}`;\n      devUpdateStatus.className = 'result warn';\n    } finally {\n      checkUpdateButton.disabled = false;\n      checkUpdateButton.textContent = 'Check development update now';\n    }\n  });\n  scanToggleButton.addEventListener('click', async () => {",
    'popup manual update action')
pj = replace_once(
    pj,
    "    if (changes.backgroundScanState) renderScanner().catch(()=>{});\n  });\n  renderLedger(); renderScanner(); setInterval(renderScanner,1600);",
    "    if (changes.backgroundScanState) renderScanner().catch(()=>{});\n    if (changes.devUpdateStatus) renderDevUpdateStatus().catch(()=>{});\n  });\n  renderLedger(); renderScanner(); renderDevUpdateStatus(); setInterval(renderScanner,1600);",
    'popup status refresh')
write('popup.js', pj)

# ---------------- NativeHost.cs logging + self-test ----------------
nh = read('tools/dev-updater/NativeHost.cs')
nh = replace_once(
    nh,
    '        private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();\n',
    '''        private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();

        private static string InstallRootPath
        {
            get
            {
                DirectoryInfo hostDirectory = new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);
                return hostDirectory.Parent != null ? hostDirectory.Parent.FullName : hostDirectory.FullName;
            }
        }

        private static string LogPath { get { return Path.Combine(InstallRootPath, "updater.log"); } }

        private static void Log(string message)
        {
            try
            {
                File.AppendAllText(LogPath, DateTime.UtcNow.ToString("o") + " " + (message ?? String.Empty) + Environment.NewLine, Encoding.UTF8);
            }
            catch { }
        }
''',
    'native logging helpers')
nh = replace_once(
    nh,
    '''        public static int Main(string[] args)
        {
            UpdateResponse response;
            try
            {
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;

                string callerOrigin = args != null && args.Length > 0 ? args[0] : null;''',
    '''        public static int Main(string[] args)
        {
            if (args != null && args.Length > 0 && String.Equals(args[0], "--self-test", StringComparison.OrdinalIgnoreCase))
                return RunSelfTest();

            UpdateResponse response;
            try
            {
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;

                string callerOrigin = args != null && args.Length > 0 ? args[0] : null;
                Log("native-message start origin=" + (callerOrigin ?? "(null)"));''',
    'native main self test')
nh = replace_once(
    nh,
    '''                response = CheckForUpdate(request.currentVersion);
            }
            catch (Exception ex)
            {
                response = new UpdateResponse''',
    '''                Log("check request current=" + (request.currentVersion ?? "(null)") + " reason=" + (request.reason ?? "(null)"));
                response = CheckForUpdate(request.currentVersion);
                Log("check result status=" + (response.status ?? "(null)") + " latest=" + (response.latestVersion ?? "(null)") + " installed=" + (response.installedVersion ?? "(null)"));
            }
            catch (Exception ex)
            {
                Log("native-message error=" + SafeError(ex));
                response = new UpdateResponse''',
    'native main logging')

self_test = '''        private static int RunSelfTest()
        {
            try
            {
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
                string currentManifest = Path.Combine(InstallRootPath, "current", "manifest.json");
                string currentVersion = "missing";
                if (File.Exists(currentManifest))
                {
                    ManifestInfo manifest = Serializer.Deserialize<ManifestInfo>(File.ReadAllText(currentManifest, Encoding.UTF8));
                    currentVersion = manifest != null && !String.IsNullOrWhiteSpace(manifest.version) ? manifest.version : "invalid";
                }
                ReleaseCandidate latest = FindLatestDevelopmentRelease();
                string latestVersion = latest != null ? NormalizeVersion(latest.Version) : "none";
                string summary = "SELF_TEST_OK current=" + currentVersion + " latest=" + latestVersion + " log=" + LogPath;
                Log(summary);
                Console.WriteLine(summary);
                return 0;
            }
            catch (Exception ex)
            {
                string message = "SELF_TEST_FAILED " + SafeError(ex);
                Log(message);
                Console.Error.WriteLine(message);
                return 1;
            }
        }

'''
marker = '        private static UpdateResponse CheckForUpdate(string currentVersionText)'
if marker not in nh:
    raise RuntimeError('native check marker missing')
nh = nh.replace(marker, self_test + marker, 1)
nh = replace_once(
    nh,
    '            ReleaseCandidate candidate = FindLatestDevelopmentRelease();\n',
    '            ReleaseCandidate candidate = FindLatestDevelopmentRelease();\n            Log("release lookup current=" + currentVersionText + " latest=" + (candidate != null ? NormalizeVersion(candidate.Version) : "none"));\n',
    'native release lookup log')
nh = replace_once(
    nh,
    '                ValidatePackage(packageRoot, candidate.Version);\n                InstallPackage(packageRoot);\n',
    '                ValidatePackage(packageRoot, candidate.Version);\n                Log("package verified sha256=" + actualHash + " version=" + latestVersionText);\n                InstallPackage(packageRoot);\n                Log("package installed version=" + latestVersionText);\n',
    'native install log')
write('tools/dev-updater/NativeHost.cs', nh)

# ---------------- Install.ps1 diagnostics ----------------
ins = read('tools/dev-updater/Install.ps1')
ins = replace_once(
    ins,
    "param(\n    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'SupremeFabWorks\\AmazonOrderManagerDev')\n)",
    "param(\n    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'SupremeFabWorks\\AmazonOrderManagerDev'),\n    [switch]$DiagnoseOnly\n)",
    'installer diagnose param')
ins = replace_once(
    ins,
    "    & $windowsPowerShell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -InstallRoot $InstallRoot\n    exit $LASTEXITCODE",
    "    $forward = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-InstallRoot',$InstallRoot)\n    if ($DiagnoseOnly) { $forward += '-DiagnoseOnly' }\n    & $windowsPowerShell @forward\n    exit $LASTEXITCODE",
    'installer forward diagnose')

diag_fn = r'''function Show-Diagnostics {
    Write-Host ''
    Write-Host 'Amazon Order Manager development updater diagnostics' -ForegroundColor Cyan
    Write-Host "Install root: $InstallRoot"
    Write-Host "Host executable: $HostExe"
    Write-Host "Host manifest: $HostManifest"
    Write-Host "Current extension: $CurrentDirectory"
    $registryPath = "Registry::HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\$HostName"
    $registered = $null
    try {
        $key = Get-Item -LiteralPath $registryPath -ErrorAction Stop
        $registered = $key.GetValue('')
    } catch {}
    Write-Host "Registry manifest: $($registered ?? '(missing)')"
    $currentManifest = Join-Path $CurrentDirectory 'manifest.json'
    if (Test-Path $currentManifest) {
        try {
            $currentVersion = (Get-Content -Raw -Path $currentManifest | ConvertFrom-Json).version
            Write-Host "Current files version: $currentVersion"
        } catch { Write-Host 'Current manifest: invalid' -ForegroundColor Yellow }
    } else { Write-Host 'Current manifest: missing' -ForegroundColor Yellow }
    if (Test-Path $HostExe) {
        & $HostExe --self-test
        if ($LASTEXITCODE -ne 0) { Write-Host "Native host self-test failed with exit code $LASTEXITCODE" -ForegroundColor Yellow }
    } else { Write-Host 'Native host executable is missing.' -ForegroundColor Yellow }
    $logPath = Join-Path $InstallRoot 'updater.log'
    Write-Host "Updater log: $logPath"
    if (Test-Path $logPath) {
        Write-Host 'Last updater log lines:'
        Get-Content -Path $logPath -Tail 12
    }
    Write-Host ''
}

'''
marker = "function Write-Utf8NoBom"
if marker not in ins:
    raise RuntimeError('installer function marker missing')
ins = ins.replace(marker, diag_fn + marker, 1)
# Diagnose-only short circuit after functions used by Show-Diagnostics are not required; it only uses vars and host.
# Put it after Get-ExpectedHash/Copy functions? Simpler just before NativeSource check, all functions already declared.
ins = replace_once(
    ins,
    "if (-not (Test-Path $NativeSource)) {\n    throw \"NativeHost.cs was not found next to this installer: $NativeSource\"\n}",
    "if ($DiagnoseOnly) { Show-Diagnostics; exit 0 }\n\nif (-not (Test-Path $NativeSource)) {\n    throw \"NativeHost.cs was not found next to this installer: $NativeSource\"\n}",
    'installer diagnose short circuit')
ins = replace_once(
    ins,
    "Write-Host 'After that, merged versioned dev releases are checked automatically at Chrome startup and every 15 minutes.'",
    "Write-Host 'After that, merged versioned dev releases are checked on worker startup, Chrome startup, manually from the popup, and every 15 minutes.'\nWrite-Host \"Updater log: $(Join-Path $InstallRoot 'updater.log')\"\nWrite-Host ''\nShow-Diagnostics",
    'installer final diagnostics')
write('tools/dev-updater/Install.ps1', ins)

# ---------------- version/package/test suite ----------------
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.2'
manifest['version_name'] = '0.18.2'
manifest['description'] = 'Amazon order/refund ledger with authoritative multi-return details, strict crawling, verified payment evidence, and observable local dev auto-updates.'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')

package = json.loads(read('package.json'))
package['version'] = '0.18.2'
package['scripts']['test'] = 'node parser-test.js && node payment-evidence-test.js && node multi-return-test.js && node storage-test.js && node background-test.js && node state-machine-test.js && node reconciliation-test.js && node ui-test.js && node dev-updater-test.js && node updater-reliability-test.js && node release-test.js'
write('package.json', json.dumps(package, indent=2) + '\n')

multi_test = r'''const fs = require('fs');
const vm = require('vm');
const sandbox = { window: {}, URL };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/parser.js', 'utf8'), sandbox);
const p = sandbox.window.AmazonRefundParser;
function assert(condition, message) { if (!condition) throw new Error(message); }

const orderId = '113-7000000-3000000';
function productAnchor(asin, title) {
  return {
    innerText: title, textContent: title, href: `https://www.amazon.com/dp/${asin}`,
    getAttribute(name) { return name === 'href' ? `/dp/${asin}` : null; }, parentElement: null
  };
}
function returnAnchor(itemId, contractId, rmaId) {
  const href = `/spr/returns/prep?orderId=${orderId}&contractId=${contractId}&rmaId=${rmaId}&itemId=${itemId}`;
  return {
    innerText: 'View return/refund status', textContent: 'View return/refund status', href,
    getAttribute(name) { return name === 'href' ? href : null; }, parentElement: null
  };
}
function itemBlock(asin, title, itemId, contractId, rmaId) {
  const product = productAnchor(asin, title);
  const ret = returnAnchor(itemId, contractId, rmaId);
  const block = {
    innerText: `Return complete\nYour return is complete. Your refund has been issued.\n${title}`,
    textContent: '', parentElement: null,
    querySelectorAll(selector) { return selector === 'a[href]' ? [product, ret] : []; }
  };
  product.parentElement = block; ret.parentElement = block;
  return { block, product, ret };
}
const a = itemBlock('B000000001', 'Returned Hydraulic Hose', 'item-a', 'contract-a', 'RMA-A');
const b = itemBlock('B000000002', 'Returned Repair Kit', 'item-b', 'contract-b', 'RMA-B');
const c = itemBlock('B000000003', 'Returned JIC Fittings', 'item-c', 'contract-c', 'RMA-C');
const allAnchors = [a.product,a.ret,b.product,b.ret,c.product,c.ret];
const doc = { querySelectorAll(selector) { return selector === 'a[href]' ? allAnchors : []; } };
const links = p.extractReturnStatusLinks(doc, `https://www.amazon.com/your-orders/order-details?orderID=${orderId}`);
assert(links.length === 3, 'three explicit return links must remain three distinct return groups');
assert(links.map(x => x.itemNames[0]).join('|') === 'Returned Hydraulic Hose|Returned Repair Kit|Returned JIC Fittings', 'each return link must bind to its nearest product title');
assert(links.map(x => x.asins[0]).join('|') === 'B000000001|B000000002|B000000003', 'each return link must bind to its nearest ASIN');
assert(links.map(x => x.returnItemId).join('|') === 'item-a|item-b|item-c', 'return itemId must be retained');
assert(new Set(links.map(x => x.returnToken)).size === 3, 'independent RMA values must remain distinct return tokens');

const provisional = { recordType:'return', orderId, returnToken:'RMA-A', returnItemId:'item-a', itemNames:['Returned Hydraulic Hose'], asins:['B000000001'], provisionalReturn:true };
const authoritative = { ...provisional, provisionalReturn:false, authoritativeReturnCapture:true, itemNames:['Returned Hydraulic Hose Updated'] };
assert(p.makeRecordId(provisional) === p.makeRecordId(authoritative), 'provisional and authoritative capture for the same itemId must use one stable record ID');
const sibling = { ...provisional, returnItemId:'item-b' };
assert(p.makeRecordId(provisional) !== p.makeRecordId(sibling), 'different itemIds under one order/return must not collide');

const meta = p.returnUrlMetadata(`https://www.amazon.com/spr/returns/prep?orderId=${orderId}&contractId=contract-x&rmaId=RMA-X&itemId=item-x`);
assert(meta.returnToken === 'RMA-X' && meta.returnItemId === 'item-x' && meta.returnContractId === 'contract-x' && meta.returnRmaId === 'RMA-X', 'return URL metadata must preserve Amazon return identity');
console.log('multi-return identity tests passed');
'''
write('multi-return-test.js', multi_test)

# Append trusted identity regression to storage-test before final log.
st = read('storage-test.js')
st = replace_once(
    st,
    "  console.log('storage tests passed');",
    '''  const trustedReturn = {
    recordId: 'return:113-7000000-3000000:rma-trusted:item-item-a', recordType: 'return', orderId: '113-7000000-3000000',
    returnToken: 'RMA-TRUSTED', returnItemId: 'item-a', itemNames: ['Trusted Order Details Item'], asins: ['B000000010'],
    itemIdentitySource: 'order-detail-return-link', status: 'return_in_progress', returnStage: 'started', provisionalReturn: true
  };
  await s.upsertRecords([trustedReturn]);
  await s.upsertRecords([{ ...trustedReturn, itemNames: ['Wrong Return Page Sibling'], asins: ['B000000099'], itemIdentitySource: 'return-page-item', authoritativeReturnCapture: true, provisionalReturn: false, status: 'refunded', returnStage: 'refund_issued' }]);
  const trustedMerged = (await s.getLedger()).find(r => r.recordId === trustedReturn.recordId);
  assert(trustedMerged.itemNames[0] === 'Trusted Order Details Item', 'exact Order Details return-link identity must survive conflicting return-page item text');
  assert(trustedMerged.asins[0] === 'B000000010', 'trusted return-link ASIN must survive a conflicting authoritative-page ASIN');
  assert(trustedMerged.itemIdentityConflict === true, 'conflicting return-page identity must be flagged instead of silently replacing trusted identity');
  assert(s.needsCreditReview(trustedMerged) === true, 'item identity conflicts must require review');

  console.log('storage tests passed');''',
    'storage test trusted identity')
write('storage-test.js', st)

# Strengthen UI static regression checks.
uit = read('ui-test.js')
uit = replace_once(
    uit,
    "assert(css.includes('overflow-x: hidden'), 'ledger must continue forbidding horizontal order scrolling');\nconsole.log('ui regression tests passed');",
    "assert(css.includes('overflow-x: hidden'), 'ledger must continue forbidding horizontal order scrolling');\nassert(dashboard.includes('groupReturnRecords'), 'dashboard must group child return records by Amazon return token');\nassert(dashboard.includes('canonicalRefundTotal'), 'dashboard must prefer canonical Order Details Refund Total');\nassert(dashboard.includes('refundAmountMismatch'), 'dashboard must flag child-return totals that exceed canonical refund total');\nassert(dashboard.includes('Return ${index}'), 'dashboard must render distinct compact child return blocks');\nconsole.log('ui regression tests passed');",
    'ui multi-return assertions')
write('ui-test.js', uit)

# Replace updater test to cover worker-start check and synchronous reload.
up_test = r'''const fs = require('fs');
const vm = require('vm');
function assert(condition, message) { if (!condition) throw new Error(message); }

(async () => {
  const alarms = [];
  const listeners = { alarm: [], startup: [], installed: [], message: [] };
  const statusWrites = [];
  const nativeCalls = [];
  let reloadCount = 0;
  let storedStatus = null;
  let nativeResponse = { protocol:'arl-dev-updater-v1', ok:true, updated:false, status:'up_to_date', latestVersion:'0.18.2', installedVersion:'0.18.2' };
  const chrome = {
    alarms: {
      async get() { return null; },
      async create(name, options) { alarms.push({ name, options }); },
      onAlarm: { addListener: fn => listeners.alarm.push(fn) }
    },
    storage: { local: {
      async get() { return storedStatus ? { devUpdateStatus: storedStatus } : {}; },
      async set(value) { statusWrites.push(value); if (value.devUpdateStatus) storedStatus = value.devUpdateStatus; }
    } },
    runtime: {
      id:'hhmimkpolikhncnbkkbbabbopbccabcf', getManifest:()=>({version:'0.18.2'}),
      async sendNativeMessage(host,message) { nativeCalls.push({host,message}); if (nativeResponse instanceof Error) throw nativeResponse; return nativeResponse; },
      reload(){ reloadCount += 1; },
      onStartup:{addListener:fn=>listeners.startup.push(fn)}, onInstalled:{addListener:fn=>listeners.installed.push(fn)}, onMessage:{addListener:fn=>listeners.message.push(fn)}
    }
  };
  const sandbox = { chrome, console, Date, Promise, setTimeout, clearTimeout };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(__dirname + '/dev-updater.js','utf8'), sandbox);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert(alarms.some(entry => entry.name === 'arl-dev-auto-update' && entry.options.periodInMinutes === 15), 'worker startup must recreate a 15-minute update alarm');
  assert(nativeCalls.some(call => call.message.reason === 'worker-start'), 'worker startup must perform an immediate updater check');

  nativeResponse = { protocol:'arl-dev-updater-v1', ok:true, updated:true, status:'updated', latestVersion:'0.18.3', installedVersion:'0.18.3' };
  const updated = await sandbox.initializeDevUpdater('manual-test', true);
  assert(updated.ok === true && updated.updated === true, 'strictly newer verified native install must be accepted');
  assert(reloadCount === 1, 'successful install must request reload synchronously exactly once');
  assert(nativeCalls.at(-1).host === 'com.supremefabworks.amazon_order_manager_updater', 'native updater host name must remain fixed');

  nativeResponse = new Error('Specified native messaging host not found.');
  const missing = await sandbox.initializeDevUpdater('missing-host-test', true);
  assert(missing.ok === false && missing.hostAvailable === false, 'missing native host must fail closed and expose host availability');
  assert(storedStatus && storedStatus.error, 'native host failure must persist an updater diagnostic');
  assert(statusWrites.length >= 3, 'updater must persist check/install/error status');
  console.log('development auto-update tests passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
write('dev-updater-test.js', up_test)

up_rel = r'''const fs = require('fs');
function assert(condition, message) { if (!condition) throw new Error(message); }
const updater = fs.readFileSync(__dirname + '/dev-updater.js','utf8');
const popup = fs.readFileSync(__dirname + '/popup.html','utf8') + fs.readFileSync(__dirname + '/popup.js','utf8');
const host = fs.readFileSync(__dirname + '/tools/dev-updater/NativeHost.cs','utf8');
const installer = fs.readFileSync(__dirname + '/tools/dev-updater/Install.ps1','utf8');
assert(updater.includes("initializeDevUpdater('worker-start')"), 'updater must check whenever the MV3 worker starts');
assert(updater.includes('persistAcrossSessions'), 'updater must request alarm persistence where supported');
assert(!updater.includes("setTimeout(() => {\n      try { chrome.runtime.reload()"), 'verified update reload must not depend on a service-worker timer');
assert(popup.includes('Check development update now') && popup.includes('ARL_CHECK_DEV_UPDATE'), 'popup must expose a manual update check');
assert(popup.includes('ARL_GET_DEV_UPDATE_STATUS'), 'popup must expose persisted updater status');
assert(host.includes('updater.log') && host.includes('--self-test'), 'native host must provide file logging and a local self-test');
assert(installer.includes('DiagnoseOnly') && installer.includes('Show-Diagnostics'), 'installer must expose a diagnostics-only mode');
console.log('updater reliability tests passed');
'''
write('updater-reliability-test.js', up_rel)

print('v0.18.2 patch applied')
