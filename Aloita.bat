@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Rahaputki. Tama on pelkka tynka: kaikki logiikka on kansiossa koodi\,
rem joten tata tiedostoa ei tarvitse koskaan paivittaa.

if exist "koodi\aloita.bat" goto aja
echo Kansiota koodi ei loydy taalta:
cd
echo.
echo Rahaputken ohjelmatiedostot puuttuvat. Lataa paketti uudelleen ja
echo kopioi siita koodi-kansio tahan kansioon.
echo.
pause
goto loppu

:aja
call "koodi\aloita.bat"

:loppu
