from pathlib import Path
p=Path('ui-test.js')
s=p.read_text(encoding='utf-8')
old="assert(dashboardJsV01814.includes('resume #${crawl.resumeCount || 1}'), 'scanner checkpoint UI must expose resume diagnostics');"
new="assert(dashboardJsV01814.includes('worker recovery #${crawl.resumeCount || 1}'), 'scanner checkpoint UI must expose internal worker-recovery diagnostics without calling a new session a resume');"
if old not in s: raise SystemExit('old resume UI assertion not found')
p.write_text(s.replace(old,new,1),encoding='utf-8')
print('v0.18.15 worker recovery UI regression updated')
