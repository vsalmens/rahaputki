#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
laskusta_csv.py — muunna luottokorttilaskun PDF putken ymmärtämäksi CSV:ksi.

  python3 laskusta_csv.py lasku.pdf [lasku2.pdf ...]     # -> inbox/<nimi>.csv
  python3 laskusta_csv.py --tili "S-Pankki Visa" *.pdf   # pakota kortin nimi
  python3 laskusta_csv.py --nayta lasku.pdf              # näytä miten rivit tulkitaan

Tekstin poiminta: pdfplumber (pip install pdfplumber) TAI pdftotext (poppler).
Kumpi tahansa riittää. Tämä skripti on tarkoituksella erillään ytimestä:
kirjanpito.py pysyy riippuvuusvapaana.

Miten se toimii: laskusta poimitaan rivit, jotka alkavat päivämäärällä ja
päättyvät summaan. Laskun oma vuosi päätellään dokumentin päiväyksistä
(vuodenvaihde hoituu: joulukuun ostot tammikuun laskulla saavat edellisen
vuoden). Ostot kirjataan negatiivisina (= menoja), hyvitykset positiivisina.
Laskun maksusuoritukset ohitetaan — ne näkyvät jo pankkitilillä Siirtona.
"""

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

MUUNNIN_VERSIO = "v5"

JUURI = Path(__file__).resolve().parent
INBOX = JUURI / "inbox"

# Tapahtumarivi: pvm [pvm2] teksti summa[-]
RIVI = re.compile(
    r"^\s*(?P<p>\d{1,2})\.(?P<k>\d{1,2})\.(?P<v>\d{2,4})?\s+"
    r"(?:\d{1,2}\.\d{1,2}\.(?:\d{2,4})?\s+)?"
    r"(?P<teksti>.+?)\s+"
    r"(?P<etu>-)?(?P<summa>(?:\d{1,3}(?:[ .]{1,2}\d{3})+|\d+),\d{2})(?P<taka>-)?\s*(?:EUR)?\s*$"
)
TAYSI_PVM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b")

# Rivit, jotka näyttävät tapahtumilta mutta eivät ole ostoja:
OHITA = re.compile(
    r"maksu[,.]?\s*kiitos|suoritus|maksettu|edellinen\s+(lasku|saldo)|"
    r"siirto\s+edelli|yhteens[aä]|loppusaldo|alkusaldo",
    re.IGNORECASE,
)
# Laskun ylätunnisteista yhteen liimautuneet rivit yms. — ohitetaan hiljaa,
# EIKÄ lasketa saldotarkistukseen (toisin kuin OHITA-maksurivit)
JUNK = re.compile(
    r"luottoraja|käyttövara|kuukausier|laskutuskausi|luoton\s+(nimi|numero)|"
    r"käytettäviss[aä]|eräpäiv[aä]|viitenumero|vähimmäismaksu",
    re.IGNORECASE,
)

KORTIT = [
    (re.compile(r"s-pankki|s-etukortti", re.I), "S-Pankki Visa"),
    (re.compile(r"op\s+(classic|gold|platinum|duo)|op\s+v[aä]hitt[aä]isasiakkaat|osuuspankki|"
                r"op[- ]visa|op[- ]mastercard|op\s+retail", re.I), "OP-kortti"),
]

# "Laskutuskausi 10.12.2025 - 09.01.2026" → kauden loppu on paras vuosiviite
KAUSI = re.compile(
    r"(?:Laskutuskausi|Tapahtumaerittely)\s+\d{1,2}\.\d{1,2}\.20\d{2}\s*[-\u2013\u2014]\s*"
    r"(\d{1,2})\.(\d{1,2})\.(20\d{2})", re.I)
KORKO = re.compile(r"^\s*Korko\s+(\d[\d ]*,\d{2})\s*$", re.I | re.M)
TARKSUMMA = re.compile(r"^\s*(?:Laskutuskauden\s+)?[Tt]apahtumat\s+yhteens[aä]\s+(-?\d[\d ]*,\d{2})\s*$", re.M)


def _eur(s: str) -> float:
    return round(float(s.replace(" ", "").replace(",", ".")), 2)


def _norm(t: str) -> str:
    """Sitkeät ja kapeat välilyönnit tavallisiksi — PDF-poiminta tuottaa näitä
    ja ne näyttävät konsolissa identtisiltä mutta kaatavat regexit."""
    t = (t.replace("\u00a0", " ").replace("\u202f", " ")
          .replace("\u2009", " ").replace("\u2007", " "))
    # nollaleveysmerkit (mm. U+FEFF, jota PDF-poiminta kylvää jopa tuhaterottimiksi) pois kokonaan
    return t.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "")


def pdf_teksti(polku: Path) -> str:
    """Poimi tekstikerros: ensin pdfplumber, sitten pdftotext -layout."""
    viat = []
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(polku) as pdf:
            t = "\n".join(p.extract_text() or "" for p in pdf.pages)
        if t.strip():
            return _norm(t)
        viat.append("pdfplumber on asennettu, mutta tekstiä ei irronnut (kokeillaan pdftotextiä)")
    except ImportError:
        viat.append("pdfplumber ei ole asennettu TÄLLE Pythonille → aja: python3 -m pip install pdfplumber")
    import subprocess
    try:
        r = subprocess.run(["pdftotext", "-layout", str(polku), "-"],
                           capture_output=True, text=True, check=True)
        if r.stdout.strip():
            return _norm(r.stdout)
        viat.append("pdftotext löytyi, mutta tekstiä ei irronnut — PDF lienee skannattu kuva (vaatisi OCR:n)")
    except FileNotFoundError:
        viat.append("pdftotext-komentoa ei löydy → macOS: brew install poppler")
    except subprocess.CalledProcessError as e:
        viat.append(f"pdftotext epäonnistui: {e}")
    sys.exit(f"En saanut tekstiä tiedostosta {polku.name}:\n  - " + "\n  - ".join(viat))


def summaksi(t) -> float:
    arvo = float(t["summa"].replace(" ", "").replace(".", "").replace(",", "."))
    hyvitys = bool(t["etu"] or t["taka"])
    # laskulla osto on positiivinen -> putkessa meno on negatiivinen; hyvitys päinvastoin
    return round(arvo if hyvitys else -arvo, 2)


def laskun_paivays(teksti: str):
    m = KAUSI.search(teksti)
    if m:
        p, k, v = m.groups()
        return date(int(v), int(k), int(p))
    pvmt = [date(int(v), int(k), int(p)) for p, k, v in TAYSI_PVM.findall(teksti)]
    return max(pvmt) if pvmt else date.today()


def tunnista_kortti(teksti: str, pakotettu: str | None) -> str:
    if pakotettu:
        return pakotettu
    for malli, nimi in KORTIT:
        if malli.search(teksti):
            return nimi
    return "Luottokortti"


def _yhdista_rivit(teksti: str):
    """Yhdistä rivinvaihdolle katkenneet tapahtumarivit (esim. pitkä kauppiasnimi
    jatkuu seuraavalla rivillä): päivämäärällä alkava rivi ilman loppusummaa imee
    jatkorivejä kunnes summa löytyy tai uusi päivämäärärivi/tyhjä rivi katkaisee."""
    ALKU = re.compile(r"^\s*\d{1,2}\.\d{1,2}\.(\d{2,4})?\s+\S")
    LOPPU = re.compile(r"\d,\d{2}-?\s*(?:EUR)?\s*$")
    ulos, pusku = [], None
    for rivi in teksti.splitlines():
        if pusku is not None:
            if ALKU.match(rivi) or not rivi.strip():
                ulos.append(pusku)
                pusku = None
            else:
                pusku = pusku + " " + rivi.strip()
                if LOPPU.search(pusku):
                    ulos.append(pusku)
                    pusku = None
                continue
        if ALKU.match(rivi) and not LOPPU.search(rivi):
            pusku = rivi.rstrip()
        else:
            ulos.append(rivi)
    if pusku is not None:
        ulos.append(pusku)
    return ulos


KORTTINUMERO = re.compile(r"\d{4}\s+\d{2}\*{2}\s+\*{4}\s+\d{4}")
RAHA = re.compile(r"(?<![\d,])(?P<etu>-)?(?P<summa>(?:\d{1,3}(?:[ .]{1,2}\d{3})+|\d+),\d{2})(?P<taka>-)?(?!\d)")
ALKU_PVM = re.compile(r"^\s*(?P<p>\d{1,2})\.(?P<k>\d{1,2})\.(?P<v>\d{2,4})?\s+"
                      r"(?:\d{1,2}\.\d{1,2}\.(?:\d{2,4})?\s+)?")


def tulkitse_rivi(raaka: str):
    """Tapahtumarivi → kentät, tai None. Kortinnumero riisutaan ennen jäsennystä,
    ja jos päärivikuvio ei osu, poimitaan rivin VIIMEINEN rahasumma (kattaa
    valuuttarivit ja oudot hännät), kunhan se on rivin loppupäässä."""
    rivi = KORTTINUMERO.sub(" ", raaka).rstrip()
    m = RIVI.match(rivi)
    if m:
        return {k: m.group(k) for k in ("p", "k", "v", "teksti", "etu", "summa", "taka")}
    d = ALKU_PVM.match(rivi)
    if not d:
        return None
    osumat = list(RAHA.finditer(rivi, d.end()))
    if not osumat:
        return None
    vika = osumat[-1]
    if vika.end() < len(rivi) - 15:
        return None  # summa keskellä riviä — liian epävarma
    teksti = rivi[d.end():vika.start()].strip()
    if not teksti:
        return None
    return {"p": d.group("p"), "k": d.group("k"), "v": d.group("v"), "teksti": teksti,
            "etu": vika.group("etu"), "summa": vika.group("summa"), "taka": vika.group("taka")}
ALKUSALDO_RE = re.compile(r"ALKUSALDO\s+(-?\d[\d ]*,\d{2})")
LOPPUSALDO_RE = re.compile(r"LOPPUSALDO\s+(-?\d[\d ]*,\d{2})")


def jasenna(teksti: str, kortti: str):
    lasku = laskun_paivays(teksti)
    rivit, ohitetut = [], []
    ohitettu_laskulla = 0.0  # ohitettujen rivien summa laskun omalla etumerkillä
    for raaka in _yhdista_rivit(teksti):
        m = tulkitse_rivi(raaka)
        if not m:
            continue
        nimi = re.sub(r"\s+", " ", m["teksti"]).strip()
        if JUNK.search(nimi) or len(nimi) > 70:
            continue  # yhteen liimautunut ylätunniste tms.
        if OHITA.search(nimi):
            ohitetut.append(raaka.strip())
            ohitettu_laskulla += -summaksi(m)
            continue
        if not re.search(r"[A-Za-zÅÄÖåäö]", nimi) or nimi.lower() in ("euro", "eur"):
            continue  # esim. tilisiirtolomakkeen irtorivit
        v = m["v"]
        if v:
            vuosi = int(v) + (2000 if int(v) < 100 else 0)
        else:
            vuosi = lasku.year - (1 if int(m["k"]) > lasku.month else 0)
        try:
            pvm = date(vuosi, int(m["k"]), int(m["p"]))
        except ValueError:
            continue
        rivit.append({
            "Ostopäivä": pvm.isoformat(),
            "Summa": f"{summaksi(m):.2f}",
            "Ostopaikka": re.sub(r"^Osto\s+", "", nimi),
            "Selite": f"korttilasku {lasku.isoformat()[:7]}",
            "Tili": kortti,
        })
    netto = round(sum(float(r["Summa"]) for r in rivit), 2)

    # Tarkistussumma kahdella tavalla:
    # 1) OP: "Tapahtumat yhteensä X" == poimitut rivit (korko listataan erikseen)
    # 2) S-Pankki: LOPPUSALDO - ALKUSALDO == poimitut + ohitetut (suoritukset) yhteensä
    tarkistus = "· laskulta ei löytynyt yhteissummaa/saldoja tarkistussummaksi"
    ts = TARKSUMMA.search(teksti)
    a, l = ALKUSALDO_RE.search(teksti), LOPPUSALDO_RE.search(teksti)
    def _fi(x):
        return f"{x:.2f}".replace(".", ",")
    if ts:
        ilmoitettu = _eur(ts.group(1))
        if abs(netto + ilmoitettu) < 0.01:
            tarkistus = f"✓ tarkistussumma täsmää laskun kanssa ({_fi(ilmoitettu)} €)"
        else:
            tarkistus = (f"⚠ TARKISTUSSUMMA EI TÄSMÄÄ: poimittu {_fi(-netto)} €, "
                         f"laskulla {_fi(ilmoitettu)} € — aja --nayta ja katso mikä rivi puuttuu")
    elif a and l:
        odotettu = round(_eur(l.group(1)) - _eur(a.group(1)), 2)
        toteutunut = round(-netto + ohitettu_laskulla, 2)
        if abs(odotettu - toteutunut) < 0.01:
            tarkistus = f"✓ saldotarkistus täsmää (muutos {_fi(odotettu)} €)"
        else:
            tarkistus = (f"⚠ SALDOTARKISTUS EI TÄSMÄÄ: rivit antavat {_fi(toteutunut)} €, "
                         f"saldoero on {_fi(odotettu)} € — aja --nayta ja katso mikä rivi puuttuu")

    # korko omana kulurivinään, jos laskulla päiväämätön Korko-rivi (OP:n tapa)
    mk = KORKO.search(teksti)
    if mk:
        rivit.append({
            "Ostopäivä": lasku.isoformat(),
            "Summa": f"{-_eur(mk.group(1)):.2f}",
            "Ostopaikka": "Korko (korttilasku)",
            "Selite": f"korttilasku {lasku.isoformat()[:7]}",
            "Tili": kortti,
        })
    return lasku, rivit, ohitetut, tarkistus


def nayta(polku: Path, pakotettu):
    teksti = pdf_teksti(polku)
    kortti = tunnista_kortti(teksti, pakotettu)
    lasku, rivit, ohitetut, tarkistus = jasenna(teksti, kortti)
    print(f"{polku.name}: muunnin {MUUNNIN_VERSIO}, kortti = {kortti}, laskutuskauden loppu = {lasku}\n")
    epavarmat = 0
    for raaka in _yhdista_rivit(teksti):
        if not raaka.strip():
            continue
        m = tulkitse_rivi(raaka)
        merkki, summa_info = "·", " " * 10
        if m:
            nimi = re.sub(r"\s+", " ", m["teksti"]).strip()
            if JUNK.search(nimi) or len(nimi) > 70:
                merkki = "·"
            else:
                merkki = "×" if OHITA.search(nimi) else "✔"
                summa_info = f"{summaksi(m):>9.2f} "
        elif (ALKU_PVM.match(KORTTINUMERO.sub(" ", raaka))
                and re.search(r",\d{2}(?!\d)", raaka)):
            merkki = "?"
            epavarmat += 1
        print(f" {merkki} {summa_info}{raaka.strip()[:100]}")
        if merkki == "?":
            print(f"     ↳ rivin häntä: {raaka.rstrip()[-45:]!r}")
    print(f"\n✔ poimitaan ({len(rivit)}) · × ohitetaan maksuna/summana ({len(ohitetut)}) · "
          f"· ei tapahtumarivi" + (f" · ? jäsentymätön päivämäärärivi ({epavarmat}) — LÄHETÄ HÄNTÄ" if epavarmat else ""))
    print(tarkistus)
    print("Jos jokin ostorivi jää ilman ✔-merkkiä, lähetä tämä tuloste (summat saa sotkea) niin sääntöä säädetään.")


def muunna(polku: Path, pakotettu):
    teksti = pdf_teksti(polku)
    kortti = tunnista_kortti(teksti, pakotettu)
    lasku, rivit, _, tarkistus = jasenna(teksti, kortti)
    if not rivit:
        print(f"⚠ {polku.name}: yhtään tapahtumariviä ei tunnistettu — aja --nayta ja katso miltä rivit näyttävät.")
        return
    INBOX.mkdir(exist_ok=True)
    ulos = INBOX / f"{polku.stem}.csv"
    with open(ulos, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Ostopäivä", "Summa", "Ostopaikka", "Selite", "Tili"], delimiter=";")
        w.writeheader()
        w.writerows(rivit)
    summa = sum(float(r["Summa"]) for r in rivit)
    print(f"✓ {polku.name} [{kortti}]: {len(rivit)} tapahtumaa, netto {summa:.2f} € → {ulos.relative_to(JUURI)}")
    print(f"  {tarkistus}")


def main():
    p = argparse.ArgumentParser(description="Korttilaskun PDF → CSV inboxiin")
    p.add_argument("pdf", nargs="+", help="korttilaskun PDF-tiedosto(t)")
    p.add_argument("--tili", help="pakota kortin nimi (esim. 'S-Pankki Visa')")
    p.add_argument("--nayta", action="store_true", help="näytä rivien tulkinta, älä kirjoita mitään")
    args = p.parse_args()
    for nimi in args.pdf:
        polku = Path(nimi)
        if not polku.exists():
            print(f"⚠ ei löydy: {nimi}")
            continue
        (nayta if args.nayta else muunna)(polku, args.tili)


if __name__ == "__main__":
    main()
