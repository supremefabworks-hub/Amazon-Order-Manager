from pathlib import Path

path = Path('parser-test.js')
text = path.read_text(encoding='utf-8')
old = """// v0.8: every history order gets a detail URL, even if one anchor is missing from the rendered DOM.\nconst twoOrderHistoryDoc = {\n  body: { innerText: 'Your Orders\\nOrder # 113-5152372-1721051\\nOrder # 114-1111111-2222222', textContent: '' },\n  querySelectorAll(selector) { return selector === 'a[href]' ? [currentDetailAnchor] : []; },\n  querySelector() { return null; }\n};\nconst everyDetail = p.extractOrderDetailLinks(twoOrderHistoryDoc, 'https://www.amazon.com/your-orders/orders?orderFilter=year-2026');\nassert(everyDetail.length === 2, 'every Order ID on history must produce one detail link');\nconst fallbackDetail = everyDetail.find(x => x.orderId === '114-1111111-2222222');\nassert(fallbackDetail && fallbackDetail.url === 'https://www.amazon.com/your-orders/order-details?orderID=114-1111111-2222222', 'missing detail anchor should use current Amazon detail route');\nconsole.log('mandatory order-detail tests passed');\n"""
new = """// v0.17: visible orders and canonical detail links are tracked independently.\n// Missing anchors are a crawler stop condition, never permission to invent a canonical URL.\nconst twoOrderHistoryDoc = {\n  body: { innerText: 'Your Orders\\nOrder # 113-5152372-1721051\\nOrder # 114-1111111-2222222', textContent: '' },\n  querySelectorAll(selector) { return selector === 'a[href]' ? [currentDetailAnchor] : []; },\n  querySelector() { return null; }\n};\nconst everyDetail = p.extractOrderDetailLinks(twoOrderHistoryDoc, 'https://www.amazon.com/your-orders/orders?orderFilter=year-2026');\nassert(everyDetail.length === 1, 'only real rendered View order details links may become canonical detail links');\nassert(!everyDetail.some(x => x.orderId === '114-1111111-2222222'), 'missing detail anchor must not synthesize a canonical URL');\nconst twoOrderParsed = p.parseDocument(twoOrderHistoryDoc, 'https://www.amazon.com/your-orders/orders?orderFilter=year-2026');\nassert(twoOrderParsed.historyOrderIds.length === 2, 'all visible Order IDs must remain in the history fingerprint');\nconsole.log('mandatory order-detail tests passed');\n"""
if old not in text:
    raise RuntimeError('legacy mandatory-detail fixture not found')
text = text.replace(old, new, 1)
text = text.replace(
    "Order Total: $456.78\\nPayment Method\\nAmazon Business Card ending in 4321\\nExample primary item\\nRelated order 114-9999999-8888888",
    "Order Total: $456.78\\nPayment Method\\nAmazon Business Card ending in 4321\\nExample primary item\\nQuantity: 1\\nRelated order 114-9999999-8888888",
    1
)
path.write_text(text, encoding='utf-8')

recon_path = Path('reconciliation-test.js')
recon = recon_path.read_text(encoding='utf-8')
if "manifest.version !== '0.16.0'" not in recon:
    raise RuntimeError('reconciliation manifest-version assertion not found')
recon = recon.replace("manifest.version !== '0.16.0'", "manifest.version !== '0.17.0'", 1)
recon_path.write_text(recon, encoding='utf-8')

print('v0.17 legacy/release test expectations updated')
