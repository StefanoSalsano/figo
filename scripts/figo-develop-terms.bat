:: Batch file that opens up a windows terminal with 5 tabs connected to FIGO servers
:: Inside each tab the terminal "profile" executes tmux-resume so that
:: all the working session are resumed

@echo off

:: Open the first window without specifying --window 0
start wt new-tab --profile "Command Prompt"
timeout /t 2 /nobreak >nul

:: Use --window 0 to open tabs in just created window
wt --window 0 new-tab --profile "Ubuntu"
timeout /t 1 /nobreak >nul

wt --window 0 new-tab --profile "gpu_server"
timeout /t 1 /nobreak >nul

wt --window 0 new-tab --profile "blade3"
timeout /t 1 /nobreak >nul

wt --window 0 new-tab --profile "figo-2gpu"
timeout /t 1 /nobreak >nul