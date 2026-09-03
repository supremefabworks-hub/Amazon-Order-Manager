# Restore the exact v0.16.0 snapshot

The v0.16.0 ZIP was stored as ordered Base64 text chunks because the GitHub connector could not safely upload the binary archive in one request.

From this directory on macOS/Linux:

```bash
cat amazon-refund-ledger-v0.16.0.zip.b64.part* > amazon-refund-ledger-v0.16.0.zip.b64
base64 -d amazon-refund-ledger-v0.16.0.zip.b64 > amazon-refund-ledger-v0.16.0.zip
sha256sum amazon-refund-ledger-v0.16.0.zip
```

Expected SHA-256:

```text
0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42
```

Expected ZIP size: **77,670 bytes**.

Then unzip the archive. It contains the complete v0.16.0 extension source and regression tests as they existed at the handoff point.

Do not edit the `.partNN` files. They are an archival snapshot, not the active development source.
