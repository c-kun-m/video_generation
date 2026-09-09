param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'setup', 'check', 'infra', 'migrate', 'pair', 'backend', 'worker', 'dispatcher', 'init-temporal', 'desktop', 'preview', 'contracts', 'build', 'test', 'test-e2e', 'package')]
    [string]$Action = 'check',
    [string]$Config = 'startup.yml',
    [switch]$Check
)
$ErrorActionPreference = 'Stop'
$videoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $videoRoot
$env:PYTHONIOENCODING = 'utf-8'

function Run-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)" }
}
function Invoke-Uv([string[]]$Arguments) { Run-Checked 'python' (@('-m', 'uv') + $Arguments) }
function Invoke-Frontend([string[]]$Arguments) { Run-Checked 'pnpm' (@('--dir', 'frontend') + $Arguments) }
function Ensure-TemporalConfig {
    if (-not (Test-Path -LiteralPath '.env')) { throw 'Run setup first.' }
    $videoConfig = [IO.File]::ReadAllText((Join-Path $videoRoot '.env'))
    if ($videoConfig -notmatch '(?m)^VIDEO_TEMPORAL_DB_PASSWORD=.+$' -or $videoConfig.Contains('replace-with-a-temporal-password')) {
        $videoBytes = New-Object byte[] 24
        $videoRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $videoRng.GetBytes($videoBytes) } finally { $videoRng.Dispose() }
        $videoPassword = -join ($videoBytes | ForEach-Object { $_.ToString('x2') })
        if ($videoConfig -match '(?m)^VIDEO_TEMPORAL_DB_PASSWORD=') {
            $videoConfig = [regex]::Replace($videoConfig, '(?m)^VIDEO_TEMPORAL_DB_PASSWORD=.*$', "VIDEO_TEMPORAL_DB_PASSWORD=$videoPassword")
        } else { $videoConfig = $videoConfig.TrimEnd() + "`nVIDEO_TEMPORAL_DB_PASSWORD=$videoPassword`n" }
        [IO.File]::WriteAllText((Join-Path $videoRoot '.env'), $videoConfig)
        Write-Host 'Configured an independent local Temporal database password.'
    }
}
function Read-ServiceConfig {
    # Only the public service URL reaches Electron. Database credentials stay in Python/Compose.
    if (-not $env:VIDEO_SERVICE_URL -and (Test-Path -LiteralPath '.env')) {
        foreach ($line in Get-Content -LiteralPath '.env') {
            if ($line -match '^VIDEO_SERVICE_URL=(.+)$') { $env:VIDEO_SERVICE_URL = $Matches[1].Trim() }
        }
    }
    # Some IDE terminals set this for their own Node helpers; Electron needs normal app mode.
    Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
}
switch ($Action) {
    'start' {
        $videoInterpreter = Join-Path $videoRoot 'backend/.venv/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $videoInterpreter)) { throw 'Run setup first to create the backend environment.' }
        $videoLaunchArgs = @('-m', 'video_generation', 'start', '--config', $Config)
        if ($Check) { $videoLaunchArgs += '--check' }
        Run-Checked $videoInterpreter $videoLaunchArgs
    }
    'setup' {
        Run-Checked 'python' @('--version')
        Run-Checked 'node' @('--version')
        Run-Checked 'pnpm' @('--version')
        if (-not (Test-Path -LiteralPath '.env')) {
            $videoBytes = New-Object byte[] 24
            $videoRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
            try { $videoRng.GetBytes($videoBytes) } finally { $videoRng.Dispose() }
            $videoPassword = -join ($videoBytes | ForEach-Object { $_.ToString('x2') })
            $videoContents = (Get-Content -Raw -LiteralPath '.env.example').Replace('replace-with-a-local-password', $videoPassword)
            [IO.File]::WriteAllText((Join-Path $videoRoot '.env'), $videoContents)
            Write-Host 'Created .env with a random local database password.'
        }
        Ensure-TemporalConfig
        Invoke-Uv @('sync', '--project', 'backend', '--frozen')
        Invoke-Frontend @('install', '--frozen-lockfile')
    }
    'check' {
        Run-Checked 'python' @('--version')
        Run-Checked 'node' @('--version')
        Run-Checked 'pnpm' @('--version')
        Invoke-Uv @('--version')
        Run-Checked 'docker' @('version', '--format', '{{.Server.Version}}')
        if (-not (Test-Path -LiteralPath '.env')) { throw 'Run setup to create .env first.' }
        Write-Host 'Local tools are available.'
    }
    'infra' {
        Ensure-TemporalConfig
        Run-Checked 'docker' @('compose', '--env-file', '.env', '-f', 'deploy/video/compose.yaml', 'up', '-d', '--wait')
        Invoke-Uv @('run', '--project', 'backend', '--frozen', 'python', '-m', 'video_generation', 'init-temporal')
    }
    'migrate' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head') }
    'pair' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'video-admin', 'init-owner') }
    'backend' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'video-api') }
    'worker' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'python', '-m', 'video_generation', 'worker') }
    'dispatcher' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'python', '-m', 'video_generation', 'dispatcher') }
    'init-temporal' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'python', '-m', 'video_generation', 'init-temporal') }
    'desktop' { Read-ServiceConfig; Invoke-Frontend @('dev') }
    'preview' { Read-ServiceConfig; Invoke-Frontend @('preview') }
    'contracts' {
        Invoke-Uv @('run', '--project', 'backend', '--frozen', 'python', '-m', 'video_generation.contracts.export')
        Invoke-Frontend @('contracts')
    }
    'build' { Invoke-Frontend @('build') }
    'package' { Invoke-Frontend @('package') }
    'test' {
        Invoke-Uv @('run', '--project', 'backend', '--frozen', 'python', 'scripts/prepare_test_db.py')
        Invoke-Uv @('run', '--project', 'backend', '--frozen', 'ruff', 'check', 'backend', 'scripts')
        Invoke-Uv @('run', '--project', 'backend', '--frozen', 'ruff', 'format', '--check', 'backend', 'scripts')
        Invoke-Uv @('run', '--project', 'backend', '--frozen', 'pytest', 'backend/tests', '-q')
        Invoke-Frontend @('typecheck')
        Invoke-Frontend @('format:check')
        Invoke-Frontend @('test')
    }
    'test-e2e' {
        Invoke-Uv @('run', '--project', 'backend', '--frozen', 'python', 'scripts/prepare_test_db.py')
        Invoke-Frontend @('build')
        Read-ServiceConfig
        Invoke-Frontend @('test:e2e')
    }
}
