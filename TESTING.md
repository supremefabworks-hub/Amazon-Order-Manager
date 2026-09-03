# Amazon Order Manager validation

## Current test target

**v0.17.0** is the current source baseline and user-testable candidate.

Automated regression coverage must pass before packaging. Live Amazon Business validation is still required because account-specific Amazon markup, pagination controls, and return pages cannot be fully proven from repository fixtures.

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
- manifest version change wipes development ledger/crawl state, including v0.16 -> v0.17 where no prior version key exists,
- dashboard has fixed `Details / Credit / Reset / Refresh` actions and no horizontal order scrolling,
- bank reconciliation bridge remains narrow and version-aligned.

## Required live Amazon Business validation

Load the unpacked v0.17.0 extension in Chrome and perform this acceptance pass against the real Amazon Business account.

### Clean start

1. Confirm `chrome://extensions` shows version `0.17.0`.
2. Reload/update the extension from v0.16 or earlier.
3. Confirm the development reset starts with a clean ledger/crawl state.
4. Keep Amazon Business signed in normally. Do not provide credentials to the extension or repository.

### Strict crawl sequence

1. Start a lifetime/full crawl at the newest available year.
2. On newest-year page 1, record the visible Amazon Order IDs.
3. Confirm every visible unique Order ID gets a real captured `View order details` URL.
4. Confirm the crawler completes canonical Order Details for every order on page 1 before attempting page 2.
5. Confirm `Detailed` appears only after successful canonical capture.
6. Confirm the crawler activates Amazon's real page-2 control or taught Business pager route.
7. Confirm page 2 counts as progress only after its visible Order-ID fingerprint differs from page 1.
8. Repeat through page 3 and every remaining page in that year.
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

Use at least:

- one ordinary non-returned order that offers `Return or replace items`,
- one in-progress return,
- one return where Amazon states a refund was issued,
- one bundled/multi-item order with a partial return if available,
- one Amazon Order ID with multiple separate returns if available.

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

For an order with a known return and an ordinary order:

1. Click `Refresh`.
2. Confirm Chrome opens an inactive/background Amazon Order Details tab rather than navigating the active dashboard tab.
3. Confirm the canonical detail capture refreshes.
4. For the returned order, confirm a real `/spr/returns/prep` page is followed for that same order when Amazon exposes it.
5. Confirm the return status/expected refund updates from the refreshed evidence.
6. Confirm the temporary background tab closes after completion.
7. Confirm Refresh refuses to invent a URL if the order has no real stored Order Details URL.

### Dashboard acceptance

1. Verify `All orders`, `Returns`, and `Needs review` filters.
2. Verify every row uses the same fixed grid regardless of status.
3. Verify all rows show the same four action positions: `Details`, `Credit`, `Reset`, `Refresh`.
4. Verify inapplicable actions are disabled rather than removed.
5. Verify the order containers are not horizontally scrollable at normal desktop widths.
6. Verify Needs Review total equals the sum of expected refund amounts for the currently flagged return records.

### Bank bridge privacy boundary

1. Export a reconciliation request and verify it contains only the narrow documented refund verification fields.
2. Do not place bank credentials, financial-provider tokens, or full transaction feeds into the extension.
3. Import a narrow reconciliation result and verify only `confirmed` posted-credit evidence completes `Bank credited`.
4. Pending, ambiguous, needs-review, or not-found results must not complete the bank-credit milestone.

## Release decision

v0.17.0 may be merged and packaged after automated tests pass. Issue #7 should remain open until the live Amazon Business acceptance checklist above is completed or any live defects found during it are fixed and regression-tested.
