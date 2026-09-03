const fs = require('fs');
const vm = require('vm');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

(async () => {
  const alarms = [];
  const listeners = { alarm: [], startup: [], installed: [], message: [] };
  const statusWrites = [];
  const nativeCalls = [];
  let reloadCount = 0;
  let nativeResponse = {
    protocol: 'arl-dev-updater-v1',
    ok: true,
    updated: true,
    status: 'updated',
    latestVersion: '0.18.1',
    installedVersion: '0.18.1'
  };

  const chrome = {
    alarms: {
      create: (name, options) => alarms.push({ name, options }),
      onAlarm: { addListener: fn => listeners.alarm.push(fn) }
    },
    storage: {
      local: {
        get: async () => ({}),
        set: async value => { statusWrites.push(value); }
      }
    },
    runtime: {
      id: 'hhmimkpolikhncnbkkbbabbopbccabcf',
      getManifest: () => ({ version: '0.18.0' }),
      sendNativeMessage: async (host, message) => {
        nativeCalls.push({ host, message });
        if (nativeResponse instanceof Error) throw nativeResponse;
        return nativeResponse;
      },
      reload: () => { reloadCount += 1; },
      onStartup: { addListener: fn => listeners.startup.push(fn) },
      onInstalled: { addListener: fn => listeners.installed.push(fn) },
      onMessage: { addListener: fn => listeners.message.push(fn) }
    }
  };

  const sandbox = {
    chrome,
    console,
    Date,
    Promise,
    setTimeout: fn => { fn(); return 0; },
    clearTimeout: () => {}
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(__dirname + '/dev-updater.js', 'utf8'), sandbox);

  assert(sandbox.compareExtensionVersions('0.18.1', '0.18.0') === 1, 'newer version must compare greater');
  assert(sandbox.compareExtensionVersions('0.18', '0.18.0') === 0, 'missing version fields must compare as zero');
  assert(sandbox.compareExtensionVersions('0.17.9', '0.18.0') === -1, 'older version must compare lower');
  assert(sandbox.compareExtensionVersions('0.18.beta', '0.18.0') === null, 'invalid versions must be rejected');

  assert(alarms.some(entry => entry.name === 'arl-dev-auto-update' && entry.options.periodInMinutes === 15), 'auto-update alarm must be scheduled every 15 minutes');

  const updated = await sandbox.checkForDevUpdate('test');
  assert(updated.ok === true && updated.updated === true, 'newer verified host result must be accepted');
  assert(reloadCount === 1, 'successful newer install must reload the extension exactly once');
  assert(nativeCalls[0].host === 'com.supremefabworks.amazon_order_manager_updater', 'native updater host name must be fixed');
  assert(nativeCalls[0].message.protocol === 'arl-dev-updater-v1', 'native updater protocol must be versioned');
  assert(nativeCalls[0].message.currentVersion === '0.18.0', 'current manifest version must be sent to the host');

  nativeResponse = {
    protocol: 'arl-dev-updater-v1',
    ok: true,
    updated: true,
    status: 'updated',
    latestVersion: '0.18.0',
    installedVersion: '0.18.0'
  };
  const sameVersion = await sandbox.checkForDevUpdate('test-same');
  assert(sameVersion.updated === false, 'host cannot force reload when installed version is not newer');
  assert(reloadCount === 1, 'same version must not reload');

  nativeResponse = { protocol: 'wrong-protocol', ok: true, updated: true, installedVersion: '0.19.0' };
  const wrongProtocol = await sandbox.checkForDevUpdate('test-protocol');
  assert(wrongProtocol.ok === false, 'invalid host protocol must be rejected');
  assert(reloadCount === 1, 'invalid protocol must not reload');

  nativeResponse = new Error('Specified native messaging host not found.');
  const missingHost = await sandbox.checkForDevUpdate('test-missing-host');
  assert(missingHost.ok === false && missingHost.hostAvailable === false, 'missing native host must fail closed without breaking the extension');
  assert(reloadCount === 1, 'missing native host must not reload');
  assert(statusWrites.length >= 3, 'updater checks should persist diagnostics');

  console.log('development auto-update tests passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
