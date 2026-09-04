from pathlib import Path
p=Path('background-test.js')
s=p.read_text(encoding='utf-8')
old="assert(backgroundSourceV01814.includes(\"ignored: 'crawler-already-processing'\") && backgroundSourceV01814.includes('if (processing) {') && backgroundSourceV01814.includes(\"if (source !== 'auto-amazon')\"), 'Auto-start/manual resume must not requeue an in-flight currentJob in the same service worker');"
new="assert(backgroundSourceV01814.includes(\"ignored: 'crawler-already-processing'\") && backgroundSourceV01814.includes('const livePass =') && backgroundSourceV01814.includes('if (!restart && livePass) return state;'), 'Auto-start/manual Start must not create a second session while a pass is already live');"
if old not in s: raise SystemExit('first v0.18.14 in-flight assertion not found')
s=s.replace(old,new,1)
old2="assert(backgroundSourceV01814.includes(\"if (processing) {\") && backgroundSourceV01814.includes(\"if (source !== 'auto-amazon')\"), 'manual Resume during an in-flight job must clear Stop without requeueing the live currentJob');"
new2="assert(backgroundSourceV01814.includes('const livePass =') && backgroundSourceV01814.includes('if (processing) return state;'), 'newest-session Start must not race or replace an in-flight currentJob in the same service worker');"
if old2 not in s: raise SystemExit('second v0.18.14 in-flight assertion not found')
s=s.replace(old2,new2,1)
p.write_text(s,encoding='utf-8')
print('v0.18.15 static in-flight regressions updated')
