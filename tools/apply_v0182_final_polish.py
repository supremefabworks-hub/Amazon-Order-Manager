from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def write(p,t): (ROOT/p).write_text(t,encoding='utf-8')
def once(t,a,b,label):
    n=t.count(a)
    if n!=1: raise RuntimeError(f'{label}: expected 1, got {n}')
    return t.replace(a,b,1)

# Dashboard: null is unknown, never monetary zero; canonical refund and grouped amount math stay scoped.
d=read('dashboard.js')
d=once(d,
"  function money(value) { return Number.isFinite(Number(value)) ? `$${Number(value).toFixed(2)}` : '—'; }",
"  function money(value) { if (value === null || value === undefined || value === '') return '—'; return Number.isFinite(Number(value)) ? `$${Number(value).toFixed(2)}` : '—'; }",
'dashboard money null')
d=once(d,
'''      const groupValue = Number(r.returnGroupRefundAmount);
      const scopedValue = r.refundAmountScope === 'return' ? Number(r.refundAmount ?? r.refundSubtotal) : NaN;
      const value = Number.isFinite(groupValue) ? groupValue : scopedValue;''',
'''      const groupRaw = r.returnGroupRefundAmount;
      const scopedRaw = r.refundAmountScope === 'return' ? (r.refundAmount ?? r.refundSubtotal) : null;
      const groupValue = groupRaw === null || groupRaw === undefined || groupRaw === '' ? NaN : Number(groupRaw);
      const scopedValue = scopedRaw === null || scopedRaw === undefined || scopedRaw === '' ? NaN : Number(scopedRaw);
      const value = Number.isFinite(groupValue) ? groupValue : scopedValue;''',
'group amount null')
d=once(d,
'''      const value = Number(r.refundAmount ?? r.refundSubtotal);
      if (!Number.isFinite(value)) continue;''',
'''      const raw = r.refundAmount ?? r.refundSubtotal;
      const value = raw === null || raw === undefined || raw === '' ? NaN : Number(raw);
      if (!Number.isFinite(value)) continue;''',
'item amount null')
d=once(d,
'''    const legacy = ordered.map(r => Number(r.refundAmount ?? r.refundSubtotal)).find(Number.isFinite);''',
'''    const legacy = ordered.map(r => {
      const raw = r.refundAmount ?? r.refundSubtotal;
      return raw === null || raw === undefined || raw === '' ? NaN : Number(raw);
    }).find(Number.isFinite);''',
'legacy amount null')
d=once(d,
'''      const canonicalRefundTotal = Number.isFinite(Number(canonicalRefundCandidate)) ? Number(canonicalRefundCandidate) : null;''',
'''      const canonicalRefundTotal = canonicalRefundCandidate !== null && canonicalRefundCandidate !== undefined && canonicalRefundCandidate !== '' && Number.isFinite(Number(canonicalRefundCandidate))
        ? Number(canonicalRefundCandidate)
        : null;''',
'canonical null guard')
d=once(d,
'''  function needsReviewExpectedAmount(row) {
    return returnRecordAmountTotal((row.returns || []).filter(r => storage.needsCreditReview(r)));
  }''',
'''  function needsReviewExpectedAmount(row) {
    const recordTotal = returnRecordAmountTotal((row.returns || []).filter(r => storage.needsCreditReview(r)));
    if (row.refundAmountMismatch || row.itemIdentityConflict || row.groupAmountConflict) {
      const orderExpected = row.refundAmount;
      if (orderExpected !== null && orderExpected !== undefined && orderExpected !== '' && Number.isFinite(Number(orderExpected))) return Number(orderExpected);
    }
    return recordTotal;
  }''',
'needs review integrity total')
d=once(d,
'''      sourceExtensionVersion: '0.17.0',''',
'''      sourceExtensionVersion: chrome.runtime.getManifest()?.version || null,''',
'bank source version')
write('dashboard.js',d)

# Preserve the canonical Order Details item binding as a durable source of identity across matching scans.
s=read('storage.js')
start=s.index('  function trustedReturnIdentityShouldWin(existing, incoming) {')
end=s.index('  function mergeRecord(existing, incoming, scannedAt) {',start)
new_helper='''  function trustedReturnIdentityDecision(existing, incoming) {
    const none = { bound: false, preserve: false, conflict: false };
    if (existing?.recordType !== 'return' || incoming?.recordType !== 'return') return none;
    if (existing.itemIdentitySource !== 'order-detail-return-link') return none;
    if (!existing.returnItemId || !incoming.returnItemId || existing.returnItemId !== incoming.returnItemId) return none;

    const existingAsins = new Set((existing.asins || []).map(value => String(value || '').toUpperCase()).filter(Boolean));
    const incomingAsins = new Set((incoming.asins || []).map(value => String(value || '').toUpperCase()).filter(Boolean));
    const existingNames = new Set((existing.itemNames || []).map(value => String(value || '').trim().toLowerCase()).filter(Boolean));
    const incomingNames = new Set((incoming.itemNames || []).map(value => String(value || '').trim().toLowerCase()).filter(Boolean));

    if (incomingAsins.size) {
      for (const asin of existingAsins) if (incomingAsins.has(asin)) return { bound: true, preserve: false, conflict: false };
      if (existingAsins.size) return { bound: true, preserve: true, conflict: true };
    }
    if (incomingNames.size) {
      for (const name of existingNames) if (incomingNames.has(name)) return { bound: true, preserve: true, conflict: false };
      if (existingNames.size) return { bound: true, preserve: true, conflict: true };
    }
    return { bound: true, preserve: true, conflict: false };
  }

'''
s=s[:start]+new_helper+s[end:]
s=once(s,
'''    const preserveTrustedItemIdentity = trustedReturnIdentityShouldWin(existing, incoming);''',
'''    const trustedIdentity = trustedReturnIdentityDecision(existing, incoming);''',
'storage decision var')
s=once(s,
'''        if (preserveTrustedItemIdentity && ['itemNames', 'asins'].includes(key)) {''',
'''        if (trustedIdentity.preserve && ['itemNames', 'asins'].includes(key)) {''',
'storage preserve arrays')
s=once(s,
'''      else if (preserveTrustedItemIdentity && key === 'itemIdentitySource') merged[key] = existing.itemIdentitySource;''',
'''      else if (trustedIdentity.bound && key === 'itemIdentitySource') merged[key] = existing.itemIdentitySource;''',
'storage preserve source')
s=once(s,
'''    if (preserveTrustedItemIdentity) {
      merged.itemIdentityConflict = true;
      merged.itemIdentityConflictIncoming = {
        itemNames: mergeArray([], incoming.itemNames || []),
        asins: mergeArray([], incoming.asins || []),
        source: incoming.itemIdentitySource || null
      };
    }''',
'''    if (trustedIdentity.bound) merged.itemIdentitySource = existing.itemIdentitySource;
    if (trustedIdentity.conflict) {
      merged.itemIdentityConflict = true;
      merged.itemIdentityConflictIncoming = {
        itemNames: mergeArray([], incoming.itemNames || []),
        asins: mergeArray([], incoming.asins || []),
        source: incoming.itemIdentitySource || null
      };
    }''',
'storage conflict only')
write('storage.js',s)

# Extend storage regressions with matching/missing identity evidence that should not create false conflict.
st=read('storage-test.js')
needle="  assert(s.needsCreditReview(trustedMerged) === true, 'item identity conflicts must require review');\n\n  console.log('storage tests passed');"
replacement="""  assert(s.needsCreditReview(trustedMerged) === true, 'item identity conflicts must require review');

  const stableTrusted = {
    recordId: 'return:113-7000000-3000001:rma-stable:item-item-b', recordType: 'return', orderId: '113-7000000-3000001',
    returnToken: 'RMA-STABLE', returnItemId: 'item-b', itemNames: ['Stable Trusted Item'], asins: ['B000000011'],
    itemIdentitySource: 'order-detail-return-link', status: 'return_in_progress', returnStage: 'started', provisionalReturn: true
  };
  await s.upsertRecords([stableTrusted]);
  await s.upsertRecords([{ ...stableTrusted, asins: [], itemNames: ['Stable Trusted Item'], itemIdentitySource: 'return-page-item', authoritativeReturnCapture: true, provisionalReturn: false, status: 'refunded', returnStage: 'refund_issued' }]);
  const stableMerged = (await s.getLedger()).find(r => r.recordId === stableTrusted.recordId);
  assert(stableMerged.itemIdentitySource === 'order-detail-return-link', 'matching refresh must retain the trusted Order Details binding');
  assert(!stableMerged.itemIdentityConflict, 'missing ASIN with the same trusted title must not create a false identity conflict');

  console.log('storage tests passed');"""
st=once(st,needle,replacement,'storage matching identity regression')
write('storage-test.js',st)

# Give child return group amount/status a compact symmetric presentation.
css=read('ui.css')
append='''
/* v0.18.2 explicit multi-return child groups */
.return-track-meta { display:flex; align-items:baseline; justify-content:space-between; gap:8px; margin:1px 0 2px; min-width:0; font-size:8px; color:#59616b; }
.return-track-meta span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.return-track-meta strong { flex:0 0 auto; font-size:9px; color:#1f2328; }
'''
if '/* v0.18.2 explicit multi-return child groups */' not in css: css += append
write('ui.css',css)

# Strengthen UI invariants around unknown money, review totals, and dynamic bridge version.
ui=read('ui-test.js')
needle="assert(background.includes('returnItemId: link.returnItemId'), 'rendered per-order Refresh must pass exact return item identity to the worker scan');"
replacement="""assert(background.includes('returnItemId: link.returnItemId'), 'rendered per-order Refresh must pass exact return item identity to the worker scan');
assert(dashboard.includes("value === null || value === undefined || value === ''"), 'unknown money must render as unknown rather than $0.00');
assert(dashboard.includes('row.refundAmountMismatch || row.itemIdentityConflict || row.groupAmountConflict'), 'integrity-review orders must contribute their canonical expected refund to Needs Review totals');
assert(dashboard.includes('sourceExtensionVersion: chrome.runtime.getManifest()?.version'), 'bank bridge export must report the actual extension version');
assert(css.includes('v0.18.2 explicit multi-return child groups'), 'multi-return child status/amount metadata must have compact styling');"""
ui=once(ui,needle,replacement,'ui final invariants')
write('ui-test.js',ui)

print('v0.18.2 final polish applied')
