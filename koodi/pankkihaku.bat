@echo off
chcp 65001 >nul

rem Rahaputki - automaattinen pankkihaku. Paivittyy koodi-kansion mukana.
rem Nouda tapahtumat pankista, lue ne kirjanpitoon ja avaa raportti.
rem Ensimmaisella kerralla kaynnistaa ohjatun kayttoonoton.

set "KOODI=%~dp0"
set "KOODI=%KOODI:~0,-1%"
for %%I in ("%KOODI%") do set "KOODINIMI=%%~nxI"
set "JUURI=%KOODI%"
if /i "%KOODINIMI%"=="koodi" for %%I in ("%KOODI%") do set "JUURI=%%~dpI"
cd /d "%JUURI%"

set "PY="
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"
if defined PY goto tarkista
where python >nul 2>nul
if %errorlevel%==0 set "PY=python"

:tarkista
if not defined PY goto ei_pythonia
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>nul
if errorlevel 1 goto ei_pythonia

%PY% "%KOODI%\kirjanpito.py" hae
echo.
%PY% "%KOODI%\kirjanpito.py" aja
echo.

%PY% "%KOODI%\kirjanpito.py" onko-dataa
if errorlevel 1 goto tyhja

echo Avataan raportti selaimeen. Sulje tama ikkuna kun olet valmis.
echo.
%PY% "%KOODI%\kirjanpito.py" selaa
goto loppu

:tyhja
pause
goto loppu

:ei_pythonia
echo Python 3.9 tai uudempi puuttuu.
echo Asenna se osoitteesta https://www.python.org/downloads/
echo Muista valita asennuksessa "Add python.exe to PATH".
echo.
pause

:loppu
