from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path): return (ROOT/path).read_text(encoding='utf-8')
def write(path,text): (ROOT/path).write_text(text,encoding='utf-8')
def once(text,old,new,label):
    count=text.count(old)
    if count!=1: raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old,new,1)

# ---------------- canonical order refund + trust source ----------------
p=read('parser.js')
anchor='''  function findRefundAmount(text) {
    const direct = findLabeledMoney(text, [
      'Total refund', 'Total estimated refund*', 'Total estimated refund', 'Estimated refund', 'Refund amount', 'Refund total', 'Refund subtotal'
    ]);'''
if anchor not in p: raise RuntimeError('findRefundAmount anchor missing')
p=p.replace('  function findRefundAmount(text) {', '''  function findOrderRefundTotal(text) {
    // Canonical order-level refund money comes only from a standalone Amazon Order Details
    // "Refund Total" label. Generic refund lifecycle prose must never become this field.
    const normalized = normalizeText(text);
    const match = normalized.match(/(?:^|\\n)\\s*Refund Total\\s*:?\\s*\\$\\s*([0-9,]+(?:\\.\\d{2})?)\\s*(?:$|\\n)/im);
    if (!match) return null;
    const value = Number(match[1].replace(/,/g, ''));
    return Number.isFinite(value) ? value : null;
  }

  function findRefundAmount(text) {''',1)
p=once(p,
'''        record.canonicalRefundTotal = Number.isFinite(Number(record.refundAmount)) ? Number(record.refundAmount) : null;''',
'''        const canonicalRefundTotal = findOrderRefundTotal(context);
        record.canonicalRefundTotal = canonicalRefundTotal != null && Number.isFinite(Number(canonicalRefundTotal)) ? Number(canonicalRefundTotal) : null;''',
'canonical refund assignment')
p=once(p,
'''        itemIdentitySource: (evidence.itemNames.length || evidence.asins.length) ? 'order-detail-return-link' : null''',
'''        itemIdentitySource: (evidence.itemNames.length || evidence.asins.length)
          ? (isOrderDetailPage(baseUrl) ? 'order-detail-return-link' : 'return-link')
          : null''',
'only Order Details gets trusted return-link identity')
p=once(p,
'''    findRefundAmount,
    findCardLast4,''',
'''    findRefundAmount,
    findOrderRefundTotal,
    findCardLast4,''',
'parser export canonical refund')
write('parser.js',p)

# ---------------- parser regressions ----------------
t=read('parser-test.js')
needle="assert(!detailWithRelated.records.some(x => x.orderId === '114-9999999-8888888'), 'related order IDs should not become records on a targeted detail page');\nconsole.log('authoritative detail-page tests passed');"
replacement="""assert(!detailWithRelated.records.some(x => x.orderId === '114-9999999-8888888'), 'related order IDs should not become records on a targeted detail page');

const canonicalRefundDoc = {
  title: 'Order Details',
  body: { innerText: `Order placed September 1, 2026\nOrder # 113-5152372-1721052\nOrder Total: $262.86\nRefund Total $185.46\nExample returned item\nQuantity: 1`, textContent: '' },
  querySelectorAll() { return []; }, querySelector() { return null; }
};
const canonicalRefundParsed = p.parseDocument(canonicalRefundDoc, 'https://www.amazon.com/your-orders/order-details?orderID=113-5152372-1721052');
const canonicalRefundOrder = canonicalRefundParsed.records.find(x => x.recordType === 'order');
assert(canonicalRefundOrder.canonicalRefundTotal === 185.46, 'Order Details Refund Total must become the canonical order-level refund total');
assert(p.findOrderRefundTotal(`Order Total $262.86\nRefund Total $185.46`) === 185.46, 'canonical Refund Total helper must parse the explicit label');

const proseRefundDoc = {
  title: 'Order Details',
  body: { innerText: `Order placed September 1, 2026\nOrder # 113-5152372-1721053\nOrder Total: $100.00\nExample returned item\nQuantity: 1\nYour refund has been issued $88.00`, textContent: '' },
  querySelectorAll() { return []; }, querySelector() { return null; }
};
const proseRefundParsed = p.parseDocument(proseRefundDoc, 'https://www.amazon.com/your-orders/order-details?orderID=113-5152372-1721053');
const proseRefundOrder = proseRefundParsed.records.find(x => x.recordType === 'order');
assert(proseRefundOrder.refundAmount === 88, 'generic refund parser should still retain lifecycle refund evidence where applicable');
assert(proseRefundOrder.canonicalRefundTotal == null, 'refund lifecycle prose must not become canonical Order Details Refund Total');
assert(p.findOrderRefundTotal(`Your refund has been issued $88.00`) === null, 'canonical helper must reject refund lifecycle prose');
console.log('authoritative detail-page tests passed');"""
t=once(t,needle,replacement,'parser canonical refund regression')
write('parser-test.js',t)

# ---------------- canonical refund display ----------------
d=read('dashboard.js')
d=once(d,
'''      const canonicalRefundCandidate = order?.canonicalRefundTotal ?? (order?.detailScanComplete ? order?.refundAmount : null);''',
'''      const canonicalRefundCandidate = order?.canonicalRefundTotal;''',
'dashboard canonical-only refund')
write('dashboard.js',d)

pj=read('popup.js')
pj=once(pj,
'''        const canonical = Number(order?.canonicalRefundTotal ?? (order?.detailScanComplete ? order?.refundAmount : null));
        returnTotal += Number.isFinite(canonical) ? canonical : refundTotal(rs);''',
'''        const canonicalRaw = order?.canonicalRefundTotal;
        const canonical = canonicalRaw == null ? NaN : Number(canonicalRaw);
        returnTotal += Number.isFinite(canonical) ? canonical : refundTotal(rs);''',
'popup canonical-only refund')
write('popup.js',pj)

# ---------------- stable return identity across return-page redirects ----------------
c=read('content.js')
helper='''
  function applySingleReturnIdentityHint(records, hint) {
    const list = Array.isArray(records) ? records.slice() : [];
    const authoritative = list.filter(record => record?.recordType === 'return' && record?.authoritativeReturnCapture);
    if (authoritative.length !== 1 || !hint?.returnItemId) return list;
    const target = authoritative[0];
    const enriched = {
      ...target,
      returnToken: hint.returnToken || target.returnToken || null,
      returnItemId: hint.returnItemId,
      returnContractId: hint.returnContractId || target.returnContractId || null,
      returnRmaId: hint.returnRmaId || target.returnRmaId || null
    };
    enriched.recordId = parser.makeRecordId(enriched);
    return list.map(record => record === target ? enriched : record);
  }

'''
marker='  async function announceDiscovery(result) {'
if marker not in c: raise RuntimeError('content announce marker missing')
c=c.replace(marker,helper+marker,1)

c=once(c,
'''        return scanPage({ force: true, notify: false, discover: false, reportChange: false });''',
'''        const scanned = await scanPage({ force: true, notify: false, discover: false, reportChange: false });
        if (message.job?.type === 'return' && scanned?.ok) {
          const stabilizedRecords = applySingleReturnIdentityHint(scanned.records || [], message.job);
          if (stabilizedRecords.some((record, index) => record?.recordId !== scanned.records?.[index]?.recordId)) {
            const stabilizedReturns = stabilizedRecords.filter(record => record?.recordType === 'return' && record?.authoritativeReturnCapture);
            const stabilizedSave = stabilizedReturns.length ? await storage.upsertRecords(stabilizedReturns) : scanned.save;
            return { ...scanned, records: stabilizedRecords, save: stabilizedSave };
          }
        }
        return scanned;''',
'worker rendered return identity stabilization')

c=once(c,
'''            const returnRecords = (returnParsed.records || []).filter(record => record?.recordType === 'return' && record?.orderId === orderId && record?.authoritativeReturnCapture);
            if (!returnRecords.length) return { ok: false, error: `Return status for ${orderId} did not contain an authoritative return record.` };
            const returnSave = await storage.upsertRecords(returnRecords);''',
'''            let returnRecords = (returnParsed.records || []).filter(record => record?.recordType === 'return' && record?.orderId === orderId && record?.authoritativeReturnCapture);
            returnRecords = applySingleReturnIdentityHint(returnRecords, link).filter(record => record?.recordType === 'return' && record?.authoritativeReturnCapture);
            if (!returnRecords.length) return { ok: false, error: `Return status for ${orderId} did not contain an authoritative return record.` };
            const returnSave = await storage.upsertRecords(returnRecords);''',
'authenticated return fetch identity stabilization')
write('content.js',c)

b=read('background.js')
b=once(b,
'''      const returnResult = await scanWorkerTab(tabId, { type: 'return', manualRefresh: true, orderId: id, url: link.url });''',
'''      const returnResult = await scanWorkerTab(tabId, {
        type: 'return', manualRefresh: true, orderId: id, url: link.url,
        returnToken: link.returnToken || null,
        returnItemId: link.returnItemId || null,
        returnContractId: link.returnContractId || null,
        returnRmaId: link.returnRmaId || null
      });''',
'manual rendered return identity hint')
write('background.js',b)

# ---------------- Windows PowerShell 5.1 diagnostics ----------------
ins=read('tools/dev-updater/Install.ps1')
ins=once(ins,
'''    Write-Host "Registry manifest: $($registered ?? '(missing)')"''',
'''    $registeredDisplay = '(missing)'
    if ($null -ne $registered -and -not [string]::IsNullOrWhiteSpace([string]$registered)) { $registeredDisplay = [string]$registered }
    Write-Host "Registry manifest: $registeredDisplay"''',
'PowerShell 5.1 registry display')
write('tools/dev-updater/Install.ps1',ins)

u=read('updater-reliability-test.js')
u=once(u,
"assert(installer.includes('DiagnoseOnly') && installer.includes('Show-Diagnostics'), 'installer must expose a diagnostics-only mode');",
"assert(installer.includes('DiagnoseOnly') && installer.includes('Show-Diagnostics'), 'installer must expose a diagnostics-only mode');\nassert(!installer.includes('??'), 'Windows PowerShell 5.1 installer must not use the PowerShell 7 null-coalescing operator');",
'PowerShell regression')
write('updater-reliability-test.js',u)

ui=read('ui-test.js')
ui=once(ui,
"assert(dashboard.includes('canonicalRefundTotal'), 'dashboard must prefer canonical Order Details Refund Total');",
"assert(dashboard.includes('canonicalRefundTotal'), 'dashboard must prefer canonical Order Details Refund Total');\nassert(!dashboard.includes('order?.detailScanComplete ? order?.refundAmount'), 'dashboard must never use generic order refund prose as canonical Refund Total');\nassert(content.includes('applySingleReturnIdentityHint'), 'return-page refresh must preserve exact Order Details itemId identity across redirects');\nassert(background.includes('returnItemId: link.returnItemId'), 'rendered per-order Refresh must pass exact return item identity to the worker scan');",
'UI/refresh identity regression')
write('ui-test.js',ui)

print('v0.18.2 review hardening applied')
