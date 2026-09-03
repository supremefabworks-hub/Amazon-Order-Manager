'use strict';

const DEV_UPDATE_HOST_NAME = 'com.supremefabworks.amazon_order_manager_updater';
const DEV_UPDATE_PROTOCOL = 'arl-dev-updater-v1';
const DEV_UPDATE_ALARM_NAME = 'arl-dev-auto-update';
const DEV_UPDATE_STATUS_KEY = 'devUpdateStatus';
const DEV_UPDATE_PERIOD_MINUTES = 15;
const DEV_UPDATE_INITIAL_DELAY_MINUTES = 1;
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

async function writeDevUpdateStatus(status) {
  try {
    const prior = await chrome.storage.local.get([DEV_UPDATE_STATUS_KEY]);
    const previous = prior?.[DEV_UPDATE_STATUS_KEY] || {};
    await chrome.storage.local.set({
      [DEV_UPDATE_STATUS_KEY]: {
        ...previous,
        ...status,
        updatedAt: new Date().toISOString()
      }
    });
  } catch (_) {}
}

function scheduleDevUpdateAlarm() {
  if (!DEV_AUTO_UPDATE_ENABLED) return;
  try {
    chrome.alarms.create(DEV_UPDATE_ALARM_NAME, {
      delayInMinutes: DEV_UPDATE_INITIAL_DELAY_MINUTES,
      periodInMinutes: DEV_UPDATE_PERIOD_MINUTES
    });
  } catch (_) {}
}

async function performDevUpdateCheck(reason = 'scheduled') {
  if (!DEV_AUTO_UPDATE_ENABLED) return { ok: true, enabled: false, updated: false };

  const currentVersion = chrome.runtime.getManifest()?.version || null;
  if (!currentVersion || !extensionVersionParts(currentVersion)) {
    return { ok: false, updated: false, error: 'Current extension version is invalid.' };
  }

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
      hostAvailable: false,
      reason,
      currentVersion,
      error: message,
      lastCheckedAt: new Date().toISOString()
    });
    return { ok: false, updated: false, hostAvailable: false, error: message };
  }

  if (!response || response.protocol !== DEV_UPDATE_PROTOCOL) {
    const error = 'Native updater returned an invalid protocol response.';
    await writeDevUpdateStatus({
      ok: false,
      hostAvailable: true,
      reason,
      currentVersion,
      error,
      lastCheckedAt: new Date().toISOString()
    });
    return { ok: false, updated: false, hostAvailable: true, error };
  }

  if (response.ok !== true) {
    const error = response.error || 'Native updater reported an error.';
    await writeDevUpdateStatus({
      ok: false,
      hostAvailable: true,
      reason,
      currentVersion,
      latestVersion: response.latestVersion || null,
      error,
      lastCheckedAt: new Date().toISOString()
    });
    return { ok: false, updated: false, hostAvailable: true, error };
  }

  const installedVersion = response.installedVersion || response.latestVersion || null;
  const comparison = installedVersion ? compareExtensionVersions(installedVersion, currentVersion) : null;
  const shouldReload = response.updated === true && comparison === 1;

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
    reason,
    error: null,
    lastCheckedAt: new Date().toISOString(),
    ...(shouldReload ? { lastInstalledAt: new Date().toISOString() } : {})
  });

  if (shouldReload) {
    setTimeout(() => {
      try { chrome.runtime.reload(); } catch (_) {}
    }, 150);
  }

  return result;
}

function checkForDevUpdate(reason = 'scheduled') {
  if (devUpdateCheckInFlight) return devUpdateCheckInFlight;
  devUpdateCheckInFlight = performDevUpdateCheck(reason)
    .finally(() => { devUpdateCheckInFlight = null; });
  return devUpdateCheckInFlight;
}

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm?.name === DEV_UPDATE_ALARM_NAME) checkForDevUpdate('alarm').catch(() => {});
});

chrome.runtime.onStartup.addListener(() => {
  scheduleDevUpdateAlarm();
  checkForDevUpdate('startup').catch(() => {});
});

chrome.runtime.onInstalled.addListener(() => {
  scheduleDevUpdateAlarm();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'ARL_CHECK_DEV_UPDATE') {
    checkForDevUpdate('manual')
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ ok: false, updated: false, error: error?.message || String(error) }));
    return true;
  }

  if (message?.type === 'ARL_GET_DEV_UPDATE_STATUS') {
    chrome.storage.local.get([DEV_UPDATE_STATUS_KEY])
      .then(data => sendResponse({ ok: true, status: data?.[DEV_UPDATE_STATUS_KEY] || null }))
      .catch(error => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
});

scheduleDevUpdateAlarm();
