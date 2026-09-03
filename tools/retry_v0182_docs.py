from pathlib import Path

path = Path(__file__).with_name('apply_v0182_docs.py')
text = path.read_text(encoding='utf-8')
old = """t = once(t,
'''node payment-evidence-test.js
node storage-test.js''',
'''node payment-evidence-test.js
node multi-return-test.js
node storage-test.js''',
'TESTING add multi test')"""
new = """t = once(t,
'''node parser-test.js
node storage-test.js''',
'''node parser-test.js
node payment-evidence-test.js
node multi-return-test.js
node storage-test.js''',
'TESTING add payment/multi tests')"""
if text.count(old) != 1:
    raise RuntimeError(f'expected one stale TESTING matcher, found {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('corrected v0.18.2 documentation matcher')
