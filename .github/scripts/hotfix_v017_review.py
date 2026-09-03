from pathlib import Path


def patch(path, old, new, label):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'missing anchor: {label}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# Payment last-four must come from locally scoped payment evidence when parsing a DOM document.
patch(
    'parser.js',
    "  function extractPaymentEvidenceText(container) {\n    if (!container?.querySelectorAll) return '';",
    "  function extractPaymentEvidenceText(container) {\n    if (!container) return '';",
    'payment evidence body support'
)
patch(
    'parser.js',
    "    return chunks.join('\\n');\n  }\n\n  function extractOrderIds",
    "    if (!chunks.length) {\n      const lines = normalizeText(container.innerText || container.textContent || '').split('\\n').map(line => line.trim()).filter(Boolean);\n      for (let i = 0; i < lines.length; i += 1) {\n        if (!/payment\\s+(?:method|information)/i.test(lines[i])) continue;\n        add(lines.slice(i, i + 5).join(' '));\n      }\n    }\n    return chunks.join('\\n');\n  }\n\n  function extractOrderIds",
    'payment local-text fallback'
)
patch(
    'parser.js',
    "    const cardLast4 = findCardLast4(options.paymentText || text);",
    "    const cardLast4 = Object.prototype.hasOwnProperty.call(options, 'paymentText') ? findCardLast4(options.paymentText) : findCardLast4(text);",
    'explicit payment scope'
)
patch(
    'parser.js',
    "        paymentText: paymentEvidenceText || context,",
    "        paymentText: paymentEvidenceText,",
    'no whole-page payment fallback'
)

# A v0.16 -> v0.17 update must reset even though v0.16 did not yet persist VERSION_KEY.
patch(
    'background.js',
    "async function ensureDevelopmentVersionState() {\n  const version = chrome.runtime?.getManifest?.()?.version || null;\n  if (!version) return { changed: false, version: null };\n  const data = await chrome.storage.local.get([VERSION_KEY]);\n  const prior = data[VERSION_KEY] || null;",
    "async function ensureDevelopmentVersionState(previousVersionHint = null) {\n  const version = chrome.runtime?.getManifest?.()?.version || null;\n  if (!version) return { changed: false, version: null };\n  const data = await chrome.storage.local.get([VERSION_KEY]);\n  const prior = data[VERSION_KEY] || previousVersionHint || null;",
    'previous-version hint'
)
patch(
    'background.js',
    "chrome.runtime.onInstalled.addListener(() => { ensureDevelopmentVersionState().catch(() => {}); });",
    "chrome.runtime.onInstalled.addListener(details => { ensureDevelopmentVersionState(details?.previousVersion || null).catch(() => {}); });",
    'update event previousVersion'
)

# Regression: an unrelated brand/last-four elsewhere on a document is not payment evidence.
path = Path('parser-test.js')
text = path.read_text(encoding='utf-8')
needle = "assert(semanticPayment.cardLast4 === '4821', 'semantic payment evidence should capture card last four');\n"
addition = """assert(semanticPayment.cardLast4 === '4821', 'semantic payment evidence should capture card last four');
const unrelatedCardDoc = {
  title: 'Order Details',
  body: { innerText: 'Order placed Sep 2, 2026\\nOrder # 114-1234567-7654321\\nOrder Total: $19.99\\nExample item\\nQuantity: 1\\nOld receipt note: Visa ending in 4821', textContent: '' },
  querySelectorAll() { return []; },
  querySelector() { return null; }
};
const unrelatedCardParsed = p.parseDocument(unrelatedCardDoc, 'https://www.amazon.com/your-orders/order-details?orderID=114-1234567-7654321');
const unrelatedCardOrder = unrelatedCardParsed.records.find(record => record.recordType === 'order');
assert(unrelatedCardOrder.cardLast4 === null, 'document parsing must not accept last four outside payment-method evidence');
"""
if needle not in text:
    raise RuntimeError('parser payment regression anchor missing')
path.write_text(text.replace(needle, addition, 1), encoding='utf-8')

# Regression: upgrade previousVersion must reset even with no pre-existing VERSION_KEY.
path = Path('state-machine-test.js')
text = path.read_text(encoding='utf-8')
needle = "  assert(store.installedExtensionVersion === '0.17.0', 'version reset should store new manifest version');\n\n  console.log('strict crawl state-machine tests passed');"
replacement = """  assert(store.installedExtensionVersion === '0.17.0', 'version reset should store new manifest version');

  delete store.installedExtensionVersion;
  store.ledger = [{ recordId:'order:legacy', orderId:'113-1111111-1111111' }];
  store.backgroundScanState = { running:true };
  await sandbox.ensureDevelopmentVersionState('0.16.0');
  assert(store.ledger === undefined && store.backgroundScanState === undefined, 'upgrade previousVersion must wipe legacy state even before VERSION_KEY existed');
  assert(store.installedExtensionVersion === '0.17.0', 'legacy upgrade reset should persist v0.17 version key');

  console.log('strict crawl state-machine tests passed');"""
if needle not in text:
    raise RuntimeError('state-machine version regression anchor missing')
path.write_text(text.replace(needle, replacement, 1), encoding='utf-8')

# The release assertion must be durable in the committed candidate, not only modified in a CI workspace.
patch(
    'reconciliation-test.js',
    "manifest.version !== '0.16.0'",
    "manifest.version !== '0.17.0'",
    'reconciliation manifest version'
)

print('v0.17 review hardening applied')
