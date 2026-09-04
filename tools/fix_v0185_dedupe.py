from pathlib import Path
p = Path('parser.js')
text = p.read_text(encoding='utf-8')
old = '''    const byKey = new Map();
    for (const entry of candidates) {
      const key = entry.asin || String(entry.itemName || '').toLowerCase();
      const prior = byKey.get(key);
      const score = (entry.asinEvidenceSource ? 100000 : 0) + (entry.strongItemSelector ? 10000 : 0) - entry.textLength;
      const priorScore = prior ? ((prior.asinEvidenceSource ? 100000 : 0) + (prior.strongItemSelector ? 10000 : 0) - prior.textLength) : -Infinity;
      if (!prior || score > priorScore) byKey.set(key, entry);
    }
    return Array.from(byKey.values()).map(({ textLength, strongItemSelector, ...entry }) => entry).slice(0, 30);
'''
new = '''    const deduped = [];
    const scoreEntry = entry => (entry.asinEvidenceSource ? 100000 : 0) + (entry.strongItemSelector ? 10000 : 0) - entry.textLength;
    const nameKey = entry => normalizeText(entry.itemName || '').toLowerCase();
    for (const entry of candidates) {
      const index = deduped.findIndex(prior =>
        (entry.asin && prior.asin && entry.asin === prior.asin) ||
        (nameKey(entry) && nameKey(entry) === nameKey(prior))
      );
      if (index < 0) deduped.push(entry);
      else if (scoreEntry(entry) > scoreEntry(deduped[index])) deduped[index] = entry;
    }
    return deduped.map(({ textLength, strongItemSelector, ...entry }) => entry).slice(0, 30);
'''
if text.count(old) != 1:
    raise SystemExit(f'expected one return-entry dedupe block, got {text.count(old)}')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

t = Path('parser-test.js')
txt = t.read_text(encoding='utf-8')
append = r'''

// v0.18.5 strong+weak duplicate collapse regression
const v185DuplicateAnchor = v185ProductAnchor('B000000003', 'Duplicate Returned Product');
const v185StrongChild = v185FakeNode('Return item\nDuplicate Returned Product\nQuantity: 1\nRefund amount $9.99', null, [v185DuplicateAnchor], {'data-asin':'B000000003'});
const v185BroadParent = v185FakeNode('Return item\nDuplicate Returned Product\nQuantity: 1\nRefund amount $9.99', null, [v185DuplicateAnchor]);
const v185CompositeReturn = {
  querySelectorAll(selector) {
    if (selector === '[data-asin]') return [v185StrongChild];
    if (selector === '.a-box') return [v185BroadParent];
    return [];
  }
};
const v185CollapsedEntries = p.extractReturnItemEntries(v185CompositeReturn);
assert(v185CollapsedEntries.length === 1, 'specific and broad representations of the same return item must collapse to one child');
assert(v185CollapsedEntries[0].asin === 'B000000003' && v185CollapsedEntries[0].asinEvidenceSource === 'return-item-data-asin', 'strong item-specific evidence must win duplicate collapse');
console.log('v0.18.5 duplicate return item collapse regression passed');
'''
if 'v0.18.5 duplicate return item collapse regression passed' not in txt:
    txt += append
t.write_text(txt, encoding='utf-8')
print('v0.18.5 return item dedupe hardened')
