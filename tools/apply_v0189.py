from pathlib import Path
import json

R=Path('.')
def read(p): return (R/p).read_text(encoding='utf-8')
def write(p,s): (R/p).write_text(s,encoding='utf-8')
def once(s,a,b,label):
    n=s.count(a)
    if n!=1: raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return s.replace(a,b,1)
def replace_between(s,start_marker,end_marker,new,label):
    start=s.index(start_marker)
    end=s.index(end_marker,start)
    return s[:start]+new+s[end:]

# ---------- parser: structural/affirmative milestone evidence ----------
p=read('parser.js')
marker='  function extractCompletedReturnMilestonesFromDom(container) {'
helper=r'''  function affirmativeReturnStageFromText(text) {
    const lines = normalizeText(text).split('\n').map(line => line.trim()).filter(Boolean);
    if (lines.some(line => /(?:your refund (?:has been|was) credited|we (?:have )?credited your refund|refund (?:has been|was) credited to|credited to your (?:original )?payment method on)/i.test(line))) return 'credited';
    if (lines.some(line => /(?:we (?:have )?issued your refund|your refund (?:has been|was) issued|refund has been issued|refund issued\s+(?:on|\$))/i.test(line))) return 'refund_issued';
    if (lines.some(line => /(?:we (?:have )?received your return|your return (?:has been|was) received|received your return|item (?:has been|was) received|return processed|your return is complete|return (?:has been|was) completed|return received\s+(?:on|at)\b)/i.test(line))) return 'received';
    if (lines.some(line => {
      if (/(?:drop off your return by|drop-off your return by|please drop off|once you drop off|when you drop off|time you have dropped off|after you drop off|before you drop off)/i.test(line)) return false;
      return /(?:your return (?:has been|was) dropped off|you (?:have )?dropped off your return|drop-?off complete|return (?:is|has been) in transit|on the way back|return (?:has been|was) shipped|shipped back|carrier (?:has )?received (?:your )?return|dropped off\s+(?:on|at)\b)/i.test(line);
    })) return 'shipped';
    if (lines.some(line => /(?:return request (?:is )?(?:confirmed|accepted)|return initiated|return started|accepted your return)/i.test(line))) return 'started';
    return 'unknown';
  }

  function explicitlyHiddenMilestoneNode(node) {
    let current = node || null;
    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
      if (current.hidden === true) return true;
      const ariaHidden = String(current.getAttribute?.('aria-hidden') || '').toLowerCase();
      if (ariaHidden === 'true') return true;
      const style = String(current.getAttribute?.('style') || '').toLowerCase();
      if (/(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\D|$))/.test(style)) return true;
      const cls = typeof current.className === 'string' ? current.className : String(current.getAttribute?.('class') || '');
      if (/(?:^|\s)(?:aok-hidden|a-hidden|hidden|is-hidden|visually-hidden|milestone-hidden)(?:\s|$)/i.test(cls)) return true;
    }
    return false;
  }

'''
p=p.replace(marker,helper+marker,1)
start=p.index('  function extractCompletedReturnMilestonesFromDom(container) {')
end=p.index('\n\n  function applyDomReturnMilestones(record, container) {',start)
new_extract=r'''  function extractCompletedReturnMilestonesFromDom(container) {
    const done = { started: false, shipped: false, received: false, refundIssued: false, credited: false };
    if (!container?.querySelectorAll) return done;
    let checks = [];
    try { checks = Array.from(container.querySelectorAll('img[src*="milestone_checkmark" i], img[data-src*="milestone_checkmark" i], img[alt*="checkmark" i]')); } catch (_) {}
    const stageForLabel = line => {
      const value = normalizeText(line).toLowerCase();
      if (value === 'initiated' || value === 'return initiated' || value === 'return started') return 'started';
      if (value === 'drop off' || value === 'dropped off' || value === 'return shipped') return 'shipped';
      if (value === 'return received') return 'received';
      if (value === 'refund issued') return 'refundIssued';
      if (value === 'refund credited' || value === 'credited') return 'credited';
      return null;
    };
    // Do not infer completion from the number of checkmark image elements. Amazon can retain
    // future/hidden checkmark markup in detached return HTML. A checkmark is usable only when its
    // own non-hidden local milestone container binds it to exactly one stage label.
    for (const check of checks) {
      if (explicitlyHiddenMilestoneNode(check)) continue;
      let current = check.parentElement || null;
      for (let depth = 0; current && depth < 7; depth += 1, current = current.parentElement) {
        if (explicitlyHiddenMilestoneNode(current)) break;
        const text = normalizeText(current.innerText || current.textContent || '');
        if (!text || text.length > 650) continue;
        const labels = Array.from(new Set(text.split('\n').map(stageForLabel).filter(Boolean)));
        if (labels.length === 1) { done[labels[0]] = true; break; }
        if (labels.length > 1) break;
      }
    }
    if (done.credited) done.refundIssued = true;
    if (done.refundIssued) done.received = true;
    if (done.received) done.shipped = true;
    if (done.shipped) done.started = true;
    return done;
  }'''
p=p[:start]+new_extract+p[end:]
start=p.index('  function applyDomReturnMilestones(record, container) {')
end=p.index('\n\n  function classifyStatus(text, recordType) {',start)
new_apply=r'''  function applyDomReturnMilestones(record, container) {
    if (!record || record.recordType !== 'return') return record;
    const rawText = normalizeText(container?.innerText || container?.textContent || '');
    const affirmativeStage = affirmativeReturnStageFromText(rawText);
    const rank = { unknown:0, started:1, shipped:2, received:3, refund_issued:4, credited:5 };
    const affirmativeRank = rank[affirmativeStage] || 0;
    const dom = extractCompletedReturnMilestonesFromDom(container);
    if (affirmativeRank > 0) {
      if (affirmativeRank < 5) dom.credited = false;
      if (affirmativeRank < 4) dom.refundIssued = false;
      if (affirmativeRank < 3) dom.received = false;
      if (affirmativeRank < 2) dom.shipped = false;
      if (affirmativeRank < 1) dom.started = false;
    }
    if (!Object.values(dom).some(Boolean)) return record;
    const milestones = record.returnMilestones || parseReturnMilestones(record.statusText || '');
    for (const key of ['started', 'shipped', 'received', 'refundIssued', 'credited']) {
      if (!dom[key]) continue;
      const labels = key === 'started' ? ['Initiated','Return initiated','Return started'] : key === 'shipped' ? ['Dropped off','Drop off','Return shipped','Shipped'] : key === 'received' ? ['Return received','Received'] : key === 'refundIssued' ? ['Refund issued'] : ['Refund credited','Credited'];
      milestones[key] = { ...(milestones[key] || {}), done: true, date: milestones[key]?.date || findMilestoneDate(rawText, labels) || null };
    }
    const domStage = dom.credited ? 'credited' : dom.refundIssued ? 'refund_issued' : dom.received ? 'received' : dom.shipped ? 'shipped' : dom.started ? 'started' : 'unknown';
    const textStage = parseReturnMilestones(rawText).stage || 'unknown';
    let stage = (rank[domStage] || 0) > (rank[textStage] || 0) ? domStage : textStage;
    if (affirmativeRank > 0 && (rank[stage] || 0) > affirmativeRank) stage = affirmativeStage;
    milestones.stage = stage;
    record.returnMilestones = milestones;
    record.returnStage = stage;
    if ((rank[stage] || 0) >= 4) record.status = 'refunded';
    else if (stage === 'received') record.status = 'returned_pending_refund';
    else if ((rank[stage] || 0) >= 1) record.status = 'return_in_progress';
    return record;
  }'''
p=p[:start]+new_apply+p[end:]
p=once(p,'    extractCompletedReturnMilestonesFromDom,\n    parseTextRecord,','    affirmativeReturnStageFromText,\n    extractCompletedReturnMilestonesFromDom,\n    applyDomReturnMilestones,\n    parseTextRecord,','parser exports')
write('parser.js',p)

# ---------- content: five-stage inline UI and atomic detail+return completion ----------
c=read('content.js')
start=c.index('  function inlineReturnCard(record) {')
end=c.index('\n\n  async function decorateReturnsOnPage()',start)
new_inline=r'''  function inlineReturnCard(record) {
    const progress = storage.returnProgress(record);
    const item = record.itemNames?.[0] || `Return for order ${record.orderId}`;
    const amount = Number.isFinite(Number(record.refundAmount)) ? `$${Number(record.refundAmount).toFixed(2)}` : '';
    const expectedCredit = !progress.amazonCredited ? (record.expectedCreditDate || record?.returnMilestones?.expectedCreditDate || '') : '';
    const orderDetailsUrl = record.orderDetailsUrl && /(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details)/i.test(record.orderDetailsUrl) ? record.orderDetailsUrl : '';
    const steps = [
      ['started', 'Initiated', progress.started, milestoneDate(record, 'started')],
      ['shipped', 'Dropped off', progress.shipped, milestoneDate(record, 'shipped')],
      ['received', 'Return received', progress.received, milestoneDate(record, 'received')],
      ['refundIssued', 'Refund issued', progress.refundIssued, milestoneDate(record, 'refundIssued')],
      ['credited', progress.amazonCredited ? 'Refund credited' : (expectedCredit ? `Expected ${expectedCredit}` : 'Refund credited'), progress.amazonCredited, progress.amazonCredited ? milestoneDate(record, 'credited') : '']
    ];
    const esc = value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    return `<section class="return-box">
      <div class="head"><div><b>${esc(inlineStageLabel(progress.stage))}</b><span>${esc(item)}</span></div>${amount ? `<strong>${esc(amount)}</strong>` : ''}</div>
      <div class="track"><div class="rail"><i style="width:${progress.percent}%"></i></div>
        ${steps.map(step => `<div class="step ${step[2] ? 'done' : ''}"><em>${step[2] ? '✓' : ''}</em><small>${esc(step[3] || '')}</small><span>${esc(step[1])}</span></div>`).join('')}
      </div>
      ${orderDetailsUrl ? `<a href="${esc(orderDetailsUrl)}" target="_blank" rel="noopener">Open order details</a>` : ''}
    </section>`;
  }'''
c=c[:start]+new_inline+c[end:]
c=c.replace('.track{position:relative;display:grid;grid-template-columns:repeat(4,1fr);', '.track{position:relative;display:grid;grid-template-columns:repeat(5,1fr);',1)
seg_start=c.index('          const returnRefreshes = [];', c.index("if (message.type === 'ARL_WORKER_FETCH_DETAIL')"))
seg_end_marker="          return { ok: true, ...parsed, save, scannedUrl: finalUrl, fetchedOrderDetails: true, returnRefreshes };"
seg_end=c.index(seg_end_marker,seg_start)+len(seg_end_marker)
new_seg=r'''          const returnRefreshes = [];
          const validReturnLinks = (parsed.returnLinks || []).filter(link => link?.orderId === orderId && link?.url && /\/spr\/returns\/prep/i.test(String(link.url)));
          for (const link of validReturnLinks) {
            const returnUrl = new URL(link.url, finalUrl);
            if (!/(^|\.)amazon\.com$/i.test(returnUrl.hostname) || !/\/spr\/returns\/prep/i.test(returnUrl.pathname)) continue;
            const returnResponse = await fetch(returnUrl.toString(), { credentials: 'include', cache: 'no-store', redirect: 'follow' });
            if (!returnResponse.ok) {
              const returnRateLimited = returnResponse.status === 429 || returnResponse.status === 503;
              return { ok: false, rateLimited: returnRateLimited, error: returnRateLimited ? 'Amazon throttled the return-status refresh.' : `Amazon return status returned HTTP ${returnResponse.status}.` };
            }
            const returnHtml = await returnResponse.text();
            const returnProbe = String(returnHtml || '').replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ');
            const returnBlocked = /sorry,? we just need to make sure|not a robot|enter the characters you see below|type the characters you see|captcha/i.test(returnProbe);
            const returnSignIn = /email or mobile phone number|enter your password|<title>\s*amazon sign-in/i.test(returnProbe);
            if (returnBlocked || returnSignIn) return { ok: false, blocked: true, error: returnBlocked ? 'Amazon requested human verification during return refresh.' : 'Amazon requires sign-in during return refresh.' };
            const returnDoc = new DOMParser().parseFromString(returnHtml, 'text/html');
            const returnFinalUrl = returnResponse.url || returnUrl.toString();
            const returnParsed = parser.parseDocument(returnDoc, returnFinalUrl);
            let returnRecords = (returnParsed.records || []).filter(record => record?.recordType === 'return' && record?.orderId === orderId && record?.authoritativeReturnCapture);
            returnRecords = applySingleReturnIdentityHint(returnRecords, link).filter(record => record?.recordType === 'return' && record?.authoritativeReturnCapture);
            if (!returnRecords.length) return { ok: false, error: `Return status for ${orderId} did not contain an authoritative return record.` };
            const returnSave = await storage.upsertRecords(returnRecords);
            returnRefreshes.push({ url: returnFinalUrl, records: returnRecords.length, save: returnSave });
          }
          const expectedReturns = validReturnLinks.length;
          const authoritativeReturns = returnRefreshes.length;
          if (authoritativeReturns !== expectedReturns) return { ok: false, error: `Only ${authoritativeReturns}/${expectedReturns} return-status pages completed for ${orderId}.` };
          await storage.updateRecord(`order:${orderId}`, {
            orderDataComplete: true,
            processingState: 'complete',
            processingError: null,
            processingErrorAt: null,
            processingLastIssue: null,
            returnStatusExpectedCount: expectedReturns,
            returnStatusAuthoritativeCount: authoritativeReturns,
            returnStatusComplete: true,
            orderDataCompletedAt: new Date().toISOString()
          });
          return { ok: true, ...parsed, save, scannedUrl: finalUrl, fetchedOrderDetails: true, returnRefreshes, orderDataComplete: true, returnStatusExpectedCount: expectedReturns, returnStatusAuthoritativeCount: authoritativeReturns };'''
c=c[:seg_start]+new_seg+c[seg_end:]
write('content.js',c)

# ---------- background: processing/error state and ready-only page completion ----------
b=read('background.js')
insert='async function forceRefreshOrder(orderId) {'
helper=r'''async function patchOrderProcessing(orderId, patch) {
  const id = String(orderId || '').trim();
  if (!/^\d{3}-\d{7}-\d{7}$/.test(id)) return false;
  const data = await chrome.storage.local.get([LEDGER_KEY]);
  const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
  const index = ledger.findIndex(r => r?.recordType === 'order' && r?.orderId === id);
  if (index < 0) return false;
  ledger[index] = { ...ledger[index], ...patch, lastScannedAt: nowIso() };
  await chrome.storage.local.set({ [LEDGER_KEY]: ledger });
  return true;
}

'''
b=b.replace(insert,helper+insert,1)
b=once(b,
"    return { ok: true, orderId: id, detailScannedAt: nowIso(), returnsRefreshed };\n  } finally {",
"    await patchOrderProcessing(id, { orderDataComplete: true, processingState: 'complete', processingError: null, processingErrorAt: null, processingLastIssue: null, returnStatusExpectedCount: uniqueReturnLinks.size, returnStatusAuthoritativeCount: returnsRefreshed, returnStatusComplete: returnsRefreshed === uniqueReturnLinks.size, orderDataCompletedAt: nowIso() });\n    return { ok: true, orderId: id, detailScannedAt: nowIso(), returnsRefreshed };\n  } catch (error) {\n    await patchOrderProcessing(id, { processingState: 'error', processingError: `refresh: ${error?.message || error}`.slice(0, 500), processingErrorAt: nowIso() });\n    throw error;\n  } finally {",
'force refresh processing')
b=once(b,
"  const detailed = new Set(ledger.filter(r => r?.recordType === 'order' && r?.detailScanComplete).map(r => r.orderId));\n  return ids.every(id => state.crawl?.completedOrders?.[id] || detailed.has(id));",
"  const ready = new Set(ledger.filter(r => r?.recordType === 'order' && r?.orderDataComplete === true).map(r => r.orderId));\n  return ids.every(id => state.crawl?.completedOrders?.[id] || ready.has(id));",
'page complete ready gate')
b=once(b,
"  if (job.type === 'detail') {\n    // Keep the worker parked on Amazon and fetch the canonical Order Details HTML through the",
"  if (job.type === 'detail') {\n    await patchOrderProcessing(job.orderId, { processingState: 'processing', processingError: null, processingErrorAt: null });\n    // Keep the worker parked on Amazon and fetch the canonical Order Details HTML through the",
'processing start')
needle="    completionState.processed += 1;\n    if (jobError && !waitingForDetails) {"
replacement="    completionState.processed += 1;\n    if (job.type === 'detail' && job.orderId) {\n      const nextAttempt = Number(job.attempts || 0) + (waitingForDetails ? 0 : 1);\n      if (success) {\n        await patchOrderProcessing(job.orderId, { processingState: 'complete', processingError: null, processingErrorAt: null, processingLastIssue: null });\n      } else if (jobError && (blocked || (!rateLimited && !waitingForDetails && nextAttempt >= 3))) {\n        await patchOrderProcessing(job.orderId, { processingState: 'error', processingError: jobError, processingErrorAt: nowIso(), processingLastIssue: jobError });\n      } else if (jobError) {\n        await patchOrderProcessing(job.orderId, { processingState: 'retrying', processingError: null, processingErrorAt: null, processingLastIssue: jobError });\n      }\n    }\n    if (jobError && !waitingForDetails) {"
b=once(b,needle,replacement,'job processing state')
write('background.js',b)

# ---------- dashboard HTML: views + filters ----------
h=read('dashboard.html')
h=once(h,
'''      <button class="view-button" data-view="needs_review">Needs review <span id="navReviewCount">0</span></button>''',
'''      <button class="view-button" data-view="needs_review">Needs review <span id="navReviewCount">0</span></button>\n      <button class="view-button" data-view="processing">Processing <span id="navProcessingCount">0</span></button>\n      <button class="view-button" data-view="errors">Errors <span id="navErrorCount">0</span></button>''',
'view buttons')
h=once(h,
'''    <section class="panel filters filters-one">\n      <input id="search" type="search" placeholder="Search item, order ID, status, or card">\n    </section>''',
'''    <section class="panel filters ledger-filters">\n      <input id="search" type="search" placeholder="Search order ID, product, ASIN, status, or card">\n      <select id="statusFilter" aria-label="Filter by order or return status">\n        <option value="all">All statuses</option>\n        <option value="no_return">No return</option>\n        <option value="return_started">Return started</option>\n        <option value="dropped_off">Dropped off</option>\n        <option value="return_received">Return received</option>\n        <option value="refund_issued">Refund issued</option>\n        <option value="refund_credited">Refund credited</option>\n        <option value="needs_review">Needs review</option>\n        <option value="cancelled">Cancelled</option>\n      </select>\n      <select id="yearFilter" aria-label="Filter by order year"><option value="all">All years</option></select>\n      <select id="cardFilter" aria-label="Filter by payment card"><option value="all">All cards</option></select>\n      <select id="sortOrder" aria-label="Sort orders">\n        <option value="newest">Newest first</option>\n        <option value="oldest">Oldest first</option>\n        <option value="order_high">Order total: high to low</option>\n        <option value="order_low">Order total: low to high</option>\n        <option value="refund_high">Refund: high to low</option>\n        <option value="refund_low">Refund: low to high</option>\n        <option value="status">Status</option>\n        <option value="order_id">Order ID</option>\n      </select>\n    </section>''',
'filter controls')
write('dashboard.html',h)

# ---------- dashboard JS: complete-only views + query controls ----------
d=read('dashboard.js')
d=once(d,"  const search = document.getElementById('search');","  const search = document.getElementById('search');\n  const statusFilter = document.getElementById('statusFilter');\n  const yearFilter = document.getElementById('yearFilter');\n  const cardFilter = document.getElementById('cardFilter');\n  const sortOrder = document.getElementById('sortOrder');",'filter element refs')
d=once(d,"  const navReviewCount = document.getElementById('navReviewCount');","  const navReviewCount = document.getElementById('navReviewCount');\n  const navProcessingCount = document.getElementById('navProcessingCount');\n  const navErrorCount = document.getElementById('navErrorCount');",'nav refs')
d=once(d,"  if (!['all', 'returns', 'needs_review'].includes(currentView)) currentView = 'all';","  if (!['all', 'returns', 'needs_review', 'processing', 'errors'].includes(currentView)) currentView = 'all';",'view allowlist')
start=d.index('  function buildRows() {')
end=d.index('\n\n  function lifecycleMarkup(group, index, totalGroups) {',start)
new_build=r'''  function buildRows() {
    const orders = new Map();
    const returns = new Map();
    for (const record of ledger) {
      if (!record?.orderId) continue;
      if (record.recordType === 'order') {
        const prior = orders.get(record.orderId);
        if (!prior || (record.detailScanComplete && !prior.detailScanComplete) || String(record.lastScannedAt || '') > String(prior.lastScannedAt || '')) orders.set(record.orderId, record);
      } else if (record.recordType === 'return') {
        if (!returns.has(record.orderId)) returns.set(record.orderId, []);
        returns.get(record.orderId).push(record);
      }
    }

    const ids = new Set([...orders.keys(), ...returns.keys()]);
    const rows = [];
    for (const orderId of ids) {
      const order = orders.get(orderId) || null;
      const allReturnRecords = dedupeReturns(returns.get(orderId) || []);
      const terminalCancelled = Boolean(order?.historyTerminalComplete === true && order?.historyTerminalState === 'cancelled');
      const expectedReturnCount = Number.isFinite(Number(order?.returnStatusExpectedCount)) ? Number(order.returnStatusExpectedCount) : 0;
      const authoritativeCount = Number.isFinite(Number(order?.returnStatusAuthoritativeCount)) ? Number(order.returnStatusAuthoritativeCount) : 0;
      const dataComplete = terminalCancelled || Boolean(order?.orderDataComplete === true && authoritativeCount >= expectedReturnCount);
      const processingError = String(order?.processingError || '').trim() || null;
      const authoritativeReturns = allReturnRecords.filter(record => record?.authoritativeReturnCapture === true);
      const returnRecords = dataComplete && expectedReturnCount > 0 ? authoritativeReturns : allReturnRecords;
      const returnGroups = groupReturnRecords(returnRecords);
      const itemJoin = itemModel?.joinOrderItems(order, returnGroups) || { items: [], unmatchedReturnGroups: returnGroups.map(group => ({ group, identityStrength: 'weak', bestScore: 0 })), returnedProductCount: 0 };
      const strongUnmatchedReturnIdentity = itemJoin.unmatchedReturnGroups.some(entry => entry.identityStrength === 'strong');
      const manualReconciled = returnRecords.some(r => r.manualState === 'reconciled');
      const ranks = returnRecords.map(r => storage.returnStageRank(r));
      const hasReturn = returnRecords.length > 0;
      const allAmazonCredited = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.credited);
      const allIssued = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.refund_issued);
      const bankAmazonConflict = hasReturn && returnRecords.some(r => storage.hasAmazonBankConflict(r));

      const capturedOrderItemNames = uniqueStrings(order?.itemNames || []);
      const structuredOrderItemNames = uniqueStrings(itemJoin.items.map(item => item.itemName));
      const orderItemNames = structuredOrderItemNames.length ? structuredOrderItemNames : capturedOrderItemNames;
      const returnedItemNames = uniqueStrings(returnGroups.flatMap(group => group.itemNames || []));
      const childRefundAmount = returnGroups.reduce((total, group) => total + (Number.isFinite(Number(group.amount)) ? Number(group.amount) : 0), 0);
      const canonicalRefundCandidate = order?.canonicalRefundTotal;
      const canonicalRefundTotal = canonicalRefundCandidate !== null && canonicalRefundCandidate !== undefined && canonicalRefundCandidate !== '' && Number.isFinite(Number(canonicalRefundCandidate)) ? Number(canonicalRefundCandidate) : null;
      const refundAmount = canonicalRefundTotal != null ? canonicalRefundTotal : (returnGroups.some(g => Number.isFinite(Number(g.amount))) ? childRefundAmount : null);
      const refundAmountMismatch = canonicalRefundTotal != null && childRefundAmount > canonicalRefundTotal + 0.011;
      const itemIdentityConflict = returnGroups.some(group => group.itemIdentityConflict);
      const groupAmountConflict = returnGroups.some(group => group.amountConflict);
      const needsReview = dataComplete && hasReturn && !manualReconciled && (
        returnRecords.some(r => storage.needsCreditReview(r)) || refundAmountMismatch || itemIdentityConflict || groupAmountConflict || strongUnmatchedReturnIdentity || bankAmazonConflict
      );

      const lowestReturn = returnRecords.slice().sort((a,b) => storage.returnStageRank(a) - storage.returnStageRank(b))[0] || null;
      let stateKey = 'purchase';
      let statusLabel = order?.statusText || (order?.detailScanComplete ? 'Order details captured' : 'Order discovered');
      if (!dataComplete) { stateKey = processingError ? 'error' : 'processing'; statusLabel = processingError ? 'Processing error' : (order?.processingState === 'retrying' ? 'Retrying' : 'Processing'); }
      else if (terminalCancelled && !hasReturn) { stateKey = 'cancelled'; statusLabel = 'Cancelled'; }
      else if (manualReconciled) { stateKey = 'reconciled'; statusLabel = 'Reconciled'; }
      else if (needsReview) {
        stateKey = 'needs_review';
        if (refundAmountMismatch) statusLabel = 'Refund amount mismatch';
        else if (itemIdentityConflict) statusLabel = 'Item needs review';
        else if (groupAmountConflict) statusLabel = 'Return refund needs review';
        else if (strongUnmatchedReturnIdentity) statusLabel = 'Returned item needs matching';
        else if (bankAmazonConflict) statusLabel = 'Bank/Amazon status conflict';
        else statusLabel = stageLabel(storage.getReturnStage(lowestReturn));
      } else if (allAmazonCredited) { stateKey = 'credited'; statusLabel = 'Amazon credited'; }
      else if (allIssued) { stateKey = 'refund_issued'; statusLabel = 'Refund issued'; }
      else if (hasReturn) { stateKey = 'return'; statusLabel = stageLabel(storage.getReturnStage(lowestReturn)); }

      const statusTexts = uniqueStrings(returnRecords.map(r => r.statusText).filter(Boolean));
      const lastScannedAt = [order?.lastScannedAt, ...returnRecords.map(r => r.lastScannedAt)].filter(Boolean).sort().at(-1) || null;
      const itemNames = orderItemNames.length ? orderItemNames : returnedItemNames;
      const asins = uniqueStrings([...(order?.asins || []), ...(order?.orderItems || []).map(item => item?.asin), ...returnRecords.flatMap(r => r.asins || [])]);
      const orderDate = order?.orderDate || null;
      const orderYearMatch = String(orderDate || '').match(/\b(20\d{2})\b/);
      const orderYear = orderYearMatch ? orderYearMatch[1] : null;
      const parsedOrderDate = orderDate ? new Date(orderDate) : null;
      const sortTime = parsedOrderDate && !Number.isNaN(parsedOrderDate.getTime()) ? parsedOrderDate.getTime() : (lastScannedAt ? new Date(lastScannedAt).getTime() : 0);
      rows.push({
        orderId, order, returns: returnRecords, allReturns: allReturnRecords, returnGroups, hasReturn, needsReview, terminalCancelled, stateKey, statusLabel,
        dataComplete, processingError, processingState: order?.processingState || null, expectedReturnCount, authoritativeCount,
        itemStates: itemJoin.items, unmatchedReturnGroups: itemJoin.unmatchedReturnGroups, returnedProductCount: itemJoin.returnedProductCount,
        itemNames, orderItemNames, returnedItemNames, searchItemNames: uniqueStrings([...orderItemNames, ...returnedItemNames]), asins,
        orderTotal: order?.purchaseAmount ?? null, refundAmount, canonicalRefundTotal, childRefundAmount,
        refundAmountMismatch, itemIdentityConflict, groupAmountConflict, strongUnmatchedReturnIdentity, bankAmazonConflict,
        cardLast4: order?.cardLast4 || returnRecords.find(r => r.cardLast4)?.cardLast4 || null,
        amazonStatus: statusTexts.length ? statusTexts.join(' · ') : (order?.statusText || order?.status || '—'),
        detailComplete: Boolean(order?.detailScanComplete), detailScannedAt: order?.detailScannedAt || null,
        orderDate, orderYear, sortTime,
        lastScannedAt, openUrl: canonicalDetailUrl(orderId, order)
      });
    }
    return rows;
  }'''
d=d[:start]+new_build+d[end:]
start=d.index('  function filteredRows() {')
end=d.index('\n\n  function sum(rows, field)',start)
new_filtered=r'''  function setDynamicOptions(select, values, allLabel) {
    if (!select) return;
    const prior = select.value || 'all';
    select.innerHTML = `<option value="all">${esc(allLabel)}</option>` + values.map(value => `<option value="${esc(value)}">${esc(value)}</option>`).join('');
    select.value = values.includes(prior) || prior === 'all' ? prior : 'all';
  }

  function refreshDynamicFilters(rows) {
    const years = uniqueStrings(rows.map(row => row.orderYear).filter(Boolean)).sort((a,b) => Number(b)-Number(a));
    const cards = uniqueStrings(rows.map(row => row.cardLast4).filter(Boolean)).sort().map(value => `•••• ${value}`);
    setDynamicOptions(yearFilter, years, 'All years');
    setDynamicOptions(cardFilter, cards, 'All cards');
  }

  function rowMatchesStatus(row, value) {
    if (!value || value === 'all') return true;
    if (value === 'no_return') return row.dataComplete && !row.hasReturn && !row.terminalCancelled;
    if (value === 'needs_review') return row.needsReview;
    if (value === 'cancelled') return row.terminalCancelled;
    const target = { return_started:'started', dropped_off:'shipped', return_received:'received', refund_issued:'refund_issued', refund_credited:'credited' }[value];
    if (!target) return true;
    return (row.returns || []).some(record => storage.getReturnStage(record) === target);
  }

  function sortRows(rows) {
    const mode = sortOrder?.value || 'newest';
    const numeric = (row, field) => Number.isFinite(Number(row[field])) ? Number(row[field]) : -Infinity;
    return rows.slice().sort((a,b) => {
      if (mode === 'oldest') return (a.sortTime || 0) - (b.sortTime || 0);
      if (mode === 'order_high') return numeric(b,'orderTotal') - numeric(a,'orderTotal');
      if (mode === 'order_low') return numeric(a,'orderTotal') - numeric(b,'orderTotal');
      if (mode === 'refund_high') return numeric(b,'refundAmount') - numeric(a,'refundAmount');
      if (mode === 'refund_low') return numeric(a,'refundAmount') - numeric(b,'refundAmount');
      if (mode === 'status') return String(a.statusLabel || '').localeCompare(String(b.statusLabel || '')) || String(a.orderId).localeCompare(String(b.orderId));
      if (mode === 'order_id') return String(a.orderId).localeCompare(String(b.orderId));
      return (b.sortTime || 0) - (a.sortTime || 0);
    });
  }

  function filteredRows() {
    const allRows = buildRows();
    refreshDynamicFilters(allRows);
    const q = search.value.trim().toLowerCase();
    const selectedCard = String(cardFilter?.value || 'all').replace(/\D/g,'').slice(-4);
    const selectedYear = yearFilter?.value || 'all';
    const selectedStatus = statusFilter?.value || 'all';
    const rows = allRows.filter(row => {
      if (currentView === 'all' && !row.dataComplete) return false;
      if (currentView === 'returns' && (!row.dataComplete || !row.hasReturn)) return false;
      if (currentView === 'needs_review' && (!row.dataComplete || !row.needsReview)) return false;
      if (currentView === 'processing' && (row.dataComplete || row.processingError)) return false;
      if (currentView === 'errors' && !row.processingError) return false;
      if (selectedYear !== 'all' && row.orderYear !== selectedYear) return false;
      if (cardFilter?.value !== 'all' && String(row.cardLast4 || '') !== selectedCard) return false;
      if (!rowMatchesStatus(row, selectedStatus)) return false;
      if (q) {
        const hay = [row.orderId, ...(row.searchItemNames || row.itemNames), ...(row.asins || []), row.cardLast4, row.statusLabel, row.amazonStatus, row.processingError, row.orderTotal, row.refundAmount].join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    return sortRows(rows);
  }'''
d=d[:start]+new_filtered+d[end:]
start=d.index('  function renderStats() {')
end=d.index('\n\n  function renderViewMenu()',start)
new_stats=r'''  function renderStats() {
    const allRows = buildRows();
    const rows = allRows.filter(r => r.dataComplete);
    const processingRows = allRows.filter(r => !r.dataComplete && !r.processingError);
    const errorRows = allRows.filter(r => Boolean(r.processingError));
    const returnRows = rows.filter(r => r.hasReturn);
    const reviewRows = rows.filter(r => r.needsReview);
    const detailed = rows.filter(r => r.detailComplete);
    const issued = rows.filter(r => r.hasReturn && r.returns.every(ret => storage.returnStageRank(ret) >= storage.RETURN_STAGE_RANK.refund_issued));
    const bankCredited = rows.filter(r => r.hasReturn && r.returns.every(ret => storage.isBankCreditConfirmed(ret)));
    const reviewExpectedTotal = reviewRows.reduce((total, row) => total + needsReviewExpectedAmount(row), 0);
    navAllCount.textContent = String(rows.length);
    navReturnCount.textContent = String(returnRows.length);
    navReviewCount.textContent = String(reviewRows.length);
    navProcessingCount.textContent = String(processingRows.length);
    navErrorCount.textContent = String(errorRows.length);
    stats.innerHTML = `
      <div class="stat"><span>Complete orders</span><strong>${rows.length}</strong><small>${money(sum(rows, 'orderTotal'))} captured order total</small></div>
      <div class="stat"><span>Order details</span><strong>${detailed.length}</strong><small>Fully processed canonical orders</small></div>
      <div class="stat"><span>Returns</span><strong>${returnRows.length}</strong><small>${money(sum(returnRows, 'refundAmount'))} expected refunds</small></div>
      <div class="stat stat-review-total"><span>Needs review</span><strong>${money(reviewExpectedTotal)}</strong><small>${reviewRows.length} flagged ${reviewRows.length === 1 ? 'order' : 'orders'}</small></div>
      <div class="stat"><span>Processing</span><strong>${processingRows.length}</strong><small>Hidden from completed ledger</small></div>
      <div class="stat"><span>Errors</span><strong>${errorRows.length}</strong><small>Require retry or investigation</small></div>`;
  }'''
d=d[:start]+new_stats+d[end:]
start=d.index('  function renderTable() {')
end=d.index('\n\n  function render() {',start)
new_table=r'''  function renderTable() {
    const rows = filteredRows();
    empty.classList.toggle('hidden', rows.length !== 0);
    body.innerHTML = rows.map(row => {
      const fullItemTitle = row.itemNames.length ? row.itemNames.join(' · ') : '';
      const items = row.itemStates?.length > 1 ? `${row.itemStates.length} products · ${row.returnedProductCount || 0} returned` : (fullItemTitle || (row.hasReturn ? `${row.returnGroups.length} return${row.returnGroups.length === 1 ? '' : 's'} pending item identity` : 'Item title pending Order Details scan'));
      const detailBadge = row.terminalCancelled ? `<span class="badge">Terminal history</span>` : row.dataComplete ? `<span class="badge badge-reconciled">Complete</span>` : row.processingError ? '<span class="badge badge-error">Error</span>' : '<span class="badge badge-processing">Processing</span>';
      const bankConfirmed = row.dataComplete && row.hasReturn && row.returns.length && row.returns.every(ret => storage.isBankCreditConfirmed(ret));
      const anyIssued = row.dataComplete && row.hasReturn && row.returns.some(ret => storage.returnStageRank(ret) >= storage.RETURN_STAGE_RANK.refund_issued);
      const financialState = !row.dataComplete ? '' : row.bankAmazonConflict ? '<span class="credit-state credit-pending">Bank/Amazon conflict</span>' : bankConfirmed ? '<span class="credit-state credit-confirmed">Bank confirmed</span>' : anyIssued ? '<span class="credit-state credit-pending">Credit pending</span>' : '';
      const progressMarkup = row.processingError
        ? `<div class="processing-error"><strong>Order processing error</strong><span>${esc(row.processingError)}</span><small>Use Refresh to retry this order after the underlying Amazon issue is resolved.</small></div>`
        : !row.dataComplete
          ? `<div class="processing-state"><strong>${esc(row.processingState === 'retrying' ? 'Retrying order data' : 'Processing order data')}</strong><span>${esc(row.order?.processingLastIssue || `${row.authoritativeCount}/${row.expectedReturnCount} return-status pages complete`)}</span></div>`
          : `${orderProductStatusMarkup(row)}${financialState}`;
      return `<article class="ledger-order-card ledger-order-line ${row.hasReturn ? 'return-card-row' : ''} ${row.needsReview ? 'needs-review-card' : ''} ${row.processingError ? 'processing-error-card' : ''}">
        <div class="line-status">
          <span class="badge badge-${esc(row.stateKey)}">${esc(badgeLabel(row))}</span>
          <div class="detail-line compact-detail">${detailBadge}</div>
        </div>
        <div class="line-order-item">
          <div class="line-order-meta"><span class="mono">${esc(row.orderId)}</span><span class="muted tiny">${formatDate(row.orderDate || row.lastScannedAt)}</span></div>
          <div class="item-title line-item-title" title="${esc(fullItemTitle || items)}">${esc(items)}</div>
          <div class="muted tiny line-amazon-status" title="${esc(row.amazonStatus || '—')}">${esc(row.amazonStatus || '—')}</div>
        </div>
        <div class="line-metric"><span>Order</span><strong>${money(row.orderTotal)}</strong></div>
        <div class="line-metric"><span>Refund</span><strong class="refund-money">${money(row.refundAmount)}</strong></div>
        <div class="line-metric"><span>Card</span><strong>${row.cardLast4 ? `•••• ${esc(row.cardLast4)}` : '—'}</strong></div>
        <div class="line-progress">${progressMarkup}</div>
        <div class="line-actions">
          <button class="mini action-large" data-open-url="${esc(row.openUrl)}" ${row.openUrl ? '' : 'disabled'}>Details</button>
          <button class="mini action-large" data-action="reconcile" data-order="${esc(row.orderId)}" ${row.dataComplete && row.hasReturn ? '' : 'disabled'}>Credit</button>
          <button class="mini action-large" data-action="reset" data-order="${esc(row.orderId)}" ${row.dataComplete && row.hasReturn ? '' : 'disabled'}>Reset</button>
          <button class="mini action-large" data-refresh-order="${esc(row.orderId)}" ${row.openUrl ? '' : 'disabled'}>Refresh</button>
        </div>
      </article>`;
    }).join('');
  }'''
d=d[:start]+new_table+d[end:]
d=once(d,"    if (!['all', 'returns', 'needs_review'].includes(view)) return;","    if (!['all', 'returns', 'needs_review', 'processing', 'errors'].includes(view)) return;",'set view allowlist')
d=once(d,"  search.addEventListener('input', render);","  search.addEventListener('input', render);\n  for (const control of [statusFilter, yearFilter, cardFilter, sortOrder]) control?.addEventListener('change', render);",'filter listeners')
d=once(d,"    const rows = buildRows();\n    const pending = [];","    const rows = buildRows().filter(row => row.dataComplete);\n    const pending = [];",'bank export complete rows')
d=once(d,"    for (const row of buildRows()) lines.push([row.statusLabel,row.orderId,row.itemNames.join(' | '),row.orderTotal ?? '',row.refundAmount ?? '',row.cardLast4 || '',row.amazonStatus,row.detailComplete,row.openUrl,row.lastScannedAt || ''].map(csvCell).join(','));","    for (const row of buildRows().filter(row => row.dataComplete)) lines.push([row.statusLabel,row.orderId,row.itemNames.join(' | '),row.orderTotal ?? '',row.refundAmount ?? '',row.cardLast4 || '',row.amazonStatus,row.detailComplete,row.openUrl,row.lastScannedAt || ''].map(csvCell).join(','));",'csv complete rows')
write('dashboard.js',d)

# ---------- CSS ----------
css=read('ui.css')
css += r'''

/* v0.18.9 complete-only ledger views and query controls */
.ledger-filters { grid-template-columns: minmax(240px, 2fr) repeat(4, minmax(130px, 1fr)); align-items:center; }
.ledger-filters select { width:100%; padding:9px 10px; border:1px solid #cfd4da; border-radius:7px; background:#fff; min-width:0; }
.badge-processing { background:#eef3fa; color:#345b89; }
.badge-error, .badge-error.badge { background:#fff0f0; color:#8b2525; }
.processing-error-card { border-left:3px solid #b42318; background:#fffafa; }
.processing-error, .processing-state { display:grid; gap:3px; padding:7px 9px; border:1px solid #ead1d1; border-radius:7px; background:#fff7f7; font-size:9px; line-height:1.25; overflow-wrap:anywhere; }
.processing-state { border-color:#d7e0eb; background:#f7faff; }
.processing-error strong { color:#8b2525; }
.processing-error small, .processing-state span { color:#656d76; }
@media (max-width: 1100px) { .ledger-filters { grid-template-columns: repeat(2, minmax(0,1fr)); } .ledger-filters #search { grid-column:1 / -1; } }
@media (max-width: 650px) { .ledger-filters { grid-template-columns:1fr; } .ledger-filters #search { grid-column:auto; } }
'''
write('ui.css',css)

# ---------- regression tests ----------
pt=read('parser-test.js')
pt += r'''

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
'''
write('parser-test.js',pt)

bt=read('background-test.js')
bt += r'''

const backgroundSourceV0189 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(backgroundSourceV0189.includes("r?.orderDataComplete === true"), 'page completion must require fully processed order data');
assert(backgroundSourceV0189.includes('patchOrderProcessing'), 'background must persist order processing/error state');
assert(backgroundSourceV0189.includes("processingState: 'error'"), 'terminal detail failures must enter the Errors view state');
assert(backgroundSourceV0189.includes("processingState: 'retrying'"), 'transient detail failures must remain Processing while retrying');
console.log('v0.18.9 completion/error background regressions passed');
'''
write('background-test.js',bt)

ut=read('ui-test.js')
ut += r'''

const dashboardHtmlV0189 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
const dashboardSourceV0189 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
assert(dashboardHtmlV0189.includes('data-view="processing"') && dashboardHtmlV0189.includes('data-view="errors"'), 'dashboard must separate Processing and Errors from completed orders');
for (const id of ['statusFilter','yearFilter','cardFilter','sortOrder']) assert(dashboardHtmlV0189.includes(`id="${id}"`), `dashboard must render ${id}`);
assert(dashboardSourceV0189.includes("currentView === 'all' && !row.dataComplete"), 'All orders must hide incomplete records');
assert(dashboardSourceV0189.includes('authoritativeReturnCapture === true'), 'completed orders with return links must prefer authoritative return records');
assert(dashboardSourceV0189.includes("currentView === 'errors' && !row.processingError"), 'Errors view must be driven by persisted processing errors');
assert(dashboardSourceV0189.includes("mode === 'order_high'") && dashboardSourceV0189.includes("mode === 'refund_low'"), 'sort controls must support monetary ordering');
assert(dashboardSourceV0189.includes('...(row.asins || [])'), 'text search must include ASIN evidence');
console.log('v0.18.9 complete-ledger query UI regressions passed');
'''
write('ui-test.js',ut)

# ---------- versions ----------
manifest=json.loads(read('manifest.json'))
manifest['version']='0.18.9'; manifest['version_name']='0.18.9'
write('manifest.json',json.dumps(manifest,indent=2)+'\n')
pkg=json.loads(read('package.json')); pkg['version']='0.18.9'
write('package.json',json.dumps(pkg,indent=2)+'\n')

# ---------- durable docs ----------
for path,append in {
'README.md':'''\n\n## v0.18.9 authoritative progress and complete-only ledger\n\nv0.18.9 removes checkmark-count inference from detached Amazon return HTML. DOM checkmarks must be structurally bound/non-hidden and cannot outrank affirmative Amazon lifecycle prose. The normal ledger now shows only fully processed orders; incomplete work is isolated in Processing and terminal order failures in Errors. Completed orders with real return-status links display authoritative return captures rather than provisional link records. Search now includes ASIN/card/status/order/product evidence, with status/year/card filters and multiple sort modes. Issue #29 tracks live acceptance.\n''',
'PROJECT_HANDOFF.md':'''\n\n## v0.18.9 implementation\n- Live v0.18.8 still over-completed Breville/washer timelines because detached HTML can retain future checkmark markup. v0.18.9 removes count-based checkmark inference and caps DOM evidence at affirmative lifecycle prose.\n- A managed order is dashboard-ready only after canonical Order Details plus every discovered return-status child complete successfully.\n- Main ledger views are complete-only; Processing and Errors isolate partial/failed work. Successful retries clear the error and move the order into normal views.\n- Completed orders prefer authoritative return captures when real return-status links exist.\n- Added search across ASIN/card/order/product/status plus status/year/card filters and sort modes. Issue #29 tracks live acceptance.\n''',
'TESTING.md':'''\n\n## v0.18.9 live acceptance\n1. Allow the updater to install v0.18.9 and run a fresh scan.\n2. Breville `113-1426991-3716216`: verify only Initiated, Dropped off, Return received are complete until Amazon actually checks Refund issued/credited.\n3. Washer `113-3568581-2749842`: verify each return group reflects its own current Amazon stage and future static/checkmark markup does not promote it.\n4. RAMPOW `111-1110034-5588263`: verify Refund issued can be complete while Refund credited remains pending.\n5. Confirm All orders/Returns/Needs review show only complete orders. Observe in-flight records under Processing and force an order failure to verify exact error text under Errors; Refresh should retry and clear the error on success.\n6. Exercise text search plus status/year/card filters and every sort mode.\n''',
'NEW_CHAT_PROMPT.md':'''\n\n### v0.18.9 durable addition\nNormal ledger views are complete-only: canonical Order Details plus all discovered return-status children must finish before an order appears. Processing and Errors isolate partial/failed orders. Detached return HTML checkmark count is never completion evidence; checkmarks must be structurally bound/non-hidden and cannot outrank affirmative Amazon lifecycle prose. Completed return displays prefer authoritative return captures. Dashboard supports search plus status/year/card filtering and sort controls. Issue #29 tracks live acceptance.\n'''
}.items():
    s=read(path); write(path,s+append)

print('v0.18.9 patch applied')
