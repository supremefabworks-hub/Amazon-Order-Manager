(() => {
  'use strict';

  const parser = window.AmazonRefundParser;
  const storage = window.AmazonRefundStorage;
  if (!parser || !storage) return;

  const AUTO_SCAN_DELAY_MIN_MS = 900;
  const AUTO_SCAN_DELAY_MAX_MS = 1800;
  const MUTATION_DEBOUNCE_MIN_MS = 1400;
  const MUTATION_DEBOUNCE_MAX_MS = 2600;
  const MIN_SCAN_INTERVAL_MS = 3000;

  function randomBetween(min, max) {
    return Math.floor(min + Math.random() * Math.max(1, max - min + 1));
  }

  let scanTimer = null;
  let scanInProgress = false;
  let scanAgain = false;
  let lastScanStartedAt = 0;
  let lastUrl = location.href;
  let lastObservedOrderSignature = '';

  function likelyLedgerPage() {
    const url = location.href.toLowerCase();
    if (/(order|return|refund|your-orders|order-history|your-account)/.test(url)) return true;
    const text = String(document.body?.innerText || document.body?.textContent || '');
    return /\b\d{3}-\d{7}-\d{7}\b/.test(text) && /(order|return|refund)/i.test(text);
  }

  function pageOrderSignature() {
    const text = parser.normalizeText(document.body?.innerText || document.body?.textContent || '');
    const relevantLines = text.split('\n').map(line => line.trim()).filter(Boolean)
      .filter(line => /(\b\d{3}-\d{7}-\d{7}\b|order|return|refund|received|credited|ending in|quantity|item\(s\)|\$\s*\d)/i.test(line))
      .slice(0, 450);
    return `${location.href}|${document.title}|${relevantLines.join(' | ').slice(0, 40000)}`;
  }

  function summaryDelta(before, after) {
    return {
      lifetimeOrders: after.lifetimeOrders - before.lifetimeOrders,
      detailedOrders: (after.detailedOrders || 0) - (before.detailedOrders || 0),
      returnedOrders: after.returnedOrders - before.returnedOrders,
      confirmedReturnedOrders: after.confirmedReturnedOrders - before.confirmedReturnedOrders
    };
  }

  function signed(value) {
    if (!value) return '0';
    return value > 0 ? `+${value}` : String(value);
  }

  function showToast(save) {
    const after = save.afterSummary;
    const delta = summaryDelta(save.beforeSummary, save.afterSummary);
    let host = document.getElementById('amazon-refund-ledger-toast-host');
    if (!host) {
      host = document.createElement('div');
      host.id = 'amazon-refund-ledger-toast-host';
      host.style.position = 'fixed';
      host.style.top = '16px';
      host.style.right = '16px';
      host.style.zIndex = '2147483647';
      host.style.pointerEvents = 'none';
      (document.documentElement || document.body).appendChild(host);
      host.attachShadow({ mode: 'open' });
    }

    const root = host.shadowRoot;
    root.innerHTML = `
      <style>
        .toast { width: 365px; max-width: calc(100vw - 32px); font-family: Arial,Helvetica,sans-serif; background: rgba(20,24,30,.97); color:#fff; border:1px solid rgba(255,255,255,.15); border-radius:12px; box-shadow:0 12px 36px rgba(0,0,0,.28); padding:12px 14px; opacity:0; transform:translateY(-8px); transition:opacity .18s ease,transform .18s ease; }
        .toast.show { opacity:1; transform:translateY(0); }
        .title { font-size:13px; font-weight:700; margin-bottom:8px; }
        .change { font-size:11px; color:#c9d0d8; margin-bottom:9px; }
        .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:7px; }
        .metric { background:rgba(255,255,255,.07); border-radius:8px; padding:7px 7px; }
        .metric b { display:block; font-size:16px; line-height:1.1; }
        .metric span { display:block; font-size:8.5px; line-height:1.2; color:#c9d0d8; margin-top:3px; }
      </style>
      <div class="toast">
        <div class="title">Amazon Refund Ledger updated</div>
        <div class="change">${save.inserted} new · ${save.updated} detail/status updates · orders ${signed(delta.lifetimeOrders)} · detailed ${signed(delta.detailedOrders)} · returns ${signed(delta.returnedOrders)}</div>
        <div class="grid">
          <div class="metric"><b>${after.lifetimeOrders}</b><span>Lifetime orders</span></div>
          <div class="metric"><b>${after.detailedOrders || 0}</b><span>Details captured</span></div>
          <div class="metric"><b>${after.returnedOrders}</b><span>Returned orders</span></div>
          <div class="metric"><b>${after.confirmedReturnedOrders}</b><span>Confirmed returned</span></div>
        </div>
      </div>`;

    const toast = root.querySelector('.toast');
    requestAnimationFrame(() => toast?.classList.add('show'));
    clearTimeout(host.__arlHideTimer);
    host.__arlHideTimer = setTimeout(() => {
      toast?.classList.remove('show');
      setTimeout(() => { if (root) root.innerHTML = ''; }, 220);
    }, 5600);
  }

  function inlineStageLabel(stage) {
    return ({
      unknown: 'Return status pending', started: 'Return started', shipped: 'Dropped off / shipped',
      received: 'Amazon received return', refund_issued: 'Refund issued', refunded: 'Refund issued', credited: 'Refund credited'
    })[stage] || stage;
  }

  function milestoneDate(record, key) {
    return record?.returnMilestones?.[key]?.date || null;
  }

  function inlineReturnCard(record) {
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
  }

  async function decorateReturnsOnPage() {
    if (!likelyLedgerPage()) return;
    const ledger = await storage.getLedger();
    const returns = ledger.filter(r => r?.recordType === 'return' && r?.orderId);
    const byOrder = new Map();
    for (const record of returns) {
      if (!byOrder.has(record.orderId)) byOrder.set(record.orderId, new Map());
      const key = `${record.returnToken || record.returnStatusUrl || 'return'}:${record.returnItemId || record.asins?.[0] || record.itemNames?.[0] || record.recordId || 'item'}`;
      const bucket = byOrder.get(record.orderId);
      const prior = bucket.get(key);
      if (!prior || storage.returnStageRank(record) > storage.returnStageRank(prior) || String(record.lastScannedAt || '') > String(prior.lastScannedAt || '')) bucket.set(key, record);
    }

    for (const [orderId, recordMap] of byOrder) {
      const records = Array.from(recordMap.values());
      const container = parser.closestContainerForOrder?.(document, orderId);
      if (!container) continue;
      let host = container.querySelector?.(`:scope > [data-arl-return-tracker="${orderId}"]`);
      if (!host) {
        host = document.createElement('div');
        host.setAttribute('data-arl-return-tracker', orderId);
        host.setAttribute('data-arl-ui', 'true');
        host.style.margin = '12px 0 4px';
        container.appendChild(host);
        host.attachShadow({ mode: 'open' });
      }
      const root = host.shadowRoot;
      if (!root) continue;
      root.innerHTML = `<style>
        :host{display:block;font-family:Arial,Helvetica,sans-serif;color:#0f1111}.wrap{display:grid;gap:8px}.return-box{border:1px solid #d5d9d9;border-radius:8px;background:#fff;padding:12px 14px}.head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.head b{display:block;color:#067d62;font-size:14px}.head span{display:block;margin-top:3px;font-size:12px;color:#565959;max-width:620px}.head strong{color:#067d62;font-size:14px;white-space:nowrap}.track{position:relative;display:grid;grid-template-columns:repeat(5,1fr);margin-top:14px;gap:4px}.rail{position:absolute;left:8%;right:8%;top:19px;height:4px;background:#d5d9d9;border-radius:8px;overflow:hidden}.rail i{display:block;height:100%;background:#00a8a8;border-radius:8px}.step{position:relative;text-align:center;z-index:1;color:#68717a}.step em{display:flex;width:18px;height:18px;margin:10px auto 4px;border-radius:50%;border:2px solid #879596;background:#fff;align-items:center;justify-content:center;font-style:normal;font-size:11px;color:#fff}.step.done em{background:#00a8a8;border-color:#00a8a8}.step small{display:block;min-height:14px;font-size:9px;color:#565959}.step span{display:block;font-size:10px}.step.done span{color:#007185;font-weight:700}a{display:inline-block;margin-top:10px;color:#007185;font-size:11px;text-decoration:none}a:hover{text-decoration:underline}</style>
        <div class="wrap">${records.map(inlineReturnCard).join('')}</div>`;
    }
  }


  function applySingleReturnIdentityHint(records, hint) {
    const list = Array.isArray(records) ? records.slice() : [];
    const authoritative = list.filter(record => record?.recordType === 'return' && record?.authoritativeReturnCapture);
    if (authoritative.length !== 1 || !hint?.returnItemId) return list;
    const target = authoritative[0];
    const enriched = {
      ...target,
      returnToken: hint.returnToken || target.returnToken || null,
      returnItemId: hint.returnItemId,
      returnContractId: hint.returnContractId || target.returnContractId || null,
      returnRmaId: hint.returnRmaId || target.returnRmaId || null
    };
    enriched.recordId = parser.makeRecordId(enriched);
    return list.map(record => record === target ? enriched : record);
  }

  async function announceDiscovery(result) {
    if (!result?.detailLinks?.length && !result?.returnLinks?.length && !result?.historyPageLinks?.length) return;
    try {
      await chrome.runtime.sendMessage({
        type: 'ARL_DISCOVERED',
        detailLinks: result.detailLinks || [],
        returnLinks: result.returnLinks || [],
        historyPageLinks: result.historyPageLinks || [],
        scannedUrl: result.scannedUrl || location.href
      });
    } catch (_) {}
  }

  async function scanPage({ force = false, notify = true, discover = true, reportChange = true } = {}) {
    if (!force && !likelyLedgerPage()) return { ok: true, skipped: true, reason: 'not-ledger-page' };
    if (scanInProgress) {
      scanAgain = true;
      return { ok: true, queued: true };
    }

    const elapsed = Date.now() - lastScanStartedAt;
    if (!force && elapsed < MIN_SCAN_INTERVAL_MS) {
      scheduleScan(MIN_SCAN_INTERVAL_MS - elapsed + randomBetween(100, 450), notify);
      return { ok: true, queued: true };
    }

    scanInProgress = true;
    lastScanStartedAt = Date.now();
    try {
      const result = parser.parseDocument(document, location.href);
      let save = null;
      if (result.records?.length) {
        save = await storage.upsertRecords(result.records);
        const settings = await storage.getSettings();
        if (notify && save.changed && settings.showUpdateToast !== false) showToast(save);
        if (save.changed && reportChange) {
          chrome.runtime.sendMessage({ type: 'ARL_LEDGER_CHANGED_FROM_PAGE', save }).catch(() => {});
        }
      }
      if (discover) await announceDiscovery(result);
      await decorateReturnsOnPage().catch(() => {});
      return { ok: true, ...result, save };
    } catch (error) {
      return { ok: false, error: error?.message || String(error) };
    } finally {
      scanInProgress = false;
      if (scanAgain) {
        scanAgain = false;
        scheduleScan(randomBetween(MUTATION_DEBOUNCE_MIN_MS, MUTATION_DEBOUNCE_MAX_MS), notify);
      }
    }
  }

  function scheduleScan(delay = randomBetween(MUTATION_DEBOUNCE_MIN_MS, MUTATION_DEBOUNCE_MAX_MS), notify = true) {
    clearTimeout(scanTimer);
    scanTimer = setTimeout(() => scanPage({ notify, discover: true }), Math.max(100, delay));
  }


  function workerReadiness(job = {}) {
    const text = String(document.body?.innerText || document.body?.textContent || '');
    const normalized = parser.normalizeText(text);
    const blocked = /sorry,? we just need to make sure|not a robot|enter the characters you see below|type the characters you see|captcha/i.test(text);
    const signIn = /(?:^|\n)sign in(?:\n|$)|email or mobile phone number|enter your password/i.test(text) && !/\b\d{3}-\d{7}-\d{7}\b/.test(text);
    const rateLimited = /too many requests|request throttled|temporarily unavailable|service unavailable|please try again later/i.test(text) && !/\b\d{3}-\d{7}-\d{7}\b/.test(text);
    if (blocked || signIn) return { ok: true, ready: false, blocked: true, rateLimited: false, error: blocked ? 'Amazon requested human verification in the background tab.' : 'Amazon requires sign-in in the background tab.' };
    if (rateLimited) return { ok: true, ready: false, blocked: false, rateLimited: true, error: 'Amazon appears to be throttling requests.' };

    const type = String(job?.type || '').toLowerCase();
    const orderId = String(job?.orderId || '').trim();
    const orderIds = parser.extractOrderIds(normalized);
    let ready = false;
    let reason = 'generic-content';

    if (type === 'history' || type === 'advance') {
      ready = orderIds.length > 0;
      reason = ready ? 'history-order-fingerprint' : 'waiting-for-history-orders';
    } else if (type === 'detail') {
      const canonicalRoute = /(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details)/i.test(location.pathname);
      const matchingOrder = !orderId || orderIds.includes(orderId) || location.href.includes(orderId);
      let productAnchor = null;
      try { productAnchor = document.querySelector('a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/product/"]'); } catch (_) {}
      const hasSummary = /(?:Order Summary|Grand Total|Item\(s\) Subtotal|Total before tax|Order total)/i.test(normalized);
      ready = Boolean(canonicalRoute && matchingOrder && hasSummary && (productAnchor || /(?:Cancelled|Canceled)/i.test(normalized)));
      reason = ready ? 'canonical-detail-evidence' : 'waiting-for-detail-evidence';
    } else if (type === 'return') {
      const returnRoute = /\/spr\/returns\/(?:prep|label)|\/returns?\/(?:status|details)/i.test(location.pathname);
      const matchingOrder = !orderId || orderIds.includes(orderId) || location.href.includes(orderId);
      const lifecycle = /(?:Initiated|Return request|Drop off|Dropped off|Return received|Refund issued|Refund credited|Replacement)/i.test(normalized);
      ready = Boolean(returnRoute && matchingOrder && lifecycle);
      reason = ready ? 'return-lifecycle-evidence' : 'waiting-for-return-evidence';
    } else {
      ready = normalized.length >= 80;
    }

    return { ok: true, ready, blocked: false, rateLimited: false, reason, orderCount: orderIds.length, url: location.href };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message) return;
    if (message.type === 'ARL_SCAN_PAGE') {
      scanPage({ force: true, notify: true, discover: true }).then(sendResponse);
      return true;
    }
    if (message.type === 'ARL_WORKER_READY') {
      sendResponse(workerReadiness(message.job || {}));
      return;
    }
    if (message.type === 'ARL_WORKER_SCAN') {
      (async () => {
        const initialText = String(document.body?.innerText || document.body?.textContent || '');
        const blocked = /sorry,? we just need to make sure|not a robot|enter the characters you see below|type the characters you see|captcha/i.test(initialText);
        const signIn = /(?:^|\n)sign in(?:\n|$)|email or mobile phone number|enter your password/i.test(initialText) && !/\b\d{3}-\d{7}-\d{7}\b/.test(initialText);
        const rateLimited = /too many requests|request throttled|temporarily unavailable|service unavailable|please try again later/i.test(initialText) && !/\b\d{3}-\d{7}-\d{7}\b/.test(initialText);
        if (blocked || signIn) {
          return { ok: false, blocked: true, error: blocked ? 'Amazon requested human verification in the background tab.' : 'Amazon requires sign-in in the background tab.' };
        }
        if (rateLimited) {
          return { ok: false, rateLimited: true, error: 'Amazon appears to be throttling requests. The crawler will cool down before retrying.' };
        }
        // Some Amazon order-history pages populate more cards while scrolling. Do this only
        // inside the inactive worker tab, never in the user's active Amazon tab.
        if (message.job?.type === 'history') {
          // Amazon can lazy-load additional order cards after reaching the bottom. Stabilize on
          // both document height and the visible Order-ID fingerprint so shorter waits cannot hide
          // late-arriving orders. Three consecutive stable samples are required.
          let stable = 0;
          for (let i = 0; i < 18; i += 1) {
            const height = Math.max(document.body?.scrollHeight || 0, document.documentElement?.scrollHeight || 0);
            const fingerprint = parser.extractOrderIds(document.body?.innerText || document.body?.textContent || '').join('|');
            window.scrollTo(0, height);
            await new Promise(resolve => setTimeout(resolve, randomBetween(180, 380)));
            const nextHeight = Math.max(document.body?.scrollHeight || 0, document.documentElement?.scrollHeight || 0);
            const nextFingerprint = parser.extractOrderIds(document.body?.innerText || document.body?.textContent || '').join('|');
            if (nextFingerprint && nextHeight === height && nextFingerprint === fingerprint) stable += 1; else stable = 0;
            if (stable >= 3) break;
          }
          await new Promise(resolve => setTimeout(resolve, randomBetween(250, 600)));
        }
        const scanned = await scanPage({ force: true, notify: false, discover: false, reportChange: false });
        if (message.job?.type === 'return' && scanned?.ok) {
          const stabilizedRecords = applySingleReturnIdentityHint(scanned.records || [], message.job);
          if (stabilizedRecords.some((record, index) => record?.recordId !== scanned.records?.[index]?.recordId)) {
            const stabilizedReturns = stabilizedRecords.filter(record => record?.recordType === 'return' && record?.authoritativeReturnCapture);
            const stabilizedSave = stabilizedReturns.length ? await storage.upsertRecords(stabilizedReturns) : scanned.save;
            return { ...scanned, records: stabilizedRecords, save: stabilizedSave };
          }
        }
        return scanned;
      })().then(sendResponse);
      return true;
    }

    if (message.type === 'ARL_WORKER_FETCH_DETAIL') {
      (async () => {
        const orderId = String(message.orderId || '').trim();
        const rawUrl = String(message.url || '').trim();
        if (!/^\d{3}-\d{7}-\d{7}$/.test(orderId)) return { ok: false, error: 'Invalid Amazon order ID.' };
        if (!rawUrl) return { ok: false, error: 'Missing real Order Details URL.' };
        let url;
        try {
          url = new URL(rawUrl, location.origin);
        } catch (_) {
          return { ok: false, error: 'Invalid Order Details URL.' };
        }
        if (!/(^|\.)amazon\.com$/i.test(url.hostname) || !/(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details)/i.test(url.pathname)) {
          return { ok: false, error: 'The requested page is not an Amazon Order Details page.' };
        }

        try {
          // Reuse the authenticated Amazon session in this content-script tab. This is the same
          // pattern used by Order History Exporter for Amazon: fetch the real Order Details URL,
          // include Amazon credentials, then parse the returned HTML locally with DOMParser.
          const response = await fetch(url.toString(), {
            credentials: 'include',
            cache: 'no-store',
            redirect: 'follow'
          });
          if (!response.ok) {
            const rateLimited = response.status === 429 || response.status === 503;
            return { ok: false, rateLimited, error: rateLimited ? 'Amazon throttled the Order Details request.' : `Amazon Order Details returned HTTP ${response.status}.` };
          }
          const html = await response.text();
          const textProbe = String(html || '').replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ');
          const blocked = /sorry,? we just need to make sure|not a robot|enter the characters you see below|type the characters you see|captcha/i.test(textProbe);
          const signIn = /email or mobile phone number|enter your password|<title>\s*amazon sign-in/i.test(textProbe);
          const rateLimited = /too many requests|request throttled|temporarily unavailable|service unavailable|please try again later/i.test(textProbe);
          if (blocked || signIn) return { ok: false, blocked: true, error: blocked ? 'Amazon requested human verification.' : 'Amazon requires sign-in.' };
          if (rateLimited) return { ok: false, rateLimited: true, error: 'Amazon appears to be throttling Order Details requests.' };

          const doc = new DOMParser().parseFromString(html, 'text/html');
          const finalUrl = response.url || url.toString();
          const parsed = parser.parseDocument(doc, finalUrl);
          const matching = (parsed.records || []).filter(record => record?.recordType === 'order' && record?.orderId === orderId && record?.detailScanComplete);
          if (!matching.length) {
            return { ok: false, error: `Order Details HTML for ${orderId} was incomplete or did not match the canonical order.`, scannedUrl: finalUrl };
          }
          let save = null;
          if (parsed.records?.length) save = await storage.upsertRecords(parsed.records);
          const returnRefreshes = [];
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
          return { ok: true, ...parsed, save, scannedUrl: finalUrl, fetchedOrderDetails: true, returnRefreshes, orderDataComplete: true, returnStatusExpectedCount: expectedReturns, returnStatusAuthoritativeCount: authoritativeReturns };
        } catch (error) {
          return { ok: false, error: error?.message || String(error) };
        }
      })().then(sendResponse);
      return true;
    }
    if (message.type === 'ARL_WORKER_PAGE_STATE') {
      const filterState = parser.historyTimeFilterState ? parser.historyTimeFilterState(document) : { value: null, year: null };
      let historyOrderIds = [];
      try {
        const parsedPage = parser.parseDocument(document, location.href);
        historyOrderIds = Array.isArray(parsedPage?.historyOrderIds) ? parsedPage.historyOrderIds : [];
      } catch (_) {}
      if (!historyOrderIds.length) historyOrderIds = parser.extractOrderIds(document.body?.innerText || '');
      sendResponse({
        ok: true,
        url: location.href,
        fingerprint: historyOrderIds.join('|') || pageOrderSignature(),
        orderIds: historyOrderIds,
        historyTimeFilterValue: filterState.value || null,
        historySelectedYear: filterState.year || null
      });
      return;
    }
    if (message.type === 'ARL_WORKER_SELECT_YEAR') {
      (async () => {
        const year = String(message.year || '').trim();
        if (!/^20\d{2}$/.test(year)) return { ok: false, changed: false, error: 'Invalid history year.' };
        const select = document.querySelector('#timeFilterDropdown, select[name="timeFilterDropdown"]');
        if (!select) return { ok: false, changed: false, error: 'Amazon timeFilterDropdown was not found.' };
        const option = Array.from(select.options || []).find(opt => String(opt.value || '').trim() === year || parser.normalizeText(opt.textContent || opt.innerText || '') === year);
        if (!option) return { ok: false, changed: false, error: `Amazon does not expose ${year} in the year picker.` };
        const beforeUrl = location.href;
        const beforeValue = String(select.value || '');
        select.value = option.value;
        select.dispatchEvent(new Event('input', { bubbles: true }));
        select.dispatchEvent(new Event('change', { bubbles: true }));

        // Give Amazon AUI a moment to handle the real native dropdown event. If the Business SPA
        // does not move itself, set the exact route Teach Mode recorded; this still uses Amazon's
        // own hash router and does not invent a server-side pagination parameter.
        await new Promise(resolve => setTimeout(resolve, randomBetween(650, 1200)));
        const route = parser.historyRouteFromUrl?.(location.href) || {};
        if (Number(route.year) !== Number(year)) {
          location.hash = `time/${year}/pagination/1/`;
        }
        return { ok: true, changed: beforeValue !== String(option.value), beforeUrl, selectedValue: String(option.value), targetYear: Number(year) };
      })().then(sendResponse);
      return true;
    }
    if (message.type === 'ARL_WORKER_CLICK_NEXT') {
      (async () => {
        const selectors = [
          'a[rel="next"]',
          'ul.a-pagination li.a-last:not(.a-disabled) a',
          '.a-pagination .a-last:not(.a-disabled) a',
          'li.a-last:not(.a-disabled) a',
          'a.s-pagination-next:not(.s-pagination-disabled)',
          'button[aria-label*="next" i]:not([disabled])',
          '[role="button"][aria-label*="next" i]',
          'input[type="submit"][value*="next" i]',
          '[data-action="next"]',
          '[data-testid*="next" i]'
        ];
        let target = null;

        // Teach Mode showed Amazon Business exposing concrete numbered hash links. Clicking the
        // next NUMBER is more deterministic than its literal #.../pagination/next/ link, so mirror
        // the user's successful manual workflow whenever that numbered anchor is available.
        let currentPage = parser.historyRouteFromUrl?.(location.href)?.page || null;
        if (!currentPage) {
          for (const selector of ['.a-pagination [aria-current="page"]', '.a-pagination li.a-selected', '[aria-current="page"]']) {
            try {
              const selected = document.querySelector(selector);
              const n = Number(parser.normalizeText(selected?.innerText || selected?.textContent || ''));
              if (Number.isFinite(n) && n >= 1) { currentPage = n; break; }
            } catch (_) {}
          }
        }
        if (currentPage) {
          const nextNumber = Number(currentPage) + 1;
          for (const candidate of Array.from(document.querySelectorAll('.a-pagination a[href], a[href*="#time/"][href*="/pagination/"]'))) {
            const n = Number(parser.normalizeText(candidate.innerText || candidate.textContent || ''));
            if (n !== nextNumber) continue;
            if (candidate.getAttribute?.('aria-disabled') === 'true' || candidate.closest?.('.a-disabled')) continue;
            target = candidate;
            break;
          }
        }

        if (!target) {
          for (const selector of selectors) {
            try {
              const candidate = document.querySelector(selector);
              if (candidate && candidate.getAttribute?.('aria-disabled') !== 'true' && !candidate.closest?.('.a-disabled')) { target = candidate; break; }
            } catch (_) {}
          }
        }
        if (!target) {
          for (const candidate of Array.from(document.querySelectorAll('a, button, [role="button"], input[type="submit"], li, span'))) {
            const text = parser.normalizeText(candidate.innerText || candidate.textContent || candidate.value || candidate.getAttribute?.('aria-label') || candidate.getAttribute?.('title') || '').toLowerCase();
            if (!/(^|\b)next(?:\s+page)?(?:\b|\s*[→›»])/.test(text)) continue;
            if (candidate.disabled || candidate.getAttribute?.('aria-disabled') === 'true' || candidate.closest?.('.a-disabled')) continue;
            target = candidate.querySelector?.('a,button,input,[role="button"]') || candidate;
            break;
          }
        }
        if (!target && message.allowInferredNavigation !== false) {
          const inferred = parser.findNextLink(document, location.href);
          if (inferred) {
            const normalized = value => { try { const absolute = new URL(value, location.href).toString(); return parser.historyLocationKey ? parser.historyLocationKey(absolute) : absolute; } catch (_) { return ''; } };
            target = Array.from(document.querySelectorAll('a[href], [data-href], [data-url]')).find(a => {
              const raw = a.getAttribute('href') || a.getAttribute('data-href') || a.getAttribute('data-url') || a.href || '';
              return normalized(raw) === normalized(inferred);
            }) || null;
            if (!target) {
              // No clickable DOM node maps to the inferred URL. Navigating the inactive worker tab
              // to Amazon's own next-page URL is equivalent to clicking its pager.
              const beforeUrl = location.href;
              await new Promise(resolve => setTimeout(resolve, randomBetween(450, 1250)));
              return { ok: true, clicked: true, navigateUrl: inferred, beforeUrl };
            }
          }
        }
        if (!target) return { ok: false, clicked: false, error: 'No enabled Next control found.' };
        const beforeUrl = location.href;
        const targetHref = target.getAttribute?.('href') || target.href || null;
        const targetText = parser.normalizeText(target.innerText || target.textContent || target.value || target.getAttribute?.('aria-label') || '');
        await new Promise(resolve => setTimeout(resolve, randomBetween(450, 1250)));
        if (target.tagName === 'A' && target.href) target.click();
        else if (typeof target.click === 'function') target.click();
        else return { ok: false, clicked: false, error: 'Next control was found but could not be activated.' };
        return { ok: true, clicked: true, beforeUrl, targetHref, targetText };
      })().then(sendResponse);
      return true;
    }
    if (message.type === 'ARL_BACKGROUND_LEDGER_UPDATED') {
      if (message.save?.changed) showToast(message.save);
      sendResponse?.({ ok: true });
      return;
    }
  });

  let mutationCheckTimer = null;
  const observer = new MutationObserver(() => {
    if (!likelyLedgerPage() || mutationCheckTimer) return;
    mutationCheckTimer = setTimeout(() => {
      mutationCheckTimer = null;
      const signature = pageOrderSignature();
      if (signature === lastObservedOrderSignature) return;
      lastObservedOrderSignature = signature;
      scheduleScan(150, true);
    }, randomBetween(MUTATION_DEBOUNCE_MIN_MS, MUTATION_DEBOUNCE_MAX_MS));
  });

  if (document.documentElement) observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });

  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      lastObservedOrderSignature = '';
      scheduleScan(randomBetween(AUTO_SCAN_DELAY_MIN_MS, AUTO_SCAN_DELAY_MAX_MS), true);
    }
  }, 1500);

  chrome.storage.onChanged.addListener(changes => {
    if (changes.ledger) decorateReturnsOnPage().catch(() => {});
  });

  storage.getSettings().then(settings => {
    if (settings.autoScan !== false) scheduleScan(randomBetween(AUTO_SCAN_DELAY_MIN_MS, AUTO_SCAN_DELAY_MAX_MS), true);
  });
})();
