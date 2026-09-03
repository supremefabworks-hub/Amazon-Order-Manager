const fs = require('fs');
const vm = require('vm');
function assert(condition, message) { if (!condition) throw new Error(message); }

(async () => {
  const alarms = [];
  const listeners = { alarm: [], startup: [], installed: [], message: [] };
  const statusWrites = [];
  const nativeCalls = [];
  let reloadCount = 0;
  let storedStatus = null;
  let nativeResponse = { protocol:'arl-dev-updater-v1', ok:true, updated:false, status:'up_to_date', latestVersion:'0.18.2', installedVersion:'0.18.2' };
  const chrome = {
    alarms: {
      async get() { return null; },
      async create(name, options) { alarms.push({ name, options }); },
      onAlarm: { addListener: fn => listeners.alarm.push(fn) }
    },
    storage: { local: {
      async get() { return storedStatus ? { devUpdateStatus: storedStatus } : {}; },
      async set(value) { statusWrites.push(value); if (value.devUpdateStatus) storedStatus = value.devUpdateStatus; }
    } },
    runtime: {
      id:'hhmimkpolikhncnbkkbbabbopbccabcf', getManifest:()=>({version:'0.18.2'}),
      async sendNativeMessage(host,message) { nativeCalls.push({host,message}); if (nativeResponse instanceof Error) throw nativeResponse; return nativeResponse; },
      reload(){ reloadCount += 1; },
      onStartup:{addListener:fn=>listeners.startup.push(fn)}, onInstalled:{addListener:fn=>listeners.installed.push(fn)}, onMessage:{addListener:fn=>listeners.message.push(fn)}
    }
  };
  const sandbox = { chrome, console, Date, Promise, setTimeout, clearTimeout };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(__dirname + '/dev-updater.js','utf8'), sandbox);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert(alarms.some(entry => entry.name === 'arl-dev-auto-update' && entry.options.periodInMinutes === 15), 'worker startup must recreate a 15-minute update alarm');
  assert(nativeCalls.some(call => call.message.reason === 'worker-start'), 'worker startup must perform an immediate updater check');

  nativeResponse = { protocol:'arl-dev-updater-v1', ok:true, updated:true, status:'updated', latestVersion:'0.18.3', installedVersion:'0.18.3' };
  const updated = await sandbox.initializeDevUpdater('manual-test', true);
  assert(updated.ok === true && updated.updated === true, 'strictly newer verified native install must be accepted');
  assert(reloadCount === 1, 'successful install must request reload synchronously exactly once');
  assert(nativeCalls.at(-1).host === 'com.supremefabworks.amazon_order_manager_updater', 'native updater host name must remain fixed');

  nativeResponse = new Error('Specified native messaging host not found.');
  const missing = await sandbox.initializeDevUpdater('missing-host-test', true);
  assert(missing.ok === false && missing.hostAvailable === false, 'missing native host must fail closed and expose host availability');
  assert(storedStatus && storedStatus.error, 'native host failure must persist an updater diagnostic');
  assert(statusWrites.length >= 3, 'updater must persist check/install/error status');
  console.log('development auto-update tests passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
