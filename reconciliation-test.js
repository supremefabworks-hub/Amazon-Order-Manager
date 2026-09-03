const fs = require('fs');

const manifest = JSON.parse(fs.readFileSync(__dirname + '/manifest.json', 'utf8'));
const pkg = JSON.parse(fs.readFileSync(__dirname + '/package.json', 'utf8'));
if (manifest.version !== pkg.version) throw new Error('manifest/package version mismatch');

const dashboard = fs.readFileSync(__dirname + '/dashboard.js', 'utf8');
for (const token of [
  'amazon-refund-credit-check-request/v1',
  'amazon-refund-credit-check-result/v1',
  'Exported ${pending.length}',
  'bankVerification'
]) {
  if (!dashboard.includes(token)) throw new Error(`missing bank bridge token: ${token}`);
}

const html = fs.readFileSync(__dirname + '/dashboard.html', 'utf8');
if (!html.includes('exportBankRequest') || !html.includes('importBankResult')) throw new Error('bank bridge controls missing');
console.log('bank reconciliation bridge static tests passed');
