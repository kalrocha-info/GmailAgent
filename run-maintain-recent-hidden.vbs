Set WshShell = CreateObject("WScript.Shell")
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""D:\AGENTES-IA\run-maintain-recent.ps1"""
WshShell.Run command, 0, False
Set WshShell = Nothing
