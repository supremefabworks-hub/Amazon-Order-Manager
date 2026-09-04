from pathlib import Path
p=Path('background.js')
s=p.read_text(encoding='utf-8')
old="""function snapshotHistoricalFrontier(crawl) {
  if (!crawl?.currentYear) return crawl?.priorFrontier || null;
  return {
    capturedAt: nowIso(),
    year: Number(crawl.currentYear),
    page: Math.max(1, Number(crawl.currentPage) || 1),
    pageKey: `${Number(crawl.currentYear)}:${Math.max(1, Number(crawl.currentPage) || 1)}`,
    historyUrl: crawl.currentHistoryUrl || null,
    ordersCompleted: Object.keys(crawl.completedOrders || {}).length,
    lastCompletedOrderId: crawl.lastCompletedOrderId || null
  };
}
"""
new="""function deeperHistoricalFrontier(a, b) {
  if (!a) return b || null;
  if (!b) return a;
  const ay = Number(a.year), by = Number(b.year);
  if (Number.isFinite(ay) && Number.isFinite(by) && ay !== by) return ay < by ? a : b;
  const ap = Math.max(1, Number(a.page) || 1), bp = Math.max(1, Number(b.page) || 1);
  return ap >= bp ? a : b;
}

function snapshotHistoricalFrontier(crawl) {
  const previous = crawl?.priorFrontier || null;
  if (!crawl?.currentYear) return previous;
  const current = {
    capturedAt: nowIso(),
    year: Number(crawl.currentYear),
    page: Math.max(1, Number(crawl.currentPage) || 1),
    pageKey: `${Number(crawl.currentYear)}:${Math.max(1, Number(crawl.currentPage) || 1)}`,
    historyUrl: crawl.currentHistoryUrl || null,
    ordersCompleted: Object.keys(crawl.completedOrders || {}).length,
    lastCompletedOrderId: crawl.lastCompletedOrderId || null
  };
  return deeperHistoricalFrontier(current, previous);
}
"""
if old not in s: raise SystemExit('frontier function not found')
p.write_text(s.replace(old,new,1),encoding='utf-8')

t=Path('state-machine-test.js')
x=t.read_text(encoding='utf-8')
needle="assert(secondSessionId && secondSessionId !== firstSessionId, 'second Start must create a new scan session');\n"
insert=needle+"  assert(state.crawl.priorFrontier?.pageKey === '2026:31', 'restarting again near page 1 must retain the deepest prior historical frontier');\n"
if needle not in x: raise SystemExit('second-session assertion marker missing')
t.write_text(x.replace(needle,insert,1),encoding='utf-8')
print('v0.18.15 deepest frontier retention hardened')
