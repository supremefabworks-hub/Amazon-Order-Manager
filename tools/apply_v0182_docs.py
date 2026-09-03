from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path): return (ROOT / path).read_text(encoding='utf-8')
def write(path, text): (ROOT / path).write_text(text, encoding='utf-8')
def once(text, old, new, label):
    n = text.count(old)
    if n != 1: raise RuntimeError(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

# README
r = read('README.md')
r = once(r,
'''**Current source baseline: v0.18.1 after PR #12 merges.** GitHub is the source of truth and chat sessions are disposable.''',
'''**Current source baseline: v0.18.2 after PR #16 merges.** GitHub is the source of truth and chat sessions are disposable.''',
'README baseline')
r = once(r,
'''4. Root v0.18.0 is the active source after its release merge. The archived v0.16.0 ZIP is recovery material only.''',
'''4. Root v0.18.2 is the active source after PR #16 merges. The archived v0.16.0 ZIP is recovery material only.''',
'README active root')
r = once(r,
'''The extension checks at Chrome startup and every 15 minutes. A missing native host, GitHub/network failure, digest mismatch, invalid package, or failed install leaves the current build running and does not trigger a reload.''',
'''The v0.18.0 -> v0.18.1 unattended update did **not** succeed in live Windows testing, so that earlier path is not considered validated. v0.18.2 checks whenever the MV3 service worker starts, at Chrome startup, manually from the popup, and every 15 minutes. It recreates its important alarm, records updater diagnostics, and reloads synchronously only after the native host confirms a verified newer install. A missing native host, GitHub/network failure, digest mismatch, invalid package, or failed install leaves the current build running and exposes a diagnostic instead of reloading.''',
'README updater live finding')
insert = '''
## v0.18.2 multi-return model

A single Amazon Order ID may contain multiple independent returns. v0.18.2 models them explicitly as:

`order -> return group (rmaId / contractId) -> returned item(s) (itemId)`

- Every real Order Details `View return/refund status` link is bound to its nearest product block rather than to the whole order.
- `itemId` is the stable returned-item identity. `rmaId`/`contractId` identify the return group.
- The Order Details return-link item binding is trusted; a conflicting return-page title/ASIN is flagged for review rather than silently replacing it.
- Provisional Order Details evidence and the later authoritative return page use the same stable child record identity.
- If explicit return links exist, the parser does not add an extra broad order-level provisional return.
- The dashboard renders separate compact `Return X of N` child blocks rather than repeating the full order catalog for every lifecycle.
- Unknown child refund money displays `—`, never `$0.00`.

### Refund accounting

Amazon Order Details remains canonical for the order-level refund amount. Only the explicit standalone `Refund Total` label may populate `canonicalRefundTotal`. Generic refund lifecycle prose is not an order-level total.

The dashboard therefore:

- displays canonical Order Details `Refund Total` when available,
- counts a return-group amount only once,
- sums child item amounts only when item scope is proven,
- flags conflicting group amounts or a child aggregate that exceeds canonical Refund Total,
- uses the canonical expected refund for Needs Review totals when an integrity mismatch is present.

### v0.18.2 updater repair

Because the prior installed channel did not update itself from v0.18.0 to v0.18.1, install the v0.18.2 updater/bootstrap package once on the Windows test PC to repair the channel. The popup now exposes updater current/latest/check/error state and **Check development update now**. The native host writes `updater.log` under the updater install root, supports `--self-test`, and `Install.ps1 -DiagnoseOnly` runs local diagnostics.

A later strictly newer release must update unattended from the repaired v0.18.2 installation before Issue #10 can close.

'''
marker = '## Core v0.17/v0.18 product architecture\n'
if marker not in r: raise RuntimeError('README core marker missing')
r = r.replace(marker, insert + marker, 1)
write('README.md', r)

# PROJECT_HANDOFF
h = read('PROJECT_HANDOFF.md')
h = once(h,
'''**Current source baseline: v0.18.1 after PR #12 merges.** Root source remains the active development source.''',
'''**Current source baseline: v0.18.2 after PR #16 merges.** Root source remains the active development source.''',
'HANDOFF baseline')
section = '''
## v0.18.2 live multi-return + updater reliability release

Live Amazon Business testing exposed two defects after v0.18.1:

1. one Order ID with several independent return-status links was flattened into repeated/blended return rows, including the same wrong product title and an impossible aggregate refund greater than Amazon's canonical Order Details Refund Total;
2. the installed v0.18.0 development copy did not update itself to the published v0.18.1 prerelease.

PR #16 implements v0.18.2.

### Return hierarchy

The durable model is now:

`order -> return group -> returned item(s)`

- Return group identity: Amazon `rmaId` / `contractId` / normalized return token.
- Returned-item identity: Amazon return-link `itemId`, with ASIN/title as supporting evidence.
- Exact Order Details return-link item binding is trusted because it is physically scoped to the returned product block.
- A later authoritative return page enriches lifecycle/refund evidence but may not silently replace conflicting trusted item identity; conflicts set `itemIdentityConflict` and require review.
- Provisional and authoritative captures for the same `returnToken + itemId` intentionally share one record ID.
- Redirects that strip query identity are repaired by carrying the original return-link token/item/contract/RMA hint into a single authoritative child capture.
- Explicit return links suppress the extra broad strong-text provisional return on Order Details.
- Per-order Refresh follows every unique same-order return child separately.

### Refund accounting

Order Details' explicit standalone `Refund Total` is the only canonical order-level refund source. Generic phrases such as `refund has been issued $X` are lifecycle evidence, not canonical order totals.

Return records distinguish item-scoped and return-group-scoped amounts. A group amount is counted once; item amounts are summed only when item scope is proven. The dashboard prefers canonical `Refund Total`, displays unknown amounts as `—`, flags child/group conflicts and aggregates that exceed canonical Refund Total, and uses canonical expected refund for integrity-review totals.

### Updater reliability

The earlier v0.18.0 -> v0.18.1 unattended path failed live and is not considered validated. v0.18.2 therefore:

- initializes the updater whenever the MV3 service worker boots,
- recreates/verifies its 15-minute alarm,
- also checks at Chrome startup and via a popup `Check development update now` action,
- persists current/latest/host/check/install/reload/error diagnostics,
- calls `chrome.runtime.reload()` synchronously after a verified newer install rather than from a delayed timer,
- writes native-host diagnostics to `%LOCALAPPDATA%\\SupremeFabWorks\\AmazonOrderManagerDev\\updater.log`,
- supports native-host `--self-test`,
- adds `Install.ps1 -DiagnoseOnly`, compatible with Windows PowerShell 5.1.

Because the old channel did not self-repair, v0.18.2 requires one explicit updater/bootstrap repair on the Windows test PC. A later version must prove unattended update from v0.18.2 before Issue #10 closes.

Live tracking:

- Issue #7 — Amazon Business product acceptance.
- Issue #10 — unattended updater proof remains open.
- Issue #13 — v0.18.2 architecture/acceptance.
- Issue #15 — v0.18.2 Windows repair + multi-return live retest.

'''
marker = '## v0.18.1 live payment-card regression fix\n'
if marker not in h: raise RuntimeError('HANDOFF v0181 marker missing')
h = h.replace(marker, section + marker, 1)
h = h.replace('- checks at Chrome startup and every 15 minutes,', '- checks on MV3 worker startup, Chrome startup, manually from the popup, and every 15 minutes,', 1)
h = h.replace('- calls `chrome.runtime.reload()` only when the host reports a successful install whose version is strictly newer than the currently running manifest version,', '- calls `chrome.runtime.reload()` synchronously only when the host reports a successful install whose version is strictly newer than the currently running manifest version,', 1)
write('PROJECT_HANDOFF.md', h)

# TESTING
t = read('TESTING.md')
t = once(t,
'''**v0.18.1** is the current source baseline after PR #12 release merge.''',
'''**v0.18.2** is the current source baseline after PR #16 release merge.''',
'TESTING baseline')
t = once(t,
'''node payment-evidence-test.js
node storage-test.js''',
'''node payment-evidence-test.js
node multi-return-test.js
node storage-test.js''',
'TESTING add multi test')
t = once(t,
'''node dev-updater-test.js
node release-test.js''',
'''node dev-updater-test.js
node updater-reliability-test.js
node release-test.js''',
'TESTING updater reliability test')
required_marker = '- recognized card brands and direct masks under Payment/Refund method headings still parse correctly,\n'
required_extra = '''- multiple explicit return links under one Order ID retain distinct `rmaId`/`contractId` return groups and `itemId` child identities,
- exact Order Details return-link item evidence is not replaced by conflicting return-page identity,
- canonical order-level refund is sourced only from the explicit Order Details `Refund Total` label,
- return-group refund values are counted once and unknown refund values remain unknown rather than `$0.00`,
- child/group refund integrity conflicts are flagged instead of inflating the order-level refund,
- updater checks on MV3 worker start, persists status, exposes a popup manual check, and does not depend on a delayed service-worker reload timer,
- native-host logging/self-test and Windows PowerShell 5.1 diagnostics invariants remain intact,
'''
if required_marker not in t: raise RuntimeError('TESTING required marker missing')
t = t.replace(required_marker, required_marker + required_extra, 1)

live_section = '''
## v0.18.2 live repair and multi-return validation — Issue #15

The v0.18.0 -> v0.18.1 unattended update did not occur. Do not treat Issue #10 as passed. After PR #16 merges and `dev-v0.18.2` is published:

1. Close Chrome completely.
2. Download/extract the v0.18.2 `amazon-order-manager-dev-updater.zip` and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Install.ps1
```

3. Confirm the installer diagnostics report extension ID `hhmimkpolikhncnbkkbbabbopbccabcf`, current files version `0.18.2`, native-host self-test success, and an updater log path.
4. Reopen Chrome and confirm version `0.18.2` with the same fixed ID.
5. Open the popup. Confirm updater current/latest/check/error status is visible and **Check development update now** completes without navigating Amazon.
6. Fresh-scan an Order ID with several independent returns. Verify one order row with separate `Return X of N` children, each bound to its actual returned item.
7. Verify the order-level Refund value equals Amazon's explicit Order Details `Refund Total` when present. Unknown child amounts must display `—`; child records must not inflate the order total/refund.
8. Click per-order Refresh and confirm every unique same-order return-status link refreshes independently.
9. Only after v0.18.2 is confirmed installed should a later higher version be released to prove unattended update. Do not manually replace `current` or press Reload for that proof.

Issue #10 stays open until that later automatic update succeeds.

'''
marker = '## Development auto-update live validation — Issue #10\n'
if marker not in t: raise RuntimeError('TESTING updater marker missing')
t = t.replace(marker, live_section + marker, 1)
write('TESTING.md', t)

# NEW_CHAT_PROMPT
n = read('NEW_CHAT_PROMPT.md')
n = once(n,
'''The complete root source baseline is **v0.18.0 after PR #11 merges**.''',
'''The complete root source baseline is **v0.18.2 after PR #16 merges**.''',
'NEW_CHAT baseline') if 'The complete root source baseline is **v0.18.0 after PR #11 merges**.' in n else n
# v0.18.1 branches may already have a newer baseline string.
n = n.replace('The complete root source baseline is **v0.18.1 after PR #12 merges**.', 'The complete root source baseline is **v0.18.2 after PR #16 merges**.', 1)
n = n.replace('Read GitHub Issues **#7** and **#10** plus any newer open issue that supersedes either scope.', 'Read GitHub Issues **#7**, **#10**, **#13**, and **#15** plus any newer open issue that supersedes either scope.', 1)
new_chat_insert = '''
## v0.18.2 durable additions

Multiple returns under one Amazon Order ID must be modeled as `order -> return group -> returned item(s)`. Preserve Amazon return `rmaId`/`contractId` group identity and `itemId` child identity. Bind each return-status link to its nearest Order Details product block. Exact Order Details item binding is trusted; a conflicting later return-page identity must be flagged for review, not silently substituted.

Only the explicit standalone Order Details `Refund Total` is canonical for the order-level refund. Return/group amounts must be counted once, unknown refund money is `—`, and any child/group aggregate that exceeds the canonical refund is an integrity failure requiring review.

The prior v0.18.0 -> v0.18.1 automatic update failed in live Windows testing. v0.18.2 adds worker-start checks, observable popup updater status/manual check, synchronous reload after verified install, native-host file logging/self-test, and installer diagnostics. v0.18.2 requires one explicit Windows bootstrap repair. A later release must prove unattended update before Issue #10 closes.

'''
marker = '## Amazon product contract\n'
if marker in n and new_chat_insert.strip() not in n:
    n = n.replace(marker, new_chat_insert + marker, 1)
write('NEW_CHAT_PROMPT.md', n)

print('v0.18.2 docs updated for PR #16')
