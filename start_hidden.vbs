' Runs start_rektaprint.bat with no visible window
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.Run Chr(34) & folder & "\start_rektaprint.bat" & Chr(34), 0, False
