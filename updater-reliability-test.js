const fs = require('fs');
function assert(condition, message) { if (!condition) throw new Error(message); }
const updater = fs.readFileSync(__dirname + '/dev-updater.js','utf8');
const popup = fs.readFileSync(__dirname + '/popup.html','utf8') + fs.readFileSync(__dirname + '/popup.js','utf8');
const host = fs.readFileSync(__dirname + '/tools/dev-updater/NativeHost.cs','utf8');
const installer = fs.readFileSync(__dirname + '/tools/dev-updater/Install.ps1','utf8');
assert(updater.includes("initializeDevUpdater('worker-start')"), 'updater must check whenever the MV3 worker starts');
assert(updater.includes('persistAcrossSessions'), 'updater must request alarm persistence where supported');
assert(!updater.includes("setTimeout(() => {\n      try { chrome.runtime.reload()"), 'verified update reload must not depend on a service-worker timer');
assert(popup.includes('Check development update now') && popup.includes('ARL_CHECK_DEV_UPDATE'), 'popup must expose a manual update check');
assert(popup.includes('ARL_GET_DEV_UPDATE_STATUS'), 'popup must expose persisted updater status');
assert(host.includes('updater.log') && host.includes('--self-test'), 'native host must provide file logging and a local self-test');
assert(installer.includes('DiagnoseOnly') && installer.includes('Show-Diagnostics'), 'installer must expose a diagnostics-only mode');
assert(!installer.includes('??'), 'Windows PowerShell 5.1 installer must not use the PowerShell 7 null-coalescing operator');
console.log('updater reliability tests passed');
