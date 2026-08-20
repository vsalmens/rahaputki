@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Rahaputki - automaattinen pankkihaku. Tama on pelkka tynka: kaikki
rem logiikka on kansiossa koodi\, joten tata ei tarvitse koskaan paivittaa.

if exist "koodi\pankkihaku.bat" goto aja
echo Kansiota koodi ei loydy taalta:
cd
echo.
echo Rahaputken ohjelmatiedostot puuttuvat. Lataa paketti uudelleen ja
echo kopioi siita koodi-kansio tahan kansioon.
echo.
pause
goto loppu

:aja
call "koodi\pankkihaku.bat"

:loppu
