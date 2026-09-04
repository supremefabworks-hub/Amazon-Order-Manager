from pathlib import Path
import json

R=Path('.')
def read(p): return (R/p).read_text(encoding='utf-8')
def write(p,s): (R/p).write_text(s,encoding='utf-8')
def once(s,a,b,label):
    n=s.count(a)
    if n!=1: raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return s.replace(a,b,1)

p=read('parser.js')
p=once(p,
"      shipped: { done: shipped, date: shipped ? findMilestoneDate(normalized, ['Dropped off', 'Drop off', 'Return shipped', 'Shipped']) : null },\n      refundIssued: { done: refundIssued, date: refundIssued ? findMilestoneDate(normalized, ['Refund issued']) : null },",
"      shipped: { done: shipped, date: shipped ? findMilestoneDate(normalized, ['Dropped off', 'Drop off', 'Return shipped', 'Shipped']) : null },\n      received: { done: received, date: received ? findMilestoneDate(normalized, ['Return received', 'Received']) : null },\n      refundIssued: { done: refundIssued, date: refundIssued ? findMilestoneDate(normalized, ['Refund issued']) : null },",
'parser explicit received')
start=p.index('  function extractCompletedReturnMilestonesFromDom(container) {')
end=p.index('\n\n  function applyDomReturnMilestones(record, container) {',start)
new=r'''  function extractCompletedReturnMilestonesFromDom(container) {
    const done = { started: false, shipped: false, received: false, refundIssued: false, credited: false };
    if (!container?.querySelectorAll) return done;
    let checks = [];
    try { checks = Array.from(container.querySelectorAll('img[src*="milestone_checkmark" i], img[data-src*="milestone_checkmark" i], img[alt*="checkmark" i]')); } catch (_) {}
    if (!checks.length) return done;
    const stageForLabel = line => {
      const value = normalizeText(line).toLowerCase();
      if (value === 'initiated' || value === 'return initiated' || value === 'return started') return 'started';
      if (value === 'drop off' || value === 'dropped off' || value === 'return shipped') return 'shipped';
      if (value === 'return received') return 'received';
      if (value === 'refund issued') return 'refundIssued';
      if (value === 'refund credited' || value === 'credited') return 'credited';
      return null;
    };
    const text = normalizeText(container.innerText || container.textContent || '');
    const ordered = [];
    for (const stage of text.split('\n').map(stageForLabel).filter(Boolean)) if (ordered.at(-1) !== stage) ordered.push(stage);
    const canonical = ['started','shipped','received','refundIssued','credited'];
    const prefixUsable = ordered.length >= 2 && ordered.every((stage,index) => canonical[index] === stage);
    if (prefixUsable && checks.length <= ordered.length) {
      for (let i=0;i<checks.length;i+=1) done[ordered[i]] = true;
    } else {
      for (const check of checks) {
        let current = check.parentElement || null;
        for (let depth=0; current && depth<5; depth+=1, current=current.parentElement) {
          const local = normalizeText(current.innerText || current.textContent || '');
          if (!local || local.length > 500) continue;
          const labels = Array.from(new Set(local.split('\n').map(stageForLabel).filter(Boolean)));
          if (labels.length === 1) { done[labels[0]] = true; break; }
          if (labels.length > 1) break;
        }
      }
    }
    if (done.credited) done.refundIssued = true;
    if (done.refundIssued) done.received = true;
    if (done.received) done.shipped = true;
    if (done.shipped) done.started = true;
    return done;
  }'''
p=p[:start]+new+p[end:]
p=once(p,
"    for (const key of ['started', 'shipped', 'refundIssued', 'credited']) {\n      const domKey = key;\n      if (!dom[domKey]) continue;\n      milestones[key] = { ...(milestones[key] || {}), done: true };\n    }\n    if (dom.received) milestones.receivedByDom = true;",
"    for (const key of ['started', 'shipped', 'received', 'refundIssued', 'credited']) {\n      if (!dom[key]) continue;\n      const labels = key === 'started' ? ['Initiated','Return initiated','Return started'] : key === 'shipped' ? ['Dropped off','Drop off','Return shipped','Shipped'] : key === 'received' ? ['Return received','Received'] : key === 'refundIssued' ? ['Refund issued'] : ['Refund credited','Credited'];\n      milestones[key] = { ...(milestones[key] || {}), done: true, date: milestones[key]?.date || findMilestoneDate(normalizeText(container.innerText || container.textContent || ''), labels) || null };\n    }",
'apply DOM received')
p=once(p,"    extractStatusText,\n    parseTextRecord,","    extractStatusText,\n    extractCompletedReturnMilestonesFromDom,\n    parseTextRecord,",'export dom milestones')
write('parser.js',p)

s=read('storage.js')
s=once(s,
"  function isCreditConfirmed(record) {\n    return Boolean(record && (returnStageRank(record) >= RETURN_STAGE_RANK.credited || isBankCreditConfirmed(record)));\n  }",
"  function isCreditConfirmed(record) {\n    return Boolean(record && (returnStageRank(record) >= RETURN_STAGE_RANK.credited || isBankCreditConfirmed(record)));\n  }\n\n  function hasAmazonBankConflict(record) {\n    return Boolean(record && isBankCreditConfirmed(record) && returnStageRank(record) < RETURN_STAGE_RANK.refund_issued);\n  }",
'bank conflict helper')
s=once(s,
"    if (record.itemIdentityConflict) return true;\n    if (record.manualState === 'reconciled' || isCreditConfirmed(record)) return false;",
"    if (record.itemIdentityConflict) return true;\n    if (record.manualState === 'reconciled') return false;\n    if (hasAmazonBankConflict(record)) return true;\n    if (isCreditConfirmed(record)) return false;",
'needs review bank conflict')
start=s.index('  function returnProgress(record) {')
end=s.index('\n\n  function mergeReturnMilestones',start)
new=r'''  function returnProgress(record) {
    const stage = getReturnStage(record) || 'unknown';
    const rank = returnStageRank(stage);
    const bankConfirmed = isBankCreditConfirmed(record);
    const amazonCredited = rank >= RETURN_STAGE_RANK.credited;
    return {
      stage, rank,
      percent: rank >= 5 ? 100 : rank >= 4 ? 80 : rank >= 3 ? 60 : rank >= 2 ? 40 : rank >= 1 ? 20 : 0,
      started: rank >= 1,
      shipped: rank >= 2,
      shippedOrReceived: rank >= 2,
      received: rank >= 3,
      refundIssued: rank >= 4,
      credited: amazonCredited,
      amazonCredited,
      bankCreditConfirmed: bankConfirmed,
      bankVerificationStatus: bankVerificationStatus(record),
      amazonBankConflict: hasAmazonBankConflict(record),
      financialCreditConfirmed: amazonCredited || bankConfirmed,
      refunded: rank >= 4,
      milestones: record?.returnMilestones || null
    };
  }'''
s=s[:start]+new+s[end:]
s=once(s,"    for (const key of ['started', 'shipped', 'refundIssued', 'credited']) {","    for (const key of ['started', 'shipped', 'received', 'refundIssued', 'credited']) {",'merge received')
s=once(s,"    isCreditConfirmed,\n    expectedCreditDate,","    isCreditConfirmed,\n    hasAmazonBankConflict,\n    expectedCreditDate,",'export conflict')
write('storage.js',s)

d=read('dashboard.js')
d=once(d,
"      const allCredited = hasReturn && returnRecords.every(r => storage.isCreditConfirmed(r));\n      const allIssued = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.refund_issued);",
"      const allAmazonCredited = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.credited);\n      const allIssued = hasReturn && ranks.every(rank => rank >= storage.RETURN_STAGE_RANK.refund_issued);\n      const bankAmazonConflict = hasReturn && returnRecords.some(r => storage.hasAmazonBankConflict(r));",
'row bank separation')
d=once(d,"returnRecords.some(r => storage.needsCreditReview(r)) || refundAmountMismatch || itemIdentityConflict || groupAmountConflict || strongUnmatchedReturnIdentity","returnRecords.some(r => storage.needsCreditReview(r)) || refundAmountMismatch || itemIdentityConflict || groupAmountConflict || strongUnmatchedReturnIdentity || bankAmazonConflict",'review conflict')
d=once(d,"        else if (strongUnmatchedReturnIdentity) statusLabel = 'Returned item needs matching';\n        else {","        else if (strongUnmatchedReturnIdentity) statusLabel = 'Returned item needs matching';\n        else if (bankAmazonConflict) statusLabel = 'Bank/Amazon status conflict';\n        else {",'conflict label')
d=once(d,"      } else if (allCredited) { stateKey = 'credited'; statusLabel = 'Credited'; }","      } else if (allAmazonCredited) { stateKey = 'credited'; statusLabel = 'Amazon credited'; }",'amazon credited only')
d=once(d,"        refundAmountMismatch, itemIdentityConflict, groupAmountConflict, strongUnmatchedReturnIdentity,","        refundAmountMismatch, itemIdentityConflict, groupAmountConflict, strongUnmatchedReturnIdentity, bankAmazonConflict,",'row conflict field')
start=d.index('  function lifecycleMarkup(group, index, totalGroups) {')
end=d.index('\n  function legacyReturnProgressMarkup',start)
new=r'''  function lifecycleMarkup(group, index, totalGroups) {
    const record = group.representative;
    const progress = storage.returnProgress(record);
    const expectedCredit = !progress.amazonCredited ? storage.expectedCreditDate(record) || '' : '';
    const verificationRecord = group.records.find(r => r.bankVerification) || record;
    const verification = verificationRecord.bankVerification || null;
    const steps = [
      ['started', 'Initiated', progress.started, milestoneDate(record, 'started')],
      ['shipped', 'Dropped off', progress.shipped, milestoneDate(record, 'shipped')],
      ['received', 'Return received', progress.received, milestoneDate(record, 'received')],
      ['refundIssued', 'Refund issued', progress.refundIssued, milestoneDate(record, 'refundIssued')],
      ['credited', progress.amazonCredited ? 'Refund credited' : (expectedCredit ? `Expected ${expectedCredit}` : 'Refund credited'), progress.amazonCredited, milestoneDate(record, 'credited')]
    ];
    const items = group.itemNames.length ? group.itemNames.join(' · ') : 'Returned item pending authoritative scan';
    let verificationMarkup = '';
    if (progress.amazonBankConflict) {
      verificationMarkup = `<div class="bank-match bank-match-review"><strong>Bank/Amazon conflict</strong><span>Bank credit evidence exists before Amazon shows Refund issued. Verify the bank match.</span></div>`;
    } else if (verification) {
      if (verification.status === 'confirmed') {
        const details = [verification.matchedAmount != null ? money(verification.matchedAmount) : '', verification.postedDate || '', verification.accountLast4 ? `•••• ${verification.accountLast4}` : ''].filter(Boolean).join(' · ');
        verificationMarkup = `<div class="bank-match bank-match-confirmed"><strong>Bank confirmed</strong>${details ? `<span>${esc(details)}</span>` : ''}</div>`;
      } else if (verification.status === 'ambiguous' || verification.status === 'needs_review') {
        verificationMarkup = `<div class="bank-match bank-match-review"><strong>Bank match needs review</strong><span>${esc(verification.reason || 'Multiple plausible credits.')}</span></div>`;
      }
    }
    const warnings = [group.itemIdentityConflict ? 'Item identity conflict' : '', group.amountConflict ? 'Refund amount conflict' : ''].filter(Boolean).join(' · ');
    return `<div class="return-track-item compact-return-track">
      <div class="return-track-title">Return ${index}${totalGroups > 1 ? ` of ${totalGroups}` : ''} · ${esc(items)}</div>
      <div class="return-track-meta"><span>${esc(stageLabel(storage.getReturnStage(record)))}</span><strong>${money(group.amount)}</strong></div>
      ${warnings ? `<div class="muted tiny">${esc(warnings)}</div>` : ''}
      <div class="lifecycle lifecycle-lineitem lifecycle-five">
        <div class="lifecycle-line"><span style="width:${progress.percent}%"></span></div>
        ${steps.map(step => `<div class="life-step ${step[2] ? 'done' : ''}"><small>${esc(step[3] || '')}</small><i>${step[2] ? '✓' : ''}</i><span>${esc(step[1])}</span></div>`).join('')}
      </div>
      ${verificationMarkup}
    </div>`;
  }
'''
d=d[:start]+new+d[end:]
d=once(d,"    const credited = rows.filter(r => r.hasReturn && r.returns.every(ret => storage.isCreditConfirmed(ret)));","    const bankCredited = rows.filter(r => r.hasReturn && r.returns.every(ret => storage.isBankCreditConfirmed(ret)));",'bank stat')
d=once(d,"<div class=\"stat\"><span>Bank credited</span><strong>${credited.length}</strong>","<div class=\"stat\"><span>Bank credited</span><strong>${bankCredited.length}</strong>",'bank stat var')
d=once(d,"    if (row.stateKey === 'credited') return 'Credited';","    if (row.stateKey === 'credited') return 'Amazon credited';",'credited badge')
d=once(d,
"      const bankConfirmed = row.hasReturn && row.returns.length && row.returns.every(ret => storage.isCreditConfirmed(ret));\n      const anyIssued = row.hasReturn && row.returns.some(ret => storage.returnStageRank(ret) >= storage.RETURN_STAGE_RANK.refund_issued);\n      const financialState = bankConfirmed\n        ? '<span class=\"credit-state credit-confirmed\">Bank confirmed</span>'\n        : anyIssued\n          ? '<span class=\"credit-state credit-pending\">Credit pending</span>'\n          : '';",
"      const bankConfirmed = row.hasReturn && row.returns.length && row.returns.every(ret => storage.isBankCreditConfirmed(ret));\n      const anyIssued = row.hasReturn && row.returns.some(ret => storage.returnStageRank(ret) >= storage.RETURN_STAGE_RANK.refund_issued);\n      const financialState = row.bankAmazonConflict\n        ? '<span class=\"credit-state credit-pending\">Bank/Amazon conflict</span>'\n        : bankConfirmed\n          ? '<span class=\"credit-state credit-confirmed\">Bank confirmed</span>'\n          : anyIssued\n            ? '<span class=\"credit-state credit-pending\">Credit pending</span>'\n            : '';",
'financial state separate')
write('dashboard.js',d)

css=read('ui.css')
css += '\n\n/* v0.18.8 five-stage Amazon return lifecycle. Bank verification renders separately. */\n.lifecycle-five { grid-template-columns: repeat(5, minmax(0, 1fr)); }\n.lifecycle-five .lifecycle-line { left: 7%; right: 7%; }\n'
write('ui.css',css)

pt=read('parser-test.js')
pt += r'''

// v0.18.8 Breville: three checkmarks mean Initiated, Dropped off, Return received only.
const v0188BrevilleText = `Aug 7\nInitiated\nAug 31\nDropped off\nSep 2\nReturn received\nSep 10\nRefund issued\nSep 17\nRefund credited\nYour return was received`;
const v0188Timeline = { innerText:v0188BrevilleText, textContent:v0188BrevilleText, querySelectorAll(selector){ return selector.includes('milestone_checkmark') ? [{},{},{}] : []; } };
const v0188Dom = p.extractCompletedReturnMilestonesFromDom(v0188Timeline);
assert(v0188Dom.started && v0188Dom.shipped && v0188Dom.received, 'three milestone checkmarks must complete first three Amazon stages');
assert(!v0188Dom.refundIssued && !v0188Dom.credited, 'future unchecked Refund issued/credited labels must stay incomplete');
const v0188Parsed = p.parseTextRecord(v0188BrevilleText, '113-1426991-3716216', {pageType:'return', url:'https://www.amazon.com/spr/returns/prep?orderId=113-1426991-3716216'});
assert(v0188Parsed.returnStage === 'received', 'Breville affirmative received evidence must classify as received');
assert(v0188Parsed.returnMilestones.received.done === true, 'received milestone must be explicit');
assert(v0188Parsed.returnMilestones.refundIssued.done === false && v0188Parsed.returnMilestones.credited.done === false, 'future refund labels must not complete');
console.log('v0.18.8 Breville lifecycle regressions passed');
'''
write('parser-test.js',pt)

st=read('storage-test.js')
needle="  console.log('storage tests passed');"
insert=r'''  const bankBeforeIssued = { recordId:'return:113-1426991-3716216:breville:item-jmpgppooriprsup', recordType:'return', orderId:'113-1426991-3716216', returnStage:'received', status:'returned_pending_refund', statusText:'Your return was received', returnMilestones:{stage:'received',started:{done:true,date:'Aug 7'},shipped:{done:true,date:'Aug 31'},received:{done:true,date:'Sep 2'},refundIssued:{done:false,date:null},credited:{done:false,date:null}}, bankVerification:{status:'confirmed',matchedAmount:700.36,postedDate:'2026-09-03'} };
  assert(s.getReturnStage(bankBeforeIssued) === 'received', 'bank confirmation must not alter Amazon stage');
  assert(s.returnProgress(bankBeforeIssued).received && !s.returnProgress(bankBeforeIssued).refundIssued && !s.returnProgress(bankBeforeIssued).amazonCredited, 'Amazon lifecycle must remain received');
  assert(s.returnProgress(bankBeforeIssued).bankCreditConfirmed, 'bank evidence remains separately visible');
  assert(s.hasAmazonBankConflict(bankBeforeIssued), 'bank credit before Amazon refund-issued must be conflict');
  assert(s.needsCreditReview(bankBeforeIssued), 'bank/Amazon conflict must need review');

'''+needle
st=once(st,needle,insert,'storage v0188')
write('storage-test.js',st)

ut=read('ui-test.js')
ut += r'''

const dashboardV0188 = fs.readFileSync(__dirname + '/dashboard.js','utf8');
const storageV0188 = fs.readFileSync(__dirname + '/storage.js','utf8');
const cssV0188 = fs.readFileSync(__dirname + '/ui.css','utf8');
assert(dashboardV0188.includes("['received', 'Return received'"), 'dashboard must render Return received as its own stage');
assert(dashboardV0188.includes('storage.isBankCreditConfirmed(ret)'), 'Bank credited must use bank evidence only');
assert(dashboardV0188.includes('Bank/Amazon conflict'), 'dashboard must expose bank/Amazon conflict');
assert(dashboardV0188.includes("statusLabel = 'Amazon credited'"), 'bank match must not promote Amazon row to credited');
assert(storageV0188.includes('function hasAmazonBankConflict'), 'storage must separate Amazon/bank states');
assert(cssV0188.includes('repeat(5, minmax(0, 1fr))'), 'lifecycle must use five Amazon stages');
console.log('v0.18.8 Amazon/bank separation UI regressions passed');
'''
write('ui-test.js',ut)

for fn in ['manifest.json','package.json']:
    obj=json.loads(read(fn)); obj['version']='0.18.8';
    if fn=='manifest.json': obj['version_name']='0.18.8'
    write(fn,json.dumps(obj,indent=2)+'\n')

rm=read('README.md')
rm=rm.replace('**Current source baseline: v0.18.7 candidate for Issue #25.**','**Current source baseline: v0.18.8 candidate for Issue #27.**',1)
rm += '\n\n## v0.18.8 Amazon lifecycle / bank separation\nAmazon return lifecycle is five explicit stages: Initiated -> Dropped off -> Return received -> Refund issued -> Refund credited. Amazon milestone checkmarks complete the leading timeline stages; future unchecked labels remain pending. Bank verification is independent and never promotes Amazon stage. A bank-confirmed credit before Amazon shows Refund issued is a review conflict.\n'
write('README.md',rm)
write('PROJECT_HANDOFF.md',read('PROJECT_HANDOFF.md')+'\n\n## v0.18.8 live return-state fix\n- Breville `113-1426991-3716216`: Amazon shows completed Initiated Aug 7, Dropped off Aug 31, Return received Sep 2; Refund issued Sep 10 and Refund credited Sep 17 are future unchecked labels.\n- v0.18.8 adds explicit Return received UI/storage, ordered-prefix milestone checkmark interpretation, and strict separation of Amazon lifecycle vs bank verification.\n- Bank-before-refund-issued becomes Needs Review instead of Credited. Issue #27 tracks live acceptance.\n')
write('TESTING.md',read('TESTING.md')+'\n\n## v0.18.8 live acceptance\n1. Let updater install v0.18.8 and run a fresh scan.\n2. Breville `113-1426991-3716216` must show Initiated Aug 7, Dropped off Aug 31, Return received Sep 2 complete; Refund issued Sep 10 and Refund credited Sep 17 incomplete until Amazon checks them.\n3. Row/group label must be Return received, not Credited.\n4. Bank confirmation stays separate; bank-before-issued shows Bank/Amazon conflict / Needs Review.\n')
write('NEW_CHAT_PROMPT.md',read('NEW_CHAT_PROMPT.md')+'\n\n### v0.18.8 durable addition\nAmazon return lifecycle and bank credit verification are independent. Render five Amazon stages including Return received. Future/static labels do not complete stages; milestone checkmarks are leading-stage evidence. Bank evidence never promotes Amazon stage; bank-before-refund-issued is a review conflict. Issue #27 tracks acceptance.\n')
print('v0.18.8 patch applied')
