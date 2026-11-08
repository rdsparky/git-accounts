@echo off
rem Double-click to (re)create the Start menu and Desktop shortcuts for Git Accounts.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-shortcuts.ps1"
pause
