param([string]$PreferredPython = '', [string]$Arguments64 = '', [switch]$MaintenanceOnly)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Logs = Join-Path $Root 'logs'
$Data = Join-Path $Root 'data'
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
try {
    [IO.Directory]::CreateDirectory($Logs) | Out-Null
    [IO.Directory]::CreateDirectory($Data) | Out-Null
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    if (-not $MaintenanceOnly) { [Windows.Forms.MessageBox]::Show('FolderForge needs a writable app folder. ' + $_.Exception.Message, 'FolderForge') | Out-Null }
    exit 1
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
function Write-RuntimeLog([string]$Level, [string]$Message) {
    $Line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " $Level [runtime:0] [bootstrap] $Message"
    try {
        [IO.File]::AppendAllText((Join-Path $Logs 'folderforge.log'), $Line + [Environment]::NewLine, $Utf8NoBom)
        if ($Level -in @('WARNING','ERROR')) {
            [IO.File]::AppendAllText((Join-Path $Logs 'folderforge-errors.log'), $Line + [Environment]::NewLine, $Utf8NoBom)
        }
    } catch { }
}
function Write-CommandFailure([string]$Stage, $Result) {
    $Detail = ([string]$Result.Err).Trim()
    if (-not $Detail) { $Detail = ([string]$Result.Out).Trim() }
    if ($Detail.Length -gt 4000) { $Detail = $Detail.Substring($Detail.Length - 4000) }
    Write-RuntimeLog WARNING ($Stage + ' failed (' + $Result.Code + '): ' + $Detail)
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
function Get-PythonInfo([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $null }
    if ($Executable -match '\\Microsoft\\WindowsApps\\') { return $null } # Store alias is not an installation.
    if ([IO.Path]::GetFileName($Executable) -match '^pythonw') { $Executable = Join-Path (Split-Path $Executable) 'python.exe' }
    try {
        $Code = 'import sys,json; print(json.dumps(dict(version=list(sys.version_info[:3]), stable=sys.version_info.releaselevel=="final", base=sys.base_prefix, executable=getattr(sys,"_base_executable",sys.executable))))'
        $Result = Invoke-Hidden $Executable @('-I','-c',$Code)
        if ($Result.Code -ne 0) { return $null }
        $Info = $Result.Out.Trim() | ConvertFrom-Json
        if ($Info.version.Count -ne 3) { return $null }
        $Info | Add-Member -NotePropertyName Console -NotePropertyValue $Executable
        return $Info
    } catch { return $null }
}
function Test-AppRunning {
    foreach ($Name in @('Global\FolderForge_SingleInstance_Mutex','Local\FolderForge_SingleInstance_Mutex')) {
        try {
            $Mutex = [Threading.Mutex]::OpenExisting($Name)
            $Mutex.Dispose()
            return $true
        } catch [Threading.WaitHandleCannotBeOpenedException] { }
    }
    return $false
}
function Read-RuntimeState {
    $Path = Join-Path $Data 'python-runtime.json'
    if (Test-Path -LiteralPath $Path) {
        try { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json } catch { }
    }
    return $null
}
function Save-RuntimeState($State) {
    $Path = Join-Path $Data 'python-runtime.json'
    $Temp = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($Temp, ($State | ConvertTo-Json), [Text.Encoding]::UTF8)
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($Temp, $Path, $null) }
        else { [IO.File]::Move($Temp, $Path) }
    } finally { if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp } }
}
function Test-Environment([string]$Console) {
    $Code = 'import tkinter,customtkinter,PIL,pystray,pynput,win32api,tkinterdnd2; import importlib.metadata; print("OK")'
    $Check = Invoke-Hidden $Console @('-c',$Code)
    if ($Check.Code -ne 0) { Write-CommandFailure 'Environment imports' $Check; return $false }
    $Check = Invoke-Hidden $Console @('-m','pip','--isolated','check','--disable-pip-version-check')
    if ($Check.Code -ne 0) {
        Write-CommandFailure 'Shared environment dependency conflicts' $Check
        $script:RuntimeDependencyConflicts = $true
    }
    return $true # Unrelated shared-package conflicts must not block valid app imports.
}
function Get-LatestStableSeries {
    # Discover current stable CPython from the public winget manifests; no hard-coded release.
    $Headers = @{ 'User-Agent' = 'FolderForge'; 'Accept' = 'application/vnd.github+json' }
    $Url = 'https://api.github.com/repos/microsoft/winget-pkgs/contents/manifests/p/Python/Python/3'
    $Folders = Invoke-RestMethod -Uri $Url -Headers $Headers -TimeoutSec 20
    $Series = @($Folders |
        Where-Object { $_.name -match '^\d+$' } | Sort-Object { [int]$_.name } -Descending)
    foreach ($Item in $Series) {
        $Releases = Invoke-RestMethod -Uri $Item.url -Headers $Headers -TimeoutSec 20
        $Versions = @($Releases |
            Where-Object { $_.name -match '^3\.\d+\.\d+$' })
        if ($Versions.Count -gt 0) { return ('3.' + $Item.name) }
    }
    throw 'No stable Python release could be verified. No installation was attempted.'
}
function Get-WeeklyBoundary([datetime]$Now) {
    # Local clock, Monday 08:00; before that time belongs to the preceding week.
    $Days = (([int]$Now.DayOfWeek + 6) % 7)
    $Boundary = $Now.Date.AddDays(-$Days).AddHours(8)
    if ($Now -lt $Boundary) { $Boundary = $Boundary.AddDays(-7) }
    return $Boundary
}
function Test-PythonBusy {
    try { return @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'").Count -gt 0 }
    catch { Write-RuntimeLog WARNING 'Could not verify that shared Python is idle; maintenance deferred.'; return $true }
}
function Ensure-WeeklyTask($State) {
    try {
        $Digest = [Security.Cryptography.SHA256]::Create()
        try { $RootId = ([BitConverter]::ToString($Digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant())))).Replace('-','').Substring(0,12) }
        finally { $Digest.Dispose() }
        $Name = 'FolderForge Python weekly ' + $RootId
        $Hash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
        $Existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        if ($Existing -and $State.WeeklyTaskHash -eq $Hash) { return }
        $WindowlessHost = Join-Path ([Environment]::GetFolderPath('System')) 'wscript.exe'
        $Arguments = (Quote-Argument (Join-Path $Root 'Starta-FolderForge.vbs')) + ' --maintenance'
        $Action = New-ScheduledTaskAction -Execute $WindowlessHost -Argument $Arguments -WorkingDirectory $Root
        $Trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday -At '08:00'
        $Principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
        $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 12 -RestartInterval (New-TimeSpan -Minutes 15)
        Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
        $State.WeeklyTaskHash = $Hash
        Write-RuntimeLog INFO 'Shared Python/package maintenance scheduled Mondays at 08:00 local time; missed runs start when available.'
    } catch { Write-RuntimeLog WARNING ('Could not register weekly task; overdue checks run at next app start. ' + $_.Exception.Message) }
}
$Maintenance = New-Object Threading.Mutex($false, 'Local\FolderForge_RuntimeMaintenance')
$Held = $false
$ExitCode = 0
try {
    try { $Held = $Maintenance.WaitOne(300000) } catch [Threading.AbandonedMutexException] { $Held = $true }
    if (-not $Held) { throw 'Another runtime check is still active. Try starting again later.' }
    Push-Location $Root
    $Loaded = Read-RuntimeState
    $State = @{}
    if ($Loaded) { foreach ($Property in $Loaded.PSObject.Properties) { $State[$Property.Name] = $Property.Value } }
    $Now = Get-Date
    if (-not $State.WeeklyEnabledAt) { $State.WeeklyEnabledAt = $Now.ToString('o') }
    Ensure-WeeklyTask $State
    Save-RuntimeState $State
    $Boundary = Get-WeeklyBoundary $Now
    $Due = $Boundary -ge ([datetime]$State.WeeklyEnabledAt) -and
        (-not $State.LastAttemptPeriod -or ([datetime]$State.LastAttemptPeriod) -lt $Boundary)
    $LegacyConsole = [string]$State.Console
    if ($MaintenanceOnly -and -not $Due) {
        Write-RuntimeLog INFO 'Weekly maintenance already handled or not yet due; scheduled run skipped.'
        exit 0
    }
    $Candidates = New-Object 'Collections.Generic.List[string]'
    $Registry = @()
    if ($State -and $State.Console) { $Candidates.Add([string]$State.Console) }
    if ($PreferredPython) { $Candidates.Add($PreferredPython) }
    foreach ($Hive in @('HKCU:\Software\Python\PythonCore','HKLM:\Software\Python\PythonCore','HKLM:\Software\WOW6432Node\Python\PythonCore')) {
        if (Test-Path $Hive) {
            foreach ($Key in Get-ChildItem $Hive) {
                $Install = Get-Item ($Key.PSPath + '\InstallPath') -ErrorAction SilentlyContinue
                if ($Install) {
                    $Home = [string]$Install.GetValue('')
                    if ($Home) {
                        $Scope = if ($Hive.StartsWith('HKCU:')) { 'user' } else { 'machine' }
                        $Registry += [pscustomobject]@{ Home = $Home.TrimEnd('\'); Scope = $Scope }
                        $Candidates.Add((Join-Path $Home 'python.exe'))
                    }
                }
            }
        }
    }
    foreach ($Name in @('python.exe','python3.exe','pythonw.exe')) {
        foreach ($Command in @(Get-Command $Name -All -ErrorAction SilentlyContinue)) { $Candidates.Add($Command.Source) }
    }
    # Resolve real Microsoft Store runtimes without executing an uninstalled Store alias.
    if (Get-Command 'Get-AppxPackage' -ErrorAction SilentlyContinue) {
        foreach ($Store in @(Get-AppxPackage -Name 'PythonSoftwareFoundation.Python.3*' -ErrorAction SilentlyContinue)) {
            if ($Store.InstallLocation) { $Candidates.Add((Join-Path $Store.InstallLocation 'python.exe')) }
        }
    }
    $Py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($Py) {
        $Listed = Invoke-Hidden $Py.Source @('-0p')
        foreach ($Line in ($Listed.Out -split "`n")) {
            if ($Line -match '([A-Za-z]:\\.*pythonw?\.exe)\s*$') { $Candidates.Add($Matches[1].Trim()) }
        }
    }
    $Info = $null
    $Detected = @()
    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        $Found = Get-PythonInfo $Candidate
        if ($Found) { $Detected += $Found }
    }
    $Supported = @($Detected | Where-Object { $_.stable -and [version]($_.version[0..1] -join '.') -ge [version]'3.11' })
    if ($Supported.Count -gt 0) { $Info = $Supported[0] }
    elseif ($Detected.Count -gt 0) { $Info = $Detected[0] }
    $InstalledNow = $false
    $Winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    $Running = Test-AppRunning
    if (-not $Info) {
        $ExistingCandidates = @($Candidates | Where-Object { $_ -notmatch '\\Microsoft\\WindowsApps\\' -and (Test-Path -LiteralPath $_ -PathType Leaf) })
        if ($Registry.Count -gt 0 -or $ExistingCandidates.Count -gt 0) { throw 'Python is registered but cannot be used. Repair that installation; no second Python was installed.' }
        if ($Running) { throw 'FolderForge is already running; runtime changes were deferred.' }
        if (-not $Winget) { throw 'Python is missing and Windows App Installer (winget) is unavailable. Install App Installer, then retry.' }
        if (Test-PythonBusy) { throw 'A Python process exists but its installation could not be identified safely. No additional Python was installed.' }
        if ($MaintenanceOnly -and $Due) {
            $State.LastAttemptPeriod = $Boundary.ToString('o')
            $State.LastAttemptAt = (Get-Date).ToString('o')
            $State.LastResult = 'running'
            Save-RuntimeState $State
        }
        $Series = Get-LatestStableSeries
        Write-RuntimeLog INFO "Python is missing. Installing stable Python $Series once."
        $Installed = Invoke-Hidden $Winget.Source @('install','--id',"Python.Python.$Series",'--exact','--source','winget','--scope','user','--silent','--disable-interactivity','--accept-source-agreements','--accept-package-agreements')
        if ($Installed.Code -ne 0) { Write-CommandFailure 'Python installation' $Installed; throw "Python installation failed ($($Installed.Code))." }
        $Home = (Get-Item "HKCU:\Software\Python\PythonCore\$Series\InstallPath").GetValue('')
        $Info = Get-PythonInfo (Join-Path $Home 'python.exe')
        if (-not $Info) { throw 'The new Python installation could not be verified.' }
        $InstalledNow = $true
    }
    if (-not $Info.stable) { throw 'Only a prerelease Python was found. No additional Python was installed. Select a stable existing installation.' }
    $Series = "$($Info.version[0]).$($Info.version[1])"
    if ([version]$Series -lt [version]'3.11') { throw "Existing Python $Series is too old. No parallel Python was installed. Upgrade it explicitly to Python 3.11+ first." }
    # Use the actual shared base interpreter, never the old app virtual environment.
    $Console = [string]$Info.executable
    if (-not $Running) {
        $State.Console = $Console
        $State.Base = [string]$Info.base
        $State.Version = ($Info.version -join '.')
        Save-RuntimeState $State
    }
    if ($Running) {
        Write-RuntimeLog INFO 'FolderForge is running. Package changes deferred; no maintenance attempt recorded.'
        if ($MaintenanceOnly) { $ExitCode = 2 }
        else {
            # A secondary start may use the still-running legacy environment only to
            # reach the existing instance's health/recovery flow during migration.
            if ($LegacyConsole -and (Test-Path -LiteralPath $LegacyConsole)) { $Console = $LegacyConsole }
        }
    } else {
        if ($Due) {
            if (Test-PythonBusy) {
                Write-RuntimeLog INFO 'Shared Python is in use. Weekly maintenance deferred without stopping programs.'
                if ($MaintenanceOnly) { $ExitCode = 2 }
            } else {
                # Record before network/mutation: repeated starts or offline failures
                # must not perform repeated update rounds during the same week.
                $State.LastAttemptPeriod = $Boundary.ToString('o')
                $State.LastAttemptAt = (Get-Date).ToString('o')
                $State.LastResult = 'running'
                Save-RuntimeState $State
                Write-RuntimeLog INFO 'Weekly shared Python/package maintenance started.'
                if (-not $InstalledNow) {
                    $Official = @($Registry | Where-Object { $_.Home -eq ([string]$Info.base).TrimEnd('\') })
                    if ($Winget -and $Official.Count -gt 0) {
                        $Upgrade = Invoke-Hidden $Winget.Source @('upgrade','--id',"Python.Python.$Series",'--exact','--source','winget','--scope',$Official[0].Scope,'--silent','--disable-interactivity','--accept-source-agreements','--accept-package-agreements')
                        $ExitHex = '{0:X8}' -f ([long]$Upgrade.Code -band 4294967295)
                        if ($Upgrade.Code -eq 0) { Write-RuntimeLog INFO 'Existing shared Python installation updated.' }
                        elseif ($ExitHex -in @('8A15002B','8A15004F')) { Write-RuntimeLog INFO 'Shared Python is already current in its existing series.' }
                        else { Write-CommandFailure 'Python upgrade' $Upgrade; Write-RuntimeLog WARNING 'Existing Python retained. No install fallback.' }
                    } else { Write-RuntimeLog WARNING 'Existing Python cannot be upgraded safely with winget; no other Python is installed.' }
                }
                $Code = 'import sys,json; sys.path.insert(0,sys.argv[1]); import settings; print(json.dumps(sorted(set(p for p in settings.REQUIRED_PACKAGES.values() if p))))'
                $Requirements = Invoke-Hidden $Console @('-c',$Code,$Root)
                if ($Requirements.Code -ne 0) { throw 'Could not read app package requirements.' }
                $Packages = @($Requirements.Out | ConvertFrom-Json)
                if ($Packages.Count -eq 0 -or @($Packages | Where-Object { $_ -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$' }).Count -gt 0) { throw 'Invalid app package requirements.' }
                $PipOptions = @('-m','pip','--isolated','--cache-dir',(Join-Path $Data 'python-pip-cache'))
                $NetworkOptions = @('--disable-pip-version-check','--index-url','https://pypi.org/simple','--timeout','15','--retries','1')
                $Pip = Invoke-Hidden $Console ($PipOptions + @('install','--upgrade','--upgrade-strategy','only-if-needed') + $NetworkOptions + @('pip') + $Packages)
                if ($Pip.Code -ne 0) { Write-CommandFailure 'Shared package upgrade' $Pip; $State.LastResult = 'failed' }
                elseif (-not (Test-Environment $Console)) { $State.LastResult = 'verification_failed' }
                else {
                    $State.LastResult = if ($script:RuntimeDependencyConflicts) { 'completed_with_conflicts' } else { 'completed' }
                    Write-RuntimeLog INFO ('Weekly shared Python/package maintenance: ' + $State.LastResult)
                }
                Save-RuntimeState $State
                if ($State.LastResult -in @('failed','verification_failed')) {
                    Write-RuntimeLog ERROR 'Weekly shared-package maintenance failed. Review the error log; shared packages may have changed.'
                    $ExitCode = 1
                    if (-not $MaintenanceOnly -and -not (Test-Environment $Console)) { throw 'Shared packages failed validation after maintenance. Review the error log before restarting.' }
                }
            }
        } else { Write-RuntimeLog INFO 'No weekly maintenance due; no online Python/package update check at this start.' }
        if (-not $MaintenanceOnly) {
            # Initial setup/migration may install missing packages, but pins all
            # installed distributions: it cannot upgrade existing packages off-schedule.
            $Probe = 'import sys,json,importlib.metadata as m; sys.path.insert(0,sys.argv[1]); import settings; names=sorted(set(p for p in settings.REQUIRED_PACKAGES.values() if p)); found={d.metadata["Name"].lower().replace("_","-") for d in m.distributions() if d.metadata["Name"]}; print(json.dumps([n for n in names if n.lower().replace("_","-") not in found]))'
            $MissingResult = Invoke-Hidden $Console @('-c',$Probe,$Root)
            if ($MissingResult.Code -ne 0) { throw 'Could not inspect required packages locally.' }
            $Missing = @($MissingResult.Out | ConvertFrom-Json)
            if ($Missing.Count -gt 0) {
                if (Test-PythonBusy) { throw 'Required shared packages are missing, but Python is in use. Close Python programs and start FolderForge again.' }
                $Pins = Join-Path $Data ('runtime-pins-' + [guid]::NewGuid().ToString('N') + '.txt')
                try {
                    $PinCode = 'import importlib.metadata as m; names=sorted({d.metadata["Name"] for d in m.distributions() if d.metadata["Name"]}); print("\n".join(n+"=="+m.version(n) for n in names))'
                    $PinResult = Invoke-Hidden $Console @('-c',$PinCode)
                    if ($PinResult.Code -ne 0) { throw 'Could not pin installed packages. No package installation attempted.' }
                    [IO.File]::WriteAllText($Pins,$PinResult.Out,$Utf8NoBom)
                    $HasPip = Invoke-Hidden $Console @('-m','pip','--version')
                    if ($HasPip.Code -ne 0) {
                        $Ensure = Invoke-Hidden $Console @('-m','ensurepip')
                        if ($Ensure.Code -ne 0) { Write-CommandFailure 'Missing pip' $Ensure; throw 'pip is missing and could not be installed.' }
                    }
                    $Install = Invoke-Hidden $Console (@('-m','pip','--isolated','install','--constraint',$Pins,'--disable-pip-version-check','--index-url','https://pypi.org/simple','--timeout','15','--retries','1') + $Missing)
                    if ($Install.Code -ne 0) { Write-CommandFailure 'Missing shared packages' $Install; throw 'Missing shared packages could not be installed without changing existing versions. See the error log.' }
                    Write-RuntimeLog INFO 'Missing shared packages installed; existing versions were pinned and not upgraded.'
                } finally { if (Test-Path -LiteralPath $Pins) { Remove-Item -LiteralPath $Pins } }
            }
        }
    }
    if (-not $MaintenanceOnly) {
        $Windowless = Join-Path (Split-Path $Console) 'pythonw.exe'
        if (-not (Test-Path -LiteralPath $Windowless -PathType Leaf)) { throw 'pythonw.exe is unavailable. Start aborted instead of opening a console.' }
        if (-not $Running) {
            # Refresh cached launchers too, so a later missing-Python start can bootstrap itself.
            $BrandCode = 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from updater import ensure_launcher; ensure_launcher(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[1])/"Icon"/"projektmapp.ico")'
            try {
                $Brand = Invoke-Hidden $Console @('-I','-c',$BrandCode,$Root,$Windowless)
                if ($Brand.Code -ne 0) { Write-RuntimeLog WARNING 'Native launcher refresh failed; use Starta-FolderForge.vbs if needed.' }
            } catch { Write-RuntimeLog WARNING 'Native launcher refresh failed; use Starta-FolderForge.vbs if needed.' }
        }
        $AppArgs = @('--tray')
        if ($Arguments64) { $AppArgs = @([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Arguments64)).Split(@([char]0), [StringSplitOptions]::RemoveEmptyEntries)) }
        $env:FOLDERFORGE_RUNTIME_READY = '1'
        $env:FOLDERFORGE_RUNTIME_POLICY = 'weekly-shared'
        $env:FOLDERFORGE_RUNTIME_SECONDARY = if ($Running) { '1' } else { '0' }
        $Start = New-Object Diagnostics.ProcessStartInfo
        $Start.FileName = $Windowless
        $Start.Arguments = (Quote-Argument (Join-Path $Root 'folder.pyw')) + ' ' + (($AppArgs | ForEach-Object { Quote-Argument $_ }) -join ' ')
        $Start.WorkingDirectory = $Root
        $Start.UseShellExecute = $false
        $Start.CreateNoWindow = $true
        $Start.EnvironmentVariables.Remove('PYTHONHOME')
        $Start.EnvironmentVariables.Remove('PYTHONPATH')
        $Child = [Diagnostics.Process]::Start($Start)
        # Keep maintenance serialized until the app owns its lock, even on slow startup.
        try {
            while (-not $Child.HasExited -and -not (Test-AppRunning)) { Start-Sleep -Milliseconds 100 }
        } finally { $Child.Dispose() }
    }
} catch {
    Write-RuntimeLog ERROR $_.Exception.Message
    if ($State -and $State.LastResult -eq 'running') {
        $State.LastResult = 'failed'
        try { Save-RuntimeState $State } catch { }
    }
    if (-not $MaintenanceOnly) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'FolderForge - Python check') | Out-Null
    }
    $ExitCode = 1
} finally {
    if ($Held) { $Maintenance.ReleaseMutex() }
    $Maintenance.Dispose()
    if ((Get-Location).Path -eq $Root) { Pop-Location }
}
exit $ExitCode
