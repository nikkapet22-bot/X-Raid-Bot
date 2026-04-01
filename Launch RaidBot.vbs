Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = repoRoot
shell.Run "pythonw -m raidbot.desktop.app", 1, False
