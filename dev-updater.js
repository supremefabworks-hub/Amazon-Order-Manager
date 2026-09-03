'use strict';

const DEV_UPDATE_HOST_NAME = 'com.supremefabworks.amazon_order_manager_updater';
const DEV_UPDATE_PROTOCOL = 'arl-dev-updater-v1';
const DEV_UPDATE_ALARM_NAME = 'arl-dev-auto-update';
const DEV_UPDATE_STATUS_KEY = 'devUpdateStatus';
const DEV_UPDATE_PERIOD_MINUTES = 15;
const DEV_UPDATE_INITIAL_DELAY_MINUTES = 0.5;
const DEV_UPDATE_BOOT_THROTTLE_MS = 5 * 60 * 1000;
const DEV_AUTO_UPDATE_ENABLED = true;

let devUpdateCheckInFlight = null;

function extensionVersionParts(value) {
  const text = String(value || '').trim();
  if (!/^\d+(?:\.\d+){0,3}$/.test(text)) return null;
  const parts = text.split('.').map(Number);
  if (parts.some(part => !Number.isInteger(part) || part < 0 || part > 65535)) return null;
  while (parts.length < 4) parts.push(0);
  return parts;
}

function compareExtensionVersions(a, b) {
  const left = extensionVersionParts(a);
  const right = extensionVersionParts(b);
  if (!left || !right) return null;
  for (let i = 0; i < 4; i += 1) {
    if (left[i] > right[i]) return 1;
    if (left[i] < right[i]) return -1;
  }
  return 0;
}

async function readDevUpdateStatus() {
  try {
    const data = await chrome.storage.local.get([DEV_UPDATE_STATUS_KEY]);
    return data?.[DEV_UPDATE_STATUS_KEY] || null;
  } catch (_) { return null; }
}

async function writeDevUpdateStatus(status) {
  try {
    const previous = await readDevUpdateStatus() || {};
    await chrome.storage.local.set({
      [DEV_UPDATE_STATUS_KEY]: {
        ...previous,
        ...status,
        updatedAt: new Date().toISOString()
      }
    });
  } catch (_) {}
}

async function ensureDevUpdateAlarm() {
  if (!DEV_AUTO_UPDATE_ENABLED) return { ok: true, enabled: false };
  try {
    let existing = null;
    try { existing = await chrome.alarms.get(DEV_UPDATE_ALARM_NAME); } catch (_) {}
    if (!existing || Number(existing.periodInMinutes) !== DEV_UPDATE_PERIOD_MINUTES) {
      const options = {
        delayInMinutes: DEV_UPDATE_INITIAL_DELAY_MINUTES,
        periodInMinutes: DEV_UPDATE_PERIOD_MINUTES,
        persistAcrossSessions: true
      };
      try {
        await chrome.alarms.create(DEV_UPDATE_ALARM_NAME, options);
      } catch (_) {
        delete options.persistAcrossSessions;
        await chrome.alarms.create(DEV_UPDATE_ALARM_NAME, options);
      }
    }
    return { ok: true, enabled: true };
  } catch (error) {
    const message = error?.message || String(error);
    await writeDevUpdateStatus({ alarmOk: false, error: `Update alarm: ${message}` });
    return { ok: false, error: message };
  }
}

async function performDevUpdateCheck(reason = 'scheduled') {
  if (!DEV_AUTO_UPDATE_ENABLED) return { ok: true, enabled: false, updated: false };

  const currentVersion = chrome.runtime.getManifest()?.version || null;
  if (!currentVersion || !extensionVersionParts(currentVersion)) {
    return { ok: false, updated: false, error: 'Current extension version is invalid.' };
  }

  await writeDevUpdateStatus({
    ok: null,
    checking: true,
    reason,
    currentVersion,
    lastCheckStartedAt: new Date().toISOString(),
    error: null
  });

  const request = {
    protocol: DEV_UPDATE_PROTOCOL,
    action: 'check_update',
    currentVersion,
    extensionId: chrome.runtime.id || null,
    reason
  };

  let response;
  try {
    response = await chrome.runtime.sendNativeMessage(DEV_UPDATE_HOST_NAME, request);
  } catch (error) {
    const message = error?.message || String(error);
    await writeDevUpdateStatus({
      ok: false,
      checking: false,
      hostAvailable: false,
      reason,
      currentVersion,
      error: message,
      lastCheckedAt: new Date().toISOString()
    });
    return { ok: false, updated: false, hostAvailable: false, currentVersion, error: message };
  }

  if (!response || response.protocol !== DEV_UPDATE_PROTOCOL) {
    const error = 'Native updater returned an invalid protocol response.';
    await writeDevUpdateStatus({ ok: false, checking: false, hostAvailable: true, reason, currentVersion, error, lastCheckedAt: new Date().toISOString() });
    return { ok: false, updated: false, hostAvailable: true, currentVersion, error };
  }

  if (response.ok !== true) {
    const error = response.error || 'Native updater reported an error.';
    await writeDevUpdateStatus({
      ok: false, checking: false, hostAvailable: true, reason, currentVersion,
      latestVersion: response.latestVersion || null, error, lastCheckedAt: new Date().toISOString()
    });
    return { ok: false, updated: false, hostAvailable: true, currentVersion, latestVersion: response.latestVersion || null, error };
  }

  const installedVersion = response.installedVersion || response.latestVersion || null;
  const comparison = installedVersion ? compareExtensionVersions(installedVersion, currentVersion) : null;
  const shouldReload = response.updated === true && comparison === 1;
  const now = new Date().toISOString();
  const result = {
    ok: true,
    updated: shouldReload,
    hostAvailable: true,
    currentVersion,
    latestVersion: response.latestVersion || installedVersion || currentVersion,
    installedVersion: installedVersion || currentVersion,
    status: response.status || (shouldReload ? 'updated' : 'up_to_date')
  };

  await writeDevUpdateStatus({
    ...result,
    checking: false,
    reason,
    error: null,
    lastCheckedAt: now,
    ...(shouldReload ? { lastInstalledAt: now, lastReloadRequestedAt: now } : {})
  });

  // MV3 service workers may be suspended before a timer callback runs. Reload synchronously after
  // the verified install instead of relying on a setTimeout that may never fire.
  if (shouldReload) {
    try { chrome.runtime.reload(); }
    catch (error) {
      await writeDevUpdateStatus({ ok: false, checking: false, error: `Reload failed: ${error?.message || error}` });
      return { ...result, ok: false, updated: false, error: error?.message || String(error) };
    }
  }

  return result;
}

function checkForDevUpdate(reason = 'scheduled') {
  if (devUpdateCheckInFlight) return devUpdateCheckInFlight;
  devUpdateCheckInFlight = performDevUpdateCheck(reason)
    .finally(() => { devUpdateCheckInFlight = null; });
  return devUpdateCheckInFlight;
}

async function initializeDevUpdater(reason = 'worker-start', force = false) {
  await ensureDevUpdateAlarm();
  if (!force) {
    const status = await readDevUpdateStatus();
    const last = status?.lastCheckedAt ? new Date(status.lastCheckedAt).getTime() : 0;
    if (Number.isFinite(last) && Date.now() - last < DEV_UPDATE_BOOT_THROTTLE_MS) {
      return { ok: true, skipped: true, reason: 'recently-checked', currentVersion: chrome.runtime.getManifest()?.version || null };
    }
  }
  return checkForDevUpdate(reason);
}

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm?.name === DEV_UPDATE_ALARM_NAME) checkForDevUpdate('alarm').catch(() => {});
});

chrome.runtime.onStartup.addListener(() => {
  initializeDevUpdater('startup', true).catch(() => {});
});

chrome.runtime.onInstalled.addListener(() => {
  ensureDevUpdateAlarm().catch(() => {});
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'ARL_CHECK_DEV_UPDATE') {
    initializeDevUpdater('manual', true)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ ok: false, updated: false, error: error?.message || String(error) }));
    return true;
  }

  if (message?.type === 'ARL_GET_DEV_UPDATE_STATUS') {
    readDevUpdateStatus()
      .then(status => sendResponse({ ok: true, status }))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
});

// Important update checks must exist whenever the MV3 worker starts. Chrome explicitly recommends
// recreating important alarms at worker startup because alarm persistence can vary across versions.
initializeDevUpdater('worker-start').catch(() => {});
