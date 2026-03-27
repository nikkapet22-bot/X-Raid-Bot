Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
command = "cmd /c cd /d """ & repoRoot & """ && pythonw -m raidbot.desktop.app"
shell.Run command, 0, False
