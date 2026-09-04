'use strict';

const STATE_KEY = 'backgroundScanState';
const SETTINGS_KEY = 'settings';
const LEDGER_KEY = 'ledger';
const ALARM_NAME = 'arl-background-queue';
const WORKER_TAB_KEY = 'arlWorkerTabId';
const DETAIL_REFRESH_MS = 7 * 24 * 60 * 60 * 1000;
const RETURN_DETAIL_REFRESH_MS = 24 * 60 * 60 * 1000;
const RETURN_STATUS_REFRESH_MS = 6 * 60 * 60 * 1000;
const HISTORY_REFRESH_MS = 24 * 60 * 60 * 1000;
const JOB_DELAY_MIN_MS = 75;
const JOB_DELAY_MAX_MS = 250;
const FETCH_DISPATCH_MIN_MS = 60;
const FETCH_DISPATCH_MAX_MS = 140;
const READY_INITIAL_MIN_MS = 100;
const READY_INITIAL_MAX_MS = 150;
const READY_POLL_MIN_MS = 75;
const READY_POLL_MAX_MS = 125;
const READY_TIMEOUT_MS = 700;
const BURST_MIN_JOBS = 60;
const BURST_MAX_JOBS = 90;
const COOLDOWN_MIN_MS = 8000;
const COOLDOWN_MAX_MS = 15000;
const RATE_LIMIT_COOLDOWN_MIN_MS = 10 * 60 * 1000;
const RATE_LIMIT_COOLDOWN_MAX_MS = 20 * 60 * 1000;
const LOAD_TIMEOUT_MS = 45000;
const MAX_RECENT_KEYS = 6000;
const WORKFLOW_LOG_KEY = 'workflowLog';
const VERSION_KEY = 'installedExtensionVersion';
const DEV_RESET_ON_VERSION_CHANGE = true;
const MAX_WORKFLOW_EVENTS = 1600;
let workflowRecorderEnabled = false;

let processing = false;
let workerTabId = null;

async function ensureDevelopmentVersionState(previousVersionHint = null) {
  const version = chrome.runtime?.getManifest?.()?.version || null;
  if (!version) return { changed: false, version: null };
  const data = await chrome.storage.local.get([VERSION_KEY]);
  const prior = data[VERSION_KEY] || previousVersionHint || null;
  if (prior === version) return { changed: false, version };
  if (DEV_RESET_ON_VERSION_CHANGE && prior) {
    await chrome.storage.local.remove([
      LEDGER_KEY, STATE_KEY, WORKER_TAB_KEY, WORKFLOW_LOG_KEY,
      'lastBankVerificationRequest', 'lastBankVerificationImport'
    ]);
    workerTabId = null;
  }
  await chrome.storage.local.set({ [VERSION_KEY]: version });
  return { changed: Boolean(prior && prior !== version), previousVersion: prior, version };
}

function randomBetween(min, max) {
  return Math.floor(min + Math.random() * Math.max(1, max - min + 1));
}

function randomizedJobDelay() {
  return randomBetween(JOB_DELAY_MIN_MS, JOB_DELAY_MAX_MS);
}

function ensureCooldownPlan(state) {
  if (!Number.isInteger(state.cooldownAfter) || state.cooldownAfter < BURST_MIN_JOBS) {
    state.cooldownAfter = randomBetween(BURST_MIN_JOBS, BURST_MAX_JOBS);
  }
  return state;
}

function cooldownRemainingMs(state) {
  const until = state?.cooldownUntil ? new Date(state.cooldownUntil).getTime() : 0;
  return Number.isFinite(until) ? Math.max(0, until - Date.now()) : 0;
}

function nowIso() {
  return new Date().toISOString();
}

function sanitizeWorkflowUrl(value) {
  try {
    const u = new URL(value);
    const interesting = {};
    for (const [key, val] of u.searchParams.entries()) {
      if (/(order|page|start|index|filter|year|return|refund|rma|contract)/i.test(`${key} ${val}`)) {
        interesting[key] = String(val).slice(0, 300);
      }
    }
    return { origin: u.origin, pathname: u.pathname, interestingParams: interesting, queryKeys: Array.from(new Set([...u.searchParams.keys()])).slice(0, 80) };
  } catch (_) { return null; }
}

function workflowFormData(requestBody) {
  const form = requestBody?.formData || null;
  if (!form) return null;
  const out = {};
  for (const [key, values] of Object.entries(form)) {
    const joined = `${key} ${(values || []).join(' ')}`;
    if (!/(order|page|start|index|filter|year|return|refund|rma|contract)/i.test(joined)) continue;
    out[key] = (values || []).map(v => String(v).slice(0, 300)).slice(0, 20);
  }
  return Object.keys(out).length ? out : null;
}

async function appendWorkflowEvent(entry) {
  if (!workflowRecorderEnabled) return;
  try {
    const data = await chrome.storage.local.get([WORKFLOW_LOG_KEY]);
    const log = Array.isArray(data[WORKFLOW_LOG_KEY]) ? data[WORKFLOW_LOG_KEY] : [];
    log.push({ at: nowIso(), ...entry });
    if (log.length > MAX_WORKFLOW_EVENTS) log.splice(0, log.length - MAX_WORKFLOW_EVENTS);
    await chrome.storage.local.set({ [WORKFLOW_LOG_KEY]: log });
  } catch (_) {}
}

async function refreshWorkflowRecorderFlag() {
  try {
    const data = await chrome.storage.local.get([SETTINGS_KEY]);
    workflowRecorderEnabled = Boolean(data?.[SETTINGS_KEY]?.workflowRecorderEnabled);
  } catch (_) { workflowRecorderEnabled = false; }
}

function defaultState() {
  return {
    queue: [],
    recent: {},
    running: false,
    paused: false,
    processed: 0,
    detailProcessed: 0,
    returnProcessed: 0,
    historyProcessed: 0,
    historyYearsProcessed: {},
    lastHistoryUrl: null,
    lastHistoryAdvanceMethod: null,
    lastHistoryAdvanceError: null,
    errors: 0,
    currentJob: null,
    lastError: null,
    lastUpdatedAt: null,
    startedAt: null,
    jobsSinceCooldown: 0,
    cooldownAfter: null,
    cooldownUntil: null,
    rateLimitedCount: 0,
    crawl: {
      active: false, phase: 'idle', years: [], completedYears: [], currentYear: null, currentPage: null,
      currentHistoryUrl: null, currentPageOrderIds: [], currentPageCompleted: 0,
      seenOrders: {}, seenPages: {}, completedOrders: {}, overlapCount: 0, overlapExamples: [],
      pagesCompleted: 0, ordersCompleted: 0, lastCompletedOrderId: null, lastCompletedAt: null,
      startedAt: null, completedAt: null
    }
  };
}

async function getState() {
  const data = await chrome.storage.local.get([STATE_KEY]);
  return ensureCrawl({ ...defaultState(), ...(data[STATE_KEY] || {}) });
}

function ensureCrawl(state) {
  const base = defaultState().crawl;
  state.crawl = { ...base, ...(state.crawl || {}) };
  state.crawl.years = Array.from(new Set((state.crawl.years || []).map(Number).filter(Number.isFinite))).sort((a,b) => b-a);
  state.crawl.completedYears = Array.from(new Set((state.crawl.completedYears || []).map(Number).filter(Number.isFinite))).sort((a,b) => b-a);
  state.crawl.seenOrders = state.crawl.seenOrders || {};
  state.crawl.seenPages = state.crawl.seenPages || {};
  state.crawl.completedOrders = state.crawl.completedOrders || {};
  state.crawl.overlapExamples = Array.isArray(state.crawl.overlapExamples) ? state.crawl.overlapExamples.slice(-50) : [];
  return state;
}

async function setState(state) {
  state.lastUpdatedAt = nowIso();
  await chrome.storage.local.set({ [STATE_KEY]: state });
}

async function getSettings() {
  const data = await chrome.storage.local.get([SETTINGS_KEY]);
  return {
    autoScan: true,
    autoDetailScan: true,
    autoReturnScan: false,
    autoHistoryCrawl: true,
    showUpdateToast: true,
    workflowRecorderEnabled: false,
    ...(() => { const { ignoredCardLast4, ...clean } = data[SETTINGS_KEY] || {}; return clean; })()
  };
}

function jobKey(job) {
  if (job.type === 'return') return `return:${job.orderId || ''}:${normalizeUrl(job.url) || job.url}`;
  if (job.type === 'detail') return `detail:${job.orderId || job.url}`;
  if (job.type === 'advance') return job.customKey || `advance:${job.crawlPageKey || normalizeUrl(job.url) || job.url}`;
  return `history:${normalizeUrl(job.url) || job.url}`;
}

function compactRecent(recent) {
  const entries = Object.entries(recent || {});
  if (entries.length <= MAX_RECENT_KEYS) return recent || {};
  entries.sort((a, b) => String(b[1]).localeCompare(String(a[1])));
  return Object.fromEntries(entries.slice(0, MAX_RECENT_KEYS));
}

function historyRouteFromUrl(value) {
  try {
    const u = new URL(value);
    const hash = String(u.hash || '');
    let match = hash.match(/#time\/(20\d{2})\/pagination\/(\d+|next)\/?/i);
    if (match) return { year: Number(match[1]), page: /^\d+$/.test(match[2]) ? Number(match[2]) : null, token: match[2].toLowerCase(), mode: 'hash-time' };
    match = hash.match(/#pagination\/(\d+|next)\/?/i);
    if (match) return { year: null, page: /^\d+$/.test(match[1]) ? Number(match[1]) : null, token: match[1].toLowerCase(), mode: 'hash' };
    const raw = u.searchParams.get('orderFilter') || u.searchParams.get('timeFilter') || '';
    const yearMatch = String(raw).match(/(?:year[-_:]?)?(20\d{2})/i);
    const startRaw = u.searchParams.get('startIndex');
    const start = startRaw == null || startRaw === '' ? NaN : Number(startRaw);
    let page = Number.isFinite(start) && start >= 0 ? Math.floor(start / 10) + 1 : null;
    for (const key of ['page','pageNumber','pageNo','pageNum']) {
      if (page != null) break;
      const n = Number(u.searchParams.get(key));
      if (Number.isFinite(n) && n >= 1) page = n;
    }
    return { year: yearMatch ? Number(yearMatch[1]) : null, page, token: page != null ? String(page) : null, mode: 'query' };
  } catch (_) { return { year: null, page: null, token: null, mode: null }; }
}

function isOrderHistoryUrl(value) {
  try { return /(?:\/gp\/your-account\/order-history|\/gp\/css\/order-history|\/your-orders\/orders)/i.test(new URL(value).pathname); }
  catch (_) { return false; }
}

function normalizeUrl(value) {
  try {
    const u = new URL(value);
    const route = historyRouteFromUrl(u.toString());
    for (const key of ['ref_', 'ref', 'tag']) u.searchParams.delete(key);
    if (isOrderHistoryUrl(u.toString()) && route.mode && (route.page != null || route.token === 'next' || route.year != null)) {
      const yearPart = route.year != null ? `time/${route.year}/` : '';
      const pagePart = route.page != null ? route.page : (route.token || '');
      u.hash = `${yearPart}pagination/${pagePart}/`;
    } else {
      u.hash = '';
    }
    return u.toString();
  } catch (_) {
    return null;
  }
}

function historyYearFromUrl(value) {
  return historyRouteFromUrl(value).year;
}

function historyPageIndexFromUrl(value) {
  return historyRouteFromUrl(value).page;
}


async function seedKnownOrderDetails() {
  const data = await chrome.storage.local.get([LEDGER_KEY]);
  const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
  const detailLinks = ledger
    .filter(r => r?.recordType === 'order' && r?.orderId && !r?.detailScanComplete)
    .map(r => ({ orderId: r.orderId, url: r.orderDetailsUrl || null }))
    .filter(r => r.url);
  const returnLinks = ledger
    .filter(r => r?.recordType === 'return' && r?.orderId && r?.returnStatusUrl)
    .map(r => ({ orderId: r.orderId, url: r.returnStatusUrl, returnToken: r.returnToken || null }))
    .filter(r => r.url);
  if (!detailLinks.length && !returnLinks.length) return { added: 0, queued: 0 };
  return enqueueJobs({ detailLinks, returnLinks, source: 'known-orders-seed' });
}

async function shouldSkipDetail(job, state) {
  if (!job.orderId) return false;
  const data = await chrome.storage.local.get([LEDGER_KEY]);
  const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
  const order = ledger.find(r => r.recordId === `order:${job.orderId}`) || null;
  if (!order?.detailScanComplete || !order?.detailScannedAt) return false;
  const age = Date.now() - new Date(order.detailScannedAt).getTime();
  if (!Number.isFinite(age)) return false;
  const hasReturn = ledger.some(r => r.orderId === job.orderId && r.recordType === 'return');
  const ttl = hasReturn ? RETURN_DETAIL_REFRESH_MS : DETAIL_REFRESH_MS;
  return age < ttl;
}

async function shouldSkipReturn(job, state) {
  const key = jobKey(job);
  const recentAt = state.recent[key] ? new Date(state.recent[key]).getTime() : 0;
  return Boolean(recentAt && Date.now() - recentAt < RETURN_STATUS_REFRESH_MS);
}

function sortQueue(queue) {
  return queue.sort((a, b) => {
    const pa = Number.isFinite(a?.priority) ? a.priority : 50;
    const pb = Number.isFinite(b?.priority) ? b.priority : 50;
    if (pa !== pb) return pa - pb;
    return String(a?.queuedAt || '').localeCompare(String(b?.queuedAt || ''));
  });
}

async function enqueueJobs({ detailLinks = [], returnLinks = [], historyPageLinks = [], source = 'page' } = {}) {
  const settings = await getSettings();
  const state = ensureCrawl(await getState());
  const existing = new Set(state.queue.map(jobKey));
  if (state.currentJob) existing.add(jobKey(state.currentJob));
  let added = 0;

  // v0.12 deliberately does not background-crawl /spr/returns/* pages. Order Details is the
  // canonical per-order source. Return-status links are still saved by the parser as evidence,
  // but the worker remains on /your-orders/order-details for order processing.

  // Generic discovery outside a managed lifetime crawl may queue detail pages, but it must not
  // create a competing history traversal while the page-by-page state machine is active.
  if (settings.autoHistoryCrawl !== false && !state.crawl.active) {
    for (const rawUrl of historyPageLinks || []) {
      const url = normalizeUrl(rawUrl);
      if (!url || !/^https:\/\/[^/]*amazon\.com\//i.test(url)) continue;
      const historyYear = historyYearFromUrl(url);
      const historyPage = historyPageIndexFromUrl(url);
      // Only queue concrete page-1/year links from passive discovery. Full pagination is handled
      // by ARL_START_FULL_SCAN so duplicate/overlapping pages cannot race one another.
      if (!historyYear || (historyPage && historyPage > 1)) continue;
      const job = { type: 'history', url, source, historyYear, historyPage: historyPage || 1, priority: 40, queuedAt: nowIso(), crawlManaged: false };
      const key = jobKey(job);
      if (existing.has(key)) continue;
      const recentAt = state.recent[key] ? new Date(state.recent[key]).getTime() : 0;
      if (recentAt && Date.now() - recentAt < HISTORY_REFRESH_MS) continue;
      state.queue.push(job); existing.add(key); added += 1;
    }
  }

  if (settings.autoDetailScan !== false && !state.crawl.active) {
    for (const link of detailLinks || []) {
      const url = normalizeUrl(link?.url);
      const orderId = String(link?.orderId || '').trim();
      if (!url || !/^https:\/\/[^/]*amazon\.com\//i.test(url) || !orderId) continue;
      const job = { type: 'detail', url, orderId, source, priority: 30, queuedAt: nowIso(), crawlManaged: false };
      const key = jobKey(job);
      if (existing.has(key)) continue;
      if (await shouldSkipDetail(job, state)) continue;
      state.queue.push(job); existing.add(key); added += 1;
    }
  }

  if (added) {
    sortQueue(state.queue);
    if (!state.startedAt) state.startedAt = nowIso();
    state.running = !state.paused;
    await setState(state);
    scheduleSoon(300);
  }
  return { added, queued: state.queue.length };
}

function buildHistoryUrl(baseUrl, year, page = 1) {
  const y = Number(year);
  const p = Math.max(1, Number(page) || 1);
  try {
    const u = new URL(baseUrl || 'https://www.amazon.com/gp/your-account/order-history');
    // Amazon Business on this account uses an in-page router. Teach Mode recorded the real
    // navigation sequence as #time/YYYY/pagination/1/ -> /2/ -> /3/. Preserve that exact state.
    // Do NOT synthesize startIndex here: on this Business UI that can reload page 1 for every page.
    u.searchParams.delete('timeFilter');
    u.searchParams.delete('orderFilter');
    u.searchParams.delete('startIndex');
    for (const key of ['page','pageNumber','pageNo','pageNum']) u.searchParams.delete(key);
    u.hash = `time/${y}/pagination/${p}/`;
    return u.toString();
  } catch (_) {
    return `https://www.amazon.com/gp/your-account/order-history#time/${y}/pagination/${p}/`;
  }
}

function buildLegacyServerHistoryUrl(baseUrl, year, page = 1) {
  const y = Number(year);
  const p = Math.max(1, Number(page) || 1);
  try {
    const u = new URL(baseUrl || 'https://www.amazon.com/gp/your-account/order-history');
    u.hash = '';
    u.searchParams.set('timeFilter', `year-${y}`);
    const startIndex = (p - 1) * 10;
    if (startIndex > 0) u.searchParams.set('startIndex', String(startIndex));
    else u.searchParams.delete('startIndex');
    return u.toString();
  } catch (_) {
    const startIndex = (p - 1) * 10;
    return `https://www.amazon.com/gp/your-account/order-history?timeFilter=year-${y}${startIndex ? `&startIndex=${startIndex}` : ''}`;
  }
}

function uniqueDetailLinks(result) {
  const byId = new Map();
  for (const link of result?.detailLinks || []) {
    const orderId = String(link?.orderId || '').trim();
    const url = normalizeUrl(link?.url) || link?.url || null;
    if (!/^\d{3}-\d{7}-\d{7}$/.test(orderId) || !url || byId.has(orderId)) continue;
    if (!/(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details)/i.test(url)) continue;
    byId.set(orderId, { orderId, url });
  }
  return Array.from(byId.values());
}

function terminalCancelledHistoryOrders(result) {
  const out = new Map();
  const pageUrl = String(result?.scannedUrl || '');
  if (!isOrderHistoryUrl(pageUrl)) return out;
  for (const record of result?.records || []) {
    const orderId = String(record?.orderId || '').trim();
    const sourceUrl = String(record?.sourceUrl || pageUrl);
    const exactCancelled = /^(?:cancelled|canceled)$/i.test(String(record?.statusText || '').trim());
    const zeroTotal = record?.purchaseAmount !== null && record?.purchaseAmount !== undefined && record?.purchaseAmount !== '' && Number(record.purchaseAmount) === 0;
    if (!/^\d{3}-\d{7}-\d{7}$/.test(orderId)) continue;
    if (!isOrderHistoryUrl(sourceUrl)) continue;
    if (record?.recordType !== 'order' || record?.historyTerminalComplete !== true || record?.historyTerminalState !== 'cancelled') continue;
    if (!exactCancelled || !zeroTotal || record?.orderDetailsUrl) continue;
    out.set(orderId, record);
  }
  return out;
}

async function queueManagedHistoryResult(result, job) {
  const state = ensureCrawl(await getState());
  const crawl = state.crawl;
  const route = historyRouteFromUrl(result?.scannedUrl || job?.url || '');
  const year = Number(result?.historySelectedYear || result?.historyDisplayedYear || job?.historyYear || route.year || crawl.currentYear);
  const page = Number(route.page || job?.historyPage || crawl.currentPage || 1);
  if (!Number.isFinite(year)) throw new Error('Could not determine Amazon history year for managed crawl');

  const discoveredYears = Array.from(new Set([...(crawl.years || []), ...(result?.historyYears || []), year]
    .map(Number).filter(Number.isFinite))).sort((a,b) => b-a);
  crawl.years = discoveredYears;
  crawl.currentYear = year;
  crawl.currentPage = page;
  crawl.currentHistoryUrl = result?.scannedUrl || job?.url || buildHistoryUrl('https://www.amazon.com/gp/your-account/order-history', year, page);
  crawl.phase = 'details';

  const links = uniqueDetailLinks(result);
  const terminalByOrder = terminalCancelledHistoryOrders(result);
  const pageOrderIds = historyOrderIdSet(result);
  if (!pageOrderIds.length) throw new Error(`No visible Amazon Order IDs were found on ${year} page ${page}`);
  const linkByOrder = new Map(links.map(link => [link.orderId, link]));
  const missingDetailUrls = pageOrderIds.filter(orderId => !linkByOrder.has(orderId) && !terminalByOrder.has(orderId));
  if (missingDetailUrls.length) throw new Error(`Missing real View order details URL for ${missingDetailUrls.length} order(s) on ${year} page ${page}: ${missingDetailUrls.join(', ')}. The crawler stopped rather than inventing canonical URLs.`);
  const orderedLinks = pageOrderIds.map(orderId => linkByOrder.get(orderId)).filter(Boolean);
  crawl.currentPageOrderIds = pageOrderIds;
  crawl.currentPageCompleted = 0;
  const pageKey = `${year}:${page}`;
  const fingerprint = pageOrderIds.join('|');
  const previousFingerprint = crawl.seenPages[pageKey];
  if (previousFingerprint !== fingerprint) {
    for (const orderId of pageOrderIds) {
      const first = crawl.seenOrders[orderId];
      if (first && first.pageKey !== pageKey) {
        crawl.overlapCount = (crawl.overlapCount || 0) + 1;
        if (crawl.overlapExamples.length < 50) crawl.overlapExamples.push({ orderId, first: first.pageKey, again: pageKey });
      } else if (!first) {
        crawl.seenOrders[orderId] = { year, page, pageKey };
      }
    }
    crawl.seenPages[pageKey] = fingerprint;
  }

  for (const orderId of pageOrderIds) {
    if (!terminalByOrder.has(orderId) || crawl.completedOrders[orderId]) continue;
    crawl.completedOrders[orderId] = { at: nowIso(), year, page, terminalState: 'cancelled', source: 'order-history-card' };
    crawl.ordersCompleted = (crawl.ordersCompleted || 0) + 1;
    crawl.lastCompletedOrderId = orderId;
    crawl.lastCompletedAt = nowIso();
  }
  crawl.currentPageCompleted = pageOrderIds.filter(orderId => crawl.completedOrders[orderId]).length;

  const existingKeys = new Set(state.queue.map(jobKey));
  if (state.currentJob) existingKeys.add(jobKey(state.currentJob));
  let seq = 0;
  for (const link of orderedLinks) {
    seq += 1;
    // A duplicate order ID on a later history page is not detail-scanned again during the same
    // lifetime run. It is counted as overlap and the first capture remains authoritative.
    if (crawl.completedOrders[link.orderId]) continue;
    const detailJob = {
      type: 'detail', orderId: link.orderId, url: normalizeUrl(link.url) || link.url,
      source: `crawl ${pageKey}`, crawlManaged: true, crawlYear: year, crawlPage: page,
      crawlPageKey: pageKey, historyUrl: crawl.currentHistoryUrl, sequence: seq,
      priority: 5, queuedAt: nowIso(), attempts: 0
    };
    const key = jobKey(detailJob);
    if (!existingKeys.has(key)) { state.queue.push(detailJob); existingKeys.add(key); }
  }

  const advanceJob = {
    type: 'advance', url: crawl.currentHistoryUrl, source: `crawl ${pageKey}`, crawlManaged: true,
    crawlYear: year, crawlPage: page, crawlPageKey: pageKey, pageOrderIds,
    historyUrl: crawl.currentHistoryUrl, priority: 20, queuedAt: nowIso(), attempts: 0
  };
  const advanceKey = `advance:${pageKey}`;
  advanceJob.customKey = advanceKey;
  if (!state.queue.some(j => j.type === 'advance' && j.crawlPageKey === pageKey) && !(state.currentJob?.type === 'advance' && state.currentJob?.crawlPageKey === pageKey)) {
    state.queue.push(advanceJob);
  }
  sortQueue(state.queue);
  state.running = !state.paused;
  await setState(state);
  return { year, page, pageOrderIds };
}

async function startOrResumeFullScan({ restart = false, startYear = null } = {}) {
  const state = ensureCrawl(await getState());
  if (!restart && state.crawl.active && (state.queue.length || state.currentJob)) {
    state.paused = false;
    state.running = true;
    await setState(state);
    scheduleSoon(randomBetween(500, 1200));
    return state;
  }

  const year = Number(startYear) || new Date().getFullYear();
  state.queue = [];
  state.currentJob = null;
  state.paused = false;
  state.running = true;
  state.lastError = null;
  state.lastHistoryAdvanceError = null;
  state.crawl = {
    ...defaultState().crawl,
    active: true,
    phase: 'history',
    years: [year],
    currentYear: year,
    currentPage: 1,
    currentHistoryUrl: buildHistoryUrl('https://www.amazon.com/gp/your-account/order-history', year, 1),
    startedAt: nowIso()
  };
  state.queue.push({
    type: 'history', url: state.crawl.currentHistoryUrl, historyYear: year, historyPage: 1,
    crawlManaged: true, source: 'full-lifetime-scan', priority: 1, queuedAt: nowIso(), attempts: 0
  });
  await setState(state);
  scheduleSoon(randomBetween(300, 900));
  return state;
}

async function queueNextYear(currentYear) {
  const state = ensureCrawl(await getState());
  const crawl = state.crawl;
  if (!crawl.completedYears.includes(Number(currentYear))) crawl.completedYears.push(Number(currentYear));
  crawl.completedYears = Array.from(new Set(crawl.completedYears)).sort((a,b)=>b-a);
  const nextYear = (crawl.years || []).filter(y => y < Number(currentYear) && !crawl.completedYears.includes(y)).sort((a,b)=>b-a)[0];
  if (!nextYear) {
    crawl.active = false;
    crawl.phase = 'done';
    crawl.completedAt = nowIso();
    state.running = false;
    await setState(state);
    return null;
  }
  crawl.currentYear = nextYear;
  crawl.currentPage = 1;
  crawl.currentPageOrderIds = [];
  crawl.currentPageCompleted = 0;
  crawl.currentHistoryUrl = buildHistoryUrl(crawl.currentHistoryUrl || 'https://www.amazon.com/gp/your-account/order-history', nextYear, 1);
  crawl.phase = 'history';
  state.queue.push({
    type: 'history', url: crawl.currentHistoryUrl, historyYear: nextYear, historyPage: 1,
    crawlManaged: true, source: 'next-year', priority: 1, queuedAt: nowIso(), attempts: 0
  });
  sortQueue(state.queue);
  await setState(state);
  return nextYear;
}

function scheduleSoon(delayMs = 500) {
  try {
    chrome.alarms.create(ALARM_NAME, { when: Date.now() + Math.max(100, delayMs) });
  } catch (_) {}
  setTimeout(() => processNextJob().catch(() => {}), Math.max(100, delayMs));
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function importantNavigationParams(value) {
  try {
    const u = new URL(value);
    const out = {};
    for (const key of ['orderID','orderId','orderFilter','timeFilter','startIndex','page','pageNumber','pageNo','pageNum']) {
      if (u.searchParams.has(key)) out[key] = u.searchParams.get(key);
    }
    const historyRoute = isOrderHistoryUrl(u.toString()) ? historyRouteFromUrl(u.toString()) : null;
    return { host: u.host.toLowerCase(), path: u.pathname.replace(/\/+$/, '') || '/', params: out, historyRoute };
  } catch (_) { return null; }
}

function urlMatchesNavigationTarget(actualUrl, expectedUrl) {
  const actual = importantNavigationParams(actualUrl);
  const expected = importantNavigationParams(expectedUrl);
  if (!actual || !expected) return false;
  if (!/(^|\.)amazon\.com$/i.test(actual.host) || !/(^|\.)amazon\.com$/i.test(expected.host)) return false;

  // The taught Amazon Business history pager is a SPA fragment state machine. A page is not the
  // requested page until both the year and concrete pagination index match.
  if (expected.historyRoute && (expected.historyRoute.year != null || expected.historyRoute.page != null || expected.historyRoute.token)) {
    const ar = actual.historyRoute || {};
    const er = expected.historyRoute;
    if (er.year != null && ar.year !== er.year) return false;
    if (er.page != null && ar.page !== er.page) return false;
    if (er.token === 'next' && ar.token !== 'next' && ar.page == null) return false;
    if (er.page != null || er.year != null) return true;
  }

  const expectedParams = expected.params || {};
  const actualParams = actual.params || {};
  for (const [key, value] of Object.entries(expectedParams)) {
    if (value == null) continue;
    if (actualParams[key] === value) continue;
    if ((key === 'orderFilter' || key === 'timeFilter') &&
        (actualParams.orderFilter === value || actualParams.timeFilter === value)) continue;
    return false;
  }
  const hasStrongParam = Object.keys(expectedParams).some(k => ['orderID','orderId','orderFilter','timeFilter','startIndex','page','pageNumber','pageNo','pageNum'].includes(k));
  if (hasStrongParam) return true;
  return actual.path === expected.path;
}

async function ensureWorkerTab(url) {
  if (workerTabId == null) {
    try {
      const data = await chrome.storage.local.get([WORKER_TAB_KEY]);
      if (Number.isInteger(data[WORKER_TAB_KEY])) workerTabId = data[WORKER_TAB_KEY];
    } catch (_) {}
  }
  if (workerTabId != null) {
    try {
      await chrome.tabs.get(workerTabId);
      await chrome.tabs.update(workerTabId, { url, active: false });
      return workerTabId;
    } catch (_) {
      workerTabId = null;
      await chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
    }
  }
  const tab = await chrome.tabs.create({ url, active: false });
  workerTabId = tab.id;
  await chrome.storage.local.set({ [WORKER_TAB_KEY]: workerTabId });
  return workerTabId;
}


async function ensureFetchHostTab(preferredUrl = 'https://www.amazon.com/gp/your-account/order-history') {
  if (workerTabId == null) {
    try {
      const data = await chrome.storage.local.get([WORKER_TAB_KEY]);
      if (Number.isInteger(data[WORKER_TAB_KEY])) workerTabId = data[WORKER_TAB_KEY];
    } catch (_) {}
  }
  if (workerTabId != null) {
    try {
      const tab = await chrome.tabs.get(workerTabId);
      if (/^https:\/\/[^/]*amazon\.com\//i.test(tab?.url || '')) {
        if (tab.status !== 'complete') await waitForTabComplete(workerTabId, null);
        return workerTabId;
      }
    } catch (_) {
      workerTabId = null;
      await chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
    }
  }
  const tab = await chrome.tabs.create({ url: preferredUrl, active: false });
  workerTabId = tab.id;
  await chrome.storage.local.set({ [WORKER_TAB_KEY]: workerTabId });
  await waitForTabComplete(workerTabId, preferredUrl);
  return workerTabId;
}

function waitForTabComplete(tabId, expectedUrl) {
  return new Promise((resolve, reject) => {
    let done = false;
    let pollTimer = null;
    const deadline = Date.now() + LOAD_TIMEOUT_MS;

    function cleanup() {
      chrome.tabs.onUpdated.removeListener(onUpdated);
      if (pollTimer) clearTimeout(pollTimer);
    }

    function finish(error, tab) {
      if (done) return;
      done = true;
      cleanup();
      if (error) reject(error);
      else resolve(tab);
    }

    async function inspect() {
      if (done) return;
      if (Date.now() >= deadline) {
        finish(new Error(`Amazon page load timed out before reaching ${expectedUrl || 'the requested page'}`));
        return;
      }
      try {
        const tab = await chrome.tabs.get(tabId);
        if (tab?.url && !/^https:\/\/[^/]*amazon\.com\//i.test(tab.url)) {
          finish(new Error('Background tab left Amazon'));
          return;
        }
        // Critical v0.9 fix: do not accept the old page merely because Chrome still reports it as
        // complete immediately after tabs.update(). The loaded URL must match the requested filter,
        // offset/page, or Order ID before the scanner is allowed to read it.
        if (tab?.status === 'complete' && (!expectedUrl || urlMatchesNavigationTarget(tab.url, expectedUrl))) {
          finish(null, tab);
          return;
        }
      } catch (_) {}
      pollTimer = setTimeout(inspect, 155);
    }

    function onUpdated(updatedId, info, tab) {
      if (updatedId !== tabId || info.status !== 'complete') return;
      if (tab?.url && !/^https:\/\/[^/]*amazon\.com\//i.test(tab.url)) {
        finish(new Error('Background tab left Amazon'));
        return;
      }
      if (!expectedUrl || urlMatchesNavigationTarget(tab?.url || '', expectedUrl)) finish(null, tab);
    }

    chrome.tabs.onUpdated.addListener(onUpdated);
    inspect();
  });
}

async function navigateExistingWorkerTab(tabId, url) {
  await chrome.tabs.update(tabId, { url, active: false });
  return waitForTabComplete(tabId, url);
}

async function waitForWorkerReady(tabId, job) {
  await delay(randomBetween(READY_INITIAL_MIN_MS, READY_INITIAL_MAX_MS));
  const deadline = Date.now() + READY_TIMEOUT_MS;
  let lastState = null;
  while (Date.now() < deadline) {
    try {
      const state = await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_READY', job });
      lastState = state || null;
      if (state?.blocked) {
        const error = new Error(state.error || 'Amazon requested human verification in the background tab.');
        error.blocked = true;
        throw error;
      }
      if (state?.rateLimited) {
        const error = new Error(state.error || 'Amazon appears to be throttling requests.');
        error.rateLimited = true;
        throw error;
      }
      if (state?.ready) return { ready: true, timedOut: false, state };
    } catch (error) {
      if (error?.blocked || error?.rateLimited) throw error;
      // A content script may not be addressable on the first poll immediately after navigation.
      // Keep polling inside the bounded readiness window; the authoritative scan still has its
      // existing retry path below.
    }
    await delay(randomBetween(READY_POLL_MIN_MS, READY_POLL_MAX_MS));
  }
  // Readiness is only an optimization gate, never a completeness shortcut. If the lightweight
  // probe cannot prove readiness quickly, fall through to the normal authoritative scan, whose
  // existing parser/retry/completeness checks decide whether the job is valid.
  return { ready: false, timedOut: true, state: lastState };
}

async function scanWorkerTab(tabId, job) {
  const readiness = await waitForWorkerReady(tabId, job);
  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const result = await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_SCAN', job });
      if (result?.ok) return { ...result, workerReadiness: readiness };
      lastError = new Error(result?.error || 'Worker scan returned no data');
      if (result?.blocked) lastError.blocked = true;
      if (result?.rateLimited) lastError.rateLimited = true;
      if (result?.blocked || result?.rateLimited) throw lastError;
    } catch (error) {
      lastError = error;
      if (error?.blocked || error?.rateLimited) throw error;
    }
    const base = 1500 * Math.pow(2, attempt);
    await delay(randomBetween(base, base + 1800));
  }
  throw lastError || new Error('Could not read Amazon background tab');
}

async function getWorkerPageState(tabId) {
  try { return await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_PAGE_STATE' }); }
  catch (_) { return null; }
}

async function waitForHistorySelectedYear(tabId, year, timeoutMs = 7000, beforeFingerprint = null, requireContentChange = false) {
  const target = Number(year);
  if (!Number.isFinite(target)) return true;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const state = await getWorkerPageState(tabId);
    const routeYear = historyYearFromUrl(state?.url || '');
    const yearMatches = Number(state?.historySelectedYear) === target || Number(routeYear) === target;
    const contentMatches = !requireContentChange || !beforeFingerprint || (state?.fingerprint && state.fingerprint !== beforeFingerprint);
    if (yearMatches && contentMatches) return true;
    await delay(randomBetween(245, 490));
  }
  return false;
}

async function ensureHistoryYearSelection(tabId, year) {
  const target = Number(year);
  if (!Number.isFinite(target)) return true;
  const before = await getWorkerPageState(tabId);
  const beforeYear = Number(before?.historySelectedYear || historyYearFromUrl(before?.url || ''));
  if (beforeYear === target) return true;

  try {
    const result = await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_SELECT_YEAR', year: target });
    if (!result?.ok) return false;
  } catch (_) { return false; }

  // Switching years is not considered successful just because the <select> value changed. Amazon
  // Business must also replace the order-card fingerprint; otherwise we would relabel the same
  // page-1 orders as a different year and repeatedly scrape duplicates.
  return waitForHistorySelectedYear(tabId, target, 16000, before?.fingerprint || null, true);
}

async function clickNextHistoryPage(tabId, currentUrl) {
  let beforeState = null;
  try { beforeState = await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_PAGE_STATE' }); } catch (_) {}

  let clicked = null;
  try {
    // This is the true-click fallback. Do not let the content script silently substitute another
    // synthesized URL here; direct URL candidates are validated separately by the background worker.
    clicked = await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_CLICK_NEXT', allowInferredNavigation: false });
  } catch (_) {
    return null;
  }
  if (!clicked?.clicked) return null;
  if (clicked.navigateUrl) {
    try {
      await navigateExistingWorkerTab(tabId, clicked.navigateUrl);
      return { url: clicked.navigateUrl, inlineResult: null };
    } catch (_) { return null; }
  }

  const started = Date.now();
  let lastUrl = currentUrl;
  while (Date.now() - started < 20000) {
    await delay(randomBetween(385, 805));
    try {
      const tab = await chrome.tabs.get(tabId);
      if (!tab?.url || !/^https:\/\/[^/]*amazon\.com\//i.test(tab.url)) continue;
      lastUrl = tab.url;
      if (normalizeUrl(tab.url) !== normalizeUrl(currentUrl)) {
        if (tab.status !== 'complete') {
          try { await waitForTabComplete(tabId, tab.url); } catch (_) {}
        }
        return { url: tab.url, inlineResult: null };
      }
      // Some Amazon pagers replace the order cards with JavaScript while keeping the same URL.
      let pageState = null;
      try { pageState = await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_PAGE_STATE' }); } catch (_) {}
      if (beforeState?.fingerprint && pageState?.fingerprint && beforeState.fingerprint !== pageState.fingerprint) {
        await delay(randomBetween(490, 1050));
        const inlineResult = await scanWorkerTab(tabId, { type: 'history', url: tab.url, dynamicContinuation: true });
        return { url: null, inlineResult };
      }
    } catch (_) {}
  }
  return normalizeUrl(lastUrl) !== normalizeUrl(currentUrl) ? { url: lastUrl, inlineResult: null } : null;
}

function historyOrderIdSet(result) {
  const ids = Array.isArray(result?.historyOrderIds) && result.historyOrderIds.length
    ? result.historyOrderIds
    : (result?.detailLinks || []).map(x => x?.orderId).filter(Boolean);
  return Array.from(new Set(ids || [])).sort();
}

function historyPageChanged(before, after) {
  const a = historyOrderIdSet(before);
  const b = historyOrderIdSet(after);
  if (!a.length || !b.length) return false;
  return a.join('|') !== b.join('|');
}

async function waitForHistoryOrderIdsChange(tabId, previousResult, expectedUrl, timeoutMs = 24000) {
  const before = historyOrderIdSet(previousResult);
  const beforeKey = before.join('|');
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await delay(randomBetween(315, 630));
    try {
      const tab = await chrome.tabs.get(tabId);
      if (expectedUrl && !urlMatchesNavigationTarget(tab?.url || '', expectedUrl)) continue;
      const state = await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_PAGE_STATE' });
      const ids = Array.from(new Set(state?.orderIds || [])).sort();
      if (ids.length && (!before.length || ids.join('|') !== beforeKey)) return state;
    } catch (_) {}
  }
  throw new Error('Amazon changed the history route but the next page of Order IDs did not finish loading');
}

async function scanHistoryContinuation(tabId, candidateUrl, previousResult, job) {
  await navigateExistingWorkerTab(tabId, candidateUrl);
  // Hash navigation reaches the new URL before Amazon Business finishes replacing the order cards.
  // Wait for a different set of Order IDs before parsing/saving the page.
  await waitForHistoryOrderIdsChange(tabId, previousResult, candidateUrl);
  const nextResult = await scanWorkerTab(tabId, {
    type: 'history',
    url: candidateUrl,
    dynamicContinuation: true,
    historyYear: historyYearFromUrl(candidateUrl) || job.historyYear || null,
    historyPage: historyPageIndexFromUrl(candidateUrl)
  });
  if (!historyPageChanged(previousResult, nextResult)) {
    throw new Error('Amazon loaded the same order list instead of the requested next page');
  }
  return nextResult;
}

async function advanceHistoryPage(tabId, result, job) {
  const currentUrl = result.scannedUrl || job.url;
  const currentRoute = historyRouteFromUrl(currentUrl);
  const year = Number(job.historyYear || result.historySelectedYear || result.historyDisplayedYear || currentRoute.year);
  const page = Number(job.historyPage || currentRoute.page || 1);

  // PRIMARY: activate Amazon's real pager. The user's recorded Business workflow changes the SPA
  // route from #time/YYYY/pagination/N/ to N+1 and replaces the visible Order IDs. We accept the
  // advance only after the Order ID fingerprint changes, so a page-1 reload can never count.
  const clicked = await clickNextHistoryPage(tabId, currentUrl);
  if (clicked?.inlineResult && historyPageChanged(result, clicked.inlineResult)) {
    return { nextResult: clicked.inlineResult, url: clicked.inlineResult.scannedUrl || null, method: 'amazon-pager-click-dynamic' };
  }
  if (clicked?.url) {
    try {
      await waitForHistoryOrderIdsChange(tabId, result, clicked.url);
      const nextResult = await scanWorkerTab(tabId, {
        type: 'history', url: clicked.url, dynamicContinuation: true,
        historyYear: historyYearFromUrl(clicked.url) || year || null,
        historyPage: historyPageIndexFromUrl(clicked.url) || (page + 1)
      });
      if (historyPageChanged(result, nextResult)) {
        return { nextResult, url: clicked.url, method: 'amazon-pager-click' };
      }
    } catch (_) {}
  }

  // SECONDARY: navigate to the concrete numbered hash route. Prefer the exact URL Amazon exposed
  // in its pagination anchors, then the taught #time/YYYY/pagination/N+1/ route. This is still the
  // Business UI's native routing contract—not a guessed startIndex offset.
  const hashCandidates = Array.from(new Set([
    result.nextPageUrl,
    ...(Array.isArray(result.nextPageCandidates) ? result.nextPageCandidates : []),
    Number.isFinite(year) && Number.isFinite(page) ? buildHistoryUrl(currentUrl, year, page + 1) : null
  ].filter(candidate => candidate && String(candidate).includes('#'))));
  for (const candidate of hashCandidates.slice(0, 6)) {
    try {
      await navigateExistingWorkerTab(tabId, currentUrl).catch(() => {});
      const nextResult = await scanHistoryContinuation(tabId, candidate, result, {
        ...job,
        historyYear: year,
        historyPage: page + 1
      });
      if (historyPageChanged(result, nextResult)) {
        return { nextResult, url: candidate, method: 'amazon-hash-route' };
      }
    } catch (_) {}
  }

  // Compatibility only for non-Business/legacy Amazon pages whose pager itself exposes query
  // pagination. We intentionally do not use this on a hash-routed Business page because testing
  // showed startIndex can return page 1 repeatedly there.
  const legacyQueryPager = currentRoute.mode === 'query' && Array.from(new Set([
    result.nextPageUrl,
    ...(Array.isArray(result.nextPageCandidates) ? result.nextPageCandidates : [])
  ].filter(Boolean))).some(candidate => /(?:[?&](?:startIndex|page(?:Number|No|Num)?)=)/i.test(String(candidate)));
  if (legacyQueryPager && Number.isFinite(year) && Number.isFinite(page)) {
    const legacyUrl = buildLegacyServerHistoryUrl(currentUrl, year, page + 1);
    try {
      const nextResult = await scanHistoryContinuation(tabId, legacyUrl, result, {
        ...job,
        historyYear: year,
        historyPage: page + 1
      });
      if (historyPageChanged(result, nextResult)) {
        return { nextResult, url: legacyUrl, method: 'legacy-query-pagination' };
      }
    } catch (_) {}
  }

  return null;
}

async function patchOrderProcessing(orderId, patch) {
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

async function resetOrderForAuthoritativeRefresh(orderId) {
  const id = String(orderId || '').trim();
  if (!/^\d{3}-\d{7}-\d{7}$/.test(id)) throw new Error('Invalid Amazon order ID.');
  const data = await chrome.storage.local.get([LEDGER_KEY]);
  const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
  const order = ledger.find(r => r?.recordType === 'order' && r?.orderId === id) || null;
  const detailUrl = order?.orderDetailsUrl || null;
  if (!detailUrl || !/(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details)/i.test(detailUrl)) {
    throw new Error('This order has no real captured View order details URL. Reset & Refresh cannot invent one.');
  }

  const now = nowIso();
  const shell = {
    recordId: `order:${id}`,
    recordType: 'order',
    orderId: id,
    orderDetailsUrl: detailUrl,
    detailScanComplete: false,
    orderDataComplete: false,
    returnStatusExpectedCount: 0,
    returnStatusAuthoritativeCount: 0,
    returnStatusComplete: false,
    status: 'purchase',
    statusText: 'Reset for authoritative refresh',
    processingState: 'processing',
    processingError: null,
    processingErrorAt: null,
    processingLastIssue: null,
    firstSeenAt: order?.firstSeenAt || now,
    lastScannedAt: now
  };
  const freshLedger = ledger.filter(record => record?.orderId !== id);
  freshLedger.push(shell);
  await chrome.storage.local.set({ [LEDGER_KEY]: freshLedger });

  const state = ensureCrawl(await getState());
  const previousCrawlCompletion = state.crawl?.completedOrders?.[id] || null;
  if (state.crawl?.completedOrders?.[id]) {
    delete state.crawl.completedOrders[id];
    state.crawl.ordersCompleted = Math.max(0, Number(state.crawl.ordersCompleted || 0) - 1);
    if (state.crawl.currentPageOrderIds?.includes(id)) {
      state.crawl.currentPageCompleted = state.crawl.currentPageOrderIds.filter(orderId => state.crawl.completedOrders[orderId]).length;
    }
  }
  for (const key of Object.keys(state.recent || {})) {
    if (key.includes(id)) delete state.recent[key];
  }
  await setState(state);
  return { id, detailUrl, previousCrawlCompletion };
}

async function restoreCrawlCompletionAfterAuthoritativeRefresh(id, previousCrawlCompletion = null) {
  const state = ensureCrawl(await getState());
  if (!state.crawl?.active && !previousCrawlCompletion) return;
  if (!state.crawl.completedOrders[id]) {
    state.crawl.completedOrders[id] = {
      ...(previousCrawlCompletion || {}),
      at: nowIso(),
      refreshedManually: true
    };
    state.crawl.ordersCompleted = Number(state.crawl.ordersCompleted || 0) + 1;
  }
  if (state.crawl.currentPageOrderIds?.includes(id)) {
    state.crawl.currentPageCompleted = state.crawl.currentPageOrderIds.filter(orderId => state.crawl.completedOrders[orderId]).length;
  }
  await setState(state);
}

async function forceResetRefreshOrder(orderId) {
  const waitDeadline = Date.now() + 60000;
  while (processing && Date.now() < waitDeadline) await delay(randomBetween(75, 125));
  if (processing) throw new Error('The Amazon crawler is still busy. Try Reset & Refresh again after the current request finishes.');
  processing = true;
  let resetContext = null;
  try {
    resetContext = await resetOrderForAuthoritativeRefresh(orderId);
    const { id, detailUrl } = resetContext;
    const tab = await chrome.tabs.create({ url: detailUrl, active: false });
  const tabId = tab?.id;
  if (!Number.isInteger(tabId)) throw new Error('Could not create the inactive Amazon refresh tab.');
  try {
    await waitForTabComplete(tabId, detailUrl);
    const detailResult = await scanWorkerTab(tabId, { type: 'detail', manualRefresh: true, orderId: id, url: detailUrl });
    const complete = (detailResult.records || []).some(r => r?.recordType === 'order' && r?.orderId === id && r?.detailScanComplete);
    if (!complete) throw new Error('Rendered Order Details did not produce a complete canonical capture.');
    let returnsRefreshed = 0;
    const uniqueReturnLinks = new Map();
    for (const link of (detailResult.returnLinks || []).filter(link => link?.orderId === id && link?.url && /\/spr\/returns\/prep/i.test(link.url))) {
      const key = `${link.returnToken || link.url}:${link.returnItemId || ''}`;
      if (!uniqueReturnLinks.has(key)) uniqueReturnLinks.set(key, link);
    }
    for (const link of uniqueReturnLinks.values()) {
      await navigateExistingWorkerTab(tabId, link.url);
      const returnResult = await scanWorkerTab(tabId, {
        type: 'return', manualRefresh: true, orderId: id, url: link.url,
        returnToken: link.returnToken || null,
        returnItemId: link.returnItemId || null,
        returnContractId: link.returnContractId || null,
        returnRmaId: link.returnRmaId || null
      });
      const matched = (returnResult.records || []).some(r =>
        r?.recordType === 'return' && r?.orderId === id && r?.authoritativeReturnCapture &&
        (!link.returnToken || r.returnToken === link.returnToken) &&
        (!link.returnItemId || !r.returnItemId || r.returnItemId === link.returnItemId)
      );
      if (!matched) throw new Error('Amazon return-status page did not produce the expected authoritative return child.');
      returnsRefreshed += 1;
    }
    await patchOrderProcessing(id, { orderDataComplete: true, processingState: 'complete', processingError: null, processingErrorAt: null, processingLastIssue: null, returnStatusExpectedCount: uniqueReturnLinks.size, returnStatusAuthoritativeCount: returnsRefreshed, returnStatusComplete: returnsRefreshed === uniqueReturnLinks.size, orderDataCompletedAt: nowIso() });
    await restoreCrawlCompletionAfterAuthoritativeRefresh(id, resetContext?.previousCrawlCompletion || null);
    return { ok: true, orderId: id, detailScannedAt: nowIso(), returnsRefreshed, resetAndRefreshed: true };
    } catch (error) {
      const id = resetContext?.id || String(orderId || '').trim();
      if (/^\d{3}-\d{7}-\d{7}$/.test(id)) {
        await patchOrderProcessing(id, { processingState: 'error', orderDataComplete: false, processingError: `reset-refresh: ${error?.message || error}`.slice(0, 500), processingErrorAt: nowIso(), processingLastIssue: `reset-refresh: ${error?.message || error}`.slice(0, 500) });
      }
      throw error;
    } finally {
      try { await chrome.tabs.remove(tabId); } catch (_) {}
      processing = false;
      const state = ensureCrawl(await getState().catch(() => defaultState()));
      if (!state.paused && state.queue?.length) scheduleSoon(randomBetween(75, 250));
    }
  } catch (error) {
    processing = false;
    throw error;
  }
}

async function broadcastLedgerUpdate(save) {
  if (!save?.changed) return;
  const settings = await getSettings();
  if (settings.showUpdateToast === false) return;
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab?.id || !/^https:\/\/[^/]*amazon\.com\//i.test(tab.url || '')) return;
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'ARL_BACKGROUND_LEDGER_UPDATED', save });
  } catch (_) {}
}

async function pageDetailsComplete(pageOrderIds) {
  const ids = Array.from(new Set(pageOrderIds || []));
  if (!ids.length) return true;
  const [state, data] = await Promise.all([getState(), chrome.storage.local.get([LEDGER_KEY])]);
  const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
  const ready = new Set(ledger.filter(r => r?.recordType === 'order' && r?.orderDataComplete === true).map(r => r.orderId));
  return ids.every(id => state.crawl?.completedOrders?.[id] || ready.has(id));
}

async function runJob(job) {
  if (job.type === 'advance') {
    if (!(await pageDetailsComplete(job.pageOrderIds))) {
      const err = new Error(`Waiting for all ${job.pageOrderIds?.length || 0} order-detail pages on ${job.crawlPageKey}`);
      err.waitingForDetails = true;
      throw err;
    }

    const historyUrl = job.historyUrl || job.url;
    const tabId = await ensureWorkerTab(historyUrl);
    await waitForTabComplete(tabId, historyUrl);
    if (job.crawlYear) {
      const selected = await ensureHistoryYearSelection(tabId, job.crawlYear);
      if (!selected) throw new Error(`Amazon year picker did not switch to ${job.crawlYear}`);
    }
    let current = await scanWorkerTab(tabId, { type: 'history', url: historyUrl, crawlManaged: true, historyYear: job.crawlYear, historyPage: job.crawlPage });
    await broadcastLedgerUpdate(current.save);

    // Page is complete only after every order has either a Detail capture or proven terminal cancellation.
    const stateBeforeAdvance = ensureCrawl(await getState());
    stateBeforeAdvance.crawl.pagesCompleted = (stateBeforeAdvance.crawl.pagesCompleted || 0) + 1;
    stateBeforeAdvance.crawl.phase = 'advance';
    await setState(stateBeforeAdvance);

    if (!current.hasNextPageControl) {
      const nextYear = await queueNextYear(job.crawlYear);
      return { ...current, yearComplete: true, nextYear, historyAdvanceMethod: 'end-of-year' };
    }

    const advanced = await advanceHistoryPage(tabId, current, {
      ...job,
      type: 'history',
      historyYear: job.crawlYear,
      historyPage: job.crawlPage,
      url: historyUrl
    });
    if (!advanced?.nextResult) {
      throw new Error(`Amazon still shows Next on ${job.crawlYear} page ${job.crawlPage}, but the order list did not advance. Scan stopped instead of repeating the same orders.`);
    }

    const nextRoute = historyRouteFromUrl(advanced.nextResult.scannedUrl || advanced.url || '');
    const nextPage = Number(nextRoute.page || (Number(job.crawlPage || 1) + 1));
    await queueManagedHistoryResult(advanced.nextResult, {
      type: 'history',
      url: advanced.nextResult.scannedUrl || advanced.url || buildHistoryUrl(historyUrl, job.crawlYear, nextPage),
      historyYear: job.crawlYear,
      historyPage: nextPage,
      crawlManaged: true,
      source: 'verified-next-page'
    });
    await broadcastLedgerUpdate(advanced.nextResult.save);
    return { ...current, continuationResult: advanced.nextResult, extraHistoryPages: 1, historyAdvanceMethod: advanced.method || 'click' };
  }

  if (job.type === 'detail') {
    await patchOrderProcessing(job.orderId, { processingState: 'processing', processingError: null, processingErrorAt: null });
    // Keep the worker parked on Amazon and fetch the canonical Order Details HTML through the
    // authenticated content-script context. This avoids one full browser navigation per order.
    const state = ensureCrawl(await getState());
    if (!job.url) throw new Error('Canonical Order Details URL is missing; crawler will not synthesize one.');
    const hostUrl = job.historyUrl || state.crawl.currentHistoryUrl || 'https://www.amazon.com/gp/your-account/order-history';
    const tabId = await ensureFetchHostTab(hostUrl);
    await delay(randomBetween(FETCH_DISPATCH_MIN_MS, FETCH_DISPATCH_MAX_MS));
    let result;
    try {
      result = await chrome.tabs.sendMessage(tabId, {
        type: 'ARL_WORKER_FETCH_DETAIL',
        url: job.url,
        orderId: job.orderId
      });
    } catch (error) {
      throw new Error(`Could not fetch Amazon Order Details: ${error?.message || error}`);
    }
    if (!result?.ok) {
      const error = new Error(result?.error || 'Amazon Order Details fetch returned no data');
      if (result?.blocked) error.blocked = true;
      if (result?.rateLimited) error.rateLimited = true;
      throw error;
    }
    const matched = (result.records || []).some(record => record.orderId === job.orderId && record.recordType === 'order' && record.detailScanComplete);
    if (!matched) throw new Error('No matching completed Order Details record was found. The crawler will not advance past this order.');
    await broadcastLedgerUpdate(result.save);
    return result;
  }

  const tabId = await ensureWorkerTab(job.url);
  await waitForTabComplete(tabId, job.url);
  if (job.type === 'history' && job.historyYear) {
    const selected = await ensureHistoryYearSelection(tabId, job.historyYear);
    if (!selected) throw new Error(`Amazon year picker did not switch to ${job.historyYear}`);
  }
  const result = await scanWorkerTab(tabId, job);

  if (job.type === 'detail') {
    const matched = (result.records || []).some(record => record.orderId === job.orderId && record.recordType === 'order' && record.detailScanComplete);
    if (!matched) throw new Error('No matching completed Order Details record was found. The crawler will not advance past this order.');
    await broadcastLedgerUpdate(result.save);
    return result;
  }

  if (job.type === 'return') {
    // Kept for backwards-compatible manually queued jobs, but full-history scanning never creates
    // these jobs in v0.12.
    const matched = (result.records || []).some(record => record.orderId === job.orderId && record.recordType === 'return');
    if (!matched) throw new Error('No matching return status was found');
    await broadcastLedgerUpdate(result.save);
    return result;
  }

  if (job.type === 'history' && job.crawlManaged) {
    const pageOrderIds = historyOrderIdSet(result);
    if (!pageOrderIds.length) throw new Error(`No orders were found on ${job.historyYear || ''} page ${job.historyPage || ''}`.trim());
    await queueManagedHistoryResult(result, job);
    await broadcastLedgerUpdate(result.save);
    return result;
  }

  // Passive/manual history discovery remains lightweight. It can save the visible order cards and
  // queue their Order Details pages, but it does not run a competing lifetime traversal.
  if (job.type === 'history') {
    await enqueueJobs({ detailLinks: result.detailLinks || [], source: job.type });
    await broadcastLedgerUpdate(result.save);
    return result;
  }

  await broadcastLedgerUpdate(result.save);
  return result;
}

async function processNextJob() {
  if (processing) return;
  processing = true;
  try {
    const settings = await getSettings();
    const state = ensureCooldownPlan(await getState());
    const coolingMs = cooldownRemainingMs(state);
    if (coolingMs > 0 && !state.paused) {
      state.running = false;
      await setState(state);
      scheduleSoon(Math.min(coolingMs + randomBetween(250, 900), 2147480000));
      return;
    }
    if (state.cooldownUntil && coolingMs <= 0) state.cooldownUntil = null;
    if (state.paused || (settings.autoDetailScan === false && settings.autoReturnScan === false && settings.autoHistoryCrawl === false)) {
      state.running = false;
      state.currentJob = null;
      await setState(state);
      return;
    }

    if (!state.queue.length) {
      state.running = false;
      state.currentJob = null;
      state.startedAt = null;
      await setState(state);
      if (workerTabId != null) {
        try { await chrome.tabs.remove(workerTabId); } catch (_) {}
        workerTabId = null;
        await chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
      }
      return;
    }

    const job = state.queue.shift();
    state.currentJob = job;
    state.running = true;
    await setState(state);

    let success = false;
    let jobError = null;
    let blocked = false;
    let rateLimited = false;
    let waitingForDetails = false;
    let resultForCompletion = null;
    try {
      if (job.type === 'detail' && !job.crawlManaged && await shouldSkipDetail(job, state)) {
        success = true;
      } else {
        resultForCompletion = await runJob(job);
        success = true;
      }
    } catch (error) {
      blocked = Boolean(error?.blocked);
      rateLimited = Boolean(error?.rateLimited);
      waitingForDetails = Boolean(error?.waitingForDetails);
      jobError = `${job.type}${job.orderId ? ` ${job.orderId}` : ''}: ${error?.message || error}`.slice(0, 500);
    }

    // runJob may have discovered and enqueued additional pages. Reload state so we do not
    // overwrite those newly queued jobs with the stale pre-job snapshot.
    const completionState = ensureCooldownPlan(await getState());
    completionState.processed += 1;
    if (job.type === 'detail' && job.orderId) {
      const nextAttempt = Number(job.attempts || 0) + (waitingForDetails ? 0 : 1);
      if (success) {
        await patchOrderProcessing(job.orderId, { processingState: 'complete', processingError: null, processingErrorAt: null, processingLastIssue: null });
      } else if (jobError && (blocked || (!rateLimited && !waitingForDetails && nextAttempt >= 3))) {
        await patchOrderProcessing(job.orderId, { processingState: 'error', processingError: jobError, processingErrorAt: nowIso(), processingLastIssue: jobError });
      } else if (jobError) {
        await patchOrderProcessing(job.orderId, { processingState: 'retrying', processingError: null, processingErrorAt: null, processingLastIssue: jobError });
      }
    }
    if (jobError && !waitingForDetails) {
      completionState.errors += 1;
      completionState.lastError = jobError;
    }

    const managedRetry = job.crawlManaged && !blocked && !rateLimited && !success && (job.type === 'detail' || job.type === 'advance' || job.type === 'history');
    if (blocked) {
      completionState.paused = true;
      completionState.running = false;
      completionState.queue.unshift(job);
    } else if (rateLimited) {
      completionState.rateLimitedCount = (completionState.rateLimitedCount || 0) + 1;
      completionState.running = false;
      completionState.queue.unshift(job);
      completionState.cooldownUntil = new Date(Date.now() + randomBetween(RATE_LIMIT_COOLDOWN_MIN_MS, RATE_LIMIT_COOLDOWN_MAX_MS)).toISOString();
      completionState.jobsSinceCooldown = 0;
      completionState.cooldownAfter = randomBetween(BURST_MIN_JOBS, BURST_MAX_JOBS);
    } else if (managedRetry) {
      const retryJob = { ...job, attempts: Number(job.attempts || 0) + (waitingForDetails ? 0 : 1), queuedAt: nowIso() };
      if (waitingForDetails || retryJob.attempts < 3) {
        completionState.queue.unshift(retryJob);
        completionState.running = true;
      } else {
        // Do not skip an order/page just because Amazon failed three times. Preserve the exact
        // checkpoint and stop so Start/Resume can continue from the same job later.
        completionState.queue.unshift(retryJob);
        completionState.paused = true;
        completionState.running = false;
        completionState.crawl.phase = 'stopped_on_error';
      }
    } else {
      completionState.jobsSinceCooldown = (completionState.jobsSinceCooldown || 0) + 1;
      if (completionState.jobsSinceCooldown >= completionState.cooldownAfter) {
        completionState.cooldownUntil = new Date(Date.now() + randomBetween(COOLDOWN_MIN_MS, COOLDOWN_MAX_MS)).toISOString();
        completionState.jobsSinceCooldown = 0;
        completionState.cooldownAfter = randomBetween(BURST_MIN_JOBS, BURST_MAX_JOBS);
        completionState.running = false;
      }
    }

    if (success && job.type === 'detail') {
      completionState.detailProcessed += 1;
      if (job.crawlManaged) {
        const crawl = completionState.crawl;
        if (!crawl.completedOrders[job.orderId]) {
          crawl.completedOrders[job.orderId] = { at: nowIso(), year: job.crawlYear, page: job.crawlPage };
          crawl.ordersCompleted = (crawl.ordersCompleted || 0) + 1;
        }
        crawl.lastCompletedOrderId = job.orderId;
        crawl.lastCompletedAt = nowIso();
        if (crawl.currentPage === job.crawlPage && crawl.currentYear === job.crawlYear) {
          crawl.currentPageCompleted = (crawl.currentPageOrderIds || []).filter(id => crawl.completedOrders[id]).length;
        }
        crawl.phase = 'details';
      }
    }
    if (success && job.type === 'return') completionState.returnProcessed += 1;
    if (success && job.type === 'history') {
      completionState.historyProcessed += 1;
      completionState.lastHistoryUrl = resultForCompletion?.scannedUrl || job.url || null;
      const year = job.historyYear || historyYearFromUrl(job.url);
      if (year) {
        completionState.historyYearsProcessed = completionState.historyYearsProcessed || {};
        completionState.historyYearsProcessed[String(year)] = (completionState.historyYearsProcessed[String(year)] || 0) + 1;
      }
    }
    if (success && job.type === 'advance') {
      const extra = Number.isFinite(Number(resultForCompletion?.extraHistoryPages)) ? Number(resultForCompletion.extraHistoryPages) : 0;
      completionState.historyProcessed += extra;
      completionState.lastHistoryUrl = resultForCompletion?.continuationResult?.scannedUrl || job.historyUrl || job.url || null;
      completionState.lastHistoryAdvanceMethod = resultForCompletion?.historyAdvanceMethod || null;
      completionState.lastHistoryAdvanceError = null;
      if (extra && job.crawlYear) {
        completionState.historyYearsProcessed = completionState.historyYearsProcessed || {};
        completionState.historyYearsProcessed[String(job.crawlYear)] = (completionState.historyYearsProcessed[String(job.crawlYear)] || 0) + extra;
      }
    }
    if (success) completionState.recent[jobKey(job)] = nowIso();
    completionState.recent = compactRecent(completionState.recent);
    completionState.currentJob = null;
    await setState(completionState);

    if (!blocked && !completionState.paused) {
      const cooling = cooldownRemainingMs(completionState);
      scheduleSoon(cooling > 0 ? cooling + randomBetween(250, 900) : (waitingForDetails ? randomBetween(300, 600) : randomizedJobDelay()));
    }
  } finally {
    processing = false;
  }
}


chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes[SETTINGS_KEY]) {
    workflowRecorderEnabled = Boolean(changes[SETTINGS_KEY].newValue?.workflowRecorderEnabled);
  }
});

if (chrome.webRequest?.onBeforeRequest?.addListener) {
  chrome.webRequest.onBeforeRequest.addListener(details => {
    if (!workflowRecorderEnabled || details.tabId < 0) return;
    const sanitized = sanitizeWorkflowUrl(details.url);
    let host = '';
    try { host = new URL(details.url).hostname; } catch (_) {}
    if (!sanitized || !/(^|\.)amazon\.com$/i.test(host)) return;
    const formData = workflowFormData(details.requestBody);
    const navigation = details.type === 'main_frame' || details.type === 'sub_frame';
    const relevantUrl = /(order|your-orders|order-history|return|refund|pagination|page|ajax)/i.test(`${sanitized.pathname} ${JSON.stringify(sanitized.interestingParams)}`);
    if (!navigation && !relevantUrl && !formData) return;
    appendWorkflowEvent({
      type: 'network-request',
      tabId: details.tabId,
      requestType: details.type,
      method: details.method,
      url: sanitized,
      formData
    });
  }, { urls: ['https://*.amazon.com/*'] }, ['requestBody']);
}

refreshWorkflowRecorderFlag();

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message) return;

  if (message.type === 'ARL_LEDGER_CHANGED_FROM_PAGE') {
    if (message.save?.changed && sender?.tab?.active === false) {
      broadcastLedgerUpdate(message.save).catch(() => {});
    }
    sendResponse({ ok: true });
    return;
  }

  if (message.type === 'ARL_DISCOVERED') {
    // Page visits are still auto-parsed/saved by the content script, but background traversal is
    // controlled by Start/Stop so a passive page visit cannot create a second competing crawler.
    sendResponse({ ok: true, added: 0, queued: 0 });
    return;
  }

  if (message.type === 'ARL_START_FULL_SCAN') {
    startOrResumeFullScan({ restart: Boolean(message.restart), startYear: message.startYear || null })
      .then(state => sendResponse({ ok: true, state }))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }

  if (message.type === 'ARL_STOP_FULL_SCAN') {
    getState().then(async state => {
      state = ensureCrawl(state);
      state.paused = true;
      state.running = false;
      state.crawl.phase = state.crawl.active ? 'paused' : state.crawl.phase;
      await setState(state);
      sendResponse({ ok: true, state });
    }).catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }

  if (message.type === 'ARL_GET_BACKGROUND_STATUS') {
    getState().then(state => sendResponse({ ok: true, state })).catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }

  if (message.type === 'ARL_SET_BACKGROUND_PAUSED') {
    getState().then(async state => {
      state.paused = Boolean(message.paused);
      state.running = !state.paused && state.queue.length > 0;
      await setState(state);
      if (!state.paused) scheduleSoon(cooldownRemainingMs(state) || randomBetween(600, 1600));
      sendResponse({ ok: true, state });
    }).catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }

  if (message.type === 'ARL_RESET_REFRESH_ORDER') {
    forceResetRefreshOrder(message.orderId)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }

  if (message.type === 'ARL_RESCAN_ALL_DETAILS') {
    chrome.storage.local.get([LEDGER_KEY]).then(async data => {
      const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
      const detailLinks = ledger
        .filter(r => r.recordType === 'order' && r.orderId)
        .map(r => ({ orderId: r.orderId, url: r.orderDetailsUrl || null }))
        .filter(r => r.url);
      const state = await getState();
      for (const link of detailLinks) delete state.recent[`detail:${link.orderId}`];
      await setState(state);
      const result = await enqueueJobs({ detailLinks, source: 'manual-rescan' });
      sendResponse({ ok: true, ...result });
    }).catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
});

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === ALARM_NAME) processNextJob().catch(() => {});
});

chrome.tabs.onRemoved.addListener(tabId => {
  if (tabId === workerTabId) {
    workerTabId = null;
    chrome.storage.local.remove([WORKER_TAB_KEY]).catch(() => {});
  }
});

chrome.runtime.onStartup.addListener(() => {
  ensureDevelopmentVersionState().then(() => getState()).then(state => { if (state.crawl?.active && !state.paused && state.queue?.length) scheduleSoon(randomBetween(1200, 3000)); }).catch(() => {});
});
chrome.runtime.onInstalled.addListener(details => { ensureDevelopmentVersionState(details?.previousVersion || null).catch(() => {}); });
