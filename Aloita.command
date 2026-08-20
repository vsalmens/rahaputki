#!/bin/bash
# Rahaputki — kaksoisklikkaa tata tiedostoa.
# Etsii Pythonin, lukee inbox-kansion ja avaa raportin selaimeen.

cd "$(dirname "$0")" || exit 1

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
    read -r -p "Paina Enter sulkeaksesi..."
    exit 1
fi

"$PY" kirjanpito.py aja
echo

if "$PY" -c "import pathlib, sys
p = pathlib.Path('data/tapahtumat.csv')
sys.exit(0 if p.exists() and len(p.read_text(encoding='utf-8').splitlines()) > 1 else 1)"; then
    echo "Avataan raportti selaimeen. Sulje ikkuna kun olet valmis."
    echo
    "$PY" kirjanpito.py selaa
else
    echo
    read -r -p "Paina Enter sulkeaksesi..." || true
fi
exit 0
