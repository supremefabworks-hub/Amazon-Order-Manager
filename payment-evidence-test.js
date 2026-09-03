const fs = require('fs');
const vm = require('vm');

const sandbox = { window: {}, URL };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/parser.js', 'utf8'), sandbox);
const p = sandbox.window.AmazonRefundParser;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(p.findCardLast4('Payment method\nVisa ending in 4321') === '4321', 'real card brand + ending must parse');
assert(p.findCardLast4('Refund method\nMastercard\n•••• 9876') === '9876', 'brand on adjacent line + mask must parse');
assert(p.findCardLast4('Payment method\n•••• 2468') === '2468', 'direct masked instrument under payment heading must parse');
assert(p.findCardLast4('Gift card balance\n•••• 1000') === null, 'gift-card masked value must not parse as payment-card last4');
assert(p.findCardLast4('Order summary\nCard layout\n•••• 1000') === null, 'generic card text must not parse as payment-card last4');

const genericCard = {
  innerText: 'Order card\nGift card promotion\n•••• 1000',
  textContent: 'Order card\nGift card promotion\n•••• 1000',
  getAttribute() { return null; },
  querySelectorAll() { return []; }
};
const genericContainer = {
  innerText: 'Order # 113-1111111-2222222\nOrder card\nGift card promotion\n•••• 1000',
  textContent: '',
  querySelectorAll(selector) {
    return /card/i.test(selector) && !/payment|refund-method/i.test(selector) ? [genericCard] : [];
  }
};
const genericEvidence = p.extractPaymentEvidenceText(genericContainer);
assert(genericEvidence === '', 'generic DOM card containers must not be payment evidence');
assert(p.findCardLast4(genericEvidence) === null, 'generic DOM card container must not yield last4 1000');

const paymentSection = {
  innerText: 'Payment method\nVisa ending in 4321\nOrder total $44.00\nGift card promotion •••• 1000',
  textContent: '',
  getAttribute() { return null; },
  querySelectorAll() { return []; }
};
const paymentContainer = {
  innerText: paymentSection.innerText,
  textContent: '',
  querySelectorAll(selector) {
    return /payment/i.test(selector) ? [paymentSection] : [];
  }
};
const paymentEvidence = p.extractPaymentEvidenceText(paymentContainer);
assert(paymentEvidence.includes('Visa ending in 4321'), 'payment evidence must retain the real instrument line');
assert(p.findCardLast4(paymentEvidence) === '4321', 'real payment instrument must win over unrelated masked 1000');

const returnRecord = p.parseTextRecord(
  'Return summary\nRefund method\n$74.76 to your Visa ending in 5800\nRefund subtotal $74.76',
  '111-7520738-8077042',
  { pageType: 'return' }
);
assert(returnRecord.cardLast4 === '5800', 'return refund-method card should remain supported');

console.log('payment evidence regressions passed');
