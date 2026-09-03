from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path): return (ROOT/path).read_text(encoding='utf-8')
def write(path,text): (ROOT/path).write_text(text,encoding='utf-8')
def once(text,old,new,label):
    count=text.count(old)
    if count!=1: raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old,new,1)

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
'''    findRefundAmount,
    findCardLast4,''',
'''    findRefundAmount,
    findOrderRefundTotal,
    findCardLast4,''',
'parser export canonical refund')
write('parser.js',p)

# Add functional canonical refund regressions to parser-test.
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
assert(p.findOrderRefundTotal('Order Total $262.86\nRefund Total $185.46') === 185.46, 'canonical Refund Total helper must parse the explicit label');

const proseRefundDoc = {
  title: 'Order Details',
  body: { innerText: `Order placed September 1, 2026\nOrder # 113-5152372-1721053\nOrder Total: $100.00\nExample returned item\nQuantity: 1\nYour refund has been issued $88.00`, textContent: '' },
  querySelectorAll() { return []; }, querySelector() { return null; }
};
const proseRefundParsed = p.parseDocument(proseRefundDoc, 'https://www.amazon.com/your-orders/order-details?orderID=113-5152372-1721053');
const proseRefundOrder = proseRefundParsed.records.find(x => x.recordType === 'order');
assert(proseRefundOrder.refundAmount === 88, 'generic refund parser should still retain lifecycle refund evidence where applicable');
assert(proseRefundOrder.canonicalRefundTotal == null, 'refund lifecycle prose must not become canonical Order Details Refund Total');
assert(p.findOrderRefundTotal('Your refund has been issued $88.00') === null, 'canonical helper must reject refund lifecycle prose');
console.log('authoritative detail-page tests passed');"""
t=once(t,needle,replacement,'parser canonical refund regression')
write('parser-test.js',t)

# The dashboard/popup must never fall back from canonical Refund Total to generic order refund prose.
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

# Remove unsupported PowerShell 7 null-coalescing syntax from Windows PowerShell 5.1 installer.
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
"assert(dashboard.includes('canonicalRefundTotal'), 'dashboard must prefer canonical Order Details Refund Total');\nassert(!dashboard.includes('order?.detailScanComplete ? order?.refundAmount'), 'dashboard must never use generic order refund prose as canonical Refund Total');",
'UI canonical-only regression')
write('ui-test.js',ui)

print('v0.18.2 review hardening applied')
