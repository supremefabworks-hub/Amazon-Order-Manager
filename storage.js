(() => {
  'use strict';

  const DEFAULT_SETTINGS = {
    reviewStatuses: ['refund_expected', 'returned_pending_refund', 'return_in_progress', 'unknown'],
    autoScan: true,
    autoDetailScan: true,
    autoReturnScan: false,
    autoHistoryCrawl: true,
    showUpdateToast: true,
    workflowRecorderEnabled: false
  };

  const RETURN_STAGE_RANK = {
    unknown: 0,
    started: 1,
    shipped: 2,
    received: 3,
    refund_issued: 4,
    refunded: 4,
    credited: 5
  };

  const STATUS_RANK = {
    unknown: 0,
    purchase: 0,
    return_in_progress: 1,
    refund_expected: 1,
    returned_pending_refund: 3,
    refunded: 4
  };

  async function getLedger() {
    const data = await chrome.storage.local.get(['ledger']);
    return Array.isArray(data.ledger) ? data.ledger : [];
  }

  async function setLedger(ledger) {
    await chrome.storage.local.set({ ledger });
  }

  async function getSettings() {
    const data = await chrome.storage.local.get(['settings']);
    const { ignoredCardLast4, ...cleanSettings } = data.settings || {};
    return { ...DEFAULT_SETTINGS, ...cleanSettings };
  }

  async function setSettings(settings) {
    const { ignoredCardLast4, ...cleanSettings } = settings || {};
    await chrome.storage.local.set({ settings: { ...DEFAULT_SETTINGS, ...cleanSettings } });
  }

  function mergeArray(existing, incoming) {
    const out = [];
    const seen = new Set();
    for (const value of [...(existing || []), ...(incoming || [])]) {
      const normalized = String(value || '').trim();
      if (!normalized) continue;
      const key = normalized.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        out.push(normalized);
      }
    }
    return out;
  }

  function stageFromText(text) {
    const t = String(text || '').toLowerCase();
    if (/(?:your refund (?:has been|was) credited|we (?:have )?credited your refund|refund (?:has been|was) credited to)/.test(t)) return 'credited';
    if (/(?:we (?:have )?issued your refund|your refund (?:has been|was) issued|refund has been issued|refund issued\s+(?:on|\$))/.test(t)) return 'refund_issued';
    if (/return (?:received|complete|completed)|received your return|item received|return processed/.test(t)) return 'received';
    if (/return in transit|on the way back|return shipped|shipped back|dropped off|drop-?off complete|carrier received/.test(t)) return 'shipped';
    if (/return request|accepted your return|drop off by|dropoff by|return code|refund will be issued|estimated refund|refund method|refund subtotal|return status link detected/.test(t)) return 'started';
    return 'unknown';
  }

  function getReturnStage(record) {
    if (!record || record.recordType !== 'return') return null;
    const explicit = String(record.returnStage || '').toLowerCase();
    if (explicit === 'refunded') return 'refund_issued'; // v0.6 compatibility
    if (RETURN_STAGE_RANK[explicit] !== undefined) return explicit;
    if (record.status === 'refunded') return 'refund_issued';
    if (record.status === 'returned_pending_refund') return 'received';
    return stageFromText(`${record.statusText || ''}\n${record.status || ''}`);
  }

  function returnStageRank(recordOrStage) {
    let stage = typeof recordOrStage === 'string' ? recordOrStage : getReturnStage(recordOrStage);
    if (stage === 'refunded') stage = 'refund_issued';
    return RETURN_STAGE_RANK[stage] ?? 0;
  }

  function bankVerificationStatus(record) {
    const raw = String(record?.bankVerification?.status || '').toLowerCase();
    if (['confirmed', 'pending', 'not_found', 'ambiguous', 'needs_review'].includes(raw)) return raw;
    return '';
  }

  function isBankCreditConfirmed(record) {
    return Boolean(record && (record.manualState === 'reconciled' || bankVerificationStatus(record) === 'confirmed'));
  }

  function isCreditConfirmed(record) {
    return Boolean(record && (returnStageRank(record) >= RETURN_STAGE_RANK.credited || isBankCreditConfirmed(record)));
  }

  function expectedCreditDate(record) {
    return record?.expectedCreditDate || record?.returnMilestones?.expectedCreditDate || null;
  }

  function parseLooseDate(value, referenceYear = new Date().getFullYear()) {
    if (!value) return null;
    const text = String(value).trim();
    const m = text.match(/^([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?$/);
    if (m) {
      const d = new Date(`${m[1]} ${m[2]}, ${m[3] || referenceYear} 23:59:59`);
      return Number.isNaN(d.getTime()) ? null : d;
    }
    const direct = new Date(value);
    return Number.isNaN(direct.getTime()) ? null : direct;
  }

  function needsCreditReview(record, now = new Date()) {
    if (!record || record.recordType !== 'return') return false;
    if (record.itemIdentityConflict) return true;
    if (record.manualState === 'reconciled' || isCreditConfirmed(record)) return false;
    const rank = returnStageRank(record);
    if (rank < RETURN_STAGE_RANK.refund_issued) return true;
    const status = bankVerificationStatus(record);
    if (status === 'ambiguous' || status === 'needs_review') return true;
    const eta = parseLooseDate(expectedCreditDate(record), now.getFullYear());
    if (!eta) return false;
    const graceEnd = new Date(eta.getTime() + 24 * 60 * 60 * 1000);
    return now.getTime() > graceEnd.getTime();
  }

  function returnProgress(record) {
    const stage = getReturnStage(record) || 'unknown';
    const rank = returnStageRank(stage);
    const creditConfirmed = isCreditConfirmed(record);
    return {
      stage,
      rank,
      percent: creditConfirmed ? 100 : rank >= 4 ? 67 : rank >= 2 ? 34 : 0,
      started: rank >= 1,
      shippedOrReceived: rank >= 2,
      refundIssued: rank >= 4,
      credited: creditConfirmed,
      amazonCredited: rank >= 5,
      bankCreditConfirmed: isBankCreditConfirmed(record),
      bankVerificationStatus: bankVerificationStatus(record),
      refunded: rank >= 4,
      milestones: record?.returnMilestones || null
    };
  }

  function mergeReturnMilestones(existing, incoming) {
    if (!existing) return incoming || null;
    if (!incoming) return existing || null;
    const out = { ...existing, ...incoming };
    for (const key of ['started', 'shipped', 'refundIssued', 'credited']) {
      const a = existing[key] || {};
      const b = incoming[key] || {};
      out[key] = {
        ...a,
        ...b,
        done: Boolean(a.done || b.done),
        date: (key === 'credited' && !Boolean(a.done || b.done)) ? null : (b.date || a.date || null)
      };
    }
    const aRank = returnStageRank(existing.stage || 'unknown');
    const bRank = returnStageRank(incoming.stage || 'unknown');
    out.stage = bRank >= aRank ? (incoming.stage || existing.stage) : existing.stage;
    out.expectedCreditDate = incoming.expectedCreditDate || existing.expectedCreditDate || null;
    return out;
  }

  function trustedReturnIdentityDecision(existing, incoming) {
    const none = { bound: false, preserve: false, conflict: false };
    if (existing?.recordType !== 'return' || incoming?.recordType !== 'return') return none;
    if (existing.itemIdentitySource !== 'order-detail-return-link') return none;
    if (!existing.returnItemId || !incoming.returnItemId || existing.returnItemId !== incoming.returnItemId) return none;

    const existingAsins = new Set((existing.asins || []).map(value => String(value || '').toUpperCase()).filter(Boolean));
    const incomingAsins = new Set((incoming.asins || []).map(value => String(value || '').toUpperCase()).filter(Boolean));
    const existingNames = new Set((existing.itemNames || []).map(value => String(value || '').trim().toLowerCase()).filter(Boolean));
    const incomingNames = new Set((incoming.itemNames || []).map(value => String(value || '').trim().toLowerCase()).filter(Boolean));

    if (incomingAsins.size) {
      for (const asin of existingAsins) if (incomingAsins.has(asin)) return { bound: true, preserve: false, conflict: false };
      if (existingAsins.size) return { bound: true, preserve: true, conflict: true };
    }
    if (incomingNames.size) {
      for (const name of existingNames) if (incomingNames.has(name)) return { bound: true, preserve: true, conflict: false };
      if (existingNames.size) return { bound: true, preserve: true, conflict: true };
    }
    return { bound: true, preserve: true, conflict: false };
  }

  function mergeRecord(existing, incoming, scannedAt) {
    const merged = { ...existing };
    const existingStageRank = returnStageRank(existing);
    const incomingStageRank = returnStageRank(incoming);
    const wouldRegressReturn = existing?.recordType === 'return' && incoming?.recordType === 'return' && incomingStageRank < existingStageRank;
    const existingStatusRank = STATUS_RANK[existing?.status] ?? 0;
    const incomingStatusRank = STATUS_RANK[incoming?.status] ?? 0;
    const trustedIdentity = trustedReturnIdentityDecision(existing, incoming);

    for (const [key, value] of Object.entries(incoming)) {
      if (value === null || value === undefined || value === '') continue;
      if (wouldRegressReturn && ['returnStage', 'status', 'statusText'].includes(key)) continue;
      if (key === 'status' && incomingStatusRank < existingStatusRank) continue;
      if (Array.isArray(value)) {
        if (trustedIdentity.preserve && ['itemNames', 'asins'].includes(key)) {
          merged[key] = mergeArray([], existing?.[key] || []);
        } else if (incoming?.recordType === 'return' && incoming?.authoritativeReturnCapture && ['itemNames', 'asins'].includes(key)) merged[key] = mergeArray([], value);
        else merged[key] = mergeArray(existing?.[key], value);
      }
      else if (key === 'returnMilestones') merged[key] = mergeReturnMilestones(existing?.[key], value);
      else if (key === 'detailScanComplete') merged[key] = Boolean(existing?.[key] || value);
      else if (trustedIdentity.bound && key === 'itemIdentitySource') merged[key] = existing.itemIdentitySource;
      else merged[key] = value;
    }

    if (trustedIdentity.bound) merged.itemIdentitySource = existing.itemIdentitySource;
    if (trustedIdentity.conflict) {
      merged.itemIdentityConflict = true;
      merged.itemIdentityConflictIncoming = {
        itemNames: mergeArray([], incoming.itemNames || []),
        asins: mergeArray([], incoming.asins || []),
        source: incoming.itemIdentitySource || null
      };
    }

    if (merged.recordType === 'return') {
      const stage = getReturnStage(merged);
      if (stage) merged.returnStage = stage;
    }
    merged.firstSeenAt = existing?.firstSeenAt || scannedAt;
    merged.lastScannedAt = scannedAt;
    merged.manualState = existing?.manualState || null;
    merged.note = existing?.note || '';
    return merged;
  }

  function comparableRecord(record) {
    const ignored = new Set(['firstSeenAt', 'lastScannedAt', 'manualState', 'note', 'sourceUrl', 'sourceHost', 'pageTitle', 'detailScannedAt']);
    const out = {};
    for (const key of Object.keys(record || {}).sort()) {
      if (ignored.has(key)) continue;
      const value = record[key];
      if (Array.isArray(value)) out[key] = [...value].map(v => String(v)).sort();
      else out[key] = value ?? null;
    }
    return JSON.stringify(out);
  }

  function isConfirmedReturn(record) {
    if (!record || record.recordType !== 'return') return false;
    return returnStageRank(record) >= RETURN_STAGE_RANK.received;
  }

  function summarizeLedger(ledger) {
    const allOrders = new Set();
    const detailedOrders = new Set();
    const returnedOrders = new Set();
    const confirmedReturnedOrders = new Set();
    const refundedOrders = new Set();
    const creditedOrders = new Set();
    const unresolvedReturnOrders = new Set();
    let returnRecords = 0;
    let confirmedReturnRecords = 0;
    let unresolvedReturnRecords = 0;

    for (const record of ledger || []) {
      if (!record?.orderId) continue;
      allOrders.add(record.orderId);
      if (record.recordType === 'order' && record.detailScanComplete) detailedOrders.add(record.orderId);
      if (record.recordType === 'return') {
        returnRecords += 1;
        returnedOrders.add(record.orderId);
        const rank = returnStageRank(record);
        if (rank >= RETURN_STAGE_RANK.received) {
          confirmedReturnRecords += 1;
          confirmedReturnedOrders.add(record.orderId);
        }
        if (rank >= RETURN_STAGE_RANK.refund_issued) refundedOrders.add(record.orderId);
        if (isCreditConfirmed(record)) creditedOrders.add(record.orderId);
        if (needsCreditReview(record)) {
          unresolvedReturnRecords += 1;
          unresolvedReturnOrders.add(record.orderId);
        }
      }
    }

    return {
      lifetimeOrders: allOrders.size,
      detailedOrders: detailedOrders.size,
      returnedOrders: returnedOrders.size,
      confirmedReturnedOrders: confirmedReturnedOrders.size,
      refundedOrders: refundedOrders.size,
      creditedOrders: creditedOrders.size,
      unresolvedReturnOrders: unresolvedReturnOrders.size,
      returnRecords,
      confirmedReturnRecords,
      unresolvedReturnRecords,
      records: (ledger || []).length
    };
  }

  async function upsertRecords(records) {
    const ledger = await getLedger();
    const beforeSummary = summarizeLedger(ledger);
    const byId = new Map(ledger.map(r => [r.recordId, r]));
    const scannedAt = new Date().toISOString();
    let inserted = 0;
    let updated = 0;
    let unchanged = 0;
    let removed = 0;
    const changedRecordIds = [];

    const authoritativeGroups = new Map();
    for (const record of (records || []).filter(r => r?.recordType === 'return' && r?.authoritativeReturnCapture && r?.orderId && r?.returnToken)) {
      const key = `${record.orderId}:${record.returnToken}`;
      if (!authoritativeGroups.has(key)) authoritativeGroups.set(key, new Set());
      authoritativeGroups.get(key).add(record.recordId);
    }
    for (const [recordId, existing] of Array.from(byId.entries())) {
      if (existing?.recordType !== 'return' || !existing?.returnToken) continue;
      const keepIds = authoritativeGroups.get(`${existing.orderId}:${existing.returnToken}`);
      if (!keepIds || keepIds.has(recordId)) continue;
      if (!existing.provisionalReturn && !existing.authoritativeReturnCapture) continue;
      byId.delete(recordId);
      removed += 1;
      changedRecordIds.push(recordId);
    }

    for (const incoming of records || []) {
      if (!incoming?.recordId || !incoming?.orderId) continue;
      const existing = byId.get(incoming.recordId);
      const merged = mergeRecord(existing || {}, incoming, scannedAt);
      if (!existing) {
        inserted += 1;
        changedRecordIds.push(incoming.recordId);
        byId.set(incoming.recordId, merged);
        continue;
      }
      if (comparableRecord(existing) !== comparableRecord(merged)) {
        updated += 1;
        changedRecordIds.push(incoming.recordId);
        byId.set(incoming.recordId, merged);
      } else {
        unchanged += 1;
        if (incoming.detailScannedAt && incoming.detailScanComplete) {
          byId.set(incoming.recordId, { ...existing, detailScanComplete: true, detailScannedAt: incoming.detailScannedAt, lastScannedAt: scannedAt });
        }
      }
    }

    const changed = inserted > 0 || updated > 0 || removed > 0;
    let nextLedger = Array.from(byId.values()).sort((a, b) => String(b.lastScannedAt || b.firstSeenAt || '').localeCompare(String(a.lastScannedAt || a.firstSeenAt || '')));
    if (changed || nextLedger.some((r, i) => r !== ledger[i])) await setLedger(nextLedger);
    else nextLedger = ledger;

    const afterSummary = summarizeLedger(nextLedger);
    return { inserted, updated, removed, unchanged, changed, total: nextLedger.length, changedRecordIds, beforeSummary, afterSummary };
  }

  function effectiveState(record, settings) {
    if (record.manualState === 'reconciled') return 'reconciled';
    if (record.recordType === 'return' && isCreditConfirmed(record)) return 'credited';
    if (record.recordType === 'return' && needsCreditReview(record)) return 'needs_review';
    if (record.recordType === 'return' && returnStageRank(record) >= RETURN_STAGE_RANK.refund_issued) return 'refunded';
    if (record.recordType === 'return') return 'needs_review';
    return 'purchase';
  }

  async function updateRecord(recordId, patch) {
    const ledger = await getLedger();
    const index = ledger.findIndex(r => r.recordId === recordId);
    if (index < 0) return false;
    ledger[index] = { ...ledger[index], ...patch };
    await setLedger(ledger);
    return true;
  }

  window.AmazonRefundStorage = {
    DEFAULT_SETTINGS,
    RETURN_STAGE_RANK,
    getLedger,
    setLedger,
    getSettings,
    setSettings,
    upsertRecords,
    updateRecord,
    effectiveState,
    isConfirmedReturn,
    summarizeLedger,
    getReturnStage,
    returnStageRank,
    returnProgress,
    bankVerificationStatus,
    isBankCreditConfirmed,
    isCreditConfirmed,
    expectedCreditDate,
    needsCreditReview
  };
})();
