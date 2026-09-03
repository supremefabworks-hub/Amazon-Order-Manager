# Windows development auto-updater

This package is the one-time local bootstrap for the Amazon Order Manager development channel.

## What it installs

- Extension files under `%LOCALAPPDATA%\SupremeFabWorks\AmazonOrderManagerDev\current`.
- A small native messaging host under the sibling `host` directory.
- One HKCU Chrome native-messaging registration restricted to development extension ID `hhmimkpolikhncnbkkbbabbopbccabcf`.

The host does not receive Amazon credentials, cookies, passwords, bank credentials, or bank-provider tokens. It only receives the extension version/update-check request.

## One-time setup

1. Extract `amazon-order-manager-dev-updater.zip`.
2. Open PowerShell in the extracted folder.
3. Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
```

4. Open `chrome://extensions`, enable Developer mode, remove any older unpacked copy, choose **Load unpacked**, and select the exact `current` folder printed by the installer.

That is the final manual reload/install cycle for the development channel. Future versioned builds merged to `main` become `dev-v<version>` GitHub prereleases. The extension checks the native host at Chrome startup and every 15 minutes. The host downloads the ZIP and its SHA-256 sidecar, validates both the digest and embedded manifest version, stages the replacement, and reports success. Only then does the extension call `chrome.runtime.reload()`.

## Fail-safe behavior

- No native host installed: extension continues running; the update check records an unavailable-host diagnostic.
- GitHub unavailable: current build remains untouched.
- Digest mismatch: current build remains untouched.
- Invalid/missing package files or version mismatch: current build remains untouched.
- Install swap failure: the updater attempts to restore the previous `current` directory and does not tell Chrome to reload.

The previous successful extension directory is retained as `previous` until the next successful update.

## Production boundary

This is a development-only mechanism. Before Chrome Web Store production release, remove/disable the local native updater, replace the development manifest key/ID policy as appropriate, disable the destructive development version reset, and use schema/data migrations plus Chrome Web Store updates.
