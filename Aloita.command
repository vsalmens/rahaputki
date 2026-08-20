#!/bin/bash
# Rahaputki. Tama on pelkka tynka: kaikki logiikka on kansiossa koodi/,
# joten tata tiedostoa ei tarvitse koskaan paivittaa.

cd "$(dirname "$0")" || exit 1

if [ -f koodi/aloita.sh ]; then
    exec bash koodi/aloita.sh
fi

echo "Kansiota koodi/ ei loydy taalta:"
pwd
echo
echo "Rahaputken ohjelmatiedostot puuttuvat. Lataa paketti uudelleen ja"
echo "kopioi siita koodi-kansio tahan kansioon."
echo
read -r -p "Paina Enter sulkeaksesi..." || true
