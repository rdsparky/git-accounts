@echo off
rem Command-line entry: gitacct status | list | use ACCOUNT [REPO] | test ACCOUNT | reauthor ACCOUNT [REPO]
set PYTHONPATH=%~dp0;%PYTHONPATH%
py -3 -m gitaccounts %*
