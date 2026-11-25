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
        $TaskTree = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tree\' + $Name
        if (Test-Path -LiteralPath $TaskTree -ErrorAction SilentlyContinue) {
            $Task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
            if ($Task) { Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction Stop }
        }
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
        if (-not $Process.WaitForExit(15000)) {
            # Only this freshly launched identity/GUI probe, never a running app.
            $Process.Kill()
            $Process.WaitForExit()
            throw 'Det lokala Python-provet svarade inte inom 15 sekunder'
        }
        return [pscustomobject]@{ Code = $Process.ExitCode; Out = $Out.Result; Err = $Err.Result }
    } finally { $Process.Dispose() }
}

function Write-StartInfo([string]$Message) {
    try {
        $Logs = Join-Path $Root 'logs'
        [IO.Directory]::CreateDirectory($Logs) | Out-Null
        [IO.File]::AppendAllText((Join-Path $Logs 'folderforge.log'),
            (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' INFO [launcher] ' + $Message + [Environment]::NewLine)
    } catch { }
}
function Resolve-ExistingPython([string]$Candidate) {
    if (-not $Candidate -or $Candidate -match '\\Microsoft\\WindowsApps\\') { return $null }
    if ([IO.Path]::GetFileName($Candidate) -match '^pythonw') { $Candidate = Join-Path (Split-Path $Candidate) 'python.exe' }
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $null }
    try {
        # Identity/version of an EXISTING interpreter, never package versions or downloads.
        $Code = 'import json,sys; print(json.dumps({"executable":getattr(sys,"_base_executable",sys.executable),"version":list(sys.version_info[:2])}))'
        $Result = Invoke-Hidden $Candidate @('-c',$Code)
        if ($Result.Code -ne 0) { throw $Result.Err }
        $Identity = (($Result.Out.Trim() -split "`n")[-1]) | ConvertFrom-Json
        $Console = [string]$Identity.executable
        if ([IO.Path]::GetFileName($Console) -match '^pythonw') { $Console = Join-Path (Split-Path $Console) 'python.exe' }
        $Windowless = Join-Path (Split-Path $Console) 'pythonw.exe'
        if (-not (Test-Path -LiteralPath $Windowless -PathType Leaf)) { throw 'pythonw.exe saknas' }
        return [pscustomobject]@{ Console = $Console; Windowless = $Windowless;
            Major = [int]$Identity.version[0]; Minor = [int]$Identity.version[1];
            Version = ([string]$Identity.version[0] + '.' + [string]$Identity.version[1]) }
    } catch {
        Write-StartInfo ('Hoppar över Python ' + $Candidate + ': ' + $_.Exception.Message)
        return $null
    }
}
function Test-ExistingPythonGui($Python) {
    if ($Python.Major -ne 3 -or $Python.Minor -lt 11) {
        Write-StartInfo ('Hoppar över Python ' + $Python.Version + ': appen kräver Python 3.11 eller senare')
        return $false
    }
    try {
        # Short-lived LOCAL functional probe. No app imports, settings, pip,
        # network, hotkey hooks, autostart or installations. Withdraw before update.
        if ($env:FOLDERFORGE_GUI -eq 'tk') {
        $Code = 'import tkinter,customtkinter; from PIL import Image; import pystray; r=customtkinter.CTk(); r.withdraw(); r.update_idletasks(); r.destroy()'
        } else {
            $Code = 'from PySide6.QtWidgets import QApplication; from PySide6.QtGui import QIcon; from PySide6.QtSvgWidgets import QSvgWidget; a=QApplication([]); a.processEvents(); a.quit()'
        }
        $Result = Invoke-Hidden $Python.Console @('-c',$Code)
        if ($Result.Code -eq 0) { return $true }
        $Reason = $Result.Err.Trim()
        if ($Reason.Length -gt 1200) { $Reason = $Reason.Substring($Reason.Length - 1200) }
        Write-StartInfo ('Hoppar över Python ' + $Python.Version + ' (' + $Python.Console + '): GUI-provet misslyckades. ' + $Reason)
    } catch {
        Write-StartInfo ('Hoppar över Python ' + $Python.Version + ' (' + $Python.Console + '): ' + $_.Exception.Message)
    }
    return $false
}
function Select-ExistingPython([string[]]$Candidates) {
    $ValidCandidates = @($Candidates | Where-Object { $_ -and $_ -notmatch '\\Microsoft\\WindowsApps\\' })
    if (-not $ValidCandidates.Count) { return $null }
    $SeenKeys = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $UniqueCandidates = New-Object 'System.Collections.Generic.List[string]'
    foreach ($Candidate in $ValidCandidates) {
        $Key = $Candidate
        if ([IO.Path]::GetFileName($Candidate) -match '^pythonw?\.exe$') {
            $Dir = Split-Path $Candidate
            if ($Dir) { $Key = Join-Path $Dir 'python.exe' }
        }
        if ($SeenKeys.Add($Key)) { $UniqueCandidates.Add($Candidate) }
    }
    $PrimaryPython = Resolve-ExistingPython $UniqueCandidates[0]
    $Primary = if ($PrimaryPython) { $PrimaryPython.Windowless } else { $null }
    if ($PrimaryPython -and (Test-ExistingPythonGui $PrimaryPython)) {
        Write-StartInfo ('Vald system-Python ' + $PrimaryPython.Version + ': ' + $PrimaryPython.Windowless)
        return $PrimaryPython.Windowless
    }
    $Resolved = @()
    $Index = 0
    foreach ($Candidate in ($UniqueCandidates | Select-Object -Skip 1)) {
        $Python = Resolve-ExistingPython $Candidate
        if ($Python -and $Resolved.Windowless -notcontains $Python.Windowless -and $Python.Windowless -ne $Primary) {
            $Python | Add-Member -NotePropertyName Index -NotePropertyValue $Index -Force
            $Resolved += $Python
            $Index++
        }
    }
    if (-not $Resolved.Count) { return $null }
    # Keep the current PATH choice first. If unusable, prefer installed 3.14;
    # then try other installed versions, newest first, with deterministic tie-breaking. No version is installed.
    $Ordered = @($Resolved | Sort-Object @{Expression={
        if ($_.Windowless -eq $Primary) { 0 } elseif ($_.Version -eq '3.14') { 1 } else { 2 }
    }}, @{Expression={ -1 * $_.Minor }}, @{Expression={
        if ($_.Windowless -match '\\Programs\\Python\\') { 0 } else { 1 }
    }}, @{Expression={ $_.Index }})
    foreach ($Python in $Ordered) {
        if (Test-ExistingPythonGui $Python) {
            Write-StartInfo ('Vald system-Python ' + $Python.Version + ': ' + $Python.Windowless)
            return $Python.Windowless
        }
    }
    return $null
}

function Get-PythonCandidates {
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
    # Also discover normally registered installs when py.exe is absent.
    foreach ($RegistryRoot in @('HKCU:\Software\Python\PythonCore', 'HKLM:\Software\Python\PythonCore', 'HKLM:\Software\WOW6432Node\Python\PythonCore')) {
        foreach ($VersionKey in @(Get-ChildItem -LiteralPath $RegistryRoot -ErrorAction SilentlyContinue)) {
            $InstallKey = Get-Item -LiteralPath ($VersionKey.PSPath + '\InstallPath') -ErrorAction SilentlyContinue
            if ($InstallKey) {
                $Executable = [string]$InstallKey.GetValue('ExecutablePath')
                if (-not $Executable) {
                    $InstallDir = [string]$InstallKey.GetValue('')
                    if ($InstallDir) { $Executable = Join-Path $InstallDir 'python.exe' }
                }
                if ($Executable) { $Candidates.Add($Executable) }
            }
        }
    }
    if ($PreferredPython) { $Candidates.Add($PreferredPython) }
    foreach ($Pattern in @("$env:LOCALAPPDATA\Programs\Python\Python*\python.exe", "$env:LOCALAPPDATA\Python\pythoncore-*\python.exe", "$env:USERPROFILE\miniconda3\python.exe", "$env:USERPROFILE\anaconda3\python.exe", "$env:ProgramData\Anaconda3\python.exe")) {
        foreach ($File in @(Get-Item -Path $Pattern -ErrorAction SilentlyContinue)) { $Candidates.Add($File.FullName) }
    }
    return $Candidates.ToArray()
}
function Test-AnyInstalledPython([string[]]$Candidates) {
    # Presence, NOT GUI compatibility: old/broken Python must never trigger setup.
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and $Candidate -notmatch '\\Microsoft\\WindowsApps\\' -and
            (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $true }
    }
    return $false
}
function Get-LatestStablePythonPackageId([string]$Listing) {
    $Minors = @()
    foreach ($Line in ($Listing -split "`n")) {
        if ($Line -match '(?i)preview|alpha|beta|\drc\d|\d[aAbB]\d|\bdev\b') { continue }
        foreach ($Match in [regex]::Matches($Line, 'Python\.Python\.3\.(\d+)(?![\w.])')) {
            $Minor = [int]$Match.Groups[1].Value
            if ($Minor -ge 11) { $Minors += $Minor }
        }
    }
    if (-not $Minors.Count) { return $null }
    return 'Python.Python.3.' + ($Minors | Sort-Object -Descending -Unique | Select-Object -First 1)
}
function Invoke-PythonInstaller([string]$File, [string[]]$Arguments) {
    # Used ONLY after explicit consent and confirmed absence, never for upgrades.
    $Info = New-Object Diagnostics.ProcessStartInfo
    $Info.FileName = $File
    $Info.Arguments = (($Arguments | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $Info.UseShellExecute = $false
    $Info.CreateNoWindow = $true
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true
    $Process = [Diagnostics.Process]::Start($Info)
    try {
        $Out = $Process.StandardOutput.ReadToEndAsync()
        $Err = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        return [pscustomobject]@{ Code=$Process.ExitCode; Out=$Out.Result; Err=$Err.Result }
    } finally { $Process.Dispose() }
}
function Offer-MissingPythonInstall {
    $Dialog = New-Object -ComObject WScript.Shell
    $Answer = $Dialog.Popup('Ingen Python-installation hittades. Vill du installera den senaste stabila Python som finns i winget? Installationen sker bara efter ditt ja och kan stoppas av arbetsgivarens IT-policy. Wingets käll- och paketvillkor godkänns för hämtningen; Python-installationsprogrammet visas. Om winget saknas öppnas i stället python.org för manuell installation. FolderForges extra paket installeras inte.', 0, 'FolderForge - Python saknas', 4 + 32 + 256)
    if ($Answer -ne 6) { Write-StartInfo 'Python saknas; användaren avstod installation.'; return $false }
    $Winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $Winget) {
        Start-Process 'https://www.python.org/downloads/windows/'
        Write-StartInfo 'Öppnade python.org efter samtycke; ingen installation kördes av startfilen.'
        return $false
    }
    $Listing = Invoke-PythonInstaller $Winget.Source @('search','--id','Python.Python.3','--source','winget','--accept-source-agreements','--disable-interactivity')
    if ($Listing.Code -ne 0) { throw ('Kunde inte läsa wingets Python-lista: ' + $Listing.Err) }
    $Id = Get-LatestStablePythonPackageId $Listing.Out
    if (-not $Id) { throw 'Ingen entydig stabil Python hittades i winget. Ingen installation kördes.' }
    # Recheck just before installation in case a concurrent installer finished.
    if (Test-AnyInstalledPython @(Get-PythonCandidates)) { return $true }
    Write-StartInfo ('Uttryckligen godkänd förstagångsinstallation: ' + $Id)
    $Installed = Invoke-PythonInstaller $Winget.Source @('install','--id',$Id,'--exact','--source','winget','--scope','user','--interactive','--accept-source-agreements','--accept-package-agreements')
    if ($Installed.Code -ne 0) { throw ('Python installerades inte (winget exit ' + $Installed.Code + '): ' + $Installed.Err) }
    return $true
}


try {
    Remove-LegacyMaintenanceTask
    # Backward-compatible exit for a previously scheduled maintenance invocation.
    if ($MaintenanceOnly) { exit 0 }
    $Candidates = @(Get-PythonCandidates)
    if (-not (Test-AnyInstalledPython $Candidates)) {
        # The only install offer in the app: absence, never a failed GUI probe.
        $SetupLock = New-Object Threading.Mutex($false, 'Local\FolderForge_FirstPythonSetup')
        $OwnSetup = $false
        try {
            $OwnSetup = $SetupLock.WaitOne(0)
            if (-not $OwnSetup) { throw 'En Python-installationsdialog är redan aktiv. Starta igen när den är klar.' }
            $Candidates = @(Get-PythonCandidates)
            if (-not (Test-AnyInstalledPython $Candidates)) {
                if (-not (Offer-MissingPythonInstall)) { exit 0 }
            }
            $Candidates = @(Get-PythonCandidates)
        } finally {
            if ($OwnSetup) { $SetupLock.ReleaseMutex() }
            $SetupLock.Dispose()
        }
    }
    $Windowless = Select-ExistingPython -Candidates @($Candidates)
    if (-not $Windowless) { throw 'Ingen installerad system-Python kunde köra appens GUI-beroenden. Se hoppade tolkar i folderforge.log. Ingen Python eller paket installerades eller uppgraderades.' }
    $AppArgs = @('--tray')
    if ($Arguments64) { $AppArgs = @([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Arguments64)).Split(@([char]0), [StringSplitOptions]::RemoveEmptyEntries)) }
    if ($AppArgs -notcontains '--tray') { $AppArgs += '--tray' }
    $env:FOLDERFORGE_RUNTIME_READY = '1'
    $env:FOLDERFORGE_RUNTIME_POLICY = 'system-python'
    $Start = New-Object Diagnostics.ProcessStartInfo
    $Start.FileName = $Windowless
    $Target = Join-Path $Root 'folder.pyw'
    $Supervisor = Join-Path $Root 'data/update-supervisor.py'
    if ((Test-Path -LiteralPath (Join-Path $Root 'data/update-transaction.json')) -and (Test-Path -LiteralPath $Supervisor)) {
        $Target = $Supervisor
        $AppArgs = @('--recover',$Root,$Windowless)
    }
    $Start.Arguments = (Quote-Argument $Target) + ' ' + (($AppArgs | ForEach-Object { Quote-Argument $_ }) -join ' ')
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
