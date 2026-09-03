# Amazon Refund Ledger v0.16.0 exact snapshot

This directory contains an exact Base64-encoded copy of the last packaged v0.16.0 Chrome extension ZIP from the pre-GitHub development session.

## Integrity

- Original file: `amazon-refund-ledger-v0.16.0.zip`
- Original byte size: `77670`
- Base64 character count: `103560`
- SHA-256: `0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42`
- Parts: `13`, numbered `part01` through `part13`

The split parts contain raw Base64 with no intentional separators. Concatenate them in numeric order, decode, then verify the SHA-256.

### macOS / Linux

```bash
cat amazon-refund-ledger-v0.16.0.zip.b64.part{01..13} | base64 --decode > amazon-refund-ledger-v0.16.0.zip
shasum -a 256 amazon-refund-ledger-v0.16.0.zip
```

Expected digest:

```text
0ac308d98a4acf47fff51f5fd63410a9e9dc8e6105e7d6f17dcebd9b6e71ac42
```

### PowerShell

```powershell
$parts = 1..13 | ForEach-Object { Get-Content ("amazon-refund-ledger-v0.16.0.zip.b64.part{0:D2}" -f $_) -Raw }
$b64 = $parts -join ''
[IO.File]::WriteAllBytes('amazon-refund-ledger-v0.16.0.zip', [Convert]::FromBase64String($b64))
(Get-FileHash 'amazon-refund-ledger-v0.16.0.zip' -Algorithm SHA256).Hash
```

## Development note

This snapshot is for recovery/audit, not the desired long-term source layout. Ordinary editable source files should live at repository root going forward. `PROJECT_HANDOFF.md` and GitHub issue #7 contain the v0.17 architecture, defects, and acceptance criteria that were active when this snapshot was taken.
