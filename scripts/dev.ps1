param(
    [Parameter(Position = 0)]
    [ValidateSet('setup', 'check', 'infra', 'migrate', 'pair', 'backend', 'desktop', 'preview', 'contracts', 'build', 'test', 'test-e2e', 'package')]
    [string]$Action = 'check'
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
function Read-ServiceConfig {
    # Only the public service URL reaches Electron. Database credentials stay in Python/Compose.
    if (Test-Path -LiteralPath '.env') {
        foreach ($line in Get-Content -LiteralPath '.env') {
            if ($line -match '^VIDEO_SERVICE_URL=(.+)$') { $env:VIDEO_SERVICE_URL = $Matches[1].Trim() }
        }
    }
    # Some IDE terminals set this for their own Node helpers; Electron needs normal app mode.
    Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
}
switch ($Action) {
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
    'infra' { Run-Checked 'docker' @('compose', '--env-file', '.env', '-f', 'deploy/video/compose.yaml', 'up', '-d', '--wait') }
    'migrate' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head') }
    'pair' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'video-admin', 'init-owner') }
    'backend' { Invoke-Uv @('run', '--project', 'backend', '--frozen', 'video-api') }
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
