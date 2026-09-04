@echo off
rem Start Tyche, after checking that the executable is the one this archive
rem was built with.
rem
rem The archive ships Tyche.exe.sha256 beside the executable. This recomputes
rem that digest with certutil, which is part of Windows, and compares. What it
rem catches is a truncated download or a half-finished unpack -- damage, which
rem is the failure that actually happens to people.
rem
rem What it does NOT catch is tampering: the digest travels inside the same zip
rem as the file it describes, so whoever could replace one could replace the
rem other. The check worth doing against that is on the zip itself, against the
rem SHA-256 printed in the release notes, which reaches you by a route the
rem archive did not.
rem
rem This does not remove the SmartScreen warning and cannot. Only a
rem code-signing certificate does that.
rem
rem The messages are Italian, like the rest of the product, but this file
rem stays pure ASCII: a console window inherits the machine's OEM code page
rem (850 or 437 on an Italian install), so a UTF-8 accented letter arrives as
rem mojibake in the one place the user cannot ignore it. The phrasing avoids
rem accents rather than the file declaring chcp, which would change the code
rem page for whatever the caller runs next.

setlocal

set "APP=Tyche"
rem %~dp0 is the folder holding this script, with a trailing backslash. Not the
rem current directory: a double-click from Explorer can start anywhere.
set "HERE=%~dp0"
set "EXE=%HERE%%APP%.exe"
set "SUMS=%EXE%.sha256"

if not exist "%EXE%" (
    echo %APP%: nessun eseguibile in "%EXE%" 1>&2
    echo L'archivio non risulta scompattato del tutto. Scompattarlo di nuovo. 1>&2
    if not defined CI pause
    exit /b 1
)

rem An escape hatch that is deliberately explicit. Somebody who has patched the
rem executable on purpose should be able to run it; somebody who has not should
rem never see this path taken silently.
if "%TYCHE_SKIP_VERIFY%"=="1" (
    echo %APP%: verifica dell'impronta saltata ^(TYCHE_SKIP_VERIFY=1^) 1>&2
    goto :launch
)

if not exist "%SUMS%" (
    echo %APP%: manca %APP%.exe.sha256, avvio senza verifica 1>&2
    goto :launch
)

rem The file is in the format sha256sum -c reads: "<hex>  <name>".
rem Cleared first: setlocal copies the caller's environment, and a variable of
rem either name already in it would win the `if not defined` below.
set "EXPECTED="
set "ACTUAL="
for /f "usebackq tokens=1" %%H in ("%SUMS%") do (
    if not defined EXPECTED set "EXPECTED=%%H"
)

rem Line 1 of certutil's output is a heading and line 3 a success message; the
rem digest is line 2. Some builds space the bytes apart, so spaces come back
rem out before comparing.
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%EXE%" SHA256 2^>nul') do (
    if not defined ACTUAL set "ACTUAL=%%H"
)
if defined ACTUAL set "ACTUAL=%ACTUAL: =%"

if not defined ACTUAL (
    echo %APP%: certutil non ha calcolato l'impronta, avvio senza verifica 1>&2
    goto :launch
)
if not defined EXPECTED (
    echo %APP%: %APP%.exe.sha256 non contiene nulla, avvio senza verifica 1>&2
    goto :launch
)

rem /i because certutil's case has changed between Windows versions.
if /i not "%ACTUAL%"=="%EXPECTED%" (
    echo %APP%: l'eseguibile non corrisponde a %APP%.exe.sha256. 1>&2
    echo   atteso  %EXPECTED% 1>&2
    echo   trovato %ACTUAL% 1>&2
    echo. 1>&2
    echo Scaricare di nuovo l'archivio e scompattarlo un'altra volta. Se ancora 1>&2
    echo non corrisponde, confrontare lo zip con lo SHA-256 riportato nelle note 1>&2
    echo della release prima di eseguire qualunque cosa ne esca. 1>&2
    if not defined CI pause
    exit /b 1
)

:launch
rem With arguments -- --version, --self-check -- run in the foreground, so
rem whatever is printed lands in the console the caller is watching.
if not "%~1"=="" goto :foreground

rem With none, which is what a double-click sends, this console has one job
rem left: stay up while the program starts, and say what it is waiting for.
rem Windows scans every file in a freshly unpacked folder before it will let
rem any of them load, and this folder holds PyTorch, so the first launch is
rem slow. A console that vanishes instantly leaves nothing on screen for it.
rem
rem Asking Windows when the program is ready needs PowerShell. Without it there
rem is no way to know, so hand off and let this window close at once.
where powershell > nul 2>&1
if errorlevel 1 goto :handoff

echo Avvio di %APP% in corso...
echo.
echo Il primo avvio richiede tempo: Windows controlla ogni file della cartella
echo prima di poterne eseguire uno. Questa finestra si chiude da sola non
echo appena %APP% compare sullo schermo.

rem The path travels in a variable rather than inside the quoted -Command
rem string, so a folder name containing a space or a quote cannot break the
rem PowerShell that receives it.
set "_LAUNCH_TARGET=%EXE%"
set "_LAUNCH_TIMEOUT=%TYCHE_LAUNCH_TIMEOUT%"
if not defined _LAUNCH_TIMEOUT set "_LAUNCH_TIMEOUT=180"

rem Waits for a window by polling the started process for a main window handle.
rem
rem A folder build is a single process, so the handle Start-Process returns is
rem the one that draws the window. A onefile build would not be -- it is a
rem bootloader plus a child, and waiting on the bootloader waits forever while
rem the program sits on screen. Argus hit exactly that. Tyche is a folder build
rem precisely because bundling PyTorch makes onefile unpack hundreds of
rem megabytes on every launch, so the simple wait is the correct one here; if
rem this ever becomes a onefile build, poll by image name instead.
powershell -NoProfile -Command "$p = Start-Process -FilePath ${env:_LAUNCH_TARGET} -PassThru; $deadline = (Get-Date).AddSeconds([int]${env:_LAUNCH_TIMEOUT}); while ((Get-Date) -lt $deadline) { $p.Refresh(); if ($p.HasExited) { exit 4 }; if ($p.MainWindowHandle -ne [IntPtr]::Zero) { exit 0 }; Start-Sleep -Milliseconds 200 }; exit 3"
set "STATUS=%ERRORLEVEL%"

rem Past this point the program has been started, whatever PowerShell reported.
rem Nothing below may start it a second time.
if "%STATUS%"=="0" exit /b 0

if "%STATUS%"=="4" (
    echo. 1>&2
    echo %APP% ha smesso di funzionare prima di aprire una finestra. 1>&2
    if not defined CI pause
    exit /b 1
)

echo. 1>&2
echo %APP% non ha ancora aperto una finestra. Potrebbe essere ancora in avvio. 1>&2
if not defined CI pause
exit /b 0

:handoff
start "" "%EXE%"
exit /b 0

:foreground
"%EXE%" %*
exit /b %ERRORLEVEL%
