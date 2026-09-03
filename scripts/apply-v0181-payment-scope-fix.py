from pathlib import Path

path = Path('parser.js')
text = path.read_text(encoding='utf-8')

old = "    const addFocused = raw => {\n"
new = "    const addFocused = (raw, allowStandaloneInstrument = false) => {\n"
if old not in text:
    raise SystemExit('addFocused declaration not found')
text = text.replace(old, new, 1)

old = "        if (instrumentRe.test(lines[i])) {\n          addChunk(lines[i]);\n          continue;\n        }\n"
new = "        if (allowStandaloneInstrument && instrumentRe.test(lines[i])) {\n          addChunk(lines[i]);\n          continue;\n        }\n"
if old not in text:
    raise SystemExit('instrument standalone block not found')
text = text.replace(old, new, 1)

replacements = {
    "          addFocused(el.innerText || el.textContent || '');": "          addFocused(el.innerText || el.textContent || '', true);",
    "            try { addFocused(el.getAttribute?.(attr) || ''); } catch (_) {}": "            try { addFocused(el.getAttribute?.(attr) || '', true); } catch (_) {}",
    "                try { addFocused(child.getAttribute?.(attr) || ''); } catch (_) {}": "                try { addFocused(child.getAttribute?.(attr) || '', true); } catch (_) {}",
    "    if (!chunks.length) addFocused(container.innerText || container.textContent || '');": "    if (!chunks.length) addFocused(container.innerText || container.textContent || '', false);"
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f'expected parser text not found: {old}')
    text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
