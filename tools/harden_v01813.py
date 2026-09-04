from pathlib import Path

p = Path('background.js')
s = p.read_text(encoding='utf-8')
old = """    } finally {
      processing = false;
      const state = ensureCrawl(await getState().catch(() => defaultState()));
      if (!state.paused && state.queue?.length) scheduleSoon(randomBetween(75, 250));
    }
"""
new = """    } finally {
      try { await chrome.tabs.remove(tabId); } catch (_) {}
      processing = false;
      const state = ensureCrawl(await getState().catch(() => defaultState()));
      if (!state.paused && state.queue?.length) scheduleSoon(randomBetween(75, 250));
    }
"""
if s.count(old) != 1:
    raise SystemExit(f'cleanup block matches={s.count(old)}')
p.write_text(s.replace(old, new, 1), encoding='utf-8')

t = Path('background-test.js')
x = t.read_text(encoding='utf-8')
marker = "console.log('v0.18.13 reset-refresh background regressions passed');"
insert = "assert(backgroundSourceV01813.includes('await chrome.tabs.remove(tabId)'), 'Reset & Refresh must close its temporary inactive Amazon tab before releasing the lock');\n"
if marker not in x:
    raise SystemExit('v0.18.13 test marker missing')
x = x.replace(marker, insert + marker, 1)
t.write_text(x, encoding='utf-8')

print('v0.18.13 cleanup hardening applied')
