Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = chr(34) & currentDir & "\run_daily.bat" & chr(34)
WshShell.Run batPath, 0, False
