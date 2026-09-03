[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'SupremeFabWorks\AmazonOrderManagerDev'),
    [switch]$DiagnoseOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($PSVersionTable.PSEdition -ne 'Desktop') {
    $windowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path $windowsPowerShell)) {
        throw 'Windows PowerShell 5.1 is required to compile the native updater host.'
    }
    $forward = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-InstallRoot',$InstallRoot)
    if ($DiagnoseOnly) { $forward += '-DiagnoseOnly' }
    & $windowsPowerShell @forward
    exit $LASTEXITCODE
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo = 'supremefabworks-hub/Amazon-Order-Manager'
$HostName = 'com.supremefabworks.amazon_order_manager_updater'
$ExtensionId = 'hhmimkpolikhncnbkkbbabbopbccabcf'
$ExpectedOrigin = "chrome-extension://$ExtensionId/"
$ExtensionAssetName = 'amazon-order-manager.zip'
$ChecksumAssetName = 'amazon-order-manager.zip.sha256'
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$NativeSource = Join-Path $ScriptRoot 'NativeHost.cs'
$HostDirectory = Join-Path $InstallRoot 'host'
$HostExe = Join-Path $HostDirectory 'AmazonOrderManagerDevUpdaterHost.exe'
$HostManifest = Join-Path $HostDirectory "$HostName.json"
$CurrentDirectory = Join-Path $InstallRoot 'current'
$PreviousDirectory = Join-Path $InstallRoot 'previous'

function Show-Diagnostics {
    Write-Host ''
    Write-Host 'Amazon Order Manager development updater diagnostics' -ForegroundColor Cyan
    Write-Host "Install root: $InstallRoot"
    Write-Host "Host executable: $HostExe"
    Write-Host "Host manifest: $HostManifest"
    Write-Host "Current extension: $CurrentDirectory"
    $registryPath = "Registry::HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\$HostName"
    $registered = $null
    try {
        $key = Get-Item -LiteralPath $registryPath -ErrorAction Stop
        $registered = $key.GetValue('')
    } catch {}
    Write-Host "Registry manifest: $($registered ?? '(missing)')"
    $currentManifest = Join-Path $CurrentDirectory 'manifest.json'
    if (Test-Path $currentManifest) {
        try {
            $currentVersion = (Get-Content -Raw -Path $currentManifest | ConvertFrom-Json).version
            Write-Host "Current files version: $currentVersion"
        } catch { Write-Host 'Current manifest: invalid' -ForegroundColor Yellow }
    } else { Write-Host 'Current manifest: missing' -ForegroundColor Yellow }
    if (Test-Path $HostExe) {
        & $HostExe --self-test
        if ($LASTEXITCODE -ne 0) { Write-Host "Native host self-test failed with exit code $LASTEXITCODE" -ForegroundColor Yellow }
    } else { Write-Host 'Native host executable is missing.' -ForegroundColor Yellow }
    $logPath = Join-Path $InstallRoot 'updater.log'
    Write-Host "Updater log: $logPath"
    if (Test-Path $logPath) {
        Write-Host 'Last updater log lines:'
        Get-Content -Path $logPath -Tail 12
    }
    Write-Host ''
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Content, $utf8)
}

function Get-LatestDevRelease {
    $headers = @{
        'User-Agent' = 'SFW-Amazon-Order-Manager-Dev-Updater-Installer/1.0'
        'Accept' = 'application/vnd.github+json'
    }
    $releases = Invoke-RestMethod -UseBasicParsing -Headers $headers -Uri "https://api.github.com/repos/$Repo/releases?per_page=20"
    $candidates = @()
    foreach ($release in @($releases)) {
        if ($release.draft -or -not $release.prerelease) { continue }
        if ([string]$release.tag_name -notmatch '^dev-v(\d+(?:\.\d+){0,3})$') { continue }
        try { $version = [Version]$Matches[1] } catch { continue }
        $candidates += [pscustomobject]@{ Release = $release; Version = $version }
    }
    if (-not $candidates) { throw 'No development release was found. Merge a versioned build to main first.' }
    return $candidates | Sort-Object Version -Descending | Select-Object -First 1
}

function Get-ReleaseAsset($Release, [string]$Name) {
    $asset = @($Release.assets) | Where-Object { $_.name -eq $Name } | Select-Object -First 1
    if (-not $asset -or -not $asset.browser_download_url) {
        throw "Development release is missing required asset: $Name"
    }
    return $asset
}

function Get-ExpectedHash([string]$Path) {
    $text = Get-Content -Raw -Path $Path
    $match = [regex]::Match($text, '(?i)\b[a-f0-9]{64}\b')
    if (-not $match.Success) { throw 'SHA-256 sidecar did not contain a valid digest.' }
    return $match.Value.ToLowerInvariant()
}

function Copy-Directory([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -Force -LiteralPath $Source | ForEach-Object {
        $target = Join-Path $Destination $_.Name
        if ($_.PSIsContainer) {
            Copy-Directory -Source $_.FullName -Destination $target
        } else {
            Copy-Item -Force -LiteralPath $_.FullName -Destination $target
        }
    }
}

function Install-ExtensionPackage([string]$PackageRoot, [Version]$ExpectedVersion) {
    $manifestPath = Join-Path $PackageRoot 'manifest.json'
    if (-not (Test-Path $manifestPath)) { throw 'Downloaded package is missing manifest.json.' }
    $manifest = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json
    $embeddedVersion = [Version]$manifest.version
    if ($embeddedVersion -ne $ExpectedVersion) {
        throw "Package version $embeddedVersion does not match release version $ExpectedVersion."
    }

    $required = @(
        'manifest.json','service-worker.js','background.js','dev-updater.js','content.js','parser.js','storage.js',
        'dashboard.html','dashboard.js','popup.html','popup.js','ui.css','workflow-recorder.js'
    )
    foreach ($file in $required) {
        if (-not (Test-Path (Join-Path $PackageRoot $file))) { throw "Downloaded package is missing required file: $file" }
    }

    $next = Join-Path $InstallRoot ('.next-' + [Guid]::NewGuid().ToString('N'))
    Copy-Directory -Source $PackageRoot -Destination $next
    $movedCurrent = $false
    try {
        if (Test-Path $PreviousDirectory) { Remove-Item -Recurse -Force -LiteralPath $PreviousDirectory }
        if (Test-Path $CurrentDirectory) {
            Move-Item -LiteralPath $CurrentDirectory -Destination $PreviousDirectory
            $movedCurrent = $true
        }
        Move-Item -LiteralPath $next -Destination $CurrentDirectory
    } catch {
        if (Test-Path $next) { Remove-Item -Recurse -Force -LiteralPath $next -ErrorAction SilentlyContinue }
        if ($movedCurrent -and -not (Test-Path $CurrentDirectory) -and (Test-Path $PreviousDirectory)) {
            Move-Item -LiteralPath $PreviousDirectory -Destination $CurrentDirectory -ErrorAction SilentlyContinue
        }
        throw
    }
}

if ($DiagnoseOnly) { Show-Diagnostics; exit 0 }

if (-not (Test-Path $NativeSource)) {
    throw "NativeHost.cs was not found next to this installer: $NativeSource"
}

New-Item -ItemType Directory -Force -Path $InstallRoot, $HostDirectory | Out-Null

if (Test-Path $HostExe) { Remove-Item -Force -LiteralPath $HostExe }
Add-Type -Path $NativeSource `
    -OutputAssembly $HostExe `
    -OutputType ConsoleApplication `
    -ReferencedAssemblies @(
        'System.dll',
        'System.Core.dll',
        'System.Web.Extensions.dll',
        'System.IO.Compression.dll',
        'System.IO.Compression.FileSystem.dll'
    )

$hostDefinition = [ordered]@{
    name = $HostName
    description = 'Supreme Fab Works Amazon Order Manager verified development updater'
    path = $HostExe
    type = 'stdio'
    allowed_origins = @($ExpectedOrigin)
}
Write-Utf8NoBom -Path $HostManifest -Content ($hostDefinition | ConvertTo-Json -Depth 4)

$registryKey = "HKCU\Software\Google\Chrome\NativeMessagingHosts\$HostName"
& reg.exe add $registryKey /ve /t REG_SZ /d $HostManifest /f | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to register the Chrome native messaging host under HKCU.' }

$temp = Join-Path ([IO.Path]::GetTempPath()) ('sfw-aom-installer-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $temp | Out-Null
try {
    $candidate = Get-LatestDevRelease
    $zipAsset = Get-ReleaseAsset -Release $candidate.Release -Name $ExtensionAssetName
    $checksumAsset = Get-ReleaseAsset -Release $candidate.Release -Name $ChecksumAssetName

    $zipPath = Join-Path $temp $ExtensionAssetName
    $checksumPath = Join-Path $temp $ChecksumAssetName
    Invoke-WebRequest -UseBasicParsing -Uri $zipAsset.browser_download_url -OutFile $zipPath
    Invoke-WebRequest -UseBasicParsing -Uri $checksumAsset.browser_download_url -OutFile $checksumPath

    $expectedHash = Get-ExpectedHash -Path $checksumPath
    $actualHash = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw 'Downloaded extension ZIP failed SHA-256 verification.' }

    $extract = Join-Path $temp 'extracted'
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extract -Force
    $packageRoot = Join-Path $extract 'amazon-order-manager'
    if (-not (Test-Path (Join-Path $packageRoot 'manifest.json'))) {
        if (Test-Path (Join-Path $extract 'manifest.json')) {
            $packageRoot = $extract
        } else {
            $manifests = @(Get-ChildItem -Recurse -File -Filter manifest.json -Path $extract)
            if ($manifests.Count -ne 1) { throw 'Extension package must contain exactly one manifest.json root.' }
            $packageRoot = $manifests[0].Directory.FullName
        }
    }

    Install-ExtensionPackage -PackageRoot $packageRoot -ExpectedVersion $candidate.Version
} finally {
    if (Test-Path $temp) { Remove-Item -Recurse -Force -LiteralPath $temp -ErrorAction SilentlyContinue }
}

Write-Host ''
Write-Host 'Amazon Order Manager development auto-update is installed.' -ForegroundColor Green
Write-Host "Extension ID: $ExtensionId"
Write-Host "Load unpacked folder once: $CurrentDirectory"
Write-Host ''
Write-Host 'If an older unpacked copy is currently loaded, remove that old copy from chrome://extensions and load the folder above once.'
Write-Host 'After that, merged versioned dev releases are checked on worker startup, Chrome startup, manually from the popup, and every 15 minutes.'
Write-Host "Updater log: $(Join-Path $InstallRoot 'updater.log')"
Write-Host ''
Show-Diagnostics
