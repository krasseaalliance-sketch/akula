$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$remote = 'https://github.com/krasseaalliance-sketch/akula.git'
$tag = 'core-r1-staging-rc1-2026-09-07'
$expectedCommit = 'e497f5152b204df74a065789aeb46542089bcb99'
$alembicHead = '0025_core_day4_production_evidence'
$packageName = 'akula-platform-staging'
$packageVersion = '2026.09.07-r1'
$artifactName = 'akula-platform-staging-2026-09-07.tar.gz'
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('akula-platform-build-' + [guid]::NewGuid().ToString('N'))
$sourceRoot = Join-Path $tempRoot 'source'
$bundleParent = Join-Path $tempRoot 'bundle-parent'
$bundleRoot = Join-Path $bundleParent $packageName
$artifactDir = Join-Path $repoRoot 'artifacts'
$artifactPath = Join-Path $artifactDir $artifactName

New-Item -ItemType Directory -Path $sourceRoot, $bundleRoot -Force | Out-Null
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null

function Invoke-Git([string[]]$Arguments) {
    & git @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git failed: $($Arguments -join ' ')" }
}

function Copy-SafeTree([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $sourceResolved = (Resolve-Path $Source).Path.TrimEnd('\')
    $excluded = '\\.git(\\|$)|\\node_modules(\\|$)|\\.next(\\|$)|\\__pycache__(\\|$)|\\.pytest_cache(\\|$)|\\.core_artifacts(\\|$)|\\uploads?(\\|$)|\\logs?(\\|$)|\\.venv(\\|$)|\\venv(\\|$)|\\artifacts(\\|$)|\\archives?(\\|$)'
    Get-ChildItem -LiteralPath $sourceResolved -File -Recurse -Force |
        Where-Object { $_.FullName -notmatch $excluded -and $_.Name -notmatch '^\.env($|\.)' -and $_.Name -notmatch '\.(db|sqlite3|dump|tar|tar\.gz|zip|key|pem)$' } |
        ForEach-Object {
            $relative = $_.FullName.Substring($sourceResolved.Length).TrimStart('\')
            $target = Join-Path $Destination $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
}

function Copy-FileSafe([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

Invoke-Git @('clone', '--quiet', '--no-checkout', $remote, $sourceRoot)
Invoke-Git @('-C', $sourceRoot, 'checkout', '--quiet', '--detach', $tag)
$actualCommit = (& git -C $sourceRoot rev-parse HEAD).Trim()
if ($actualCommit -ne $expectedCommit) { throw "Unexpected source commit: $actualCommit" }
$exactTag = (& git -C $sourceRoot describe --tags --exact-match HEAD).Trim()
if ($exactTag -ne $tag) { throw "Source is not checked out at the exact tag: $exactTag" }

# Core is the runnable monorepo snapshot. Scout and Constructive below are
# explicit source slices from the same tree, so the three products travel together.
Copy-SafeTree (Join-Path $sourceRoot 'backend') (Join-Path $bundleRoot 'core/backend')
Copy-SafeTree (Join-Path $sourceRoot 'frontend') (Join-Path $bundleRoot 'core/frontend')
Copy-FileSafe (Join-Path $sourceRoot 'pyproject.toml') (Join-Path $bundleRoot 'core/pyproject.toml')
Copy-FileSafe (Join-Path $sourceRoot 'alembic.ini') (Join-Path $bundleRoot 'core/alembic.ini')
Copy-SafeTree (Join-Path $sourceRoot 'backend/migrations') (Join-Path $bundleRoot 'migrations')

Copy-SafeTree (Join-Path $sourceRoot 'backend/app/hunter') (Join-Path $bundleRoot 'scout/backend/app/hunter')
Copy-FileSafe (Join-Path $sourceRoot 'backend/app/lead_monitor_queries.py') (Join-Path $bundleRoot 'scout/backend/app/lead_monitor_queries.py')
Copy-FileSafe (Join-Path $sourceRoot 'backend/lead_monitor_service.py') (Join-Path $bundleRoot 'scout/backend/lead_monitor_service.py')
Copy-FileSafe (Join-Path $sourceRoot 'frontend/app/page.tsx') (Join-Path $bundleRoot 'scout/frontend/app/page.tsx')
Copy-FileSafe (Join-Path $sourceRoot 'frontend/app/paths.ts') (Join-Path $bundleRoot 'scout/frontend/app/paths.ts')
Copy-SafeTree (Join-Path $sourceRoot 'frontend/app/cabinet') (Join-Path $bundleRoot 'scout/frontend/app/cabinet')
foreach ($file in @('cabinet-directory.tsx', 'cabinet-directory.css', 'login/page.tsx', 'login/login.css')) {
    $sourceFile = Join-Path $sourceRoot ('frontend/app/' + $file)
    if (Test-Path -LiteralPath $sourceFile) { Copy-FileSafe $sourceFile (Join-Path $bundleRoot ('scout/frontend/app/' + $file)) }
}

foreach ($file in @('constructive_api.py', 'constructive_access.py')) {
    Copy-FileSafe (Join-Path $sourceRoot ('backend/app/' + $file)) (Join-Path $bundleRoot ('constructive/backend/app/' + $file))
}
foreach ($file in @('constructive-landing.tsx', 'constructive-view.tsx', 'constructive.css')) {
    Copy-FileSafe (Join-Path $sourceRoot ('frontend/app/' + $file)) (Join-Path $bundleRoot ('constructive/frontend/app/' + $file))
}
Copy-SafeTree (Join-Path $sourceRoot 'frontend/app/constructive') (Join-Path $bundleRoot 'constructive/frontend/app/constructive')

$kit = Join-Path $repoRoot 'deploy/platform-kit'
Copy-SafeTree (Join-Path $kit 'env') (Join-Path $bundleRoot 'env')
Copy-FileSafe (Join-Path $kit 'docker-compose.platform.yml') (Join-Path $bundleRoot 'deploy/docker-compose.platform.yml')
Copy-FileSafe (Join-Path $kit 'Caddyfile') (Join-Path $bundleRoot 'deploy/Caddyfile')
Copy-FileSafe (Join-Path $kit 'install.sh') (Join-Path $bundleRoot 'deploy/install.sh')
Copy-FileSafe (Join-Path $kit 'verify.sh') (Join-Path $bundleRoot 'deploy/verify.sh')
Copy-FileSafe (Join-Path $kit 'rollback.sh') (Join-Path $bundleRoot 'deploy/rollback.sh')
Copy-FileSafe (Join-Path $kit 'README-DEPLOY.md') (Join-Path $bundleRoot 'README-DEPLOY.md')
Copy-FileSafe (Join-Path $kit 'README-ROLLBACK.md') (Join-Path $bundleRoot 'README-ROLLBACK.md')

$buildUtc = (Get-Date).ToUniversalTime().ToString('o')

function Get-ComponentFiles([string]$ComponentPath) {
    $root = (Resolve-Path (Join-Path $bundleRoot $ComponentPath)).Path.TrimEnd('\')
    @(Get-ChildItem -LiteralPath $root -File -Recurse -Force | ForEach-Object {
        $relative = $_.FullName.Substring($bundleRoot.Length).TrimStart('\').Replace('\', '/')
        [ordered]@{ path = $relative; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    } | Sort-Object path)
}

function Get-ComponentHash($Files) {
    $canonical = ($Files | ForEach-Object { "$($_.path)|$($_.sha256)" }) -join "`n"
    $bytes = [Text.Encoding]::UTF8.GetBytes($canonical)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
}

$components = @()
foreach ($component in @(
    @{ name = 'Core'; version = 'Release 1 / 0.1.0'; path = 'core' },
    @{ name = 'Scout'; version = 'monorepo route /scout'; path = 'scout' },
    @{ name = 'Constructive'; version = 'monorepo route /scout/constructive'; path = 'constructive' }
)) {
    $files = Get-ComponentFiles $component.path
    $components += [ordered]@{ name = $component.name; version = $component.version; path = $component.path; sha256 = Get-ComponentHash $files; files = $files }
}

$allFiles = @(Get-ChildItem -LiteralPath $bundleRoot -File -Recurse -Force | ForEach-Object { $_.FullName.Substring($bundleRoot.Length).TrimStart('\').Replace('\', '/') } | Sort-Object)
$allFiles += 'RELEASE_MANIFEST.json'
$allFiles += 'CHECKSUMS.sha256'
$manifest = [ordered]@{
    package_name = $packageName
    package_version = $packageVersion
    build_utc = $buildUtc
    environment = 'staging'
    production_deployment = $false
    git = [ordered]@{ remote = $remote; tag = $tag; commit = $actualCommit }
    alembic_head = $alembicHead
    components = $components
    included_files = @($allFiles | Sort-Object -Unique)
    system_requirements = [ordered]@{ os = 'Ubuntu LTS'; vcpu = 2; ram_gb = 4; disk_gb = 40; docker = 'Docker Engine + Compose' }
    ports = @('80/tcp', '443/tcp')
    routes = @('/scout/core', '/scout', '/scout/constructive', '/ready', '/core -> 404')
    startup_order = @('db', 'redis', 'backend migrations + API', 'frontend', 'Caddy')
    rollback_target = 'previous approved staging tag/image plus staging DB backup'
}
$manifestPath = Join-Path $bundleRoot 'RELEASE_MANIFEST.json'
$manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$checksumLines = @(Get-ChildItem -LiteralPath $bundleRoot -File -Recurse -Force | Where-Object { $_.Name -ne 'CHECKSUMS.sha256' } | ForEach-Object {
    $relative = $_.FullName.Substring($bundleRoot.Length).TrimStart('\').Replace('\', '/')
    "$( (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() )  $relative"
} | Sort-Object)
Set-Content -LiteralPath (Join-Path $bundleRoot 'CHECKSUMS.sha256') -Value $checksumLines -Encoding ASCII

if (Test-Path -LiteralPath $artifactPath) { Remove-Item -LiteralPath $artifactPath -Force }
Push-Location $bundleParent
try { & tar -czf $artifactPath $packageName; if ($LASTEXITCODE -ne 0) { throw 'tar failed' } } finally { Pop-Location }

$extractRoot = Join-Path $tempRoot 'extracted'
New-Item -ItemType Directory -Path $extractRoot | Out-Null
& tar -xzf $artifactPath -C $extractRoot
if ($LASTEXITCODE -ne 0) { throw 'tar extraction failed' }
$extractedBundle = Join-Path $extractRoot $packageName
$required = @('RELEASE_MANIFEST.json', 'CHECKSUMS.sha256', 'README-DEPLOY.md', 'README-ROLLBACK.md', 'env/core.env.example', 'env/scout.env.example', 'env/constructive.env.example', 'env/shared.env.example', 'deploy/docker-compose.platform.yml', 'deploy/Caddyfile', 'deploy/install.sh', 'deploy/verify.sh', 'deploy/rollback.sh', 'core/backend/app', 'core/frontend/app', 'scout/backend/app/hunter', 'scout/frontend/app/cabinet', 'constructive/backend/app/constructive_api.py', 'constructive/frontend/app/constructive/page.tsx', 'migrations/versions/0025_core_day4_production_evidence.py')
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $extractedBundle $_)) })
if ($missing.Count -gt 0) { throw "Extracted package is missing: $($missing -join ', ')" }

Write-Output "source=$sourceRoot"
Write-Output "tag=$exactTag"
Write-Output "commit=$actualCommit"
Write-Output "artifact=$artifactPath"
Write-Output "artifact_sha256=$((Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash)"
Write-Output "package_root=$bundleRoot"
Write-Output "extract_root=$extractedBundle"
