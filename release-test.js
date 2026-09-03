const fs = require('fs');
const crypto = require('crypto');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const manifest = JSON.parse(fs.readFileSync(__dirname + '/manifest.json', 'utf8'));
const pkg = JSON.parse(fs.readFileSync(__dirname + '/package.json', 'utf8'));
const updater = fs.readFileSync(__dirname + '/dev-updater.js', 'utf8');
const nativeHost = fs.readFileSync(__dirname + '/tools/dev-updater/NativeHost.cs', 'utf8');
const installer = fs.readFileSync(__dirname + '/tools/dev-updater/Install.ps1', 'utf8');
const ci = fs.readFileSync(__dirname + '/.github/workflows/ci.yml', 'utf8');

assert(manifest.version === pkg.version, 'manifest.json and package.json versions must match');
assert(manifest.version_name === manifest.version, 'manifest version_name must match version');
assert(manifest.background?.service_worker === 'service-worker.js', 'service-worker.js must wrap the existing background worker and dev updater');
assert(Array.isArray(manifest.permissions) && manifest.permissions.includes('nativeMessaging'), 'nativeMessaging permission is required for the local updater bridge');
assert(typeof manifest.key === 'string' && manifest.key.length > 100, 'development manifest key must be present for a stable extension ID');

const publicKeyDer = Buffer.from(manifest.key, 'base64');
const hash = crypto.createHash('sha256').update(publicKeyDer).digest().subarray(0, 16);
const extensionId = Array.from(hash, byte =>
  String.fromCharCode(97 + (byte >> 4)) + String.fromCharCode(97 + (byte & 15))
).join('');
const expectedId = 'hhmimkpolikhncnbkkbbabbopbccabcf';
assert(extensionId === expectedId, `manifest key must resolve to fixed development extension ID ${expectedId}`);

const expectedHost = 'com.supremefabworks.amazon_order_manager_updater';
const expectedOrigin = `chrome-extension://${expectedId}/`;
assert(updater.includes(expectedHost), 'extension updater must use the fixed native host name');
assert(nativeHost.includes(expectedHost), 'native host source must use the same host name');
assert(nativeHost.includes(expectedOrigin), 'native host must hard-restrict the caller origin');
assert(installer.includes(expectedHost) && installer.includes(expectedId), 'installer must register the same host and extension ID');

assert(ci.includes('amazon-order-manager.zip.sha256'), 'CI must emit the extension SHA-256 sidecar');
assert(ci.includes('amazon-order-manager-dev-updater.zip'), 'CI must package the one-time Windows dev updater installer');
assert(ci.includes('gh release create'), 'main CI must publish a GitHub development release');
assert(ci.includes('dev-v${VERSION}'), 'development release tags must be versioned from the manifest');
assert(pkg.scripts.test.includes('dev-updater-test.js') && pkg.scripts.test.includes('release-test.js'), 'updater and release invariants must be part of npm test');

console.log(`release invariants passed for v${manifest.version} (${extensionId})`);
