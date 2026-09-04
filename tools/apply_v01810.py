from pathlib import Path
import json

R = Path('.')
def read(p): return (R/p).read_text(encoding='utf-8')
def write(p,s): (R/p).write_text(s, encoding='utf-8')
def once(s,a,b,label):
    n=s.count(a)
    if n != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return s.replace(a,b,1)

# dashboard.html: four user-facing views only.
h = read('dashboard.html')
h = once(h,
'''      <button class="view-button" data-view="all">All orders <span id="navAllCount">0</span></button>\n      <button class="view-button" data-view="returns">Returns <span id="navReturnCount">0</span></button>\n      <button class="view-button" data-view="needs_review">Needs review <span id="navReviewCount">0</span></button>\n      <button class="view-button" data-view="processing">Processing <span id="navProcessingCount">0</span></button>\n      <button class="view-button" data-view="errors">Errors <span id="navErrorCount">0</span></button>''',
'''      <button class="view-button" data-view="all">Orders <span id="navAllCount">0</span></button>\n      <button class="view-button" data-view="returns">Returns <span id="navReturnCount">0</span></button>\n      <button class="view-button" data-view="needs_review">Return review <span id="navReviewCount">0</span></button>\n      <button class="view-button" data-view="errors">Errors <span id="navErrorCount">0</span></button>''',
'view navigation')
h = once(h, '<option value="needs_review">Needs review</option>', '<option value="needs_review">Return review</option>', 'status filter label')
write('dashboard.html', h)

# dashboard.js: remove redundant complete/detail metric and all user-facing Processing view references.
d = read('dashboard.js')
d = once(d, "  const navProcessingCount = document.getElementById('navProcessingCount');\n", '', 'processing nav const')
d = once(d, "  if (!['all', 'returns', 'needs_review', 'processing', 'errors'].includes(currentView)) currentView = 'all';", "  if (!['all', 'returns', 'needs_review', 'errors'].includes(currentView)) currentView = 'all';", 'initial view allowlist')
d = once(d, "      if (currentView === 'processing' && (row.dataComplete || row.processingError)) return false;\n", '', 'processing view filter')
d = once(d, "    const processingRows = allRows.filter(r => !r.dataComplete && !r.processingError);\n", '', 'processing stats rows')
d = once(d, "    const detailed = rows.filter(r => r.detailComplete);\n", '', 'redundant detailed stat rows')
d = once(d, "    navProcessingCount.textContent = String(processingRows.length);\n", '', 'processing nav count')
d = once(d,
'''      <div class="stat"><span>Complete orders</span><strong>${rows.length}</strong><small>${money(sum(rows, 'orderTotal'))} captured order total</small></div>\n      <div class="stat"><span>Order details</span><strong>${detailed.length}</strong><small>Fully processed canonical orders</small></div>\n      <div class="stat"><span>Returns</span><strong>${returnRows.length}</strong><small>${money(sum(returnRows, 'refundAmount'))} expected refunds</small></div>\n      <div class="stat stat-review-total"><span>Needs review</span><strong>${money(reviewExpectedTotal)}</strong><small>${reviewRows.length} flagged ${reviewRows.length === 1 ? 'order' : 'orders'}</small></div>\n      <div class="stat"><span>Processing</span><strong>${processingRows.length}</strong><small>Hidden from completed ledger</small></div>\n      <div class="stat"><span>Errors</span><strong>${errorRows.length}</strong><small>Require retry or investigation</small></div>`;''',
'''      <div class="stat"><span>Complete orders</span><strong>${rows.length}</strong><small>${money(sum(rows, 'orderTotal'))} captured order total · fully processed canonical orders</small></div>\n      <div class="stat"><span>Returns</span><strong>${returnRows.length}</strong><small>${money(sum(returnRows, 'refundAmount'))} expected refunds</small></div>\n      <div class="stat stat-review-total"><span>Return review</span><strong>${money(reviewExpectedTotal)}</strong><small>${reviewRows.length} flagged ${reviewRows.length === 1 ? 'order' : 'orders'}</small></div>\n      <div class="stat"><span>Errors</span><strong>${errorRows.length}</strong><small>Require retry or investigation</small></div>`;''',
'stats consolidation')
d = once(d, "    if (row.stateKey === 'needs_review') return row.statusLabel || 'Needs review';", "    if (row.stateKey === 'needs_review') return row.statusLabel || 'Return review';", 'review badge fallback')
d = once(d, "    if (!['all', 'returns', 'needs_review', 'processing', 'errors'].includes(view)) return;", "    if (!['all', 'returns', 'needs_review', 'errors'].includes(view)) return;", 'setView allowlist')
write('dashboard.js', d)

# Version bump.
manifest = json.loads(read('manifest.json'))
manifest['version'] = '0.18.10'
manifest['version_name'] = '0.18.10'
write('manifest.json', json.dumps(manifest, indent=2) + '\n')
package = json.loads(read('package.json'))
package['version'] = '0.18.10'
package['description'] = 'Amazon / Amazon Business complete-order ledger with authoritative returns, return review/errors, filtering, bank verification, and verified development updates'
write('package.json', json.dumps(package, indent=2) + '\n')

# UI regression: exact four tabs, no Processing view, one combined complete-order metric.
u = read('ui-test.js')
u += r'''

const dashboardHtmlV01810 = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
const dashboardSourceV01810 = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
for (const view of ['all','returns','needs_review','errors']) assert(dashboardHtmlV01810.includes(`data-view="${view}"`), `v0.18.10 must retain ${view} navigation`);
assert(!dashboardHtmlV01810.includes('data-view="processing"'), 'Processing must remain internal and not be a user-facing tab');
assert(dashboardHtmlV01810.includes('>Orders <') && dashboardHtmlV01810.includes('>Return review <'), 'navigation labels must be Orders and Return review');
assert(!dashboardSourceV01810.includes("currentView === 'processing'"), 'dashboard must not expose a Processing view');
assert((dashboardSourceV01810.match(/<span>Complete orders<\/span>/g) || []).length === 1, 'dashboard must render exactly one Complete orders metric');
assert(!dashboardSourceV01810.includes('<span>Order details</span>'), 'redundant Order details metric must be removed');
assert(!dashboardSourceV01810.includes('<span>Processing</span>'), 'Processing top metric must be removed');
assert(dashboardSourceV01810.includes('captured order total · fully processed canonical orders'), 'Complete orders metric must combine count meaning and captured-dollar context');
assert(dashboardSourceV01810.includes('<span>Return review</span>'), 'review stat must use Return review label');
console.log('v0.18.10 consolidated dashboard metrics regressions passed');
'''
write('ui-test.js', u)

# Durable docs/handoff.
readme = read('README.md')
readme = readme.replace('**Current source baseline: v0.18.9 candidate for Issue #29.**', '**Current source baseline: v0.18.10 candidate for Issue #31.**', 1)
readme = readme.replace('- **#29 — v0.18.9 acceptance** for authoritative return progress, complete-only ledger views, Processing/Errors isolation, and sort/filter/search. Issue #29 supersedes #27 for the remaining lifecycle defect.', '- **#29 — v0.18.9 acceptance** for authoritative return progress and complete-only ledger behavior.\n- **#31 — v0.18.10 acceptance** for consolidated dashboard metrics and four user-facing views: Orders, Returns, Return review, Errors.', 1)
readme = readme.replace('2. Read Issues #7, #23, #25, and #29 and any newer issue that supersedes their scope.', '2. Read Issues #7, #23, #25, #29, and #31 and any newer issue that supersedes their scope.', 1)
readme = readme.replace('4. Root v0.18.9 is the active candidate.', '4. Root v0.18.10 is the active candidate.', 1)
readme += '\n\n## v0.18.10 dashboard metric cleanup\n\nv0.18.10 removes the redundant `Order details` stat because complete orders are already fully processed canonical orders. The single `Complete orders` stat keeps the completed-order count plus captured-order-dollar total. Processing remains an internal crawler state and is no longer a user-facing tab/stat. User navigation is exactly `Orders | Returns | Return review | Errors`. Issue #31 tracks live acceptance.\n'
write('README.md', readme)

handoff = read('PROJECT_HANDOFF.md')
handoff += '\n\n## v0.18.10 dashboard cleanup\n- Issue #31.\n- Remove duplicate `Order details` stat; `Complete orders` is the canonical completed-order metric and includes captured order-total dollars.\n- Processing remains internal/hidden; user-facing views are exactly Orders, Returns, Return review, Errors.\n- No crawler/parser/lifecycle/data-completeness semantics changed.\n- Manifest/package v0.18.10; live acceptance after verified dev release.\n'
write('PROJECT_HANDOFF.md', handoff)

testing = read('TESTING.md')
testing += '\n\n## v0.18.10 dashboard acceptance\n- Confirm top stats show Complete orders, Returns, Return review, Errors only.\n- Confirm there is no separate Order details or Processing stat.\n- Confirm navigation is exactly Orders, Returns, Return review, Errors.\n- Confirm incomplete non-error orders remain hidden while scanner progress still reports queued/in-flight work.\n'
write('TESTING.md', testing)

newchat = read('NEW_CHAT_PROMPT.md')
newchat += '\n\nCurrent UI cleanup baseline: v0.18.10 / Issue #31 consolidates Complete orders + Order details and removes the user-facing Processing tab. Processing remains internal; navigation is Orders, Returns, Return review, Errors.\n'
write('NEW_CHAT_PROMPT.md', newchat)

print('v0.18.10 patch applied')
