from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def read(p): return (ROOT / p).read_text(encoding='utf-8')
def write(p,t): (ROOT / p).write_text(t,encoding='utf-8')
def once(t,a,b,label):
    n=t.count(a)
    if n!=1: raise RuntimeError(f'{label}: expected 1, got {n}')
    return t.replace(a,b,1)

p=read('parser.js')
p=once(p,
'''        const groupRefundAmount = Number.isFinite(Number(record.refundAmount ?? record.refundSubtotal))
          ? Number(record.refundAmount ?? record.refundSubtotal)
          : null;''',
'''        const groupRefundRaw = record.refundAmount ?? record.refundSubtotal;
        const groupRefundAmount = groupRefundRaw === null || groupRefundRaw === undefined || groupRefundRaw === ''
          ? null
          : (Number.isFinite(Number(groupRefundRaw)) ? Number(groupRefundRaw) : null);''',
'parser group refund null')
p=once(p,
'''            const itemRefund = Number.isFinite(Number(item.refundAmount)) ? Number(item.refundAmount) : null;''',
'''            const itemRefund = item.refundAmount === null || item.refundAmount === undefined || item.refundAmount === ''
              ? null
              : (Number.isFinite(Number(item.refundAmount)) ? Number(item.refundAmount) : null);''',
'parser item refund null')
write('parser.js',p)

t=read('multi-return-test.js')
needle="assert(meta.returnToken === 'RMA-X' && meta.returnItemId === 'item-x' && meta.returnContractId === 'contract-x' && meta.returnRmaId === 'RMA-X', 'return URL metadata must preserve Amazon return identity');\nconsole.log('multi-return identity tests passed');"
replacement="""assert(meta.returnToken === 'RMA-X' && meta.returnItemId === 'item-x' && meta.returnContractId === 'contract-x' && meta.returnRmaId === 'RMA-X', 'return URL metadata must preserve Amazon return identity');

const noMoneyText = `Order # ${orderId}\nReturn summary\nReturn initiated\nReturned Hydraulic Hose\nQuantity: 1`;
const noMoneyDoc = {
  title: 'Online Return Center',
  body: { innerText: noMoneyText, textContent: noMoneyText },
  querySelectorAll() { return []; }, querySelector() { return null; }
};
const noMoneyParsed = p.parseDocument(noMoneyDoc, `https://www.amazon.com/spr/returns/prep?orderId=${orderId}&rmaId=RMA-NO-MONEY&itemId=item-no-money`);
const noMoneyReturn = noMoneyParsed.records.find(record => record.recordType === 'return');
assert(noMoneyReturn && noMoneyReturn.refundAmount == null, 'return with no proven refund money must keep refundAmount unknown');
assert(noMoneyReturn.returnGroupRefundAmount == null, 'return with no proven refund money must keep group refund unknown instead of zero');
console.log('multi-return identity tests passed');"""
t=once(t,needle,replacement,'multi-return unknown amount test')
write('multi-return-test.js',t)
print('v0.18.2 parser null handling fixed')
