<#
.SYNOPSIS
    Load MIDAS test-instance credentials into the CURRENT process environment.

.DESCRIPTION
    Reads the credentials file that lives OUTSIDE this repository
    (%USERPROFILE%\.structai\midas-test.env) and exports MIDAS_BASE_URL / MIDAS_MAPI_KEY
    for the requested instance.

    Why a loader instead of a committed file:
      * docs/07 section 8.5 / 14.3 -- credentials are injected by the runtime environment
        only; they must never be written into the repository, docs, tests, logs, audit or
        responses. .env.example therefore only registers the variable NAMES (values empty).
      * MidasEnvironmentCredential reads os.environ; pydantic-settings' .env only fills
        Settings fields and does NOT populate os.environ, so a .env entry would not work
        for MIDAS_* anyway.

.PARAMETER Instance
    gen | civil | cdn  -- which test instance to activate.
    all                -- export the two extra aliases (*_CIVIL / *_CDN) as well.

.PARAMETER Path
    Credentials file. Default: %USERPROFILE%\.structai\midas-test.env

.PARAMETER Show
    Print variable NAMES and whether they are set. Never prints values.

.EXAMPLE
    . .\scripts\load-midas-env.ps1 -Instance gen
    . .\scripts\load-midas-env.ps1 -Instance civil -Show
#>
[CmdletBinding()]
param(
    [ValidateSet('gen', 'civil', 'cdn', 'all')]
    [string]$Instance = 'gen',

    [string]$Path = (Join-Path $env:USERPROFILE '.structai\midas-test.env'),

    [switch]$Show
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Path)) {
    throw ("credentials file not found: {0}`ncreate it outside the repo (see the header of this script) " +
           "or pass -Path; the file must NEVER live inside the repository") -f $Path
}

# Parse: [section] headers + KEY=VALUE lines; '#' starts a comment.
$sections = @{}
$current = ''
foreach ($raw in Get-Content -LiteralPath $Path -Encoding UTF8) {
    $line = $raw.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { continue }
    if ($line.StartsWith('[') -and $line.EndsWith(']')) {
        $current = $line.Substring(1, $line.Length - 2).Trim().ToLowerInvariant()
        if (-not $sections.ContainsKey($current)) { $sections[$current] = @{} }
        continue
    }
    $pair = $line.Split('=', 2)
    if ($pair.Count -ne 2 -or $current -eq '') { continue }
    $sections[$current][$pair[0].Trim()] = $pair[1].Trim()
}

$alias = @{ gen = ''; civil = '_CIVIL'; cdn = '_CDN' }

function Set-Instance {
    param([string]$Name)
    $suffix = $alias[$Name]
    if (-not $sections.ContainsKey($Name)) {
        throw "section [$Name] is missing in $Path"
    }
    $section = $sections[$Name]
    foreach ($key in @('MIDAS_BASE_URL', 'MIDAS_MAPI_KEY')) {
        if (-not $section.ContainsKey($key) -or $section[$key] -eq '') {
            throw "section [$Name] is missing $key in $Path"
        }
        [Environment]::SetEnvironmentVariable($key + $suffix, $section[$key], 'Process')
    }
    # canonical pair = the selected instance
    $env:MIDAS_BASE_URL = $section['MIDAS_BASE_URL']
    $env:MIDAS_MAPI_KEY = $section['MIDAS_MAPI_KEY']
    Write-Host ("loaded instance '{0}' -> MIDAS_BASE_URL set, MIDAS_MAPI_KEY set (len {1})" -f `
        $Name, $section['MIDAS_MAPI_KEY'].Length)
}

if ($Instance -eq 'all') {
    foreach ($name in @('gen', 'civil', 'cdn')) { Set-Instance -Name $name }
    $env:MIDAS_BASE_URL = $sections['gen']['MIDAS_BASE_URL']
    $env:MIDAS_MAPI_KEY = $sections['gen']['MIDAS_MAPI_KEY']
} else {
    Set-Instance -Name $Instance
}

if ($Show) {
    foreach ($name in @('MIDAS_BASE_URL', 'MIDAS_MAPI_KEY', 'MIDAS_BASE_URL_CIVIL',
                        'MIDAS_MAPI_KEY_CIVIL', 'MIDAS_BASE_URL_CDN', 'MIDAS_MAPI_KEY_CDN')) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        Write-Host ("  {0,-24} set={1}" -f $name, [bool]$value)
    }
    Write-Host '  (values are never printed)'
}