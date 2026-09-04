from pathlib import Path
p = Path('state-machine-test.js')
s = p.read_text(encoding='utf-8')
old = "crawl:{ active:true, phase:'details', years:[2026,2025], currentYear:2026, currentPage:31, currentHistoryUrl:resumeUrl, currentPageOrderIds:[resumeOrderId], currentPageCompleted:1, completedOrders:{ [resumeOrderId]:{at:new Date().toISOString(),year:2026,page:31} }, seenOrders:{ [resumeOrderId]:{year:2026,page:31,pageKey:'2026:31'} }, seenPages:{'2026:31':resumeOrderId} }"
new = "crawl:{ active:true, phase:'details', years:[2026,2025], currentYear:2026, currentPage:31, currentHistoryUrl:resumeUrl, currentPageOrderIds:[resumeOrderId], currentPageCompleted:1, ordersCompleted:1, completedOrders:{ [resumeOrderId]:{at:new Date().toISOString(),year:2026,page:31} }, seenOrders:{ [resumeOrderId]:{year:2026,page:31,pageKey:'2026:31'} }, seenPages:{'2026:31':resumeOrderId} }"
if old not in s:
    raise SystemExit('resume fixture not found')
s = s.replace(old, new, 1)
old_assert = "assert(state.crawl.ordersCompleted === 0, 'overlap refresh must not increment unique-order completion count');"
new_assert = "assert(state.crawl.ordersCompleted === 1, 'overlap refresh must preserve the existing unique-order completion count without adding a second completion');"
if old_assert not in s:
    raise SystemExit('overlap completion assertion not found')
s = s.replace(old_assert, new_assert, 1)
p.write_text(s, encoding='utf-8')
print('v0.18.14 state fixture corrected')
