const fs = require('fs');
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
