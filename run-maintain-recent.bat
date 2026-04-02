@echo off
cd /d D:\AGENTES-IA
if not exist "D:\AGENTES-IA\state" mkdir "D:\AGENTES-IA\state"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\AGENTES-IA\run-maintain-recent.ps1"
