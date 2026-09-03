# Amazon Order Manager validation

## Current test target

**v0.18.1** is the current source baseline after PR #12 release merge. It preserves the v0.17 Amazon crawler/return contract, retains the verified local development auto-update channel, and fixes the live false payment-card last-four contamination found in v0.18.0.

Two independent live boundaries remain:

- Issue #7: live Amazon Business acceptance of crawler/details/returns/UI behavior.
- Issue #10: live Windows bootstrap plus one subsequent automatic development update.

Automated regression coverage must pass before packaging or merging.

## Automated checks

Run from the repository root:

```bash
npm test
```

This executes:

```text
node parser-test.js
node storage-test.js
node background-test.js
node state-machine-test.js
node reconciliation-test.js
node ui-test.js
node dev-updater-test.js
node release-test.js
```

Required automated coverage includes:

- real Order Details URLs only; no synthesized canonical URLs,
- all visible Order IDs remain in the history fingerprint even if a detail link is missing,
- a missing real `View order details` URL stops managed crawl,
- pagination only advances after a changed non-empty visible Order-ID fingerprint,
- URL/hash changes alone are not accepted as pagination progress,
- Order Details must match its URL Order ID and contain order date, total, and at least one item before `Detailed`,
- `Return or replace items` availability alone does not create a return,
- future credit dates remain ETAs and do not become completed credits,
- return lifecycle merge is monotonic,
- bundled/multi-item returns can produce separate item-level records and expected refund values,
- authoritative return capture replaces provisional bundled-item contamination,
- payment last-four parsing is restricted to payment-method/payment-information evidence,
- generic Amazon DOM `card` layout containers, gift-card values, and unrelated masked numbers cannot populate card last-four,
- recognized card brands and direct masks under Payment/Refund method headings still parse correctly,
- manifest version change wipes development ledger/crawl state,
- dashboard has fixed `Details / Credit / Reset / Refresh` actions and no horizontal order scrolling,
- bank reconciliation bridge remains narrow,
- manifest/package versions stay identical,
- the development manifest key resolves to fixed extension ID `hhmimkpolikhncnbkkbbabbopbccabcf`,
- native updater host/origin/protocol constants remain consistent,
- the extension reloads only after a strictly newer successful native-host install result,
- missing/invalid native-host responses fail closed without disrupting the extension,
- CI emits the extension ZIP, SHA-256 sidecar, one-time Windows updater package, and versioned development-release contract.

## Development auto-update live validation — Issue #10

The Windows native host cannot be fully validated by Linux GitHub Actions. Complete this on the actual Windows test PC after v0.18.0 is merged and `dev-v0.18.0` exists.

### A. Verify the release

1. Confirm GitHub Actions for the v0.18.0 `main` commit is green.
2. Confirm prerelease `dev-v0.18.0` exists.
3. Confirm it contains:
   - `amazon-order-manager.zip`
   - `amazon-order-manager.zip.sha256`
   - `amazon-order-manager-dev-updater.zip`
4. Do not install a package if the release is missing the checksum sidecar.

### B. One-time Windows bootstrap

1. Download and extract `amazon-order-manager-dev-updater.zip`.
2. Open PowerShell in that extracted directory.
3. Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
```

4. Confirm the installer exits successfully and prints:

```text
Extension ID: hhmimkpolikhncnbkkbbabbopbccabcf
```

5. Confirm this directory exists and contains `manifest.json`:

```text
%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev\current
```

6. Open `chrome://extensions`, enable Developer mode, remove the old unpacked Amazon Order Manager copy, click **Load unpacked**, and select that exact `current` directory.
7. Confirm Chrome reports extension ID `hhmimkpolikhncnbkkbbabbopbccabcf` and version `0.18.0`.
8. Confirm the normal popup/dashboard loads.
9. Because active development resets data on a version change, confirm the test ledger/crawl state starts clean as expected.
10. Confirm no Amazon credentials, cookies, bank credentials, or financial-provider tokens were requested by the installer/native host.

### C. Native host fail-safe check

After v0.18.0 is loaded:

1. Confirm normal Amazon extension operation is unaffected while no update is available.
2. Allow at least one update check or invoke the documented manual update-check message from development diagnostics if needed.
3. Confirm no page navigation or crawl job is created merely by the updater alarm.
4. If GitHub/network access is temporarily unavailable, confirm the current extension continues to run and does not reload.

### D. Prove a real automatic update

A second, higher version is required to prove the end-to-end update path.

1. Make the next user-testable revision with both manifest/package versions strictly greater than `0.18.0`.
2. Merge only after PR CI passes.
3. Confirm main CI publishes `dev-v<new version>` with ZIP + SHA-256 sidecar.
4. Leave Chrome running with the unpacked `current` folder loaded; do not manually copy/reload files.
5. At Chrome startup or within the 15-minute check interval, confirm the updater installs the newer verified package.
6. Confirm Chrome reloads the extension automatically.
7. Confirm `chrome://extensions` and the extension UI show the new version.
8. Confirm `%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev\previous` contains the prior successful build.
9. Confirm normal dashboard and Amazon behavior still work after reload.

Issue #10 stays open until A-D pass on the Windows test PC.

## Required live Amazon Business validation — Issue #7

Perform this acceptance pass against the real Amazon Business account. v0.18 must behave identically to the v0.17 authoritative Amazon contract.

### Clean start

1. Confirm `chrome://extensions` shows the current v0.18+ development version.
2. Confirm the development version reset started with a clean ledger/crawl state for this build.
3. Keep Amazon Business signed in normally. Do not provide credentials to the extension or repository.

### Strict crawl sequence

1. Start a lifetime/full crawl at the newest available year.
2. On newest-year page 1, record the visible Amazon Order IDs.
3. Confirm every visible unique Order ID gets a real captured `View order details` URL.
4. Confirm the crawler completes canonical Order Details for every order on page 1 before attempting page 2.
5. Confirm `Detailed` appears only after successful canonical capture.
6. Confirm the crawler activates Amazon's real page-2 control or taught Business pager route.
7. Confirm page 2 counts as progress only after its visible Order-ID fingerprint differs from page 1.
8. Repeat through every remaining page in that year.
9. Confirm the crawler does not switch to an older year while an enabled next-page control exists.
10. On the final page of the year, confirm it switches to the next older year only after no valid next page remains.
11. Confirm overlapping orders between pages are counted as overlap evidence and are not duplicated in the ledger.
12. If Amazon repeats the same visible Order IDs after a next-page attempt, confirm the crawler stops/retries the same checkpoint instead of claiming progress.
13. If any visible order lacks a real `View order details` link, confirm the crawler stops rather than fabricating a URL.

### Canonical Order Details

For a sample of ordinary and bundled orders:

1. Click `Details` and verify the stored URL is the same real Amazon Order Details route captured from history.
2. Verify order date, order total, and item title(s) match Amazon.
3. Verify `Detailed` is absent when any required canonical field cannot be captured.
4. Verify payment-card last four matches Amazon's Payment method / Payment information section only.
5. Verify unrelated four-digit values elsewhere on the page are ignored.

### Return detection and lifecycle

Use at least one ordinary non-returned order that offers `Return or replace items`, one in-progress return, one issued refund, one bundled partial return if available, and one Order ID with multiple returns if available.

Verify:

1. The ordinary order remains a normal order even though `Return or replace items` exists.
2. A real `/spr/returns/prep` link is associated only with the same Amazon Order ID.
3. In-progress returns do not show `Refund issued` unless Amazon provides affirmative issuance evidence.
4. A future `credited by` date is shown as an ETA, not a completed credit.
5. Bundled orders display the actual returned product, not every item in the bundle.
6. Expected refund reflects the returned item/return record, not the full bundled order total.
7. Multiple separate returns under one Amazon Order ID remain separate return records.
8. A later stale scan does not regress a more advanced authoritative return stage.

### Per-order Refresh

For a returned order and an ordinary order:

1. Click `Refresh`.
2. Confirm Chrome opens an inactive/background Amazon Order Details tab rather than navigating the active dashboard tab.
3. Confirm the canonical detail capture refreshes.
4. For the returned order, confirm a real `/spr/returns/prep` page is followed for that same order when Amazon exposes it.
5. Confirm the return status/expected refund updates from refreshed evidence.
6. Confirm the temporary background tab closes after completion.
7. Confirm Refresh refuses to invent a URL if the order has no real stored Order Details URL.

### Dashboard acceptance

1. Verify `All orders`, `Returns`, and `Needs review` filters.
2. Verify every row uses the same fixed grid regardless of status.
3. Verify all rows show the same four action positions: `Details`, `Credit`, `Reset`, `Refresh`.
4. Verify inapplicable actions are disabled rather than removed.
5. Verify order containers are not horizontally scrollable at normal desktop widths.
6. Verify Needs Review total equals the sum of expected refund amounts for the currently flagged return records.

### Bank bridge privacy boundary

1. Export a reconciliation request and verify it contains only the narrow documented refund verification fields.
2. Do not place bank credentials, financial-provider tokens, or full transaction feeds into the extension.
3. Import a narrow reconciliation result and verify only `confirmed` posted-credit evidence completes `Bank credited`.
4. Pending, ambiguous, needs-review, or not-found results must not complete the bank-credit milestone.

## Release decision

A user-testable development build may merge only after `npm test` and PR CI pass. Every such build requires a strictly newer manifest/package version. Issue #7 remains open until live Amazon Business acceptance passes. Issue #10 remains open until the Windows bootstrap and a later real automatic update both pass.
