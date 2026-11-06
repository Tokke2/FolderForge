param([string]$PreferredPython = '', [string]$Arguments64 = '', [switch]$MaintenanceOnly)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
function Write-StartError([string]$Message) {
    try {
        $Logs = Join-Path $Root 'logs'
        [IO.Directory]::CreateDirectory($Logs) | Out-Null
        [IO.File]::AppendAllText((Join-Path $Logs 'folderforge-errors.log'),
            (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ERROR [launcher] ' + $Message + [Environment]::NewLine)
    } catch { }
}
function Remove-LegacyMaintenanceTask {
    # Retire only this installation's former weekly Python task.
    try {
        $Digest = [Security.Cryptography.SHA256]::Create()
        try { $Hash = (($Digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant())) | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0,12) }
        finally { $Digest.Dispose() }
        $Name = 'FolderForge Python weekly ' + $Hash.ToUpperInvariant()
        $Task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        if ($Task) { Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction Stop }
    } catch { Write-StartError ('Could not remove obsolete Python task: ' + $_.Exception.Message) }
}
function Quote-Argument([string]$Value) {
    # CommandLineToArgvW-compatible quoting, including trailing backslashes.
    return '"' + ([regex]::Replace($Value, '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}
function Invoke-Hidden([string]$File, [string[]]$Arguments) {
    $Info = New-Object Diagnostics.ProcessStartInfo
    $Info.FileName = $File
    $Info.Arguments = (($Arguments | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $Info.WorkingDirectory = $Root
    $Info.UseShellExecute = $false
    $Info.CreateNoWindow = $true
    $Info.EnvironmentVariables.Remove('PYTHONHOME')
    $Info.EnvironmentVariables.Remove('PYTHONPATH')
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true
    $Info.StandardOutputEncoding = [Text.Encoding]::UTF8
    $Info.StandardErrorEncoding = [Text.Encoding]::UTF8
    $Process = [Diagnostics.Process]::Start($Info)
    try {
        $Out = $Process.StandardOutput.ReadToEndAsync()
        $Err = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        return [pscustomobject]@{ Code = $Process.ExitCode; Out = $Out.Result; Err = $Err.Result }
    } finally { $Process.Dispose() }
}

function Resolve-ExistingPython([string]$Candidate) {
    if (-not $Candidate -or $Candidate -match '\\Microsoft\\WindowsApps\\') { return $null }
    if ([IO.Path]::GetFileName($Candidate) -match '^pythonw') { $Candidate = Join-Path (Split-Path $Candidate) 'python.exe' }
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $null }
    try {
        # Local interpreter identity only; no version/dependency/update check.
        $Result = Invoke-Hidden $Candidate @('-c','import sys; print(getattr(sys,"_base_executable",sys.executable))')
        if ($Result.Code -ne 0) { return $null }
        $Console = $Result.Out.Trim()
        $Windowless = Join-Path (Split-Path $Console) 'pythonw.exe'
        if (Test-Path -LiteralPath $Windowless -PathType Leaf) { return $Windowless }
    } catch { }
    return $null
}
try {
    Remove-LegacyMaintenanceTask
    # Backward-compatible exit for a previously scheduled maintenance invocation.
    if ($MaintenanceOnly) { exit 0 }
    $Candidates = New-Object 'System.Collections.Generic.List[string]'
    # Respect the system PATH instead of saved runtime state or a chosen version.
    foreach ($Name in @('python.exe','python3.exe','pythonw.exe')) {
        foreach ($Command in @(Get-Command $Name -All -ErrorAction SilentlyContinue)) { $Candidates.Add($Command.Source) }
    }
    $Py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($Py) {
        # Listing does not execute a Store alias or install a missing Python.
        try { $Listed = Invoke-Hidden $Py.Source @('-0p') }
        catch { $Listed = [pscustomobject]@{ Out = '' } }
        $Lines = @($Listed.Out -split "`n")
        foreach ($Line in @($Lines | Sort-Object { if ($_ -match '\*') { 0 } else { 1 } })) {
            if ($Line -match '([A-Za-z]:\\.*pythonw?\.exe)\s*$') { $Candidates.Add($Matches[1].Trim()) }
        }
    }
    if ($PreferredPython) { $Candidates.Add($PreferredPython) }
    $Windowless = $null
    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        $Windowless = Resolve-ExistingPython $Candidate
        if ($Windowless) { break }
    }
    if (-not $Windowless) { throw 'No existing system Python with pythonw.exe could be found. No Python was installed or updated.' }
    $AppArgs = @('--tray')
    if ($Arguments64) { $AppArgs = @([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Arguments64)).Split(@([char]0), [StringSplitOptions]::RemoveEmptyEntries)) }
    if ($AppArgs -notcontains '--tray') { $AppArgs += '--tray' }
    $env:FOLDERFORGE_RUNTIME_READY = '1'
    $env:FOLDERFORGE_RUNTIME_POLICY = 'system-python'
    $Start = New-Object Diagnostics.ProcessStartInfo
    $Start.FileName = $Windowless
    $Start.Arguments = (Quote-Argument (Join-Path $Root 'folder.pyw')) + ' ' + (($AppArgs | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $Start.WorkingDirectory = $Root
    $Start.UseShellExecute = $false
    $Start.CreateNoWindow = $true
    $Start.EnvironmentVariables.Remove('PYTHONHOME')
    $Start.EnvironmentVariables.Remove('PYTHONPATH')
    $Child = [Diagnostics.Process]::Start($Start)
    $Child.Dispose()
    exit 0
} catch {
    Write-StartError $_.Exception.Message
    exit 1
}
