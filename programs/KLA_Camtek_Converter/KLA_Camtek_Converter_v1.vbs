Option Explicit
' KLA-Camtek Converter v1 launcher (portable ZIP)
' Starts app_files\app.py with runtime\pythonw.exe: the official Windows Python (signed by the
' Python Software Foundation) with every package already inside (tools/build_portable.py).
' Nothing is installed, downloaded or changed on the PC, so no Python is needed.
' -E -s: ignore PYTHON* variables and per-user packages of a Python the PC may also have.
' Keep this file in CP949 (ANSI) without BOM: some Windows Script Host setups
' reject a UTF-8 BOM (error 800A0408 at line 1, char 1).

Const APP_ID = "KLA_Camtek_Converter"
Const APP_TITLE = "KLA-Camtek Converter v1"

Dim sh, fso, rootDir, appDir, pythonw
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
rootDir = fso.GetParentFolderName(WScript.ScriptFullName)
appDir = fso.BuildPath(rootDir, "app_files")
pythonw = fso.BuildPath(rootDir, "runtime\pythonw.exe")

If Not fso.FileExists(pythonw) Or Not fso.FileExists(fso.BuildPath(appDir, "app.py")) Then
    MsgBox "필수 파일이 없습니다:" & vbCrLf & pythonw & vbCrLf & vbCrLf & _
        "릴리스의 " & APP_ID & " ZIP 전체를 새 로컬 폴더에 압축 해제한 뒤 다시 실행하세요.", vbCritical, APP_TITLE
    WScript.Quit 1
End If

sh.CurrentDirectory = appDir
sh.Run """" & pythonw & """ -E -s """ & fso.BuildPath(appDir, "app.py") & """", 1, False
