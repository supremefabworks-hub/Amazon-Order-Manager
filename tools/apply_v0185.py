from pathlib import Path
import json

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
manifest['version'] = '0.18.5'
manifest['version_name'] = '0.18.5'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
package = json.loads(read('package.json'))
package['version'] = '0.18.5'
package['description'] = 'Amazon / Amazon Business order, return-group, refund, credit, cancelled-order, and verified development-update tracking Chrome extension'
write('package.json', json.dumps(package, indent=2) + '\n')

p = read('parser.js')

# Structural history-card scoping for orders that have no View order details anchor.
old_history = '''  function historyContainerForOrder(doc, orderId) {
    if (!doc?.querySelectorAll || !orderId) return null;
    const matchingAnchors = Array.from(doc.querySelectorAll('a[href]')).filter(a => {
      const href = String(a.getAttribute('href') || a.href || '');
      const text = normalizeText(a.innerText || a.textContent || '');
      return href.includes(orderId) && (/(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|\\/gp\\/css\\/summary\\/edit\\.html|order-details|orderdetails)/i.test(href) || /view\\s+order\\s+details/i.test(text));
    });
    for (const anchor of matchingAnchors) {
      let current = anchor;
      let best = null;
      for (let depth = 0; current && depth < 12; depth += 1, current = current.parentElement) {
        const text = normalizeText(current.innerText || current.textContent || '');
        const ids = extractOrderIds(text);
        if (!ids.includes(orderId)) continue;
        if (ids.length > 1) break;
        const productLinks = Array.from(current.querySelectorAll?.('a[href]') || []).filter(a => {
          const href = String(a.getAttribute('href') || '');
          const label = normalizeText(a.innerText || a.textContent || '');
          return /(\\/dp\\/|\\/gp\\/product\\/|\\/product\\/)/i.test(href) && label && !/amazon business card|prime business/i.test(label);
        });
        if (productLinks.length) best = current;
        if (text.length > 8000) break;
      }
      if (best) return best;
    }
    return closestContainerForOrder(doc, orderId);
  }
'''
new_history = '''  function coherentSingleOrderHistoryCard(node, orderId) {
    if (!node || !orderId) return false;
    const text = normalizeText(node.innerText || node.textContent || '');
    if (!text || text.length > 12000) return false;
    const ids = extractOrderIds(text);
    if (ids.length !== 1 || ids[0] !== orderId) return false;
    const hasPlaced = /(?:^|\\n)\\s*Order placed\\s*(?:$|\\n)/im.test(text);
    const hasTotal = /(?:^|\\n)\\s*Total\\s*(?:$|\\n)/im.test(text);
    if (!hasPlaced || !hasTotal) return false;
    let hasProduct = false;
    try {
      hasProduct = Array.from(node.querySelectorAll?.('a[href]') || []).some(a => /(\\/dp\\/|\\/gp\\/product\\/|\\/product\\/)/i.test(String(a.getAttribute?.('href') || a.href || '')));
    } catch (_) {}
    const hasTerminalOrFulfillment = /(?:^|\\n)\\s*(?:cancelled|canceled|delivered(?:\\s|$)|shipped(?:\\s|$)|arriving(?:\\s|$)) /im.test(`${text} `) || /(?:^|\\n)\\s*(?:cancelled|canceled)\\s*(?:$|\\n)/im.test(text);
    return Boolean(hasProduct || hasTerminalOrFulfillment);
  }

  function structuralHistoryContainerForOrder(doc, orderId) {
    if (!doc?.querySelectorAll || !orderId) return null;
    const seeds = [];
    const seen = new Set();
    const selectors = ['[data-order-id]', '[data-orderid]', '[data-order-number]', 'span', 'a', 'div', 'li'];
    for (const selector of selectors) {
      let nodes = [];
      try { nodes = Array.from(doc.querySelectorAll(selector)); } catch (_) {}
      for (const node of nodes) {
        if (!node || seen.has(node)) continue;
        seen.add(node);
        const text = normalizeText(node.innerText || node.textContent || '');
        if (text.length > 360 || !text.includes(orderId)) continue;
        const ids = extractOrderIds(text);
        if (ids.length === 1 && ids[0] === orderId) seeds.push(node);
      }
    }

    let best = null;
    let bestLength = Infinity;
    for (const seed of seeds) {
      let current = seed;
      for (let depth = 0; current && depth < 14; depth += 1, current = current.parentElement) {
        const text = normalizeText(current.innerText || current.textContent || '');
        const ids = extractOrderIds(text);
        if (!ids.includes(orderId)) continue;
        if (ids.length > 1) break;
        if (text.length > 12000) break;
        if (coherentSingleOrderHistoryCard(current, orderId) && text.length < bestLength) {
          best = current;
          bestLength = text.length;
        }
      }
    }
    return best;
  }

  function historyContainerForOrder(doc, orderId) {
    if (!doc?.querySelectorAll || !orderId) return null;
    const matchingAnchors = Array.from(doc.querySelectorAll('a[href]')).filter(a => {
      const href = String(a.getAttribute('href') || a.href || '');
      const text = normalizeText(a.innerText || a.textContent || '');
      return href.includes(orderId) && (/(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|\\/gp\\/css\\/summary\\/edit\\.html|order-details|orderdetails)/i.test(href) || /view\\s+order\\s+details/i.test(text));
    });
    for (const anchor of matchingAnchors) {
      let current = anchor;
      let best = null;
      for (let depth = 0; current && depth < 12; depth += 1, current = current.parentElement) {
        const text = normalizeText(current.innerText || current.textContent || '');
        const ids = extractOrderIds(text);
        if (!ids.includes(orderId)) continue;
        if (ids.length > 1) break;
        const productLinks = Array.from(current.querySelectorAll?.('a[href]') || []).filter(a => {
          const href = String(a.getAttribute('href') || '');
          const label = normalizeText(a.innerText || a.textContent || '');
          return /(\\/dp\\/|\\/gp\\/product\\/|\\/product\\/)/i.test(href) && label && !/amazon business card|prime business/i.test(label);
        });
        if (productLinks.length) best = current;
        if (text.length > 8000) break;
      }
      if (best) return best;
    }
    return structuralHistoryContainerForOrder(doc, orderId) || closestContainerForOrder(doc, orderId);
  }
'''
p = once(p, old_history, new_history, 'structural no-detail history card locator')

# Product identity must be bound to the same product anchor/item block. Refactor product anchor parsing
# so return-page code can distinguish strong direct ASIN evidence from broad section contamination.
old_names = '''  function extractItemNamesFromContainer(container) {
    if (!container || !container.querySelectorAll) return [];
    const names = [];
    const seen = new Set();
    const productLinks = Array.from(container.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/product/"]'));

    for (const a of productLinks) {
      if (excludedProductAnchor(a)) continue;
      const href = String(a.getAttribute('href') || a.href || '');
      const asin = href.match(/\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})(?:[/?]|$)/i)?.[1]?.toUpperCase() || '';
      let title = normalizeText(a.innerText || a.textContent || '');

      // Port the working exporter fallbacks. Amazon frequently makes the image the product anchor,
      // leaving the anchor text blank even though the title is present in a nearby node.
      if (!title || title.length < 5) {
        let parent = a.parentElement;
        for (let depth = 0; depth < 5 && parent; depth += 1, parent = parent.parentElement) {
          const titleEl = parent.querySelector?.('.a-text-bold, [class*="product-title" i], [class*="item-title" i]');
          const candidate = normalizeText(titleEl?.innerText || titleEl?.textContent || '');
          if (candidate.length >= 5) { title = candidate; break; }
        }
      }
      if (!title || title.length < 5) title = normalizeText(a.getAttribute?.('title') || a.getAttribute?.('aria-label') || '');
      if (!title || title.length < 5) {
        const img = a.querySelector?.('img') || a.parentElement?.querySelector?.('img');
        title = normalizeText(img?.getAttribute?.('alt') || img?.alt || '');
      }

      if (!title || title.length < 3 || title.length > 500) continue;
      if (/buy it again|view order|order details|track package|return or replace|write a product review|invoice|amazon business card|prime business/i.test(title)) continue;
      const key = asin || title.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      names.push(title.slice(0, 400));
    }
    return names.slice(0, 30);
  }
'''
new_names = '''  function extractBoundProductEvidence(container) {
    if (!container?.querySelectorAll) return [];
    const out = [];
    const seen = new Set();
    const productLinks = Array.from(container.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/product/"]'));
    for (const a of productLinks) {
      if (excludedProductAnchor(a)) continue;
      const href = String(a.getAttribute('href') || a.href || '');
      const asin = href.match(/\\/(?:dp|gp\\/product)\\/([A-Z0-9]{10})(?:[/?]|$)/i)?.[1]?.toUpperCase() || '';
      if (!asin || seen.has(asin)) continue;
      let title = normalizeText(a.innerText || a.textContent || '');
      if (!title || title.length < 5) {
        let parent = a.parentElement;
        for (let depth = 0; depth < 5 && parent; depth += 1, parent = parent.parentElement) {
          const titleEl = parent.querySelector?.('.a-text-bold, [class*="product-title" i], [class*="item-title" i]');
          const candidate = normalizeText(titleEl?.innerText || titleEl?.textContent || '');
          if (candidate.length >= 5) { title = candidate; break; }
        }
      }
      if (!title || title.length < 5) title = normalizeText(a.getAttribute?.('title') || a.getAttribute?.('aria-label') || '');
      if (!title || title.length < 5) {
        const img = a.querySelector?.('img') || a.parentElement?.querySelector?.('img');
        title = normalizeText(img?.getAttribute?.('alt') || img?.alt || '');
      }
      if (!title || title.length < 3 || title.length > 500) continue;
      if (/buy it again|view order|order details|track package|return or replace|write a product review|invoice|amazon business card|prime business/i.test(title)) continue;
      seen.add(asin);
      out.push({ asin, itemName: title.slice(0, 400) });
    }
    return out.slice(0, 30);
  }

  function extractItemNamesFromContainer(container) {
    return extractBoundProductEvidence(container).map(entry => entry.itemName).slice(0, 30);
  }
'''
p = once(p, old_names, new_names, 'bound product anchor evidence')

old_entries = '''  function extractReturnItemEntries(container) {
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
        if (!/(?:quantity\\s*:|return item|item\\(s\\) in your return request|refund (?:amount|subtotal)|estimated refund)/i.test(text)) continue;
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
'''
new_entries = '''  function extractReturnItemEntries(container) {
    if (!container?.querySelectorAll) return [];
    const candidates = [];
    const seenElements = new Set();
    const selectors = ['[data-asin]', '[data-item-index]', '[class*="return-item" i]', '[class*="returnItem"]', '.a-box', '.a-section'];
    for (const selector of selectors) {
      const strongItemSelector = !['.a-box', '.a-section'].includes(selector);
      let nodes = [];
      try { nodes = Array.from(container.querySelectorAll(selector)); } catch (_) {}
      for (const el of nodes) {
        if (!el || seenElements.has(el)) continue;
        seenElements.add(el);
        const text = normalizeText(el.innerText || el.textContent || '');
        if (text.length < 8 || text.length > 3600) continue;
        if (!/(?:quantity\\s*:|return item|item\\(s\\) in your return request|refund (?:amount|subtotal)|estimated refund)/i.test(text)) continue;

        const textNames = extractItemNamesFromText(text);
        const boundProducts = extractBoundProductEvidence(el);
        const itemName = textNames[0] || boundProducts[0]?.itemName || null;
        let asin = null;
        let asinEvidenceSource = null;

        if (strongItemSelector) {
          const dataAsin = String(el.getAttribute?.('data-asin') || '').trim().toUpperCase();
          if (/^[A-Z0-9]{10}$/.test(dataAsin)) {
            asin = dataAsin;
            asinEvidenceSource = 'return-item-data-asin';
          } else if (boundProducts.length === 1) {
            asin = boundProducts[0].asin;
            asinEvidenceSource = 'return-item-direct-product-anchor';
          }
        }

        if (!itemName && !asin) continue;
        const refundAmount = findLabeledMoney(text, ['Item refund', 'Refund amount', 'Estimated refund', 'Refund subtotal']);
        candidates.push({ itemName, asin, asinEvidenceSource, refundAmount, textLength: text.length, strongItemSelector });
      }
    }
    const byKey = new Map();
    for (const entry of candidates) {
      const key = entry.asin || String(entry.itemName || '').toLowerCase();
      const prior = byKey.get(key);
      const score = (entry.asinEvidenceSource ? 100000 : 0) + (entry.strongItemSelector ? 10000 : 0) - entry.textLength;
      const priorScore = prior ? ((prior.asinEvidenceSource ? 100000 : 0) + (prior.strongItemSelector ? 10000 : 0) - prior.textLength) : -Infinity;
      if (!prior || score > priorScore) byKey.set(key, entry);
    }
    return Array.from(byKey.values()).map(({ textLength, strongItemSelector, ...entry }) => entry).slice(0, 30);
  }
'''
p = once(p, old_entries, new_entries, 'return item direct ASIN binding')

# Never attach whole-return-page product ASINs/names as item identity. Only item-scoped extraction above
# may supply return-page ASIN evidence.
old_dom = '''      const domNames = extractItemNamesFromContainer(container);
      const asins = extractAsins(container);
      if (domNames.length && !(pageType === 'return' && record.itemNames?.length)) record.itemNames = domNames;
      record.asins = asins;
'''
new_dom = '''      const domNames = pageType === 'return' ? [] : extractItemNamesFromContainer(container);
      const asins = pageType === 'return' ? [] : extractAsins(container);
      if (domNames.length) record.itemNames = domNames;
      record.asins = asins;
'''
p = once(p, old_dom, new_dom, 'no broad return-page identity')

old_item_record = '''              refundAmountScope: itemRefund != null || (singleItemGroup && groupRefundAmount != null) ? 'item' : (groupRefundAmount != null ? 'return' : null),
              itemIdentitySource: (item.itemName || item.asin) ? 'return-page-item' : null,
              provisionalReturn: false,
'''
new_item_record = '''              refundAmountScope: itemRefund != null || (singleItemGroup && groupRefundAmount != null) ? 'item' : (groupRefundAmount != null ? 'return' : null),
              itemIdentitySource: (item.itemName || item.asin) ? 'return-page-item' : null,
              itemAsinEvidenceSource: item.asinEvidenceSource || null,
              provisionalReturn: false,
'''
p = once(p, old_item_record, new_item_record, 'persist direct return ASIN evidence source')

old_fallback_identity = '''          record.refundAmountScope = (record.itemNames || []).length === 1 ? 'item' : (groupRefundAmount != null ? 'return' : null);
          record.itemIdentitySource = (record.itemNames || []).length ? 'return-page-item' : null;
          record.recordId = makeRecordId(record);
'''
new_fallback_identity = '''          record.refundAmountScope = (record.itemNames || []).length === 1 ? 'item' : (groupRefundAmount != null ? 'return' : null);
          record.asins = [];
          record.itemAsinEvidenceSource = null;
          record.itemIdentitySource = (record.itemNames || []).length ? 'return-page-text' : null;
          record.recordId = makeRecordId(record);
'''
p = once(p, old_fallback_identity, new_fallback_identity, 'safe return fallback identity')

# Export structural/bound helpers for regression tests.
p = once(p, '''    closestContainerForOrder,
    extractItemNamesFromContainer,
    orderIdFromUrl
''', '''    closestContainerForOrder,
    historyContainerForOrder,
    structuralHistoryContainerForOrder,
    coherentSingleOrderHistoryCard,
    extractBoundProductEvidence,
    extractItemNamesFromContainer,
    orderIdFromUrl
''', 'export v0.18.5 helpers')
write('parser.js', p)

# Storage: only strongly bound incoming ASIN evidence may contradict trusted Order Details identity.
s = read('storage.js')
old_conflict = '''    let asinConflict = false;
    if (existingAsins.size && incomingAsins.size) {
      let overlap = false;
      for (const asin of existingAsins) if (incomingAsins.has(asin)) overlap = true;
      asinConflict = !overlap;
    }
'''
new_conflict = '''    const strongIncomingAsin = incoming.itemIdentitySource === 'order-detail-return-link' ||
      ['return-item-data-asin', 'return-item-direct-product-anchor'].includes(String(incoming.itemAsinEvidenceSource || ''));
    let asinConflict = false;
    if (strongIncomingAsin && existingAsins.size && incomingAsins.size) {
      let overlap = false;
      for (const asin of existingAsins) if (incomingAsins.has(asin)) overlap = true;
      asinConflict = !overlap;
    }
'''
s = once(s, old_conflict, new_conflict, 'strongly bound ASIN conflict only')
write('storage.js', s)

# Parser regression tests: a no-detail card between adjacent orders must scope to itself, and broad
# return sections may not manufacture ASIN identity from unrelated product links.
t = read('parser-test.js')
append = r'''

// v0.18.5 structural no-detail history-card scoping regressions
function fakeNode(text, parent = null, anchors = [], attrs = {}) {
  return {
    innerText: text, textContent: text, parentElement: parent,
    getAttribute(name) { return attrs[name] ?? null; },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === 'a[href]' || selector.includes('a[href*="/dp/"]') || selector.includes('a[href*="/gp/product/"]') || selector.includes('a[href*="/product/"]')) return anchors;
      return [];
    }
  };
}
function productAnchor(asin, title, parent = null) {
  return {
    innerText: title, textContent: title, parentElement: parent, href: `https://www.amazon.com/dp/${asin}`,
    getAttribute(name) { if (name === 'href') return `/dp/${asin}`; if (name === 'title') return title; return null; },
    querySelector() { return null; }, closest() { return null; }
  };
}
const liveCancelledId = '112-3886192-2097013';
const cancelledProduct = productAnchor('B0FN37J39V', 'HHZL Rubber Edge Trim T Molding Seal Strip');
const cancelledCardText = `Order placed\nJune 10, 2026\nTotal\n$0.00\nOrder # ${liveCancelledId}\nCancelled\nHHZL Rubber Edge Trim T Molding Seal Strip`;
const cancelledCardNode = fakeNode(cancelledCardText, null, [cancelledProduct]);
const cancelledOrderNumberNode = fakeNode(`Order # ${liveCancelledId}`, cancelledCardNode, []);
const neighboringAncestor = fakeNode(`Order placed\nJune 11, 2026\nTotal\n$10.00\nOrder # 113-1111111-1111111\n${cancelledCardText}\nOrder placed\nJune 9, 2026\nTotal\n$20.00\nOrder # 113-2222222-2222222`, null, [cancelledProduct]);
cancelledCardNode.parentElement = neighboringAncestor;
const structuralDoc = {
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [];
    if (['span','a','div','li','[data-order-id]','[data-orderid]','[data-order-number]'].includes(selector)) return [cancelledOrderNumberNode, cancelledCardNode, neighboringAncestor];
    return [];
  }
};
const isolatedCancelled = p.historyContainerForOrder(structuralDoc, liveCancelledId);
assert(isolatedCancelled === cancelledCardNode, 'no-detail cancelled order must resolve to its own single-order card, not a neighboring multi-order ancestor');
const isolatedTerminal = p.terminalCancelledHistoryEvidence(isolatedCancelled.innerText, liveCancelledId);
assert(isolatedTerminal.complete === true, 'isolated cancelled $0.00 card must satisfy terminal evidence');
assert(p.coherentSingleOrderHistoryCard(neighboringAncestor, liveCancelledId) === false, 'multi-order ancestor must never qualify as a coherent single-order card');

// v0.18.5 return-page identity regressions
const unrelatedAnchor = productAnchor('B000000099', 'Unrelated recommendation');
const broadReturnBox = fakeNode('Return item\nRAMPOW Micro USB Cable 2 Pack 3.3ft\nQuantity: 1\nRefund amount $6.99', null, [unrelatedAnchor]);
broadReturnBox.querySelectorAll = selector => {
  if (selector === '.a-box') return [broadReturnBox];
  if (selector.includes('a[href*="/dp/"]')) return [unrelatedAnchor];
  return [];
};
const broadEntries = p.extractReturnItemEntries(broadReturnBox);
assert(broadEntries.length === 1, 'broad return text should still produce one item entry');
assert(broadEntries[0].itemName && /RAMPOW/i.test(broadEntries[0].itemName), 'return-specific text must win for the item name');
assert(broadEntries[0].asin == null && broadEntries[0].asinEvidenceSource == null, 'unrelated product link in broad return section must not become ASIN identity');

const strongReturnAnchor = productAnchor('B000000002', 'Different Product');
const strongReturnItem = fakeNode('Return item\nDifferent Product\nQuantity: 1\nRefund amount $10.00', null, [strongReturnAnchor], {'data-asin':'B000000002'});
strongReturnItem.querySelectorAll = selector => {
  if (selector === '[data-asin]') return [strongReturnItem];
  if (selector.includes('a[href*="/dp/"]')) return [strongReturnAnchor];
  return [];
};
const strongEntries = p.extractReturnItemEntries(strongReturnItem);
assert(strongEntries.length === 1 && strongEntries[0].asin === 'B000000002', 'direct data-asin item block must preserve strong ASIN evidence');
assert(strongEntries[0].asinEvidenceSource === 'return-item-data-asin', 'strong return ASIN must record its binding source');
console.log('v0.18.5 structural scope and return identity parser regressions passed');
'''
if 'v0.18.5 structural scope and return identity parser regressions passed' not in t:
    t += append
write('parser-test.js', t)

# Storage regressions: weak broad ASIN disagreement no longer flags, directly bound disagreement still does.
st = read('storage-test.js')
st = once(st,
'''  await s.upsertRecords([{ ...trustedReturn, itemNames: ['Wrong Return Page Sibling'], asins: ['B000000099'], itemIdentitySource: 'return-page-item', authoritativeReturnCapture: true, provisionalReturn: false, status: 'refunded', returnStage: 'refund_issued' }]);
  const trustedMerged = (await s.getLedger()).find(r => r.recordId === trustedReturn.recordId);
  assert(trustedMerged.itemNames[0] === 'Trusted Order Details Item', 'exact Order Details return-link identity must survive conflicting return-page item text');
  assert(trustedMerged.asins[0] === 'B000000010', 'trusted return-link ASIN must survive a conflicting authoritative-page ASIN');
  assert(trustedMerged.itemIdentityConflict === true, 'conflicting return-page identity must be flagged instead of silently replacing trusted identity');
  assert(s.needsCreditReview(trustedMerged) === true, 'item identity conflicts must require review');
''',
'''  await s.upsertRecords([{ ...trustedReturn, itemNames: ['Wrong Return Page Sibling'], asins: ['B000000099'], itemIdentitySource: 'return-page-item', itemAsinEvidenceSource: null, authoritativeReturnCapture: true, provisionalReturn: false, status: 'refunded', returnStage: 'refund_issued' }]);
  const trustedMerged = (await s.getLedger()).find(r => r.recordId === trustedReturn.recordId);
  assert(trustedMerged.itemNames[0] === 'Trusted Order Details Item', 'exact Order Details return-link identity must survive weak return-page item text');
  assert(trustedMerged.asins[0] === 'B000000010', 'trusted return-link ASIN must survive weak broad return-page ASIN contamination');
  assert(trustedMerged.itemIdentityConflict !== true, 'weak/unbound return-page ASIN must not create an item identity conflict');
''', 'weak return ASIN must not conflict')

st = once(st,
'''  await s.upsertRecords([{ ...asinConflictBase, asins: ['B000000002'], itemNames: ['Different Product'], itemIdentitySource: 'return-page-item', provisionalReturn: false, authoritativeReturnCapture: true }]);
''',
'''  await s.upsertRecords([{ ...asinConflictBase, asins: ['B000000002'], itemNames: ['Different Product'], itemIdentitySource: 'return-page-item', itemAsinEvidenceSource: 'return-item-data-asin', provisionalReturn: false, authoritativeReturnCapture: true }]);
''', 'strong contradictory ASIN test source')
write('storage-test.js', st)

# UI static regression prevents broad return-page identity from coming back.
u = read('ui-test.js')
ui_append = "\nassert(storageSourceGuard = fs.readFileSync(__dirname + '/storage.js', 'utf8'), 'storage source must load');\nassert(storageSourceGuard.includes('itemAsinEvidenceSource'), 'storage conflicts must require strong bound ASIN evidence');\nassert(!parserReturnBroadIdentityGuard, 'placeholder');\n"
# Avoid introducing test globals via placeholder; add simple source checks instead.
if "broad return-page product identity" not in u:
    u += "\nconst parserSourceV0185 = fs.readFileSync(__dirname + '/parser.js', 'utf8');\nassert(parserSourceV0185.includes(\"pageType === 'return' ? [] : extractAsins(container)\"), 'broad return-page product identity must stay disabled');\nassert(parserSourceV0185.includes('structuralHistoryContainerForOrder'), 'no-detail history cards must have structural scoping');\nassert(fs.readFileSync(__dirname + '/storage.js', 'utf8').includes('itemAsinEvidenceSource'), 'identity conflicts must require bound ASIN evidence');\n"
write('ui-test.js', u)

# Durable docs.
for path in ['README.md','PROJECT_HANDOFF.md','TESTING.md','NEW_CHAT_PROMPT.md']:
    text = read(path)
    text = text.replace('v0.18.4', 'v0.18.5')
    if path == 'README.md':
        text += '''\n\n## v0.18.5 live structural-scoping hardening\n\nv0.18.5 fixes two live parser defects. Orders with no Detail action, especially proven `$0.00` cancelled orders, are now scoped by their own structural Order History card using the visible Order ID and single-order ancestor boundaries instead of falling back to neighboring page text. Return-page identity is also hardened: whole-page/broad-section product links cannot manufacture returned-item ASINs; contradictory ASIN evidence is reviewable only when directly bound to the return item through a specific item block/data-ASIN or direct product anchor. Stable Amazon `returnItemId` plus trusted Order Details identity remains authoritative.\n'''
    elif path == 'PROJECT_HANDOFF.md':
        text += '''\n\n### v0.18.5 live fixes\n- Structural single-order history-card locator handles orders with no Detail anchor without neighboring-order contamination.\n- `$0.00` terminal cancelled exception remains strict and now receives the correct scoped card.\n- Broad return-page product links no longer create ASIN identity; only directly bound item ASIN evidence may conflict with trusted Order Details identity.\n- Live examples motivating the identity fix: RAMPOW order `111-1110034-5588263` and Milton order `111-8528386-2632255`.\n'''
    elif path == 'TESTING.md':
        text += '''\n\n## v0.18.5 live acceptance\n1. Confirm the installed build auto-updates to v0.18.5 without reinstall/reload.\n2. Restart a clean lifetime scan and verify 2026 page 6 passes order `112-3886192-2097013` as `Cancelled` / `Terminal history` / `$0.00` and continues to page 7.\n3. Confirm a normal order without a real Detail URL still hard-stops with its exact Order ID.\n4. Verify RAMPOW `111-1110034-5588263` and Milton `111-8528386-2632255` no longer show `Item identity conflict` when return-page ASIN evidence is not directly bound to the returned item.\n5. Confirm a test fixture with directly bound contradictory ASIN evidence still enters Needs Review.\n'''
    elif path == 'NEW_CHAT_PROMPT.md':
        text += '''\n- v0.18.5: no-detail Order History cards use structural single-order scoping; broad return-page product links cannot create ASIN conflicts unless identity evidence is directly item-bound.\n'''
    write(path, text)

print('v0.18.5 live parser hardening applied')
