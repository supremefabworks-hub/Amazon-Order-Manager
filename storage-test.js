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
  await s.upsertRecords([{ ...trustedReturn, itemNames: ['Wrong Return Page Sibling'], asins: ['B000000099'], itemIdentitySource: 'return-page-item', itemAsinEvidenceSource: null, authoritativeReturnCapture: true, provisionalReturn: false, status: 'refunded', returnStage: 'refund_issued' }]);
  const trustedMerged = (await s.getLedger()).find(r => r.recordId === trustedReturn.recordId);
  assert(trustedMerged.itemNames[0] === 'Trusted Order Details Item', 'exact Order Details return-link identity must survive weak return-page item text');
  assert(trustedMerged.asins[0] === 'B000000010', 'trusted return-link ASIN must survive weak broad return-page ASIN contamination');
  assert(trustedMerged.itemIdentityConflict !== true, 'weak/unbound return-page ASIN must not create an item identity conflict');

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
  await s.upsertRecords([{ ...asinConflictBase, asins: ['B000000002'], itemNames: ['Different Product'], itemIdentitySource: 'return-page-item', itemAsinEvidenceSource: 'return-item-data-asin', provisionalReturn: false, authoritativeReturnCapture: true }]);
  const asinConflict = (await s.getLedger()).find(r => r.recordId === asinConflictBase.recordId);
  assert(asinConflict.itemIdentityConflict === true, 'contradictory non-empty ASIN evidence for the same returnItemId must remain reviewable');

  console.log('storage tests passed');
})().catch(error => { console.error(error); process.exit(1); });
