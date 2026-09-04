(() => {
  'use strict';

  function clean(value) { return String(value || '').trim(); }
  function normalizeTitle(value) {
    return clean(value)
      .replace(/\d{3}-\d{7}-\d{7}/g, ' ')
      .replace(/[.…]+/g, ' ')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }
  function uniqueStrings(values) {
    const out = []; const seen = new Set();
    for (const value of values || []) {
      const s = clean(value); if (!s) continue;
      const key = s.toLowerCase(); if (seen.has(key)) continue;
      seen.add(key); out.push(s);
    }
    return out;
  }
  function normalizeOrderItems(order) {
    const structured = Array.isArray(order?.orderItems) ? order.orderItems.filter(Boolean) : [];
    if (structured.length) return structured.map((item, index) => ({
      itemKey: clean(item.itemKey) || (item.asin ? `asin:${clean(item.asin).toUpperCase()}` : `item:${index}`),
      asin: clean(item.asin).toUpperCase() || null,
      itemName: clean(item.itemName) || `Order item ${index + 1}`,
      quantity: Number.isInteger(Number(item.quantity)) && Number(item.quantity) > 0 ? Number(item.quantity) : null,
      itemAmount: item.itemAmount === null || item.itemAmount === undefined || item.itemAmount === '' || !Number.isFinite(Number(item.itemAmount)) ? null : Number(item.itemAmount),
      fulfillmentStatus: clean(item.fulfillmentStatus) || null,
      source: clean(item.source) || null
    }));

    const names = uniqueStrings(order?.itemNames || []);
    const asins = uniqueStrings(order?.asins || []).map(value => value.toUpperCase());
    const alignAsins = asins.length === names.length;
    return names.map((itemName, index) => ({
      itemKey: alignAsins && asins[index] ? `asin:${asins[index]}` : `title:${normalizeTitle(itemName).slice(0, 100)}`,
      asin: alignAsins ? (asins[index] || null) : null,
      itemName,
      quantity: null,
      itemAmount: null,
      fulfillmentStatus: null,
      source: 'legacy-order-item'
    }));
  }

  function identityEvidence(group) {
    return {
      asins: new Set(uniqueStrings(group?.asins || []).map(value => value.toUpperCase())),
      titles: uniqueStrings(group?.itemNames || []).map(normalizeTitle).filter(Boolean)
    };
  }

  function itemMatchScore(item, group) {
    const evidence = identityEvidence(group);
    const asin = clean(item?.asin).toUpperCase();
    if (asin && evidence.asins.has(asin)) return 100;
    const title = normalizeTitle(item?.itemName);
    if (!title) return 0;
    let best = 0;
    for (const returnedTitle of evidence.titles) {
      if (!returnedTitle) continue;
      if (title === returnedTitle) best = Math.max(best, 80);
      else {
        const shorter = title.length <= returnedTitle.length ? title : returnedTitle;
        const longer = title.length > returnedTitle.length ? title : returnedTitle;
        if (shorter.length >= 24 && shorter.split(' ').length >= 4 && longer.startsWith(shorter)) best = Math.max(best, 70);
      }
    }
    return best;
  }

  function joinOrderItems(order, returnGroups) {
    const items = normalizeOrderItems(order).map(item => ({ ...item, returnGroups: [] }));
    const unmatchedReturnGroups = [];
    for (const group of returnGroups || []) {
      const scores = items.map((item, index) => ({ index, score: itemMatchScore(item, group) })).sort((a,b) => b.score - a.score);
      const best = scores[0] || { index: -1, score: 0 };
      const tied = best.score > 0 && scores.filter(entry => entry.score === best.score).length > 1;
      if (best.score >= 70 && !tied && items[best.index]) {
        items[best.index].returnGroups.push(group);
      } else {
        const evidence = identityEvidence(group);
        unmatchedReturnGroups.push({ group, identityStrength: evidence.asins.size ? 'strong' : 'weak', bestScore: best.score });
      }
    }
    return {
      items,
      unmatchedReturnGroups,
      returnedProductCount: items.filter(item => item.returnGroups.length).length
    };
  }

  window.AmazonOrderItemModel = { normalizeTitle, normalizeOrderItems, itemMatchScore, joinOrderItems };
})();
