' Запускает бота без окна консоли (двойной клик — и бот работает в фоне)
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run "cmd /c start_bot.bat", 0, False
