Option Explicit
Dim sh, fso, rootDir, bootFile, command
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
rootDir = fso.GetParentFolderName(WScript.ScriptFullName)
bootFile = fso.BuildPath(rootDir, "app_files\bootstrap.pyw")
If Not fso.FileExists(bootFile) Then
    MsgBox "Required file is missing:" & vbCrLf & bootFile, vbCritical, "AOI Color-Gray Matcher v15"
    WScript.Quit 1
End If
command = "pyw """ & bootFile & """"
sh.Run command, 0, False
