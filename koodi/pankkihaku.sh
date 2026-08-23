#!/bin/bash
# Rahaputki - kaynnistin, joka avaa suoraan pankkiyhteyssivun.
# Sama ohjelma kuin Aloita, eri aloitussivu.

exec bash "$(cd "$(dirname "$0")" && pwd)/aloita.sh" --avaa velho "$@"
