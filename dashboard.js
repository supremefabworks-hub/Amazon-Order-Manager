(() => {
  'use strict';

  const storage = window.AmazonRefundStorage;
  const body = document.getElementById('ledgerBody');
  const stats = document.getElementById('stats');
  const empty = document.getElementById('empty');
  const search = document.getElementById('search');
  const scannerStatus = document.getElementById('scannerStatus');
  const scannerCheckpoint = document.getElementById('scannerCheckpoint');
  const navAllCount = document.getElementById('navAllCount');
  const navReturnCount = document.getElementById('navReturnCount');
  const navReviewCount = document.getElementById('navReviewCount');
  const bankBridgeStatus = document.getElementById('bankBridgeStatus');
  const bankResultFile = document.getElementById('bankResultFile');
  let ledger = [];
  let settings = storage.DEFAULT_SETTINGS;
  let currentView = new URLSearchParams(location.search).get('view') || 'all';
  if (!['all', 'returns', 'needs_review'].includes(currentView)) currentView = 'all';

  function esc(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  function money(value) { if (value === null || value === undefined || value === '') return '—'; return Number.isFinite(Number(value)) ? `$${Number(value).toFixed(2)}` : '—'; }
  function formatDate(value) {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' }).format(d);
  }
  function canonicalDetailUrl(orderId, order) {
    const url = order?.orderDetailsUrl || '';
    if (url && /(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details)/i.test(url)) return url;
    return '';
  }
  function stageLabel(stage) {
    return ({
      unknown: 'Return detected', started: 'Return started', shipped: 'Dropped off / shipped',
      received: 'Return received', refund_issued: 'Refund issued', refunded: 'Refund issued', credited: 'Credited'
    })[stage] || stage || 'Return detected';
  }
  function milestoneDate(record, key) { return record?.returnMilestones?.[key]?.date || ''; }
  function uniqueStrings(values) {
    const seen = new Set(); const out = [];
    for (const value of values || []) {
      const s = String(value || '').trim(); if (!s) continue;
      const k = s.toLowerCase(); if (seen.has(k)) continue; seen.add(k); out.push(s);
    }
    return out;
  }
  function returnRecordIdentity(record) {
    const token = String(record?.returnToken || record?.returnStatusUrl || record?.recordId || 'return').toLowerCase();
    const item = String(record?.returnItemId || record?.asins?.[0] || record?.itemNames?.[0] || record?.recordId || 'item').toLowerCase();
    return `${token}:${item}`;
  }
  function dedupeReturns(records) {
    const byKey = new Map();
    for (const r of records || []) {
      const key = returnRecordIdentity(r);
      const existing = byKey.get(key);
      if (!existing || storage.returnStageRank(r) > storage.returnStageRank(existing) || String(r.lastScannedAt || '') > String(existing.lastScannedAt || '')) byKey.set(key, r);
    }
    return Array.from(byKey.values());
  }
  function returnGroupAmount(records) {
    const ordered = (records || []).slice().sort((a,b) => String(b.lastScannedAt || '').localeCompare(String(a.lastScannedAt || '')));
    const explicitGroupValues = [];
    for (const r of ordered) {
      const groupRaw = r.returnGroupRefundAmount;
      const scopedRaw = r.refundAmountScope === 'return' ? (r.refundAmount ?? r.refundSubtotal) : null;
      const groupValue = groupRaw === null || groupRaw === undefined || groupRaw === '' ? NaN : Number(groupRaw);
      const scopedValue = scopedRaw === null || scopedRaw === undefined || scopedRaw === '' ? NaN : Number(scopedRaw);
      const value = Number.isFinite(groupValue) ? groupValue : scopedValue;
      if (Number.isFinite(value)) explicitGroupValues.push(value);
    }
    if (explicitGroupValues.length) {
      const cents = new Set(explicitGroupValues.map(value => value.toFixed(2)));
      return { amount: explicitGroupValues[0], conflict: cents.size > 1 };
    }
    const itemValues = new Map();
    for (const r of ordered) {
      const raw = r.refundAmount ?? r.refundSubtotal;
      const value = raw === null || raw === undefined || raw === '' ? NaN : Number(raw);
      if (!Number.isFinite(value)) continue;
      if (r.refundAmountScope === 'item') itemValues.set(returnRecordIdentity(r), value);
    }
    if (itemValues.size) return { amount: Array.from(itemValues.values()).reduce((a,b)=>a+b,0), conflict: false };
    // Legacy records did not mark scope. Treat one amount per return group, never once per child.
    const legacy = ordered.map(r => {
      const raw = r.refundAmount ?? r.refundSubtotal;
      return raw === null || raw === undefined || raw === '' ? NaN : Number(raw);
    }).find(Number.isFinite);
    return { amount: Number.isFinite(legacy) ? legacy : null, conflict: false };
  }
  function groupReturnRecords(records) {
    const groups = new Map();
    for (const record of records || []) {
      const key = String(record.returnToken || record.returnStatusUrl || record.recordId || 'return');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(record);
    }
    return Array.from(groups.entries()).map(([key, groupRecords]) => {
      const representative = groupRecords.slice().sort((a,b) => {
        const rank = storage.returnStageRank(b) - storage.returnStageRank(a);
        if (rank) return rank;
        return String(b.lastScannedAt || '').localeCompare(String(a.lastScannedAt || ''));
      })[0];
      const amountState = returnGroupAmount(groupRecords);
      const trustedIdentityRecords = groupRecords.filter(r => r.itemIdentitySource === 'order-detail-return-link' && ((r.itemNames || []).length || (r.asins || []).length));
      const identityRecords = trustedIdentityRecords.length ? trustedIdentityRecords : groupRecords;
      return {
        key,
        records: groupRecords,
        representative,
        itemNames: uniqueStrings(identityRecords.flatMap(r => r.itemNames || [])),
        asins: uniqueStrings(identityRecords.flatMap(r => r.asins || [])),
        amount: amountState.amount,
        amountConflict: amountState.conflict,
        itemIdentityConflict: groupRecords.some(r => r.itemIdentityConflict)
      };
    });
  }

  function buildRows() {
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
      const returnRecords = dedupeReturns(returns.get(orderId) || []);
      const returnGroups = groupReturnRecords(returnRecords);
      const manualReconciled = returnRecords.some(r => r.manualState === 'reconciled');
      const ranks = returnRecords.map(r => storage.returnStageRank(r));
      const hasReturn = returnRecords.length > 0;
      const terminalCancelled = Boolean(order?.historyTerminalComplete === true && order?.historyTerminalState === 'cancelled');
      const allCredited = hasReturn && returnRecords.every(r => storage.isCreditConfirmed(r));
      const allIssued = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.refund_issued);

      const orderItemNames = uniqueStrings(order?.itemNames || []);
      const returnedItemNames = uniqueStrings(returnGroups.flatMap(group => group.itemNames || []));
      const childRefundAmount = returnGroups.reduce((total, group) => total + (Number.isFinite(Number(group.amount)) ? Number(group.amount) : 0), 0);
      const canonicalRefundCandidate = order?.canonicalRefundTotal;
      const canonicalRefundTotal = canonicalRefundCandidate !== null && canonicalRefundCandidate !== undefined && canonicalRefundCandidate !== '' && Number.isFinite(Number(canonicalRefundCandidate))
        ? Number(canonicalRefundCandidate)
        : null;
      const refundAmount = canonicalRefundTotal != null ? canonicalRefundTotal : (returnGroups.some(g => Number.isFinite(Number(g.amount))) ? childRefundAmount : null);
      const refundAmountMismatch = canonicalRefundTotal != null && childRefundAmount > canonicalRefundTotal + 0.011;
      const itemIdentityConflict = returnGroups.some(group => group.itemIdentityConflict);
      const groupAmountConflict = returnGroups.some(group => group.amountConflict);
      const needsReview = hasReturn && !manualReconciled && (
        returnRecords.some(r => storage.needsCreditReview(r)) || refundAmountMismatch || itemIdentityConflict || groupAmountConflict
      );

      let stateKey = 'purchase';
      let statusLabel = order?.statusText || (order?.detailScanComplete ? 'Order details captured' : 'Order discovered');
      if (terminalCancelled && !hasReturn) { stateKey = 'cancelled'; statusLabel = 'Cancelled'; }
      else if (manualReconciled) { stateKey = 'reconciled'; statusLabel = 'Reconciled'; }
      else if (needsReview) {
        stateKey = 'needs_review';
        if (refundAmountMismatch) statusLabel = 'Refund amount mismatch';
        else if (itemIdentityConflict) statusLabel = 'Item needs review';
        else if (groupAmountConflict) statusLabel = 'Return refund needs review';
        else {
          const lowest = returnRecords.slice().sort((a,b) => storage.returnStageRank(a)-storage.returnStageRank(b))[0];
          statusLabel = stageLabel(storage.getReturnStage(lowest));
        }
      } else if (allCredited) { stateKey = 'credited'; statusLabel = 'Credited'; }
      else if (allIssued) { stateKey = 'refund_issued'; statusLabel = 'Refund issued'; }
      else if (hasReturn) { stateKey = 'return'; statusLabel = stageLabel(storage.getReturnStage(returnRecords[0])); }

      const statusTexts = uniqueStrings(returnRecords.map(r => r.statusText).filter(Boolean));
      const lastScannedAt = [order?.lastScannedAt, ...returnRecords.map(r => r.lastScannedAt)].filter(Boolean).sort().at(-1) || null;
      const itemNames = hasReturn ? returnedItemNames : orderItemNames;
      rows.push({
        orderId, order, returns: returnRecords, returnGroups, hasReturn, needsReview, terminalCancelled, stateKey, statusLabel,
        itemNames, orderItemNames, returnedItemNames, searchItemNames: uniqueStrings([...orderItemNames, ...returnedItemNames]),
        orderTotal: order?.purchaseAmount ?? null, refundAmount, canonicalRefundTotal, childRefundAmount,
        refundAmountMismatch, itemIdentityConflict, groupAmountConflict,
        cardLast4: order?.cardLast4 || returnRecords.find(r => r.cardLast4)?.cardLast4 || null,
        amazonStatus: statusTexts.length ? statusTexts.join(' · ') : (order?.statusText || order?.status || '—'),
        detailComplete: Boolean(order?.detailScanComplete), detailScannedAt: order?.detailScannedAt || null,
        lastScannedAt, openUrl: canonicalDetailUrl(orderId, order)
      });
    }
    return rows.sort((a,b) => {
      if (a.needsReview !== b.needsReview) return a.needsReview ? -1 : 1;
      if (a.hasReturn !== b.hasReturn) return a.hasReturn ? -1 : 1;
      return String(b.lastScannedAt || '').localeCompare(String(a.lastScannedAt || ''));
    });
  }

  function lifecycleMarkup(group, index, totalGroups) {
    const record = group.representative;
    const progress = storage.returnProgress(record);
    const expectedCredit = !progress.credited ? storage.expectedCreditDate(record) || '' : '';
    const verificationRecord = group.records.find(r => r.bankVerification) || record;
    const verification = verificationRecord.bankVerification || null;
    const creditDate = progress.bankCreditConfirmed
      ? (verification?.postedDate || verification?.verifiedAt || '')
      : progress.amazonCredited
        ? milestoneDate(record, 'credited')
        : '';
    const steps = [
      ['started', 'Initiated', progress.started, milestoneDate(record, 'started')],
      ['shipped', 'Dropped off', progress.shippedOrReceived, milestoneDate(record, 'shipped')],
      ['refundIssued', 'Refund issued', progress.refundIssued, milestoneDate(record, 'refundIssued')],
      ['credited', progress.credited ? 'Bank credited' : (expectedCredit ? `Expected ${expectedCredit}` : 'Credit pending'), progress.credited, creditDate]
    ];
    const items = group.itemNames.length ? group.itemNames.join(' · ') : 'Returned item pending authoritative scan';
    let verificationMarkup = '';
    if (verification) {
      if (verification.status === 'confirmed') {
        const details = [verification.matchedAmount != null ? money(verification.matchedAmount) : '', verification.postedDate || '', verification.accountLast4 ? `•••• ${verification.accountLast4}` : ''].filter(Boolean).join(' · ');
        verificationMarkup = `<div class="bank-match bank-match-confirmed"><strong>Bank confirmed</strong>${details ? `<span>${esc(details)}</span>` : ''}</div>`;
      } else if (verification.status === 'ambiguous' || verification.status === 'needs_review') {
        verificationMarkup = `<div class="bank-match bank-match-review"><strong>Bank match needs review</strong><span>${esc(verification.reason || 'Multiple plausible credits.')}</span></div>`;
      }
    }
    const warnings = [group.itemIdentityConflict ? 'Item identity conflict' : '', group.amountConflict ? 'Refund amount conflict' : ''].filter(Boolean).join(' · ');
    return `<div class="return-track-item compact-return-track">
      <div class="return-track-title">Return ${index}${totalGroups > 1 ? ` of ${totalGroups}` : ''} · ${esc(items)}</div>
      <div class="return-track-meta"><span>${esc(stageLabel(storage.getReturnStage(record)))}</span><strong>${money(group.amount)}</strong></div>
      ${warnings ? `<div class="muted tiny">${esc(warnings)}</div>` : ''}
      <div class="lifecycle lifecycle-lineitem">
        <div class="lifecycle-line"><span style="width:${progress.percent}%"></span></div>
        ${steps.map(step => `<div class="life-step ${step[2] ? 'done' : ''}"><small>${esc(step[3] || '')}</small><i>${step[2] ? '✓' : ''}</i><span>${esc(step[1])}</span></div>`).join('')}
      </div>
      ${verificationMarkup}
    </div>`;
  }
  function returnProgressMarkup(row) {
    if (!row.returnGroups.length) return '<span class="muted">—</span>';
    return `<div class="return-track-stack compact-return-stack">${row.returnGroups.map((group, index) => lifecycleMarkup(group, index + 1, row.returnGroups.length)).join('')}</div>`;
  }

  function filteredRows() {
    const q = search.value.trim().toLowerCase();
    return buildRows().filter(row => {
      if (currentView === 'returns' && !row.hasReturn) return false;
      if (currentView === 'needs_review' && !row.needsReview) return false;
      if (q) {
        const hay = [row.orderId, ...(row.searchItemNames || row.itemNames), row.cardLast4, row.statusLabel, row.amazonStatus, row.orderTotal, row.refundAmount].join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function sum(rows, field) { return rows.reduce((total,row) => total + (Number.isFinite(Number(row[field])) ? Number(row[field]) : 0), 0); }
  function returnRecordAmountTotal(records) {
    return groupReturnRecords(dedupeReturns(records || [])).reduce((total, group) => total + (Number.isFinite(Number(group.amount)) ? Number(group.amount) : 0), 0);
  }
  function needsReviewExpectedAmount(row) {
    const recordTotal = returnRecordAmountTotal((row.returns || []).filter(r => storage.needsCreditReview(r)));
    if (row.refundAmountMismatch || row.itemIdentityConflict || row.groupAmountConflict) {
      const orderExpected = row.refundAmount;
      if (orderExpected !== null && orderExpected !== undefined && orderExpected !== '' && Number.isFinite(Number(orderExpected))) return Number(orderExpected);
    }
    return recordTotal;
  }

  function renderStats() {
    const rows = buildRows();
    const returnRows = rows.filter(r => r.hasReturn);
    const reviewRows = rows.filter(r => r.needsReview);
    const detailed = rows.filter(r => r.detailComplete);
    const issued = rows.filter(r => r.hasReturn && r.returns.every(ret => storage.returnStageRank(ret) >= storage.RETURN_STAGE_RANK.refund_issued));
    const credited = rows.filter(r => r.hasReturn && r.returns.every(ret => storage.isCreditConfirmed(ret)));
    const reviewExpectedTotal = reviewRows.reduce((total, row) => total + needsReviewExpectedAmount(row), 0);
    navAllCount.textContent = String(rows.length);
    navReturnCount.textContent = String(returnRows.length);
    navReviewCount.textContent = String(reviewRows.length);
    stats.innerHTML = `
      <div class="stat"><span>All orders</span><strong>${rows.length}</strong><small>${money(sum(rows, 'orderTotal'))} captured order total</small></div>
      <div class="stat"><span>Order details</span><strong>${detailed.length}</strong><small>View order details parsed</small></div>
      <div class="stat"><span>Returns</span><strong>${returnRows.length}</strong><small>${money(sum(returnRows, 'refundAmount'))} expected refunds</small></div>
      <div class="stat stat-review-total"><span>Needs review</span><strong>${money(reviewExpectedTotal)}</strong><small>${reviewRows.length} flagged ${reviewRows.length === 1 ? 'order' : 'orders'}</small></div>
      <div class="stat"><span>Refund issued</span><strong>${issued.length}</strong><small>Amazon says refund issued</small></div>
      <div class="stat"><span>Bank credited</span><strong>${credited.length}</strong><small>Bank evidence confirmed</small></div>`;
  }

  function renderViewMenu() {
    for (const button of document.querySelectorAll('.view-button')) button.classList.toggle('active', button.dataset.view === currentView);
  }

  function badgeLabel(row) {
    if (row.stateKey === 'purchase') return row.detailComplete ? 'Order' : 'Order queued';
    if (row.stateKey === 'cancelled') return 'Cancelled';
    if (row.stateKey === 'needs_review') return row.statusLabel || 'Needs review';
    if (row.stateKey === 'refund_issued') return 'Refund issued';
    if (row.stateKey === 'credited') return 'Credited';
    if (row.stateKey === 'reconciled') return 'Reconciled';
    return row.statusLabel || 'Return';
  }

  function renderTable() {
    const rows = filteredRows();
    empty.classList.toggle('hidden', rows.length !== 0);
    body.innerHTML = rows.map(row => {
      const items = row.itemNames.length ? row.itemNames.join(' · ') : (row.hasReturn ? `${row.returnGroups.length} return${row.returnGroups.length === 1 ? '' : 's'} pending item identity` : 'Item title pending Order Details scan');
      const detailBadge = row.terminalCancelled
        ? `<span class="badge">Terminal history</span>`
        : row.detailComplete
          ? `<span class="badge badge-reconciled">Detailed</span>`
          : '<span class="badge">Detail queued</span>';
      const bankConfirmed = row.hasReturn && row.returns.length && row.returns.every(ret => storage.isCreditConfirmed(ret));
      const anyIssued = row.hasReturn && row.returns.some(ret => storage.returnStageRank(ret) >= storage.RETURN_STAGE_RANK.refund_issued);
      const financialState = bankConfirmed
        ? '<span class="credit-state credit-confirmed">Bank confirmed</span>'
        : anyIssued
          ? '<span class="credit-state credit-pending">Credit pending</span>'
          : '';
      return `<article class="ledger-order-card ledger-order-line ${row.hasReturn ? 'return-card-row' : ''} ${row.needsReview ? 'needs-review-card' : ''}">
        <div class="line-status">
          <span class="badge badge-${esc(row.stateKey)}">${esc(badgeLabel(row))}</span>
          <div class="detail-line compact-detail">${detailBadge}</div>
        </div>
        <div class="line-order-item">
          <div class="line-order-meta"><span class="mono">${esc(row.orderId)}</span><span class="muted tiny">${formatDate(row.lastScannedAt)}</span></div>
          <div class="item-title line-item-title" title="${esc(items)}">${esc(items)}</div>
          <div class="muted tiny line-amazon-status" title="${esc(row.amazonStatus || '—')}">${esc(row.amazonStatus || '—')}</div>
        </div>
        <div class="line-metric"><span>Order</span><strong>${money(row.orderTotal)}</strong></div>
        <div class="line-metric"><span>Refund</span><strong class="refund-money">${money(row.refundAmount)}</strong></div>
        <div class="line-metric"><span>Card</span><strong>${row.cardLast4 ? `•••• ${esc(row.cardLast4)}` : '—'}</strong></div>
        <div class="line-progress">
          ${row.hasReturn ? `${returnProgressMarkup(row)}${financialState}` : `<span class="muted tiny">${esc(row.statusLabel || 'Order')}</span>`}
        </div>
        <div class="line-actions">
          <button class="mini action-large" data-open-url="${esc(row.openUrl)}" ${row.openUrl ? '' : 'disabled'}>Details</button>
          <button class="mini action-large" data-action="reconcile" data-order="${esc(row.orderId)}" ${row.hasReturn ? '' : 'disabled'}>Credit</button>
          <button class="mini action-large" data-action="reset" data-order="${esc(row.orderId)}" ${row.hasReturn ? '' : 'disabled'}>Reset</button>
          <button class="mini action-large" data-refresh-order="${esc(row.orderId)}" ${row.openUrl ? '' : 'disabled'}>Refresh</button>
        </div>
      </article>`;
    }).join('');
  }

  function render() { renderStats(); renderViewMenu(); renderTable(); }

  function formatRemaining(ms) {
    if (!ms || ms <= 0) return '';
    const sec = Math.ceil(ms / 1000); return sec < 60 ? `${sec}s` : `${Math.ceil(sec / 60)}m`;
  }

  async function renderScannerStatus() {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'ARL_GET_BACKGROUND_STATUS' });
      const state = response?.state; if (!state) throw new Error('No status');
      const crawl = state.crawl || {};
      const cooldownMs = state.cooldownUntil ? Math.max(0, new Date(state.cooldownUntil).getTime() - Date.now()) : 0;
      const mode = state.paused ? 'Stopped' : cooldownMs > 0 ? `Cooling down ${formatRemaining(cooldownMs)}` : state.running ? 'Running' : crawl.phase === 'done' ? 'Complete' : 'Idle';
      const current = state.currentJob ? `${state.currentJob.type}${state.currentJob.orderId ? ` · ${state.currentJob.orderId}` : ''}` : 'none';
      scannerStatus.textContent = `${mode} · ${state.queue?.length || 0} queued · ${state.historyProcessed || 0} history pages · ${state.detailProcessed || 0} Order Details pages · current ${current}${state.lastError ? ` · last issue: ${state.lastError}` : ''}`;
      const pageCount = (crawl.currentPageOrderIds || []).length;
      const doneOnPage = crawl.currentPageCompleted || 0;
      const yearsDone = (crawl.completedYears || []).length ? ` · completed years ${(crawl.completedYears || []).join(', ')}` : '';
      scannerCheckpoint.textContent = crawl.currentYear
        ? `Checkpoint: ${crawl.currentYear} page ${crawl.currentPage || 1} · ${doneOnPage}/${pageCount || '?'} details complete · ${crawl.ordersCompleted || 0} unique orders completed · ${crawl.overlapCount || 0} overlapping history hits${crawl.lastCompletedOrderId ? ` · last ${crawl.lastCompletedOrderId}` : ''}${yearsDone}`
        : `Checkpoint: no lifetime scan started · ${crawl.overlapCount || 0} overlaps recorded`;
    } catch (error) {
      scannerStatus.textContent = `Status unavailable: ${error?.message || error}`;
      scannerCheckpoint.textContent = 'Checkpoint unavailable.';
    }
  }

  async function reload() {
    [ledger, settings] = await Promise.all([storage.getLedger(), storage.getSettings()]);
    render();
  }
  function setView(view) {
    if (!['all', 'returns', 'needs_review'].includes(view)) return;
    currentView = view;
    const url = new URL(location.href); url.searchParams.set('view', view); history.replaceState(null, '', url.toString());
    render();
  }

  document.querySelector('.view-menu').addEventListener('click', event => {
    const button = event.target.closest('[data-view]'); if (button) setView(button.dataset.view);
  });
  body.addEventListener('click', async event => {
    const refresh = event.target.closest('button[data-refresh-order]');
    if (refresh && !refresh.disabled) {
      const original = refresh.textContent;
      refresh.disabled = true;
      refresh.textContent = 'Refreshing…';
      try {
        const response = await chrome.runtime.sendMessage({ type: 'ARL_REFRESH_ORDER', orderId: refresh.dataset.refreshOrder });
        if (!response?.ok) throw new Error(response?.error || 'Refresh failed');
        await reload();
      } catch (error) {
        alert(`Order refresh failed: ${error?.message || error}`);
      } finally {
        refresh.disabled = false;
        refresh.textContent = original;
      }
      return;
    }
    const open = event.target.closest('[data-open-url]');
    if (open && open.dataset.openUrl) { await chrome.tabs.create({ url: open.dataset.openUrl }); return; }
    const action = event.target.closest('button[data-action]');
    if (!action) return;
    const manualState = action.dataset.action === 'reconcile' ? 'reconciled' : null;
    const matching = ledger.filter(r => r.recordType === 'return' && r.orderId === action.dataset.order);
    for (const record of matching) await storage.updateRecord(record.recordId, { manualState });
    await reload();
  });
  search.addEventListener('input', render);

  document.getElementById('startScanner').addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ type: 'ARL_START_FULL_SCAN' }); await renderScannerStatus();
  });
  document.getElementById('stopScanner').addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ type: 'ARL_STOP_FULL_SCAN' }); await renderScannerStatus();
  });
  document.getElementById('restartScanner').addEventListener('click', async () => {
    if (!confirm('Restart the lifetime history scan from the current year? Existing ledger data will be kept.')) return;
    await chrome.runtime.sendMessage({ type: 'ARL_START_FULL_SCAN', restart: true }); await renderScannerStatus();
  });

  function download(filename, text, type) {
    const blob = new Blob([text], { type }); const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function refundIssuedDate(record) {
    return record?.returnMilestones?.refundIssued?.date || record?.refundIssuedDate || null;
  }

  function makeBankRequestEntry(row, record) {
    const amount = Number(record.refundAmount ?? record.refundSubtotal);
    return {
      returnRecordId: record.recordId,
      returnToken: record.returnToken || null,
      orderId: row.orderId,
      itemNames: uniqueStrings([...(record.itemNames || []), ...(row.itemNames || [])]),
      expectedRefund: Number.isFinite(amount) ? Number(amount.toFixed(2)) : null,
      paymentCardLast4: record.cardLast4 || row.cardLast4 || null,
      refundIssuedDate: refundIssuedDate(record),
      expectedCreditDate: storage.expectedCreditDate(record),
      amazonStage: storage.getReturnStage(record),
      amazonStatus: record.statusText || record.status || null
    };
  }

  async function exportBankVerificationRequest() {
    const rows = buildRows();
    const pending = [];
    const seen = new Set();
    for (const row of rows) {
      for (const record of row.returns || []) {
        if (storage.returnStageRank(record) < storage.RETURN_STAGE_RANK.refund_issued) continue;
        if (storage.isBankCreditConfirmed(record)) continue;
        if (seen.has(record.recordId)) continue;
        seen.add(record.recordId);
        pending.push(makeBankRequestEntry(row, record));
      }
    }
    if (!pending.length) {
      bankBridgeStatus.textContent = 'No refund-issued records currently need bank verification.';
      return;
    }
    const requestId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const payload = {
      schema: 'amazon-refund-credit-check-request/v1',
      requestId,
      generatedAt: new Date().toISOString(),
      sourceExtensionVersion: chrome.runtime.getManifest()?.version || null,
      privacy: 'Contains Amazon Order IDs, refund amounts, dates, item titles, and card last four only. No bank credentials or financial-provider tokens.',
      matchingPolicy: {
        amountTolerance: 0.01,
        preferSameCardLast4: true,
        preferAmazonMerchantEvidence: true,
        postedCreditOnlyForConfirmation: true,
        doNotReuseOneCreditForMultipleReturnsUnlessExplicitlyGrouped: true
      },
      returns: pending
    };
    await chrome.storage.local.set({
      lastBankVerificationRequest: {
        requestId,
        generatedAt: payload.generatedAt,
        returnRecordIds: pending.map(x => x.returnRecordId)
      }
    });
    download(`amazon-refund-credit-check-${new Date().toISOString().slice(0,10)}.json`, JSON.stringify(payload, null, 2), 'application/json');
    bankBridgeStatus.textContent = `Exported ${pending.length} refund${pending.length === 1 ? '' : 's'} for bank verification. Upload that JSON to ChatGPT and ask it to reconcile against your connected Finances accounts.`;
  }

  function normalizeBankResultEntry(entry) {
    const allowed = new Set(['confirmed', 'pending', 'not_found', 'ambiguous', 'needs_review']);
    const status = String(entry?.status || entry?.outcome || '').toLowerCase();
    if (!allowed.has(status)) throw new Error(`Unknown bank verification status: ${status || '(blank)'}`);
    const matchedAmount = entry?.matchedAmount == null ? null : Number(entry.matchedAmount);
    if (matchedAmount != null && !Number.isFinite(matchedAmount)) throw new Error('Invalid matchedAmount in bank result.');
    return {
      returnRecordId: String(entry.returnRecordId || ''),
      orderId: entry.orderId ? String(entry.orderId) : null,
      status,
      matchedAmount,
      postedDate: entry.postedDate || null,
      accountLast4: entry.accountLast4 ? String(entry.accountLast4).slice(-4) : null,
      accountName: entry.accountName ? String(entry.accountName).slice(0, 120) : null,
      merchantName: entry.merchantName ? String(entry.merchantName).slice(0, 160) : null,
      confidence: entry.confidence ? String(entry.confidence).slice(0, 40) : null,
      reason: entry.reason ? String(entry.reason).slice(0, 500) : null,
      checkedAt: entry.checkedAt || null
    };
  }

  async function importBankVerificationResult(payload) {
    if (!payload || payload.schema !== 'amazon-refund-credit-check-result/v1') throw new Error('This is not an Amazon Refund Ledger bank-result file.');
    const saved = await chrome.storage.local.get(['lastBankVerificationRequest']);
    const last = saved.lastBankVerificationRequest || null;
    if (last?.requestId && payload.requestId !== last.requestId) throw new Error('This bank result does not match the most recent exported verification request.');
    if (!Array.isArray(payload.matches)) throw new Error('Bank result is missing its matches array.');

    const currentLedger = await storage.getLedger();
    const byId = new Map(currentLedger.map(record => [record.recordId, record]));
    let applied = 0, missing = 0, confirmed = 0, review = 0;
    const checkedAt = payload.checkedAt || payload.generatedAt || new Date().toISOString();

    for (const raw of payload.matches) {
      const match = normalizeBankResultEntry(raw);
      if (!match.returnRecordId || !byId.has(match.returnRecordId)) { missing += 1; continue; }
      const record = byId.get(match.returnRecordId);
      const expected = Number(record.refundAmount ?? record.refundSubtotal);
      if (match.status === 'confirmed' && Number.isFinite(expected) && Number.isFinite(match.matchedAmount) && Math.abs(expected - match.matchedAmount) > 0.011) {
        throw new Error(`Confirmed amount for ${record.orderId} does not match the expected refund.`);
      }
      const bankVerification = {
        status: match.status,
        matchedAmount: match.matchedAmount,
        postedDate: match.postedDate,
        accountLast4: match.accountLast4,
        accountName: match.accountName,
        merchantName: match.merchantName,
        confidence: match.confidence,
        reason: match.reason,
        checkedAt,
        verifiedAt: match.status === 'confirmed' ? checkedAt : null,
        source: 'chatgpt-finances-bridge',
        requestId: payload.requestId
      };
      await storage.updateRecord(match.returnRecordId, { bankVerification });
      applied += 1;
      if (match.status === 'confirmed') confirmed += 1;
      if (match.status === 'ambiguous' || match.status === 'needs_review') review += 1;
    }

    await chrome.storage.local.set({
      lastBankVerificationImport: {
        requestId: payload.requestId,
        importedAt: new Date().toISOString(),
        applied,
        confirmed,
        review,
        missing
      }
    });
    bankBridgeStatus.textContent = `Imported bank verification: ${confirmed} confirmed, ${review} need review, ${Math.max(0, applied - confirmed - review)} still pending${missing ? `, ${missing} unmatched record IDs` : ''}.`;
    await reload();
  }

  async function readJsonFile(file) {
    const text = await file.text();
    return JSON.parse(text);
  }

  function csvCell(value) { const s = String(value ?? ''); return `"${s.replace(/"/g, '""')}"`; }
  document.getElementById('exportCsv').addEventListener('click', () => {
    const headers = ['status','order_id','items','order_total','expected_refund','card_last4','amazon_status','detail_complete','order_details_url','last_scanned_at'];
    const lines = [headers.map(csvCell).join(',')];
    for (const row of buildRows()) lines.push([row.statusLabel,row.orderId,row.itemNames.join(' | '),row.orderTotal ?? '',row.refundAmount ?? '',row.cardLast4 || '',row.amazonStatus,row.detailComplete,row.openUrl,row.lastScannedAt || ''].map(csvCell).join(','));
    download(`amazon-refund-ledger-${new Date().toISOString().slice(0,10)}.csv`, lines.join('\n'), 'text/csv;charset=utf-8');
  });
  document.getElementById('exportJson').addEventListener('click', () => {
    download(`amazon-refund-ledger-${new Date().toISOString().slice(0,10)}.json`, JSON.stringify({ exportedAt: new Date().toISOString(), settings, rows: buildRows(), ledger }, null, 2), 'application/json');
  });
  document.getElementById('exportBankRequest').addEventListener('click', () => {
    exportBankVerificationRequest().catch(error => { bankBridgeStatus.textContent = `Bank check export failed: ${error?.message || error}`; });
  });
  document.getElementById('importBankResult').addEventListener('click', () => bankResultFile.click());
  bankResultFile.addEventListener('change', async () => {
    const file = bankResultFile.files?.[0];
    if (!file) return;
    try {
      const payload = await readJsonFile(file);
      await importBankVerificationResult(payload);
    } catch (error) {
      bankBridgeStatus.textContent = `Bank result import failed: ${error?.message || error}`;
    } finally {
      bankResultFile.value = '';
    }
  });
  document.getElementById('clearLedger').addEventListener('click', async () => {
    if (!confirm('Clear the entire local Amazon Refund Ledger?')) return; await storage.setLedger([]); await reload();
  });

  chrome.storage.onChanged.addListener(changes => {
    if (changes.ledger || changes.backgroundScanState) { reload().catch(() => {}); renderScannerStatus().catch(() => {}); }
  });

  reload(); renderScannerStatus(); setInterval(renderScannerStatus, 1800);
})();
