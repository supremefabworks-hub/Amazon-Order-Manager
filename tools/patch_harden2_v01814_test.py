from pathlib import Path
p = Path('background-test.js')
s = p.read_text(encoding='utf-8')
old = "assert(backgroundSourceV01814.includes(\"ignored: 'crawler-already-processing'\") && backgroundSourceV01814.includes('if (processing && !state.paused) return state;'), 'Auto-start/manual resume must not requeue an in-flight currentJob in the same service worker');"
new = "assert(backgroundSourceV01814.includes(\"ignored: 'crawler-already-processing'\") && backgroundSourceV01814.includes('if (processing) {') && backgroundSourceV01814.includes(\"if (source !== 'auto-amazon')\"), 'Auto-start/manual resume must not requeue an in-flight currentJob in the same service worker');"
if old not in s:
    raise SystemExit('old in-flight assertion not found')
p.write_text(s.replace(old, new, 1), encoding='utf-8')
print('v0.18.14 in-flight resume regression updated')
