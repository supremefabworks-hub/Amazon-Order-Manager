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

def regex_once(text, pattern, replacement, label):
    out, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 regex match, got {count}')
    return out

# Version bump.
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.3'
manifest['version_name'] = '0.18.3'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
package = json.loads(read('package.json'))
package['version'] = '0.18.3'
write('package.json', json.dumps(package, indent=2) + '\n')

# Parser: accept Amazon's captured legacy Order Details route, but never synthesize one.
p = read('parser.js')
p = once(
    p,
    "  function isOrderDetailPage(url) {\n    return /(?:order-details|orderdetails|order-detail)/i.test(String(url || ''));\n  }",
    "  function isOrderDetailPage(url) {\n    return /(?:order-details|orderdetails|order-detail|\\/gp\\/css\\/summary\\/edit\\.html(?:[/?#]|$))/i.test(String(url || ''));\n  }",
    'parser legacy detail page classifier'
)
p = once(
    p,
    "      const looksLikeDetailHref = /(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|order-details|orderdetails|order-detail)/i.test(href);",
    "      const looksLikeDetailHref = /(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|\\/gp\\/css\\/summary\\/edit\\.html|order-details|orderdetails|order-detail)/i.test(href);",
    'parser legacy href discovery'
)
p = once(
    p,
    "      try { actualDetailPath = /(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details)(?:[/?#]|$)/i.test(new URL(url).pathname); } catch (_) {}",
    "      try { actualDetailPath = /(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|\\/gp\\/css\\/summary\\/edit\\.html)(?:[/?#]|$)/i.test(new URL(url).pathname); } catch (_) {}",
    'parser legacy actual detail path'
)

# Status text must agree with the evidence-based return stage. Bare timeline labels are UI labels,
# not affirmative lifecycle evidence.
status_fn = r'''  function extractStatusText(text) {
    const normalized = normalizeText(text);
    const lines = normalized.split('\n').map(s => s.trim()).filter(Boolean);
    if (!lines.length) return null;

    const stage = parseReturnMilestones(normalized).stage;
    const stagePatterns = {
      credited: [
        /(?:your refund (?:has been|was) credited|we (?:have )?credited your refund|refund (?:has been|was) credited to|credited to your (?:original )?payment method on)/i
      ],
      refund_issued: [
        /(?:we (?:have )?issued your refund|your refund (?:has been|was) issued|refund has been issued|refund issued\s+(?:on|\$))/i
      ],
      received: [
        /(?:we (?:have )?received your return|return (?:has been )?received|received your return|item received|return processed|your return is complete|return complete)/i
      ],
      shipped: [
        /(?:dropped off|drop-?off complete|return (?:is )?in transit|on the way back|return shipped|shipped back|carrier received)/i
      ],
      started: [
        /(?:return request|return initiated|return started|accepted your return|return code|return summary|refund will be issued|estimated refund)/i
      ]
    };

    for (const pattern of stagePatterns[stage] || []) {
      const line = lines.find(candidate => pattern.test(candidate));
      if (line) return line.slice(0, 500);
    }

    // Normal purchase/delivery rows still need useful order status text, but static return
    // timeline labels such as a bare "Refund issued" are deliberately excluded here.
    for (const line of lines) {
      if (/^(?:refund issued|refund credited|credited|initiated|dropped off|credit pending)$/i.test(line)) continue;
      if (/(?:delivered|arriving|shipped)/i.test(line) && !/(?:refund issued|refund credited)/i.test(line)) return line.slice(0, 500);
    }
    return null;
  }
'''
p = regex_once(
    p,
    r"  function extractStatusText\(text\) \{.*?\n  \}\n\n  function parseTextRecord",
    status_fn + "\n  function parseTextRecord",
    'evidence-aware status text'
)
write('parser.js', p)

# Storage: the stable Amazon returnItemId is the binding. Title/description variation alone is not
# a conflict. Contradictory non-empty ASIN evidence remains a conflict.
s = read('storage.js')
identity_fn = r'''  function trustedReturnIdentityDecision(existing, incoming) {
    const none = { bound: false, preserveNames: false, preserveAsins: false, conflict: false };
    if (existing?.recordType !== 'return' || incoming?.recordType !== 'return') return none;
    if (existing.itemIdentitySource !== 'order-detail-return-link') return none;
    if (!existing.returnItemId || !incoming.returnItemId || existing.returnItemId !== incoming.returnItemId) return none;

    const existingAsins = new Set((existing.asins || []).map(value => String(value || '').toUpperCase()).filter(Boolean));
    const incomingAsins = new Set((incoming.asins || []).map(value => String(value || '').toUpperCase()).filter(Boolean));
    let asinConflict = false;
    if (existingAsins.size && incomingAsins.size) {
      let overlap = false;
      for (const asin of existingAsins) if (incomingAsins.has(asin)) overlap = true;
      asinConflict = !overlap;
    }

    return {
      bound: true,
      preserveNames: true,
      preserveAsins: existingAsins.size > 0,
      conflict: asinConflict
    };
  }
'''
s = regex_once(
    s,
    r"  function trustedReturnIdentityDecision\(existing, incoming\) \{.*?\n  \}\n\n  function mergeRecord",
    identity_fn + "\n  function mergeRecord",
    'same-item identity decision'
)
s = once(
    s,
    "        if (trustedIdentity.preserve && ['itemNames', 'asins'].includes(key)) {\n          merged[key] = mergeArray([], existing?.[key] || []);",
    "        if ((key === 'itemNames' && trustedIdentity.preserveNames) || (key === 'asins' && trustedIdentity.preserveAsins)) {\n          merged[key] = mergeArray([], existing?.[key] || []);",
    'separate trusted name/asin preservation'
)
write('storage.js', s)

# Accept the captured legacy detail route through every runtime validator.
legacy_old = r'(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|order-details)'
legacy_new = r'(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details)'
for path in ['background.js', 'content.js', 'dashboard.js']:
    text = read(path)
    count = text.count(legacy_old)
    if count < 1:
        raise RuntimeError(f'{path}: no detail validator matches found')
    text = text.replace(legacy_old, legacy_new)
    write(path, text)

# Better missing-link diagnostics: preserve strict stop, but tell us exactly which Amazon IDs lack
# a real captured detail href.
b = read('background.js')
b = once(
    b,
    "  if (missingDetailUrls.length) throw new Error(`Missing real View order details URL for ${missingDetailUrls.length} order(s) on ${year} page ${page}. The crawler stopped rather than inventing canonical URLs.`);",
    "  if (missingDetailUrls.length) throw new Error(`Missing real View order details URL for ${missingDetailUrls.length} order(s) on ${year} page ${page}: ${missingDetailUrls.join(', ')}. The crawler stopped rather than inventing canonical URLs.`);",
    'missing detail id diagnostics'
)
write('background.js', b)

# Dashboard: use trusted Order Details return-link identity for display, so verbose/ambiguous return
# page text cannot duplicate product titles or append the Order ID into each child block.
d = read('dashboard.js')
d = once(
    d,
    "      const amountState = returnGroupAmount(groupRecords);\n      return {",
    "      const amountState = returnGroupAmount(groupRecords);\n      const trustedIdentityRecords = groupRecords.filter(r => r.itemIdentitySource === 'order-detail-return-link' && ((r.itemNames || []).length || (r.asins || []).length));\n      const identityRecords = trustedIdentityRecords.length ? trustedIdentityRecords : groupRecords;\n      return {",
    'trusted return group display identity'
)
d = once(
    d,
    "        itemNames: uniqueStrings(groupRecords.flatMap(r => r.itemNames || [])),\n        asins: uniqueStrings(groupRecords.flatMap(r => r.asins || [])),",
    "        itemNames: uniqueStrings(identityRecords.flatMap(r => r.itemNames || [])),\n        asins: uniqueStrings(identityRecords.flatMap(r => r.asins || [])),",
    'return group identity source'
)
d = once(
    d,
    "      const returnedItemNames = uniqueStrings(returnRecords.flatMap(r => r.itemNames || []));",
    "      const returnedItemNames = uniqueStrings(returnGroups.flatMap(group => group.itemNames || []));",
    'top row trusted return item names'
)
d = d.replace("statusLabel = 'Return item needs review';", "statusLabel = 'Item needs review';")
write('dashboard.js', d)

# Long badges must wrap inside the fixed status column rather than overlap the Order ID column.
css = read('ui.css')
css_rule = "\n/* v0.18.3 status badges stay inside their fixed ledger column. */\n.line-status .badge { max-width: 100%; white-space: normal; overflow-wrap: anywhere; line-height: 1.15; text-align: left; }\n"
if css_rule.strip() not in css:
    css += css_rule
write('ui.css', css)

# Parser regressions.
t = read('parser-test.js')
append = r'''

// v0.18.3 live acceptance regressions
assert(p.isOrderDetailPage('https://www.amazon.com/gp/css/summary/edit.html?orderID=113-1234567-7654321') === true, 'captured legacy /gp/css/summary/edit.html must be recognized as an Order Details page');
const legacyDetailAnchor = {
  innerText: 'View order details', textContent: 'View order details', parentElement: null,
  href: 'https://www.amazon.com/gp/css/summary/edit.html?orderID=113-1234567-7654321',
  getAttribute(name) { return name === 'href' ? '/gp/css/summary/edit.html?orderID=113-1234567-7654321' : null; }
};
const legacyDetailDoc = {
  body: { innerText: 'Order # 113-1234567-7654321', textContent: '' },
  querySelectorAll(selector) { return selector === 'a[href]' ? [legacyDetailAnchor] : []; },
  querySelector() { return null; }
};
const legacyLinks = p.extractOrderDetailLinks(legacyDetailDoc, 'https://www.amazon.com/gp/your-account/order-history');
assert(legacyLinks.length === 1 && legacyLinks[0].orderId === '113-1234567-7654321', 'real captured legacy Order Details href must be preserved');
assert(legacyLinks[0].url.includes('/gp/css/summary/edit.html'), 'legacy detail discovery must preserve Amazon supplied href');

const staticRefundTimeline = p.parseTextRecord('Return started\nInitiated\nDropped off\nRefund issued\nCredit pending', '113-2222222-3333333', { pageType: 'return', forceRecordType: 'return' });
assert(staticRefundTimeline.returnStage !== 'refund_issued', 'bare Refund issued timeline label must not promote lifecycle');
assert(!/refund issued/i.test(staticRefundTimeline.statusText || ''), 'bare Refund issued timeline label must not leak into affirmative status text');
const affirmativeRefund = p.parseTextRecord('Return complete\nYour refund has been issued.\nRefund issued', '113-2222222-3333334', { pageType: 'return', forceRecordType: 'return' });
assert(affirmativeRefund.returnStage === 'refund_issued', 'affirmative refund-issued sentence must still promote lifecycle');
assert(/refund has been issued/i.test(affirmativeRefund.statusText || ''), 'affirmative refund-issued sentence must remain visible status evidence');
console.log('v0.18.3 parser live regressions passed');
'''
if 'v0.18.3 parser live regressions passed' not in t:
    t += append
write('parser-test.js', t)

# Storage regressions for title-only variation vs contradictory ASIN.
st = read('storage-test.js')
needle = "  console.log('storage tests passed');"
storage_tests = r'''

  const trustedTitleBase = {
    recordId: 'return:113-7777777-8888888:rma-title:item-item-1', recordType: 'return', orderId: '113-7777777-8888888',
    returnToken: 'RMA-TITLE', returnItemId: 'ITEM-1', itemNames: ['RAMPOW Micro USB Cable 2 Pack 3.3ft'], asins: [],
    itemIdentitySource: 'order-detail-return-link', provisionalReturn: true, authoritativeReturnCapture: false,
    status: 'return_in_progress', returnStage: 'started'
  };
  await s.upsertRecords([trustedTitleBase]);
  await s.upsertRecords([{ ...trustedTitleBase,
    itemNames: ['RAMPOW Micro USB Cable 2 Pack 3.3FT, USB-A to Micro USB Fast Charging Cable & Data Sync Cord'],
    itemIdentitySource: 'return-page-item', provisionalReturn: false, authoritativeReturnCapture: true
  }]);
  const titleVariation = (await s.getLedger()).find(r => r.recordId === trustedTitleBase.recordId);
  assert(titleVariation.itemIdentityConflict !== true, 'same returnItemId title variation without contradictory ASIN must not become an item conflict');
  assert(titleVariation.itemNames.length === 1 && titleVariation.itemNames[0] === trustedTitleBase.itemNames[0], 'trusted Order Details item title must remain the display identity');

  const asinConflictBase = { ...trustedTitleBase,
    recordId: 'return:113-7777777-8888889:rma-asin:item-item-2', orderId: '113-7777777-8888889', returnToken: 'RMA-ASIN', returnItemId: 'ITEM-2',
    itemNames: ['Trusted Product'], asins: ['B000000001']
  };
  await s.upsertRecords([asinConflictBase]);
  await s.upsertRecords([{ ...asinConflictBase, asins: ['B000000002'], itemNames: ['Different Product'], itemIdentitySource: 'return-page-item', provisionalReturn: false, authoritativeReturnCapture: true }]);
  const asinConflict = (await s.getLedger()).find(r => r.recordId === asinConflictBase.recordId);
  assert(asinConflict.itemIdentityConflict === true, 'contradictory non-empty ASIN evidence for the same returnItemId must remain reviewable');
'''
if 'same returnItemId title variation' not in st:
    st = once(st, needle, storage_tests + '\n' + needle, 'storage live regressions')
write('storage-test.js', st)

# Source-level runtime/UI regressions.
u = read('ui-test.js')
ui_append = r'''
assert(background.includes('gp\\/css\\/summary\\/edit\\.html'), 'background canonical validator must accept captured legacy Order Details route');
assert(content.includes('gp\\/css\\/summary\\/edit\\.html'), 'content detail fetch validator must accept captured legacy Order Details route');
assert(dashboard.includes('gp\\/css\\/summary\\/edit\\.html'), 'dashboard Details action must accept captured legacy Order Details route');
assert(background.includes("missingDetailUrls.join(', ')"), 'missing-detail hard stop must identify the exact missing Order IDs');
assert(dashboard.includes("itemIdentitySource === 'order-detail-return-link'"), 'return group display must prefer trusted Order Details identity');
assert(css.includes('.line-status .badge') && css.includes('white-space: normal'), 'long status badges must wrap instead of overlapping the order column');
'''
if 'missing-detail hard stop must identify' not in u:
    u = u.replace("console.log('ui regression tests passed');", ui_append + "\nconsole.log('ui regression tests passed');")
write('ui-test.js', u)

# Durable docs/handoff.
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.2 after PR #16 merges.**', '**Current source baseline: v0.18.3 candidate for Issue #17.**', 1)
section = '''\n## v0.18.3 live acceptance hardening\n\nv0.18.3 addresses live Amazon Business findings after v0.18.2: captured legacy `/gp/css/summary/edit.html?orderID=...` links are accepted as real canonical Order Details routes; strict missing-link failures now name the exact Order ID(s); same-`itemId` title variation no longer creates false item conflicts unless non-empty ASIN evidence contradicts; dashboard return-group identity prefers the exact Order Details return-link binding; and bare static `Refund issued` timeline labels cannot appear as affirmative refund-issued status text. Long status badges wrap within the fixed column.\n\nThis release is also the unattended updater proof from repaired v0.18.2. Do not manually replace `current` or press Reload when `dev-v0.18.3` publishes.\n\n'''
marker = '## v0.18.2 multi-return model\n'
if '## v0.18.3 live acceptance hardening' not in readme and marker in readme:
    readme = readme.replace(marker, section + marker, 1)
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
handoff = handoff.replace('**Current source baseline: v0.18.2 after PR #16 merges.**', '**Current source baseline: v0.18.3 candidate for Issue #17.**', 1)
handoff_section = '''\n## v0.18.3 live acceptance fixes\n\nIssue #17 captures the next live defects from v0.18.2. The strict crawler now accepts Amazon-supplied legacy `/gp/css/summary/edit.html?orderID=...` as a real detail route while continuing to forbid synthesized URLs; a genuine missing link names its exact Order ID. Return identity uses stable `returnItemId` as the binding, preserves exact Order Details titles, and only flags identity conflict for contradictory non-empty ASIN evidence. Dashboard child-return item text is sourced from trusted Order Details bindings when available. `extractStatusText` is now stage-aware, so static `Refund issued` timeline labels cannot advertise a refund milestone that `parseReturnMilestones` has not affirmatively proven. Badge wrapping prevents long review labels from overlapping the order column.\n\nv0.18.3 must be used to prove unattended update from repaired v0.18.2; no manual extension reload/replacement is allowed for that acceptance.\n\n'''
marker = '## v0.18.2 live multi-return + updater reliability release\n'
if '## v0.18.3 live acceptance fixes' not in handoff and marker in handoff:
    handoff = handoff.replace(marker, handoff_section + marker, 1)
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
testing = testing.replace('**v0.18.2** is the current source baseline after PR #16 release merge.', '**v0.18.3** is the current live-fix target for Issue #17.', 1)
if '### v0.18.3 focused live checks' not in testing:
    testing += '''\n\n### v0.18.3 focused live checks\n\n- Resume the 2026 crawl at the page-6 boundary. A captured `/gp/css/summary/edit.html?orderID=...` detail link must be processed; if a link is truly absent, the stop message must name the exact Order ID.\n- Same-return verbose title differences with the same `itemId` must not produce `Item needs review` unless non-empty ASIN evidence contradicts.\n- A bare static `Refund issued` timeline label must not make the order/return status say Refund issued; affirmative Amazon issuance prose must still do so.\n- Long review/status badges must wrap without overlapping the Order ID.\n- Leave v0.18.2 installed and do not manually reload/replace it after `dev-v0.18.3` publishes; confirm Chrome advances to v0.18.3 through the native updater.\n'''
write('TESTING.md', testing)

newchat = read('NEW_CHAT_PROMPT.md')
newchat = newchat.replace('The complete root source baseline is **v0.18.2 after PR #16 merges**.', 'The complete root source baseline is **v0.18.3 candidate for Issue #17**.', 1)
if '## v0.18.3 live acceptance additions' not in newchat:
    marker = '## v0.18.2 durable additions\n'
    addition = '''## v0.18.3 live acceptance additions\n\nAccept captured Amazon legacy `/gp/css/summary/edit.html?orderID=...` as a real Order Details route, but never synthesize one. Missing-link stops must name the exact Order ID. Stable `returnItemId` binds a returned item; title variation alone is not a conflict, while contradictory non-empty ASIN evidence remains reviewable. Prefer trusted Order Details return-link item identity in the dashboard. Bare static `Refund issued` timeline labels are not affirmative status evidence. v0.18.3 is the unattended updater proof from repaired v0.18.2.\n\n'''
    if marker in newchat:
        newchat = newchat.replace(marker, addition + marker, 1)
write('NEW_CHAT_PROMPT.md', newchat)

print('v0.18.3 live acceptance patch applied')
