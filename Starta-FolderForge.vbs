Option Explicit
Dim shell, fs, script, command, result
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
script = fs.BuildPath(fs.GetParentFolderName(WScript.ScriptFullName), "Starta-FolderForge.ps1")
command = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & script & """"
If WScript.Arguments.Count > 0 Then
    If LCase(WScript.Arguments(0)) = "--maintenance" Then
        command = command & " -MaintenanceOnly"
        result = shell.Run(command, 0, True)
        WScript.Quit result
    End If
End If
shell.Run command, 0, False
