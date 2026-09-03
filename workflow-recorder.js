(() => {
  'use strict';

  const SETTINGS_KEY = 'settings';
  const LOG_KEY = 'workflowLog';
  const MAX_EVENTS = 1600;
  const MAX_TEXT = 240;
  const parser = window.AmazonRefundParser;
  let enabled = false;
  let overlay = null;
  let eventCount = 0;
  let pageLoadLogged = false;
  let urlWatchTimer = null;
  let lastUrl = location.href;
  let postClickTimers = new Set();

  function iso() { return new Date().toISOString(); }
  function cleanText(value, max = MAX_TEXT) {
    return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
  }
  function amazonUrl(value) {
    try {
      const u = new URL(value, location.href);
      return /(^|\.)amazon\.com$/i.test(u.hostname) ? u.toString() : null;
    } catch (_) { return null; }
  }
  function cssToken(value) {
    return String(value || '').trim().replace(/[^a-zA-Z0-9_-]/g, '');
  }
  function classList(el) {
    return Array.from(el?.classList || []).map(cssToken).filter(Boolean).slice(0, 8);
  }
  function stableNode(el) {
    if (!el || el.nodeType !== 1) return null;
    const tag = String(el.tagName || '').toLowerCase();
    const href = el.matches?.('a[href]') ? amazonUrl(el.getAttribute('href') || el.href || '') : null;
    return {
      tag,
      id: cleanText(el.id, 100) || null,
      classes: classList(el),
      role: cleanText(el.getAttribute?.('role'), 60) || null,
      ariaLabel: cleanText(el.getAttribute?.('aria-label'), 180) || null,
      title: cleanText(el.getAttribute?.('title'), 180) || null,
      name: cleanText(el.getAttribute?.('name'), 100) || null,
      type: cleanText(el.getAttribute?.('type'), 60) || null,
      value: tag === 'select' ? cleanText(el.value, 120) : null,
      text: cleanText(el.innerText || el.textContent || el.value, MAX_TEXT) || null,
      href,
      dataAction: cleanText(el.getAttribute?.('data-action'), 120) || null,
      dataTestId: cleanText(el.getAttribute?.('data-testid'), 120) || null,
      dataValue: cleanText(el.getAttribute?.('data-value'), 120) || null,
      ariaCurrent: cleanText(el.getAttribute?.('aria-current'), 40) || null,
      ariaDisabled: cleanText(el.getAttribute?.('aria-disabled'), 40) || null,
      disabled: Boolean(el.disabled)
    };
  }
  function trail(el) {
    const out = [];
    let cur = el;
    for (let i = 0; cur && i < 6; i += 1, cur = cur.parentElement) {
      const node = stableNode(cur);
      if (node) out.push(node);
    }
    return out;
  }
  function likelyNavigationRoot(el) {
    return el?.closest?.('.a-pagination, nav, [role="navigation"], form, [class*="pagination" i], [class*="orders" i], [id*="orders" i], [class*="filter" i], [id*="filter" i], [class*="dropdown" i], [class*="select" i]') || null;
  }
  function controlSummary(root) {
    if (!root?.querySelectorAll) return [];
    const els = Array.from(root.querySelectorAll('a[href],button,select,input,[role="button"],[aria-current="page"]')).slice(0, 80);
    return els.map(stableNode).filter(Boolean);
  }
  function visibleOrderHeading() {
    const text = String(document.body?.innerText || '');
    const m = text.match(/Viewing\s+\d+\s+orders?\s+placed\s+in[\s\S]{0,180}?((?:20\d{2})|Last\s+30\s+days|Last\s+3\s+months|All\s+orders)/i);
    return m ? cleanText(m[0], 260) : null;
  }
  function selectSummary() {
    return Array.from(document.querySelectorAll('select')).slice(0, 20).map(sel => ({
      node: stableNode(sel),
      options: Array.from(sel.options || []).slice(0, 80).map(o => ({ text: cleanText(o.textContent, 100), value: cleanText(o.value, 140), selected: Boolean(o.selected) }))
    }));
  }
  function paginationSummary() {
    const roots = Array.from(document.querySelectorAll('.a-pagination, nav[aria-label*="page" i], [role="navigation"], [class*="pagination" i]')).slice(0, 8);
    return roots.map(root => ({ root: stableNode(root), controls: controlSummary(root) }));
  }
  function parsedSnapshot() {
    if (!parser?.parseDocument) return null;
    try {
      const result = parser.parseDocument(document, location.href);
      return {
        pageType: result.pageType,
        isOrderHistoryPage: Boolean(result.isOrderHistoryPage),
        isOrderDetailPage: Boolean(result.isOrderDetailPage),
        historyDisplayedYear: result.historyDisplayedYear || null,
        historyTotalOrders: result.historyTotalOrders ?? null,
        historyVisibleCount: result.historyVisibleCount ?? null,
        historyOrderIds: (result.historyOrderIds || []).slice(0, 80),
        nextPageUrl: result.nextPageUrl || null,
        nextPageCandidates: (result.nextPageCandidates || []).slice(0, 12),
        hasNextPageControl: Boolean(result.hasNextPageControl),
        historyPageLinks: (result.historyPageLinks || []).slice(0, 40),
        detailLinks: (result.detailLinks || []).slice(0, 40),
        returnLinks: (result.returnLinks || []).slice(0, 40)
      };
    } catch (error) {
      return { parserError: cleanText(error?.message || error, 300) };
    }
  }
  function pageSnapshot() {
    return {
      url: location.href,
      title: document.title,
      readyState: document.readyState,
      visibleOrderHeading: visibleOrderHeading(),
      parsed: parsedSnapshot(),
      selects: selectSummary(),
      pagination: paginationSummary()
    };
  }
  function shouldRecordClick(el) {
    if (!el?.closest) return false;
    const c = el.closest('a,button,input,select,option,[role="button"],li,label');
    if (!c) return false;
    const text = cleanText(c.innerText || c.textContent || c.value || c.getAttribute?.('aria-label') || c.getAttribute?.('title'), 220).toLowerCase();
    const href = cleanText(c.getAttribute?.('href'), 300).toLowerCase();
    if (c.closest('.a-pagination, [class*="pagination" i], nav, [role="navigation"]')) return true;
    if (/next|previous|orders?|view order details|return|refund|last 30|last 3|all orders|20\d{2}|paid by/.test(`${text} ${href}`)) return true;
    if (c.tagName === 'SELECT' || c.tagName === 'OPTION') return true;
    return false;
  }
  async function append(entry) {
    if (!enabled) return;
    try {
      const data = await chrome.storage.local.get([LOG_KEY]);
      const log = Array.isArray(data[LOG_KEY]) ? data[LOG_KEY] : [];
      log.push({ at: iso(), ...entry });
      if (log.length > MAX_EVENTS) log.splice(0, log.length - MAX_EVENTS);
      await chrome.storage.local.set({ [LOG_KEY]: log });
      eventCount = log.length;
      renderOverlay();
    } catch (_) {}
  }
  function renderOverlay() {
    if (!enabled) {
      overlay?.remove(); overlay = null; return;
    }
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'arl-teach-mode';
      overlay.style.cssText = 'position:fixed;z-index:2147483647;right:14px;bottom:14px;background:#111827;color:#fff;border:1px solid #374151;border-radius:9px;padding:9px 11px;font:12px/1.35 system-ui,sans-serif;box-shadow:0 5px 18px rgba(0,0,0,.28);max-width:280px;pointer-events:none';
      document.documentElement.appendChild(overlay);
    }
    overlay.textContent = `Amazon Refund Ledger · TEACH MODE · ${eventCount} events`;
  }
  async function enable() {
    if (enabled) return;
    enabled = true;
    const data = await chrome.storage.local.get([LOG_KEY]);
    eventCount = Array.isArray(data[LOG_KEY]) ? data[LOG_KEY].length : 0;
    renderOverlay();
    addListeners();
    await append({ type: 'page-load', snapshot: pageSnapshot() });
    pageLoadLogged = true;
    lastUrl = location.href;
    urlWatchTimer = setInterval(() => {
      if (!enabled) return;
      if (location.href !== lastUrl) {
        const before = lastUrl; lastUrl = location.href;
        append({ type: 'url-change', from: before, to: lastUrl, snapshot: pageSnapshot() });
      }
    }, 450);
  }
  function disable() {
    enabled = false;
    removeListeners();
    if (urlWatchTimer) clearInterval(urlWatchTimer);
    urlWatchTimer = null;
    for (const timer of postClickTimers) clearTimeout(timer);
    postClickTimers.clear();
    renderOverlay();
  }
  function onClick(event) {
    if (!enabled) return;
    const raw = event.target?.nodeType === 1 ? event.target : event.target?.parentElement;
    const target = raw?.closest?.('a,button,input,select,option,[role="button"],li,label') || raw;
    if (!shouldRecordClick(target)) return;
    const navRoot = likelyNavigationRoot(target);
    append({
      type: 'click',
      trusted: Boolean(event.isTrusted),
      target: stableNode(target),
      trail: trail(target),
      navigationContainer: navRoot ? { node: stableNode(navRoot), controls: controlSummary(navRoot) } : null,
      before: pageSnapshot()
    });
    const t = setTimeout(() => {
      postClickTimers.delete(t);
      if (enabled) append({ type: 'post-click-state', target: stableNode(target), snapshot: pageSnapshot() });
    }, 1200);
    postClickTimers.add(t);
  }
  function onChange(event) {
    if (!enabled) return;
    const target = event.target;
    if (!(target instanceof HTMLSelectElement) && !(target instanceof HTMLInputElement)) return;
    const navRoot = likelyNavigationRoot(target);
    append({
      type: 'change',
      trusted: Boolean(event.isTrusted),
      target: stableNode(target),
      selectedText: target instanceof HTMLSelectElement ? cleanText(target.selectedOptions?.[0]?.textContent, 160) : null,
      navigationContainer: navRoot ? { node: stableNode(navRoot), controls: controlSummary(navRoot) } : null,
      snapshot: pageSnapshot()
    });
  }
  function onPopState() { if (enabled) append({ type: 'popstate', snapshot: pageSnapshot() }); }
  function onPageShow(event) { if (enabled) append({ type: 'pageshow', persisted: Boolean(event?.persisted), snapshot: pageSnapshot() }); }
  function addListeners() {
    document.addEventListener('click', onClick, true);
    document.addEventListener('change', onChange, true);
    window.addEventListener('popstate', onPopState);
    window.addEventListener('pageshow', onPageShow);
  }
  function removeListeners() {
    document.removeEventListener('click', onClick, true);
    document.removeEventListener('change', onChange, true);
    window.removeEventListener('popstate', onPopState);
    window.removeEventListener('pageshow', onPageShow);
  }
  async function syncFromSettings() {
    try {
      const data = await chrome.storage.local.get([SETTINGS_KEY]);
      const should = Boolean(data?.[SETTINGS_KEY]?.workflowRecorderEnabled);
      if (should && !enabled) await enable();
      else if (!should && enabled) disable();
    } catch (_) {}
  }

  chrome.storage.onChanged.addListener(changes => {
    if (changes[SETTINGS_KEY]) syncFromSettings();
    if (changes[LOG_KEY] && enabled) {
      eventCount = Array.isArray(changes[LOG_KEY].newValue) ? changes[LOG_KEY].newValue.length : 0;
      renderOverlay();
    }
  });

  syncFromSettings();
})();
