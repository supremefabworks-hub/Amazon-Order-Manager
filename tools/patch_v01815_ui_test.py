from pathlib import Path
p=Path('ui-test.js')
s=p.read_text(encoding='utf-8')
old="assert(dashboard.includes('orders complete'), 'dashboard checkpoint must include terminal-complete orders without calling them Detail captures');"
new="assert(dashboard.includes('unique orders stored'), 'dashboard checkpoint must count terminal-complete and canonical orders without calling every completion a Detail capture');"
if old not in s: raise SystemExit('old checkpoint wording assertion not found')
p.write_text(s.replace(old,new,1),encoding='utf-8')
print('v0.18.15 scanner wording regression updated')
