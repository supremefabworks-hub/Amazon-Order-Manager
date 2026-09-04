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

const canonicalRefundDoc = {
  title: 'Order Details',
  body: { innerText: `Order placed September 1, 2026
Order # 113-5152372-1721052
Order Total: $262.86
Refund Total $185.46
Example returned item
Quantity: 1`, textContent: '' },
  querySelectorAll() { return []; }, querySelector() { return null; }
};
const canonicalRefundParsed = p.parseDocument(canonicalRefundDoc, 'https://www.amazon.com/your-orders/order-details?orderID=113-5152372-1721052');
const canonicalRefundOrder = canonicalRefundParsed.records.find(x => x.recordType === 'order');
assert(canonicalRefundOrder.canonicalRefundTotal === 185.46, 'Order Details Refund Total must become the canonical order-level refund total');
assert(p.findOrderRefundTotal(`Order Total $262.86
Refund Total $185.46`) === 185.46, 'canonical Refund Total helper must parse the explicit label');

const proseRefundDoc = {
  title: 'Order Details',
  body: { innerText: `Order placed September 1, 2026
Order # 113-5152372-1721053
Order Total: $100.00
Example returned item
Quantity: 1
Your refund has been issued $88.00`, textContent: '' },
  querySelectorAll() { return []; }, querySelector() { return null; }
};
const proseRefundParsed = p.parseDocument(proseRefundDoc, 'https://www.amazon.com/your-orders/order-details?orderID=113-5152372-1721053');
const proseRefundOrder = proseRefundParsed.records.find(x => x.recordType === 'order');
assert(proseRefundOrder.refundAmount === 88, 'generic refund parser should still retain lifecycle refund evidence where applicable');
assert(proseRefundOrder.canonicalRefundTotal == null, 'refund lifecycle prose must not become canonical Order Details Refund Total');
assert(p.findOrderRefundTotal(`Your refund has been issued $88.00`) === null, 'canonical helper must reject refund lifecycle prose');
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


// v0.18.3 live acceptance regressions
assert(p.isOrderDetailPage('https://www.amazon.com/gp/css/summary/edit.html?orderID=113-1234567-7654321') === true, 'captured legacy /gp/css/summary/edit.html must be recognized as an Order Details page');
const legacyDetailAnchor = {
  innerText: 'View order details', textContent: 'View order details', parentElement: null,
  href: 'https://www.amazon.com/gp/css/summary/edit.html?orderID=113-1234567-7654321',
  getAttribute(name) { return name === 'href' ? '/gp/css/summary/edit.html?orderID=113-1234567-7654321' : null; }
};
const legacyDetailDoc = {
  body: { innerText: 'Order # 113-1234567-7654321', textContent: '' },
  querySelectorAll(selector) { return selector === 'a[href]' ? [legacyDetailAnchor] : []; },
  querySelector() { return null; }
};
const legacyLinks = p.extractOrderDetailLinks(legacyDetailDoc, 'https://www.amazon.com/gp/your-account/order-history');
assert(legacyLinks.length === 1 && legacyLinks[0].orderId === '113-1234567-7654321', 'real captured legacy Order Details href must be preserved');
assert(legacyLinks[0].url.includes('/gp/css/summary/edit.html'), 'legacy detail discovery must preserve Amazon supplied href');

const staticRefundTimeline = p.parseTextRecord('Return started\nInitiated\nDropped off\nRefund issued\nCredit pending', '113-2222222-3333333', { pageType: 'return', forceRecordType: 'return' });
assert(staticRefundTimeline.returnStage !== 'refund_issued', 'bare Refund issued timeline label must not promote lifecycle');
assert(!/refund issued/i.test(staticRefundTimeline.statusText || ''), 'bare Refund issued timeline label must not leak into affirmative status text');
const affirmativeRefund = p.parseTextRecord('Return complete\nYour refund has been issued.\nRefund issued', '113-2222222-3333334', { pageType: 'return', forceRecordType: 'return' });
assert(affirmativeRefund.returnStage === 'refund_issued', 'affirmative refund-issued sentence must still promote lifecycle');
assert(/refund has been issued/i.test(affirmativeRefund.statusText || ''), 'affirmative refund-issued sentence must remain visible status evidence');
console.log('v0.18.3 parser live regressions passed');


// v0.18.4 terminal cancelled-order regressions
const cancelledOrderId = '112-3886192-2097013';
const cancelledCardText = `Order placed\nJune 10, 2026\nTotal\n$0.00\nPlaced by\nVadya\nOrder # ${cancelledOrderId}\nCancelled\nHHZL Rubber Edge Trim T Molding Seal Strip`;
const cancelledEvidence = p.terminalCancelledHistoryEvidence(cancelledCardText, cancelledOrderId);
assert(cancelledEvidence.complete === true, 'exact Cancelled + $0.00 + same Order ID must be a terminal history order');
assert(cancelledEvidence.total === 0, 'terminal cancellation must preserve exact $0.00 order total');
assert(p.terminalCancelledHistoryEvidence(cancelledCardText.replace('$0.00', '$12.34'), cancelledOrderId).complete === false, 'nonzero cancelled order must still require Order Details');
assert(p.terminalCancelledHistoryEvidence(cancelledCardText.replace('\nCancelled\n', '\nCancellation requested\n'), cancelledOrderId).complete === false, 'ambiguous cancellation prose must not satisfy terminal gate');
assert(p.terminalCancelledHistoryEvidence(cancelledCardText.replace(cancelledOrderId, '112-0000000-0000000'), cancelledOrderId).complete === false, 'terminal evidence must be bound to the same visible Order ID');
console.log('v0.18.4 terminal cancellation parser regressions passed');


// v0.18.5 structural no-detail history-card scoping regressions
function v185FakeNode(text, parent = null, anchors = [], attrs = {}) {
  return {
    innerText: text, textContent: text, parentElement: parent,
    getAttribute(name) { return attrs[name] ?? null; },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === 'a[href]' || selector.includes('a[href*="/dp/"]') || selector.includes('a[href*="/gp/product/"]') || selector.includes('a[href*="/product/"]')) return anchors;
      return [];
    }
  };
}
function v185ProductAnchor(asin, title, parent = null) {
  return {
    innerText: title, textContent: title, parentElement: parent, href: `https://www.amazon.com/dp/${asin}`,
    getAttribute(name) { if (name === 'href') return `/dp/${asin}`; if (name === 'title') return title; return null; },
    querySelector() { return null; }, closest() { return null; }
  };
}
const v185LiveCancelledId = '112-3886192-2097013';
const v185CancelledProduct = v185ProductAnchor('B0FN37J39V', 'HHZL Rubber Edge Trim T Molding Seal Strip');
const v185CancelledCardText = `Order placed\nJune 10, 2026\nTotal\n$0.00\nOrder # ${v185LiveCancelledId}\nCancelled\nHHZL Rubber Edge Trim T Molding Seal Strip`;
const v185CancelledCardNode = v185FakeNode(v185CancelledCardText, null, [v185CancelledProduct]);
const v185CancelledOrderNumberNode = v185FakeNode(`Order # ${v185LiveCancelledId}`, v185CancelledCardNode, []);
const v185NeighboringAncestor = v185FakeNode(`Order placed\nJune 11, 2026\nTotal\n$10.00\nOrder # 113-1111111-1111111\n${v185CancelledCardText}\nOrder placed\nJune 9, 2026\nTotal\n$20.00\nOrder # 113-2222222-2222222`, null, [v185CancelledProduct]);
v185CancelledCardNode.parentElement = v185NeighboringAncestor;
const v185StructuralDoc = {
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [];
    if (['span','a','div','li','[data-order-id]','[data-orderid]','[data-order-number]'].includes(selector)) return [v185CancelledOrderNumberNode, v185CancelledCardNode, v185NeighboringAncestor];
    return [];
  }
};
const v185IsolatedCancelled = p.historyContainerForOrder(v185StructuralDoc, v185LiveCancelledId);
assert(v185IsolatedCancelled === v185CancelledCardNode, 'no-detail cancelled order must resolve to its own single-order card, not a neighboring multi-order ancestor');
const v185IsolatedTerminal = p.terminalCancelledHistoryEvidence(v185IsolatedCancelled.innerText, v185LiveCancelledId);
assert(v185IsolatedTerminal.complete === true, 'isolated cancelled $0.00 card must satisfy terminal evidence');
assert(p.coherentSingleOrderHistoryCard(v185NeighboringAncestor, v185LiveCancelledId) === false, 'multi-order ancestor must never qualify as a coherent single-order card');

// v0.18.5 return-page identity regressions
const v185UnrelatedAnchor = v185ProductAnchor('B000000099', 'Unrelated recommendation');
const v185BroadReturnBox = v185FakeNode('Return item\nRAMPOW Micro USB Cable 2 Pack 3.3ft\nQuantity: 1\nRefund amount $6.99', null, [v185UnrelatedAnchor]);
v185BroadReturnBox.querySelectorAll = selector => {
  if (selector === '.a-box') return [v185BroadReturnBox];
  if (selector.includes('a[href*="/dp/"]')) return [v185UnrelatedAnchor];
  return [];
};
const v185BroadEntries = p.extractReturnItemEntries(v185BroadReturnBox);
assert(v185BroadEntries.length === 1, 'broad return text should still produce one item entry');
assert(v185BroadEntries[0].itemName && /RAMPOW/i.test(v185BroadEntries[0].itemName), 'return-specific text must win for the item name');
assert(v185BroadEntries[0].asin == null && v185BroadEntries[0].asinEvidenceSource == null, 'unrelated product link in broad return section must not become ASIN identity');

const v185StrongReturnAnchor = v185ProductAnchor('B000000002', 'Different Product');
const v185StrongReturnItem = v185FakeNode('Return item\nDifferent Product\nQuantity: 1\nRefund amount $10.00', null, [v185StrongReturnAnchor], {'data-asin':'B000000002'});
v185StrongReturnItem.querySelectorAll = selector => {
  if (selector === '[data-asin]') return [v185StrongReturnItem];
  if (selector.includes('a[href*="/dp/"]')) return [v185StrongReturnAnchor];
  return [];
};
const v185StrongEntries = p.extractReturnItemEntries(v185StrongReturnItem);
assert(v185StrongEntries.length === 1 && v185StrongEntries[0].asin === 'B000000002', 'direct data-asin item block must preserve strong ASIN evidence');
assert(v185StrongEntries[0].asinEvidenceSource === 'return-item-data-asin', 'strong return ASIN must record its binding source');
console.log('v0.18.5 structural scope and return identity parser regressions passed');


// v0.18.5 strong+weak duplicate collapse regression
const v185DuplicateAnchor = v185ProductAnchor('B000000003', 'Duplicate Returned Product');
const v185StrongChild = v185FakeNode('Return item\nDuplicate Returned Product\nQuantity: 1\nRefund amount $9.99', null, [v185DuplicateAnchor], {'data-asin':'B000000003'});
const v185BroadParent = v185FakeNode('Return item\nDuplicate Returned Product\nQuantity: 1\nRefund amount $9.99', null, [v185DuplicateAnchor]);
const v185CompositeReturn = {
  querySelectorAll(selector) {
    if (selector === '[data-asin]') return [v185StrongChild];
    if (selector === '.a-box') return [v185BroadParent];
    return [];
  }
};
const v185CollapsedEntries = p.extractReturnItemEntries(v185CompositeReturn);
assert(v185CollapsedEntries.length === 1, 'specific and broad representations of the same return item must collapse to one child');
assert(v185CollapsedEntries[0].asin === 'B000000003' && v185CollapsedEntries[0].asinEvidenceSource === 'return-item-data-asin', 'strong item-specific evidence must win duplicate collapse');
console.log('v0.18.5 duplicate return item collapse regression passed');


// v0.18.6 final-page pagination regressions
function v0186PagerElement({ text = '', href = '', className = '', tagName = 'A', ariaDisabled = null, inPager = true, role = null } = {}) {
  return {
    innerText: text, textContent: text, href, className, tagName, disabled: false,
    getAttribute(name) {
      if (name === 'href') return href || null;
      if (name === 'class') return className || null;
      if (name === 'aria-disabled') return ariaDisabled;
      if (name === 'aria-label') return text;
      if (name === 'role') return role;
      return null;
    },
    closest(selector) {
      if (/(?:\.a-disabled|\.s-pagination-disabled|\[aria-disabled="true"\])/.test(selector) && (ariaDisabled === 'true' || /(?:^|\s)(?:a-disabled|s-pagination-disabled|disabled)(?:\s|$)/i.test(className))) return this;
      if (inPager && /(?:\.a-pagination|ul\.a-pagination|aria-label\*?=.?pagination|data-testid\*?=.?pagination)/i.test(selector)) return { className: 'a-pagination' };
      return null;
    }
  };
}
function v0186PagerDoc(currentPage, controls, activeNext = null) {
  const current = v0186PagerElement({ text: String(currentPage), href: `#pagination/${currentPage}/` });
  return {
    querySelector(selector) {
      if (selector.includes('a-selected') || selector.includes('aria-current') || selector.includes('s-pagination-selected')) return current;
      if (activeNext && /next|a-last|rel="next"/i.test(selector)) return activeNext;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === 'a[href]') return controls.filter(x => x.href);
      if (selector.includes('a[href], button')) return controls;
      return [];
    }
  };
}
const v0186DisabledNext = v0186PagerElement({ text: 'Next', tagName: 'LI', href: '', className: 'a-last a-disabled', ariaDisabled: 'true' });
const v0186FinalLinks = [11,12,13,14,15,16,17,18].map(n => v0186PagerElement({ text:String(n), href:`#pagination/${n}/` }));
const v0186FinalDoc = v0186PagerDoc(18, [...v0186FinalLinks, v0186DisabledNext]);
const v0186FinalUrl = 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/18/';
assert(p.hasNextPageControl(v0186FinalDoc, v0186FinalUrl) === false, 'selected final page + disabled Next must end the current history year');
assert(p.findNextLink(v0186FinalDoc, v0186FinalUrl) == null, 'final page must not synthesize or discover page 19 when Next is disabled');

const v0186Page18 = v0186PagerElement({ text:'18', href:'#pagination/18/' });
const v0186EnabledNext = v0186PagerElement({ text:'Next', href:'#pagination/18/' });
const v0186Page17Doc = v0186PagerDoc(17, [v0186Page18, v0186EnabledNext], v0186EnabledNext);
const v0186Page17Url = 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/17/';
assert(p.hasNextPageControl(v0186Page17Doc, v0186Page17Url) === true, 'page 17 with real page 18/enabled Next must continue');
const v0186NextUrl = p.findNextLink(v0186Page17Doc, v0186Page17Url);
assert(v0186NextUrl && /pagination\/18\//.test(v0186NextUrl), 'page 17 must resolve the concrete page 18 route');

const v0186UnrelatedNext = v0186PagerElement({ text:'Next', tagName:'BUTTON', href:'', inPager:false });
const v0186UnrelatedDoc = v0186PagerDoc(18, [v0186UnrelatedNext]);
assert(p.hasNextPageControl(v0186UnrelatedDoc, v0186FinalUrl) === false, 'unrelated whole-page Next text/button must not masquerade as history pagination');


// v0.18.7 live ThermoMaven: future instructions/static labels are not completed milestones.
const v0187ThermoMaven = `
Drop off your return by Sep 8
Location: Any UPS dropoff
We will issue your refund within 30 days from the time you have dropped off your return.
Note: Once issued, refunds typically become available in your account within 7 days.
Aug 31
Initiated
Drop off
Return received
Refund issued
Refund credited
`;
const v0187Thermo = p.parseTextRecord(v0187ThermoMaven, '111-1790078-4741015', { pageType: 'return', url: 'https://www.amazon.com/spr/returns/prep?orderId=111-1790078-4741015&rmaId=RMA-THERMO' });
assert(v0187Thermo.returnStage === 'started', 'future dropoff instructions/static labels must leave ThermoMaven at Initiated');
assert(v0187Thermo.returnMilestones.shipped.done === false, 'policy phrase about time you have dropped off must not complete Dropped off');
assert(v0187Thermo.returnMilestones.refundIssued.done === false, 'bare Refund issued timeline label must not complete refund issued');
assert(v0187Thermo.returnMilestones.credited.done === false, 'bare Refund credited timeline label must not complete credit');
const v0187ActualDropoff = p.parseTextRecord('Your return was dropped off and is on the way back to Amazon.', '111-1790078-4741015', { pageType: 'return' });
assert(v0187ActualDropoff.returnStage === 'shipped', 'affirmative completed dropoff language must still complete shipped stage');

function v0187ProductAnchor(asin, title) {
  return {
    href: `https://www.amazon.com/dp/${asin}`,
    innerText: title, textContent: title, parentElement: null,
    getAttribute(name) { if (name === 'href') return `/dp/${asin}`; if (name === 'title') return title; return null; },
    closest() { return null; }, querySelector() { return null; }
  };
}
function v0187ItemNode(text, anchor) {
  const node = {
    innerText: text, textContent: text, parentElement: null,
    querySelectorAll(selector) {
      if (selector.includes('a[href*="/dp/"]')) return [anchor];
      if (selector === '.a-price .a-offscreen' || selector.includes('item-price')) return [];
      return [];
    },
    querySelector() { return null; }
  };
  anchor.parentElement = node;
  return node;
}
const v0187Anchors = Array.from({length:6}, (_,i) => v0187ProductAnchor(`B00000010${i}`, `Purchased Product ${i + 1} Long Descriptive Title`));
const v0187Nodes = v0187Anchors.map((anchor,i) => v0187ItemNode(`Purchased Product ${i + 1} Long Descriptive Title\nQuantity: ${i === 0 ? 2 : 1}\n${i === 1 ? 'Item price $19.99\n' : ''}Delivered Sep ${i + 1}`, anchor));
const v0187OrderBody = {
  innerText: v0187Nodes.map(node => node.innerText).join('\n'), textContent: '', parentElement:null,
  querySelectorAll(selector) {
    if (selector.includes('a[href*="/dp/"]')) return v0187Anchors;
    return [];
  }
};
for (const node of v0187Nodes) node.parentElement = v0187OrderBody;
const v0187LineItems = p.extractOrderLineItems(v0187OrderBody);
assert(v0187LineItems.length === 6, 'canonical Order Details must capture all six purchased products');
assert(v0187LineItems[0].quantity === 2, 'explicit quantity must be captured');
assert(v0187LineItems[1].itemAmount === 19.99, 'direct labeled item price may be captured');
assert(v0187LineItems[2].itemAmount == null, 'item price must remain unknown when not directly proven');
assert(v0187LineItems.every(item => item.fulfillmentStatus && item.fulfillmentStatus.startsWith('Delivered')), 'per-product fulfillment status should remain item scoped');
console.log('v0.18.7 evidence and multi-product parser regressions passed');


// v0.18.7 DOM milestone evidence: only the stage with a real Amazon checkmark completes.
const v0187InitiatedRow = { innerText:'Aug 31\nInitiated', textContent:'Aug 31\nInitiated', parentElement:null };
const v0187Check = { parentElement:v0187InitiatedRow };
const v0187MilestoneDom = { querySelectorAll(selector) { return selector.includes('milestone_checkmark') ? [v0187Check] : []; } };
const v0187DomDone = p.extractCompletedReturnMilestonesFromDom(v0187MilestoneDom);
assert(v0187DomDone.started === true, 'Amazon checkmark next to Initiated must complete Initiated');
assert(v0187DomDone.shipped === false && v0187DomDone.received === false && v0187DomDone.refundIssued === false, 'one Initiated checkmark must not spill into later static labels');


// v0.18.8 Breville: three checkmarks mean Initiated, Dropped off, Return received only.
const v0188BrevilleText = `Aug 7\nInitiated\nAug 31\nDropped off\nSep 2\nReturn received\nSep 10\nRefund issued\nSep 17\nRefund credited\nYour return was received`;
const v0188Rows = ['Initiated','Dropped off','Return received'].map(label => ({ innerText:label, textContent:label, parentElement:null, getAttribute(){ return null; } }));
const v0188Checks = v0188Rows.map(row => ({ parentElement:row, getAttribute(){ return null; } }));
const v0188Timeline = { innerText:v0188BrevilleText, textContent:v0188BrevilleText, querySelectorAll(selector){ return selector.includes('milestone_checkmark') ? v0188Checks : []; }, getAttribute(){ return null; }, parentElement:null };
const v0188Dom = p.extractCompletedReturnMilestonesFromDom(v0188Timeline);
assert(v0188Dom.started && v0188Dom.shipped && v0188Dom.received, 'three structurally bound milestone checkmarks must complete first three Amazon stages');
assert(!v0188Dom.refundIssued && !v0188Dom.credited, 'future unchecked Refund issued/credited labels must stay incomplete');
const v0188Parsed = p.parseTextRecord(v0188BrevilleText, '113-1426991-3716216', {pageType:'return', url:'https://www.amazon.com/spr/returns/prep?orderId=113-1426991-3716216'});
assert(v0188Parsed.returnStage === 'received', 'Breville affirmative received evidence must classify as received');
assert(v0188Parsed.returnMilestones.received.done === true, 'received milestone must be explicit');
assert(v0188Parsed.returnMilestones.refundIssued.done === false && v0188Parsed.returnMilestones.credited.done === false, 'future refund labels must not complete');
console.log('v0.18.8 Breville lifecycle regressions passed');


// v0.18.9: detached Amazon HTML may retain checkmark markup for future stages. Affirmative
// lifecycle prose caps DOM checkmark evidence so future stages cannot be completed by element count.
function v0189Check(label, hidden=false) {
  const parent = {
    innerText: label, textContent: label, parentElement: null,
    hidden, className: hidden ? 'aok-hidden' : '',
    getAttribute(name) { if (name === 'class') return this.className; if (name === 'aria-hidden') return hidden ? 'true' : null; return null; }
  };
  return { parentElement: parent, hidden:false, className:'', getAttribute(){ return null; } };
}
function v0189TimelineContainer(text, labels, hiddenIndexes=[]) {
  const checks = labels.map((label,index) => v0189Check(label, hiddenIndexes.includes(index)));
  return { innerText:text, textContent:text, querySelectorAll(selector){ return selector.includes('milestone_checkmark') ? checks : []; }, getAttribute(){ return null; }, parentElement:null };
}
const v0189Breville = { recordType:'return', returnStage:'received', status:'returned_pending_refund', statusText:'Your return was received', returnMilestones:p.parseReturnMilestones('Your return was received') };
p.applyDomReturnMilestones(v0189Breville, v0189TimelineContainer('Your return was received\nAug 7\nInitiated\nAug 31\nDropped off\nSep 2\nReturn received\nSep 10\nRefund issued\nSep 17\nRefund credited', ['Initiated','Dropped off','Return received','Refund issued','Refund credited']));
assert(v0189Breville.returnStage === 'received', 'Breville affirmative received prose must cap future checkmark markup at Return received');
assert(v0189Breville.returnMilestones.refundIssued.done === false && v0189Breville.returnMilestones.credited.done === false, 'future refund stages must remain incomplete after received');
const v0189Washer = { recordType:'return', returnStage:'started', status:'return_in_progress', statusText:'Your return request is confirmed', returnMilestones:p.parseReturnMilestones('Your return request is confirmed') };
p.applyDomReturnMilestones(v0189Washer, v0189TimelineContainer('Your return request is confirmed\nInitiated\nDropped off\nReturn received\nRefund issued\nRefund credited', ['Initiated','Dropped off','Return received','Refund issued','Refund credited']));
assert(v0189Washer.returnStage === 'started', 'confirmed return request must not be promoted by future checkmark markup');
const v0189Rampow = { recordType:'return', returnStage:'refund_issued', status:'refunded', statusText:'$7.53 refund issued on Aug 18, 2026.', returnMilestones:p.parseReturnMilestones('$7.53 refund issued on Aug 18, 2026.') };
p.applyDomReturnMilestones(v0189Rampow, v0189TimelineContainer('$7.53 refund issued on Aug 18, 2026.\nInitiated\nDropped off\nReturn received\nRefund issued\nRefund credited', ['Initiated','Dropped off','Return received','Refund issued','Refund credited']));
assert(v0189Rampow.returnStage === 'refund_issued' && v0189Rampow.returnMilestones.credited.done === false, 'issued refund must not become credited from future checkmark markup');
assert(p.extractCompletedReturnMilestonesFromDom(v0189TimelineContainer('Initiated\nDropped off', ['Initiated','Dropped off'], [1])).shipped === false, 'explicitly hidden milestone checkmarks must not count');
console.log('v0.18.9 authoritative milestone regressions passed');


// v0.18.11 replacement workflow regressions (synthetic fixture only).
const replacementComplete = p.replacementEvidenceFromText(`Replacement complete\nThere's no need to return your item. Your replacement is complete.`);
assert(replacementComplete.detected && replacementComplete.stage === 'complete', 'replacement-complete text must be detected as replacement state');
assert(replacementComplete.noReturnRequired === true, 'explicit no-return-required replacement must be recognized');
const replacementNeedsOriginal = p.replacementEvidenceFromText(`Replacement ordered\nReturn the original item by Sep 20.`);
assert(replacementNeedsOriginal.detected && replacementNeedsOriginal.noReturnRequired === false, 'replacement without explicit no-return evidence must remain return-eligible');

const replacementProductAnchor = {
  getAttribute(name) { return name === 'href' ? '/dp/B0ABC12345' : null; },
  href:'/dp/B0ABC12345', innerText:'Synthetic Hydraulic Steering Rack', textContent:'Synthetic Hydraulic Steering Rack', parentElement:null
};
const replacementStatusAnchorV1811 = {
  getAttribute(name) { return name === 'href' ? '/spr/returns/prep?orderId=111-0000000-0000001&contractId=synthetic-contract&itemId=synthetic-item' : null; },
  href:'/spr/returns/prep?orderId=111-0000000-0000001&contractId=synthetic-contract&itemId=synthetic-item',
  innerText:'View return/refund status', textContent:'View return/refund status', parentElement:null
};
const replacementBlockText = `Order # 111-0000000-0000001\nReplacement complete\nThere's no need to return your item. Your replacement is complete.\nSynthetic Hydraulic Steering Rack`;
const replacementBlock = {
  innerText: replacementBlockText, textContent: replacementBlockText, parentElement:null,
  querySelectorAll(selector) {
    if (selector === 'a[href]') return [replacementProductAnchor, replacementStatusAnchorV1811];
    if (selector.includes('/dp/') || selector.includes('/gp/product/') || selector.includes('/product/')) return [replacementProductAnchor];
    return [];
  }
};
replacementProductAnchor.parentElement = replacementBlock;
replacementStatusAnchorV1811.parentElement = replacementBlock;
const replacementLinkDoc = { querySelectorAll(selector) { return selector === 'a[href]' ? [replacementStatusAnchorV1811] : []; } };
const syntheticReplacementLinks = p.extractReturnStatusLinks(replacementLinkDoc, 'https://www.amazon.com/gp/your-account/order-details?orderID=111-0000000-0000001');
assert(syntheticReplacementLinks.length === 1 && syntheticReplacementLinks[0].replacementOnly === true, 'no-return replacement management link must be marked replacement-only');
console.log('v0.18.11 replacement parser regressions passed');
