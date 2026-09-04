(() => {
  'use strict';

  const ORDER_ID_RE = /\b(?:order\s*(?:#|id)?\s*[:#-]?\s*)?(\d{3}-\d{7}-\d{7})\b/gi;
  const MONEY_RE = /\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{2})|[0-9]+(?:\.\d{2})?)/i;
  const CARD_PATTERNS = [
    /(?:visa|mastercard|master card|american express|amex|discover|amazon business card|card)?\s*(?:ending in|ending|last four|last 4|\*{1,4}|[•·xX]{2,})\s*[:#-]?\s*(\d{4})\b/i,
    /\b(?:card|payment method|payment)\s*[:#-]?\s*(?:ending in\s*)?(?:\*{0,4}|[•·xX]{0,6})\s*(\d{4})\b/i,
    /(?:\*{2,}|[•·xX]{2,})\s*(\d{4})\b/
  ];

  function normalizeText(value) {
    return String(value || '')
      .replace(/\u00a0/g, ' ')
      .replace(/[ \t]+/g, ' ')
      .replace(/\r/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function slug(value) {
    return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);
  }

  function parseMoney(value) {
    const match = String(value || '').match(MONEY_RE);
    if (!match) return null;
    const number = Number(match[1].replace(/,/g, ''));
    return Number.isFinite(number) ? number : null;
  }

  function findLabeledMoney(text, labels) {
    const normalized = normalizeText(text);
    for (const label of labels) {
      const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`${escaped}\\s*[:]?\\s*\\$\\s*([0-9,]+(?:\\.\\d{2})?)`, 'i');
      const match = normalized.match(regex);
      if (match) return Number(match[1].replace(/,/g, ''));
    }
    return null;
  }


  function findOrderTotal(text) {
    const direct = findLabeledMoney(text, [
      'Order total', 'Order Total', 'Grand total', 'Grand Total', 'Total charged', 'Amount charged'
    ]);
    if (direct !== null) return direct;
    const normalized = normalizeText(text);
    const scoped = normalized.match(/(?:order summary|payment information)[\s\S]{0,1400}?(?:^|\n)\s*Total\s*[:]?\s*\$\s*([0-9,]+(?:\.\d{2})?)/i);
    if (scoped) return Number(scoped[1].replace(/,/g, ''));
    return null;
  }

  function findOrderRefundTotal(text) {
    // Canonical order-level refund money comes only from a standalone Amazon Order Details
    // "Refund Total" label. Generic refund lifecycle prose must never become this field.
    const normalized = normalizeText(text);
    const match = normalized.match(/(?:^|\n)\s*Refund Total\s*:?\s*\$\s*([0-9,]+(?:\.\d{2})?)\s*(?:$|\n)/im);
    if (!match) return null;
    const value = Number(match[1].replace(/,/g, ''));
    return Number.isFinite(value) ? value : null;
  }

  function findRefundAmount(text) {
    const direct = findLabeledMoney(text, [
      'Total refund', 'Total estimated refund*', 'Total estimated refund', 'Estimated refund', 'Refund amount', 'Refund total', 'Refund subtotal'
    ]);
    if (direct !== null) return direct;
    const normalized = normalizeText(text);
    for (const regex of [
      /\$\s*([0-9,]+(?:\.\d{2})?)\s+(?:refund (?:has been |was )?issued|refund issued)/i,
      /(?:refund (?:has been |was )?issued|refund issued)[^$]{0,100}\$\s*([0-9,]+(?:\.\d{2})?)/i,
      /\$\s*([0-9,]+(?:\.\d{2})?)\s+(?:will be|was|has been)\s+credited/i
    ]) {
      const m = normalized.match(regex);
      if (m) return Number(m[1].replace(/,/g, ''));
    }
    return null;
  }

  function findCardLast4(text) {
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

    const addFocused = (raw, allowStandaloneInstrument = false) => {
      const value = normalizeText(raw);
      if (!value) return;
      const lines = value.split('\n').map(line => line.trim()).filter(Boolean);
      for (let i = 0; i < lines.length; i += 1) {
        if (allowStandaloneInstrument && instrumentRe.test(lines[i])) {
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
          addFocused(el.innerText || el.textContent || '', true);
          for (const attr of ['aria-label', 'title', 'alt']) {
            try { addFocused(el.getAttribute?.(attr) || '', true); } catch (_) {}
          }
          try {
            for (const child of Array.from(el.querySelectorAll?.('[aria-label], [title], img[alt]') || [])) {
              for (const attr of ['aria-label', 'title', 'alt']) {
                try { addFocused(child.getAttribute?.(attr) || '', true); } catch (_) {}
              }
            }
          } catch (_) {}
        }
      } catch (_) {}
    }

    if (!chunks.length) addFocused(container.innerText || container.textContent || '', false);
    return chunks.join('\n');
  }

  function extractOrderIds(text) {
    const ids = [];
    const seen = new Set();
    let match;
    ORDER_ID_RE.lastIndex = 0;
    while ((match = ORDER_ID_RE.exec(String(text || ''))) !== null) {
      if (!seen.has(match[1])) {
        seen.add(match[1]);
        ids.push(match[1]);
      }
    }
    return ids;
  }

  function contextAround(text, needle, radius = 4200) {
    const raw = String(text || '');
    const index = raw.indexOf(needle);
    if (index < 0) return raw.slice(0, radius * 2);
    return raw.slice(Math.max(0, index - radius), Math.min(raw.length, index + needle.length + radius));
  }

  function findDateAfterLabel(text, labels) {
    const normalized = normalizeText(text);
    const month = '(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)';
    for (const label of labels) {
      const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`${escaped}\\s*[:]?\\s*(${month}\\s+\\d{1,2}(?:,\\s*\\d{4})?)`, 'i');
      const match = normalized.match(regex);
      if (match) return match[1];
    }
    return null;
  }

  function findMilestoneDate(text, labels) {
    const normalized = normalizeText(text);
    const date = '(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\\s+\\d{1,2}(?:,\\s*\\d{4})?';
    for (const label of labels) {
      const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      for (const regex of [
        new RegExp(`(${date})\\s*${escaped}`, 'i'),
        new RegExp(`${escaped}\\s*(${date})`, 'i')
      ]) {
        const match = normalized.match(regex);
        if (match) return match[1];
      }
    }
    return null;
  }

  function findExpectedCreditDate(text) {
    const normalized = normalizeText(text);
    const date = '((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?)';
    for (const regex of [
      new RegExp(`(?:will|should|expected to)\s+be\s+credited[^\n]{0,160}?\bby\s+${date}`, 'i'),
      new RegExp(`(?:refund|credit)[^\n]{0,100}?(?:expected|estimated)[^\n]{0,80}?${date}`, 'i'),
      new RegExp(`(?:credited|credit)[^\n]{0,100}?\bby\s+${date}`, 'i')
    ]) {
      const match = normalized.match(regex);
      if (match) return match[1];
    }
    // Amazon's timeline can render a future date immediately above the static "Refund credited"
    // label even though the milestone is not complete yet. Treat that as an ETA, not completion.
    return findMilestoneDate(normalized, ['Refund credited', 'Credited']);
  }

  function parseReturnMilestones(text) {
    const normalized = normalizeText(text);

    // Static timeline labels are not evidence of completion. A completed credit requires an
    // affirmative sentence that Amazon actually credited the refund.
    const credited = /(?:your refund (?:has been|was) credited|we (?:have )?credited your refund|refund (?:has been|was) credited to|credited to your (?:original )?payment method on)/i.test(normalized);
    const refundIssued = credited || /(?:we (?:have )?issued your refund|your refund (?:has been|was) issued|refund has been issued|refund issued\s+(?:on|\$))/i.test(normalized);
    const received = refundIssued || /(?:we (?:have )?received your return|return (?:has been )?received|received your return|item received|return processed)/i.test(normalized);
    const shipped = received || /(?:dropped off|drop-?off complete|return (?:is )?in transit|on the way back|return shipped|shipped back|carrier received)/i.test(normalized);
    const started = shipped || /(?:return request|return initiated|initiated|accepted your return|return code|return summary|refund will be issued|estimated refund|refund method|refund subtotal)/i.test(normalized);

    const stage = credited ? 'credited' : refundIssued ? 'refund_issued' : received ? 'received' : shipped ? 'shipped' : started ? 'started' : 'unknown';
    const expectedCreditDate = credited ? null : findExpectedCreditDate(normalized);

    return {
      stage,
      expectedCreditDate,
      started: { done: started, date: started ? findMilestoneDate(normalized, ['Initiated', 'Return initiated', 'Return started']) : null },
      shipped: { done: shipped, date: shipped ? findMilestoneDate(normalized, ['Dropped off', 'Drop off', 'Return shipped', 'Shipped']) : null },
      refundIssued: { done: refundIssued, date: refundIssued ? findMilestoneDate(normalized, ['Refund issued']) : null },
      credited: { done: credited, date: credited ? findMilestoneDate(normalized, ['Refund credited', 'Credited']) : null }
    };
  }

  function classifyStatus(text, recordType) {
    if (recordType === 'return') {
      const stage = parseReturnMilestones(text).stage;
      if (stage === 'credited' || stage === 'refund_issued') return 'refunded';
      if (stage === 'received') return 'returned_pending_refund';
      if (stage === 'shipped' || stage === 'started') return 'return_in_progress';
      if (/refund will be issued|estimated refund|refund method|refund subtotal/i.test(normalizeText(text))) return 'refund_expected';
      return 'unknown';
    }
    const t = normalizeText(text).toLowerCase();
    if (/delivered|shipped|arriving|ordered|order placed/.test(t)) return 'purchase';
    return 'purchase';
  }

  function classifyReturnStage(text, recordType) {
    if (recordType !== 'return') return null;
    return parseReturnMilestones(text).stage;
  }

  function extractStatusText(text) {
    const normalized = normalizeText(text);
    const lines = normalized.split('\n').map(s => s.trim()).filter(Boolean);
    if (!lines.length) return null;

    const stage = parseReturnMilestones(normalized).stage;
    const stagePatterns = {
      credited: [
        /(?:your refund (?:has been|was) credited|we (?:have )?credited your refund|refund (?:has been|was) credited to|credited to your (?:original )?payment method on)/i
      ],
      refund_issued: [
        /(?:we (?:have )?issued your refund|your refund (?:has been|was) issued|refund has been issued|refund issued\s+(?:on|\$))/i
      ],
      received: [
        /(?:we (?:have )?received your return|return (?:has been )?received|received your return|item received|return processed|your return is complete|return complete)/i
      ],
      shipped: [
        /(?:dropped off|drop-?off complete|return (?:is )?in transit|on the way back|return shipped|shipped back|carrier received)/i
      ],
      started: [
        /(?:return request|return initiated|return started|accepted your return|return code|return summary|refund will be issued|estimated refund)/i
      ]
    };

    for (const pattern of stagePatterns[stage] || []) {
      const line = lines.find(candidate => pattern.test(candidate));
      if (line) return line.slice(0, 500);
    }

    // Normal purchase/delivery rows still need useful order status text, but static return
    // timeline labels such as a bare "Refund issued" are deliberately excluded here.
    for (const line of lines) {
      if (/^(?:refund issued|refund credited|credited|initiated|dropped off|credit pending)$/i.test(line)) continue;
      if (/(?:delivered|arriving|shipped)/i.test(line) && !/(?:refund issued|refund credited)/i.test(line)) return line.slice(0, 500);
    }
    return null;
  }

  function inferPageType(text, url) {
    const t = normalizeText(text).toLowerCase();
    const u = String(url || '').toLowerCase();
    // An order-history/detail page can contain return buttons/status text for individual orders;
    // that must not turn every order on the page into a return record.
    if (/order-history|your-orders|yourorders|order-details|orderdetails|order-detail|\/gp\/css\/summary\/edit\.html/.test(u)) return 'order';
    if (/\/spr\/returns\/(?:prep|label|cart)|\/returns?\/(?:status|details)|return-status|\/refund(?:\/|\?|$)/.test(u)) return 'return';
    if (/return summary/.test(t) && /(refund method|refund subtotal|total refund|return instructions)/.test(t)) return 'return';
    return 'order';
  }

  function isOrderDetailPage(url) {
    return /(?:order-details|orderdetails|order-detail|\/gp\/css\/summary\/edit\.html(?:[/?#]|$))/i.test(String(url || ''));
  }

  function isOrderHistoryPage(doc, url) {
    const u = String(url || '').toLowerCase();
    // /your-orders/order-details is a detail page, not a one-order history page. Treating it as
    // history caused the crawler to rediscover the same order and manufacture bogus pagination.
    if (/\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|orderdetails|order-detail/.test(u)) return false;
    if (/\/gp\/your-account\/order-history|\/gp\/css\/order-history|\/your-orders\/orders(?:[/?#]|$)/.test(u)) return true;
    const text = normalizeText(doc?.body?.innerText || doc?.body?.textContent || '').toLowerCase();
    return /your orders/.test(text) && /viewing\s+[0-9,]+\s+orders?\s+placed\s+in|(?:^|\n)order placed(?:\n|$)/.test(text);
  }

  function extractItemNamesFromText(text) {
    const normalized = normalizeText(text);
    const patterns = [
      /Item\(s\) in your return request\s*\n?(.+?)\s*\n?Quantity\s*:/i,
      /Return Item\s*:\s*(.+?)(?:\n|Quantity|Return Reason)/i,
      /(?:^|\n)([^\n]{5,300})\n\s*Quantity\s*:\s*\d+/i
    ];
    for (const pattern of patterns) {
      const match = normalized.match(pattern);
      if (match) return [normalizeText(match[1]).replace(/\.{3,}$/, '').slice(0, 300)];
    }
    return [];
  }

  function closestContainerForOrder(doc, orderId) {
    if (!doc || !doc.querySelectorAll) return null;
    const candidates = Array.from(doc.querySelectorAll('[data-order-id], [class*="order"], [class*="shipment"], [class*="return"], .a-box-group, .a-box'));
    let best = null;
    let bestLength = Infinity;
    for (const el of candidates) {
      const text = normalizeText(el.innerText || el.textContent || '');
      if (text.includes(orderId) && text.length < bestLength && text.length > orderId.length) {
        best = el;
        bestLength = text.length;
      }
    }
    return best;
  }

  function historyContainerForOrder(doc, orderId) {
    if (!doc?.querySelectorAll || !orderId) return null;
    const matchingAnchors = Array.from(doc.querySelectorAll('a[href]')).filter(a => {
      const href = String(a.getAttribute('href') || a.href || '');
      const text = normalizeText(a.innerText || a.textContent || '');
      return href.includes(orderId) && (/(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details|orderdetails)/i.test(href) || /view\s+order\s+details/i.test(text));
    });
    for (const anchor of matchingAnchors) {
      let current = anchor;
      let best = null;
      for (let depth = 0; current && depth < 12; depth += 1, current = current.parentElement) {
        const text = normalizeText(current.innerText || current.textContent || '');
        const ids = extractOrderIds(text);
        if (!ids.includes(orderId)) continue;
        if (ids.length > 1) break;
        const productLinks = Array.from(current.querySelectorAll?.('a[href]') || []).filter(a => {
          const href = String(a.getAttribute('href') || '');
          const label = normalizeText(a.innerText || a.textContent || '');
          return /(\/dp\/|\/gp\/product\/|\/product\/)/i.test(href) && label && !/amazon business card|prime business/i.test(label);
        });
        if (productLinks.length) best = current;
        if (text.length > 8000) break;
      }
      if (best) return best;
    }
    return closestContainerForOrder(doc, orderId);
  }

  function excludedProductAnchor(a) {
    const excluded = a.closest?.('#rhf, [id*="recommend" i], [class*="recommend" i], footer, aside, [data-a-carousel-options]');
    if (excluded) return true;
    let current = a.parentElement;
    for (let depth = 0; current && depth < 5; depth += 1, current = current.parentElement) {
      const text = normalizeText(current.innerText || current.textContent || '');
      if (text.length <= 4500 && /products related to your return|customers who viewed|sponsored products/i.test(text)) return true;
    }
    return false;
  }

  function extractItemNamesFromContainer(container) {
    if (!container || !container.querySelectorAll) return [];
    const names = [];
    const seen = new Set();
    const productLinks = Array.from(container.querySelectorAll('a[href*="/dp/"], a[href*="/gp/product/"], a[href*="/product/"]'));

    for (const a of productLinks) {
      if (excludedProductAnchor(a)) continue;
      const href = String(a.getAttribute('href') || a.href || '');
      const asin = href.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})(?:[/?]|$)/i)?.[1]?.toUpperCase() || '';
      let title = normalizeText(a.innerText || a.textContent || '');

      // Port the working exporter fallbacks. Amazon frequently makes the image the product anchor,
      // leaving the anchor text blank even though the title is present in a nearby node.
      if (!title || title.length < 5) {
        let parent = a.parentElement;
        for (let depth = 0; depth < 5 && parent; depth += 1, parent = parent.parentElement) {
          const titleEl = parent.querySelector?.('.a-text-bold, [class*="product-title" i], [class*="item-title" i]');
          const candidate = normalizeText(titleEl?.innerText || titleEl?.textContent || '');
          if (candidate.length >= 5) { title = candidate; break; }
        }
      }
      if (!title || title.length < 5) title = normalizeText(a.getAttribute?.('title') || a.getAttribute?.('aria-label') || '');
      if (!title || title.length < 5) {
        const img = a.querySelector?.('img') || a.parentElement?.querySelector?.('img');
        title = normalizeText(img?.getAttribute?.('alt') || img?.alt || '');
      }

      if (!title || title.length < 3 || title.length > 500) continue;
      if (/buy it again|view order|order details|track package|return or replace|write a product review|invoice|amazon business card|prime business/i.test(title)) continue;
      const key = asin || title.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      names.push(title.slice(0, 400));
    }
    return names.slice(0, 30);
  }

  function extractAsins(container) {
    if (!container || !container.querySelectorAll) return [];
    const asins = [];
    const seen = new Set();
    for (const a of Array.from(container.querySelectorAll('a[href]'))) {
      if (excludedProductAnchor(a)) continue;
      const href = String(a.getAttribute('href') || '');
      const match = href.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})(?:[/?]|$)/i);
      if (match && !seen.has(match[1].toUpperCase())) {
        seen.add(match[1].toUpperCase());
        asins.push(match[1].toUpperCase());
      }
    }
    return asins.slice(0, 30);
  }


  function extractReturnItemEntries(container) {
    if (!container?.querySelectorAll) return [];
    const candidates = [];
    const seenElements = new Set();
    for (const selector of ['[data-asin]', '[data-item-index]', '[class*="return-item" i]', '[class*="returnItem"]', '.a-box', '.a-section']) {
      let nodes = [];
      try { nodes = Array.from(container.querySelectorAll(selector)); } catch (_) {}
      for (const el of nodes) {
        if (!el || seenElements.has(el)) continue;
        seenElements.add(el);
        const text = normalizeText(el.innerText || el.textContent || '');
        if (text.length < 8 || text.length > 3600) continue;
        if (!/(?:quantity\s*:|return item|item\(s\) in your return request|refund (?:amount|subtotal)|estimated refund)/i.test(text)) continue;
        const names = extractItemNamesFromContainer(el);
        const fallback = names.length ? names : extractItemNamesFromText(text);
        const itemName = fallback[0] || null;
        const asin = extractAsins(el)[0] || null;
        if (!itemName && !asin) continue;
        const refundAmount = findLabeledMoney(text, ['Item refund', 'Refund amount', 'Estimated refund', 'Refund subtotal']);
        candidates.push({ itemName, asin, refundAmount, textLength: text.length });
      }
    }
    const byKey = new Map();
    for (const entry of candidates) {
      const key = entry.asin || String(entry.itemName || '').toLowerCase();
      const prior = byKey.get(key);
      if (!prior || entry.textLength < prior.textLength) byKey.set(key, entry);
    }
    return Array.from(byKey.values()).map(({ textLength, ...entry }) => entry).slice(0, 30);
  }

  function isCompleteCanonicalDetail(record, url) {
    if (!record || record.recordType !== 'order' || !isOrderDetailPage(url)) return false;
    const urlId = orderIdFromUrl(url);
    if (!urlId || urlId !== record.orderId) return false;
    if (!record.orderDetailsUrl || !isOrderDetailPage(record.orderDetailsUrl)) return false;
    return Boolean(record.orderDate && Number.isFinite(Number(record.purchaseAmount)) && Array.isArray(record.itemNames) && record.itemNames.length);
  }

  function extractReturnToken(url) {
    try {
      const u = new URL(url);
      for (const key of ['rmaId', 'contractId', 'returnId']) if (u.searchParams.get(key)) return u.searchParams.get(key);
      const match = u.pathname.match(/(?:return|returns|label)\/([a-z0-9-]{8,})/i);
      return match ? match[1] : null;
    } catch (_) {
      return null;
    }
  }

  function makeRecordId(record) {
    if (record.recordType === 'order') return `order:${record.orderId}`;
    const tokenKey = slug(record.returnToken || record.returnStatusUrl || '') || 'return';
    // Amazon's return-status URL gives us a stable child identity. Prefer itemId so the
    // provisional Order Details record and later authoritative return-page capture merge into
    // the same row instead of being re-keyed by whichever title the page parser happened to see.
    const itemKey = record.returnItemId
      ? `item-${slug(record.returnItemId)}`
      : (record.asins?.[0] || slug(record.itemNames?.[0] || '') || (record.provisionalReturn ? 'pending' : String(record.refundAmount ?? record.refundSubtotal ?? 'unknown')));
    return `return:${record.orderId}:${tokenKey}:${itemKey}`;
  }

  function parseTextRecord(text, orderId, options = {}) {
    const pageType = options.pageType || inferPageType(text, options.url);
    const returnMeta = returnUrlMetadata(options.returnStatusUrl || options.url || '');
    const refundAmount = findRefundAmount(text);
    const refundSubtotal = findLabeledMoney(text, ['Refund subtotal']);
    const purchaseAmount = findOrderTotal(text);
    const cardLast4 = Object.prototype.hasOwnProperty.call(options, 'paymentText') ? findCardLast4(options.paymentText) : findCardLast4(text);
    const orderDate = findDateAfterLabel(text, ['Order placed', 'Order date']);
    const returnDate = findDateAfterLabel(text, ['Return initiated', 'Return started', 'Returned on', 'Drop off by', 'Dropoff by']);
    const recordType = options.forceRecordType || (pageType === 'return' ? 'return' : 'order');
    const itemNames = extractItemNamesFromText(text);
    const returnMilestones = recordType === 'return' ? parseReturnMilestones(text) : null;
    const record = {
      recordType,
      orderId,
      itemNames,
      asins: [],
      orderDate,
      returnDate,
      purchaseAmount: recordType === 'order' ? purchaseAmount : null,
      refundSubtotal,
      refundAmount: refundAmount ?? refundSubtotal,
      cardLast4,
      refundMethod: cardLast4 ? `card ending ${cardLast4}` : (/original payment method/i.test(text) ? 'original payment method' : null),
      status: classifyStatus(text, recordType),
      returnStage: classifyReturnStage(text, recordType),
      returnMilestones,
      expectedCreditDate: returnMilestones?.expectedCreditDate || null,
      statusText: extractStatusText(text),
      returnToken: options.returnToken || returnMeta.returnToken || null,
      returnItemId: options.returnItemId || returnMeta.returnItemId || null,
      returnContractId: options.returnContractId || returnMeta.returnContractId || null,
      returnRmaId: options.returnRmaId || returnMeta.returnRmaId || null,
      itemIdentitySource: options.itemIdentitySource || null,
      returnStatusUrl: options.returnStatusUrl || (recordType === 'return' ? options.url || null : null),
      sourceUrl: options.url || null,
      sourceHost: options.host || null,
      pageTitle: options.title || null,
      orderDetailsUrl: options.orderDetailsUrl || null,
      detailScanComplete: Boolean(options.detailScanComplete),
      detailScannedAt: options.detailScanComplete ? new Date().toISOString() : null
    };
    record.recordId = makeRecordId(record);
    return record;
  }

  function absoluteAmazonUrl(href, baseUrl) {
    try {
      const url = new URL(href, baseUrl);
      if (!/^https:\/\/[^/]*amazon\.com$/i.test(url.origin)) return null;
      return url.toString();
    } catch (_) {
      return null;
    }
  }

  function orderIdFromUrl(url) {
    try {
      const u = new URL(url);
      for (const [key, value] of u.searchParams.entries()) {
        if (/^order_?id$/i.test(key) || /^orderid$/i.test(key)) {
          const match = String(value).match(/\d{3}-\d{7}-\d{7}/);
          if (match) return match[0];
        }
      }
      const match = u.toString().match(/\d{3}-\d{7}-\d{7}/);
      return match ? match[0] : null;
    } catch (_) {
      return null;
    }
  }

  function nearestOrderId(node) {
    let current = node;
    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
      const ids = extractOrderIds(normalizeText(current.innerText || current.textContent || ''));
      if (ids.length === 1) return ids[0];
    }
    return null;
  }

  function extractOrderDetailLinks(doc, baseUrl) {
    if (!doc?.querySelectorAll) return [];
    const byOrder = new Map();

    // The real "View order details" href is authoritative. Preserve it exactly (apart from
    // resolving it to an absolute URL) rather than guessing an older /gp/your-account route.
    for (const a of Array.from(doc.querySelectorAll('a[href]'))) {
      const href = String(a.getAttribute('href') || a.href || '');
      const text = normalizeText(a.innerText || a.textContent || '');
      const looksLikeDetailHref = /(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html|order-details|orderdetails|order-detail)/i.test(href);
      const looksLikeDetailText = /^(?:view\s+)?order\s+details$/i.test(text);
      if (!looksLikeDetailHref && !looksLikeDetailText) continue;
      const url = absoluteAmazonUrl(href, baseUrl);
      if (!url) continue;
      let actualDetailPath = false;
      try { actualDetailPath = /(?:\/your-orders\/order-details|\/gp\/your-account\/order-details|\/gp\/css\/summary\/edit\.html)(?:[/?#]|$)/i.test(new URL(url).pathname); } catch (_) {}
      if (!actualDetailPath && !looksLikeDetailText) continue;
      const orderId = orderIdFromUrl(url) || nearestOrderId(a);
      if (!orderId || byOrder.has(orderId)) continue;
      byOrder.set(orderId, { orderId, url, discoveredFrom: 'view-order-details-link' });
    }

    return Array.from(byOrder.values());
  }

  function returnUrlMetadata(url) {
    const out = { returnToken: extractReturnToken(url), returnItemId: null, returnContractId: null, returnRmaId: null };
    try {
      const u = new URL(url);
      out.returnItemId = u.searchParams.get('itemId') || null;
      out.returnContractId = u.searchParams.get('contractId') || null;
      out.returnRmaId = u.searchParams.get('rmaId') || null;
    } catch (_) {}
    return out;
  }

  function nearestReturnItemEvidence(anchor) {
    let current = anchor?.parentElement || null;
    let fallback = null;
    for (let depth = 0; current && depth < 10; depth += 1, current = current.parentElement) {
      let anchors = [];
      try { anchors = Array.from(current.querySelectorAll?.('a[href]') || []); } catch (_) {}
      const byAsin = new Map();
      for (const a of anchors) {
        const href = String(a.getAttribute?.('href') || a.href || '');
        const match = href.match(/\/dp\/([A-Z0-9]{10})(?:[/?#]|$)/i) || href.match(/[?&]asin=([A-Z0-9]{10})(?:&|$)/i);
        if (!match) continue;
        const asin = match[1].toUpperCase();
        let itemName = normalizeText(a.innerText || a.textContent || a.getAttribute?.('aria-label') || a.getAttribute?.('title') || '');
        if (/^(?:view your item|buy it again|write a product review|ask product question)$/i.test(itemName)) itemName = '';
        const existing = byAsin.get(asin);
        if (!existing || (!existing.itemName && itemName)) byAsin.set(asin, { asin, itemName });
      }
      if (!byAsin.size) continue;
      const entries = Array.from(byAsin.values());
      const evidence = {
        itemNames: entries.map(entry => entry.itemName).filter(Boolean),
        asins: entries.map(entry => entry.asin).filter(Boolean)
      };
      if (!fallback) fallback = evidence;
      // A duplicated image/title anchor for one ASIN still counts as one product. The smallest
      // ancestor with one unique product is the item-specific return block we want.
      if (entries.length === 1) return evidence;
    }
    return fallback || { itemNames: [], asins: [] };
  }

  function extractReturnStatusLinks(doc, baseUrl) {
    if (!doc?.querySelectorAll) return [];
    const results = [];
    const seen = new Set();
    const statusTextRe = /(?:view|check|track|see|print|share)?\s*(?:your\s*)?(?:return\s*(?:&|and|\/)\s*refund|return|refund)\s*(?:status|details|label)|check return\s*(?:&|and)\s*refund status|return label/i;
    const genericActionRe = /return or replace|return items?|replace items?|start a return/i;

    for (const a of Array.from(doc.querySelectorAll('a[href]'))) {
      const href = String(a.getAttribute('href') || a.href || '');
      const text = normalizeText(a.innerText || a.textContent || '');
      if (!href || genericActionRe.test(text)) continue;
      const url = absoluteAmazonUrl(href, baseUrl);
      if (!url) continue;
      let explicitUrl = false;
      try {
        const u = new URL(url);
        explicitUrl = Boolean(u.searchParams.get('rmaId') || u.searchParams.get('contractId') || u.searchParams.get('returnId')) ||
          /\/spr\/returns\/(?:prep|label)|\/returns?\/(?:status|details)|return-status/i.test(u.pathname);
      } catch (_) {}
      if (!explicitUrl && !statusTextRe.test(text)) continue;
      const orderId = orderIdFromUrl(url) || nearestOrderId(a);
      if (!orderId) continue;
      const meta = returnUrlMetadata(url);
      const token = meta.returnToken || slug(url);
      const itemKey = meta.returnItemId || '';
      const key = `${orderId}:${token}:${itemKey}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const evidence = nearestReturnItemEvidence(a);
      results.push({
        orderId,
        url,
        returnToken: token,
        returnItemId: meta.returnItemId,
        returnContractId: meta.returnContractId,
        returnRmaId: meta.returnRmaId,
        itemNames: evidence.itemNames,
        asins: evidence.asins,
        itemIdentitySource: (evidence.itemNames.length || evidence.asins.length)
          ? (isOrderDetailPage(baseUrl) ? 'order-detail-return-link' : 'return-link')
          : null
      });
    }
    return results;
  }

  function historyRouteFromUrl(url) {
    try {
      const u = new URL(url);
      const hash = String(u.hash || '');
      let match = hash.match(/#time\/(20\d{2})\/pagination\/(\d+|next)\/?/i);
      if (match) return { year: Number(match[1]), page: /^\d+$/.test(match[2]) ? Number(match[2]) : null, token: match[2].toLowerCase(), mode: 'hash-time' };
      match = hash.match(/#pagination\/(\d+|next)\/?/i);
      if (match) return { year: null, page: /^\d+$/.test(match[1]) ? Number(match[1]) : null, token: match[1].toLowerCase(), mode: 'hash' };
      const raw = u.searchParams.get('orderFilter') || u.searchParams.get('timeFilter') || '';
      const yearMatch = String(raw).match(/(?:year[-_:]?)?(20\d{2})/i);
      const startRaw = u.searchParams.get('startIndex');
      const start = startRaw == null || startRaw === '' ? NaN : Number(startRaw);
      let page = Number.isFinite(start) && start >= 0 ? Math.floor(start / 10) + 1 : null;
      for (const key of ['page', 'pageNumber', 'pageNo', 'pageNum']) {
        if (page != null) break;
        const n = Number(u.searchParams.get(key));
        if (Number.isFinite(n) && n >= 1) page = n;
      }
      return { year: yearMatch ? Number(yearMatch[1]) : null, page, token: page != null ? String(page) : null, mode: 'query' };
    } catch (_) { return { year: null, page: null, token: null, mode: null }; }
  }

  function buildHistoryRouteUrl(baseUrl, year, page = 1) {
    try {
      const u = new URL(baseUrl);
      const y = Number(year);
      const p = Number(page);
      if (Number.isFinite(y) && y >= 2000 && Number.isFinite(p) && p >= 1) {
        u.hash = `time/${y}/pagination/${Math.floor(p)}/`;
      } else if (Number.isFinite(p) && p >= 1) {
        u.hash = `pagination/${Math.floor(p)}/`;
      }
      return u.toString();
    } catch (_) { return null; }
  }


  function buildServerHistoryUrl(baseUrl, year, page = 1) {
    try {
      const u = new URL(baseUrl);
      const y = Number(year);
      const p = Math.max(1, Number(page) || 1);
      if (!Number.isFinite(y)) return null;
      u.searchParams.delete('orderFilter');
      u.searchParams.set('timeFilter', `year-${y}`);
      const startIndex = (p - 1) * 10;
      if (startIndex > 0) u.searchParams.set('startIndex', String(startIndex));
      else u.searchParams.delete('startIndex');
      u.hash = '';
      return u.toString();
    } catch (_) { return null; }
  }

  function historyLocationKey(value) {
    try {
      const u = new URL(value);
      const route = historyRouteFromUrl(u.toString());
      for (const key of ['ref_', 'ref', 'tag']) u.searchParams.delete(key);
      if (route.mode && (route.page != null || route.token === 'next' || route.year != null)) {
        const yearPart = route.year != null ? `time/${route.year}/` : '';
        const pagePart = route.page != null ? route.page : (route.token || '');
        u.hash = `${yearPart}pagination/${pagePart}/`;
      } else {
        u.hash = '';
      }
      return u.toString();
    } catch (_) { return String(value || ''); }
  }

  function paginationNumber(url, key) {
    try {
      const u = new URL(url);
      const raw = u.searchParams.get(key);
      if (raw == null || raw === '') return null;
      const value = Number(raw);
      return Number.isFinite(value) ? value : null;
    } catch (_) {
      return null;
    }
  }

  function visibleHistoryOrderCount(doc) {
    const text = normalizeText(doc?.body?.innerText || doc?.body?.textContent || '');
    return extractOrderIds(text).length;
  }

  function totalOrdersForCurrentFilter(doc) {
    const text = normalizeText(doc?.body?.innerText || doc?.body?.textContent || '');
    const match = text.match(/Viewing\s+([0-9,]+)\s+orders?\s+placed\s+in/i) || text.match(/([0-9,]+)\s+orders?\s+placed\s+in/i);
    if (!match) return null;
    const n = Number(match[1].replace(/,/g, ''));
    return Number.isFinite(n) ? n : null;
  }


  function historyTimeFilterState(doc) {
    try {
      const select = doc?.querySelector?.('#timeFilterDropdown, select[name="timeFilterDropdown"]');
      if (!select) return { value: null, label: null, year: null };
      const value = String(select.value || '').trim();
      const label = normalizeText(select.selectedOptions?.[0]?.textContent || select.selectedOptions?.[0]?.innerText || '');
      const raw = `${value} ${label}`;
      const match = raw.match(/\b(20\d{2})\b/);
      return { value: value || null, label: label || null, year: match ? Number(match[1]) : null };
    } catch (_) { return { value: null, label: null, year: null }; }
  }

  function displayedHistoryYear(doc, baseUrl = '') {
    const filter = historyTimeFilterState(doc);
    if (filter.year) return filter.year;
    const route = historyRouteFromUrl(baseUrl);
    if (route.year) return route.year;
    const text = normalizeText(doc?.body?.innerText || doc?.body?.textContent || '');
    const match = text.match(/Viewing\s+[0-9,]+\s+orders?\s+placed\s+in\s+(20\d{2})/i) || text.match(/orders?\s+placed\s+in\s+(20\d{2})/i);
    return match ? Number(match[1]) : null;
  }

  function syntheticNextHistoryUrls(doc, baseUrl) {
    const visible = visibleHistoryOrderCount(doc);
    const total = totalOrdersForCurrentFilter(doc);
    const route = historyRouteFromUrl(baseUrl);
    const selectedYear = route.year || displayedHistoryYear(doc, baseUrl);
    const currentPage = route.page || 1;
    const out = [];
    const seen = new Set();
    const add = url => { if (url && !seen.has(url)) { seen.add(url); out.push(url); } };

    // Amazon Business on the recorded account uses a hash-routed pager. Queue its exact next
    // numbered route first; query offsets are only compatibility fallbacks for other Amazon UIs.
    if (isOrderHistoryPage(doc, baseUrl) && hasNextPageControl(doc)) {
      add(buildHistoryRouteUrl(baseUrl, selectedYear, currentPage + 1));
    }

    // Query offsets remain compatibility fallbacks only.
    if (visible && total != null) {
      const currentStart = paginationNumber(baseUrl, 'startIndex') ?? 0;
      if (currentStart + visible < total) {
        const addStep = step => {
          const n = Number(step);
          if (!Number.isFinite(n) || n <= 0) return;
          try {
            const u = new URL(baseUrl);
            u.searchParams.set('startIndex', String(currentStart + n));
            u.hash = '';
            add(u.toString());
          } catch (_) {}
        };
        addStep(10);
        if (visible !== 10) addStep(visible);
      }
    }
    return out;
  }

  function paginationAttributeUrls(doc, baseUrl) {
    if (!doc?.querySelectorAll) return [];
    const out = [];
    const seen = new Set();
    const attrs = ['href', 'data-href', 'data-url', 'data-a-href', 'formaction', 'data-action-url'];
    for (const el of Array.from(doc.querySelectorAll('*'))) {
      for (const attr of attrs) {
        const raw = el.getAttribute?.(attr);
        if (!raw || !/(startIndex|page(?:Number|No|Num)?|orderFilter|order-history)/i.test(raw)) continue;
        const absolute = absoluteAmazonUrl(raw, baseUrl);
        if (absolute && !seen.has(absolute)) { seen.add(absolute); out.push(absolute); }
      }
    }
    return out;
  }

  function historyYearFromUrl(url) {
    return historyRouteFromUrl(url).year;
  }

  function synthesizeYearUrl(baseUrl, year, rawValue = null) {
    const y = Number(year);
    if (!Number.isFinite(y)) return null;
    return buildHistoryRouteUrl(baseUrl, y, 1) || buildServerHistoryUrl(baseUrl, y, 1);
  }

  function extractHistoryYearLinks(doc, baseUrl) {
    if (!isOrderHistoryPage(doc, baseUrl)) return [];
    const byYear = new Map();
    const add = (year, rawUrl = null, rawValue = null) => {
      const y = Number(year);
      if (!Number.isFinite(y) || y < 2000 || y > new Date().getFullYear() + 1) return;
      const url = rawUrl ? absoluteAmazonUrl(rawUrl, baseUrl) : synthesizeYearUrl(baseUrl, y, rawValue);
      if (url && !byYear.has(y)) byYear.set(y, url);
    };

    for (const a of Array.from(doc.querySelectorAll?.('a[href]') || [])) {
      const label = normalizeText(a.innerText || a.textContent || '');
      const y = label.match(/^(20\d{2})$/)?.[1];
      const href = a.getAttribute('href') || a.href || '';
      const hrefYear = String(href).match(/(?:year[-_=:%2D]?)(20\d{2})/i)?.[1];
      if (y || hrefYear) add(y || hrefYear, href);
    }

    for (const select of Array.from(doc.querySelectorAll?.('select') || [])) {
      for (const option of Array.from(select.options || [])) {
        const label = normalizeText(option.textContent || option.innerText || '');
        const value = String(option.value || option.getAttribute?.('data-value') || '').trim();
        const y = label.match(/\b(20\d{2})\b/)?.[1] || value.match(/\b(20\d{2})\b/)?.[1];
        if (y) add(y, /^https?:/i.test(value) || value.startsWith('/') ? value : null, value);
      }
    }

    // Amazon sometimes renders the year picker as a custom menu instead of a <select>.
    for (const el of Array.from(doc.querySelectorAll?.('[data-value], [data-filter], [role="option"], button') || [])) {
      const label = normalizeText(el.innerText || el.textContent || '');
      const raw = String(el.getAttribute?.('data-value') || el.getAttribute?.('data-filter') || '').trim();
      const y = label.match(/^\s*(20\d{2})\s*$/)?.[1] || raw.match(/\b(20\d{2})\b/)?.[1];
      if (y) add(y, null, raw);
    }

    // Last-resort only when no real year picker/options were found. Scanning every 4-digit year
    // in the whole page can mistake product text for an order-history year.
    if (!byYear.size) {
      const pageText = normalizeText(doc?.body?.innerText || doc?.body?.textContent || '');
      const years = Array.from(new Set((pageText.match(/\b20\d{2}\b/g) || []).map(Number)))
        .filter(y => y >= 2000 && y <= new Date().getFullYear() + 1)
        .sort((a, b) => b - a);
      for (const y of years) add(y);
    }

    return Array.from(byYear.entries()).sort((a, b) => b[0] - a[0]).map(([year, url]) => ({ year, url }));
  }

  function inferNextPaginationLink(doc, baseUrl) {
    if (!doc?.querySelectorAll) return null;
    const anchors = Array.from(doc.querySelectorAll('a[href]'));
    const route = historyRouteFromUrl(baseUrl);
    let selectedPage = route.page;
    if (selectedPage == null) {
      for (const selector of ['.a-pagination li.a-selected', '.a-pagination [aria-current="page"]', '[aria-current="page"]', '.s-pagination-selected']) {
        try {
          const el = doc.querySelector(selector);
          const n = Number(normalizeText(el?.innerText || el?.textContent || ''));
          if (Number.isFinite(n) && n >= 1) { selectedPage = n; break; }
        } catch (_) {}
      }
    }

    const numeric = [];
    for (const a of anchors) {
      const n = Number(normalizeText(a.innerText || a.textContent || ''));
      if (!Number.isFinite(n) || n < 1) continue;
      const absolute = absoluteAmazonUrl(a.getAttribute('href') || a.href || '', baseUrl);
      if (absolute) numeric.push({ n, url: absolute });
    }
    numeric.sort((a, b) => a.n - b.n);
    if (selectedPage != null) {
      const exact = numeric.find(x => x.n === selectedPage + 1);
      if (exact) return exact.url;
      if (hasNextPageControl(doc)) {
        const year = route.year || displayedHistoryYear(doc, baseUrl);
        const synthetic = buildHistoryRouteUrl(baseUrl, year, selectedPage + 1);
        if (synthetic) return synthetic;
      }
    } else {
      const pageTwo = numeric.find(x => x.n === 2);
      if (pageTwo) return pageTwo.url;
    }

    const candidateUrls = [...anchors.map(a => absoluteAmazonUrl(a.getAttribute('href') || a.href || '', baseUrl)).filter(Boolean), ...paginationAttributeUrls(doc, baseUrl)];
    const keys = ['startIndex', 'page', 'pageNumber', 'pageNo', 'pageNum'];
    for (const key of keys) {
      const current = paginationNumber(baseUrl, key) ?? (key === 'startIndex' ? 0 : 1);
      const candidates = [];
      for (const absolute of candidateUrls) {
        const value = paginationNumber(absolute, key);
        if (value == null || value <= current) continue;
        candidates.push({ value, url: absolute });
      }
      if (candidates.length) {
        candidates.sort((a, b) => a.value - b.value);
        return candidates[0].url;
      }
    }
    return syntheticNextHistoryUrls(doc, baseUrl)[0] || null;
  }

  function findNextLink(doc, baseUrl) {
    if (!doc?.querySelectorAll) return null;
    // Prefer a concrete page-number route over Amazon's literal #.../pagination/next/ href.
    const inferred = inferNextPaginationLink(doc, baseUrl);
    if (inferred) return inferred;

    const selectors = [
      'a[rel="next"]',
      'ul.a-pagination li.a-last:not(.a-disabled) a',
      '.a-pagination .a-last:not(.a-disabled) a',
      'li.a-last:not(.a-disabled) a',
      'a.s-pagination-next:not(.s-pagination-disabled)',
      'a[aria-label="Go to next page"]',
      'a[aria-label*="next page" i]',
      'a[aria-label*="Next" i]',
      '[data-action="next"] a[href]',
      '[data-testid*="next" i] a[href]'
    ];
    for (const selector of selectors) {
      let link = null;
      try { link = doc.querySelector(selector); } catch (_) {}
      const raw = link?.getAttribute?.('href') || link?.href || link?.getAttribute?.('data-href') || link?.getAttribute?.('data-url');
      const absolute = raw ? absoluteAmazonUrl(raw, baseUrl) : null;
      if (absolute) return absolute;
    }
    for (const a of Array.from(doc.querySelectorAll('a[href]'))) {
      const text = normalizeText(a.innerText || a.textContent || a.getAttribute?.('aria-label') || a.getAttribute?.('title') || '').toLowerCase();
      if (!/(^|\b)next(?:\s+page)?(?:\b|\s*[→›»])/.test(text)) continue;
      if (a.closest?.('.a-disabled') || a.getAttribute?.('aria-disabled') === 'true') continue;
      const absolute = absoluteAmazonUrl(a.getAttribute('href') || a.href || '', baseUrl);
      if (absolute) return absolute;
    }
    return null;
  }

  function hasNextPageControl(doc) {
    if (!doc?.querySelectorAll) return false;
    const selectors = [
      'a[rel="next"]', 'ul.a-pagination li.a-last:not(.a-disabled) a', '.a-pagination .a-last:not(.a-disabled) a',
      'li.a-last:not(.a-disabled) a', 'a.s-pagination-next:not(.s-pagination-disabled)',
      'button[aria-label*="next" i]:not([disabled])', '[role="button"][aria-label*="next" i]',
      'input[type="submit"][value*="next" i]', '[data-action="next"]', '[data-testid*="next" i]'
    ];
    for (const selector of selectors) {
      try {
        const el = doc.querySelector(selector);
        if (el && el.getAttribute?.('aria-disabled') !== 'true' && !el.closest?.('.a-disabled')) return true;
      } catch (_) {}
    }
    for (const el of Array.from(doc.querySelectorAll('a, button, [role="button"], input[type="submit"], li'))) {
      const text = normalizeText(el.innerText || el.textContent || el.value || el.getAttribute?.('aria-label') || el.getAttribute?.('title') || '').toLowerCase();
      if (!/(^|\b)next(?:\s+page)?(?:\b|\s*[→›»])/.test(text)) continue;
      if (el.disabled || el.getAttribute?.('aria-disabled') === 'true' || el.closest?.('.a-disabled')) continue;
      return true;
    }
    return false;
  }

  function nextPageCandidates(doc, baseUrl) {
    const out = [];
    const seen = new Set();
    const add = value => {
      const url = absoluteAmazonUrl(value, baseUrl);
      if (!url) return;
      const key = historyLocationKey(url);
      if (seen.has(key)) return;
      seen.add(key);
      out.push(url);
    };
    add(inferNextPaginationLink(doc, baseUrl));
    add(findNextLink(doc, baseUrl));
    for (const url of syntheticNextHistoryUrls(doc, baseUrl)) add(url);
    return out;
  }

  function extractOrderHistoryLinks(doc, baseUrl) {
    if (!isOrderHistoryPage(doc, baseUrl)) return [];
    const links = [];
    const seen = new Set();
    const baseKey = historyLocationKey(baseUrl);
    const add = value => {
      const url = absoluteAmazonUrl(value, baseUrl);
      if (!url) return;
      const key = historyLocationKey(url);
      if (seen.has(key) || key === baseKey) return;
      seen.add(key);
      links.push(url);
    };

    const next = findNextLink(doc, baseUrl);
    if (next) add(next);
    for (const entry of extractHistoryYearLinks(doc, baseUrl)) add(entry.url);

    // Retain explicit legacy year links Amazon may expose outside the year picker, but do not queue
    // every numbered pager anchor at once. Pagination is intentionally advanced one page at a time.
    for (const a of Array.from(doc.querySelectorAll('a[href]'))) {
      const href = String(a.getAttribute('href') || '');
      if (/orderFilter=year[-_%:]?\d{4}/i.test(href) || (/order-history/i.test(href) && /year[-_%:]?\d{4}/i.test(href))) add(href);
    }
    return links.slice(0, 240);
  }

  function strongReturnEvidence(text) {
    const t = normalizeText(text).toLowerCase();
    if (!t) return false;
    if (/return or replace items?|start a return|eligible for return/.test(t) && !/(return (?:request|started|initiated|received|complete|in transit|shipped)|dropped off|refund (?:issued|credited|processed|pending)|check return.*refund status)/.test(t)) return false;
    return /(return (?:request (?:confirmed|accepted)|started|initiated|received|complete|completed|in transit|shipped)|dropped off|drop-off complete|refund (?:issued|credited|processed|pending)|your refund|check return\s*(?:&|and)\s*refund status)/.test(t);
  }

  function parseDocument(doc, url) {
    const bodyText = normalizeText(doc?.body?.innerText || doc?.body?.textContent || '');
    const pageType = inferPageType(bodyText, url);
    const returnMeta = returnUrlMetadata(url);
    const returnToken = returnMeta.returnToken;
    const detailPage = isOrderDetailPage(url);
    const extractedOrderIds = extractOrderIds(bodyText);
    const urlOrderId = orderIdFromUrl(url);
    // On Order Details and Return Center pages, the order ID in Amazon's URL is authoritative.
    // Related links can contain other order IDs and previously caused the parser to scope itself
    // to the wrong DOM box, losing the order total/payment fields from the full page.
    const orderIds = ((detailPage || pageType === 'return') && urlOrderId)
      ? [urlOrderId]
      : extractedOrderIds.slice();
    if (urlOrderId && !orderIds.includes(urlOrderId)) orderIds.unshift(urlOrderId);
    const records = [];
    const detailLinks = extractOrderDetailLinks(doc, url);
    const returnLinks = extractReturnStatusLinks(doc, url);
    const detailByOrder = new Map(detailLinks.map(link => [link.orderId, link.url]));

    for (const orderId of orderIds) {
      let container = isOrderHistoryPage(doc, url) ? historyContainerForOrder(doc, orderId) : closestContainerForOrder(doc, orderId);
      if ((detailPage || pageType === 'return') && orderIds.length === 1) container = doc?.body || container;
      const containerText = container ? normalizeText(container.innerText || container.textContent || '') : contextAround(bodyText, orderId);
      const context = (detailPage || pageType === 'return') && orderIds.length === 1 ? bodyText : (containerText.length >= 80 ? containerText : contextAround(bodyText, orderId));
      const paymentEvidenceText = extractPaymentEvidenceText(container || doc?.body);
      const record = parseTextRecord(context, orderId, {
        pageType,
        paymentText: paymentEvidenceText,
        returnToken,
        returnItemId: returnMeta.returnItemId,
        returnContractId: returnMeta.returnContractId,
        returnRmaId: returnMeta.returnRmaId,
        returnStatusUrl: pageType === 'return' ? url : null,
        url,
        host: (() => { try { return new URL(url).host; } catch (_) { return null; } })(),
        title: doc?.title || null,
        orderDetailsUrl: detailPage ? url : (detailByOrder.get(orderId) || null),
        detailScanComplete: false,
        forceRecordType: pageType === 'return' ? 'return' : 'order'
      });
      const domNames = extractItemNamesFromContainer(container);
      const asins = extractAsins(container);
      if (domNames.length && !(pageType === 'return' && record.itemNames?.length)) record.itemNames = domNames;
      record.asins = asins;

      if (detailPage && record.recordType === 'order') {
        record.detailScanComplete = isCompleteCanonicalDetail(record, url);
        record.detailScannedAt = record.detailScanComplete ? new Date().toISOString() : null;
        // Order Details' Refund Total is the canonical order-level refund figure. Keep it separate
        // from child-return amounts so the dashboard can never inflate the order by summing
        // duplicated return-page totals.
        const canonicalRefundTotal = findOrderRefundTotal(context);
        record.canonicalRefundTotal = canonicalRefundTotal != null && Number.isFinite(Number(canonicalRefundTotal)) ? Number(canonicalRefundTotal) : null;
      }

      if (pageType === 'return') {
        const returnItems = extractReturnItemEntries(container || doc?.body);
        const groupRefundRaw = record.refundAmount ?? record.refundSubtotal;
        const groupRefundAmount = groupRefundRaw === null || groupRefundRaw === undefined || groupRefundRaw === ''
          ? null
          : (Number.isFinite(Number(groupRefundRaw)) ? Number(groupRefundRaw) : null);
        if (returnItems.length) {
          for (const item of returnItems) {
            const itemRefund = item.refundAmount === null || item.refundAmount === undefined || item.refundAmount === ''
              ? null
              : (Number.isFinite(Number(item.refundAmount)) ? Number(item.refundAmount) : null);
            const singleItemGroup = returnItems.length === 1;
            const scopedRefund = itemRefund ?? (singleItemGroup ? groupRefundAmount : null);
            const itemRecord = {
              ...record,
              itemNames: item.itemName ? [item.itemName] : [],
              asins: item.asin ? [item.asin] : [],
              returnItemId: singleItemGroup ? record.returnItemId : null,
              refundAmount: scopedRefund,
              refundSubtotal: scopedRefund,
              returnGroupRefundAmount: groupRefundAmount,
              refundAmountScope: itemRefund != null || (singleItemGroup && groupRefundAmount != null) ? 'item' : (groupRefundAmount != null ? 'return' : null),
              itemIdentitySource: (item.itemName || item.asin) ? 'return-page-item' : null,
              provisionalReturn: false,
              authoritativeReturnCapture: true
            };
            itemRecord.recordId = makeRecordId(itemRecord);
            records.push(itemRecord);
          }
        } else {
          record.provisionalReturn = false;
          record.authoritativeReturnCapture = true;
          record.returnGroupRefundAmount = groupRefundAmount;
          record.refundAmountScope = (record.itemNames || []).length === 1 ? 'item' : (groupRefundAmount != null ? 'return' : null);
          record.itemIdentitySource = (record.itemNames || []).length ? 'return-page-item' : null;
          record.recordId = makeRecordId(record);
          records.push(record);
        }
      } else {
        record.recordId = makeRecordId(record);
        records.push(record);
      }

      // Amazon Business sometimes shows a return-status sentence on the order card without a
      // dedicated return-status anchor. Treat only strong lifecycle text as evidence; the generic
      // "Return or replace items" action is intentionally excluded.
      if (pageType !== 'return' && strongReturnEvidence(context) && !(detailPage && returnLinks.some(link => link.orderId === orderId))) {
        const linked = returnLinks.find(x => x.orderId === orderId) || null;
        const milestones = parseReturnMilestones(context);
        const provisional = {
          recordType: 'return', orderId,
          itemNames: linked?.itemNames || [], asins: linked?.asins || [],
          orderDate: record.orderDate || null, returnDate: record.returnDate || null,
          purchaseAmount: null, refundSubtotal: findLabeledMoney(context, ['Refund subtotal']), refundAmount: findRefundAmount(context),
          cardLast4: record.cardLast4 || null, refundMethod: /original payment method/i.test(context) ? 'original payment method' : null,
          status: classifyStatus(context, 'return'), returnStage: milestones.stage, returnMilestones: milestones,
          expectedCreditDate: milestones.expectedCreditDate || null, statusText: extractStatusText(context) || 'Amazon return status detected',
          returnToken: linked?.returnToken || `status-${slug(orderId)}`,
          returnStatusUrl: linked?.url || null,
          sourceUrl: url, sourceHost: (() => { try { return new URL(url).host; } catch (_) { return null; } })(), pageTitle: doc?.title || null,
          orderDetailsUrl: detailPage ? url : (detailByOrder.get(orderId) || null), detailScanComplete: false, detailScannedAt: null,
          provisionalReturn: true, authoritativeReturnCapture: false
        };
        provisional.recordId = makeRecordId(provisional);
        records.push(provisional);
      }
    }

    // A "View/Check return & refund status" link is evidence that a return exists even before
    // the return page has been crawled. Add a provisional return record immediately so the UI can
    // flag it, then the background return-page job upgrades it with exact item/refund milestones.
    if (pageType !== 'return') {
      for (const link of returnLinks) {
        const token = link.returnToken || slug(link.url);
        const provisional = {
          recordType: 'return',
          orderId: link.orderId,
          itemNames: link.itemNames || [],
          asins: link.asins || [],
          orderDate: null,
          returnDate: null,
          purchaseAmount: null,
          refundSubtotal: null,
          refundAmount: null,
          cardLast4: null,
          refundMethod: null,
          status: 'return_in_progress',
          returnStage: 'started',
          returnMilestones: {
            stage: 'started', expectedCreditDate: null,
            started: { done: true, date: null }, shipped: { done: false, date: null },
            refundIssued: { done: false, date: null }, credited: { done: false, date: null }
          },
          expectedCreditDate: null,
          statusText: 'Amazon return status link detected',
          returnToken: token,
          returnItemId: link.returnItemId || null,
          returnContractId: link.returnContractId || null,
          returnRmaId: link.returnRmaId || null,
          itemIdentitySource: link.itemIdentitySource || null,
          returnStatusUrl: link.url,
          sourceUrl: url,
          sourceHost: (() => { try { return new URL(url).host; } catch (_) { return null; } })(),
          pageTitle: doc?.title || null,
          orderDetailsUrl: detailByOrder.get(link.orderId) || null,
          detailScanComplete: false,
          detailScannedAt: null,
          provisionalReturn: true,
          authoritativeReturnCapture: false
        };
        provisional.recordId = makeRecordId(provisional);
        records.push(provisional);
      }
    }

    const deduped = [];
    const seen = new Set();
    for (const record of records) {
      if (!seen.has(record.recordId)) {
        seen.add(record.recordId);
        deduped.push(record);
      }
    }

    return {
      pageType,
      isOrderDetailPage: detailPage,
      isOrderHistoryPage: isOrderHistoryPage(doc, url),
      records: deduped,
      detailLinks,
      returnLinks,
      historyPageLinks: extractOrderHistoryLinks(doc, url),
      nextPageUrl: findNextLink(doc, url),
      nextPageCandidates: nextPageCandidates(doc, url),
      hasNextPageControl: hasNextPageControl(doc),
      historyOrderIds: isOrderHistoryPage(doc, url) ? extractOrderIds(bodyText) : [],
      historyVisibleCount: isOrderHistoryPage(doc, url) ? extractOrderIds(bodyText).length : 0,
      historyTotalOrders: isOrderHistoryPage(doc, url) ? totalOrdersForCurrentFilter(doc) : null,
      historyDisplayedYear: isOrderHistoryPage(doc, url) ? displayedHistoryYear(doc, url) : null,
      historyTimeFilterValue: isOrderHistoryPage(doc, url) ? historyTimeFilterState(doc).value : null,
      historySelectedYear: isOrderHistoryPage(doc, url) ? historyTimeFilterState(doc).year : null,
      historyYears: isOrderHistoryPage(doc, url) ? extractHistoryYearLinks(doc, url).map(x => x.year) : [],
      scannedUrl: url,
      title: doc?.title || null
    };
  }

  window.AmazonRefundParser = {
    normalizeText,
    parseMoney,
    findLabeledMoney,
    findOrderTotal,
    findRefundAmount,
    findOrderRefundTotal,
    findCardLast4,
    extractPaymentEvidenceText,
    extractReturnItemEntries,
    isCompleteCanonicalDetail,
    extractOrderIds,
    inferPageType,
    classifyStatus,
    classifyReturnStage,
    parseReturnMilestones,
    findExpectedCreditDate,
    extractStatusText,
    parseTextRecord,
    parseDocument,
    makeRecordId,
    extractOrderDetailLinks,
    extractReturnStatusLinks,
    returnUrlMetadata,
    nearestReturnItemEvidence,
    extractOrderHistoryLinks,
    extractHistoryYearLinks,
    historyYearFromUrl,
    historyRouteFromUrl,
    buildHistoryRouteUrl,
    buildServerHistoryUrl,
    historyLocationKey,
    historyTimeFilterState,
    displayedHistoryYear,
    syntheticNextHistoryUrls,
    nextPageCandidates,
    findNextLink,
    inferNextPaginationLink,
    hasNextPageControl,
    isOrderDetailPage,
    isOrderHistoryPage,
    closestContainerForOrder,
    extractItemNamesFromContainer,
    orderIdFromUrl
  };
})();
