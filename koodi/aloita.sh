#!/bin/bash
# Rahaputki - varsinainen kaynnistyslogiikka. Paivittyy koodi-kansion mukana.
# Etsii Pythonin, lukee inbox-kansion ja avaa raportin selaimeen.

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

"$PY" "$KOODI/kirjanpito.py" aja
echo

if "$PY" "$KOODI/kirjanpito.py" onko-dataa; then
    echo "Avataan raportti selaimeen. Sulje ikkuna kun olet valmis."
    echo
    "$PY" "$KOODI/kirjanpito.py" selaa
else
    echo
    read -r -p "Paina Enter sulkeaksesi..." || true
fi
exit 0
