from pathlib import Path
import json

ROOT = Path('.')

def read(path): return (ROOT / path).read_text(encoding='utf-8')
def write(path, text): (ROOT / path).write_text(text, encoding='utf-8')
def once(text, old, new, label):
    n = text.count(old)
    if n != 1: raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

def replace_function(text, name, next_name, replacement):
    start = text.index(f'  function {name}(')
    end = text.index(f'\n\n  function {next_name}(', start)
    return text[:start] + replacement.rstrip() + text[end:]

# ---------- parser.js: evidence-safe milestones + canonical Order Details line items ----------
p = read('parser.js')

milestones = r'''  function parseReturnMilestones(text) {
    const normalized = normalizeText(text);
    const lines = normalized.split('\n').map(line => line.trim()).filter(Boolean);

    // A return-status page contains static labels for every future step. Completion therefore
    // requires affirmative event language (or a DOM checkmark applied later), never the label alone.
    const credited = lines.some(line => /(?:your refund (?:has been|was) credited|we (?:have )?credited your refund|refund (?:has been|was) credited to|credited to your (?:original )?payment method on)/i.test(line));
    const refundIssuedDirect = lines.some(line => /(?:we (?:have )?issued your refund|your refund (?:has been|was) issued|refund has been issued|refund issued\s+(?:on|\$))/i.test(line));
    const refundIssued = credited || refundIssuedDirect;

    const receivedDirect = lines.some(line =>
      /(?:we (?:have )?received your return|your return (?:has been|was) received|received your return|item (?:has been|was) received|return processed|your return is complete|return (?:has been|was) completed|return received\s+(?:on|at)\b)/i.test(line)
    );
    const received = refundIssued || receivedDirect;

    const shippedDirect = lines.some(line => {
      if (/(?:drop off your return by|drop-off your return by|please drop off|once you drop off|when you drop off|time you have dropped off|after you drop off|before you drop off)/i.test(line)) return false;
      return /(?:your return (?:has been|was) dropped off|you (?:have )?dropped off your return|drop-?off complete|return (?:is|has been) in transit|on the way back|return (?:has been|was) shipped|shipped back|carrier (?:has )?received (?:your )?return|dropped off\s+(?:on|at)\b)/i.test(line);
    });
    const shipped = received || shippedDirect;

    const started = shipped || lines.some(line =>
      /(?:return request (?:is )?(?:confirmed|accepted)|return initiated|return started|accepted your return|drop off your return by|drop-off your return by|return code|return summary|refund will be issued|estimated refund|refund method|refund subtotal|^initiated$)/i.test(line)
    );

    const stage = credited ? 'credited' : refundIssued ? 'refund_issued' : received ? 'received' : shipped ? 'shipped' : started ? 'started' : 'unknown';
    const expectedCreditDate = credited ? null : findExpectedCreditDate(normalized);

    return {
      stage,
      expectedCreditDate,
      started: { done: started, date: started ? findMilestoneDate(normalized, ['Initiated', 'Return initiated', 'Return started']) : null },
      shipped: { done: shipped, date: shipped ? findMilestoneDate(normalized, ['Dropped off', 'Drop off', 'Return shipped', 'Shipped']) : null },
      refundIssued: { done: refundIssued, date: refundIssued ? findMilestoneDate(normalized, ['Refund issued']) : null },
      credited: { done: credited, date: credited ? findMilestoneDate(normalized, ['Refund credited', 'Credited']) : null }
    };
  }

  function extractCompletedReturnMilestonesFromDom(container) {
    const done = { started: false, shipped: false, received: false, refundIssued: false, credited: false };
    if (!container?.querySelectorAll) return done;
    let checks = [];
    try {
      checks = Array.from(container.querySelectorAll('img[src*="milestone_checkmark" i], img[data-src*="milestone_checkmark" i], img[alt*="checkmark" i]'));
    } catch (_) {}
    const stageForLabel = line => {
      const value = normalizeText(line).toLowerCase();
      if (value === 'initiated' || value === 'return initiated' || value === 'return started') return 'started';
      if (value === 'drop off' || value === 'dropped off' || value === 'return shipped') return 'shipped';
      if (value === 'return received') return 'received';
      if (value === 'refund issued') return 'refundIssued';
      if (value === 'refund credited' || value === 'credited') return 'credited';
      return null;
    };
    for (const check of checks) {
      let current = check.parentElement || null;
      for (let depth = 0; current && depth < 6; depth += 1, current = current.parentElement) {
        const text = normalizeText(current.innerText || current.textContent || '');
        if (!text || text.length > 700) continue;
        const labels = Array.from(new Set(text.split('\n').map(stageForLabel).filter(Boolean)));
        if (labels.length === 1) { done[labels[0]] = true; break; }
        if (labels.length > 1) break;
      }
    }
    // Later completed milestones imply the earlier physical steps.
    if (done.credited) done.refundIssued = true;
    if (done.refundIssued) done.received = true;
    if (done.received) done.shipped = true;
    if (done.shipped) done.started = true;
    return done;
  }

  function applyDomReturnMilestones(record, container) {
    if (!record || record.recordType !== 'return') return record;
    const dom = extractCompletedReturnMilestonesFromDom(container);
    if (!Object.values(dom).some(Boolean)) return record;
    const milestones = record.returnMilestones || parseReturnMilestones(record.statusText || '');
    for (const key of ['started', 'shipped', 'refundIssued', 'credited']) {
      const domKey = key;
      if (!dom[domKey]) continue;
      milestones[key] = { ...(milestones[key] || {}), done: true };
    }
    if (dom.received) milestones.receivedByDom = true;
    const stage = dom.credited ? 'credited' : dom.refundIssued ? 'refund_issued' : dom.received ? 'received' : dom.shipped ? 'shipped' : dom.started ? 'started' : milestones.stage || 'unknown';
    const rank = { unknown:0, started:1, shipped:2, received:3, refund_issued:4, credited:5 };
    if ((rank[stage] || 0) > (rank[milestones.stage] || 0)) milestones.stage = stage;
    record.returnMilestones = milestones;
    record.returnStage = milestones.stage;
    if ((rank[record.returnStage] || 0) >= 4) record.status = 'refunded';
    else if (record.returnStage === 'received') record.status = 'returned_pending_refund';
    else if ((rank[record.returnStage] || 0) >= 1) record.status = 'return_in_progress';
    return record;
  }'''
p = replace_function(p, 'parseReturnMilestones', 'classifyStatus', milestones)

status_text = r'''  function extractStatusText(text) {
    const normalized = normalizeText(text);
    const lines = normalized.split('\n').map(s => s.trim()).filter(Boolean);
    if (!lines.length) return null;

    const stage = parseReturnMilestones(normalized).stage;
    const stagePatterns = {
      credited: [/(?:your refund (?:has been|was) credited|we (?:have )?credited your refund|refund (?:has been|was) credited to|credited to your (?:original )?payment method on)/i],
      refund_issued: [/(?:we (?:have )?issued your refund|your refund (?:has been|was) issued|refund has been issued|refund issued\s+(?:on|\$))/i],
      received: [/(?:we (?:have )?received your return|your return (?:has been|was) received|received your return|item (?:has been|was) received|return processed|your return is complete|return (?:has been|was) completed|return received\s+(?:on|at)\b)/i],
      shipped: [/(?:your return (?:has been|was) dropped off|you (?:have )?dropped off your return|drop-?off complete|return (?:is|has been) in transit|on the way back|return (?:has been|was) shipped|shipped back|carrier (?:has )?received (?:your )?return|dropped off\s+(?:on|at)\b)/i],
      started: [/(?:return request (?:is )?(?:confirmed|accepted)|return initiated|return started|accepted your return|drop off your return by|return code|return summary|refund will be issued|estimated refund)/i]
    };

    for (const pattern of stagePatterns[stage] || []) {
      const line = lines.find(candidate => pattern.test(candidate));
      if (line) return line.slice(0, 500);
    }

    for (const line of lines) {
      if (/^(?:refund issued|refund credited|return received|drop off|dropped off|credited|initiated|credit pending)$/i.test(line)) continue;
      if (/(?:delivered|arriving|shipped)/i.test(line) && !/(?:refund issued|refund credited)/i.test(line)) return line.slice(0, 500);
    }
    return null;
  }'''
p = replace_function(p, 'extractStatusText', 'inferPageType', status_text)

strong = r'''  function strongReturnEvidence(text) {
    const t = normalizeText(text).toLowerCase();
    if (!t) return false;
    if (/return or replace items?|start a return|eligible for return/.test(t) && !/check return\s*(?:&|and)\s*refund status/.test(t)) return false;
    return parseReturnMilestones(text).stage !== 'unknown' || /check return\s*(?:&|and)\s*refund status/.test(t);
  }'''
p = replace_function(p, 'strongReturnEvidence', 'parseDocument', strong)

insert_anchor = '''  function extractAsins(container) {
'''
# Insert new order line-item helpers immediately before extractReturnItemEntries, after extractAsins closes.
marker = '\n\n\n  function extractReturnItemEntries(container) {'
if marker not in p: raise RuntimeError('order line item insertion marker missing')
order_items = r'''

  function productAnchorInfo(anchor) {
    if (!anchor) return null;
    const href = String(anchor.getAttribute?.('href') || anchor.href || '');
    const asin = href.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})(?:[/?#]|$)/i)?.[1]?.toUpperCase() || '';
    if (!asin || excludedProductAnchor(anchor)) return null;
    let itemName = normalizeText(anchor.innerText || anchor.textContent || anchor.getAttribute?.('aria-label') || anchor.getAttribute?.('title') || '');
    if (!itemName || itemName.length < 3) {
      const img = anchor.querySelector?.('img') || anchor.parentElement?.querySelector?.('img');
      itemName = normalizeText(img?.getAttribute?.('alt') || img?.alt || '');
    }
    if (!itemName || itemName.length < 3 || itemName.length > 500) return null;
    if (/buy it again|view order|order details|track package|return or replace|write a product review|invoice|amazon business card|prime business/i.test(itemName)) return null;
    return { asin, itemName: itemName.slice(0, 400) };
  }

  function singleProductContainerForAnchor(anchor, asin) {
    let current = anchor?.parentElement || anchor || null;
    let best = current;
    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
      const text = normalizeText(current.innerText || current.textContent || '');
      if (text.length > 6500) break;
      let links = [];
      try { links = Array.from(current.querySelectorAll?.('a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/product/"]') || []); } catch (_) {}
      const asins = new Set(links.map(a => productAnchorInfo(a)?.asin).filter(Boolean));
      if (!asins.size || (asins.size === 1 && asins.has(asin))) best = current;
      if (asins.size > 1) break;
    }
    return best;
  }

  function extractDirectItemQuantity(text) {
    const normalized = normalizeText(text);
    const match = normalized.match(/(?:^|\n)\s*(?:Quantity|Qty)\s*[:x]?\s*(\d+)\s*(?:$|\n)/im);
    if (!match) return null;
    const value = Number(match[1]);
    return Number.isInteger(value) && value > 0 ? value : null;
  }

  function extractDirectItemAmount(container, text) {
    const labeled = findLabeledMoney(text, ['Item subtotal', 'Item price']);
    if (labeled != null) return labeled;
    if (!container?.querySelectorAll) return null;
    const values = [];
    for (const selector of ['.a-price .a-offscreen', '[class*="item-price" i]', '[data-testid*="item-price" i]']) {
      let nodes = [];
      try { nodes = Array.from(container.querySelectorAll(selector)); } catch (_) {}
      for (const node of nodes) {
        const value = parseMoney(node.innerText || node.textContent || '');
        if (value != null && Number.isFinite(Number(value))) values.push(Number(value));
      }
    }
    const unique = Array.from(new Set(values.map(value => value.toFixed(2))));
    return unique.length === 1 ? Number(unique[0]) : null;
  }

  function extractDirectFulfillmentStatus(text) {
    const lines = normalizeText(text).split('\n').map(line => line.trim()).filter(Boolean);
    for (const line of lines) {
      if (/return|refund|drop off/i.test(line)) continue;
      if (/^(?:Delivered|Arriving|Shipped|Out for delivery|Preparing for shipment|Not yet shipped|Cancelled|Canceled)\b/i.test(line)) return line.slice(0, 180);
    }
    return null;
  }

  function extractOrderLineItems(container) {
    if (!container?.querySelectorAll) return [];
    let anchors = [];
    try { anchors = Array.from(container.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/product/"]')); } catch (_) {}
    const byAsin = new Map();
    for (const anchor of anchors) {
      const info = productAnchorInfo(anchor);
      if (!info) continue;
      const itemContainer = singleProductContainerForAnchor(anchor, info.asin);
      const text = normalizeText(itemContainer?.innerText || itemContainer?.textContent || '');
      const candidate = {
        itemKey: `asin:${info.asin}`,
        asin: info.asin,
        itemName: info.itemName,
        quantity: extractDirectItemQuantity(text),
        itemAmount: extractDirectItemAmount(itemContainer, text),
        fulfillmentStatus: extractDirectFulfillmentStatus(text),
        source: 'order-details-product-anchor'
      };
      const existing = byAsin.get(info.asin);
      if (!existing) byAsin.set(info.asin, candidate);
      else byAsin.set(info.asin, {
        ...existing,
        itemName: existing.itemName || candidate.itemName,
        quantity: existing.quantity ?? candidate.quantity,
        itemAmount: existing.itemAmount ?? candidate.itemAmount,
        fulfillmentStatus: existing.fulfillmentStatus || candidate.fulfillmentStatus
      });
    }
    return Array.from(byAsin.values()).slice(0, 60);
  }
'''
p = p.replace(marker, order_items + marker, 1)

# Apply DOM milestone checkmarks after base return parsing, and structured purchased items on details.
p = once(p,
'''      if (domNames.length) record.itemNames = domNames;
      record.asins = asins;

      if (historyPage && record.recordType === 'order' && !detailByOrder.get(orderId)) {''',
'''      if (domNames.length) record.itemNames = domNames;
      record.asins = asins;
      if (pageType === 'return') applyDomReturnMilestones(record, container || doc?.body);

      if (historyPage && record.recordType === 'order' && !detailByOrder.get(orderId)) {''',
'apply DOM return milestone evidence')

p = once(p,
'''      if (detailPage && record.recordType === 'order') {
        record.detailScanComplete = isCompleteCanonicalDetail(record, url);''',
'''      if (detailPage && record.recordType === 'order') {
        const orderItems = extractOrderLineItems(container || doc?.body);
        if (orderItems.length) {
          record.orderItems = orderItems;
          record.itemNames = orderItems.map(item => item.itemName).filter(Boolean);
          record.asins = orderItems.map(item => item.asin).filter(Boolean);
        }
        record.detailScanComplete = isCompleteCanonicalDetail(record, url);''',
'canonical Order Details structured items')

p = once(p,
'''    extractPaymentEvidenceText,
    extractReturnItemEntries,''',
'''    extractPaymentEvidenceText,
    extractCompletedReturnMilestonesFromDom,
    applyDomReturnMilestones,
    extractOrderLineItems,
    extractReturnItemEntries,''',
'export v0.18.7 parser helpers')
write('parser.js', p)

# ---------- storage.js: strict fallback stage text + object-safe orderItems persistence ----------
s = read('storage.js')
insert = '''  function mergeArray(existing, incoming) {
'''
# Add order-item normalizer after mergeArray function before stageFromText.
marker = '\n\n  function stageFromText(text) {'
if marker not in s: raise RuntimeError('storage stage marker missing')
order_item_merge = r'''

  function normalizeOrderItems(items) {
    const out = [];
    const seen = new Set();
    for (const raw of items || []) {
      if (!raw || typeof raw !== 'object') continue;
      const asin = String(raw.asin || '').trim().toUpperCase();
      const itemName = String(raw.itemName || '').trim();
      const itemKey = String(raw.itemKey || (asin ? `asin:${asin}` : '')).trim();
      if (!itemKey || !itemName || seen.has(itemKey.toLowerCase())) continue;
      seen.add(itemKey.toLowerCase());
      const quantity = raw.quantity === null || raw.quantity === undefined || raw.quantity === '' ? null : Number(raw.quantity);
      const itemAmount = raw.itemAmount === null || raw.itemAmount === undefined || raw.itemAmount === '' ? null : Number(raw.itemAmount);
      out.push({
        itemKey,
        asin: /^[A-Z0-9]{10}$/.test(asin) ? asin : null,
        itemName: itemName.slice(0, 400),
        quantity: Number.isInteger(quantity) && quantity > 0 ? quantity : null,
        itemAmount: Number.isFinite(itemAmount) ? itemAmount : null,
        fulfillmentStatus: raw.fulfillmentStatus ? String(raw.fulfillmentStatus).slice(0, 180) : null,
        source: raw.source ? String(raw.source).slice(0, 80) : null
      });
    }
    return out;
  }
'''
s = s.replace(marker, order_item_merge + marker, 1)

stage = r'''  function stageFromText(text) {
    const lines = String(text || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (lines.some(line => /(?:your refund (?:has been|was) credited|we (?:have )?credited your refund|refund (?:has been|was) credited to)/i.test(line))) return 'credited';
    if (lines.some(line => /(?:we (?:have )?issued your refund|your refund (?:has been|was) issued|refund has been issued|refund issued\s+(?:on|\$))/i.test(line))) return 'refund_issued';
    if (lines.some(line => /(?:we (?:have )?received your return|your return (?:has been|was) received|received your return|item (?:has been|was) received|return processed|your return is complete|return received\s+(?:on|at)\b)/i.test(line))) return 'received';
    if (lines.some(line => {
      if (/(?:drop off your return by|please drop off|once you drop off|when you drop off|time you have dropped off|after you drop off)/i.test(line)) return false;
      return /(?:your return (?:has been|was) dropped off|you (?:have )?dropped off your return|drop-?off complete|return (?:is|has been) in transit|on the way back|return (?:has been|was) shipped|shipped back|carrier (?:has )?received (?:your )?return|dropped off\s+(?:on|at)\b)/i.test(line);
    })) return 'shipped';
    if (lines.some(line => /(?:return request|accepted your return|drop off your return by|dropoff by|return code|refund will be issued|estimated refund|refund method|refund subtotal|return status link detected|^initiated$)/i.test(line))) return 'started';
    return 'unknown';
  }'''
s = replace_function(s, 'stageFromText', 'getReturnStage', stage)

s = once(s,
'''      if (Array.isArray(value)) {
        if ((key === 'itemNames' && trustedIdentity.preserveNames) || (key === 'asins' && trustedIdentity.preserveAsins)) {''',
'''      if (key === 'orderItems' && Array.isArray(value)) {
        const normalizedItems = normalizeOrderItems(value);
        if (incoming?.recordType === 'order' && incoming?.detailScanComplete && normalizedItems.length) merged[key] = normalizedItems;
        else if (!Array.isArray(existing?.orderItems) || !existing.orderItems.length) merged[key] = normalizedItems;
      }
      else if (Array.isArray(value)) {
        if ((key === 'itemNames' && trustedIdentity.preserveNames) || (key === 'asins' && trustedIdentity.preserveAsins)) {''',
'object-safe orderItems merge')

s = once(s,
'''      if (Array.isArray(value)) out[key] = [...value].map(v => String(v)).sort();
      else out[key] = value ?? null;''',
'''      if (key === 'orderItems' && Array.isArray(value)) out[key] = normalizeOrderItems(value).slice().sort((a,b) => a.itemKey.localeCompare(b.itemKey));
      else if (Array.isArray(value)) out[key] = [...value].map(v => String(v)).sort();
      else out[key] = value ?? null;''',
'comparable structured orderItems')
write('storage.js', s)

# ---------- pure item join model ----------
item_model = r'''(() => {
  'use strict';

  function clean(value) { return String(value || '').trim(); }
  function normalizeTitle(value) {
    return clean(value)
      .replace(/\d{3}-\d{7}-\d{7}/g, ' ')
      .replace(/[.…]+/g, ' ')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }
  function uniqueStrings(values) {
    const out = []; const seen = new Set();
    for (const value of values || []) {
      const s = clean(value); if (!s) continue;
      const key = s.toLowerCase(); if (seen.has(key)) continue;
      seen.add(key); out.push(s);
    }
    return out;
  }
  function normalizeOrderItems(order) {
    const structured = Array.isArray(order?.orderItems) ? order.orderItems.filter(Boolean) : [];
    if (structured.length) return structured.map((item, index) => ({
      itemKey: clean(item.itemKey) || (item.asin ? `asin:${clean(item.asin).toUpperCase()}` : `item:${index}`),
      asin: clean(item.asin).toUpperCase() || null,
      itemName: clean(item.itemName) || `Order item ${index + 1}`,
      quantity: Number.isInteger(Number(item.quantity)) && Number(item.quantity) > 0 ? Number(item.quantity) : null,
      itemAmount: item.itemAmount === null || item.itemAmount === undefined || item.itemAmount === '' || !Number.isFinite(Number(item.itemAmount)) ? null : Number(item.itemAmount),
      fulfillmentStatus: clean(item.fulfillmentStatus) || null,
      source: clean(item.source) || null
    }));

    const names = uniqueStrings(order?.itemNames || []);
    const asins = uniqueStrings(order?.asins || []).map(value => value.toUpperCase());
    const alignAsins = asins.length === names.length;
    return names.map((itemName, index) => ({
      itemKey: alignAsins && asins[index] ? `asin:${asins[index]}` : `title:${normalizeTitle(itemName).slice(0, 100)}`,
      asin: alignAsins ? (asins[index] || null) : null,
      itemName,
      quantity: null,
      itemAmount: null,
      fulfillmentStatus: null,
      source: 'legacy-order-item'
    }));
  }

  function identityEvidence(group) {
    return {
      asins: new Set(uniqueStrings(group?.asins || []).map(value => value.toUpperCase())),
      titles: uniqueStrings(group?.itemNames || []).map(normalizeTitle).filter(Boolean)
    };
  }

  function itemMatchScore(item, group) {
    const evidence = identityEvidence(group);
    const asin = clean(item?.asin).toUpperCase();
    if (asin && evidence.asins.has(asin)) return 100;
    const title = normalizeTitle(item?.itemName);
    if (!title) return 0;
    let best = 0;
    for (const returnedTitle of evidence.titles) {
      if (!returnedTitle) continue;
      if (title === returnedTitle) best = Math.max(best, 80);
      else {
        const shorter = title.length <= returnedTitle.length ? title : returnedTitle;
        const longer = title.length > returnedTitle.length ? title : returnedTitle;
        if (shorter.length >= 24 && shorter.split(' ').length >= 4 && longer.startsWith(shorter)) best = Math.max(best, 70);
      }
    }
    return best;
  }

  function joinOrderItems(order, returnGroups) {
    const items = normalizeOrderItems(order).map(item => ({ ...item, returnGroups: [] }));
    const unmatchedReturnGroups = [];
    for (const group of returnGroups || []) {
      const scores = items.map((item, index) => ({ index, score: itemMatchScore(item, group) })).sort((a,b) => b.score - a.score);
      const best = scores[0] || { index: -1, score: 0 };
      const tied = best.score > 0 && scores.filter(entry => entry.score === best.score).length > 1;
      if (best.score >= 70 && !tied && items[best.index]) {
        items[best.index].returnGroups.push(group);
      } else {
        const evidence = identityEvidence(group);
        unmatchedReturnGroups.push({ group, identityStrength: evidence.asins.size ? 'strong' : 'weak', bestScore: best.score });
      }
    }
    return {
      items,
      unmatchedReturnGroups,
      returnedProductCount: items.filter(item => item.returnGroups.length).length
    };
  }

  window.AmazonOrderItemModel = { normalizeTitle, normalizeOrderItems, itemMatchScore, joinOrderItems };
})();
'''
write('item-model.js', item_model)

# ---------- dashboard.js: order-centric product rows ----------
d = read('dashboard.js')
d = once(d,
'''  const storage = window.AmazonRefundStorage;
  const body = document.getElementById('ledgerBody');''',
'''  const storage = window.AmazonRefundStorage;
  const itemModel = window.AmazonOrderItemModel;
  const body = document.getElementById('ledgerBody');''',
'load item model')

d = once(d,
'''      const returnGroups = groupReturnRecords(returnRecords);
      const manualReconciled = returnRecords.some(r => r.manualState === 'reconciled');''',
'''      const returnGroups = groupReturnRecords(returnRecords);
      const itemJoin = itemModel?.joinOrderItems(order, returnGroups) || { items: [], unmatchedReturnGroups: returnGroups.map(group => ({ group, identityStrength: 'weak', bestScore: 0 })), returnedProductCount: 0 };
      const strongUnmatchedReturnIdentity = itemJoin.unmatchedReturnGroups.some(entry => entry.identityStrength === 'strong');
      const manualReconciled = returnRecords.some(r => r.manualState === 'reconciled');''',
'join return groups to purchased items')

d = once(d,
'''      const orderItemNames = uniqueStrings(order?.itemNames || []);
      const returnedItemNames = uniqueStrings(returnGroups.flatMap(group => group.itemNames || []));''',
'''      const capturedOrderItemNames = uniqueStrings(order?.itemNames || []);
      const structuredOrderItemNames = uniqueStrings(itemJoin.items.map(item => item.itemName));
      const orderItemNames = structuredOrderItemNames.length ? structuredOrderItemNames : capturedOrderItemNames;
      const returnedItemNames = uniqueStrings(returnGroups.flatMap(group => group.itemNames || []));''',
'prefer structured purchased items')

d = once(d,
'''        returnRecords.some(r => storage.needsCreditReview(r)) || refundAmountMismatch || itemIdentityConflict || groupAmountConflict
      );''',
'''        returnRecords.some(r => storage.needsCreditReview(r)) || refundAmountMismatch || itemIdentityConflict || groupAmountConflict || strongUnmatchedReturnIdentity
      );''',
'flag strong unmatched return identity')

d = once(d,
'''        else if (groupAmountConflict) statusLabel = 'Return refund needs review';
        else {''',
'''        else if (groupAmountConflict) statusLabel = 'Return refund needs review';
        else if (strongUnmatchedReturnIdentity) statusLabel = 'Returned item needs matching';
        else {''',
'unmatched return review label')

d = once(d,
'''      const itemNames = hasReturn ? returnedItemNames : orderItemNames;
      rows.push({
        orderId, order, returns: returnRecords, returnGroups, hasReturn, needsReview, terminalCancelled, stateKey, statusLabel,
        itemNames, orderItemNames, returnedItemNames, searchItemNames: uniqueStrings([...orderItemNames, ...returnedItemNames]),''',
'''      const itemNames = orderItemNames.length ? orderItemNames : returnedItemNames;
      rows.push({
        orderId, order, returns: returnRecords, returnGroups, hasReturn, needsReview, terminalCancelled, stateKey, statusLabel,
        itemStates: itemJoin.items, unmatchedReturnGroups: itemJoin.unmatchedReturnGroups, returnedProductCount: itemJoin.returnedProductCount,
        itemNames, orderItemNames, returnedItemNames, searchItemNames: uniqueStrings([...orderItemNames, ...returnedItemNames]),''',
'persist product states in dashboard row')

# Replace returnProgressMarkup with legacy+product-aware render helpers.
old = '''  function returnProgressMarkup(row) {
    if (!row.returnGroups.length) return '<span class="muted">—</span>';
    return `<div class="return-track-stack compact-return-stack">${row.returnGroups.map((group, index) => lifecycleMarkup(group, index + 1, row.returnGroups.length)).join('')}</div>`;
  }
'''
new = r'''  function legacyReturnProgressMarkup(row) {
    if (!row.returnGroups.length) return '<span class="muted">—</span>';
    return `<div class="return-track-stack compact-return-stack">${row.returnGroups.map((group, index) => lifecycleMarkup(group, index + 1, row.returnGroups.length)).join('')}</div>`;
  }

  function orderProductStatusMarkup(row) {
    if (!row.itemStates?.length) return row.hasReturn ? legacyReturnProgressMarkup(row) : `<span class="muted tiny">${esc(row.statusLabel || 'Order')}</span>`;
    const products = row.itemStates.map((item, index) => {
      const groups = item.returnGroups || [];
      const representatives = groups.map(group => group.representative).filter(Boolean);
      const highest = representatives.slice().sort((a,b) => storage.returnStageRank(b) - storage.returnStageRank(a))[0] || null;
      const returnLabel = groups.length ? `${groups.length > 1 ? `${groups.length} returns · ` : ''}${stageLabel(storage.getReturnStage(highest))}` : 'Not returned';
      const meta = [
        item.quantity != null ? `Qty ${item.quantity}` : '',
        item.itemAmount != null ? money(item.itemAmount) : '',
        item.asin || '',
        item.fulfillmentStatus || ''
      ].filter(Boolean).join(' · ');
      return `<div class="order-product-row ${groups.length ? 'has-product-return' : ''}">
        <div class="order-product-head">
          <div><span class="order-product-index">${index + 1}</span><strong title="${esc(item.itemName)}">${esc(item.itemName)}</strong></div>
          <span class="product-state ${groups.length ? 'product-returned' : 'product-not-returned'}">${esc(returnLabel)}</span>
        </div>
        ${meta ? `<div class="muted tiny order-product-meta">${esc(meta)}</div>` : ''}
        ${groups.length ? `<div class="product-return-lifecycles">${groups.map((group, returnIndex) => lifecycleMarkup(group, returnIndex + 1, groups.length)).join('')}</div>` : ''}
      </div>`;
    }).join('');
    const unmatched = (row.unmatchedReturnGroups || []).map((entry, index) => {
      const group = entry.group;
      const title = group?.itemNames?.length ? group.itemNames.join(' · ') : 'Returned item with no purchased-item match';
      return `<div class="order-product-row unmatched-product-return"><div class="order-product-head"><div><span class="order-product-index">!</span><strong>${esc(title)}</strong></div><span class="product-state product-unmatched">Unmatched return</span></div>${lifecycleMarkup(group, index + 1, row.unmatchedReturnGroups.length)}</div>`;
    }).join('');
    return `<div class="order-product-stack">${products}${unmatched}</div>`;
  }
'''
d = once(d, old, new, 'product-aware progress renderer')

# Render summary and product state stack.
d = once(d,
'''      const items = row.itemNames.length ? row.itemNames.join(' · ') : (row.hasReturn ? `${row.returnGroups.length} return${row.returnGroups.length === 1 ? '' : 's'} pending item identity` : 'Item title pending Order Details scan');''',
'''      const fullItemTitle = row.itemNames.length ? row.itemNames.join(' · ') : '';
      const items = row.itemStates?.length > 1
        ? `${row.itemStates.length} products · ${row.returnedProductCount || 0} returned`
        : (fullItemTitle || (row.hasReturn ? `${row.returnGroups.length} return${row.returnGroups.length === 1 ? '' : 's'} pending item identity` : 'Item title pending Order Details scan'));''',
'compact multi-product order summary')

d = once(d,
'''          <div class="item-title line-item-title" title="${esc(items)}">${esc(items)}</div>''',
'''          <div class="item-title line-item-title" title="${esc(fullItemTitle || items)}">${esc(items)}</div>''',
'top title retains full product tooltip')

d = once(d,
'''        <div class="line-progress">
          ${row.hasReturn ? `${returnProgressMarkup(row)}${financialState}` : `<span class="muted tiny">${esc(row.statusLabel || 'Order')}</span>`}
        </div>''',
'''        <div class="line-progress">
          ${`${orderProductStatusMarkup(row)}${financialState}`}
        </div>''',
'render all product statuses')

# CSV item-level detail.
d = once(d,
'''    const headers = ['status','order_id','items','order_total','expected_refund','card_last4','amazon_status','detail_complete','order_details_url','last_scanned_at'];
    const lines = [headers.map(csvCell).join(',')];
    for (const row of buildRows()) lines.push([row.statusLabel,row.orderId,row.itemNames.join(' | '),row.orderTotal ?? '',row.refundAmount ?? '',row.cardLast4 || '',row.amazonStatus,row.detailComplete,row.openUrl,row.lastScannedAt || ''].map(csvCell).join(','));''',
'''    const headers = ['status','order_id','product_count','returned_product_count','items','product_statuses','order_total','expected_refund','card_last4','amazon_status','detail_complete','order_details_url','last_scanned_at'];
    const lines = [headers.map(csvCell).join(',')];
    for (const row of buildRows()) {
      const productStatuses = (row.itemStates || []).map(item => `${item.itemName} => ${(item.returnGroups || []).length ? stageLabel(storage.getReturnStage(item.returnGroups[0]?.representative)) : 'Not returned'}`).join(' | ');
      lines.push([row.statusLabel,row.orderId,row.itemStates?.length || row.itemNames.length,row.returnedProductCount || 0,row.itemNames.join(' | '),productStatuses,row.orderTotal ?? '',row.refundAmount ?? '',row.cardLast4 || '',row.amazonStatus,row.detailComplete,row.openUrl,row.lastScannedAt || ''].map(csvCell).join(','));
    }''',
'CSV product status detail')
write('dashboard.js', d)

# dashboard loads pure item model.
h = read('dashboard.html')
h = once(h,
'''  <script src="storage.js"></script>
  <script src="dashboard.js"></script>''',
'''  <script src="storage.js"></script>
  <script src="item-model.js"></script>
  <script src="dashboard.js"></script>''',
'load item model before dashboard')
write('dashboard.html', h)

# ---------- background.js: ~30% shorter serial pacing, same safety gates ----------
b = read('background.js')
replacements = {
    'const JOB_DELAY_MIN_MS = 250;': 'const JOB_DELAY_MIN_MS = 175;',
    'const JOB_DELAY_MAX_MS = 650;': 'const JOB_DELAY_MAX_MS = 455;',
    'const LOAD_SETTLE_MIN_MS = 650;': 'const LOAD_SETTLE_MIN_MS = 450;',
    'const LOAD_SETTLE_MAX_MS = 1300;': 'const LOAD_SETTLE_MAX_MS = 900;',
    'pollTimer = setTimeout(inspect, 220);': 'pollTimer = setTimeout(inspect, 155);',
    'await delay(randomBetween(350, 700));': 'await delay(randomBetween(245, 490));',
    'await delay(randomBetween(550, 1150));': 'await delay(randomBetween(385, 805));',
    'await delay(randomBetween(700, 1500));': 'await delay(randomBetween(490, 1050));',
    'await delay(randomBetween(450, 900));': 'await delay(randomBetween(315, 630));',
    'await delay(randomBetween(150, 350));': 'await delay(randomBetween(105, 245));'
}
for old, newv in replacements.items():
    if old not in b: raise RuntimeError(f'background pacing anchor missing: {old}')
    b = b.replace(old, newv)
write('background.js', b)

# ---------- CSS ----------
css = read('ui.css')
css += r'''

/* v0.18.7 per-product order status */
.order-product-stack { display:grid; gap:5px; min-width:0; }
.order-product-row { min-width:0; padding:5px 6px; border:1px solid #e6e9ec; border-radius:7px; background:#fbfcfd; }
.order-product-row.has-product-return { background:#fcfefe; border-color:#d9e9e9; }
.order-product-head { display:flex; align-items:flex-start; justify-content:space-between; gap:7px; min-width:0; }
.order-product-head > div { display:flex; align-items:flex-start; gap:5px; min-width:0; }
.order-product-head strong { min-width:0; font-size:8.5px; line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.order-product-index { flex:0 0 auto; display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px; border-radius:50%; background:#eef1f4; font-size:7px; font-weight:900; }
.product-state { flex:0 0 auto; padding:2px 5px; border-radius:999px; font-size:7px; font-weight:850; white-space:nowrap; }
.product-not-returned { background:#eef3fa; color:#345b89; }
.product-returned { background:#fff3d8; color:#765109; }
.product-unmatched { background:#fff0d8; color:#7e5300; }
.order-product-meta { margin:2px 0 0 20px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.product-return-lifecycles { margin-top:3px; padding-left:20px; }
.product-return-lifecycles .return-track-title { display:none; }
.unmatched-product-return { border-color:#d8b163; background:#fffaf0; }
@media (max-width: 1050px) {
  .order-product-head strong { white-space:normal; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
}
'''
write('ui.css', css)

# ---------- Tests ----------
t = read('parser-test.js')
t += r'''

// v0.18.7 live ThermoMaven: future instructions/static labels are not completed milestones.
const v0187ThermoMaven = `
Drop off your return by Sep 8
Location: Any UPS dropoff
We will issue your refund within 30 days from the time you have dropped off your return.
Note: Once issued, refunds typically become available in your account within 7 days.
Aug 31
Initiated
Drop off
Return received
Refund issued
Refund credited
`;
const v0187Thermo = p.parseTextRecord(v0187ThermoMaven, '111-1790078-4741015', { pageType: 'return', url: 'https://www.amazon.com/spr/returns/prep?orderId=111-1790078-4741015&rmaId=RMA-THERMO' });
assert(v0187Thermo.returnStage === 'started', 'future dropoff instructions/static labels must leave ThermoMaven at Initiated');
assert(v0187Thermo.returnMilestones.shipped.done === false, 'policy phrase about time you have dropped off must not complete Dropped off');
assert(v0187Thermo.returnMilestones.refundIssued.done === false, 'bare Refund issued timeline label must not complete refund issued');
assert(v0187Thermo.returnMilestones.credited.done === false, 'bare Refund credited timeline label must not complete credit');
const v0187ActualDropoff = p.parseTextRecord('Your return was dropped off and is on the way back to Amazon.', '111-1790078-4741015', { pageType: 'return' });
assert(v0187ActualDropoff.returnStage === 'shipped', 'affirmative completed dropoff language must still complete shipped stage');

function v0187ProductAnchor(asin, title) {
  return {
    href: `https://www.amazon.com/dp/${asin}`,
    innerText: title, textContent: title, parentElement: null,
    getAttribute(name) { if (name === 'href') return `/dp/${asin}`; if (name === 'title') return title; return null; },
    closest() { return null; }, querySelector() { return null; }
  };
}
function v0187ItemNode(text, anchor) {
  const node = {
    innerText: text, textContent: text, parentElement: null,
    querySelectorAll(selector) {
      if (selector.includes('a[href*="/dp/"]')) return [anchor];
      if (selector === '.a-price .a-offscreen' || selector.includes('item-price')) return [];
      return [];
    },
    querySelector() { return null; }
  };
  anchor.parentElement = node;
  return node;
}
const v0187Anchors = Array.from({length:6}, (_,i) => v0187ProductAnchor(`B00000010${i}`, `Purchased Product ${i + 1} Long Descriptive Title`));
const v0187Nodes = v0187Anchors.map((anchor,i) => v0187ItemNode(`Purchased Product ${i + 1} Long Descriptive Title\nQuantity: ${i === 0 ? 2 : 1}\n${i === 1 ? 'Item price $19.99\n' : ''}Delivered Sep ${i + 1}`, anchor));
const v0187OrderBody = {
  innerText: v0187Nodes.map(node => node.innerText).join('\n'), textContent: '', parentElement:null,
  querySelectorAll(selector) {
    if (selector.includes('a[href*="/dp/"]')) return v0187Anchors;
    return [];
  }
};
for (const node of v0187Nodes) node.parentElement = v0187OrderBody;
const v0187LineItems = p.extractOrderLineItems(v0187OrderBody);
assert(v0187LineItems.length === 6, 'canonical Order Details must capture all six purchased products');
assert(v0187LineItems[0].quantity === 2, 'explicit quantity must be captured');
assert(v0187LineItems[1].itemAmount === 19.99, 'direct labeled item price may be captured');
assert(v0187LineItems[2].itemAmount == null, 'item price must remain unknown when not directly proven');
assert(v0187LineItems.every(item => item.fulfillmentStatus && item.fulfillmentStatus.startsWith('Delivered')), 'per-product fulfillment status should remain item scoped');
console.log('v0.18.7 evidence and multi-product parser regressions passed');
'''
write('parser-test.js', t)

st = read('storage-test.js')
st = once(st,
'''    ...index, itemNames: ['Example Part'], purchaseAmount: 123.45, cardLast4: '3172',
    detailScanComplete: true, detailScannedAt: new Date().toISOString()''',
'''    ...index, itemNames: ['Example Part'], purchaseAmount: 123.45, cardLast4: '3172',
    orderItems: [{ itemKey:'asin:B000000777', asin:'B000000777', itemName:'Example Part', quantity:2, itemAmount:null, fulfillmentStatus:'Delivered Sep 1', source:'order-details-product-anchor' }],
    detailScanComplete: true, detailScannedAt: new Date().toISOString()''',
'storage structured order item fixture')
st = once(st,
'''  assert(ledger[0].purchaseAmount === 123.45, 'detail total should merge into order');''',
'''  assert(ledger[0].purchaseAmount === 123.45, 'detail total should merge into order');
  assert(Array.isArray(ledger[0].orderItems) && ledger[0].orderItems.length === 1, 'structured purchased items must survive storage merge as objects');
  assert(ledger[0].orderItems[0].quantity === 2 && ledger[0].orderItems[0].itemAmount == null, 'known quantity and unknown item money must remain distinct');''',
'storage orderItems assertions')
write('storage-test.js', st)

item_test = r'''const fs = require('fs');
const vm = require('vm');
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/item-model.js', 'utf8'), sandbox);
const model = sandbox.window.AmazonOrderItemModel;
function assert(condition, message) { if (!condition) throw new Error(message); }

const order = { orderItems: Array.from({length:6}, (_,i) => ({
  itemKey:`asin:B00000010${i}`, asin:`B00000010${i}`, itemName:`Purchased Product ${i+1} Long Descriptive Title`,
  quantity:1, itemAmount:null, fulfillmentStatus:'Delivered'
})) };
const groups = Array.from({length:4}, (_,i) => ({
  key:`return-${i}`, asins:[`B00000010${i}`], itemNames:[`Purchased Product ${i+1} Long Descriptive Title`], representative:{ returnStage:i < 2 ? 'started' : 'received' }, records:[]
}));
const joined = model.joinOrderItems(order, groups);
assert(joined.items.length === 6, 'six purchased products must remain six product rows');
assert(joined.returnedProductCount === 4, 'exactly four of six products should be associated with returns');
assert(joined.items.filter(item => item.returnGroups.length).length === 4, 'four item rows must carry return lifecycles');
assert(joined.items.filter(item => !item.returnGroups.length).length === 2, 'two purchased products must remain visible as not returned');
assert(joined.unmatchedReturnGroups.length === 0, 'strong ASIN matches should not create unmatched returns');

const truncated = model.joinOrderItems({ orderItems:[{itemKey:'asin:B000000500', asin:null, itemName:'ThermoMaven Sub-1G Smart Wireless Meat Thermometer with Standalone Base'}] }, [
  { key:'return-title', asins:[], itemNames:['ThermoMaven Sub-1G Smart Wireless Meat Thermometer with Standalone Ba…'], representative:{returnStage:'started'}, records:[] }
]);
assert(truncated.returnedProductCount === 1, 'conservative long-title prefix matching must handle Amazon truncation');

const unmatched = model.joinOrderItems(order, [{ key:'unknown', asins:['B999999999'], itemNames:['Different Product'], representative:{returnStage:'started'}, records:[] }]);
assert(unmatched.unmatchedReturnGroups.length === 1 && unmatched.unmatchedReturnGroups[0].identityStrength === 'strong', 'contradictory strong returned ASIN must stay visible as unmatched/reviewable');
console.log('item model tests passed');
'''
write('item-model-test.js', item_test)

bt = read('background-test.js')
bt += r'''

const backgroundSourceV0187 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(backgroundSourceV0187.includes('const JOB_DELAY_MIN_MS = 175;') && backgroundSourceV0187.includes('const JOB_DELAY_MAX_MS = 455;'), 'v0.18.7 normal inter-job pacing should be about 30% faster');
assert(backgroundSourceV0187.includes('const LOAD_SETTLE_MIN_MS = 450;') && backgroundSourceV0187.includes('const LOAD_SETTLE_MAX_MS = 900;'), 'v0.18.7 page settle pacing should be about 30% faster');
assert(backgroundSourceV0187.includes('RATE_LIMIT_COOLDOWN_MIN_MS = 10 * 60 * 1000') && backgroundSourceV0187.includes('RATE_LIMIT_COOLDOWN_MAX_MS = 20 * 60 * 1000'), 'rate-limit cooldown safety must remain unchanged');
console.log('v0.18.7 pacing regression passed');
'''
write('background-test.js', bt)

ui = read('ui-test.js')
ui += r'''

assert(fs.readFileSync(__dirname + '/dashboard.html', 'utf8').includes('item-model.js'), 'dashboard must load the pure per-product item model');
assert(dashboard.includes('orderProductStatusMarkup'), 'dashboard must render purchased products independently inside each order');
assert(dashboard.includes("'Not returned'"), 'non-returned purchased products must stay visible with Not returned state');
assert(dashboard.includes('returnedProductCount'), 'order summary must expose how many purchased products were returned');
assert(css.includes('v0.18.7 per-product order status'), 'per-product order rows must have responsive no-horizontal-scroll styling');
'''
write('ui-test.js', ui)

# package version/test script and manifest version.
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.7'
manifest['version_name'] = '0.18.7'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
pkg = json.loads(read('package.json'))
pkg['version'] = '0.18.7'
if 'item-model-test.js' not in pkg['scripts']['test']:
    pkg['scripts']['test'] = pkg['scripts']['test'].replace('node storage-test.js', 'node storage-test.js && node item-model-test.js')
write('package.json', json.dumps(pkg, indent=2) + '\n')

# Durable docs.
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.6', '**Current source baseline: v0.18.7', 1)
readme += '''\n\n## v0.18.7 evidence-safe milestones, faster serial crawl, and per-product state\n\n- Return milestones now require affirmative completion evidence or an item-scoped Amazon timeline checkmark; future instructions, policy prose, and static labels do not advance lifecycle state.\n- Normal serial crawl idle/settle intervals are approximately 30% shorter. Concurrency, retry counts, rate-limit cooldowns, canonical Detail requirements, and Order-ID fingerprint gates are unchanged.\n- Canonical Order Details now persists structured `orderItems`. The dashboard remains one card per order but shows every purchased product beneath it, with product-scoped quantity/price/fulfillment fields only when directly proven. Return groups join to purchased products by strong ASIN or conservative long-title evidence; non-returned products remain visible as `Not returned`, and unmatched returned children stay visible for review.\n'''
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
handoff += '''\n\n## v0.18.7 implementation\n- Live ThermoMaven order `111-1790078-4741015` proved static return timeline labels/policy prose could falsely promote Dropped off / Return received. v0.18.7 moves milestone completion to affirmative evidence, with DOM checkmarks as structured supplemental evidence.\n- Crawl pacing is ~30% faster through shorter serial delays only; rate-limit and correctness gates are unchanged.\n- Canonical Order Details now stores structured purchased `orderItems`; UI joins return groups per purchased product and displays all purchased products, including non-returned ones.\n- Issue #25 tracks live acceptance. Issue #23 remains separate until year rollover is observed live.\n'''
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
testing += '''\n\n## v0.18.7 live acceptance\n1. Allow the verified updater to install v0.18.7 automatically and run a fresh scan (dev version reset clears stale false milestone state).\n2. Order `111-1790078-4741015`: verify only Initiated is complete while Amazon still says `Drop off your return by Sep 8`; Dropped off / Return received / Refund issued / credited must remain incomplete.\n3. Verify a genuinely dropped-off/received/refunded return still advances when Amazon provides affirmative completion evidence or a completed timeline checkmark.\n4. Verify a multi-product order (e.g. six purchased products / four returned) displays six product rows under one order, four with their own return lifecycles and two as `Not returned`.\n5. Confirm item quantity/price stay `—`/absent when Amazon does not directly prove them; no order-total allocation.\n6. Observe throughput improvement while confirming no duplicate page/order regression and no new rate-limit behavior.\n'''
write('TESTING.md', testing)

newchat = read('NEW_CHAT_PROMPT.md')
newchat += '''\n\n### v0.18.7 durable addition\nReturn milestone completion is evidence-safe: static timeline labels, future instructions, and policy/hypothetical prose never complete a milestone. Canonical Order Details persists structured purchased `orderItems`; the dashboard stays one order card with per-product status/return lifecycles. Normal crawl pacing is ~30% faster by shorter serial waits only, with concurrency/rate-limit/fingerprint/canonical-detail safeguards unchanged. Issue #25 tracks live acceptance.\n'''
write('NEW_CHAT_PROMPT.md', newchat)

print('v0.18.7 patch applied')
