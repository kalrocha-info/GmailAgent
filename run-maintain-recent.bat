@echo off
cd /d D:\AGENTES-IA
if not exist "D:\AGENTES-IA\state" mkdir "D:\AGENTES-IA\state"
"C:\Users\kalro\AppData\Local\Programs\Python\Python314\Scripts\gmail-agent.exe" maintain-recent --limit 300 --recent-days 60 --learning-days 14 >> "D:\AGENTES-IA\state\maintain-recent.log" 2>&1
