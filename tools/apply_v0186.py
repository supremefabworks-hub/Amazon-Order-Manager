from pathlib import Path
import json, re

ROOT = Path('.')

def read(path): return (ROOT / path).read_text(encoding='utf-8')
def write(path, text): (ROOT / path).write_text(text, encoding='utf-8')
def once(text, old, new, label):
    n = text.count(old)
    if n != 1: raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

p = read('parser.js')

# Route-aware pagination state. Only controls structurally belonging to Amazon pagination may
# advertise a next page; disabled Next text and unrelated page UI cannot keep a year alive.
start = p.index('  function hasNextPageControl(doc) {')
end = p.index('\n\n  function nextPageCandidates(doc, baseUrl) {', start)
new_block = r'''  function isDisabledPaginationControl(el) {
    if (!el) return true;
    if (el.disabled || String(el.getAttribute?.('aria-disabled') || '').toLowerCase() === 'true') return true;
    const className = typeof el.className === 'string' ? el.className : String(el.getAttribute?.('class') || '');
    if (/(?:^|\s)(?:a-disabled|s-pagination-disabled|disabled)(?:\s|$)/i.test(className)) return true;
    try {
      if (el.closest?.('.a-disabled, .s-pagination-disabled, [aria-disabled="true"]')) return true;
    } catch (_) {}
    return false;
  }

  function paginationControlContext(el) {
    if (!el) return false;
    const href = String(el.getAttribute?.('href') || el.href || el.getAttribute?.('data-href') || el.getAttribute?.('data-url') || '');
    if (/#(?:time\/20\d{2}\/)?pagination\/(?:\d+|next|previous)\/?/i.test(href)) return true;
    if (/[?&](?:startIndex|page(?:Number|No|Num)?)=\d+/i.test(href)) return true;
    try {
      return Boolean(el.closest?.('ul.a-pagination, .a-pagination, nav[aria-label*="pagination" i], [role="navigation"][aria-label*="pagination" i], [data-testid*="pagination" i]'));
    } catch (_) { return false; }
  }

  function selectedPaginationPage(doc) {
    if (!doc?.querySelector) return null;
    for (const selector of ['.a-pagination li.a-selected', '.a-pagination [aria-current="page"]', '[aria-current="page"]', '.s-pagination-selected']) {
      try {
        const el = doc.querySelector(selector);
        const n = Number(normalizeText(el?.innerText || el?.textContent || ''));
        if (Number.isFinite(n) && n >= 1) return n;
      } catch (_) {}
    }
    return null;
  }

  function paginationPageNumberFromControl(el) {
    if (!el) return null;
    const href = String(el.getAttribute?.('href') || el.href || el.getAttribute?.('data-href') || el.getAttribute?.('data-url') || '');
    const hashMatch = href.match(/#(?:time\/20\d{2}\/)?pagination\/(\d+)\/?/i);
    if (hashMatch) return Number(hashMatch[1]);
    try {
      const u = new URL(href, 'https://www.amazon.com/');
      const startRaw = u.searchParams.get('startIndex');
      if (startRaw != null && startRaw !== '') {
        const start = Number(startRaw);
        if (Number.isFinite(start) && start >= 0) return Math.floor(start / 10) + 1;
      }
      for (const key of ['page', 'pageNumber', 'pageNo', 'pageNum']) {
        const value = Number(u.searchParams.get(key));
        if (Number.isFinite(value) && value >= 1) return value;
      }
    } catch (_) {}
    const textNumber = Number(normalizeText(el.innerText || el.textContent || ''));
    return Number.isFinite(textNumber) && textNumber >= 1 ? textNumber : null;
  }

  function hasNextPageControl(doc, baseUrl = '') {
    if (!doc?.querySelectorAll) return false;
    const routePage = historyRouteFromUrl(baseUrl).page;
    const currentPage = Number.isFinite(Number(routePage)) ? Number(routePage) : selectedPaginationPage(doc);

    // High-confidence enabled Next controls. Broad whole-page "Next" text is deliberately excluded.
    const selectors = [
      'a[rel="next"]',
      'ul.a-pagination li.a-last:not(.a-disabled) a[href]',
      '.a-pagination .a-last:not(.a-disabled) a[href]',
      'li.a-last:not(.a-disabled) a[href]',
      'a.s-pagination-next:not(.s-pagination-disabled)',
      'a[aria-label="Go to next page"]',
      'a[aria-label*="next page" i]',
      '.a-pagination button[aria-label*="next" i]:not([disabled])',
      '.a-pagination [role="button"][aria-label*="next" i]',
      '[data-testid*="pagination" i] a[aria-label*="next" i]'
    ];
    for (const selector of selectors) {
      try {
        const el = doc.querySelector(selector);
        if (el && !isDisabledPaginationControl(el)) return true;
      } catch (_) {}
    }

    // Numeric N+1 links are also authoritative, but only when their href/ancestor proves they are
    // pagination controls. This handles Amazon's hash pager even if it omits a separate Next anchor.
    let controls = [];
    try { controls = Array.from(doc.querySelectorAll('a[href], button, [role="button"], li, span')); } catch (_) {}
    for (const el of controls) {
      if (!paginationControlContext(el)) continue;
      if (isDisabledPaginationControl(el)) continue;
      const href = String(el.getAttribute?.('href') || el.href || el.getAttribute?.('data-href') || el.getAttribute?.('data-url') || '');
      const text = normalizeText(el.innerText || el.textContent || el.getAttribute?.('aria-label') || el.getAttribute?.('title') || '').toLowerCase();
      const isNext = /#(?:time\/20\d{2}\/)?pagination\/next\/?/i.test(href) || /(^|\b)next(?:\s+page)?(?:\b|\s*[→›»])/.test(text);
      if (isNext) {
        const tag = String(el.tagName || '').toLowerCase();
        if (href || tag === 'button' || String(el.getAttribute?.('role') || '').toLowerCase() === 'button') return true;
      }
      const pageNumber = paginationPageNumberFromControl(el);
      if (currentPage != null && pageNumber != null && pageNumber > currentPage) return true;
    }
    return false;
  }'''
p = p[:start] + new_block + p[end:]

p = once(p,
    'if (isOrderHistoryPage(doc, baseUrl) && hasNextPageControl(doc)) {',
    'if (isOrderHistoryPage(doc, baseUrl) && hasNextPageControl(doc, baseUrl)) {',
    'synthetic next route-aware control')
p = once(p,
    'if (hasNextPageControl(doc)) {\n        const year = route.year || displayedHistoryYear(doc, baseUrl);',
    'if (hasNextPageControl(doc, baseUrl)) {\n        const year = route.year || displayedHistoryYear(doc, baseUrl);',
    'infer next route-aware control')
p = once(p,
    '      hasNextPageControl: hasNextPageControl(doc),',
    '      hasNextPageControl: hasNextPageControl(doc, url),',
    'parsed history route-aware control')\n
# The generic anchor fallback in findNextLink may only use links that actually belong to pagination.
needle = "      if (!/(^|\\b)next(?:\\s+page)?(?:\\b|\\s*[→›»])/.test(text)) continue;\n      if (a.closest?.('.a-disabled') || a.getAttribute?.('aria-disabled') === 'true') continue;"
replacement = "      if (!/(^|\\b)next(?:\\s+page)?(?:\\b|\\s*[→›»])/.test(text)) continue;\n      if (!paginationControlContext(a)) continue;\n      if (isDisabledPaginationControl(a)) continue;"
p = once(p, needle, replacement, 'findNextLink structural Next fallback')
write('parser.js', p)

# Version bump.
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.6'
manifest['version_name'] = '0.18.6'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
package = json.loads(read('package.json'))
package['version'] = '0.18.6'
write('package.json', json.dumps(package, indent=2) + '\n')

# Pager regressions: final selected page with disabled Next ends the year; prior page with a real N+1 remains actionable.
t = read('parser-test.js')
append = r'''

// v0.18.6 final-page pagination regressions
function v0186PagerElement({ text = '', href = '', className = '', tagName = 'A', ariaDisabled = null, inPager = true, role = null } = {}) {
  return {
    innerText: text, textContent: text, href, className, tagName, disabled: false,
    getAttribute(name) {
      if (name === 'href') return href || null;
      if (name === 'class') return className || null;
      if (name === 'aria-disabled') return ariaDisabled;
      if (name === 'aria-label') return text;
      if (name === 'role') return role;
      return null;
    },
    closest(selector) {
      if (/(?:\.a-disabled|\.s-pagination-disabled|\[aria-disabled="true"\])/.test(selector) && (ariaDisabled === 'true' || /(?:^|\s)(?:a-disabled|s-pagination-disabled|disabled)(?:\s|$)/i.test(className))) return this;
      if (inPager && /pagination/i.test(selector)) return { className: 'a-pagination' };
      return null;
    }
  };
}
function v0186PagerDoc(currentPage, controls, activeNext = null) {
  const current = v0186PagerElement({ text: String(currentPage), href: `#pagination/${currentPage}/` });
  return {
    querySelector(selector) {
      if (selector.includes('a-selected') || selector.includes('aria-current') || selector.includes('s-pagination-selected')) return current;
      if (activeNext && /next|a-last|rel="next"/i.test(selector)) return activeNext;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === 'a[href]') return controls.filter(x => x.href);
      if (selector.includes('a[href], button')) return controls;
      return [];
    }
  };
}
const v0186DisabledNext = v0186PagerElement({ text: 'Next', tagName: 'LI', href: '', className: 'a-last a-disabled', ariaDisabled: 'true' });
const v0186FinalLinks = [11,12,13,14,15,16,17,18].map(n => v0186PagerElement({ text:String(n), href:`#pagination/${n}/` }));
const v0186FinalDoc = v0186PagerDoc(18, [...v0186FinalLinks, v0186DisabledNext]);
const v0186FinalUrl = 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/18/';
assert(p.hasNextPageControl(v0186FinalDoc, v0186FinalUrl) === false, 'selected final page + disabled Next must end the current history year');
assert(p.findNextLink(v0186FinalDoc, v0186FinalUrl) == null, 'final page must not synthesize or discover page 19 when Next is disabled');

const v0186Page18 = v0186PagerElement({ text:'18', href:'#pagination/18/' });
const v0186EnabledNext = v0186PagerElement({ text:'Next', href:'#pagination/18/' });
const v0186Page17Doc = v0186PagerDoc(17, [v0186Page18, v0186EnabledNext], v0186EnabledNext);
const v0186Page17Url = 'https://www.amazon.com/gp/your-account/order-history#time/2026/pagination/17/';
assert(p.hasNextPageControl(v0186Page17Doc, v0186Page17Url) === true, 'page 17 with real page 18/enabled Next must continue');
const v0186NextUrl = p.findNextLink(v0186Page17Doc, v0186Page17Url);
assert(v0186NextUrl && /pagination\/18\//.test(v0186NextUrl), 'page 17 must resolve the concrete page 18 route');

const v0186UnrelatedNext = v0186PagerElement({ text:'Next', tagName:'BUTTON', href:'', inPager:false });
const v0186UnrelatedDoc = v0186PagerDoc(18, [v0186UnrelatedNext]);
assert(p.hasNextPageControl(v0186UnrelatedDoc, v0186FinalUrl) === false, 'unrelated whole-page Next text/button must not masquerade as history pagination');
'''
if 'v0.18.6 final-page pagination regressions' in t: raise RuntimeError('v0.18.6 tests already present')
t += append
write('parser-test.js', t)

# Durable docs/handoff.
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.5', '**Current source baseline: v0.18.6', 1)
readme += '''\n\n## v0.18.6 end-of-year pagination boundary\n\nv0.18.6 treats Amazon history pagination as a scoped control state, not generic page text. A selected final page with disabled/no actionable Next now marks that year complete and queues the next older discovered year. Enabled Next or a concrete numeric N+1 pagination target still advances only after the visible Order-ID fingerprint changes. Generic unrelated `Next` text cannot keep a year alive.\n'''
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
handoff += '''\n\n## v0.18.6 live boundary fix\n- Live v0.18.5 reached 2026 page 18 with 7/7 orders complete but mistook disabled Next for an actionable pager and stopped instead of switching years.\n- v0.18.6 scopes Next detection to real pagination controls/numeric pagination routes. Final selected page + disabled/no actionable Next = year complete -> next older year.\n- Page fingerprint remains the only proof of a successful within-year advance.\n- Issue #23 remains open until a live lifetime scan crosses 2026 page 18 into 2025.\n'''
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
testing += '''\n\n## v0.18.6 final-page / year rollover\n1. Let the verified updater install v0.18.6 automatically.\n2. Run a fresh lifetime scan through the last page of the current year.\n3. On a pager where page 18 is selected and Next is disabled, confirm the crawler does not attempt page 19.\n4. Confirm the current year is marked complete and page 1 of the next older discovered year is queued.\n5. Confirm a non-final page with enabled Next or a concrete numeric N+1 still advances only after the Order-ID fingerprint changes.\n'''
write('TESTING.md', testing)

newchat = read('NEW_CHAT_PROMPT.md')
newchat += '''\n\n### v0.18.6 durable addition\nAmazon Order History year rollover is determined by scoped pager state. Disabled/no actionable Next on the selected final page ends the year; unrelated `Next` page text is ignored. Within-year progress still requires a changed visible Order-ID fingerprint. Issue #23 tracks live rollover acceptance.\n'''
write('NEW_CHAT_PROMPT.md', newchat)

print('v0.18.6 end-of-year pagination patch applied')
