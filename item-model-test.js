const fs = require('fs');
const vm = require('vm');
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/item-model.js', 'utf8'), sandbox);
const model = sandbox.window.AmazonOrderItemModel;
function assert(condition, message) { if (!condition) throw new Error(message); }

const order = { orderItems: Array.from({length:6}, (_,i) => ({
  itemKey:`asin:B00000010${i}`, asin:`B00000010${i}`, itemName:`Purchased Product ${i+1} Long Descriptive Title`,
  quantity:1, itemAmount:null, fulfillmentStatus:'Delivered'
})) };
const groups = Array.from({length:4}, (_,i) => ({
  key:`return-${i}`, asins:[`B00000010${i}`], itemNames:[`Purchased Product ${i+1} Long Descriptive Title`], representative:{ returnStage:i < 2 ? 'started' : 'received' }, records:[]
}));
const joined = model.joinOrderItems(order, groups);
assert(joined.items.length === 6, 'six purchased products must remain six product rows');
assert(joined.returnedProductCount === 4, 'exactly four of six products should be associated with returns');
assert(joined.items.filter(item => item.returnGroups.length).length === 4, 'four item rows must carry return lifecycles');
assert(joined.items.filter(item => !item.returnGroups.length).length === 2, 'two purchased products must remain visible as not returned');
assert(joined.unmatchedReturnGroups.length === 0, 'strong ASIN matches should not create unmatched returns');

const truncated = model.joinOrderItems({ orderItems:[{itemKey:'asin:B000000500', asin:null, itemName:'ThermoMaven Sub-1G Smart Wireless Meat Thermometer with Standalone Base'}] }, [
  { key:'return-title', asins:[], itemNames:['ThermoMaven Sub-1G Smart Wireless Meat Thermometer with Standalone Ba…'], representative:{returnStage:'started'}, records:[] }
]);
assert(truncated.returnedProductCount === 1, 'conservative long-title prefix matching must handle Amazon truncation');

const unmatched = model.joinOrderItems(order, [{ key:'unknown', asins:['B999999999'], itemNames:['Different Product'], representative:{returnStage:'started'}, records:[] }]);
assert(unmatched.unmatchedReturnGroups.length === 1 && unmatched.unmatchedReturnGroups[0].identityStrength === 'strong', 'contradictory strong returned ASIN must stay visible as unmatched/reviewable');
console.log('item model tests passed');
