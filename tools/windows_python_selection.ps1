# Regression tests for the real Windows PowerShell bootstrap, no user installs.
$ErrorActionPreference = 'Stop'
$Source = Join-Path (Split-Path $PSScriptRoot) 'Starta-FolderForge.ps1'
$Tokens = $null
$ParseErrors = $null
$Tree = [Management.Automation.Language.Parser]::ParseFile($Source, [ref]$Tokens, [ref]$ParseErrors)
if ($ParseErrors.Count) { throw ($ParseErrors | Out-String) }
foreach ($Statement in $Tree.EndBlock.Statements) {
    if ($Statement -is [Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($Statement.Extent.Text))
    }
}
$Root = Join-Path $env:TEMP ('FolderForge-selection-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($Root) | Out-Null
$Evidence = Join-Path (Split-Path $PSScriptRoot) 'windows-evidence'
[IO.Directory]::CreateDirectory($Evidence) | Out-Null
function Assert-Equal($Actual, $Expected, $Message) {
    if ($Actual -ne $Expected) { throw ($Message + ': actual=' + $Actual + ', expected=' + $Expected) }
}
try {
    $Real = Resolve-ExistingPython (Get-Command python.exe).Source
    if (-not $Real -or -not (Test-ExistingPythonGui $Real)) { throw 'The real installed test Python failed its hidden GUI probe' }
    # A native stub really starts and returns missing-customtkinter on the GUI
    # probe. It identifies itself as 3.15, but is NOT a downloaded Python 3.15.
    $FakeDir = Join-Path $Root 'Python315'
    [IO.Directory]::CreateDirectory($FakeDir) | Out-Null
    $FakeExe = Join-Path $FakeDir 'python.exe'
    $Identity = (@{ executable=$FakeExe; version=@(3,15) } | ConvertTo-Json -Compress).Replace('\','\\').Replace('"','\"')
    $Code = @"
using System;
public class BrokenPython {
    public static int Main(string[] args) {
        if (args.Length > 1 && args[1].Contains("json.dumps")) {
            Console.WriteLine("$Identity");
            return 0;
        }
        Console.Error.WriteLine("ModuleNotFoundError: No module named customtkinter");
        return 1;
    }
}
"@
    Add-Type -TypeDefinition $Code -OutputAssembly $FakeExe -OutputType ConsoleApplication
    Copy-Item -LiteralPath $FakeExe -Destination (Join-Path $FakeDir 'pythonw.exe')
    $Selected = Select-ExistingPython -Candidates @($FakeExe, $Real.Console)
    Assert-Equal $Selected $Real.Windowless 'Broken 3.15 did not fall back to the actual installed Python'
    & {
        # Deterministic ordering tests, independent of the runner's install list.
        function Resolve-ExistingPython([string]$Candidate) {
            if ($Candidate -eq 'broken') { return $null }
            return [pscustomobject]@{ Console=$Candidate; Windowless=('python-' + $Candidate);
                Major=3; Minor=([version]$Candidate).Minor; Version=$Candidate }
        }
        function Test-ExistingPythonGui($Python) {
            $Attempts.Add($Python.Version)
            return $Python.Version -eq $Working
        }
        $Working = '3.15'
        $Attempts = New-Object 'Collections.Generic.List[string]'
        Assert-Equal (Select-ExistingPython @('3.15','3.13','3.14')) 'python-3.15' 'Working primary was not retained'
        Assert-Equal ($Attempts -join ',') '3.15' 'Unnecessary GUI probes'
        $Working = '3.14'; $Attempts.Clear()
        Assert-Equal (Select-ExistingPython @('3.15','3.13','3.14')) 'python-3.14' '3.14 must be the first fallback'
        Assert-Equal ($Attempts -join ',') '3.15,3.14' 'Fallback priority'
        $Working = '3.13'; $Attempts.Clear()
        Assert-Equal (Select-ExistingPython @('3.15','3.13','3.14')) 'python-3.13' 'Other installed Python must remain available'
        Assert-Equal ($Attempts -join ',') '3.15,3.14,3.13' 'Fallback attempts'
        $Working = '3.14'; $Attempts.Clear()
        Assert-Equal (Select-ExistingPython @('broken','3.13','3.14')) 'python-3.14' 'Unrunnable primary must not bypass 3.14 priority'
        $Working = 'none'; $Attempts.Clear()
        if (Select-ExistingPython @('3.15','3.14','3.13')) { throw 'All failed candidates must fail closed' }
    }
    @{ native_failure_fallback=$true; primary_priority=$true; python314_priority=$true;
       other_installed_fallback=$true; all_failed_closed=$true; real_python=$Real.Console } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Evidence 'python-selection.json')
} catch {
    Write-Output ('::error title=Windows Python fallback::' + $_.Exception.ToString().Replace("`r",'%0D').Replace("`n",'%0A'))
    throw
} finally {
    if (Test-Path (Join-Path $Root 'logs/folderforge.log')) {
        Copy-Item (Join-Path $Root 'logs/folderforge.log') (Join-Path $Evidence 'python-selection.log')
    }
    Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
}
