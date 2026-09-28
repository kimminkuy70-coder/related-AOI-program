Option Explicit
' Wafer Map Converter WebView2 v5 launcher
' Fast path : the ready file written by app_files\setup_env.py points to the shared
'             venv, so the program starts directly (no install check, one Python start).
' Slow path : first run, Python changed or environment broken -> setup_env.py
'             (pick Python, create venv, pip install online, then start the program).
' Keep this file in CP949 (ANSI) without BOM: some Windows Script Host setups
' reject a UTF-8 BOM (error 800A0408 at line 1, char 1).

Const APP_ID = "Wafer_Map_Converter"
Const APP_TITLE = "Wafer Map Converter WebView2 v5"
Const ENV_REVISION = 1
Const MIN_MINOR = 6
Const PYTHON_WINGET_ID = "Python.Python.3.12"
Const PYTHON_URL = "https://www.python.org/downloads/windows/"

Dim sh, fso, rootDir, appDir, localData
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
rootDir = fso.GetParentFolderName(WScript.ScriptFullName)
appDir = fso.BuildPath(rootDir, "app_files")
localData = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%")

If Not fso.FileExists(fso.BuildPath(appDir, "app.py")) Or Not fso.FileExists(fso.BuildPath(appDir, "setup_env.py")) Then
    MsgBox "필수 파일이 없습니다:" & vbCrLf & appDir & vbCrLf & vbCrLf & "ZIP 전체를 새 로컬 폴더에 압축 해제한 뒤 다시 실행하세요.", vbCritical, APP_TITLE
    WScript.Quit 1
End If

If TryFastLaunch() Then WScript.Quit 0
RunSetup
WScript.Quit 0

Function Q(text)
    Q = """" & text & """"
End Function

Function TryFastLaunch()
    Dim readyFile, ts, revision, envPython, basePython
    TryFastLaunch = False
    readyFile = localData & "\AOI_Tools\ready\" & APP_ID & ".txt"
    If Not fso.FileExists(readyFile) Then Exit Function
    On Error Resume Next
    Set ts = fso.OpenTextFile(readyFile, 1, False, -1)   ' -1: Unicode (UTF-16), user paths may be Korean
    revision = Trim(ts.ReadLine)
    envPython = Trim(ts.ReadLine)
    basePython = Trim(ts.ReadLine)
    ts.Close
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If
    On Error GoTo 0
    If Not IsNumeric(revision) Then Exit Function
    If CLng(revision) < ENV_REVISION Then Exit Function
    ' The venv only works while its base Python is still installed.
    If Not fso.FileExists(envPython) Or Not fso.FileExists(basePython) Then Exit Function
    sh.CurrentDirectory = appDir
    sh.Run Q(envPython) & " " & Q(fso.BuildPath(appDir, "app.py")), 1, False
    TryFastLaunch = True
End Function

Sub RunSetup()
    Dim runner, answer
    runner = FindPythonRunner()
    If runner = "" Then
        answer = MsgBox("Python 3.9 이상(64bit)이 설치되어 있지 않습니다." & vbCrLf & vbCrLf & _
            "지금 Python 3.12를 설치할까요? (사용자 계정 설치, 관리자 권한 불필요)" & vbCrLf & _
            "'아니요'를 누르면 다운로드 페이지를 엽니다.", vbYesNoCancel + vbQuestion, APP_TITLE)
        If answer = vbYes Then
            If Not InstallPythonWithWinget() Then Exit Sub
            runner = FindPythonRunner()
            If runner = "" Then
                MsgBox "Python 설치 후에도 찾지 못했습니다. PC에 로그아웃/로그인 후 다시 실행하세요.", vbExclamation, APP_TITLE
                Exit Sub
            End If
        ElseIf answer = vbNo Then
            sh.Run Q(PYTHON_URL), 1, False
            Exit Sub
        Else
            Exit Sub
        End If
    End If
    sh.CurrentDirectory = appDir
    sh.Run runner & " " & Q(fso.BuildPath(appDir, "setup_env.py")), 1, False
End Sub

Function InstallPythonWithWinget()
    Dim winget, code
    InstallPythonWithWinget = False
    winget = localData & "\Microsoft\WindowsApps\winget.exe"
    If Not fso.FileExists(winget) Then
        MsgBox "winget을 찾을 수 없어 다운로드 페이지를 엽니다." & vbCrLf & "Python 3.12 (64bit)를 설치한 뒤 다시 실행하세요.", vbInformation, APP_TITLE
        sh.Run Q(PYTHON_URL), 1, False
        Exit Function
    End If
    code = sh.Run(Q(winget) & " install -e --id " & PYTHON_WINGET_ID & " --scope user --accept-package-agreements --accept-source-agreements", 1, True)
    If code <> 0 Then
        MsgBox "Python 자동 설치에 실패했습니다(코드 " & code & ")." & vbCrLf & "다운로드 페이지에서 직접 설치하세요.", vbExclamation, APP_TITLE
        sh.Run Q(PYTHON_URL), 1, False
        Exit Function
    End If
    InstallPythonWithWinget = True
End Function

' Any Python 3.6+ can run setup_env.py; setup_env.py itself picks the best
' supported Python (3.9-3.14) for the environment.
Function FindPythonRunner()
    Dim candidates, path
    FindPythonRunner = ""
    candidates = Array(sh.ExpandEnvironmentStrings("%WINDIR%") & "\pyw.exe", localData & "\Programs\Python\Launcher\pyw.exe")
    For Each path In candidates
        If fso.FileExists(path) Then
            FindPythonRunner = Q(path) & " -3"
            Exit Function
        End If
    Next
    path = FindRegisteredPython()
    If path <> "" Then FindPythonRunner = Q(path)
End Function

Function FindRegisteredPython()
    Const HKCU = &H80000001
    Const HKLM = &H80000002
    Dim reg, hives, bases, hive, base, tags, tag, installPath, exe, best, bestMinor, minor
    FindRegisteredPython = ""
    best = ""
    bestMinor = -1
    On Error Resume Next
    Set reg = GetObject("winmgmts:{impersonationLevel=impersonate}!\\.\root\default:StdRegProv")
    If Err.Number <> 0 Then
        Err.Clear
        Exit Function
    End If
    hives = Array(HKCU, HKLM)
    bases = Array("SOFTWARE\Python\PythonCore", "SOFTWARE\WOW6432Node\Python\PythonCore")
    For Each hive In hives
        For Each base In bases
            tags = Null
            reg.EnumKey hive, base, tags
            If IsArray(tags) Then
                For Each tag In tags
                    minor = MinorOf(tag)
                    If minor >= MIN_MINOR And minor > bestMinor Then
                        installPath = ""
                        reg.GetStringValue hive, base & "\" & tag & "\InstallPath", "", installPath
                        If Not IsNull(installPath) And installPath <> "" Then
                            exe = fso.BuildPath(installPath, "pythonw.exe")
                            If fso.FileExists(exe) Then
                                best = exe
                                bestMinor = minor
                            End If
                        End If
                    End If
                Next
            End If
        Next
    Next
    On Error GoTo 0
    FindRegisteredPython = best
End Function

' "3.12" / "3.12-32" -> 12, anything that is not Python 3 -> -1
Function MinorOf(tag)
    Dim i, ch, digits
    MinorOf = -1
    If Left(tag, 2) <> "3." Then Exit Function
    digits = ""
    For i = 3 To Len(tag)
        ch = Mid(tag, i, 1)
        If ch < "0" Or ch > "9" Then Exit For
        digits = digits & ch
    Next
    If digits <> "" Then MinorOf = CInt(digits)
End Function
