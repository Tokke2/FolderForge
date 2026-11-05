param([string]$PreferredPython = '', [string]$Arguments64 = '')
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
    [Windows.Forms.MessageBox]::Show('FolderForge needs a writable app folder. ' + $_.Exception.Message, 'FolderForge') | Out-Null
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
    $Check = Invoke-Hidden $Console @('-I','-c',$Code)
    if ($Check.Code -ne 0) { Write-CommandFailure 'Environment imports' $Check; return $false }
    $Check = Invoke-Hidden $Console @('-I','-m','pip','--isolated','check','--disable-pip-version-check')
    if ($Check.Code -ne 0) { Write-CommandFailure 'Environment pip check' $Check }
    return $Check.Code -eq 0
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
$Maintenance = New-Object Threading.Mutex($false, 'Local\FolderForge_RuntimeMaintenance')
$Held = $false
$ExitCode = 0
try {
    try { $Held = $Maintenance.WaitOne(300000) } catch [Threading.AbandonedMutexException] { $Held = $true }
    if (-not $Held) { throw 'Another runtime check is still active. Try starting again later.' }
    Push-Location $Root
    Write-RuntimeLog INFO 'Startup Python and app-package check started.'
    $State = Read-RuntimeState
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
    Write-RuntimeLog INFO "Python $($Info.version -join '.') detected; existing series $Series is retained."
    if (-not $Running -and -not $InstalledNow) {
        $Official = @($Registry | Where-Object { $_.Home -eq ([string]$Info.base).TrimEnd('\') })
        if ($Winget -and $Official.Count -gt 0) {
            # Never update a base interpreter while another program is using it.
            $Busy = $true
            try {
                $Busy = @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'").Count -gt 0
            } catch { Write-RuntimeLog WARNING 'Could not verify that Python is idle; binary upgrade deferred.' }
            if (-not $Busy) {
                $Upgrade = Invoke-Hidden $Winget.Source @('upgrade','--id',"Python.Python.$Series",'--exact','--source','winget','--scope',$Official[0].Scope,'--silent','--disable-interactivity','--accept-source-agreements','--accept-package-agreements')
                $ExitHex = '{0:X8}' -f ([long]$Upgrade.Code -band 4294967295)
                if ($Upgrade.Code -eq 0) { Write-RuntimeLog INFO 'Existing Python installation updated.' }
                elseif ($ExitHex -in @('8A15002B','8A15004F')) { Write-RuntimeLog INFO 'Python is already at the latest available patch in its existing series.' }
                else { Write-CommandFailure 'Python upgrade' $Upgrade; Write-RuntimeLog WARNING "No Python upgrade completed (winget code $ExitHex); existing installation retained. No install fallback." }
                $Refreshed = Get-PythonInfo $Info.executable
                if ($Refreshed) { $Info = $Refreshed }
            } else { Write-RuntimeLog INFO 'Python is in use; binary upgrade deferred without stopping other programs.' }
        } else { Write-RuntimeLog WARNING 'Existing Python cannot be safely upgraded with winget; retained without installing another Python.' }
    }
    $Console = if ($State) { [string]$State.Console } else { '' }
    if ($Running) {
        Write-RuntimeLog INFO 'FolderForge is already running. Package changes deferred to avoid changing loaded files.'
        if (-not $Console -or -not (Test-Path -LiteralPath $Console)) { $Console = [string]$Info.Console }
    } else {
        $Code = 'import sys,json; sys.path.insert(0,sys.argv[1]); import settings; print(json.dumps(sorted(set(p for p in settings.REQUIRED_PACKAGES.values() if p))))'
        $Requirements = Invoke-Hidden $Info.executable @('-I','-c',$Code,$Root)
        if ($Requirements.Code -ne 0) { throw 'App package requirements could not be read.' }
        $Packages = @($Requirements.Out | ConvertFrom-Json)
        if ($Packages.Count -eq 0 -or @($Packages | Where-Object { $_ -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$' }).Count -gt 0) { throw 'Invalid app package requirements.' }
        $Cache = Join-Path $Data 'python-pip-cache'
        $PipOptions = @('-I','-m','pip','--isolated','--cache-dir',$Cache)
        $NetworkOptions = @('--disable-pip-version-check','--index-url','https://pypi.org/simple','--timeout','15','--retries','1')
        $Valid = $Console -and (Test-Path -LiteralPath $Console) -and (Test-Environment $Console)
        $NeedsUpdate = -not $Valid
        if ($Valid) {
            $Plan = Join-Path $Data ('runtime-plan-' + [guid]::NewGuid().ToString('N') + '.json')
            try {
                # Resolve compatible upgrades without changing the active environment.
                $Check = Invoke-Hidden $Console ($PipOptions + @('install','--dry-run','--report',$Plan,'--upgrade','--upgrade-strategy','eager') + $NetworkOptions + @('pip') + $Packages)
                if ($Check.Code -eq 0 -and (Test-Path -LiteralPath $Plan)) {
                    $Report = Get-Content -Raw -LiteralPath $Plan | ConvertFrom-Json
                    $NeedsUpdate = @($Report.install).Count -gt 0
                } else { Write-CommandFailure 'Package update plan' $Check; Write-RuntimeLog WARNING 'Package update check failed or is offline; verified environment retained.' }
            } catch { Write-RuntimeLog WARNING 'Could not read package update plan; verified environment retained.' }
            finally { if (Test-Path -LiteralPath $Plan) { Remove-Item -LiteralPath $Plan } }
        }
        if ($NeedsUpdate) {
            # Stage at its permanent path. Do not move a venv: its scripts contain absolute paths.
            $Environment = Join-Path $Data ('python-envs\' + [guid]::NewGuid().ToString('N'))
            $CandidateConsole = Join-Path $Environment 'Scripts\python.exe'
            $CandidateWindowless = Join-Path $Environment 'Scripts\pythonw.exe'
            $Success = $false
            try {
                $Created = Invoke-Hidden $Info.executable @('-I','-m','venv',$Environment)
                if ($Created.Code -eq 0) {
                    $Pip = Invoke-Hidden $CandidateConsole ($PipOptions + @('install','--upgrade','--upgrade-strategy','eager') + $NetworkOptions + @('pip') + $Packages)
                    if ($Pip.Code -ne 0) { Write-CommandFailure 'Candidate package installation' $Pip }
                    $Success = $Pip.Code -eq 0 -and (Test-Environment $CandidateConsole) -and (Test-Path $CandidateWindowless)
                } else { Write-CommandFailure 'Candidate environment creation' $Created }
            } catch { Write-RuntimeLog WARNING 'Candidate environment could not be prepared; previous state was not changed.' }
            if (-not $Success -and (Test-Path -LiteralPath $Environment)) {
                try {
                    $CleanCode = 'import shutil,sys; shutil.rmtree(sys.argv[1])'
                    $Clean = Invoke-Hidden $Info.executable @('-I','-c',$CleanCode,$Environment)
                    if ($Clean.Code -ne 0) { Write-RuntimeLog WARNING 'Failed candidate cleanup was deferred.' }
                } catch { Write-RuntimeLog WARNING 'Failed candidate cleanup was deferred.' }
            }
            if ($Success) {
                $NewState = @{ Console = $CandidateConsole; Base = $Info.base; Version = ($Info.version -join '.'); Checked = (Get-Date).ToString('o') }
                Save-RuntimeState $NewState
                $Console = $CandidateConsole
                Write-RuntimeLog INFO 'App packages verified and updated in an isolated environment. Previous environment retained.'
            } elseif ($Valid) { Write-RuntimeLog WARNING 'Candidate package update failed; previous verified environment retained.' }
            else { throw 'Required Python packages or Tk could not be installed/verified. Check network/access and retry; no existing Python was replaced.' }
        } else { Write-RuntimeLog INFO 'App package check completed; existing verified environment reused.' }
    }
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
} catch {
    Write-RuntimeLog ERROR $_.Exception.Message
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'FolderForge - Python check') | Out-Null
    $ExitCode = 1
} finally {
    if ($Held) { $Maintenance.ReleaseMutex() }
    $Maintenance.Dispose()
    if ((Get-Location).Path -eq $Root) { Pop-Location }
}
exit $ExitCode
