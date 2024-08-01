@echo off

rem Change directory to where your Python script is located
cd /d "%USERPROFILE%\Documents\GitHub\SubnauticaSaveSaver"

rem Ensure the log directory exists
if not exist logs mkdir logs

rem Run Python script in the background and redirect output to a log file
start /B "" pythonw SubnauticaSaveSaver.py --silent > logs\app.log 2>&1

rem Exit the batch script without waiting for the Python script to finish
exit /b