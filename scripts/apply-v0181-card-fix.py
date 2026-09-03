from pathlib import Path

path = Path('parser.js')
text = path.read_text(encoding='utf-8')
start = text.index('  function findCardLast4(text) {')
end = text.index('  function extractOrderIds(text) {', start)
replacement = r'''  function findCardLast4(text) {
    const normalized = normalizeText(text);
    if (!normalized) return null;

    // Accept last-four only when the digits are directly bound to a real card instrument or to
    // an explicit Payment/Refund method heading. Amazon uses "card" for generic layout elements,
    // so generic card containers, gift-card text, dates, and unrelated masked values are ignored.
    const brand = '(?:visa|master\\s*card|mastercard|american express|amex|discover|amazon(?: business)?(?: prime)? visa|amazon business card|amazon store card|credit card|debit card)';
    const marker = '(?:ending in|ending|last four|last 4|\\*{2,}|[•·xX]{2,})';
    const lines = normalized.split('\n').map(line => line.trim()).filter(Boolean);
    const windows = [];
    for (let i = 0; i < lines.length; i += 1) {
      windows.push(lines[i]);
      if (i + 1 < lines.length) windows.push(`${lines[i]}\n${lines[i + 1]}`);
      if (i + 2 < lines.length) windows.push(`${lines[i]}\n${lines[i + 1]}\n${lines[i + 2]}`);
    }

    const branded = new RegExp(`${brand}[^\\d]{0,100}?${marker}\\s*[:#-]?\\s*(\\d{4})\\b`, 'i');
    for (const windowText of windows) {
      if (/gift\s*card|gift certificate/i.test(windowText)) continue;
      const match = windowText.match(branded);
      if (match) return match[1];
    }

    // Some Amazon layouts render only "Payment method" followed immediately by a mask.
    // Keep the fallback local so an unrelated masked number cannot bleed into the payment field.
    const headingMasked = /(?:payment\s+(?:method|information)|refund method)\s*[:#-]?\s*(?:\n\s*)?(?:\*{2,}|[•·xX]{2,})\s*[:#-]?\s*(\d{4})\b/i;
    for (const windowText of windows) {
      if (/gift\s*card|gift certificate/i.test(windowText)) continue;
      const match = windowText.match(headingMasked);
      if (match) return match[1];
    }

    return null;
  }

  function extractPaymentEvidenceText(container) {
    if (!container) return '';
    const chunks = [];
    const seen = new Set();
    const headingRe = /(?:payment\s+(?:method|information)|refund method)/i;
    const instrumentRe = /(?:visa|master\s*card|mastercard|american express|amex|discover|amazon(?: business)?(?: prime)? visa|amazon business card|amazon store card|credit card|debit card)[^\n]{0,120}?(?:ending in|ending|last four|last 4|\*{2,}|[•·xX]{2,})\s*[:#-]?\s*\d{4}\b/i;

    const addChunk = raw => {
      const value = normalizeText(raw);
      if (!value) return;
      const key = value.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      chunks.push(value);
    };

    const addFocused = raw => {
      const value = normalizeText(raw);
      if (!value) return;
      const lines = value.split('\n').map(line => line.trim()).filter(Boolean);
      for (let i = 0; i < lines.length; i += 1) {
        if (instrumentRe.test(lines[i])) {
          addChunk(lines[i]);
          continue;
        }
        if (!headingRe.test(lines[i])) continue;
        addChunk(lines.slice(i, Math.min(lines.length, i + 4)).join('\n'));
      }
    };

    // Only payment/refund-specific hooks qualify. Never use generic id/class/data-testid values
    // containing only "card"; Amazon uses those for unrelated layout cards throughout the page.
    for (const selector of [
      '[id*="payment" i]', '[class*="payment" i]', '[data-testid*="payment" i]', '[aria-label*="payment" i]',
      '[id*="refund-method" i]', '[class*="refund-method" i]', '[data-testid*="refund-method" i]', '[aria-label*="refund method" i]'
    ]) {
      try {
        for (const el of Array.from(container.querySelectorAll(selector))) {
          addFocused(el.innerText || el.textContent || '');
          for (const attr of ['aria-label', 'title', 'alt']) {
            try { addFocused(el.getAttribute?.(attr) || ''); } catch (_) {}
          }
          try {
            for (const child of Array.from(el.querySelectorAll?.('[aria-label], [title], img[alt]') || [])) {
              for (const attr of ['aria-label', 'title', 'alt']) {
                try { addFocused(child.getAttribute?.(attr) || ''); } catch (_) {}
              }
            }
          } catch (_) {}
        }
      } catch (_) {}
    }

    if (!chunks.length) addFocused(container.innerText || container.textContent || '');
    return chunks.join('\n');
  }

'''
text = text[:start] + replacement + text[end:]
needle = '          cardLast4: findCardLast4(context), refundMethod:'
if needle not in text:
    raise SystemExit('provisional return cardLast4 call not found')
text = text.replace(needle, '          cardLast4: record.cardLast4 || null, refundMethod:', 1)
path.write_text(text, encoding='utf-8')
