(() => {
  'use strict';
  const storage = window.AmazonRefundStorage;
  const popupSummary = document.getElementById('popupSummary');
  const backgroundStatus = document.getElementById('backgroundStatus');
  const checkpointStatus = document.getElementById('checkpointStatus');
  const scanToggleButton = document.getElementById('scanToggleButton');
  const dashboardButton = document.getElementById('dashboardButton');
  const result = document.getElementById('result');
  const versionLabel = document.getElementById('versionLabel');
  const devUpdateStatus = document.getElementById('devUpdateStatus');
  const checkUpdateButton = document.getElementById('checkUpdateButton');
  let scannerState = null;
  versionLabel.textContent = `AMAZON REFUND LEDGER · v${chrome.runtime.getManifest()?.version || '—'}`;

  function money(value) { return Number.isFinite(Number(value)) ? `$${Number(value).toFixed(2)}` : '$0.00'; }
  function esc(value) { return String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function unique(values) { return Array.from(new Set((values || []).filter(Boolean))); }
  function summarizeOrders(ledger, settings) {
    const orders = new Map(); const returns = new Map();
    for (const r of ledger) {
      if (!r?.orderId) continue;
      if (r.recordType === 'order') {
        const prior = orders.get(r.orderId);
        if (!prior || (r.detailScanComplete && !prior.detailScanComplete) || String(r.lastScannedAt || '') > String(prior.lastScannedAt || '')) orders.set(r.orderId, r);
      } else if (r.recordType === 'return') {
        if (!returns.has(r.orderId)) returns.set(r.orderId, []); returns.get(r.orderId).push(r);
      }
    }
    function refundTotal(records) {
      const seen = new Map();
      for (const r of records || []) {
        const amount = Number(r.refundAmount ?? r.refundSubtotal);
        if (!Number.isFinite(amount)) continue;
        const items = [...(r.asins || []), ...(r.itemNames || [])].map(x => String(x || '').trim().toLowerCase()).filter(Boolean).join('|');
        const key = r.returnToken || `${amount.toFixed(2)}:${items}`;
        if (!seen.has(key)) seen.set(key, amount);
      }
      return Array.from(seen.values()).reduce((a,b) => a + b, 0);
    }
    const ids = new Set([...orders.keys(), ...returns.keys()]);
    let allTotal = 0, returnTotal = 0, reviewTotal = 0, returnCount = 0, reviewCount = 0;
    for (const id of ids) {
      const order = orders.get(id); const rs = returns.get(id) || [];
      const total = Number(order?.purchaseAmount); if (Number.isFinite(total)) allTotal += total;
      if (rs.length) {
        returnCount += 1;
        const canonicalRaw = order?.canonicalRefundTotal;
        const canonical = canonicalRaw == null ? NaN : Number(canonicalRaw);
        returnTotal += Number.isFinite(canonical) ? canonical : refundTotal(rs);
        const reconciled = rs.some(r => r.manualState === 'reconciled');
        const flagged = reconciled ? [] : rs.filter(r => storage.needsCreditReview(r));
        if (flagged.length) {
          reviewCount += 1;
          reviewTotal += refundTotal(flagged);
        }
      }
    }
    return { allCount: ids.size, allTotal, returnCount, returnTotal, reviewCount, reviewTotal, detailed: Array.from(orders.values()).filter(o => o.detailScanComplete).length };
  }
  function card(view, label, count, total) {
    return `<button class="summary-button" data-view="${view}"><span>${esc(label)}</span><strong>${count}</strong><small>${money(total)}</small></button>`;
  }
  async function renderLedger() {
    const [ledger, settings] = await Promise.all([storage.getLedger(), storage.getSettings()]);
    const s = summarizeOrders(ledger, settings);
    popupSummary.innerHTML = card('all','All orders',s.allCount,s.allTotal) + card('returns','Returns',s.returnCount,s.returnTotal) + card('needs_review','Needs review',s.reviewCount,s.reviewTotal);
  }
  async function renderDevUpdateStatus() {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'ARL_GET_DEV_UPDATE_STATUS' });
      const status = response?.status || null;
      const current = chrome.runtime.getManifest()?.version || '—';
      if (!status) {
        devUpdateStatus.textContent = `Development updater · current ${current} · no check recorded yet`;
        devUpdateStatus.className = 'result warn';
        return;
      }
      const latest = status.latestVersion || status.installedVersion || current;
      const checked = status.lastCheckedAt || status.lastCheckStartedAt || '';
      const suffix = status.error ? ` · ${status.error}` : status.checking ? ' · checking…' : status.hostAvailable === false ? ' · native host unavailable' : '';
      devUpdateStatus.textContent = `Development updater · current ${current} · latest ${latest}${checked ? ` · checked ${new Date(checked).toLocaleTimeString()}` : ''}${suffix}`;
      devUpdateStatus.className = `result ${status.error || status.hostAvailable === false ? 'warn' : 'ok'}`;
    } catch (error) {
      devUpdateStatus.textContent = `Development updater status unavailable · ${error?.message || error}`;
      devUpdateStatus.className = 'result warn';
    }
  }
  function formatRemaining(ms) { const sec=Math.ceil(ms/1000); return sec<60?`${sec}s`:`${Math.ceil(sec/60)}m`; }
  async function renderScanner() {
    const response = await chrome.runtime.sendMessage({ type: 'ARL_GET_BACKGROUND_STATUS' });
    scannerState = response?.state || null;
    if (!scannerState) return;
    const state = scannerState; const crawl = state.crawl || {};
    const cooling = state.cooldownUntil ? Math.max(0,new Date(state.cooldownUntil).getTime()-Date.now()) : 0;
    const mode = state.paused ? 'Stopped' : cooling>0 ? `Cooling down ${formatRemaining(cooling)}` : state.running ? 'Running' : crawl.phase==='done' ? 'Complete' : 'Idle';
    backgroundStatus.textContent = `${mode} · ${state.queue?.length || 0} queued · ${state.historyProcessed || 0} history pages · ${state.detailProcessed || 0} details`;
    backgroundStatus.className = `result ${state.lastError ? 'warn' : 'ok'}`;
    const pageOrders=(crawl.currentPageOrderIds||[]).length;
    checkpointStatus.textContent = crawl.currentYear
      ? `${crawl.currentYear} · page ${crawl.currentPage || 1} · ${crawl.currentPageCompleted || 0}/${pageOrders || '?'} order details · ${crawl.ordersCompleted || 0} unique completed · ${crawl.overlapCount || 0} overlaps${crawl.lastCompletedOrderId ? ` · last ${crawl.lastCompletedOrderId}` : ''}`
      : 'No lifetime scan checkpoint yet.';
    if (crawl.active && !state.paused) scanToggleButton.textContent = 'Stop lifetime scan';
    else if (crawl.active && state.paused) scanToggleButton.textContent = 'Resume lifetime scan';
    else scanToggleButton.textContent = 'Start lifetime scan';
  }
  async function openDashboard(view='all') {
    await chrome.tabs.create({ url: chrome.runtime.getURL(`dashboard.html?view=${encodeURIComponent(view)}`) }); window.close();
  }
  popupSummary.addEventListener('click', event => { const b=event.target.closest('[data-view]'); if (b) openDashboard(b.dataset.view); });
  dashboardButton.addEventListener('click', () => openDashboard('all'));
  checkUpdateButton.addEventListener('click', async () => {
    checkUpdateButton.disabled = true;
    checkUpdateButton.textContent = 'Checking…';
    try {
      const response = await chrome.runtime.sendMessage({ type: 'ARL_CHECK_DEV_UPDATE' });
      if (!response?.ok) throw new Error(response?.error || 'Update check failed');
      await renderDevUpdateStatus();
    } catch (error) {
      devUpdateStatus.textContent = `Development update failed · ${error?.message || error}`;
      devUpdateStatus.className = 'result warn';
    } finally {
      checkUpdateButton.disabled = false;
      checkUpdateButton.textContent = 'Check development update now';
    }
  });
  scanToggleButton.addEventListener('click', async () => {
    scanToggleButton.disabled = true;
    try {
      if (scannerState?.crawl?.active && !scannerState?.paused) await chrome.runtime.sendMessage({ type: 'ARL_STOP_FULL_SCAN' });
      else await chrome.runtime.sendMessage({ type: 'ARL_START_FULL_SCAN' });
      await renderScanner();
    } catch (error) {
      result.textContent = error?.message || String(error); result.className='result error';
    } finally { scanToggleButton.disabled=false; }
  });
  chrome.storage.onChanged.addListener(changes => {
    if (changes.ledger) renderLedger().catch(()=>{});
    if (changes.backgroundScanState) renderScanner().catch(()=>{});
    if (changes.devUpdateStatus) renderDevUpdateStatus().catch(()=>{});
  });
  renderLedger(); renderScanner(); renderDevUpdateStatus(); setInterval(renderScanner,1600);
})();
