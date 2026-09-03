from pathlib import Path

def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing expected text in {path}: {old[:80]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

replace_once(
    'README.md',
    '**Current source baseline: v0.18.0.** GitHub is the source of truth and chat sessions are disposable.',
    '**Current source baseline: v0.18.1 after PR #12 merges.** GitHub is the source of truth and chat sessions are disposable.'
)
replace_once(
    'README.md',
    'v0.18 does not loosen the v0.17 Amazon data contract.',
    'v0.18.1 does not loosen the v0.17 Amazon data contract. It additionally hardens payment-card last-four capture so generic Amazon layout `card` containers, gift-card values, and unrelated masked numbers cannot become canonical card evidence.'
)

replace_once(
    'PROJECT_HANDOFF.md',
    '**Current source baseline: v0.18.0 after PR #11 merges.** Root source remains the active development source.',
    '**Current source baseline: v0.18.1 after PR #12 merges.** Root source remains the active development source.'
)
marker = 'Two live-validation tracks remain separate:\n\n'
p = Path('PROJECT_HANDOFF.md')
text = p.read_text(encoding='utf-8')
if marker not in text:
    raise SystemExit('handoff live-validation marker missing')
insert = '''## v0.18.1 live payment-card regression fix\n\nLive Amazon Business testing of v0.18.0 exposed repeated incorrect `Card •••• 1000` values across unrelated orders. The root cause was generic DOM selectors whose id/class/data-testid contained `card`; Amazon uses `card` for non-payment layout components, so unrelated masked values could contaminate payment evidence.\n\nv0.18.1 changes the invariant to: card last-four is accepted only from payment/refund-method-specific evidence and must be directly tied to a recognized payment-card instrument or an immediately masked value under an explicit Payment/Refund method heading. Gift-card/generic masked values are rejected. Provisional return records inherit the already-scoped canonical order card value rather than reparsing broad order context.\n\n`payment-evidence-test.js` reproduces the false `1000` case and protects legitimate Visa/Mastercard/refund-method parsing. Because development version changes intentionally reset the ledger, the v0.18.1 auto-update starts with clean state so stale v0.18.0 card values do not survive the retest.\n\n'''
text = text.replace(marker, insert + marker, 1)
p.write_text(text, encoding='utf-8')

replace_once(
    'TESTING.md',
    '**v0.18.0** is the current source baseline after release merge. It preserves the v0.17 Amazon crawler/return contract and adds the verified local development auto-update channel.',
    '**v0.18.1** is the current source baseline after PR #12 release merge. It preserves the v0.17 Amazon crawler/return contract, retains the verified local development auto-update channel, and fixes the live false payment-card last-four contamination found in v0.18.0.'
)
needle = '- payment last-four parsing is restricted to payment-method/payment-information evidence,\n'
p = Path('TESTING.md')
text = p.read_text(encoding='utf-8')
if needle not in text:
    raise SystemExit('testing payment bullet missing')
text = text.replace(needle, needle + '- generic Amazon DOM `card` layout containers, gift-card values, and unrelated masked numbers cannot populate card last-four,\n- recognized card brands and direct masks under Payment/Refund method headings still parse correctly,\n', 1)
p.write_text(text, encoding='utf-8')

replace_once(
    'NEW_CHAT_PROMPT.md',
    'The complete root source baseline is **v0.18.0 after PR #11 merges**.',
    'The complete root source baseline is **v0.18.1 after PR #12 merges**.'
)
p = Path('NEW_CHAT_PROMPT.md')
text = p.read_text(encoding='utf-8')
needle = 'Payment-card last-four parsing must be scoped to actual payment-method/payment-information evidence. Never use arbitrary four-digit page text.\n'
if needle not in text:
    raise SystemExit('new-chat payment rule missing')
text = text.replace(needle, needle + 'v0.18.1 specifically rejects generic Amazon DOM `card` containers, gift-card values, and unrelated masked values; only direct recognized card/payment/refund-method evidence may populate last-four.\n', 1)
p.write_text(text, encoding='utf-8')
