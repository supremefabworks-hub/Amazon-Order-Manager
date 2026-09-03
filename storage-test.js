const fs = require('fs');
const vm = require('vm');

const backing = {};
const sandbox = {
  window: {},
  chrome: {
    storage: {
      local: {
        async get(keys) {
          const out = {};
          for (const key of keys) if (Object.prototype.hasOwnProperty.call(backing, key)) out[key] = backing[key];
          return out;
        },
        async set(values) { Object.assign(backing, values); }
      }
    }
  }
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/storage.js', 'utf8'), sandbox);
const s = sandbox.window.AmazonRefundStorage;

function assert(condition, message) { if (!condition) throw new Error(message); }

(async () => {
  const index = {
    recordId: 'order:114-4444444-5555555', recordType: 'order', orderId: '114-4444444-5555555',
    itemNames: [], orderDetailsUrl: 'https://www.amazon.com/gp/your-account/order-details?orderID=114-4444444-5555555',
    detailScanComplete: false, status: 'purchase'
  };
  await s.upsertRecords([index]);
  let summary = s.summarizeLedger(await s.getLedger());
  assert(summary.lifetimeOrders === 1, 'index should create one lifetime order');
  assert(summary.detailedOrders === 0, 'index should not count as detailed');

  const detailed = {
    ...index, itemNames: ['Example Part'], purchaseAmount: 123.45, cardLast4: '3172',
    detailScanComplete: true, detailScannedAt: new Date().toISOString()
  };
  const result = await s.upsertRecords([detailed]);
  const ledger = await s.getLedger();
  summary = s.summarizeLedger(ledger);
  assert(result.updated === 1, 'detail upgrade should be a meaningful update');
  assert(summary.detailedOrders === 1, 'detail upgrade should count as detailed');
  assert(ledger[0].itemNames.includes('Example Part'), 'detail item should merge into order');
  assert(ledger[0].purchaseAmount === 123.45, 'detail total should merge into order');

  const retBase = {
    recordId: 'return:114-4444444-5555555:example-part', recordType: 'return', orderId: '114-4444444-5555555',
    itemNames: ['Example Part'], refundAmount: 42.00, status: 'return_in_progress', returnStage: 'started', statusText: 'Return request confirmed'
  };
  await s.upsertRecords([retBase]);
  await s.upsertRecords([{ ...retBase, status: 'returned_pending_refund', returnStage: 'received', statusText: 'We received your return' }]);
  await s.upsertRecords([{ ...retBase, status: 'return_in_progress', returnStage: 'started', statusText: 'Return request confirmed' }]);
  const ret = (await s.getLedger()).find(r => r.recordId === retBase.recordId);
  assert(s.getReturnStage(ret) === 'received', 'return lifecycle must not regress after an older page is rescanned');
  assert(s.returnProgress(ret).shippedOrReceived === true, 'received return should complete middle lifecycle step');
  const retSummary = s.summarizeLedger(await s.getLedger());
  assert(retSummary.returnedOrders === 1, 'return should count once by order');
  assert(retSummary.confirmedReturnedOrders === 1, 'received return should count as confirmed returned');
  assert(retSummary.unresolvedReturnOrders === 1, 'received but not refunded return should remain unresolved');

  await s.upsertRecords([{ ...retBase, status: 'refunded', returnStage: 'refund_issued', statusText: 'We have issued your refund', returnMilestones: {
    stage: 'refund_issued', started: {done:true,date:'Aug 30'}, shipped:{done:true,date:'Aug 31'}, refundIssued:{done:true,date:'Aug 31'}, credited:{done:false,date:null}, expectedCreditDate:'Sep 7'
  } }]);
  const issued = (await s.getLedger()).find(r => r.recordId === retBase.recordId);
  assert(s.getReturnStage(issued) === 'refund_issued', 'refund-issued stage should be retained');
  assert(s.returnProgress(issued).refundIssued === true, 'refund-issued milestone should be completed');
  assert(s.returnProgress(issued).credited === false, 'future credit milestone should remain incomplete');
  assert(issued.returnMilestones.credited.date == null, 'expected credit ETA must not be stored as completed credit date');
  assert(issued.returnMilestones.expectedCreditDate === 'Sep 7', 'expected credit ETA should remain available separately');
  const issuedSummary = s.summarizeLedger(await s.getLedger());
  assert(issuedSummary.refundedOrders === 1, 'refund-issued order should count as refunded');
  assert(issuedSummary.unresolvedReturnOrders === 0, 'refund-issued order should leave Needs Review');



  await s.updateRecord(retBase.recordId, { bankVerification: {
    status: 'confirmed', matchedAmount: 42.00, postedDate: '2026-09-03',
    accountLast4: '3172', accountName: 'Amazon Visa', checkedAt: '2026-09-03T19:00:00Z'
  } });
  const bankConfirmed = (await s.getLedger()).find(r => r.recordId === retBase.recordId);
  assert(s.isBankCreditConfirmed(bankConfirmed) === true, 'bank verification should confirm posted credit');
  assert(s.isCreditConfirmed(bankConfirmed) === true, 'bank confirmation should complete final credit milestone');
  assert(s.returnProgress(bankConfirmed).credited === true, 'return progress should finish after bank confirmation');
  const bankSummary = s.summarizeLedger(await s.getLedger());
  assert(bankSummary.creditedOrders >= 1, 'bank-confirmed refund should count as credited');

  const prov = {
    recordId: 'return:114-9999999-1111111:rmaabc123:pending', recordType: 'return', orderId: '114-9999999-1111111',
    itemNames: ['Wrong bundled sibling'], returnToken: 'RMAABC123', returnStatusUrl: 'https://amazon.com/spr/returns/prep?orderId=114-9999999-1111111&rmaId=RMAABC123',
    status: 'return_in_progress', returnStage: 'started', statusText: 'Amazon return status link detected', provisionalReturn: true, authoritativeReturnCapture: false
  };
  await s.upsertRecords([prov]);
  await s.upsertRecords([{ ...prov, recordId: 'return:114-9999999-1111111:rmaabc123:returned-widget', itemNames: ['Returned Widget'], refundAmount: 88.50, status: 'refunded', returnStage: 'refund_issued', statusText: 'We have issued your refund', provisionalReturn: false, authoritativeReturnCapture: true }]);
  const sameReturnRows = (await s.getLedger()).filter(r => r.orderId === prov.orderId && r.recordType === 'return');
  assert(sameReturnRows.length === 1, 'provisional return should upgrade in-place when the return page has the same token');
  assert(sameReturnRows[0].itemNames.length === 1 && sameReturnRows[0].itemNames[0] === 'Returned Widget', 'authoritative return page must replace provisional bundled item names');

  await s.upsertRecords([
    { ...sameReturnRows[0], recordId:'return:114-9999999-1111111:rmaabc123:item-a', itemNames:['Item A'], asins:['B000000001'], refundAmount:20, authoritativeReturnCapture:true, provisionalReturn:false },
    { ...sameReturnRows[0], recordId:'return:114-9999999-1111111:rmaabc123:item-b', itemNames:['Item B'], asins:['B000000002'], refundAmount:30, authoritativeReturnCapture:true, provisionalReturn:false }
  ]);
  const itemLevelRows = (await s.getLedger()).filter(r => r.orderId === prov.orderId && r.recordType === 'return');
  assert(itemLevelRows.some(r => r.itemNames[0] === 'Item A' && r.refundAmount === 20), 'first returned item must retain its own expected refund');
  assert(itemLevelRows.some(r => r.itemNames[0] === 'Item B' && r.refundAmount === 30), 'second returned item must retain its own expected refund');

  const trustedReturn = {
    recordId: 'return:113-7000000-3000000:rma-trusted:item-item-a', recordType: 'return', orderId: '113-7000000-3000000',
    returnToken: 'RMA-TRUSTED', returnItemId: 'item-a', itemNames: ['Trusted Order Details Item'], asins: ['B000000010'],
    itemIdentitySource: 'order-detail-return-link', status: 'return_in_progress', returnStage: 'started', provisionalReturn: true
  };
  await s.upsertRecords([trustedReturn]);
  await s.upsertRecords([{ ...trustedReturn, itemNames: ['Wrong Return Page Sibling'], asins: ['B000000099'], itemIdentitySource: 'return-page-item', authoritativeReturnCapture: true, provisionalReturn: false, status: 'refunded', returnStage: 'refund_issued' }]);
  const trustedMerged = (await s.getLedger()).find(r => r.recordId === trustedReturn.recordId);
  assert(trustedMerged.itemNames[0] === 'Trusted Order Details Item', 'exact Order Details return-link identity must survive conflicting return-page item text');
  assert(trustedMerged.asins[0] === 'B000000010', 'trusted return-link ASIN must survive a conflicting authoritative-page ASIN');
  assert(trustedMerged.itemIdentityConflict === true, 'conflicting return-page identity must be flagged instead of silently replacing trusted identity');
  assert(s.needsCreditReview(trustedMerged) === true, 'item identity conflicts must require review');

  console.log('storage tests passed');
})().catch(error => { console.error(error); process.exit(1); });
