const fs = require('fs');
const vm = require('vm');

const sandbox = { window: {}, URL };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/parser.js', 'utf8'), sandbox);
const p = sandbox.window.AmazonRefundParser;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const returnText = `
Your return request is confirmed.
Item(s) in your return request
Mishimoto MMFAN-CNTL-UPROBE Adjustable Fan Controller
Quantity: 1
Order # 111-7520738-8077042
Return summary
Refund subtotal $74.76
Total estimated refund* $74.76
Refund method
$74.76 to your Visa ending in 5800
Your refund will be issued within 24 hours after dropoff.
`;

const r = p.parseTextRecord(returnText, '111-7520738-8077042', { pageType: 'return', url: 'https://business.amazon.com/returns' });
assert(r.refundAmount === 74.76, 'refund amount should parse');
assert(r.cardLast4 === '5800', 'card last4 should parse');
assert(r.status === 'return_in_progress' || r.status === 'refund_expected', 'return should classify as pending');
assert(r.itemNames[0].includes('Mishimoto'), 'item name should parse');

const orderText = `Order placed May 1, 2026 Order # 114-1111111-2222222 Order total $268.30`;
const o = p.parseTextRecord(orderText, '114-1111111-2222222', { pageType: 'order' });
assert(o.purchaseAmount === 268.30, 'order total should parse');
assert(o.status === 'purchase', 'order should classify as purchase');

const refundedText = `Order # 114-2222222-3333333 Refund issued $52.79 to your original payment method`;
const f = p.parseTextRecord(refundedText, '114-2222222-3333333', { pageType: 'return' });
assert(f.status === 'refunded', 'refund-issued text should classify as refunded');

const receivedText = `
Order # 111-3333333-4444444
We received your return.
Your refund will be processed shortly.
`;
const received = p.parseTextRecord(receivedText, '111-3333333-4444444', { pageType: 'return', url: 'https://www.amazon.com/returns' });
assert(received.status === 'returned_pending_refund', 'received return should classify as confirmed returned');

console.log('parser tests passed');

const detailText = `
Order placed June 2, 2026
Order # 114-4444444-5555555
Order Total: $123.45
Payment method Visa ending in 3172
Delivered June 5
`;
const d = p.parseTextRecord(detailText, '114-4444444-5555555', {
  pageType: 'order',
  url: 'https://www.amazon.com/gp/your-account/order-details?orderID=114-4444444-5555555',
  detailScanComplete: true,
  orderDetailsUrl: 'https://www.amazon.com/gp/your-account/order-details?orderID=114-4444444-5555555'
});
assert(d.purchaseAmount === 123.45, 'detail page order total should parse');
assert(d.cardLast4 === '3172', 'detail page payment card should parse');
assert(d.detailScanComplete === true, 'detail page should be marked complete');
assert(p.isOrderDetailPage(d.orderDetailsUrl), 'order detail URL should be recognized');

const fakeDetailAnchor = {
  getAttribute(name) { return name === 'href' ? '/gp/your-account/order-details?orderID=114-7777777-8888888' : null; },
  innerText: 'View order details', textContent: 'View order details', parentElement: null
};
const fakeDoc = {
  body: { innerText: 'Your Orders\nOrder placed\nOrder # 114-7777777-8888888', textContent: '' },
  querySelectorAll(selector) { return selector === 'a[href]' ? [fakeDetailAnchor] : []; },
  querySelector() { return null; }
};
const links = p.extractOrderDetailLinks(fakeDoc, 'https://www.amazon.com/gp/your-account/order-history');
assert(links.length === 1, 'order history should discover one detail link');
assert(links[0].orderId === '114-7777777-8888888', 'detail link should carry order id');


// Pagination fallback: Amazon sometimes changes/removes the literal Next anchor while
// numbered history links still expose startIndex/page parameters.
function pagAnchor(href, text = '') {
  return {
    getAttribute(name) { return name === 'href' ? href : null; },
    href,
    innerText: text,
    textContent: text,
    parentElement: null
  };
}
const paginationDoc = {
  body: { innerText: 'Your Orders\nOrder placed\nOrder # 114-9999999-0000001', textContent: '' },
  querySelector() { return null; },
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [
      pagAnchor('/gp/your-account/order-history?orderFilter=year-2025&startIndex=0', '1'),
      pagAnchor('/gp/your-account/order-history?orderFilter=year-2025&startIndex=18', '3')
    ];
    if (selector === 'select') return [];
    return [];
  }
};
const inferredNext = p.findNextLink(
  paginationDoc,
  'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2025&startIndex=9'
);
assert(inferredNext && inferredNext.includes('startIndex=18'), 'pagination fallback should infer the next startIndex link');

const firstPagePaginationDoc = {
  ...paginationDoc,
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [
      pagAnchor('/gp/your-account/order-history?orderFilter=year-2025&startIndex=9', '2'),
      pagAnchor('/gp/your-account/order-history?orderFilter=year-2025&startIndex=18', '3')
    ];
    if (selector === 'select') return [];
    return [];
  }
};
const inferredFirstNext = p.findNextLink(
  firstPagePaginationDoc,
  'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2025'
);
assert(inferredFirstNext && inferredFirstNext.includes('startIndex=9'), 'first history page should infer the smallest positive startIndex');
console.log('pagination tests passed');

const buttonNextDoc = {
  querySelector(selector) {
    if (selector.includes('button[aria-label')) {
      return { getAttribute(name) { return name === 'aria-disabled' ? 'false' : null; } };
    }
    return null;
  },
  querySelectorAll() { return []; }
};
assert(p.hasNextPageControl(buttonNextDoc) === true, 'button-only Next pagination should be detected');
console.log('next-control tests passed');

const shippedText = `
Order # 111-5555555-6666666
Your return was dropped off and is on the way back to Amazon.
Refund subtotal $42.00
`;
const shipped = p.parseTextRecord(shippedText, '111-5555555-6666666', { pageType: 'return', url: 'https://www.amazon.com/returns' });
assert(shipped.returnStage === 'shipped', 'dropped-off return should map to shipped stage');
assert(received.returnStage === 'received', 'received return should map to received stage');
assert(f.returnStage === 'refund_issued', 'refund issued should map to refund-issued stage');
assert(r.returnStage === 'started', 'return request should map to started stage');
console.log('return lifecycle tests passed');


// Amazon return-center timeline: future "Refund credited" label must not be treated as completed.
const amazonTimelineText = `
Your refund was issued
We have issued your refund
$150.84 will be credited to the original payment method by Sep 7
Aug 30
Initiated
Aug 31
Dropped off
Aug 31
Refund issued
Sep 7
Refund credited
ecozy Portable Ice Cube Maker Countertop, 45 lbs/Day, Self-Cleaning
Quantity: 1
Total refund $150.84
`;
const timeline = p.parseTextRecord(amazonTimelineText, '114-6491523-3490653', {
  pageType: 'return',
  url: 'https://amazon.com/spr/returns/prep?orderId=114-6491523-3490653&contractId=abc12345&rmaId=RMA123456'
});
assert(timeline.returnStage === 'refund_issued', 'Amazon issued-refund page should stop at refund issued until credited');
assert(timeline.expectedCreditDate === 'Sep 7', 'expected credit date should parse');
assert(timeline.returnMilestones.started.date === 'Aug 30', 'initiated date should parse');
assert(timeline.returnMilestones.shipped.date === 'Aug 31', 'dropoff date should parse');
assert(timeline.returnMilestones.refundIssued.date === 'Aug 31', 'refund-issued date should parse');
assert(timeline.returnMilestones.credited.done === false, 'future refund-credit milestone must remain incomplete');
assert(timeline.returnMilestones.credited.date === null, 'future expected credit date must not be stored as completed credited date');
assert(timeline.itemNames[0].includes('ecozy'), 'return-center item should parse from Quantity line');

const creditedText = `Your refund has been credited to your original payment method. Refund credited on Sep 7.`;
const credited = p.parseTextRecord(creditedText, '114-6491523-3490653', { pageType: 'return' });
assert(credited.returnStage === 'credited', 'actual credited status should map to credited stage');

const returnStatusAnchor = {
  getAttribute(name) { return name === 'href' ? '/spr/returns/prep?orderId=114-7777777-8888888&contractId=contract123&rmaId=rma123456' : null; },
  href: '/spr/returns/prep?orderId=114-7777777-8888888&contractId=contract123&rmaId=rma123456',
  innerText: 'Check return & refund status', textContent: 'Check return & refund status', parentElement: null
};
const returnLinkDoc = {
  body: { innerText: 'Your Orders\nOrder placed\nOrder # 114-7777777-8888888', textContent: '' },
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [returnStatusAnchor];
    return [];
  },
  querySelector() { return null; }
};
const returnLinks = p.extractReturnStatusLinks(returnLinkDoc, 'https://www.amazon.com/gp/your-account/order-history');
assert(returnLinks.length === 1, 'existing return-status link should be discovered');
assert(returnLinks[0].orderId === '114-7777777-8888888', 'return-status link should carry order ID');

const returnPageDoc = {
  title: 'Online Return Center',
  body: { innerText: amazonTimelineText, textContent: amazonTimelineText },
  querySelectorAll() { return []; },
  querySelector() { return null; }
};
const returnPageParsed = p.parseDocument(returnPageDoc, 'https://amazon.com/spr/returns/prep?orderId=114-6491523-3490653&contractId=abc12345&rmaId=RMA123456');
assert(returnPageParsed.records.some(x => x.orderId === '114-6491523-3490653' && x.recordType === 'return'), 'return URL orderId should be parsed even when body omits the order number');
console.log('return-center tests passed');

const provisionalDoc = {
  title: 'Your Orders',
  body: { innerText: 'Your Orders\nOrder placed\nOrder # 114-7777777-8888888', textContent: '' },
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [returnStatusAnchor];
    if (selector === 'select') return [];
    return [];
  },
  querySelector() { return null; }
};
const provisionalParsed = p.parseDocument(provisionalDoc, 'https://www.amazon.com/gp/your-account/order-history');
assert(provisionalParsed.records.some(x => x.recordType === 'return' && x.orderId === '114-7777777-8888888' && x.returnStage === 'started'), 'order page should create a provisional return when an existing return-status link is present');

const genericReturnAnchor = {
  getAttribute(name) { return name === 'href' ? '/spr/returns?orderId=114-7777777-8888888' : null; },
  href: '/spr/returns?orderId=114-7777777-8888888',
  innerText: 'Return or replace items', textContent: 'Return or replace items', parentElement: null
};
const genericDoc = {
  body: provisionalDoc.body,
  querySelectorAll(selector) { return selector === 'a[href]' ? [genericReturnAnchor] : []; },
  querySelector() { return null; }
};
assert(p.extractReturnStatusLinks(genericDoc, 'https://www.amazon.com/gp/your-account/order-history').length === 0, 'generic Return or replace action must not be treated as a started return');
console.log('provisional-return tests passed');

const selectedNumericDoc = {
  body: { innerText: 'Your Orders\nOrder placed\nOrder # 114-9999999-0000002', textContent: '' },
  querySelector(selector) {
    if (selector === '.a-pagination li.a-selected') return { innerText: '2', textContent: '2' };
    return null;
  },
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [
      pagAnchor('/gp/your-account/order-history?cursor=opaque-page-1', '1'),
      pagAnchor('/gp/your-account/order-history?cursor=opaque-page-3', '3'),
      pagAnchor('/gp/your-account/order-history?cursor=opaque-page-4', '4')
    ];
    if (selector === 'select') return [];
    return [];
  }
};
const selectedNumericNext = p.findNextLink(selectedNumericDoc, 'https://www.amazon.com/gp/your-account/order-history?cursor=opaque-page-2');
assert(selectedNumericNext && selectedNumericNext.includes('opaque-page-3'), 'selected numeric paginator should advance even with an unknown cursor parameter');
console.log('selected-page pagination test passed');

// v0.8: Amazon Business year picker should seed lifetime history, even when options are values rather than URLs.
const yearSelect = {
  options: [
    { value: 'year-2026', textContent: '2026', innerText: '2026', getAttribute(){ return null; } },
    { value: 'year-2025', textContent: '2025', innerText: '2025', getAttribute(){ return null; } },
    { value: '2024', textContent: '2024', innerText: '2024', getAttribute(){ return null; } },
    { value: 'last30', textContent: 'Last 30 days', innerText: 'Last 30 days', getAttribute(){ return null; } }
  ]
};
const yearDoc = {
  body: { innerText: 'Your Orders\nViewing 177 orders placed in\n2026\n2025\n2024\nOrder # 114-1111111-0000001', textContent: '' },
  querySelector() { return null; },
  querySelectorAll(selector) {
    if (selector === 'select') return [yearSelect];
    if (selector === 'a[href]' || selector === '*' || selector.includes('[data-value]')) return [];
    return [];
  }
};
const yearLinks = p.extractHistoryYearLinks(yearDoc, 'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2026');
assert(yearLinks.some(x => x.year === 2025 && x.url.includes('#time/2025/pagination/1/')), '2025 year picker should synthesize the taught Business hash route');
assert(yearLinks.some(x => x.year === 2024 && x.url.includes('#time/2024/pagination/1/')), '2024 year picker should synthesize the taught Business hash route');
console.log('year-history tests passed');

// v0.11: Teach Mode proved Amazon Business uses SPA fragment routes for year + page traversal.
const taughtPage1Url = 'https://www.amazon.com/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/1/';
const taughtPage2Url = 'https://www.amazon.com/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/2/';
const taughtRoute = p.historyRouteFromUrl(taughtPage2Url);
assert(taughtRoute.year === 2026 && taughtRoute.page === 2, 'taught hash route should parse year and page');
const taughtPagerDoc = {
  body: { innerText: 'Your Orders\nViewing 177 orders placed in All orders\nOrder # 114-1234567-1234567', textContent: '' },
  querySelector(selector) {
    if (selector === '.a-pagination [aria-current="page"]' || selector === '[aria-current="page"]') return { innerText: '1', textContent: '1' };
    return null;
  },
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [
      pagAnchor('/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/1/', '1'),
      pagAnchor('/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/2/', '2'),
      pagAnchor('/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/3/', '3'),
      pagAnchor('/gp/your-account/order-history?ref_=ya_d_c_yo#time/2026/pagination/next/', 'Next')
    ];
    if (selector === 'select') return [];
    return [];
  }
};
const taughtNext = p.findNextLink(taughtPagerDoc, taughtPage1Url);
assert(taughtNext && taughtNext.includes('#time/2026/pagination/2/'), 'taught pager should choose concrete page 2 instead of #pagination/next');
console.log('taught hash-route pagination tests passed');

// v0.9: if Business hides pager hrefs, try Amazon's canonical +10 slot then the visible-card count fallback.
const syntheticNextDoc = {
  body: { innerText: `Your Orders\nViewing 177 orders placed in 2026\n${Array.from({length:9}, (_,i)=>`Order # 114-123456${i}-123456${i}`).join('\n')}`, textContent: '' },
  querySelector() { return null; },
  querySelectorAll(selector) { return []; }
};
const syntheticNext = p.findNextLink(syntheticNextDoc, 'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2026');
const syntheticCandidates = p.syntheticNextHistoryUrls(syntheticNextDoc, 'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2026');
assert(syntheticNext && syntheticNext.includes('startIndex=10'), 'hidden Business pager should try Amazon canonical startIndex +10 first');
assert(syntheticCandidates.some(x => x.includes('startIndex=9')), 'hidden Business pager should retain visible-count +9 as a verified fallback');
console.log('synthetic-next tests passed');

// v0.8: return-center Total refund and bullet-masked card formats should parse.
const refundCenter = p.parseTextRecord('Total refund $150.84\nRefund issued $150.84\nPayment method Visa •••• 3172', '114-2222222-4444444', { pageType: 'return' });
assert(refundCenter.refundAmount === 150.84, 'Total refund should populate expected refund');
assert(refundCenter.cardLast4 === '3172', 'bullet-masked card should parse');
console.log('refund amount/card tests passed');

// v0.8: strong return-status text on an order card should create a provisional return without a status link.
const statusContainer = {
  innerText: 'Order placed Aug 20, 2026\nOrder # 114-3333333-5555555\nExample returned item\nReturn started\nDropped off Aug 30',
  textContent: '',
  parentElement: null,
  querySelectorAll() { return []; },
  getAttribute() { return null; }
};
const statusOnlyDoc = {
  title: 'Your Orders',
  body: { innerText: statusContainer.innerText, textContent: statusContainer.innerText },
  querySelector() { return null; },
  querySelectorAll(selector) {
    if (selector === 'a[href]' || selector === 'select' || selector === '*' || selector.includes('[data-value]')) return [];
    if (selector.includes('[data-order-id]')) return [statusContainer];
    return [];
  }
};
const statusOnlyParsed = p.parseDocument(statusOnlyDoc, 'https://www.amazon.com/gp/your-account/order-history?orderFilter=year-2026');
assert(statusOnlyParsed.records.some(x => x.recordType === 'return' && x.orderId === '114-3333333-5555555'), 'strong return text should flag the order as returned');
console.log('status-only return detection test passed');


// v0.8: the current Amazon /your-orders/order-details link is authoritative.
const currentDetailAnchor = {
  getAttribute(name) { return name === 'href' ? '/your-orders/order-details?orderID=113-5152372-1721051&ref=ab_ppx_yo_dt_b_fed_order_details' : null; },
  href: '/your-orders/order-details?orderID=113-5152372-1721051&ref=ab_ppx_yo_dt_b_fed_order_details',
  innerText: 'View order details', textContent: 'View order details', parentElement: null
};
const currentDetailDoc = {
  body: { innerText: 'Your Orders\nOrder # 113-5152372-1721051', textContent: '' },
  querySelectorAll(selector) { return selector === 'a[href]' ? [currentDetailAnchor] : []; },
  querySelector() { return null; }
};
const currentDetailLinks = p.extractOrderDetailLinks(currentDetailDoc, 'https://www.amazon.com/your-orders/orders?orderFilter=year-2026');
assert(currentDetailLinks.length === 1, 'current View order details route should be discovered');
assert(currentDetailLinks[0].url.includes('/your-orders/order-details?'), 'current /your-orders/order-details route should be preserved');
assert(currentDetailLinks[0].url.includes('orderID=113-5152372-1721051'), 'current detail URL should preserve order ID');

// v0.17: visible orders and canonical detail links are tracked independently.
// Missing anchors are a crawler stop condition, never permission to invent a canonical URL.
const twoOrderHistoryDoc = {
  body: { innerText: 'Your Orders\nOrder # 113-5152372-1721051\nOrder # 114-1111111-2222222', textContent: '' },
  querySelectorAll(selector) { return selector === 'a[href]' ? [currentDetailAnchor] : []; },
  querySelector() { return null; }
};
const everyDetail = p.extractOrderDetailLinks(twoOrderHistoryDoc, 'https://www.amazon.com/your-orders/orders?orderFilter=year-2026');
assert(everyDetail.length === 1, 'only real rendered View order details links may become canonical detail links');
assert(!everyDetail.some(x => x.orderId === '114-1111111-2222222'), 'missing detail anchor must not synthesize a canonical URL');
const twoOrderParsed = p.parseDocument(twoOrderHistoryDoc, 'https://www.amazon.com/your-orders/orders?orderFilter=year-2026');
assert(twoOrderParsed.historyOrderIds.length === 2, 'all visible Order IDs must remain in the history fingerprint');
console.log('mandatory order-detail tests passed');


// v0.8: Order Details URL must win over unrelated order IDs present elsewhere on the page.
const detailWithRelatedOrderDoc = {
  title: 'Order Details',
  body: { innerText: `Order placed September 1, 2026\nOrder # 113-5152372-1721051\nOrder Total: $456.78\nPayment Method\nAmazon Business Card ending in 4321\nExample primary item\nQuantity: 1\nRelated order 114-9999999-8888888`, textContent: '' },
  querySelectorAll() { return []; },
  querySelector() { return null; }
};
const detailWithRelated = p.parseDocument(detailWithRelatedOrderDoc, 'https://www.amazon.com/your-orders/order-details?orderID=113-5152372-1721051');
const authoritative = detailWithRelated.records.find(x => x.recordType === 'order' && x.orderId === '113-5152372-1721051');
assert(authoritative && authoritative.detailScanComplete === true, 'URL-targeted detail order should be marked detailed');
assert(authoritative.purchaseAmount === 456.78, 'URL-targeted detail parser should read the full-page order total');
assert(authoritative.cardLast4 === '4321', 'URL-targeted detail parser should read the payment card');
assert(!detailWithRelated.records.some(x => x.orderId === '114-9999999-8888888'), 'related order IDs should not become records on a targeted detail page');
console.log('authoritative detail-page tests passed');

const detailHistoryGuardDoc = {
  body: { innerText: 'Your Orders\nOrder # 113-6604769-5603459\nOrder Total: $25.00', textContent: '' },
  querySelectorAll() { return []; },
  querySelector() { return null; }
};
assert(
  p.parseDocument(detailHistoryGuardDoc, 'https://www.amazon.com/your-orders/order-details?orderID=113-6604769-5603459').isOrderHistoryPage === false,
  'Order Details must never be treated as an order-history page'
);
console.log('detail/history separation test passed');


const fallbackProductAnchor = {
  innerText: '', textContent: '', parentElement: null,
  href: 'https://www.amazon.com/dp/B012345678',
  closest() { return null; },
  getAttribute(name) {
    if (name === 'href') return '/dp/B012345678';
    if (name === 'title') return 'Fallback Product Title From Amazon';
    if (name === 'aria-label') return null;
    return null;
  },
  querySelector() { return null; }
};
const productContainer = {
  querySelectorAll(selector) {
    if (selector.includes('/dp/')) return [fallbackProductAnchor];
    return [];
  }
};
const immediateTitles = p.extractItemNamesFromContainer(productContainer);
assert(immediateTitles[0] === 'Fallback Product Title From Amazon', 'blank product anchors should fall back to title/aria/image text immediately');
const serverYear = p.buildServerHistoryUrl('https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/1/', 2025, 3);
assert(serverYear.includes('timeFilter=year-2025') && serverYear.includes('startIndex=20') && !serverYear.includes('#time/'), 'server history helper should use timeFilter + startIndex and clear hash');
console.log('upstream exporter integration parser tests passed');


// v0.17 regressions
const unrelatedDigits = p.parseTextRecord('Order # 114-1234567-7654321 Tracking XXXX 4821 Invoice 2026', '114-1234567-7654321', { pageType: 'order' });
assert(unrelatedDigits.cardLast4 === null, 'arbitrary four-digit page text must never become a payment card');
const semanticPayment = p.parseTextRecord('Payment information\nVisa ending in 4821\nOrder total $19.99', '114-1234567-7654321', { pageType: 'order' });
assert(semanticPayment.cardLast4 === '4821', 'semantic payment evidence should capture card last four');
const unrelatedCardDoc = {
  title: 'Order Details',
  body: { innerText: 'Order placed Sep 2, 2026\nOrder # 114-1234567-7654321\nOrder Total: $19.99\nExample item\nQuantity: 1\nOld receipt note: Visa ending in 4821', textContent: '' },
  querySelectorAll() { return []; },
  querySelector() { return null; }
};
const unrelatedCardParsed = p.parseDocument(unrelatedCardDoc, 'https://www.amazon.com/your-orders/order-details?orderID=114-1234567-7654321');
const unrelatedCardOrder = unrelatedCardParsed.records.find(record => record.recordType === 'order');
assert(unrelatedCardOrder.cardLast4 === null, 'document parsing must not accept last four outside payment-method evidence');

const noDetailAnchorDoc = {
  body: { innerText: 'Your Orders\nOrder placed\nOrder # 114-8888888-9999999', textContent: '' },
  querySelectorAll() { return []; },
  querySelector() { return null; }
};
assert(p.extractOrderDetailLinks(noDetailAnchorDoc, 'https://www.amazon.com/gp/your-account/order-history').length === 0, 'history parser must not synthesize missing Order Details URLs');
const noAnchorParsed = p.parseDocument(noDetailAnchorDoc, 'https://www.amazon.com/gp/your-account/order-history');
assert(noAnchorParsed.historyOrderIds.includes('114-8888888-9999999'), 'visible Order IDs must remain in pagination fingerprint even if canonical link is missing');

const staticTimelineOnly = p.parseTextRecord('Initiated Aug 30\nDropped off Aug 31\nRefund issued\nRefund credited Sep 7\n$75.00 will be credited by Sep 7', '114-2222222-3333333', { pageType: 'return' });
assert(staticTimelineOnly.returnStage !== 'refund_issued' && staticTimelineOnly.returnStage !== 'credited', 'static timeline labels and future ETA must not prove refund issuance');

const itemA = { recordType:'return', orderId:'114-3333333-4444444', returnToken:'RMA-ITEMS', itemNames:['Widget A'], asins:['B000000001'], refundAmount:10, provisionalReturn:false };
const itemB = { ...itemA, itemNames:['Widget B'], asins:['B000000002'], refundAmount:20 };
assert(p.makeRecordId(itemA) !== p.makeRecordId(itemB), 'multiple returned items under one return token need distinct item-level record IDs');
assert(p.isCompleteCanonicalDetail({ recordType:'order', orderId:'114-3333333-4444444', orderDetailsUrl:'https://www.amazon.com/your-orders/order-details?orderID=114-3333333-4444444', orderDate:'Sep 1, 2026', purchaseAmount:20, itemNames:['Widget'] }, 'https://www.amazon.com/your-orders/order-details?orderID=114-3333333-4444444') === true, 'complete canonical detail should require real URL/date/total/item');
assert(p.isCompleteCanonicalDetail({ recordType:'order', orderId:'114-3333333-4444444', orderDetailsUrl:'https://www.amazon.com/your-orders/order-details?orderID=114-3333333-4444444', orderDate:'Sep 1, 2026', purchaseAmount:20, itemNames:[] }, 'https://www.amazon.com/your-orders/order-details?orderID=114-3333333-4444444') === false, 'detail page without item capture must not be Detailed');
console.log('v0.17 parser regressions passed');
