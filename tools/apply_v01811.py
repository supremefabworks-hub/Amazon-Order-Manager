from pathlib import Path
import json

R = Path('.')
def read(path): return (R / path).read_text(encoding='utf-8')
def write(path, text): (R / path).write_text(text, encoding='utf-8')
def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)

# ---------------- parser.js ----------------
p = read('parser.js')
replacement_helpers = r'''
  const REPLACEMENT_STAGE_RANK = { unknown: 0, detected: 1, requested: 2, ordered: 2, shipped: 3, delivered: 4, complete: 5 };

  function replacementStageRank(stage) {
    return REPLACEMENT_STAGE_RANK[String(stage || '').toLowerCase()] ?? 0;
  }

  function replacementEvidenceFromText(text) {
    const normalized = normalizeText(text);
    const lines = normalized.split('\n').map(line => line.trim()).filter(Boolean);
    const noReturnRequired = lines.some(line =>
      /(?:there(?:'|’)?s|there is)\s+no need to return (?:your )?(?:item|product)|(?:you (?:do not|don't|don’t) need to|no need to) return (?:the |your )?(?:original )?(?:item|product)|no return (?:is )?required/i.test(line)
    );
    const stageRules = [
      ['complete', /(?:replacement (?:is )?complete|your replacement (?:is )?complete|replacement (?:has been|was) completed|replacement complete)/i],
      ['delivered', /(?:replacement (?:has been|was|is) delivered|replacement delivered)/i],
      ['shipped', /(?:replacement (?:has been|was|is) shipped|replacement shipped|replacement is on the way)/i],
      ['ordered', /(?:replacement (?:has been|was|is) ordered|replacement order (?:has been|was) placed|replacement approved)/i],
      ['requested', /(?:replacement (?:has been|was|is) requested|replacement request (?:is )?(?:confirmed|approved)|we(?:'|’)ll send (?:you )?a replacement|we will send (?:you )?a replacement|replacement (?:is )?being prepared|replacement arriving)/i]
    ];
    let stage = null;
    let statusText = null;
    for (const [candidateStage, pattern] of stageRules) {
      const line = lines.find(value => pattern.test(value));
      if (line) { stage = candidateStage; statusText = line.slice(0, 220); break; }
    }
    if (!stage && noReturnRequired && /replacement/i.test(normalized)) {
      stage = 'detected';
      statusText = lines.find(line => /replacement/i.test(line))?.slice(0, 220) || 'Replacement detected';
    }
    return {
      detected: Boolean(stage),
      stage: stage || null,
      statusText: statusText || null,
      noReturnRequired: Boolean(stage && noReturnRequired)
    };
  }

  function strongerReplacement(existing, incoming) {
    const a = existing || { detected: false, stage: null, statusText: null, noReturnRequired: false };
    const b = incoming || { detected: false, stage: null, statusText: null, noReturnRequired: false };
    const winner = replacementStageRank(b.stage) >= replacementStageRank(a.stage) ? b : a;
    return {
      detected: Boolean(a.detected || b.detected),
      stage: winner.stage || a.stage || b.stage || null,
      statusText: winner.statusText || a.statusText || b.statusText || null,
      noReturnRequired: Boolean(a.noReturnRequired || b.noReturnRequired)
    };
  }

  function nearestReplacementEvidence(anchor) {
    let current = anchor?.parentElement || null;
    let fallback = null;
    for (let depth = 0; current && depth < 9; depth += 1, current = current.parentElement) {
      const text = normalizeText(current.innerText || current.textContent || '');
      if (!text || text.length > 7000) continue;
      let productLinks = [];
      try { productLinks = Array.from(current.querySelectorAll?.('a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/product/"]') || []); } catch (_) {}
      const asins = new Set(productLinks.map(link => productAnchorInfo(link)?.asin).filter(Boolean));
      if (asins.size > 1) break;
      const evidence = replacementEvidenceFromText(text);
      if (!evidence.detected) continue;
      if (asins.size === 1 && evidence.noReturnRequired) return evidence;
      if (!fallback) fallback = evidence;
    }
    return fallback || { detected: false, stage: null, statusText: null, noReturnRequired: false };
  }

'''
p = once(p, '  function extractOrderLineItems(container) {', replacement_helpers + '  function extractOrderLineItems(container) {', 'insert replacement helpers')
p = once(p,
"        fulfillmentStatus: extractDirectFulfillmentStatus(text),\n        source: 'order-details-product-anchor'",
"        fulfillmentStatus: extractDirectFulfillmentStatus(text),\n        replacementStage: replacementEvidenceFromText(text).stage,\n        replacementStatusText: replacementEvidenceFromText(text).statusText,\n        replacementNoReturnRequired: replacementEvidenceFromText(text).noReturnRequired,\n        replacementSource: replacementEvidenceFromText(text).detected ? 'order-details-product-block' : null,\n        source: 'order-details-product-anchor'",
'order item replacement fields')
p = once(p,
"        quantity: existing.quantity ?? candidate.quantity,\n        itemAmount: existing.itemAmount ?? candidate.itemAmount,\n        fulfillmentStatus: existing.fulfillmentStatus || candidate.fulfillmentStatus\n      });",
"        quantity: existing.quantity ?? candidate.quantity,\n        itemAmount: existing.itemAmount ?? candidate.itemAmount,\n        fulfillmentStatus: existing.fulfillmentStatus || candidate.fulfillmentStatus,\n        ...(() => {\n          const replacement = strongerReplacement(\n            { detected: Boolean(existing.replacementStage), stage: existing.replacementStage, statusText: existing.replacementStatusText, noReturnRequired: existing.replacementNoReturnRequired },\n            { detected: Boolean(candidate.replacementStage), stage: candidate.replacementStage, statusText: candidate.replacementStatusText, noReturnRequired: candidate.replacementNoReturnRequired }\n          );\n          return {\n            replacementStage: replacement.stage,\n            replacementStatusText: replacement.statusText,\n            replacementNoReturnRequired: replacement.noReturnRequired,\n            replacementSource: replacement.detected ? (existing.replacementSource || candidate.replacementSource || 'order-details-product-block') : null\n          };\n        })()\n      });",
'merge replacement fields')
p = once(p,
"      const evidence = nearestReturnItemEvidence(a);\n      results.push({",
"      const evidence = nearestReturnItemEvidence(a);\n      const replacement = nearestReplacementEvidence(a);\n      const replacementOnly = Boolean(isOrderDetailPage(baseUrl) && replacement.detected && replacement.noReturnRequired);\n      results.push({",
'link replacement evidence')
p = once(p,
"        itemIdentitySource: (evidence.itemNames.length || evidence.asins.length)\n          ? (isOrderDetailPage(baseUrl) ? 'order-detail-return-link' : 'return-link')\n          : null\n      });",
"        itemIdentitySource: (evidence.itemNames.length || evidence.asins.length)\n          ? (isOrderDetailPage(baseUrl) ? 'order-detail-return-link' : 'return-link')\n          : null,\n        replacementContext: replacement.detected,\n        replacementStage: replacement.stage,\n        replacementStatusText: replacement.statusText,\n        replacementNoReturnRequired: replacement.noReturnRequired,\n        replacementOnly\n      });",
'link replacement fields')
p = once(p,
"    const detailLinks = extractOrderDetailLinks(doc, url);\n    const returnLinks = extractReturnStatusLinks(doc, url);\n    const detailByOrder = new Map(detailLinks.map(link => [link.orderId, link.url]));",
"    const detailLinks = extractOrderDetailLinks(doc, url);\n    const statusLinks = extractReturnStatusLinks(doc, url);\n    const replacementLinks = statusLinks.filter(link => link.replacementOnly === true);\n    const returnLinks = statusLinks.filter(link => link.replacementOnly !== true);\n    const detailByOrder = new Map(detailLinks.map(link => [link.orderId, link.url]));",
'filter replacement-only links')
p = once(p,
"      detailLinks,\n      returnLinks,\n      historyPageLinks: extractOrderHistoryLinks(doc, url),",
"      detailLinks,\n      returnLinks,\n      replacementLinks,\n      historyPageLinks: extractOrderHistoryLinks(doc, url),",
'parse output replacement links')
p = once(p,
"    extractReturnStatusLinks,\n    returnUrlMetadata,\n    nearestReturnItemEvidence,",
"    extractReturnStatusLinks,\n    returnUrlMetadata,\n    nearestReturnItemEvidence,\n    replacementEvidenceFromText,\n    nearestReplacementEvidence,\n    replacementStageRank,",
'export replacement helpers')
write('parser.js', p)

# ---------------- storage.js ----------------
s = read('storage.js')
s = once(s,
"        fulfillmentStatus: raw.fulfillmentStatus ? String(raw.fulfillmentStatus).slice(0, 180) : null,\n        source: raw.source ? String(raw.source).slice(0, 80) : null",
"        fulfillmentStatus: raw.fulfillmentStatus ? String(raw.fulfillmentStatus).slice(0, 180) : null,\n        replacementStage: ['detected','requested','ordered','shipped','delivered','complete'].includes(String(raw.replacementStage || '').toLowerCase()) ? String(raw.replacementStage).toLowerCase() : null,\n        replacementStatusText: raw.replacementStatusText ? String(raw.replacementStatusText).slice(0, 220) : null,\n        replacementNoReturnRequired: Boolean(raw.replacementNoReturnRequired),\n        replacementSource: raw.replacementSource ? String(raw.replacementSource).slice(0, 80) : null,\n        source: raw.source ? String(raw.source).slice(0, 80) : null",
'storage replacement fields')
write('storage.js', s)

# ---------------- item-model.js ----------------
im = read('item-model.js')
im = once(im,
"      fulfillmentStatus: clean(item.fulfillmentStatus) || null,\n      source: clean(item.source) || null",
"      fulfillmentStatus: clean(item.fulfillmentStatus) || null,\n      replacementStage: ['detected','requested','ordered','shipped','delivered','complete'].includes(clean(item.replacementStage).toLowerCase()) ? clean(item.replacementStage).toLowerCase() : null,\n      replacementStatusText: clean(item.replacementStatusText) || null,\n      replacementNoReturnRequired: Boolean(item.replacementNoReturnRequired),\n      replacementSource: clean(item.replacementSource) || null,\n      source: clean(item.source) || null",
'item model structured replacement')
im = once(im,
"      fulfillmentStatus: null,\n      source: 'legacy-order-item'",
"      fulfillmentStatus: null,\n      replacementStage: null,\n      replacementStatusText: null,\n      replacementNoReturnRequired: false,\n      replacementSource: null,\n      source: 'legacy-order-item'",
'item model legacy replacement')
write('item-model.js', im)

# ---------------- dashboard.js ----------------
d = read('dashboard.js')
replacement_dashboard_helpers = r'''  function replacementStageRank(stage) {
    return ({ detected:1, requested:2, ordered:2, shipped:3, delivered:4, complete:5 })[String(stage || '').toLowerCase()] || 0;
  }
  function replacementLabel(stage) {
    return ({
      detected: 'Replacement', requested: 'Replacement requested', ordered: 'Replacement ordered',
      shipped: 'Replacement shipped', delivered: 'Replacement delivered', complete: 'Replacement complete'
    })[String(stage || '').toLowerCase()] || 'Replacement';
  }
'''
d = once(d, '  function milestoneDate(record, key) {', replacement_dashboard_helpers + '  function milestoneDate(record, key) {', 'dashboard replacement helpers')
d = once(d,
"      const hasReturn = returnRecords.length > 0;\n      const allAmazonCredited = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.credited);",
"      const hasReturn = returnRecords.length > 0;\n      const replacementItems = itemJoin.items.filter(item => Boolean(item.replacementStage));\n      const hasReplacement = replacementItems.length > 0;\n      const replacementStage = replacementItems.map(item => item.replacementStage).filter(Boolean).sort((a,b) => replacementStageRank(a) - replacementStageRank(b))[0] || null;\n      const allAmazonCredited = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.credited);",
'row replacement state')
d = once(d,
"      } else if (allAmazonCredited) { stateKey = 'credited'; statusLabel = 'Amazon credited'; }\n      else if (allIssued) { stateKey = 'refund_issued'; statusLabel = 'Refund issued'; }\n      else if (hasReturn) { stateKey = 'return'; statusLabel = stageLabel(storage.getReturnStage(lowestReturn)); }",
"      } else if (allAmazonCredited) { stateKey = 'credited'; statusLabel = 'Amazon credited'; }\n      else if (allIssued) { stateKey = 'refund_issued'; statusLabel = 'Refund issued'; }\n      else if (hasReturn) { stateKey = 'return'; statusLabel = stageLabel(storage.getReturnStage(lowestReturn)); }\n      else if (hasReplacement) { stateKey = 'replacement'; statusLabel = replacementLabel(replacementStage); }",
'order replacement badge')
d = once(d,
"      const statusTexts = uniqueStrings(returnRecords.map(r => r.statusText).filter(Boolean));\n      const lastScannedAt =",
"      const statusTexts = uniqueStrings(returnRecords.map(r => r.statusText).filter(Boolean));\n      const replacementStatusTexts = uniqueStrings(replacementItems.map(item => item.replacementStatusText || replacementLabel(item.replacementStage)).filter(Boolean));\n      const lastScannedAt =",
'replacement status text')
d = once(d,
"        orderId, order, returns: returnRecords, allReturns: allReturnRecords, returnGroups, hasReturn, needsReview, terminalCancelled, stateKey, statusLabel,",
"        orderId, order, returns: returnRecords, allReturns: allReturnRecords, returnGroups, hasReturn, hasReplacement, replacementStage, needsReview, terminalCancelled, stateKey, statusLabel,",
'row replacement fields')
d = once(d,
"        amazonStatus: statusTexts.length ? statusTexts.join(' · ') : (order?.statusText || order?.status || '—'),",
"        amazonStatus: uniqueStrings([...replacementStatusTexts, ...statusTexts]).join(' · ') || (order?.statusText || order?.status || '—'),",
'row replacement status')
start = d.index('  function orderProductStatusMarkup(row) {')
end = d.index('\n  function setDynamicOptions', start)
new_product_markup = r'''  function orderProductStatusMarkup(row) {
    if (!row.itemStates?.length) return row.hasReturn ? legacyReturnProgressMarkup(row) : `<span class="muted tiny">${esc(row.statusLabel || 'Order')}</span>`;
    const products = row.itemStates.map((item, index) => {
      const groups = item.returnGroups || [];
      const representatives = groups.map(group => group.representative).filter(Boolean);
      const highest = representatives.slice().sort((a,b) => storage.returnStageRank(b) - storage.returnStageRank(a))[0] || null;
      const returnText = groups.length ? `${groups.length > 1 ? `${groups.length} returns · ` : ''}${stageLabel(storage.getReturnStage(highest))}` : '';
      const replacementText = item.replacementStage ? replacementLabel(item.replacementStage) : '';
      const workflowLabel = [replacementText, returnText].filter(Boolean).join(' · ') || 'Not returned';
      const meta = [
        item.quantity != null ? `Qty ${item.quantity}` : '',
        item.itemAmount != null ? money(item.itemAmount) : '',
        item.asin || '',
        item.fulfillmentStatus || '',
        item.replacementNoReturnRequired ? 'No return required' : ''
      ].filter(Boolean).join(' · ');
      const classes = [groups.length ? 'has-product-return' : '', item.replacementStage ? 'has-product-replacement' : ''].filter(Boolean).join(' ');
      const stateClass = groups.length ? 'product-returned' : item.replacementStage ? 'product-replacement' : 'product-not-returned';
      return `<div class="order-product-row ${classes}">
        <div class="order-product-head">
          <div><span class="order-product-index">${index + 1}</span><strong title="${esc(item.itemName)}">${esc(item.itemName)}</strong></div>
          <span class="product-state ${stateClass}">${esc(workflowLabel)}</span>
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
d = d[:start] + new_product_markup + d[end:]
d = once(d,
"    if (value === 'needs_review') return row.needsReview;\n    if (value === 'cancelled') return row.terminalCancelled;",
"    if (value === 'needs_review') return row.needsReview;\n    if (value === 'replacement') return row.hasReplacement;\n    if (value === 'cancelled') return row.terminalCancelled;",
'replacement filter')
write('dashboard.js', d)

# ---------------- dashboard.html ----------------
h = read('dashboard.html')
h = once(h,
"        <option value=\"no_return\">No return</option>\n        <option value=\"return_started\">Return started</option>",
"        <option value=\"no_return\">No return</option>\n        <option value=\"replacement\">Replacement</option>\n        <option value=\"return_started\">Return started</option>",
'replacement status option')
write('dashboard.html', h)

# ---------------- ui.css ----------------
css = read('ui.css')
css += r'''

/* v0.18.11 replacement workflow state */
.badge-replacement { background:#eef4ff; color:#234f8c; }
.order-product-row.has-product-replacement { border-left:3px solid #5b7fb0; }
.product-state.product-replacement { background:#eef4ff; color:#234f8c; }
'''
write('ui.css', css)

# ---------------- tests ----------------
pt = read('parser-test.js')
pt += r'''

// v0.18.11 replacement workflow regressions (synthetic fixture only).
const replacementComplete = p.replacementEvidenceFromText(`Replacement complete\nThere's no need to return your item. Your replacement is complete.`);
assert(replacementComplete.detected && replacementComplete.stage === 'complete', 'replacement-complete text must be detected as replacement state');
assert(replacementComplete.noReturnRequired === true, 'explicit no-return-required replacement must be recognized');
const replacementNeedsOriginal = p.replacementEvidenceFromText(`Replacement ordered\nReturn the original item by Sep 20.`);
assert(replacementNeedsOriginal.detected && replacementNeedsOriginal.noReturnRequired === false, 'replacement without explicit no-return evidence must remain return-eligible');

const replacementProductAnchor = {
  getAttribute(name) { return name === 'href' ? '/dp/B0ABC12345' : null; },
  href:'/dp/B0ABC12345', innerText:'Synthetic Hydraulic Steering Rack', textContent:'Synthetic Hydraulic Steering Rack', parentElement:null
};
const replacementStatusAnchorV1811 = {
  getAttribute(name) { return name === 'href' ? '/spr/returns/prep?orderId=111-0000000-0000001&contractId=synthetic-contract&itemId=synthetic-item' : null; },
  href:'/spr/returns/prep?orderId=111-0000000-0000001&contractId=synthetic-contract&itemId=synthetic-item',
  innerText:'View return/refund status', textContent:'View return/refund status', parentElement:null
};
const replacementBlockText = `Order # 111-0000000-0000001\nReplacement complete\nThere's no need to return your item. Your replacement is complete.\nSynthetic Hydraulic Steering Rack`;
const replacementBlock = {
  innerText: replacementBlockText, textContent: replacementBlockText, parentElement:null,
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [replacementProductAnchor, replacementStatusAnchorV1811];
    if (selector.includes('/dp/') || selector.includes('/gp/product/') || selector.includes('/product/')) return [replacementProductAnchor];
    return [];
  }
};
replacementProductAnchor.parentElement = replacementBlock;
replacementStatusAnchorV1811.parentElement = replacementBlock;
const replacementLinkDoc = { querySelectorAll(selector) { return selector === 'a[href]' ? [replacementStatusAnchorV1811] : []; } };
const syntheticReplacementLinks = p.extractReturnStatusLinks(replacementLinkDoc, 'https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000001');
assert(syntheticReplacementLinks.length === 1 && syntheticReplacementLinks[0].replacementOnly === true, 'no-return replacement management link must be marked replacement-only');
console.log('v0.18.11 replacement parser regressions passed');
'''
write('parser-test.js', pt)

st = read('storage-test.js')
st = once(st,
"  console.log('storage tests passed');",
"  const replacementOrder = { recordId:'order:111-0000000-0000002', recordType:'order', orderId:'111-0000000-0000002', detailScanComplete:true, orderItems:[{ itemKey:'asin:B0ABC12345', asin:'B0ABC12345', itemName:'Synthetic Steering Rack', fulfillmentStatus:'Delivered', replacementStage:'complete', replacementStatusText:'Replacement complete', replacementNoReturnRequired:true, replacementSource:'order-details-product-block', source:'order-details-product-anchor' }] };\n  await s.upsertRecords([replacementOrder]);\n  const storedReplacement = (await s.getLedger()).find(r => r.recordId === replacementOrder.recordId);\n  assert(storedReplacement.orderItems[0].replacementStage === 'complete', 'storage must preserve product replacement stage');\n  assert(storedReplacement.orderItems[0].replacementNoReturnRequired === true, 'storage must preserve no-return-required replacement evidence');\n\n  console.log('storage tests passed');",
'storage replacement regression')
write('storage-test.js', st)

imt = read('item-model-test.js')
imt = once(imt,
"console.log('item model tests passed');",
"const replacementModel = model.normalizeOrderItems({ orderItems:[{ itemKey:'asin:B0ABC12345', asin:'B0ABC12345', itemName:'Synthetic Steering Rack', replacementStage:'complete', replacementStatusText:'Replacement complete', replacementNoReturnRequired:true, replacementSource:'order-details-product-block' }] });\nassert(replacementModel.length === 1 && replacementModel[0].replacementStage === 'complete', 'item model must preserve replacement stage');\nassert(replacementModel[0].replacementNoReturnRequired === true, 'item model must preserve no-return-required evidence');\n\nconsole.log('item model tests passed');",
'item model replacement regression')
write('item-model-test.js', imt)

ut = read('ui-test.js')
ut += r'''

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
'''
write('ui-test.js', ut)

# ---------------- release version ----------------
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.11'
manifest['version_name'] = '0.18.11'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
package = json.loads(read('package.json'))
package['version'] = '0.18.11'
package['description'] = 'Amazon / Amazon Business complete-order ledger with authoritative returns, replacement workflows, return review/errors, filtering, bank verification, and verified development updates'
write('package.json', json.dumps(package, indent=2) + '\n')

# ---------------- durable docs ----------------
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.10 candidate for Issue #31.**', '**Current source baseline: v0.18.11 candidate for Issue #33.**', 1)
readme = readme.replace('- **#31 — v0.18.10 acceptance** for consolidated dashboard metrics and four user-facing views: Orders, Returns, Return review, Errors.', '- **#31 — v0.18.10 acceptance** for consolidated dashboard metrics and four user-facing views: Orders, Returns, Return review, Errors.\n- **#33 — v0.18.11 acceptance** for replacement detection and replacement-vs-return separation.', 1)
readme = readme.replace('2. Read Issues #7, #23, #25, #29, and #31 and any newer issue that supersedes their scope.', '2. Read Issues #7, #23, #25, #29, #31, and #33 and any newer issue that supersedes their scope.', 1)
readme = readme.replace('4. Root v0.18.10 is the active candidate.', '4. Root v0.18.11 is the active candidate.', 1)
readme += '''\n\n## v0.18.11 replacement workflow separation\n\nAmazon replacements are modeled independently from refund returns. Product-scoped Order Details evidence such as `Replacement requested`, `Replacement shipped`, `Replacement delivered`, and `Replacement complete` is retained on the purchased item. A replacement-management `/spr/returns/prep` link is excluded from return/refund processing only when the same product context affirmatively proves that no return is required. Replacement workflows without that proof remain return-eligible because some replacements require the original item back. Replacement-only orders do not count as Returns, do not show a synthetic `$0.00` refund, and expose replacement state in the order/product UI and status filter. Issue #33 tracks live acceptance.\n'''
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
handoff += '''\n\n## v0.18.11 replacement workflow candidate\n- Issue #33 tracks live replacement-vs-return acceptance.\n- Replacement is product fulfillment state, not automatically a refund return.\n- Explicit no-return-required replacement evidence suppresses the replacement-management return-status link from return counting/fetching; ambiguous/return-required replacements remain eligible for normal return processing.\n- Replacement-only orders should show replacement status, Refund `—`, and remain outside Returns/Return review.\n- Use synthetic fixtures only in committed tests; do not commit live order exports or addresses.\n'''
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
testing += '''\n\n## v0.18.11 replacement live acceptance\n1. Allow the development updater to install v0.18.11.\n2. Fresh-scan a known replacement-only order where Amazon explicitly says no return is required.\n3. Verify the order/product shows the actual replacement stage and no return lifecycle. Refund must be `—`, and the order must not appear in Returns or Return review.\n4. Verify the Replacement status filter finds it.\n5. Verify a replacement that does not explicitly waive original-item return remains eligible for return processing rather than being suppressed.\n'''
write('TESTING.md', testing)

newchat = read('NEW_CHAT_PROMPT.md')
newchat += '''\n\n### Replacement workflow rule\nTreat replacement and return as independent product workflows. Only suppress a replacement-management return-status link when product-scoped Amazon evidence explicitly proves no return is required. Otherwise retain normal return eligibility. Replacement-only orders are not refunds and must not display `$0.00` as a refund placeholder.\n'''
write('NEW_CHAT_PROMPT.md', newchat)

print('v0.18.11 patch applied')
