(() => {
  'use strict';

  const storage = window.AmazonRefundStorage;
  const itemModel = window.AmazonOrderItemModel;
  const body = document.getElementById('ledgerBody');
  const stats = document.getElementById('stats');
  const empty = document.getElementById('empty');
  const search = document.getElementById('search');
  const statusFilter = document.getElementById('statusFilter');
  const yearFilter = document.getElementById('yearFilter');
  const cardFilter = document.getElementById('cardFilter');
  const sortOrder = document.getElementById('sortOrder');
  const scannerStatus = document.getElementById('scannerStatus');
  const scannerCheckpoint = document.getElementById('scannerCheckpoint');
  const autoStartScanner = document.getElementById('autoStartScanner');
  const navAllCount = document.getElementById('navAllCount');
  const navReturnCount = document.getElementById('navReturnCount');
  const navReviewCount = document.getElementById('navReviewCount');
  const navErrorCount = document.getElementById('navErrorCount');
  const bankBridgeStatus = document.getElementById('bankBridgeStatus');
  const bankResultFile = document.getElementById('bankResultFile');
  const ledgerVersion = document.getElementById('ledgerVersion');
  const manifest = chrome.runtime.getManifest();
  const displayedVersion = String(manifest.version_name || manifest.version || '').trim();
  if (ledgerVersion) ledgerVersion.textContent = `AMAZON REFUND LEDGER${displayedVersion ? ` · v${displayedVersion}` : ''}`;
  let ledger = [];
  let settings = storage.DEFAULT_SETTINGS;
  let currentView = new URLSearchParams(location.search).get('view') || 'all';
  if (!['all', 'returns', 'needs_review', 'errors'].includes(currentView)) currentView = 'all';

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
  function replacementStageRank(stage) {
    return ({ detected:1, requested:2, ordered:2, shipped:3, delivered:4, complete:5 })[String(stage || '').toLowerCase()] || 0;
  }
  function replacementLabel(stage) {
    return ({
      detected: 'Replacement', requested: 'Replacement requested', ordered: 'Replacement ordered',
      shipped: 'Replacement shipped', delivered: 'Replacement delivered', complete: 'Replacement complete'
    })[String(stage || '').toLowerCase()] || 'Replacement';
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
      const replacementItems = itemJoin.items.filter(item => Boolean(item.replacementStage));
      const hasReplacement = replacementItems.length > 0;
      const replacementStage = replacementItems.map(item => item.replacementStage).filter(Boolean).sort((a,b) => replacementStageRank(a) - replacementStageRank(b))[0] || null;
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
      else if (hasReplacement) { stateKey = 'replacement'; statusLabel = replacementLabel(replacementStage); }

      const statusTexts = uniqueStrings(returnRecords.map(r => r.statusText).filter(Boolean));
      const replacementStatusTexts = uniqueStrings(replacementItems.map(item => item.replacementStatusText || replacementLabel(item.replacementStage)).filter(Boolean));
      const lastScannedAt = [order?.lastScannedAt, ...returnRecords.map(r => r.lastScannedAt)].filter(Boolean).sort().at(-1) || null;
      const itemNames = orderItemNames.length ? orderItemNames : returnedItemNames;
      const asins = uniqueStrings([...(order?.asins || []), ...(order?.orderItems || []).map(item => item?.asin), ...returnRecords.flatMap(r => r.asins || [])]);
      const orderDate = order?.orderDate || null;
      const orderYearMatch = String(orderDate || '').match(/\b(20\d{2})\b/);
      const orderYear = orderYearMatch ? orderYearMatch[1] : null;
      const parsedOrderDate = orderDate ? new Date(orderDate) : null;
      const sortTime = parsedOrderDate && !Number.isNaN(parsedOrderDate.getTime()) ? parsedOrderDate.getTime() : (lastScannedAt ? new Date(lastScannedAt).getTime() : 0);
      rows.push({
        orderId, order, returns: returnRecords, allReturns: allReturnRecords, returnGroups, hasReturn, hasReplacement, replacementStage, needsReview, terminalCancelled, stateKey, statusLabel,
        dataComplete, processingError, processingState: order?.processingState || null, expectedReturnCount, authoritativeCount,
        itemStates: itemJoin.items, unmatchedReturnGroups: itemJoin.unmatchedReturnGroups, returnedProductCount: itemJoin.returnedProductCount,
        itemNames, orderItemNames, returnedItemNames, searchItemNames: uniqueStrings([...orderItemNames, ...returnedItemNames]), asins,
        orderTotal: order?.purchaseAmount ?? null, refundAmount, canonicalRefundTotal, childRefundAmount,
        refundAmountMismatch, itemIdentityConflict, groupAmountConflict, strongUnmatchedReturnIdentity, bankAmazonConflict,
        cardLast4: order?.cardLast4 || returnRecords.find(r => r.cardLast4)?.cardLast4 || null,
        amazonStatus: uniqueStrings([...replacementStatusTexts, ...statusTexts]).join(' · ') || (order?.statusText || order?.status || '—'),
        detailComplete: Boolean(order?.detailScanComplete), detailScannedAt: order?.detailScannedAt || null,
        orderDate, orderYear, sortTime,
        lastScannedAt, openUrl: canonicalDetailUrl(orderId, order)
      });
    }
    return rows;
  }

  function lifecycleMarkup(group, index, totalGroups) {
    const record = group.representative;
    const progress = storage.returnProgress(record);
    const expectedCredit = !progress.amazonCredited ? storage.expectedCreditDate(record) || '' : '';
    const verificationRecord = group.records.find(r => r.bankVerification) || record;
    const verification = verificationRecord.bankVerification || null;
    const steps = [
      ['started', 'Initiated', progress.started, milestoneDate(record, 'started')],
      ['shipped', 'Dropped off', progress.shipped, milestoneDate(record, 'shipped')],
      ['received', 'Return received', progress.received, milestoneDate(record, 'received')],
      ['refundIssued', 'Refund issued', progress.refundIssued, milestoneDate(record, 'refundIssued')],
      ['credited', progress.amazonCredited ? 'Refund credited' : (expectedCredit ? `Expected ${expectedCredit}` : 'Refund credited'), progress.amazonCredited, milestoneDate(record, 'credited')]
    ];
    const items = group.itemNames.length ? group.itemNames.join(' · ') : 'Returned item pending authoritative scan';
    let verificationMarkup = '';
    if (progress.amazonBankConflict) {
      verificationMarkup = `<div class="bank-match bank-match-review"><strong>Bank/Amazon conflict</strong><span>Bank credit evidence exists before Amazon shows Refund issued. Verify the bank match.</span></div>`;
    } else if (verification) {
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
      <div class="lifecycle lifecycle-lineitem lifecycle-five">
        <div class="lifecycle-line"><span style="width:${progress.percent}%"></span></div>
        ${steps.map(step => `<div class="life-step ${step[2] ? 'done' : ''}"><small>${esc(step[3] || '')}</small><i>${step[2] ? '✓' : ''}</i><span>${esc(step[1])}</span></div>`).join('')}
      </div>
      ${verificationMarkup}
    </div>`;
  }

  function legacyReturnProgressMarkup(row) {
    if (!row.returnGroups.length) return '<span class="muted">—</span>';
    return `<div class="return-track-stack compact-return-stack">${row.returnGroups.map((group, index) => lifecycleMarkup(group, index + 1, row.returnGroups.length)).join('')}</div>`;
  }

  function orderProductStatusMarkup(row) {
    if (!row.itemStates?.length) return row.hasReturn ? legacyReturnProgressMarkup(row) : `<span class="muted tiny">${esc(row.statusLabel || 'Order')}</span>`;
    const products = row.itemStates.map((item, index) => {
      const groups = item.returnGroups || [];
      const representatives = groups.map(group => group.representative).filter(Boolean);
      const highest = representatives.slice().sort((a,b) => storage.returnStageRank(b) - storage.returnStageRank(a))[0] || null;
      const returnText = groups.length ? `${groups.length > 1 ? `${groups.length} returns · ` : ''}${stageLabel(storage.getReturnStage(highest))}` : '';
      const replacementText = item.replacementStage ? replacementLabel(item.replacementStage) : '';
      const workflowLabel = [replacementText, returnText].filter(Boolean).join(' · ') || 'Not returned';
      const meta = [
        item.quantity != null ? `Qty ${item.quantity}` : '',
        item.itemAmount != null ? money(item.itemAmount) : '',
        item.asin || '',
        item.fulfillmentStatus || '',
        item.replacementNoReturnRequired ? 'No return required' : ''
      ].filter(Boolean).join(' · ');
      const classes = [groups.length ? 'has-product-return' : '', item.replacementStage ? 'has-product-replacement' : ''].filter(Boolean).join(' ');
      const stateClass = groups.length ? 'product-returned' : item.replacementStage ? 'product-replacement' : 'product-not-returned';
      return `<div class="order-product-row ${classes}">
        <div class="order-product-head">
          <div><span class="order-product-index">${index + 1}</span><strong title="${esc(item.itemName)}">${esc(item.itemName)}</strong></div>
          <span class="product-state ${stateClass}">${esc(workflowLabel)}</span>
        </div>
        ${meta ? `<div class="muted tiny order-product-meta">${esc(meta)}</div>` : ''}
        ${groups.length ? `<div class="product-return-lifecycles">${groups.map((group, returnIndex) => lifecycleMarkup(group, returnIndex + 1, groups.length)).join('')}</div>` : ''}
      </div>`;
    }).join('');
    const unmatched = (row.unmatchedReturnGroups || []).map((entry, index) => {
      const group = entry.group;
      const title = group?.itemNames?.length ? group.itemNames.join(' · ') : 'Returned item with no purchased-item match';
      return `<div class="order-product-row unmatched-product-return"><div class="order-product-head"><div><span class="order-product-index">!</span><strong>${esc(title)}</strong></div><span class="product-state product-unmatched">Unmatched return</span></div>${lifecycleMarkup(group, index + 1, row.unmatchedReturnGroups.length)}</div>`;
    }).join('');
    return `<div class="order-product-stack">${products}${unmatched}</div>`;
  }

  function setDynamicOptions(select, values, allLabel) {
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
    if (value === 'replacement') return row.hasReplacement;
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
  }

  function sum(rows, field) { return rows.reduce((total,row) => total + (Number.isFinite(Number(row[field])) ? Number(row[field]) : 0), 0); }
  function returnRecordAmountTotal(records) {
    return groupReturnRecords(dedupeReturns(records || [])).reduce((total, group) => total + (Number.isFinite(Number(group.amount)) ? Number(group.amount) : 0), 0);
  }
  function needsReviewExpectedAmount(row) {
    const recordTotal = returnRecordAmountTotal((row.returns || []).filter(r => storage.needsCreditReview(r)));
    if (row.refundAmountMismatch || row.itemIdentityConflict || row.groupAmountConflict || row.strongUnmatchedReturnIdentity) {
      const orderExpected = row.refundAmount;
      if (orderExpected !== null && orderExpected !== undefined && orderExpected !== '' && Number.isFinite(Number(orderExpected))) return Number(orderExpected);
    }
    return recordTotal;
  }

  function renderStats() {
    const allRows = buildRows();
    const rows = allRows.filter(r => r.dataComplete);
    const errorRows = allRows.filter(r => Boolean(r.processingError));
    const returnRows = rows.filter(r => r.hasReturn);
    const reviewRows = rows.filter(r => r.needsReview);
    const issued = rows.filter(r => r.hasReturn && r.returns.every(ret => storage.returnStageRank(ret) >= storage.RETURN_STAGE_RANK.refund_issued));
    const bankCredited = rows.filter(r => r.hasReturn && r.returns.every(ret => storage.isBankCreditConfirmed(ret)));
    const reviewExpectedTotal = reviewRows.reduce((total, row) => total + needsReviewExpectedAmount(row), 0);
    navAllCount.textContent = String(rows.length);
    navReturnCount.textContent = String(returnRows.length);
    navReviewCount.textContent = String(reviewRows.length);
    navErrorCount.textContent = String(errorRows.length);
    stats.innerHTML = `
      <div class="stat"><span>Complete orders</span><strong>${rows.length}</strong><small>${money(sum(rows, 'orderTotal'))} captured order total · fully processed canonical orders</small></div>
      <div class="stat"><span>Returns</span><strong>${returnRows.length}</strong><small>${money(sum(returnRows, 'refundAmount'))} expected refunds</small></div>
      <div class="stat stat-review-total"><span>Return review</span><strong>${money(reviewExpectedTotal)}</strong><small>${reviewRows.length} flagged ${reviewRows.length === 1 ? 'order' : 'orders'}</small></div>
      <div class="stat"><span>Errors</span><strong>${errorRows.length}</strong><small>Require retry or investigation</small></div>`;
  }

  function renderViewMenu() {
    for (const button of document.querySelectorAll('.view-button')) button.classList.toggle('active', button.dataset.view === currentView);
  }

  function badgeLabel(row) {
    if (row.stateKey === 'purchase') return row.detailComplete ? 'Order' : 'Order queued';
    if (row.stateKey === 'cancelled') return 'Cancelled';
    if (row.stateKey === 'needs_review') return row.statusLabel || 'Return review';
    if (row.stateKey === 'refund_issued') return 'Refund issued';
    if (row.stateKey === 'credited') return 'Amazon credited';
    if (row.stateKey === 'reconciled') return 'Reconciled';
    return row.statusLabel || 'Return';
  }

  function renderTable() {
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
        ? `<div class="processing-error"><strong>Order processing error</strong><span>${esc(row.processingError)}</span><small>Use Reset & Refresh to retry this order after the underlying Amazon issue is resolved.</small></div>`
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
          <button class="mini action-large" data-reset-refresh-order="${esc(row.orderId)}" ${row.openUrl ? '' : 'disabled'}>Reset & Refresh</button>
        </div>
      </article>`;
    }).join('');
  }

  function renderAutoStart() {
    if (!autoStartScanner) return;
    const enabled = Boolean(settings.autoStartOnAmazon);
    autoStartScanner.textContent = `Auto-start: ${enabled ? 'On' : 'Off'}`;
    autoStartScanner.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    autoStartScanner.classList.toggle('auto-start-enabled', enabled);
  }

  function render() { renderStats(); renderViewMenu(); renderTable(); renderAutoStart(); }

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
      const resumeInfo = crawl.lastResumeAt ? ` · resume #${crawl.resumeCount || 1} from ${crawl.resumePageKey || `${crawl.currentYear}:${crawl.currentPage || 1}`} (${crawl.lastResumeSource || 'resume'})` : '';
      scannerCheckpoint.textContent = crawl.currentYear
        ? `Checkpoint: ${crawl.currentYear} page ${crawl.currentPage || 1} · ${doneOnPage}/${pageCount || '?'} details complete · ${crawl.ordersCompleted || 0} unique orders completed · ${crawl.overlapCount || 0} overlapping history hits${crawl.lastCompletedOrderId ? ` · last ${crawl.lastCompletedOrderId}` : ''}${resumeInfo}${yearsDone}`
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
    if (!['all', 'returns', 'needs_review', 'errors'].includes(view)) return;
    currentView = view;
    const url = new URL(location.href); url.searchParams.set('view', view); history.replaceState(null, '', url.toString());
    render();
  }

  document.querySelector('.view-menu').addEventListener('click', event => {
    const button = event.target.closest('[data-view]'); if (button) setView(button.dataset.view);
  });
  body.addEventListener('click', async event => {
    const resetRefresh = event.target.closest('button[data-reset-refresh-order]');
    if (resetRefresh && !resetRefresh.disabled) {
      const original = resetRefresh.textContent;
      resetRefresh.disabled = true;
      resetRefresh.textContent = 'Rebuilding…';
      try {
        const response = await chrome.runtime.sendMessage({ type: 'ARL_RESET_REFRESH_ORDER', orderId: resetRefresh.dataset.resetRefreshOrder });
        if (!response?.ok) throw new Error(response?.error || 'Reset & Refresh failed');
        await reload();
      } catch (error) {
        alert(`Order rebuild failed: ${error?.message || error}`);
        await reload().catch(() => {});
      } finally {
        resetRefresh.disabled = false;
        resetRefresh.textContent = original;
      }
      return;
    }
    const open = event.target.closest('[data-open-url]');
    if (open && open.dataset.openUrl) { await chrome.tabs.create({ url: open.dataset.openUrl }); return; }
    const action = event.target.closest('button[data-action]');
    if (!action) return;
    if (action.dataset.action !== 'reconcile') return;
    const matching = ledger.filter(r => r.recordType === 'return' && r.orderId === action.dataset.order);
    for (const record of matching) await storage.updateRecord(record.recordId, { manualState: 'reconciled' });
    await reload();
  });
  search.addEventListener('input', render);
  for (const control of [statusFilter, yearFilter, cardFilter, sortOrder]) control?.addEventListener('change', render);


  autoStartScanner?.addEventListener('click', async () => {
    const enabled = !Boolean(settings.autoStartOnAmazon);
    const response = await chrome.runtime.sendMessage({ type: 'ARL_SET_AUTO_START', enabled });
    if (!response?.ok) { alert(`Could not update Auto-start: ${response?.error || 'unknown error'}`); return; }
    settings = { ...settings, autoStartOnAmazon: enabled };
    renderAutoStart();
  });

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
    const rows = buildRows().filter(row => row.dataComplete);
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
    const headers = ['status','order_id','product_count','returned_product_count','items','product_statuses','order_total','expected_refund','card_last4','amazon_status','detail_complete','order_details_url','last_scanned_at'];
    const lines = [headers.map(csvCell).join(',')];
    for (const row of buildRows().filter(row => row.dataComplete)) {
      const productStatuses = (row.itemStates || []).map(item => `${item.itemName} => ${(item.returnGroups || []).length ? stageLabel(storage.getReturnStage(item.returnGroups[0]?.representative)) : 'Not returned'}`).join(' | ');
      lines.push([row.statusLabel,row.orderId,row.itemStates?.length || row.itemNames.length,row.returnedProductCount || 0,row.itemNames.join(' | '),productStatuses,row.orderTotal ?? '',row.refundAmount ?? '',row.cardLast4 || '',row.amazonStatus,row.detailComplete,row.openUrl,row.lastScannedAt || ''].map(csvCell).join(','));
    }
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
