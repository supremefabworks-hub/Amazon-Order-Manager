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

# ---------------- background.js ----------------
b = read('background.js')
b = once(b,
"const JOB_DELAY_MIN_MS = 175;\nconst JOB_DELAY_MAX_MS = 455;\nconst LOAD_SETTLE_MIN_MS = 450;\nconst LOAD_SETTLE_MAX_MS = 900;\nconst BURST_MIN_JOBS = 40;\nconst BURST_MAX_JOBS = 70;\nconst COOLDOWN_MIN_MS = 10000;\nconst COOLDOWN_MAX_MS = 25000;",
"const JOB_DELAY_MIN_MS = 75;\nconst JOB_DELAY_MAX_MS = 250;\nconst FETCH_DISPATCH_MIN_MS = 60;\nconst FETCH_DISPATCH_MAX_MS = 140;\nconst READY_INITIAL_MIN_MS = 100;\nconst READY_INITIAL_MAX_MS = 150;\nconst READY_POLL_MIN_MS = 75;\nconst READY_POLL_MAX_MS = 125;\nconst READY_TIMEOUT_MS = 700;\nconst BURST_MIN_JOBS = 60;\nconst BURST_MAX_JOBS = 90;\nconst COOLDOWN_MIN_MS = 8000;\nconst COOLDOWN_MAX_MS = 15000;",
'pacing constants')

old_scan = """async function scanWorkerTab(tabId, job) {
  await delay(randomBetween(LOAD_SETTLE_MIN_MS, LOAD_SETTLE_MAX_MS));
  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const result = await chrome.tabs.sendMessage(tabId, { type: 'ARL_WORKER_SCAN', job });
      if (result?.ok) return result;
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
"""
new_scan = """async function waitForWorkerReady(tabId, job) {
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
"""
b = once(b, old_scan, new_scan, 'adaptive worker readiness')
b = once(b, "    await delay(randomBetween(105, 245));", "    await delay(randomBetween(FETCH_DISPATCH_MIN_MS, FETCH_DISPATCH_MAX_MS));", 'fetch dispatch pacing')
write('background.js', b)

# ---------------- content.js ----------------
c = read('content.js')
ready_helper = r'''
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

'''
c = once(c, "  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {", ready_helper + "  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {", 'insert worker readiness helper')
c = once(c,
"    if (message.type === 'ARL_WORKER_SCAN') {\n      (async () => {",
"    if (message.type === 'ARL_WORKER_READY') {\n      sendResponse(workerReadiness(message.job || {}));\n      return;\n    }\n    if (message.type === 'ARL_WORKER_SCAN') {\n      (async () => {",
'worker readiness message')
old_history = """        if (message.job?.type === 'history') {
          let stable = 0;
          let previousHeight = 0;
          for (let i = 0; i < 18; i += 1) {
            const height = Math.max(document.body?.scrollHeight || 0, document.documentElement?.scrollHeight || 0);
            window.scrollTo(0, height);
            await new Promise(resolve => setTimeout(resolve, randomBetween(450, 1050)));
            const nextHeight = Math.max(document.body?.scrollHeight || 0, document.documentElement?.scrollHeight || 0);
            if (nextHeight === previousHeight || nextHeight === height) stable += 1; else stable = 0;
            previousHeight = nextHeight;
            if (stable >= 2) break;
          }
          await new Promise(resolve => setTimeout(resolve, randomBetween(700, 1600)));
        }
"""
new_history = """        if (message.job?.type === 'history') {
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
"""
c = once(c, old_history, new_history, 'history evidence stabilization')
write('content.js', c)

# ---------------- background-test.js ----------------
t = read('background-test.js')
old_test = """const backgroundSourceV0187 = fs.readFileSync(__dirname + '/background.js', 'utf8');
assert(backgroundSourceV0187.includes('const JOB_DELAY_MIN_MS = 175;') && backgroundSourceV0187.includes('const JOB_DELAY_MAX_MS = 455;'), 'v0.18.7 normal inter-job pacing should be about 30% faster');
assert(backgroundSourceV0187.includes('const LOAD_SETTLE_MIN_MS = 450;') && backgroundSourceV0187.includes('const LOAD_SETTLE_MAX_MS = 900;'), 'v0.18.7 page settle pacing should be about 30% faster');
assert(backgroundSourceV0187.includes('RATE_LIMIT_COOLDOWN_MIN_MS = 10 * 60 * 1000') && backgroundSourceV0187.includes('RATE_LIMIT_COOLDOWN_MAX_MS = 20 * 60 * 1000'), 'rate-limit cooldown safety must remain unchanged');
console.log('v0.18.7 pacing regression passed');
"""
new_test = """const backgroundSourceV01812 = fs.readFileSync(__dirname + '/background.js', 'utf8');
const contentSourceV01812 = fs.readFileSync(__dirname + '/content.js', 'utf8');
assert(backgroundSourceV01812.includes('const JOB_DELAY_MIN_MS = 75;') && backgroundSourceV01812.includes('const JOB_DELAY_MAX_MS = 250;'), 'v0.18.12 must use the approved smart-fast inter-job pacing');
assert(backgroundSourceV01812.includes('const READY_INITIAL_MIN_MS = 100;') && backgroundSourceV01812.includes('const READY_INITIAL_MAX_MS = 150;'), 'v0.18.12 readiness polling must start after a short 100-150 ms delay');
assert(backgroundSourceV01812.includes('const READY_POLL_MIN_MS = 75;') && backgroundSourceV01812.includes('const READY_POLL_MAX_MS = 125;') && backgroundSourceV01812.includes('const READY_TIMEOUT_MS = 700;'), 'v0.18.12 readiness polling bounds must stay explicit');
assert(backgroundSourceV01812.includes('const BURST_MIN_JOBS = 60;') && backgroundSourceV01812.includes('const BURST_MAX_JOBS = 90;'), 'normal burst size must be 60-90 serial jobs');
assert(backgroundSourceV01812.includes('const COOLDOWN_MIN_MS = 8000;') && backgroundSourceV01812.includes('const COOLDOWN_MAX_MS = 15000;'), 'normal cooldown must be 8-15 seconds');
assert(backgroundSourceV01812.includes('RATE_LIMIT_COOLDOWN_MIN_MS = 10 * 60 * 1000') && backgroundSourceV01812.includes('RATE_LIMIT_COOLDOWN_MAX_MS = 20 * 60 * 1000'), 'rate-limit cooldown safety must remain unchanged');
assert(backgroundSourceV01812.includes('const LOAD_TIMEOUT_MS = 45000;'), '45-second navigation timeout must remain unchanged');
assert(backgroundSourceV01812.includes('async function waitForWorkerReady') && backgroundSourceV01812.includes("type: 'ARL_WORKER_READY'"), 'rendered worker scans must use adaptive readiness polling');
assert(backgroundSourceV01812.includes('return { ready: false, timedOut: true, state: lastState };') && backgroundSourceV01812.includes("type: 'ARL_WORKER_SCAN'"), 'readiness timeout must fall through to the authoritative scan rather than accepting incomplete data');
assert(backgroundSourceV01812.includes('let processing = false;') && backgroundSourceV01812.includes('if (processing) return;'), 'crawler must remain single-job serial');
assert(contentSourceV01812.includes("message.type === 'ARL_WORKER_READY'") && contentSourceV01812.includes('canonical-detail-evidence') && contentSourceV01812.includes('history-order-fingerprint'), 'content script must expose job-specific readiness evidence');
assert(contentSourceV01812.includes('nextFingerprint === fingerprint') && contentSourceV01812.includes('stable >= 3'), 'history lazy-load stabilization must require repeated stable height and Order-ID fingerprint');
console.log('v0.18.12 adaptive smart-fast pacing regressions passed');
"""
t = once(t, old_test, new_test, 'replace pacing tests')
write('background-test.js', t)

# ---------------- release versions ----------------
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.12'
manifest['version_name'] = '0.18.12'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
package = json.loads(read('package.json'))
package['version'] = '0.18.12'
package['description'] = 'Amazon / Amazon Business complete-order ledger with adaptive serial crawling, authoritative return/replacement separation, return review/errors, filtering, bank verification, and verified development updates'
write('package.json', json.dumps(package, indent=2) + '\n')

# ---------------- docs ----------------
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.11 candidate for Issue #33.**', '**Current source baseline: v0.18.12 candidate for Issue #35.**', 1)
readme = readme.replace('- **#33 — v0.18.11 acceptance** for replacement detection and replacement-vs-return separation.', '- **#33 — v0.18.11 acceptance** for replacement detection and replacement-vs-return separation.\n- **#35 — v0.18.12 acceptance** for adaptive smart-fast serial crawl pacing and rate-limit safety.', 1)
readme = readme.replace('2. Read Issues #7, #23, #25, #29, #31, and #33 and any newer issue that supersedes their scope.', '2. Read Issues #7, #23, #25, #29, #31, #33, and #35 and any newer issue that supersedes their scope.', 1)
readme = readme.replace('4. Root v0.18.11 is the active candidate.', '4. Root v0.18.12 is the active candidate.', 1)
readme += '''\n\n## v0.18.12 adaptive smart-fast serial pacing\n\nv0.18.12 speeds the default crawler without adding concurrency. Inter-job delay is 75–250 ms, normal bursts are 60–90 jobs with 8–15 second cooldowns, and Amazon throttle cooldown remains 10–20 minutes. Rendered worker pages no longer use a blind 450–900 ms settle delay: after Chrome reports navigation complete, the background worker polls a lightweight content-script readiness probe after 100–150 ms and every 75–125 ms for up to 700 ms. Detail/history/return readiness requires job-specific DOM evidence. A readiness timeout is not accepted as completeness; it falls through to the existing authoritative scan/retry/completeness gates. History lazy-load settling now requires both document height and visible Order-ID fingerprint to remain stable for three samples. The crawler remains one job at a time. Issue #35 tracks live throughput/rate-limit acceptance.\n'''
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
handoff += '''\n\n## v0.18.12 adaptive smart-fast pacing candidate\n- Issue #35 tracks live throughput/rate-limit acceptance.\n- Serial architecture remains mandatory: one Amazon job at a time; no parallel detail, return, or history requests.\n- Normal pacing: 75–250 ms between jobs; 60–90 jobs per burst; 8–15 sec normal cooldown. Amazon throttle cooldown stays 10–20 min.\n- Rendered pages use bounded job-specific readiness polling instead of fixed 450–900 ms settle delay. Readiness timeout falls through to authoritative scan; it never counts as completeness.\n- History lazy-load stabilization requires both scroll height and Order-ID fingerprint stable for three samples.\n'''
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
testing += '''\n\n## v0.18.12 smart-fast live acceptance\n1. Let the updater install v0.18.12 and start a fresh lifetime scan.\n2. Compare visible throughput with v0.18.11; target is a noticeable additional improvement without parallel requests.\n3. Confirm history pages still capture every visible Order ID before advancing and final-page/year rollover behavior remains correct.\n4. Confirm multi-product, return lifecycle, replacement-only, payment-card, and complete-only ledger behavior remain unchanged.\n5. Watch scanner status for rate limiting/human verification. If Amazon throttles, confirm the crawler requeues the job and enters the unchanged 10–20 minute cooldown rather than retrying aggressively.\n6. Record pages/orders completed and any throttle count before closing Issue #35.\n'''
write('TESTING.md', testing)

newchat = read('NEW_CHAT_PROMPT.md')
newchat += '''\n\n### Smart-fast pacing rule\nThe v0.18.12 default crawler is serial and adaptive: 75–250 ms inter-job delay, 60–90-job normal bursts, 8–15 sec normal cooldown, unchanged 10–20 min Amazon throttle cooldown. Rendered pages use job-specific readiness polling, but readiness only controls when parsing starts; authoritative parser/completeness/fingerprint gates remain mandatory and a readiness timeout falls through to normal scanning. Never add parallel Amazon jobs as a speed optimization without an explicit architecture decision and new safety review.\n'''
write('NEW_CHAT_PROMPT.md', newchat)

print('v0.18.12 patch applied')
