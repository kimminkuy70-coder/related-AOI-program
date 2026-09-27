Option Explicit
Dim sh,fso,root,boot,cmd
Set sh=CreateObject("WScript.Shell")
Set fso=CreateObject("Scripting.FileSystemObject")
root=fso.GetParentFolderName(WScript.ScriptFullName)
boot=fso.BuildPath(root,"app_files\bootstrap.pyw")
If Not fso.FileExists(boot) Then
 MsgBox "필수 실행 파일이 없습니다:" & vbCrLf & boot,vbCritical,"Wafer Map Converter WebView2 v4"
 WScript.Quit 1
End If
cmd="pyw """ & boot & """"
sh.Run cmd,0,False
