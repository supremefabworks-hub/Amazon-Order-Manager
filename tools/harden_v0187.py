from pathlib import Path
ROOT=Path('.')
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def write(p,t): (ROOT/p).write_text(t,encoding='utf-8')
def once(t,a,b,label):
    n=t.count(a)
    if n!=1: raise RuntimeError(f'{label}: expected 1 got {n}')
    return t.replace(a,b,1)

p=read('parser.js')
p=once(p,
'''        itemName: existing.itemName || candidate.itemName,
        quantity: existing.quantity ?? candidate.quantity,''',
'''        itemName: String(candidate.itemName || '').length > String(existing.itemName || '').length ? candidate.itemName : existing.itemName,
        quantity: existing.quantity ?? candidate.quantity,''',
'prefer fuller canonical product title')
write('parser.js',p)

d=read('dashboard.js')
d=once(d,
'''        refundAmountMismatch, itemIdentityConflict, groupAmountConflict,
        cardLast4:''',
'''        refundAmountMismatch, itemIdentityConflict, groupAmountConflict, strongUnmatchedReturnIdentity,
        cardLast4:''',
'persist strong unmatched flag')
d=once(d,
'''    if (row.refundAmountMismatch || row.itemIdentityConflict || row.groupAmountConflict) {''',
'''    if (row.refundAmountMismatch || row.itemIdentityConflict || row.groupAmountConflict || row.strongUnmatchedReturnIdentity) {''',
'needs review dollars include unmatched strong item')
write('dashboard.js',d)

t=read('parser-test.js')
t += r'''

// v0.18.7 DOM milestone evidence: only the stage with a real Amazon checkmark completes.
const v0187InitiatedRow = { innerText:'Aug 31\nInitiated', textContent:'Aug 31\nInitiated', parentElement:null };
const v0187Check = { parentElement:v0187InitiatedRow };
const v0187MilestoneDom = { querySelectorAll(selector) { return selector.includes('milestone_checkmark') ? [v0187Check] : []; } };
const v0187DomDone = p.extractCompletedReturnMilestonesFromDom(v0187MilestoneDom);
assert(v0187DomDone.started === true, 'Amazon checkmark next to Initiated must complete Initiated');
assert(v0187DomDone.shipped === false && v0187DomDone.received === false && v0187DomDone.refundIssued === false, 'one Initiated checkmark must not spill into later static labels');
'''
write('parser-test.js',t)

s=read('storage-test.js')
s=once(s,
'''  const retBase = {''',
'''  const policyOnlyStage = s.getReturnStage({ recordType:'return', statusText:'Drop off your return by Sep 8\\nWe will issue your refund within 30 days from the time you have dropped off your return.\\nDrop off\\nReturn received\\nRefund issued\\nRefund credited' });
  assert(policyOnlyStage === 'started', 'storage fallback must not promote future/policy/static return text beyond Initiated');

  const retBase = {''',
'storage false-milestone regression')
write('storage-test.js',s)

u=read('ui-test.js')
u += "\nassert(dashboard.includes('row.strongUnmatchedReturnIdentity'), 'strong unmatched returned items must contribute canonical expected refund to Needs Review dollars');\n"
write('ui-test.js',u)
print('v0.18.7 review hardening applied')
