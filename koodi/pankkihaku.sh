#!/bin/bash
# Rahaputki - automaattinen pankkihaku. Paivittyy koodi-kansion mukana.
# Nouda tapahtumat pankista, lue ne kirjanpitoon ja avaa raportti.
# Ensimmaisella kerralla kaynnistaa ohjatun kayttoonoton.

KOODI="$(cd "$(dirname "$0")" && pwd)"
JUURI="$KOODI"
[ "$(basename "$KOODI")" = "koodi" ] && JUURI="$(dirname "$KOODI")"
cd "$JUURI" || exit 1

PY=""
for komento in python3 python; do
    if command -v "$komento" >/dev/null 2>&1 &&
       "$komento" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
        PY="$komento"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "Python 3.9 tai uudempi puuttuu."
    echo "Asenna se osoitteesta https://www.python.org/downloads/"
    echo "ja kaksoisklikkaa uudelleen."
    echo
    read -r -p "Paina Enter sulkeaksesi..." || true
    exit 0
fi

LUKKO=4  # kirjanpito.py: lukko, ei virhe

"$PY" "$KOODI/kirjanpito.py" hae
TILA=$?
echo

# Muu haun virhe (verkko, vanhentunut valtuutus) ei estä inboxin lukemista:
# tiedostot voivat olla jo siella. Lukko estaa, koska aja torppaisi samaan.
if [ "$TILA" -eq "$LUKKO" ]; then
    read -r -p "Paina Enter sulkeaksesi..." || true
    exit "$TILA"
fi

"$PY" "$KOODI/kirjanpito.py" aja
TILA=$?
echo

if [ "$TILA" -ne 0 ]; then
    read -r -p "Paina Enter sulkeaksesi..." || true
    exit "$TILA"
fi

if "$PY" "$KOODI/kirjanpito.py" onko-dataa; then
    echo "Avataan raportti selaimeen. Sulje ikkuna kun olet valmis."
    echo
    "$PY" "$KOODI/kirjanpito.py" selaa
else
    read -r -p "Paina Enter sulkeaksesi..." || true
fi
exit 0
