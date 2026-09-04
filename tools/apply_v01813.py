from pathlib import Path
import json

R = Path('.')
def read(path): return (R / path).read_text(encoding='utf-8')
def write(path, text): (R / path).write_text(text, encoding='utf-8')
def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)

# ---------------- dashboard.html ----------------
h = read('dashboard.html')
h = once(h, '<div class="eyebrow">AMAZON REFUND LEDGER · v0.16</div>', '<div class="eyebrow" id="ledgerVersion">AMAZON REFUND LEDGER</div>', 'dynamic version host')
write('dashboard.html', h)

# ---------------- dashboard.js ----------------
d = read('dashboard.js')
d = once(d,
"  const bankResultFile = document.getElementById('bankResultFile');\n  let ledger = [];",
"  const bankResultFile = document.getElementById('bankResultFile');\n  const ledgerVersion = document.getElementById('ledgerVersion');\n  const manifest = chrome.runtime.getManifest();\n  const displayedVersion = String(manifest.version_name || manifest.version || '').trim();\n  if (ledgerVersion) ledgerVersion.textContent = `AMAZON REFUND LEDGER${displayedVersion ? ` · v${displayedVersion}` : ''}`;\n  let ledger = [];",
'dashboard live manifest version')
d = once(d,
'''          <button class="mini action-large" data-open-url="${esc(row.openUrl)}" ${row.openUrl ? '' : 'disabled'}>Details</button>
          <button class="mini action-large" data-action="reconcile" data-order="${esc(row.orderId)}" ${row.dataComplete && row.hasReturn ? '' : 'disabled'}>Credit</button>
          <button class="mini action-large" data-action="reset" data-order="${esc(row.orderId)}" ${row.dataComplete && row.hasReturn ? '' : 'disabled'}>Reset</button>
          <button class="mini action-large" data-refresh-order="${esc(row.orderId)}" ${row.openUrl ? '' : 'disabled'}>Refresh</button>''',
'''          <button class="mini action-large" data-open-url="${esc(row.openUrl)}" ${row.openUrl ? '' : 'disabled'}>Details</button>
          <button class="mini action-large" data-action="reconcile" data-order="${esc(row.orderId)}" ${row.dataComplete && row.hasReturn ? '' : 'disabled'}>Credit</button>
          <button class="mini action-large" data-reset-refresh-order="${esc(row.orderId)}" ${row.openUrl ? '' : 'disabled'}>Reset & Refresh</button>''',
'combine reset refresh buttons')
old_refresh = '''    const refresh = event.target.closest('button[data-refresh-order]');
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
'''
new_refresh = '''    const resetRefresh = event.target.closest('button[data-reset-refresh-order]');
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
'''
d = once(d, old_refresh, new_refresh, 'reset refresh click handler')
d = once(d,
'''    const action = event.target.closest('button[data-action]');
    if (!action) return;
    const manualState = action.dataset.action === 'reconcile' ? 'reconciled' : null;
    const matching = ledger.filter(r => r.recordType === 'return' && r.orderId === action.dataset.order);
    for (const record of matching) await storage.updateRecord(record.recordId, { manualState });
    await reload();''',
'''    const action = event.target.closest('button[data-action]');
    if (!action) return;
    if (action.dataset.action !== 'reconcile') return;
    const matching = ledger.filter(r => r.recordType === 'return' && r.orderId === action.dataset.order);
    for (const record of matching) await storage.updateRecord(record.recordId, { manualState: 'reconciled' });
    await reload();''',
'remove old manual reset behavior')
write('dashboard.js', d)

# ---------------- background.js ----------------
b = read('background.js')
old_force_start = '''async function forceRefreshOrder(orderId) {
  const id = String(orderId || '').trim();
  if (!/^\\d{3}-\\d{7}-\\d{7}$/.test(id)) throw new Error('Invalid Amazon order ID.');
  const data = await chrome.storage.local.get([LEDGER_KEY]);
  const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
  const order = ledger.find(r => r?.recordType === 'order' && r?.orderId === id) || null;
  const detailUrl = order?.orderDetailsUrl || null;
  if (!detailUrl || !/(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|\\/gp\\/css\\/summary\\/edit\\.html|order-details)/i.test(detailUrl)) {
    throw new Error('This order has no real captured View order details URL. Refresh cannot invent one.');
  }
  const tab = await chrome.tabs.create({ url: detailUrl, active: false });'''
new_force_start = '''async function resetOrderForAuthoritativeRefresh(orderId) {
  const id = String(orderId || '').trim();
  if (!/^\\d{3}-\\d{7}-\\d{7}$/.test(id)) throw new Error('Invalid Amazon order ID.');
  const data = await chrome.storage.local.get([LEDGER_KEY]);
  const ledger = Array.isArray(data[LEDGER_KEY]) ? data[LEDGER_KEY] : [];
  const order = ledger.find(r => r?.recordType === 'order' && r?.orderId === id) || null;
  const detailUrl = order?.orderDetailsUrl || null;
  if (!detailUrl || !/(?:\\/your-orders\\/order-details|\\/gp\\/your-account\\/order-details|\\/gp\\/css\\/summary\\/edit\\.html|order-details)/i.test(detailUrl)) {
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
    const tab = await chrome.tabs.create({ url: detailUrl, active: false });'''
b = once(b, old_force_start, new_force_start, 'replace force refresh entry')
# Replace references to local id/detailUrl still work inside nested try; now tab is scoped inside outer try.
old_end = '''    await patchOrderProcessing(id, { orderDataComplete: true, processingState: 'complete', processingError: null, processingErrorAt: null, processingLastIssue: null, returnStatusExpectedCount: uniqueReturnLinks.size, returnStatusAuthoritativeCount: returnsRefreshed, returnStatusComplete: returnsRefreshed === uniqueReturnLinks.size, orderDataCompletedAt: nowIso() });
    return { ok: true, orderId: id, detailScannedAt: nowIso(), returnsRefreshed };
  } catch (error) {
    await patchOrderProcessing(id, { processingState: 'error', processingError: `refresh: ${error?.message || error}`.slice(0, 500), processingErrorAt: nowIso() });
    throw error;
  } finally {
    try { await chrome.tabs.remove(tabId); } catch (_) {}
  }
}'''
new_end = '''    await patchOrderProcessing(id, { orderDataComplete: true, processingState: 'complete', processingError: null, processingErrorAt: null, processingLastIssue: null, returnStatusExpectedCount: uniqueReturnLinks.size, returnStatusAuthoritativeCount: returnsRefreshed, returnStatusComplete: returnsRefreshed === uniqueReturnLinks.size, orderDataCompletedAt: nowIso() });
    await restoreCrawlCompletionAfterAuthoritativeRefresh(id, resetContext?.previousCrawlCompletion || null);
    return { ok: true, orderId: id, detailScannedAt: nowIso(), returnsRefreshed, resetAndRefreshed: true };
    } catch (error) {
      const id = resetContext?.id || String(orderId || '').trim();
      if (/^\\d{3}-\\d{7}-\\d{7}$/.test(id)) {
        await patchOrderProcessing(id, { processingState: 'error', orderDataComplete: false, processingError: `reset-refresh: ${error?.message || error}`.slice(0, 500), processingErrorAt: nowIso(), processingLastIssue: `reset-refresh: ${error?.message || error}`.slice(0, 500) });
      }
      throw error;
    } finally {
      processing = false;
      const state = ensureCrawl(await getState().catch(() => defaultState()));
      if (!state.paused && state.queue?.length) scheduleSoon(randomBetween(75, 250));
    }
  } catch (error) {
    processing = false;
    throw error;
  }
}'''
b = once(b, old_end, new_end, 'force refresh completion/failure')
old_msg = '''  if (message.type === 'ARL_REFRESH_ORDER') {
    forceRefreshOrder(message.orderId)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }'''
new_msg = '''  if (message.type === 'ARL_RESET_REFRESH_ORDER') {
    forceResetRefreshOrder(message.orderId)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }'''
b = once(b, old_msg, new_msg, 'message handler reset refresh')
write('background.js', b)

# ---------------- tests ----------------
ut = read('ui-test.js')
ut += r'''

const dashboardHtmlV01813 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
const dashboardJsV01813 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
assert(!dashboardHtmlV01813.includes('AMAZON REFUND LEDGER · v0.16'), 'dashboard must not hard-code stale v0.16 text');
assert(dashboardHtmlV01813.includes('id="ledgerVersion"'), 'dashboard must expose a dynamic version host');
assert(dashboardJsV01813.includes('chrome.runtime.getManifest()') && dashboardJsV01813.includes('manifest.version_name || manifest.version'), 'dashboard version must come from the installed manifest');
assert(dashboardJsV01813.includes('data-reset-refresh-order') && dashboardJsV01813.includes('Reset & Refresh'), 'order row must expose one combined Reset & Refresh action');
assert(!dashboardJsV01813.includes('data-refresh-order=') && !dashboardJsV01813.includes('data-action="reset"'), 'separate Reset and Refresh controls must be removed');
assert(dashboardJsV01813.includes("type: 'ARL_RESET_REFRESH_ORDER'"), 'combined button must call the authoritative rebuild path');
console.log('v0.18.13 reset-refresh/version UI regressions passed');
'''
write('ui-test.js', ut)

bt = read('background-test.js')
bt += r'''

const backgroundSourceV01813 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(backgroundSourceV01813.includes('async function resetOrderForAuthoritativeRefresh(orderId)'), 'combined recovery must clear order-scoped derived data first');
assert(backgroundSourceV01813.includes("ledger.filter(record => record?.orderId !== id)"), 'reset must remove every stored record for the selected order ID');
assert(backgroundSourceV01813.includes("statusText: 'Reset for authoritative refresh'") && backgroundSourceV01813.includes("processingState: 'processing'"), 'reset must leave a minimal processing shell with the real route');
assert(backgroundSourceV01813.includes('previousCrawlCompletion') && backgroundSourceV01813.includes('restoreCrawlCompletionAfterAuthoritativeRefresh'), 'crawl completion must be removed during rebuild and restored only after success');
assert(backgroundSourceV01813.includes("message.type === 'ARL_RESET_REFRESH_ORDER'"), 'background must expose one combined reset-refresh message');
assert(!backgroundSourceV01813.includes("message.type === 'ARL_REFRESH_ORDER'"), 'old standalone refresh message path must be removed');
assert(backgroundSourceV01813.includes('while (processing && Date.now() < waitDeadline)') && backgroundSourceV01813.includes('processing = true'), 'manual rebuild must share the serial crawler lock');
assert(backgroundSourceV01813.includes("processingError: `reset-refresh:"), 'failed rebuild must retain an Errors-view shell');
console.log('v0.18.13 reset-refresh background regressions passed');
'''
write('background-test.js', bt)

# ---------------- versions ----------------
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.13'
manifest['version_name'] = '0.18.13'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
package = json.loads(read('package.json'))
package['version'] = '0.18.13'
package['description'] = 'Amazon / Amazon Business complete-order ledger with adaptive serial crawling, authoritative reset-refresh recovery, return/replacement separation, filtering, bank verification, and verified development updates'
write('package.json', json.dumps(package, indent=2) + '\n')

# ---------------- docs ----------------
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.12 candidate for Issue #35.**', '**Current source baseline: v0.18.13 candidate for Issue #37.**', 1)
readme = readme.replace('- **#35 — v0.18.12 acceptance** for adaptive smart-fast serial crawler pacing and live throughput/rate-limit validation.', '- **#35 — v0.18.12 acceptance** for adaptive smart-fast serial crawler pacing and live throughput/rate-limit validation.\n- **#37 — v0.18.13 acceptance** for combined Reset & Refresh recovery and dynamic installed-version display.', 1)
readme = readme.replace('2. Read Issues #7, #23, #25, #29, #31, #33, and #35 and any newer issue that supersedes their scope.', '2. Read Issues #7, #23, #25, #29, #31, #33, #35, and #37 and any newer issue that supersedes their scope.', 1)
readme = readme.replace('4. Root v0.18.12 is the active candidate.', '4. Root v0.18.13 is the active candidate.', 1)
readme = readme.replace('Every row uses the same fixed `Details | Credit | Reset | Refresh` action group.', 'Every row uses the fixed `Details | Credit | Reset & Refresh` action group. `Reset & Refresh` clears all derived data for that Order ID while preserving only the real captured Order Details route, then rebuilds the order from Amazon; failures remain visible in Errors with the route preserved.', 1)
readme += '''\n\n## v0.18.13 authoritative Reset & Refresh and dynamic version display\n\nSeparate Reset and Refresh controls are replaced by one `Reset & Refresh` recovery action. It preserves only the selected Order ID and captured real Order Details URL, removes all stored product/return/refund/replacement/bank/manual derived state, reopens the order as incomplete, and immediately rebuilds it from canonical Amazon evidence using the existing serial crawler lock. A failed rebuild remains in Errors with the real Details URL so retry remains possible. The dashboard header no longer hard-codes a historical version; it renders `chrome.runtime.getManifest().version_name || version` from the installed build. Issue #37 tracks live acceptance.\n'''
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
handoff += '''\n\n## v0.18.13 combined recovery candidate\n- Issue #37 tracks live acceptance.\n- Row actions are `Details | Credit | Reset & Refresh`; old standalone Reset/Refresh paths are removed.\n- Reset & Refresh preserves only Order ID + real captured Order Details URL, deletes order-scoped derived ledger state, and rebuilds under the same single-job lock.\n- Failed rebuilds keep a minimal Errors-view shell and never invent a URL.\n- Dashboard version is derived dynamically from the installed manifest; no hard-coded release number belongs in dashboard HTML.\n'''
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
testing += '''\n\n## v0.18.13 live acceptance\n1. Verify dashboard header shows the actual installed `0.18.13` version, not `v0.16`.\n2. Pick a complete order and click `Reset & Refresh`. Confirm there is no separate Reset or Refresh button.\n3. Confirm the order temporarily leaves completed views while rebuilding, then returns with fresh canonical product/return/replacement/refund/payment state.\n4. Confirm prior manual bank/reconciliation state for that Order ID is cleared by the rebuild.\n5. Test one forced/real refresh failure if available: the order must remain in Errors with its real Details URL and exact error, then successfully rebuild when retried.\n6. Run alongside/resume the lifetime crawler and verify no concurrent Amazon job race or skipped page occurs.\n'''
write('TESTING.md', testing)

newchat = read('NEW_CHAT_PROMPT.md')
newchat += '''\n\n### Order recovery action\nUse one `Reset & Refresh` action only. It is an authoritative rebuild: preserve only the Order ID and captured real Order Details route, clear all order-scoped derived ledger data, then rebuild from Amazon under the serial worker lock. A failed rebuild must remain retryable in Errors. Dashboard version text must always come from the installed manifest, never a hard-coded string.\n'''
write('NEW_CHAT_PROMPT.md', newchat)

print('v0.18.13 patch applied')
