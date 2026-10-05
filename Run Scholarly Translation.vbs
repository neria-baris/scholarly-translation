' Double-click this file to start the local translation server and open
' the website in your browser. A small window stays open while the
' server runs (it shows the local address and lets you stop the server
' with Ctrl+C); closing that window stops the server.
'
' This file only launches run-ui.ps1 -- it adds no logic of its own, so
' there is one place (run-ui.ps1 / scholarly_translation/web_ui.py) that
' decides how the server actually starts and opens the browser.

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = scriptDir & "\run-ui.ps1"

If Not fso.FileExists(scriptPath) Then
    MsgBox "run-ui.ps1 was not found in the project folder:" & vbCrLf & scriptPath, vbExclamation, "Scholarly Translation"
    WScript.Quit 1
End If

Set shell = CreateObject("WScript.Shell")
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File """ & scriptPath & """"
' Window style 1 = normal, visible window; "False" = do not wait for it,
' so this launcher returns immediately while the server keeps running.
shell.Run command, 1, False
