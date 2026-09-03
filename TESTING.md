# Amazon Order Manager validation

## Automated checks

Run from the repository root:

```bash
npm test
```

This executes parser, storage, background, crawl-state, and reconciliation regression suites.

## Required live Amazon Business validation

1. Start at the current year's page 1.
2. Detail count reaches the number of unique orders on page 1.
3. Worker activates page 2 using Amazon's pager.
4. History pages increases only after different Order IDs appear.
5. Continue through all pages of the current year.
6. Confirm crawler does not switch years while an enabled next page exists.
7. On the final page, confirm it switches to the next older year and the order fingerprint changes.
8. Verify payment card comes only from payment-method evidence.
9. Verify actual return-status links update item-level return records without converting ordinary orders into returns.
