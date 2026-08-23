#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kirjanpito.py — kevyt, pankkiriippumaton henkilökohtainen rahaputki.

Ei riippuvuuksia (pelkkä Pythonin standardikirjasto). Idempotentti:
saman tiliotteen voi tuoda montaa kertaa, päällekkäisyydet ohitetaan.

Komennot:
  python3 kirjanpito.py aja                # lue inbox/, luokittele, raportoi
  python3 kirjanpito.py opi               # lue täytetty tarkistettavat.csv takaisin
  python3 kirjanpito.py raportti [--kk N] # rakenna raportit uudelleen
  python3 kirjanpito.py budjetti-ehdotus  # ehdota raamit toteuman mediaanista
  python3 kirjanpito.py kurkista TIEDOSTO # näytä miten tiedosto tulkittaisiin
  python3 kirjanpito.py pankkihaku        # ohjattu käyttöönotto: automaattinen pankkihaku
"""

import argparse
import calendar
import csv
import hashlib
import html
import io
import time
import json
import os
import queue
import re
import shutil
import socket
import statistics
import sys
import tempfile
import threading
import uuid
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

# Tiedostolukkoon: fcntl on POSIXissa, msvcrt Windowsissa. Kumpikaan ei ole
# pakollinen — ilman niitä ohjelma toimii, mutta ei huomaa rinnakkaista ajoa.
try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

# Ohjelmatiedostot asuvat koodi/-alihakemistossa ja data sen yläpuolella, jotta
# päivitys on yhden kansion korvaaminen. Vanha litteä asennus (kaikki samassa
# kansiossa) toimii edelleen sellaisenaan.
KOODI = Path(__file__).resolve().parent
KOODIJUURI = KOODI.parent if KOODI.name == "koodi" else KOODI


# Koneen omat asetukset asuvat koodin juuressa, koska se on ainoa paikka joka
# on varmasti konekohtainen: asetukset/ on itse tietokansion sisällä (eikä
# sieltä voisi lukea, missä tietokansio on), ja kotihakemisto on koneen kaikkien
# asennusten yhteinen. Tiedosto ei seuraa mukana repossa eikä päivityksessä.
# Nimi on pari jaetulle asetukset/-kansiolle: siellä ovat asetukset jotka
# seuraavat kirjanpitoa, täällä ne jotka jäävät koneelle. Pääte on .txt eikä
# .ini tai .conf, koska molemmat käyttöjärjestelmät avaavat sen
# kaksoisklikkauksella ilman kysymyksiä — .ini:llä ei ole macOS:ssä
# oletussovellusta lainkaan, ja .conf on kehittäjien tapa, ei kenenkään muun.
PAIKALLISET_TIEDOSTO = "koneen-asetukset.txt"
# Aiemmat nimet luetaan yhä ja kirjoitetaan uudella nimellä. Osoitin
# tietokansioon ei saa kadota kesken päivityksen: ilman sitä ohjelma aloittaisi
# tyhjän kirjanpidon väärässä paikassa.
PAIKALLISET_VANHAT = ("paikalliset.txt",)
DATAKANSIO_TIEDOSTO = "datakansio.txt"  # vanhin muoto: pelkkä polku, ei avaimia
# Avaimen vanha nimi. "datakansio" luetaan helposti data/-kansioksi, vaikka
# kyse on kansiosta jonka sisällä data/ on.
AVAINTEN_VANHAT_NIMET = {"datakansio": "tietokansio"}
# Leima kertoo, minkä version ohjelma tiedoston kirjoitti. Se on kommentissa
# eikä avaimena, koska se ei ole käyttäjän asetettavissa: jos versio ei täsmää,
# tiedosto kirjoitetaan uudelleen, ja käsin muutettu arvo katoaisi silloin
# joka tapauksessa. Näin jokainen avain = arvo -rivi on käyttäjän omaa.
PAIKALLISET_LEIMA = re.compile(r"#\s*---\s*Rahaputki\s+(\S+)\s*---")
PAIKALLISET_VARATUT = ("muoto", "versio")  # aiempi muotoavain: ei enää käytössä

PAIKALLISET_OHJE = """\
# Rahaputken paikalliset asetukset — koskevat vain tätä konetta.
#
# Tiedosto on konekohtainen: se ei seuraa päivityksessä (koodi/ korvataan
# kokonaan) eikä pilvisynkassa, joten jokaisella koneella on omansa.
#
# Muoto: avain = arvo, yksi per rivi. Rivi joka alkaa #-merkillä on kommentti.
#
# Tunnetut avaimet:
#   tietokansio  kansio, jonka SISÄLLÄ ovat asetukset/, data/ ja raportit/.
#                Oletus on tämän tiedoston oma kansio, eli kaikki yhdessä
#                paikassa — niin sen kuuluu useimmiten olla. Toisin sanoen:
#                    tietokansio = .
#                Muuta tämä vain jos haluat kirjanpidon eri paikkaan kuin
#                ohjelman, esimerkiksi jaettuun pilvikansioon. Kirjoita polku
#                kokonaisena tai ~/-alkuisena.
#
# Alla oleva versioleima on ohjelman omaa kirjanpitoa: sitä ei tarvitse
# muuttaa, eikä muutoksesta seuraa mitään. Kun ohjelma päivittyy, se
# kirjoittaa tämän tiedoston uudelleen leimoineen ja ohjeineen — omat
# kommenttisi eivät silloin säily, mutta asetuksesi säilyvät.
# --- Rahaputki {versio} ---
"""


def _lue_avainarvot(polku):
    """avain = arvo -rivit sanakirjaksi. Tuntemattomat avaimet säilyvät, jotta
    uudempi versio voi kirjoittaa niitä eikä vanhempi hukkaa niitä."""
    arvot = {}
    try:
        teksti = polku.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return arvot
    for rivi in teksti.splitlines():
        rivi = rivi.strip()
        if not rivi or rivi.startswith("#") or "=" not in rivi:
            continue
        avain, _, arvo = rivi.partition("=")
        arvot[avain.strip().lower()] = arvo.strip()
    return arvot


def _nimea_avaimet(arvot):
    """Vanhalla nimellä kirjoitettu avain luetaan uudella nimellä. Käyttäjän
    tiedostoon ei tarvitse koskea heti: se kirjoitetaan uusiksi seuraavan
    version leiman yhteydessä, ja siihen asti molemmat toimivat."""
    for vanha_nimi, uusi_nimi in AVAINTEN_VANHAT_NIMET.items():
        if vanha_nimi in arvot and uusi_nimi not in arvot:
            arvot[uusi_nimi] = arvot.pop(vanha_nimi)
        else:
            arvot.pop(vanha_nimi, None)
    return arvot


def _lue_paikalliset():
    """Koneen omat asetukset: arvot, luettu muotoversio ja tiedosto josta ne
    tulivat (None jos tiedostoa ei ole — se on täysin normaalia, koska yhden
    kansion asennus ei tarvitse yhtään paikallista asetusta).

    Versio on se, jolla tiedosto on kirjoitettu (tyhjä jos leimaa ei ole, eli
    tiedosto on vanhaa muotoa). Vanha datakansio.txt luetaan yhä: siinä on
    pelkkä polku ilman avainta. varmista_aloitus kirjoittaa sen uudelleen."""
    for nimi in (PAIKALLISET_TIEDOSTO,) + PAIKALLISET_VANHAT:
        polku = KOODIJUURI / nimi
        if not polku.is_file():
            continue
        arvot = _nimea_avaimet(_lue_avainarvot(polku))
        try:
            osuma = PAIKALLISET_LEIMA.search(polku.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            osuma = None
        return arvot, (osuma.group(1) if osuma else ""), polku
    vanhin = KOODIJUURI / DATAKANSIO_TIEDOSTO
    if vanhin.is_file():
        try:
            rivit = vanhin.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            rivit = []
        for rivi in rivit:
            rivi = rivi.strip()
            if rivi and not rivi.startswith("#"):
                return {"tietokansio": rivi}, "", vanhin
        return {}, "", vanhin
    return {}, "", None


def _siisti_polkuarvo(arvo):
    """Polku sellaisena kuin ihminen sen kirjoittaa, poluksi jonka voi avata.

    Leikepöydältä tulee lainausmerkkejä ("…" tai '…'), Finderistä vedetty polku
    kenoviivoittaa välilyönnit, ja komentotulkkiin tottunut kirjoittaa $HOME.
    Mikään näistä ei ole polku sellaisenaan, mutta jokainen on selvästi se mitä
    tarkoitettiin — ja väärin tulkittuna niistä syntyy suhteellinen polku, joka
    liimautuu ohjelman kansion perään aivan väärään paikkaan."""
    arvo = arvo.strip()
    for merkki in ('"', "'"):
        if len(arvo) >= 2 and arvo.startswith(merkki) and arvo.endswith(merkki):
            arvo = arvo[1:-1].strip()
            break
    if os.sep != "\\":  # Windowsissa kenoviiva on erotin, ei suojamerkki
        arvo = arvo.replace("\\ ", " ")
    return os.path.expandvars(arvo)  # $HOME, %USERPROFILE%


def _datajuuri():
    """Kansio, jossa kirjanpito asuu, ja mistä tieto tuli.

    Oletus on sama kuin ennen — kaikki yhdessä kansiossa — joten olemassa olevat
    asennukset toimivat muuttumatta. Asetus on niitä varten, jotka haluavat
    pitää ohjelman git-checkouttina koneen omalla levyllä ja kirjanpidon
    jaetussa pilvikansiossa: silloin koodi päivittyy git pullilla eikä
    pilvisynkka näe .git-hakemistoa lainkaan.

    Kansion voi kertoa kahdella tavalla. Ympäristömuuttuja RAHAPUTKI_DATA
    voittaa, ja se on kätevä kertakokeiluun. Pysyvä tapa on avain tietokansio
    paikallisissa asetuksissa: ne lukee myös kaksoisklikattu käynnistin, joka ei
    näe komentotulkin asetuksia lainkaan.

    Suhteellinen arvo tulkitaan koodin juuresta, ei työhakemistosta, jotta
    kaksoisklikkaus ja komentorivi eivät eroa toisistaan."""
    arvo = _siisti_polkuarvo(os.environ.get("RAHAPUTKI_DATA", ""))
    lahde = "ympäristömuuttuja RAHAPUTKI_DATA"
    if not arvo:
        arvo = _siisti_polkuarvo(PAIKALLISET.get("tietokansio", ""))
        lahde = str(PAIKALLISET_LAHDE)
        if PAIKALLISET_LAHDE is not None and PAIKALLISET_LAHDE.name != DATAKANSIO_TIEDOSTO:
            lahde += " (avain tietokansio)"
    if not arvo:
        return KOODIJUURI, None, ""
    polku = Path(arvo).expanduser()
    if not polku.is_absolute():
        polku = KOODIJUURI / polku
    return polku.resolve(), lahde, arvo


PAIKALLISET, PAIKALLISET_VERSIO, PAIKALLISET_LAHDE = _lue_paikalliset()
DATAJUURI, DATAJUURI_LAHDE, DATAJUURI_ARVO = _datajuuri()

# Inbox on läpikulkupaikka, ei kirjanpitoa: tiliotteet ladataan sillä koneella
# jolla ollaan, ja tuonnin jälkeen ne ovat pääkirjassa. Siksi se jää koneen
# omaan kansioon silloinkin, kun kirjanpito on jaetussa kansiossa — jaettuna se
# olisi vain synkkaa odottavaa läpikulkutavaraa. Yhden kansion asennuksessa
# juuret ovat sama polku, joten mikään ei muutu.
INBOX = KOODIJUURI / "inbox"
ARKISTO = INBOX / "arkisto"
DATA = DATAJUURI / "data"
RAPORTIT = DATAJUURI / "raportit"
ASETUKSET = DATAJUURI / "asetukset"
LEDGER = DATA / "tapahtumat.csv"
SAANNOT = ASETUKSET / "saannot.csv"
CONFIG = ASETUKSET / "config.json"
BUDJETTI = ASETUKSET / "budjetti.csv"
ENV = ASETUKSET / "pankkihaku.env"
TARKISTETTAVAT = RAPORTIT / "tarkistettavat.csv"

# Numerointi alkaa nollasta: tämä on kehitysversio, ei julkaisu. Ensimmäinen
# julkaisu on v1.0. Viimeinen numero kasvaa jokaisella committilla —
# .githooks/pre-commit hoitaa sen, jottei versio jää jälkeen koodista niin kuin
# kävi v125:n kohdalla: kolmisenkymmentä committia samalla numerolla, eikä
# toisella koneella voinut päätellä kumpi koodi siellä ajaa.
VERSIO = "v0.9"

LEDGER_KENTAT = ["id", "pvm", "tili", "summa", "saaja", "selite", "kategoria",
                 "tarkenne", "peruste", "lahde", "tila"]
# tila: tyhjä = pankin kirjaama, "varaus" = vasta varattu (ei vielä kirjattu)
VARAUS = "varaus"
VARAUKSET = DATA / "varaukset.json"
# Pankkiyhteyden tila on ohjelman havaintoa, ei käyttäjän asetus: milloin
# tililtä viimeksi saatiin tapahtumia ja mihin asti pankin antama valtuutus on
# voimassa. Siksi data/-kansiossa eikä config.jsonissa, jota käyttäjä muokkaa.
PANKKITILA = DATA / "pankkitila.json"
# Pankkiyhteyden loki: milloin rajapintaa kutsuttiin, mitä vastattiin ja kuinka
# kauan siinä meni. Tästä näkee jälkikäteen, miten pankin päivittäinen hakuraja
# oikeasti käyttäytyy — liukuuko ikkuna vai nollautuuko kiintiö — eikä sitä
# tarvitse arvata. Lokiin ei kirjoiteta salaisuuksia: ei tunnuksia, ei
# pyyntöjen runkoja, ei tilinumeroita. Tilin tunnus lyhennetään tiivisteeksi,
# joka erottaa tilit toisistaan mutta ei kelpaa miksikään muuksi.
PANKKILOKI = DATA / "pankkiloki.csv"
PANKKILOKI_KENTAT = ["aika", "toiminto", "kohde", "tulos", "koodi", "kesto_s",
                     "vastaus_tavua", "lisatieto"]
PANKKILOKI_RIVEJA = 2000
# Varaukset vanhenevat: jos hae ei ole käynyt hetkeen, niitä ei pidetä yllä.
VARAUS_VANHENEE_PV = 3
PVM_MUODOT = ["%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%d.%m.%y"]
ENKOODAUKSET = ["utf-8-sig", "utf-8", "iso-8859-1"]

MIN_PYTHON = (3, 9)

# Kansiot ja mallitiedostot, jotka ensikäynnistys luo puolestasi.
ALOITUSKANSIOT = (INBOX, DATA, RAPORTIT, ASETUKSET)
ALOITUSMALLIT = ((CONFIG, "config.esimerkki.json"),
                 (SAANNOT, "saannot.esimerkki.csv"))

# Aiemmat versiot pitivät nämä juuressa; siirretään kerran asetukset-kansioon.
VANHAT_ASETUKSET = (("config.json", CONFIG), ("saannot.csv", SAANNOT),
                    ("budjetti.csv", BUDJETTI), (".env", ENV))


# ------------------------------------------------------- ensikäynnistys

def _varmista_python():
    """Vanha Python antaisi myöhemmin hämärän virheen — kerrotaan se heti selvästi."""
    if sys.version_info < MIN_PYTHON:
        vaadittu = ".".join(str(o) for o in MIN_PYTHON)
        nyt = ".".join(str(o) for o in sys.version_info[:3])
        print(f"Rahaputki vaatii Pythonin version {vaadittu} tai uudemman "
              f"(käytössä {nyt}).\n"
              "Lataa uudempi osoitteesta https://www.python.org/downloads/ "
              "ja käynnistä uudelleen.")
        sys.exit(1)


def _siisti_konsoli():
    """Windowsin konsoli on oletuksena cp1252/cp850, jolloin ä, ✓ ja — kaatuisivat
    UnicodeEncodeError-virheeseen heti kun tuloste ohjataan putkeen tai tiedostoon."""
    for virta in (sys.stdout, sys.stderr):
        try:
            virta.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _paikallinen_env():
    """Konekohtainen pankkihaku.env koodin juuressa.

    Merkitystä vain silloin, kun data on erotettu omaan kansioonsa
    (RAHAPUTKI_DATA). Tunnukset osoittavat yksityisavaimeen, joka on
    tarkoituksella vain yhdellä koneella, joten ne eivät kuulu jaettuun
    pilvikansioon vaan sen koneen omaan hakemistoon."""
    if DATAJUURI == KOODIJUURI:
        return None
    return KOODIJUURI / "pankkihaku.env"


def _env_polku():
    """Pankkihaun tunnukset. Erotetussa asennuksessa ensin koneen oma tiedosto,
    muuten asetukset/pankkihaku.env (näkyvä nimi); vanhat piilotetut paikat
    luetaan yhä, jos sellainen on jäljellä."""
    paikallinen = _paikallinen_env()
    if paikallinen is None:
        paikallinen = ENV
    for polku in (paikallinen, ENV, ASETUKSET / ".env", DATAJUURI / ".env"):
        if polku.is_file():
            return polku
    return _paikallinen_env() or ENV


def _varmista_datajuuri():
    """Osoitettu tietokansio on oltava olemassa ennen kuin sinne kirjoitetaan.

    Jos se puuttuu — pilvikansio ei ole vielä latautunut, levy ei ole kiinni,
    polussa on kirjoitusvirhe — kansiorakenne luotaisiin muuten vaiti uuteen
    paikkaan ja kirjanpito alkaisi tyhjästä. Kaksi rinnakkaista pääkirjaa on
    pahempi vika kuin selvä virheilmoitus."""
    if DATAJUURI_LAHDE is None or DATAJUURI.is_dir():
        return
    print(f"Tietokansiota ei löydy: {DATAJUURI}\n"
          f"  asetettu täällä: {DATAJUURI_LAHDE}\n"
          f"  siinä lukee:     {DATAJUURI_ARVO}")
    # Suhteellinen polku on ylivoimaisesti yleisin virhe: unohtunut ~/ liimaa
    # kirjanpidon ohjelman kansion sisään, ja tulokseen ilmestyy kansion nimi
    # kahdesti. Sitä ei arvaa ilman että sen sanoo ääneen.
    if not Path(DATAJUURI_ARVO).expanduser().is_absolute():
        print(f"  Polku on suhteellinen, joten se luettiin ohjelman kansiosta:\n"
              f"  {KOODIJUURI}\n"
              "  Jos tarkoitit kotihakemistoasi, kirjoita eteen ~/ — tai koko\n"
              "  polku alusta asti.")
    print("Tarkista polku, tai luo kansio ensin jos aloitat uuden kirjanpidon.\n"
          "Rahaputki ei aloita tyhjää kirjanpitoa väärään paikkaan.")
    sys.exit(1)


def _kirjoita_paikalliset(arvot):
    """Kirjoittaa koneen omat asetukset uusimmassa muodossa.

    Tiedosto rakennetaan otsikko-ohjeesta ja avaimista, joten käyttäjän omat
    kommentit eivät säily. Se on tietoinen vaihtokauppa: näin ohje tiedoston
    sisällä pysyy ajan tasalla silloinkin kun muoto muuttuu, eikä kukaan lue
    vanhentunutta neuvoa omasta tiedostostaan. Uudelleen kirjoitetaan vain
    muodon päivittyessä, ei joka ajolla."""
    rivit = [PAIKALLISET_OHJE.format(versio=VERSIO)]
    rivit += [f"{avain} = {arvot[avain]}" for avain in sorted(arvot)
              if avain not in PAIKALLISET_VARATUT]
    sisalto = "\n".join(rivit) + "\n"
    turvakirjoita(KOODIJUURI / PAIKALLISET_TIEDOSTO, sisalto)
    return sisalto


def _vain_leima_vaihtui(vanha, uusi):
    """Erosivatko tiedostot vain versioleiman riviltä?"""
    def ilman_leimaa(teksti):
        return [r for r in (teksti or "").splitlines()
                if not PAIKALLISET_LEIMA.search(r)]
    return ilman_leimaa(vanha) == ilman_leimaa(uusi)


def _paivita_paikalliset():
    """Paikallisten asetusten muoto päivitetään samalla tavalla kuin muidenkin
    asetusten ja pääkirjan: vanha luetaan, uusi kirjoitetaan, eikä käyttäjän
    tarvitse tietää tapahtuneesta muuta kuin yhden rivin.

    Leima kertoo, millä versiolla tiedosto on kirjoitettu. Erillistä
    muotonumeroa ei ole: ohjelman oma versio on jo olemassa, ja kaksi numeroa
    tarkoittaisi kahta asiaa jotka voivat ajautua eri linjoille. Uudelleen
    kirjoitetaan siis päivityksen jälkeen kerran, vaikkei muoto olisi
    muuttunut — se maksaa yhden tiedoston ja pitää tiedoston sisällä olevan
    ohjeen aina saman version kanssa yhtä mieltä.

    Vanha datakansio.txt oli pelkkä polku ilman avainta, eikä siihen olisi
    mahtunut mitään muuta; se luetaan yhä ja kirjoitetaan uuteen tiedostoon."""
    if PAIKALLISET_LAHDE is None:
        return
    if PAIKALLISET_VERSIO == VERSIO and PAIKALLISET_LAHDE.name == PAIKALLISET_TIEDOSTO:
        return
    # Versio kasvaa jokaisella committilla, joten pelkkä leiman vaihtuminen on
    # tavallisin syy tulla tänne. Se ei ole uutinen käyttäjälle: rivi
    # "asetukset päivitetty" joka ainoan päivityksen jälkeen opettaisi vain
    # ohittamaan sen silloinkin kun se kertoo jotain.
    vanha_sisalto = ""
    try:
        vanha_sisalto = PAIKALLISET_LAHDE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    try:
        uusi_sisalto = _kirjoita_paikalliset(PAIKALLISET)
    except OSError as e:
        print(f"⚠ Paikallisia asetuksia ei saatu kirjoitettua ({e}).\n"
              f"  {PAIKALLISET_LAHDE.name} kelpaa yhä, joten mikään ei katkennut.")
        return
    vanha = PAIKALLISET_LAHDE.name
    if vanha == PAIKALLISET_TIEDOSTO:
        if _vain_leima_vaihtui(vanha_sisalto, uusi_sisalto):
            return
        print(f"Paikalliset asetukset päivitetty versiolle {VERSIO}.")
        return
    try:
        PAIKALLISET_LAHDE.unlink()
    except OSError:
        pass
    print(f"Paikalliset asetukset päivitetty versiolle {VERSIO}: "
          f"{vanha} → {PAIKALLISET_TIEDOSTO}")


def _siirra_vanhat_asetukset():
    """Siirrä juuressa olleet asetustiedostot asetukset/-kansioon. Ajetaan joka
    kerta, mutta tekee jotain vain kerran: olemassa olevan päälle ei kirjoiteta."""
    siirretyt = []
    for vanha_nimi, uusi in VANHAT_ASETUKSET:
        vanha = DATAJUURI / vanha_nimi
        if vanha.is_file() and not uusi.exists():
            uusi.parent.mkdir(parents=True, exist_ok=True)
            os.replace(vanha, uusi)
            siirretyt.append(f"  {vanha_nimi} -> asetukset/{uusi.name}")
    if siirretyt:
        print("Asetukset siirretty omaan kansioonsa:")
        print("\n".join(siirretyt))


def varmista_aloitus():
    """Luo puuttuvat kansiot ja mallitiedostot. Uusi käyttäjä ei saa törmätä
    traceback-tulosteeseen ennen kuin on edes päässyt alkuun. Olemassa olevaa
    ei kosketa koskaan, joten tämän voi ajaa turvallisesti joka kerta."""
    _varmista_datajuuri()
    _paivita_paikalliset()
    _siirra_vanhat_asetukset()
    ensikerta = not CONFIG.exists()
    for kansio in ALOITUSKANSIOT:
        kansio.mkdir(parents=True, exist_ok=True)
    for kohde, malli_nimi in ALOITUSMALLIT:
        malli = KOODI / malli_nimi
        if not kohde.exists() and malli.exists():
            turvakirjoita_kopio(malli, kohde)
            print(f"Luotu {kohde.parent.name}/{kohde.name} tiedostosta {malli_nimi} "
                  "— muokkaa omaksesi kun haluat.")
    if not CONFIG.exists():
        print(f"config.json puuttuu kansiosta {DATAJUURI}, eikä mallipohjaa "
              f"(config.esimerkki.json) löydy kansiosta {KOODI}.\n"
              "Lataa työkalu uudelleen kokonaisena pakettina.")
        sys.exit(1)
    if ensikerta:
        erillinen = KOODI != KOODIJUURI
        koodirivi = ("  koodi/      ohjelma; päivitys korvaa vain tämän kansion\n"
                     if erillinen else "")
        ohje = "koodi/OHJE.md" if erillinen else "OHJE.md"
        seuraava = ("Seuraava askel: vie tiliotteet verkkopankista CSV-muodossa "
                    f"kansioon inbox/\nja käynnistä uudelleen. Tarkemmat ohjeet: {ohje}")
        if DATAJUURI == KOODIJUURI:
            print(f"""
Tervetuloa. Kansio {DATAJUURI.name} on nyt valmis:

  inbox/      <- VIE PANKKIESI CSV-TIEDOSTOT TÄNNE
  asetukset/  kategoriat, säännöt ja budjetti — muokkaa kun haluat
  data/       kirjanpitosi kertyy tänne (tapahtumat.csv on koko totuus)
  raportit/   raportti.html syntyy tänne
{koodirivi}
{seuraava}
""")
        else:
            # Erotettu asennus: kirjanpito on jaetussa kansiossa, ohjelma ja
            # inbox koneen omassa. Yksi yhteinen puu valehtelisi kummastakin,
            # ja juuri tässä kohtaa käyttäjä päättää minne tiliotteet vie.
            print(f"""
Tervetuloa. Kirjanpitosi asuu kansiossa
{DATAJUURI}

  asetukset/  kategoriat, säännöt ja budjetti — muokkaa kun haluat
  data/       kirjanpitosi kertyy tänne (tapahtumat.csv on koko totuus)
  raportit/   raportti.html syntyy tänne

Ohjelma ja inbox jäävät tälle koneelle kansioon
{KOODIJUURI}

  inbox/      <- VIE PANKKIESI CSV-TIEDOSTOT TÄNNE
{koodirivi}
{seuraava}
""")



# ---------------------------------------------------------------- apurit

def lue_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def lue_teksti(polku: Path):
    """Lue tiedosto kokeillen yleisimmät enkoodaukset. UTF-8 ensin; jos ei kelpaa,
    valitaan 8-bittisistä (cp1252 / Mac Roman / latin-1) se, joka tuottaa eniten
    suomea ja vähiten roskamerkkejä — Excel Macilla tallentaa usein Mac Romania."""
    import threading
    vahti = threading.Timer(4.0, lambda: print(
        f"⏳ {polku.name}: luku kestää — pilvisynkka (esim. Google Drive) lataa "
        f"tiedostoa? Harkitse kansion merkitsemistä 'Available offline'."))
    vahti.daemon = True
    vahti.start()
    try:
        data = polku.read_bytes()
    finally:
        vahti.cancel()
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    paras, paras_enc, paras_p = None, "?", -10**9
    for enc in ("windows-1252", "mac_roman", "iso-8859-1"):
        try:
            t = data.decode(enc)
        except UnicodeDecodeError:
            continue
        p = sum(t.count(c) for c in "äöåÄÖÅéü€") - sum(t.count(c) for c in "ŠŽšž‰†°¤ƒ√∫")
        if p > paras_p:
            paras, paras_enc, paras_p = t, enc, p
    return paras, paras_enc


@contextmanager
def _hidas_vahti(viesti, sekuntia=4.0):
    """Kertoo käyttäjälle, jos pilvikansio ei vastaa heti.

    Ensimmäinen kosketus Driveen tai iCloudiin voi kestää sekunteja: File
    Provider hakee tiedostot palvelimelta, ja jos toinen kone on juuri
    kirjoittanut pääkirjan ja raportit, luku jonottaa niiden latauksen perässä.
    Ohjelma näyttää silloin jumittuneelta, vaikka se odottaa levyä — ja
    tyhjälle ruudulle painetaan Ctrl-C.

    Viesti tulostuu vain jos odotus venyy. Ajastin on daemon-säie, joten se ei
    pidä prosessia hengissä eikä sillä ole väliä, ehtiikö se koskaan laueta."""
    ajastin = threading.Timer(sekuntia, lambda: print(viesti))
    ajastin.daemon = True
    ajastin.start()
    try:
        yield
    finally:
        ajastin.cancel()


TURVAKIRJOITUS_YRITYKSET = 4


def turvakirjoita(polku, teksti):
    """Kirjoita tiedosto niin, ettei siitä voi jäädä puolikasta.

    Sisältö menee ensin viereiseen tilapäistiedostoon, joka vaihdetaan
    paikalleen yhdellä os.replacella. Keskeytys — kaatuminen, virtakatko,
    pilvisynkka kesken kirjoituksen — jättää siis aina joko vanhan tai uuden
    version, ei koskaan katkaistua.

    Käytetään tiedostoihin, jotka ovat käyttäjän totuus: pääkirja, säännöt,
    config, pankkihaun tunnukset, yhteistalouden tila ja pankista noudetut
    CSV:t. Raportit syntyvät joka ajossa uudelleen, joten niitä ei tarvitse
    suojata.

    Pilvikansiossa (Drive, iCloud, OneDrive) juuri luotu tilapäistiedosto voi
    kadota käsistä ennen kuin se ehditään vaihtaa paikalleen: tiedostojärjestelmä
    on palvelimen välityspalvelin eikä levy, ja se materialisoi tiedostot omaan
    tahtiinsa. Silloin os.replace kaatuu virheeseen "No such file or directory"
    tiedostoon, joka kirjoitettiin rivi sitten. Siksi koko kirjoitus yritetään
    uudelleen muutaman kerran, joka kerta uudella tilapäisnimellä. Vanha versio
    on koko ajan tallessa: replace joko onnistuu tai ei tapahdu lainkaan."""
    polku = Path(polku)
    polku.parent.mkdir(parents=True, exist_ok=True)
    viimeisin = None
    for yritys in range(TURVAKIRJOITUS_YRITYKSET):
        tilapainen = polku.with_name(f"{polku.name}.uusi{os.getpid()}-{yritys}")
        try:
            with open(tilapainen, "w", encoding="utf-8", newline="") as f:
                f.write(teksti)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tilapainen, polku)
            return
        except BaseException as e:
            # Myös Ctrl-C kesken kirjoituksen: tilapäistiedosto siivotaan aina,
            # ja keskeytys päästetään sen jälkeen menemään. Kohdetiedosto on
            # koskematon, koska replacea ei ehditty tehdä.
            try:
                tilapainen.unlink(missing_ok=True)
            except OSError:
                pass
            if not isinstance(e, OSError):
                raise
            viimeisin = e
            if yritys + 1 < TURVAKIRJOITUS_YRITYKSET:
                time.sleep(0.4 * (yritys + 1))
    raise RuntimeError(
        f"Tiedostoa {polku.name} ei saatu kirjoitettua ({viimeisin}).\n"
        f"  Kansio: {polku.parent}\n"
        "  Pilvisynkka voi viedä juuri luodun tiedoston hetkeksi alta. Vanha\n"
        "  versio on tallessa eikä mitään rikkoutunut — kokeile uudelleen.")


def _tilin_summa(ledger, tili, varaukset_mukaan=False):
    """Tilin rivien summa pääkirjassa. Varaukset mukaan vain jos vertailukohta
    (pankin saldo) sisältää nekin."""
    summa = 0.0
    for r in ledger:
        if r.get("tili") != tili:
            continue
        if r.get("tila") == VARAUS and not varaukset_mukaan:
            continue
        try:
            summa += float(r.get("summa") or 0)
        except (TypeError, ValueError):
            continue
    return round(summa, 2)


def _vertailukelpoinen(tyyppi):
    """Kirjattu saldo (ITBD/CLBD) vastaa kirjattuja rivejä. ITAV sisältää myös
    odottavat korttivaraukset — silloin vertailuun otetaan varauksetkin."""
    return str(tyyppi or "").upper().startswith(("ITBD", "CLBD"))


def tasmayta(ledger, cfg, account_id):
    """Vertaa pankin saldoa kirjanpitoon ankkurin kautta.

    Ankkuri on hyväksytty lähtöpiste: saldo, jonka käyttäjä on todennut
    oikeaksi, ja pääkirjan summa sillä hetkellä. Vertailu on niiden erotusten
    vertailu, ei absoluuttinen summa:

        odotettu = ankkurin saldo + (pääkirjan summa nyt − pääkirjan summa ankkurilla)

    Näin päivärajat eivät haittaa: jälkikäteen ilmestynyt vanhalla
    kirjauspäivällä varustettu tapahtuma siirtää odotettua saldoa oikein,
    vaikka se ilmestyisi keskelle historiaa. Absoluuttinen vertailu ei olisi
    mahdollinenkaan, koska pääkirja alkaa tilikohtaisesta alkupäivästä eikä
    tilin avaamisesta."""
    tila = lue_pankkitila().get(str(account_id), {})
    saldo = tila.get("saldo")
    if not isinstance(saldo, (int, float)):
        return {"ok": False, "virhe": "tilin saldoa ei ole haettu"}
    nimi = tila.get("tili") or next(
        (t.get("tili") for t in ((cfg.get("pankkihaku") or {}).get("tilit") or [])
         if str(t.get("account_id")) == str(account_id)), "")
    tyyppi = str(tila.get("saldo_tyyppi", ""))
    varaukset_mukaan = not _vertailukelpoinen(tyyppi)
    summa_nyt = _tilin_summa(ledger, nimi, varaukset_mukaan)
    tulos = {"ok": True, "tili": nimi, "pankissa": round(float(saldo), 2),
             "saldo_tyyppi": tyyppi, "saldo_haettu": tila.get("saldo_haettu", ""),
             "varaukset_mukana": varaukset_mukaan,
             "kirjanpito_summa": summa_nyt}
    if not isinstance(tila.get("ankkuri_saldo"), (int, float)):
        tulos.update(ankkuri=None, odotettu=None, ero=None)
        return tulos
    odotettu = round(float(tila["ankkuri_saldo"])
                     + (summa_nyt - float(tila.get("ankkuri_summa") or 0)), 2)
    tulos.update(ankkuri={"saldo": tila["ankkuri_saldo"], "pvm": tila.get("ankkuri_pvm", ""),
                          "summa": tila.get("ankkuri_summa"),
                          "ero": tila.get("ankkuri_ero", 0)},
                 odotettu=odotettu,
                 ero=round(tulos["pankissa"] - odotettu, 2))
    return tulos


def ankkuroi(ledger, cfg, account_id):
    """Hyväksy pankin saldo lähtöpisteeksi. Mahdollinen ero jää muistiin — se
    on tieto siitä, että jotain jäi selvittämättä, eikä sitä pidä hukata."""
    tulos = tasmayta(ledger, cfg, account_id)
    if not tulos.get("ok"):
        return tulos
    paivita_pankkitila(account_id,
                       ankkuri_saldo=tulos["pankissa"],
                       ankkuri_summa=tulos["kirjanpito_summa"],
                       ankkuri_tyyppi=tulos["saldo_tyyppi"],
                       ankkuri_pvm=date.today().isoformat(),
                       ankkuri_ero=tulos.get("ero") or 0,
                       tasmaytetty=date.today().isoformat())
    tulos["ankkuroitu"] = True
    return tulos


def _lokitunnus(teksti):
    """Tilin tunnisteesta lyhyt tiiviste: erottaa tilit toisistaan lokissa,
    mutta ei ole tilin tunnus eikä palaudu siksi."""
    return hashlib.sha1(str(teksti).encode("utf-8")).hexdigest()[:8]


def _lokipolku(polku):
    """Rajapintapolku lokiin: tilin uid korvataan tiivisteellä ja kyselyosa
    pudotetaan (siellä on päivämäärärajat ja sivutusavaimet, ei asiaa lokiin)."""
    polku = str(polku).partition("?")[0]
    osat = [_lokitunnus(o) if len(o) >= 20 else o for o in polku.split("/")]
    return "/".join(osat)


# Lokiin päätyvästä virhetekstistä siivotaan kaikki, mikä voisi olla tunnus.
# Järjestys on tärkeä: ensin tunnetut muodot (JWT, avain: arvo -parit), sitten
# kaikki riittävän pitkät merkkijonot varmuuden vuoksi. Väärä positiivinen on
# harmiton — lokiin ei tarvita tunnuksia, ei edes vahingossa.
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}(?:\.[A-Za-z0-9_-]+){1,2}")
# "Authorization: Bearer <tunnus>" tarvitsee oman sääntönsä: muuten yleinen
# avain–arvo-sääntö nappaa arvokseen sanan "Bearer" ja jättää tunnuksen näkyviin.
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}")
_AVAINARVO = re.compile(
    r"(?i)\b(bearer|token|access_token|id_token|code|secret|password|authorization|"
    r"api[_-]?key)\b[\"'\s:=]*(?!bearer\b)([A-Za-z0-9._~+/=-]{6,})")
_PITKA = re.compile(r"[A-Za-z0-9_-]{24,}")


def _siivoa_lokiteksti(teksti):
    """Virheen runko lokiin: ei tunnuksia, ei rivinvaihtoja, ei pitkiä pötköjä."""
    teksti = _JWT.sub("<tunnus>", str(teksti or ""))
    teksti = _BEARER.sub("Bearer <poistettu>", teksti)
    teksti = _AVAINARVO.sub(lambda m: f"{m.group(1)} <poistettu>", teksti)
    teksti = _PITKA.sub("<pitkä>", teksti)
    return siisti(teksti)[:200]


def pankkiloki(toiminto, kohde, tulos, koodi="", kesto_s=None, tavuja=None,
               lisatieto=""):
    """Yksi rivi pankkiyhteyden lokiin. Epäonnistuminen ei saa haitata hakua."""
    rivi = {"aika": datetime.now().isoformat(timespec="seconds"),
            "toiminto": toiminto, "kohde": kohde, "tulos": tulos, "koodi": koodi,
            "kesto_s": f"{kesto_s:.2f}" if kesto_s is not None else "",
            "vastaus_tavua": tavuja if tavuja is not None else "",
            "lisatieto": _siivoa_lokiteksti(lisatieto)}
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        uusi = not PANKKILOKI.exists()
        with open(PANKKILOKI, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PANKKILOKI_KENTAT, delimiter=";")
            if uusi:
                w.writeheader()
            w.writerow(rivi)
        _karsi_pankkiloki()
    except OSError:
        pass


def _karsi_pankkiloki():
    """Loki ei saa kasvaa rajatta. Karsitaan harvakseltaan, ei joka rivillä."""
    try:
        if PANKKILOKI.stat().st_size < 300 * 1024:
            return
        rivit = PANKKILOKI.read_text(encoding="utf-8").splitlines(keepends=True)
        if len(rivit) <= PANKKILOKI_RIVEJA + 1:
            return
        turvakirjoita(PANKKILOKI, rivit[0] + "".join(rivit[-PANKKILOKI_RIVEJA:]))
    except (OSError, ValueError, RuntimeError):
        pass


def lue_pankkitila():
    try:
        with open(PANKKITILA, encoding="utf-8") as f:
            tila = json.load(f)
        return tila if isinstance(tila, dict) else {}
    except (OSError, ValueError):
        return {}


def paivita_pankkitila(account_id, **kentat):
    """Merkitse tilin pankkiyhteydestä tiedetty. Epäonnistuminen ei kaada
    hakua: tämä on tietoa käyttäjälle, ei kirjanpidon totuutta."""
    if not account_id:
        return
    tila = lue_pankkitila()
    tila.setdefault(str(account_id), {}).update(
        {k: v for k, v in kentat.items() if v is not None})
    try:
        turvakirjoita_json(PANKKITILA, tila)
    except (OSError, RuntimeError):
        pass


def _paivia_jaljella(pvm):
    """Päiviä annettuun päivämäärään; None jos päivämäärää ei ole tai se ei jäsenny."""
    if not pvm:
        return None
    try:
        return (date.fromisoformat(str(pvm)[:10]) - date.today()).days
    except ValueError:
        return None


def turvakirjoita_kopio(lahde, kohde):
    """Kopioi tiedosto niin, ettei kohteeksi voi jäädä puolikasta.

    shutil.copy2 kirjoittaa suoraan kohteeseen: keskeytys kesken kopion jättää
    katkaistun tiedoston, jolla on oikea nimi. Varmuuskopiossa se on pahin
    mahdollinen lopputulos — tiedosto näyttää varmuuskopiolta mutta ei ole.
    Kopio menee siis viereen ja vaihdetaan paikalleen yhdellä replacella."""
    kohde = Path(kohde)
    tilapainen = kohde.with_name(f"{kohde.name}.uusi{os.getpid()}")
    try:
        shutil.copy2(lahde, tilapainen)
        os.replace(tilapainen, kohde)
    except BaseException:
        try:
            tilapainen.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def turvakirjoita_json(polku, data):
    turvakirjoita(polku, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _kopion_aika(polku, etuliite):
    try:
        return datetime.strptime(polku.stem[len(etuliite):], "%Y-%m-%d_%H%M%S")
    except (ValueError, IndexError):
        return None


def _karsi_varmuuskopiot(kansio, etuliite, paate, tuoreita=10,
                         paivia=7, viikkoja=8, kuukausia=12):
    """Säilytä tuoreimmat ja lisäksi kunkin päivän, viikon ja kuukauden viimeisin.

    Pelkkä "N tuoreinta" on petollinen turva: yhden iltapäivän aherrus tuottaa
    helposti kymmenen kopiota, jolloin ne kaikki ovat samalta tunnilta eikä
    eilistä ole enää missään. Juuri silloin varmuuskopiota tarvitaan — virhe
    huomataan tyypillisesti vasta seuraavana päivänä."""
    try:
        tiedostot = sorted(kansio.glob(f"{etuliite}*{paate}"))
    except OSError:
        return
    if len(tiedostot) <= tuoreita:
        return
    pidettavat = set(tiedostot[-tuoreita:])
    for avain, maara in ((lambda d: d.strftime("%Y-%m-%d"), paivia),
                         (lambda d: d.strftime("%G-W%V"), viikkoja),
                         (lambda d: d.strftime("%Y-%m"), kuukausia)):
        korit = {}
        for tiedosto in tiedostot:
            aika = _kopion_aika(tiedosto, etuliite)
            if aika is not None:
                korit[avain(aika)] = tiedosto   # nouseva järjestys -> uusin jää koriin
        for kori in sorted(korit)[-maara:]:
            pidettavat.add(korit[kori])
    for tiedosto in tiedostot:
        if tiedosto not in pidettavat:
            try:
                tiedosto.unlink()
            except OSError:
                pass


def varmuuskopioi(polku, etuliite=None):
    """Ottaa talteen minkä tahansa tiedoston samalla sukupolvilogiikalla.

    Pääkirjalla on oma, tiukempi kopiointinsa (_varmuuskopioi_ledger). Tämä on
    niitä tiedostoja varten, jotka sisältävät käsityötä eivätkä synny
    uudelleen pankkidatasta: säännöt ja yhteistalouden tila."""
    polku = Path(polku)
    if not polku.exists():
        return
    etuliite = etuliite or (polku.stem + "_")
    kansio = DATA / "varmuuskopiot"
    kohde = kansio / f"{etuliite}{time.strftime('%Y-%m-%d_%H%M%S')}{polku.suffix}"
    try:
        kansio.mkdir(parents=True, exist_ok=True)
        if not kohde.exists():
            turvakirjoita_kopio(polku, kohde)
    except OSError:
        return
    _karsi_varmuuskopiot(kansio, etuliite, polku.suffix)


def siisti(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def normalisoi(s):
    return siisti(s).lower()


def parsi_summa(raaka, desimaali=","):
    """'−1 975,80 €' -> -1975.80  (kestää €-merkit, välit, unicode-miinuksen)."""
    s = (raaka or "").replace("\u2212", "-").replace("\u00a0", " ").replace("€", "")
    s = s.replace("EUR", "").strip().replace(" ", "")
    if not s:
        raise ValueError("tyhjä summa")
    if desimaali == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    return round(float(s), 2)


def parsi_pvm(raaka, ensisijainen=None):
    s = siisti(raaka)
    muodot = ([ensisijainen] if ensisijainen else []) + PVM_MUODOT
    for m in muodot:
        try:
            return datetime.strptime(s, m).date()
        except (ValueError, TypeError):
            continue
    raise ValueError(f"päivämäärää ei tunnistettu: {raaka!r}")


def fmt_eur(x):
    """1234.5 -> '1 234,50' (suomalainen muotoilu)."""
    s = f"{x:,.2f}".replace(",", " ").replace(".", ",")
    return s


# ---------------------------------------------------------------- säännöt

def kirjoita_saannot(teksti):
    """Sääntötiedostoon kertyy käsityötä, jota ei saa takaisin pankkidatasta:
    varmuuskopio ennen jokaista kirjoitusta."""
    varmuuskopioi(SAANNOT)
    turvakirjoita(SAANNOT, teksti)


def _saanto_fyysiset(teksti):
    """Sääntötiedoston loogiset rivit: [(fyysinen_rivi_indeksi, osat)].
    Yksi fyysinen rivi = aina yksi tietue, kommentit ja otsikkorivit ohitetaan.
    Sama laskuri kaikille (näyttö, siirto, moottori), jotta #-numerointi täsmää."""
    ulos = []
    for i, rv in enumerate(teksti.splitlines()):
        if not rv.strip() or rv.lstrip().startswith("#"):
            continue
        osat = next(csv.reader([rv], delimiter=";"), [])
        if not osat or not siisti(osat[0]) or normalisoi(osat[0]) == "malli":
            continue
        ulos.append((i, osat))
    return ulos


def lue_saannot():
    """saannot.csv: malli;kategoria. Järjestys ratkaisee (ensimmäinen osuma voittaa).
    Malli on osamerkkijono (kirjainkoosta riippumaton) tai 're:'-alkuinen regex."""
    saannot = []
    if not SAANNOT.exists():
        return saannot
    teksti, _ = lue_teksti(SAANNOT)
    for _, rivi in _saanto_fyysiset(teksti):
        malli = normalisoi(rivi[0])
        kategoria = siisti(rivi[1]) if len(rivi) > 1 else ""
        ehto = siisti(rivi[2]) if len(rivi) > 2 else ""
        if malli.startswith("re:"):
            saannot.append(("re", re.compile(malli[3:], re.IGNORECASE), kategoria, ehto, malli))
        else:
            saannot.append(("osa", malli, kategoria, ehto, malli))
    return saannot


def _ehto_ok(ehto, summa):
    """Summaehto: 'max=50' -> |summa| <= 50, 'min=50' -> |summa| >= 50."""
    if not ehto:
        return True
    try:
        op, raja = ehto.split("=")
        raja = float(raja.replace(",", "."))
    except ValueError:
        return True
    a = abs(float(summa))
    return a <= raja + 1e-9 if op.strip() == "max" else (a >= raja - 1e-9 if op.strip() == "min" else True)


def lue_saannot_raaka():
    """Säännöt näyttömuodossa: [{malli, kategoria, ehto}], kommentit ohitetaan."""
    ulos = []
    if not SAANNOT.exists():
        return ulos
    teksti, _ = lue_teksti(SAANNOT)
    for _, rivi in _saanto_fyysiset(teksti):
        ulos.append({"malli": siisti(rivi[0]), "kategoria": siisti(rivi[1]) if len(rivi) > 1 else "",
                     "ehto": siisti(rivi[2]) if len(rivi) > 2 else ""})
    return ulos


def poista_saanto(malli, kategoria="", ehto=""):
    """Poista sääntö(t), joiden malli (+ kategoria/ehto jos annettu) täsmää. Palauttaa määrän."""
    if not SAANNOT.exists():
        return 0
    teksti, _ = lue_teksti(SAANNOT)
    m_n, k_n, e_n = normalisoi(malli), siisti(kategoria).lower(), siisti(ehto).lower()
    jaa, poistettu = [], 0
    for rivi in teksti.splitlines():
        osat = next(csv.reader([rivi], delimiter=";"), [])
        if (osat and not rivi.startswith("#") and normalisoi(osat[0]) == m_n
                and (not k_n or (len(osat) > 1 and siisti(osat[1]).lower() == k_n))
                and (not e_n or (len(osat) > 2 and siisti(osat[2]).lower() == e_n))):
            poistettu += 1
            continue
        jaa.append(rivi)
    if poistettu:
        kirjoita_saannot("\n".join(jaa) + "\n")
    return poistettu


def _riisu(malli):
    """Mallin ydin vertailua varten: re:-etuliite ja \\b-merkit pois."""
    m = normalisoi(malli)
    if m.startswith("re:"):
        m = m[3:]
    return m.replace("\\b", "").replace("\\", "")


def _sijoituskohta(mallit, uusi_malli):
    """Indeksi, jonka EDELLE tarkempi sääntö kuuluu (None = loppuun).
    Tarkempi = uusi malli sisältää olemassa olevan mallin ytimen."""
    uusi_r = _riisu(uusi_malli)
    for i, m in enumerate(mallit):
        vanha_r = _riisu(m)
        if vanha_r and vanha_r != uusi_r and vanha_r in uusi_r:
            return i
    return None


def lisaa_saanto(malli, kategoria, ehto=""):
    """Lisää sääntö: yleissääntöä tarkempi malli sijoitetaan automaattisesti
    sen edelle (poikkeus voittaa), muuten loppuun."""
    rivi_uusi = ";".join([malli, kategoria] + ([ehto] if ehto else []))
    if not SAANNOT.exists():
        kirjoita_saannot("malli;kategoria\n" + rivi_uusi + "\n")
        return True
    teksti, _ = lue_teksti(SAANNOT)
    rivit = teksti.splitlines()
    # Täsmälleen sama sääntö jo olemassa? Ei kahdennnusta.
    m_uusi, k_uusi, e_uusi = normalisoi(malli), siisti(kategoria).lower(), siisti(ehto).lower()
    for _, osat in _saanto_fyysiset(teksti):
        if (normalisoi(osat[0]) == m_uusi
                and siisti(osat[1] if len(osat) > 1 else "").lower() == k_uusi
                and siisti(osat[2] if len(osat) > 2 else "").lower() == e_uusi):
            return False
    saanto_rivit = []  # (rivinumero, malli)
    for i, rv in enumerate(rivit):
        if not rv.strip() or rv.startswith("#"):
            continue
        osat = next(csv.reader([rv], delimiter=";"), [])
        if osat and siisti(osat[0]) and normalisoi(osat[0]) != "malli":
            saanto_rivit.append((i, osat[0]))
    kohta = _sijoituskohta([m for _, m in saanto_rivit], malli)
    if kohta is None:
        rivit.append(rivi_uusi)
    else:
        rivit.insert(saanto_rivit[kohta][0], rivi_uusi)
    kirjoita_saannot("\n".join(rivit) + "\n")
    return True


def siirra_saanto(malli, kategoria="", ehto="", suunta=-1, kohde_sija=None):
    """Siirrä sääntöä askel ylös/alas (suunta) tai suoraan sijaintiin (kohde_sija, 1-pohjainen)."""
    if not SAANNOT.exists():
        return False
    teksti, _ = lue_teksti(SAANNOT)
    rivit = teksti.splitlines()
    m_n, k_n = normalisoi(malli), siisti(kategoria).lower()
    indeksit = []
    kohde = None
    for i, osat in _saanto_fyysiset(teksti):
        indeksit.append(i)
        if (kohde is None and normalisoi(osat[0]) == m_n
                and (not k_n or (len(osat) > 1 and siisti(osat[1]).lower() == k_n))):
            kohde = len(indeksit) - 1
    if kohde is None:
        return False
    if kohde_sija is not None:
        t = max(0, min(len(indeksit) - 1, int(kohde_sija) - 1))
        if t == kohde:
            return True
        a = indeksit[kohde]
        sisalto = rivit[a]
        del rivit[a]
        rivit.insert(indeksit[t], sisalto)
        kirjoita_saannot("\n".join(rivit) + "\n")
        return True
    naapuri = kohde + (1 if suunta > 0 else -1)
    if naapuri < 0 or naapuri >= len(indeksit):
        return False
    a, b = indeksit[kohde], indeksit[naapuri]
    rivit[a], rivit[b] = rivit[b], rivit[a]
    kirjoita_saannot("\n".join(rivit) + "\n")
    return True


def luokittele(rivi, saannot, omat_ibanit):
    teksti = normalisoi(f"{rivi['saaja']} {rivi['selite']}")
    summa = rivi.get("summa", 0.0)
    for tyyppi, malli, kategoria, ehto, raaka in saannot:
        osuu = malli.search(teksti) if tyyppi == "re" else (malli in teksti)
        if osuu and _ehto_ok(ehto, summa):
            return kategoria, f"sääntö: {raaka}"
    # eksplisiittinen sääntö voittaa; vasta sitten oma-IBAN-heuristiikka
    kohde = (normalisoi(rivi.get("iban", "")) + " " + teksti).replace(" ", "")
    for oma in omat_ibanit:
        oma_n = normalisoi(oma).replace(" ", "")
        if oma_n and oma_n in kohde:
            return "Siirto", "oma tili"
    return "TARKISTA", ""


# ---------------------------------------------------------------- lähteiden tulkinta

def hae_sarake(otsikot, ehdokkaat):
    """Palauta ensimmäinen otsikoista löytyvä ehdokassarake (tai None)."""
    norm = {normalisoi(o): o for o in otsikot}
    if isinstance(ehdokkaat, str):
        ehdokkaat = [ehdokkaat]
    for e in ehdokkaat:
        if normalisoi(e) in norm:
            return norm[normalisoi(e)]
    return None


def tunnista_lahde(otsikot, cfg):
    """Etsi config.json:sta lähde, jonka tunnistesarakkeet löytyvät otsikkoriviltä."""
    for nimi, l in cfg["lahteet"].items():
        if all(hae_sarake(otsikot, t) for t in l["tunniste_sarakkeet"]):
            return nimi, l
    return None, None


def _rev_eur(s):
    """'-€0.26', '€1,234.56' tai '£18.00 (€20.85)' -> euromäärä floattina."""
    s = (s or "").strip()
    if not s:
        return None
    m = re.search(r"\(([^)]*)\)", s)
    if m:
        s = m.group(1)  # valuuttariveillä euro-vastine suluissa
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parsi_revolut_v2(teksti):
    """Revolutin 'consolidated statement v2': monilohkoinen raportti, josta
    poimitaan vain Personal Account -tilien tapahtumataulukot. Taskusiirrot
    (To pocket / To investment account) luokittuvat säännöillä Sijoituksiksi."""
    rivit, varoitukset = [], []
    otsikko, taulussa = "", False
    PVM_ENG = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$")
    for osat in csv.reader(teksti.splitlines()):
        if not osat:
            continue
        eka = (osat[0] or "").strip()
        if taulussa:
            if PVM_ENG.match(eka) and len(osat) >= 4:
                try:
                    pvm = datetime.strptime(eka, "%b %d, %Y").date()
                except ValueError:
                    taulussa = False
                else:
                    summa = _rev_eur(osat[3])
                    if summa is not None:
                        rivit.append({
                            "pvm": pvm, "summa": summa,
                            "saaja": siisti(osat[1]),
                            "selite": siisti(f"{osat[2]} | {otsikko}"),
                            "iban": "", "tili": "Revolut",
                        })
                    continue
            else:
                taulussa = False
        if eka == "Date":
            taulussa = otsikko.startswith("Personal Account")
            continue
        if (eka and eka not in ("Transaction statement", "---------")
                and not eka.startswith("Total") and not PVM_ENG.match(eka)):
            otsikko = eka
    if not rivit:
        varoitukset.append("Revolut consolidated: yhtään tapahtumaa ei löytynyt Personal Account -taulukoista")
    return "revolut_consolidated", rivit, varoitukset


def parsi_tiedosto(polku: Path, cfg):
    """Palauttaa (lahteen_nimi, rivit, varoitukset). Rivi = dict(pvm, summa, saaja, selite, tili, iban)."""
    teksti, enc = lue_teksti(polku)
    varoitukset = []
    ekarivi = teksti.splitlines()[0] if teksti.strip() else ""
    if "Current Accounts Summaries" in ekarivi or '"Transaction statement"' in teksti:
        return parsi_revolut_v2(teksti)
    erotin = ";" if ekarivi.count(";") >= ekarivi.count(",") else ","
    lukija = csv.DictReader(teksti.splitlines(), delimiter=erotin)
    otsikot = lukija.fieldnames or []
    nimi, l = tunnista_lahde(otsikot, cfg)
    if not nimi:
        raise ValueError(
            f"Tuntematon tiedostomuoto: {polku.name}\n"
            f"  Otsikot: {otsikot}\n"
            f"  Lisää sopiva lähde config.json:iin (apuna: python3 kirjanpito.py kurkista {polku.name})"
        )
    s = l["sarakkeet"]
    pvm_sar = hae_sarake(otsikot, s["pvm"])
    summa_sar = hae_sarake(otsikot, s["summa"])
    saaja_sar = hae_sarake(otsikot, s.get("saaja", []))
    selite_sar = [hae_sarake(otsikot, e) for e in s.get("selite", [])]
    selite_sar = [x for x in selite_sar if x]
    iban_sar = hae_sarake(otsikot, s.get("iban", []))
    kulu_sar = hae_sarake(otsikot, s.get("kulu", []))
    tili_sar = hae_sarake(otsikot, s.get("tili", []))
    suodata = l.get("suodata", {})

    rivit = []
    for n, raaka in enumerate(lukija, start=2):
        try:
            ohita = False
            for sar, sallittu in suodata.items():
                oikea = hae_sarake(otsikot, sar)
                if oikea and siisti(raaka.get(oikea, "")) not in sallittu:
                    ohita = True
            if ohita:
                continue
            if not siisti(raaka.get(pvm_sar, "")):
                continue
            summa = parsi_summa(raaka.get(summa_sar, ""), l.get("desimaali", ","))
            if kulu_sar and siisti(raaka.get(kulu_sar, "")):
                summa = round(summa - abs(parsi_summa(raaka.get(kulu_sar), l.get("desimaali", ","))), 2)
            rivit.append({
                "pvm": parsi_pvm(raaka.get(pvm_sar, ""), l.get("pvm_muoto")),
                "summa": summa,
                "saaja": siisti(raaka.get(saaja_sar, "")) if saaja_sar else "",
                "selite": siisti(" ".join(raaka.get(x, "") or "" for x in selite_sar)),
                "iban": siisti(raaka.get(iban_sar, "")) if iban_sar else "",
                "tili": (siisti(raaka.get(tili_sar, "")) if tili_sar else "") or l["tili"],
            })
        except Exception as e:
            varoitukset.append(f"{polku.name} rivi {n}: {e}")
    return nimi, rivit, varoitukset


# ---------------------------------------------------------------- lukitus

# Lukittavia ovat komennot, jotka kirjoittavat pääkirjaa tai sääntöjä. Pelkkä
# katselu (raportti, kurkista, budjetti-ehdotus) ei lukitse mitään: pääkirjan
# lukeminen toiselta koneelta on aina sallittua.
KIRJOITTAVAT = {"aja", "hae", "opi", "luokittele", "siivoa-kopiot", "selaa",
                "tarkista-kortit", "pankkihaku"}
LUKKO_VANHENEE_MIN = 30
LUKKO_TUNNISTE = None
LUKKO_KOMENTO = None


LUKKO_KOODI = 4  # paluuarvo, josta käynnistin tunnistaa lukon muista virheistä


def _lukko_seis(viesti):
    """Lukon takia perääntyminen ei ole virhe: mitään ei rikkoutunut, ja oikea
    vastaus on odottaa hetki. Käynnistin erottaa sen paluuarvosta, jottei se
    jatka ketjun seuraavaan komentoon — se törmäisi samaan lukkoon ja toistaisi
    saman varoituksen, kuin ohjelma ei olisi kuullut ensimmäistä."""
    print(viesti, file=sys.stderr)
    raise SystemExit(LUKKO_KOODI)


def _paikallinen_lukko():
    """Saman koneen rinnakkaiset ajot: käyttöjärjestelmän oma tiedostolukko
    väliaikaiskansiossa. Tämä on aukoton, eikä se voi jäädä roikkumaan —
    käyttöjärjestelmä vapauttaa lukon, kun prosessi päättyy, tapahtui se miten
    tahansa."""
    tunnus = hashlib.sha1(str(DATA.resolve()).encode("utf-8")).hexdigest()[:10]
    polku = Path(tempfile.gettempdir()) / f"rahaputki-{tunnus}.lock"
    try:
        kahva = open(polku, "w", encoding="utf-8")
    except OSError:
        return None
    try:
        if fcntl is not None:
            fcntl.flock(kahva.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt is not None:
            msvcrt.locking(kahva.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        kahva.close()
        _lukko_seis("⚠ Rahaputki on jo ajossa tällä koneella. Odota että "
                    "edellinen ajo valmistuu.")
    return kahva


def _vapauta_paikallinen(kahva):
    if kahva is None:
        return
    try:
        if fcntl is not None:
            fcntl.flock(kahva.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:
            kahva.seek(0)
            msvcrt.locking(kahva.fileno(), msvcrt.LK_UNLCK, 1)
    except (OSError, ValueError):
        pass
    kahva.close()


def _konenimi():
    return re.sub(r"[^A-Za-z0-9_-]+", "-", socket.gethostname() or "") or "kone"


def _lukkotiedosto():
    """Konekohtainen nimi: jokainen kone kirjoittaa vain omaan tiedostoonsa.

    Yhteinen nimi altistaisi kirjoitus-kirjoitus-törmäykselle, jonka pilvisynkka
    ratkaisee joko rinnakkaiskopiolla tai — pahemmin — sillä että viimeinen
    voittaa. Silloin toisen koneen lukko katoaisi äänettömästi. Kilpailijat
    tunnistetaan siksi kansiolistauksesta, ei yhteisestä tiedostosta."""
    return DATA / f".lukko.{_konenimi()}.json"


def _kaikki_lukot():
    ulos = []
    try:
        polut = sorted(DATA.glob(".lukko.*.json"))
    except OSError:
        return ulos
    for polku in polut:
        try:
            with open(polku, encoding="utf-8") as f:
                ulos.append(json.load(f))
        except (OSError, ValueError):
            continue
    return ulos


def _lukon_ika_min(tiedot):
    try:
        alku = datetime.fromisoformat(str(tiedot.get("aloitettu", "")))
    except ValueError:
        return 10 ** 6
    return (datetime.now() - alku).total_seconds() / 60.0


def _kesto(minuutteja):
    """Ikä ihmisen mitassa. "455 min" ei kerro mitään ilman jakolaskua, ja juuri
    lukkoa katsoessa kysymys on nimenomaan siitä, onko tämä hetki sitten vai
    eilinen jäänne."""
    m = int(round(minuutteja))
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} h {m} min"
    d, h = divmod(h, 24)
    return f"{d} vrk {h} h {m} min"


def _lukon_polku(tiedot):
    """Lukkotiedoston nimi tietokansiosta katsottuna: sen voi poistaa käsin, jos
    kone on lopullisesti poissa, eikä nimeä muuten arvaa."""
    kone = str(tiedot.get("kone", "")) or "kone"
    return (DATA / f".lukko.{kone}.json").relative_to(DATAJUURI)


def _jarjestysavain(tiedot):
    """Tasatilanteen ratkaisu: aiemmin aloittanut voittaa, tasapelissä pienempi
    tunniste. Molemmat koneet päätyvät samaan tulokseen ilman neuvottelua."""
    return (str(tiedot.get("aloitettu", "")), str(tiedot.get("tunniste", "")))


def _lue_lukko():
    try:
        with open(_lukkotiedosto(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _kirjoita_lukko(komento, tunniste):
    try:
        turvakirjoita_json(_lukkotiedosto(), {
            "kone": _konenimi(), "pid": os.getpid(), "tunniste": tunniste,
            "komento": komento,
            "aloitettu": datetime.now().isoformat(timespec="seconds")})
    except OSError:
        pass


def _kilpaileva_lukko(tunniste):
    """Toisen koneen tuore lukko, joka voittaa oman — tai None."""
    oma, muut = None, []
    for tiedot in _kaikki_lukot():
        if tiedot.get("tunniste") == tunniste:
            oma = tiedot
        elif _lukon_ika_min(tiedot) < LUKKO_VANHENEE_MIN:
            muut.append(tiedot)
    if oma is None or not muut:
        return None
    paras = min(muut, key=_jarjestysavain)
    return paras if _jarjestysavain(paras) < _jarjestysavain(oma) else None


def _varmista_omistus(tunniste, varmistus_s):
    """Kirjoita, odota, lue: jos toinen kone ehti ensin, perääntymme.

    Tämä ei tee lukosta atomista — pilvisynkan yli se ei voi olla. Se kutistaa
    kilpailuikkunan synkan kierrosajan mittaiseksi ja tekee ratkaisusta
    deterministisen: kumpikin kone laskee saman voittajan, joten kumpikaan ei
    jää odottamaan turhaan."""
    if varmistus_s <= 0:
        return
    time.sleep(varmistus_s)
    voittaja = _kilpaileva_lukko(tunniste)
    if voittaja:
        _lukko_seis(f"⚠ Toinen kone ({voittaja.get('kone', '?')}) ehti ensin "
                    f"({voittaja.get('komento', '?')}). Yritä hetken päästä uudelleen.")


def _lukko_vietiin():
    """Oma lukko on kadonnut kesken ajon — mitä tehdään?

    Syitä on kaksi, eikä niitä voi täältä käsin erottaa toisistaan: toinen kone
    ohitti lukon luvalla, tai pilvisynkka vei tiedoston hetkeksi alta.
    Ensimmäisessä tapauksessa jatkaminen tarkoittaa kahta konetta saman
    pääkirjan kimpussa. Jälkimmäisessä keskeytys on turha, mutta harmiton:
    putki on idempotentti, ja saman ajon voi toistaa sellaisenaan. Siksi
    oletus on keskeyttää, ja jatkaminen vaatii sanotun luvan.

    Selaimesta tulevaa kirjoitusta ei voi kysyä konsolista: käyttäjä katsoo
    selainta, ja pyyntö jäisi roikkumaan odottamaan vastausta, jota kukaan ei
    ole antamassa. Siellä kirjoitus estetään ja syy kerrotaan selaimeen."""
    syy = ("Lukkosi on kadonnut kesken ajon: joko toinen kone otti sen luvalla,\n"
           "  tai pilvisynkka vei tiedoston alta. Jos toinen kone kirjoittaa nyt\n"
           "  samaa pääkirjaa, jatkaminen sekoittaa molempien työn keskenään.")
    if threading.current_thread() is not threading.main_thread():
        print(f"\n⚠ {syy}\n  Kirjoitus estetty.")
        raise RuntimeError("Lukkosi vietiin toisella koneella — kirjoitusta ei "
                           "tehty. Sulje raportti ja aja uudelleen, kun tiedät "
                           "kumpi kone on liikkeellä.")
    print(f"\n⚠ {syy}")
    if _valikko("Mitä tehdään?",
                [("keskeyta", "Keskeytä — pääkirjaan ei kirjoiteta mitään"),
                 ("jatka", "Ota lukko takaisin ja jatka")], oletus=1) != "jatka":
        _lukko_seis("Keskeytetty. Pääkirjaan ei kirjoitettu mitään.")
    _kirjoita_lukko(LUKKO_KOMENTO or "", LUKKO_TUNNISTE)
    print("→ Lukko otettu takaisin, jatketaan.")


def lukon_virkistys():
    """Pitkä ajo (selaa voi olla auki tunteja) pitää lukkonsa tuoreena joka
    kirjoituksella. Samalla tarkistetaan, ettei lukko ole vaihtanut omistajaa
    kesken ajon: jos on, keskeytetään ennen kirjoitusta eikä vasta sen
    jälkeen, kun toisen koneen työ on jo mennyt yli."""
    if LUKKO_TUNNISTE is None:
        return
    voittaja = _kilpaileva_lukko(LUKKO_TUNNISTE)
    if voittaja:
        _lukko_seis(f"⚠ Toinen kone ({voittaja.get('kone', '?')}) otti lukon kesken "
                    f"ajon. Kirjoitus keskeytetty, jotta muutokset eivät mene ristiin.")
    tiedot = _lue_lukko()
    if tiedot is None or tiedot.get("tunniste") != LUKKO_TUNNISTE:
        _lukko_vietiin()
        return
    _kirjoita_lukko(tiedot.get("komento", ""), LUKKO_TUNNISTE)


@contextmanager
def paakirjalukko(komento, pakota=False):
    """Estää päällekkäiset ajot kahdella tasolla.

    1) Sama kone: käyttöjärjestelmän tiedostolukko. Aukoton.
    2) Eri koneet: neuvoa-antava .lukko-tiedosto tietokansiossa. Pilvisynkan
       viiveen takia se ei voi olla atominen, mutta se muuttaa hiljaisen
       datamenetyksen äänekkääksi varoitukseksi.

    Toinen taso on käytössä vain, jos config.jsonissa on "lukitus": "jaettu".
    Yhden koneen asennus on tavallisin, eikä sen kansioon kannata kirjoittaa
    lukkotiedostoja eikä sen ajoon lisätä odotusta."""
    global LUKKO_TUNNISTE, LUKKO_KOMENTO
    if komento not in KIRJOITTAVAT:
        yield
        return
    DATA.mkdir(parents=True, exist_ok=True)
    kahva = _paikallinen_lukko()
    try:
        cfg = lue_config() or {}
    except (OSError, ValueError):
        cfg = {}
    if siisti(str(cfg.get("lukitus", "kone"))).lower() != "jaettu":
        try:
            yield
        finally:
            _vapauta_paikallinen(kahva)
        return
    if not pakota:
        for tiedot in _kaikki_lukot():
            if tiedot.get("kone") == _konenimi():
                continue
            ika = _lukon_ika_min(tiedot)
            if ika < LUKKO_VANHENEE_MIN:
                _vapauta_paikallinen(kahva)
                _lukko_seis(
                    f"⚠ Pääkirja on lukittu: {tiedot.get('kone', '?')} "
                    f"({tiedot.get('komento', '?')}), {_kesto(ika)} sitten.\n"
                    f"  Lukko: {_lukon_polku(tiedot)}\n"
                    f"  Odota että ajo valmistuu ja synkka ehtii perille. Jos lukko on\n"
                    f"  jäänyt jumiin: {_komentorivi()} --pakota {komento}")
            # Vanha lukko on melkein aina jäänne keskeytyneestä ajosta. "Melkein
            # aina" ei silti riitä perusteeksi ohittaa sitä käyttäjän puolesta:
            # jos toinen kone on yhä työn touhussa, molemmat kirjoittavat
            # pääkirjaa yhtä aikaa, ja sen huomaa vasta kun toinen on hävinnyt.
            # Kysytään siis, ja oletus on ettei ohiteta. Putkitetussa ajossa
            # kysymys jää vastaamatta ja oletus pitää — se on oikea suunta.
            print(f"⚠ Toisen koneen lukko on vanha: {tiedot.get('kone', '?')} "
                  f"({tiedot.get('komento', '?')}), {_kesto(ika)} sitten.\n"
                  f"  Lukko: {_lukon_polku(tiedot)}\n"
                  "  Yleensä ajo on keskeytynyt ja lukko jäänyt roikkumaan.\n"
                  "  Jos se sen sijaan on yhä käynnissä, ohittaminen tarkoittaa\n"
                  "  kahta konetta saman pääkirjan kimpussa yhtä aikaa.")
            if not _kylla("Ohitetaanko vanha lukko?", oletus=False):
                _vapauta_paikallinen(kahva)
                _lukko_seis("Ei ohitettu. Yritä uudelleen kun toinen ajo on "
                            f"valmis — tai {_komentorivi()} --pakota {komento}")
            # Keskeytyneen ajon jättämä lukko ei vanhene pois itsestään, joten
            # ilman poistoa sama kysymys toistuisi joka ajolla. Poistetaan vasta
            # luvan saatuaan — se on koko luvan sisältö.
            try:
                (DATA / f".lukko.{tiedot.get('kone', '')}.json").unlink()
            except OSError:
                pass
            print(f"→ Vanha lukko ({tiedot.get('kone', '?')}) ohitettu luvallasi.")
    tunniste = uuid.uuid4().hex
    _kirjoita_lukko(komento, tunniste)
    try:
        varmistus = float(cfg.get("lukko_varmistus_s", 3))
    except (TypeError, ValueError):
        varmistus = 3.0
    try:
        _varmista_omistus(tunniste, varmistus)
    except SystemExit:
        _lukkotiedosto().unlink(missing_ok=True)
        _vapauta_paikallinen(kahva)
        raise
    LUKKO_TUNNISTE, LUKKO_KOMENTO = tunniste, komento
    try:
        yield
    finally:
        # Lukkotiedoston nimessä on koneen nimi, ja saman koneen rinnakkaiset
        # ajot estää jo paikallinen tiedostolukko — poistettava tiedosto on siis
        # aina oma. Sitä ei tarvitse lukea, ja juuri lukeminen oli se hidas
        # operaatio, joka sai pilvikansiossa ohjelman näyttämään jumittuneelta
        # sulkemisen jälkeen: käyttäjä painoi Ctrl-C:tä toisen kerran, ja lukko
        # jäi roikkumaan kesken poiston. Keskeytys ei saa jättää lukkoa: se
        # nielaistaan täällä ja poisto yritetään uudelleen.
        for _ in range(3):
            try:
                _lukkotiedosto().unlink(missing_ok=True)
                break
            except OSError:
                break
            except KeyboardInterrupt:
                continue
        LUKKO_TUNNISTE, LUKKO_KOMENTO = None, None
        _vapauta_paikallinen(kahva)


# ---------------------------------------------------------------- pääkirja

def lue_ledger():
    if not LEDGER.exists():
        return []
    with open(LEDGER, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _varmuuskopioi_ledger():
    """Ennen jokaista pääkirjan kirjoitusta: nykyinen versio talteen
    data/varmuuskopiot/-kansioon (säilytys: ks. _karsi_varmuuskopiot).

    Tämä on pääkirjan oma kopiointi eikä yleinen varmuuskopioi, koska
    epäonnistuminen ei saa jäädä huomaamatta: jos kopiota ei saada, koko
    tallennus keskeytetään."""
    if not LEDGER.exists():
        return
    kansio = DATA / "varmuuskopiot"
    kohde = kansio / f"tapahtumat_{time.strftime('%Y-%m-%d_%H%M%S')}.csv"
    viimeisin = None
    for yritys in range(3):
        try:
            kansio.mkdir(parents=True, exist_ok=True)
            if not kohde.exists():
                turvakirjoita_kopio(LEDGER, kohde)
            break
        except OSError as e:
            # Pilvisynkka (esim. Google Drive) voi hetkellisesti viedä kansion alta.
            viimeisin = e
            time.sleep(0.6)
    else:
        raise RuntimeError(
            f"Varmuuskopiota ei saatu kirjoitettua ({viimeisin}) — tallennus keskeytetty "
            f"turvallisuussyistä. Tarkista että kansio {kansio} on olemassa "
            f"(pilvisynkka voi piilottaa sen hetkellisesti; kokeile uudelleen).")
    _karsi_varmuuskopiot(kansio, "tapahtumat_", ".csv")


# Selaa-tila ei kirjoita raporttia levylle joka sivunlatauksella (se olisi lähes
# megatavu pilvikansiaan per lataus). Tiedosto on silti se, jonka puhelin avaa
# Drivestä, joten sen pitää seurata muutoksia — vain hitaammin. Kirjoitus
# ajastetaan viimeisen muutoksen jälkeen: peräkkäiset luokittelut kuittaantuvat
# yhdellä kirjoituksella, eikä viimeinenkään jää tekemättä.
SELAA_KAYNNISSA = False
RAPORTTI_VIIVE_S = 20.0
_raportti_ajastin = None
_raportti_lukko = threading.Lock()


def _kirjoita_raportti_taustalla():
    try:
        rakenna_raportit(lue_ledger(), lue_config(), kk=13)
    except (OSError, ValueError, RuntimeError, KeyError):
        pass  # raportti syntyy joka tapauksessa seuraavassa ajossa


def _raportti_vanheni():
    """Merkitse levyllä oleva raportti vanhentuneeksi ja ajasta uusi kirjoitus."""
    global _raportti_ajastin
    if not SELAA_KAYNNISSA:
        return
    with _raportti_lukko:
        if _raportti_ajastin is not None:
            _raportti_ajastin.cancel()
        _raportti_ajastin = threading.Timer(RAPORTTI_VIIVE_S,
                                            _kirjoita_raportti_taustalla)
        _raportti_ajastin.daemon = True
        _raportti_ajastin.start()


def kirjoita_ledger(rivit):
    DATA.mkdir(exist_ok=True)
    lukon_virkistys()
    _varmuuskopioi_ledger()
    for r in rivit:
        r["tarkenne"] = siisti(r.get("tarkenne", "")).lower()
        r.setdefault("peruste", "")
        r.setdefault("tila", "")
    rivit.sort(key=lambda r: (r["pvm"], r["tili"], r["id"]))
    puskuri = io.StringIO()
    w = csv.DictWriter(puskuri, fieldnames=LEDGER_KENTAT, delimiter=";")
    w.writeheader()
    w.writerows(rivit)
    turvakirjoita(LEDGER, puskuri.getvalue())
    _raportti_vanheni()


def avain(tili, pvm, summa, saaja):
    return f"{tili}|{pvm}|{summa:.2f}|{normalisoi(saaja)[:40]}"


def tee_id(av, jarjestys):
    return hashlib.sha1(f"{av}#{jarjestys}".encode()).hexdigest()[:10]


# ---------------------------------------------------------------- komennot

GC_API = "https://bankaccountdata.gocardless.com/api/v2"


def _env_salaisuudet():
    """GC_SECRET_ID/GC_SECRET_KEY ympäristöstä tai .env-tiedostosta (avain=arvo-rivit)."""
    arvot = {"GC_SECRET_ID": os.environ.get("GC_SECRET_ID", ""),
             "GC_SECRET_KEY": os.environ.get("GC_SECRET_KEY", "")}
    env = _env_polku()
    if env.exists():
        for rv in env.read_text(encoding="utf-8").splitlines():
            if "=" in rv and not rv.lstrip().startswith("#"):
                k, _, v = rv.partition("=")
                k, v = k.strip(), v.strip()
                if k in arvot and not arvot[k]:
                    arvot[k] = v
    return arvot


def gc_nouda(account_id, cfg):
    """Nouda tilin tapahtumat GoCardless Bank Account Data -rajapinnasta.
    HUOM: kirjoitettu dokumentaation mukaan, EI testattu livenä (uusien
    tunnusten luonti oli palvelussa tauolla 7/2026). Mock-adapteri kattaa
    kaiken tämän jälkeisen putken."""
    import urllib.request
    sal = _env_salaisuudet()
    if not sal["GC_SECRET_ID"] or not sal["GC_SECRET_KEY"]:
        raise ValueError("GC_SECRET_ID / GC_SECRET_KEY puuttuvat (.env tai ympäristömuuttujat)")

    def _kutsu(polku, runko=None, token=None):
        data = json.dumps(runko).encode() if runko is not None else None
        req = urllib.request.Request(GC_API + polku, data=data,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {token}"} if token else {})})
        with urllib.request.urlopen(req, timeout=30) as v:
            return json.loads(v.read().decode())

    tok = _kutsu("/token/new/", {"secret_id": sal["GC_SECRET_ID"],
                                 "secret_key": sal["GC_SECRET_KEY"]})["access"]
    return _kutsu(f"/accounts/{account_id}/transactions/", token=tok)


EB_API = "https://api.enablebanking.com"


def _eb_asetukset():
    """EB_APP_ID ja EB_KEY_PATH (.pem) ympäristöstä tai .env-tiedostosta.

    EB_SOVELLUS_OK on sen sovelluksen tunnus, jonka käyttäjä on nimenomaan
    hyväksynyt tälle asennukselle. Sitä vasten vaiheen 2 varoitukset
    vaimennetaan: tietoinen valinta kysytään kerran, ei joka ajolla."""
    arvot = {"EB_APP_ID": os.environ.get("EB_APP_ID", ""),
             "EB_KEY_PATH": os.environ.get("EB_KEY_PATH", ""),
             "EB_SOVELLUS_OK": os.environ.get("EB_SOVELLUS_OK", "")}
    env = _env_polku()
    if env.exists():
        for rv in env.read_text(encoding="utf-8").splitlines():
            if "=" in rv and not rv.lstrip().startswith("#"):
                k, _, v = rv.partition("=")
                if k.strip() in arvot and not arvot[k.strip()]:
                    arvot[k.strip()] = v.strip()
    return arvot


def eb_jwt(app_id, avain_pem):
    """Enable Bankingin vaatima RS256-JWT: kid = sovelluksen id."""
    try:
        import jwt
    except ImportError:
        raise ValueError("asenna ensin: pip install pyjwt cryptography")
    nyt = int(time.time())
    return jwt.encode({"iss": "enablebanking.com", "aud": "api.enablebanking.com",
                       "iat": nyt, "exp": nyt + 3600},
                      avain_pem, algorithm="RS256", headers={"kid": app_id})


def eb_token():
    a = _eb_asetukset()
    env = _env_polku()
    if not a["EB_APP_ID"] or not a["EB_KEY_PATH"]:
        raise ValueError(f"EB_APP_ID ja/tai EB_KEY_PATH puuttuvat tiedostosta {env} — "
                         f"ohjattu käyttöönotto: {_komentorivi()} pankkihaku")
    polku = _avainpolku(a["EB_KEY_PATH"])
    if not polku.exists():
        raise ValueError(f"yksityisavainta ei löydy polusta {polku} — "
                         f"tarkista EB_KEY_PATH tiedostossa {env} "
                         "(avain on koneella jolla valtuutus tehtiin), tai aja "
                         f"'{_komentorivi()} pankkihaku --uusi-sovellus'")
    return eb_jwt(a["EB_APP_ID"], polku.read_text(encoding="utf-8"))


class EBVirhe(ValueError):
    def __init__(self, koodi, runko):
        super().__init__(f"EB vastasi {koodi}: {runko}")
        self.koodi, self.runko = koodi, runko


def _eb_kutsu(polku, token, runko=None):
    import urllib.request
    import urllib.error
    data = json.dumps(runko).encode() if runko is not None else None
    req = urllib.request.Request(EB_API + polku, data=data,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    kohde = _lokipolku(polku)
    toiminto = ("POST " if data is not None else "GET ") + kohde
    alku = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as v:
            vastaus = v.read()
            pankkiloki(toiminto, kohde, "ok", v.status, time.time() - alku, len(vastaus))
            return json.loads(vastaus.decode())
    except urllib.error.HTTPError as e:
        try:
            teksti = e.read().decode()[:300]
        except OSError:
            teksti = ""
        # Rajan ylityksessä pankki kertoo usein milloin seuraava haku sallitaan.
        # Juuri se vastaa kysymykseen, jota muuten joutuisi arvailemaan.
        odota = ""
        try:
            for otsake in ("Retry-After", "X-RateLimit-Reset", "RateLimit-Reset"):
                if e.headers and e.headers.get(otsake):
                    odota = f"{otsake}={e.headers.get(otsake)} "
        except (AttributeError, TypeError):
            pass
        pankkiloki(toiminto, kohde, "virhe", e.code, time.time() - alku,
                   len(teksti), odota + teksti)
        raise EBVirhe(e.code, teksti) from e
    except OSError as e:
        pankkiloki(toiminto, kohde, "katkos", "", time.time() - alku, None, str(e))
        raise


def eb_riveiksi(data, kerro=None, varaukset=None):
    """Enable Bankingin tapahtumamuoto -> {pvm, summa, saaja, selite}.

    Nollasummaiset (rauenneet varaukset) ohitetaan. Kirjautumattomat (PDNG)
    eivät kelpaa pääkirjaan sellaisenaan, mutta ne kerätään `varaukset`-listaan,
    josta aja pitää niitä yllä väliaikaisina riveinä. `kerro` saa yhteenvedon
    ohitetuista, jotta mitään ei tapahdu hiljaa."""
    ulos = []
    ohitetut = Counter()
    for tx in data.get("transactions", []) or []:
        try:
            pvm = date.fromisoformat(str(tx.get("booking_date") or tx.get("value_date")
                                         or tx.get("transaction_date")))
            summa = round(float(tx.get("transaction_amount", {}).get("amount")), 2)
        except (TypeError, ValueError):
            ohitetut["tulkitsematon"] += 1
            continue
        tila = siisti(str(tx.get("status") or "")).upper()
        kirjattu = not tila or tila in ("BOOK", "BOOKED")
        if not kirjattu and varaukset is None:
            # Varaus, ei vielä kirjaus: summa ja päivä voivat vielä muuttua, ja
            # kirjautuessaan se tulisi eri avaimella toiseen kertaan.
            ohitetut["kirjautumaton"] += 1
            continue
        if summa == 0:
            # Rauennut korttivaraus. Ei rahaa, mutta jäisi ikuisesti
            # odottamaan luokittelua.
            ohitetut["nollasumma"] += 1
            continue
        if str(tx.get("credit_debit_indicator", "")).upper() == "DBIT" and summa > 0:
            summa = -summa
        osap = (tx.get("creditor") if summa < 0 else tx.get("debtor")) or {}
        saaja = siisti(osap.get("name") or (tx.get("creditor") or {}).get("name")
                       or (tx.get("debtor") or {}).get("name") or "")
        rem = tx.get("remittance_information") or []
        if isinstance(rem, str):
            rem = [rem]
        valuutta = siisti(str(tx.get("transaction_amount", {}).get("currency") or ""))
        if valuutta and valuutta.upper() != "EUR":
            ohitetut["muu_valuutta"] += 1
        btc = tx.get("bank_transaction_code")
        if isinstance(btc, dict):
            btc = "/".join(str(x) for x in (btc.get("code"), btc.get("sub_code"),
                                            btc.get("description")) if x)
        viite = tx.get("entry_reference") or tx.get("reference_number") or ""
        tilinro = ((tx.get("creditor_account") or {}).get("iban")
                   or (tx.get("debtor_account") or {}).get("iban") or "")
        osat = [siisti(str(x)) for x in rem if siisti(str(x))]
        if not saaja:
            # Varasaaja viestiosasta. Revolut kertoo vastapuolen muodossa
            # "To <saaja>" / "From <maksaja>" omana viestirivinään — se on
            # oleellisin tieto, kun creditor/debtor puuttuu kokonaan.
            vastapuoli = next((o.split(" ", 1)[1] for o in osat
                               if o[:3].lower() == "to " or o[:5].lower() == "from "), "")
            saaja = (vastapuoli or " ".join(osat))[:40]
        # Viestiosa, joka vain toistaa saajan nimen, ei kerro selitteessä mitään
        # uutta ("Billa 137" + "Billa 137 CARD_PAYMENT") — jätetään pois.
        nimi = normalisoi(saaja)
        jaljelle = [o for o in osat
                    if nimi and normalisoi(o) not in (nimi, f"to {nimi}", f"from {nimi}")]
        selite = siisti(" ".join(str(x) for x in [
            *(jaljelle if nimi else osat), btc, tilinro, tx.get("note"),
            valuutta if valuutta.upper() not in ("", "EUR") else "",
            viite and f"viite {viite}"] if x))
        if not saaja:
            saaja = selite[:40]
        koodi = tx.get("bank_transaction_code")
        laji = siisti(str(koodi.get("code") or "")) if isinstance(koodi, dict) else ""
        rivi = {"pvm": pvm, "summa": summa, "saaja": saaja, "selite": selite,
                "laji": laji}
        if kirjattu:
            ulos.append(rivi)
        else:
            ohitetut["varaus"] += 1
            varaukset.append(rivi)
    if kerro is not None:
        kerro.update(ohitetut)
    return ulos


# PSD2:n tekninen sääntö (RTS 36 art.) velvoittaa pankin sallimaan vain neljä
# hakua vuorokaudessa tiliä kohden silloin kun käyttäjä ei ole itse paikalla.
# Saldo on oma pyyntönsä ja kuluttaa samaa budjettia kuin tapahtumat, joten sitä
# ei haeta koskaan itsestään: se haetaan vain kun käyttäjä sitä pyytää
# (täsmäytys). Sama malli kuin YNABissa — täsmäytys on tietoinen toimitus, ei
# taustalla jyskyttävä tarkistus, ja niukka hakubudjetti kuluu siihen mihin
# käyttäjä sen haluaa kuluvan.


def eb_saldot(account_uid):
    """Tilin saldot rajapinnasta. Palauttaa pankin vastauksen sellaisenaan."""
    return _eb_kutsu(f"/accounts/{account_uid}/balances", eb_token())


def _poimi_saldo(vastaus):
    """Täsmäytykseen kelpaava saldo pankin vastauksesta.

    Saldotyyppejä tulee useita, ja vain osa niistä on vertailukelpoinen
    kirjattujen tapahtumien kanssa:

      ITBD  interim booked   — kirjatut tapahtumat tähän hetkeen. Tämä.
      CLBD  closing booked   — kirjattu edellisen pankkipäivän lopussa.
      ITAV  interim available — sisältää korttivaraukset, jotka eivät ole
                                vielä kirjanpidossa. Ei kelpaa vertailuun.

    OP palauttaa sekä ITAV:n ("Net balance") että ITBD:n ("Gross balance"),
    S-Pankki vain ITBD:n, ja kortit usein pelkän ITAV:n. Palautetaan paras
    saatavilla oleva ja kerrotaan kutsujalle kumpi se oli, jotta raportti voi
    sanoa sen ääneen eikä vertaa omenoita appelsiineihin."""
    saldot = (vastaus or {}).get("balances") or []
    if not isinstance(saldot, list):
        return None

    def _arvo(b):
        m = b.get("balance_amount") or b.get("amount") or {}
        try:
            return round(float(m.get("amount")), 2), siisti(str(m.get("currency", "")))
        except (TypeError, ValueError):
            return None

    for tyyppi_toive in ("ITBD", "CLBD", "ITAV", ""):
        for b in saldot:
            tyyppi = str(b.get("balance_type") or b.get("balanceType") or "").upper()
            if tyyppi_toive and not tyyppi.startswith(tyyppi_toive):
                continue
            arvo = _arvo(b)
            if arvo:
                return {"saldo": arvo[0], "saldo_valuutta": arvo[1],
                        "saldo_tyyppi": tyyppi or "?",
                        "saldo_nimi": siisti(str(b.get("name") or "")),
                        "saldo_hetki": str(b.get("reference_date")
                                           or b.get("last_change_date_time") or ""),
                        "saldo_viimeisin_tapahtuma": str(b.get("last_committed_transaction") or ""),
                        "saldo_kaikki": [{"tyyppi": str(x.get("balance_type") or ""),
                                          "summa": (_arvo(x) or [None])[0],
                                          "nimi": siisti(str(x.get("name") or ""))}
                                         for x in saldot]}
    return None


def _eb_raja(paivia, cfg_alkaen, tili_alkaen):
    """Noudon alkupäivä: enintään `paivia` taakse, ei ennen globaalia eikä
    tilikohtaista alkaen-katkopäivää."""
    raja = date.today() - timedelta(days=max(1, int(paivia)))
    for a in (cfg_alkaen, tili_alkaen):
        a = siisti(str(a or ""))
        if a and a > raja.isoformat():
            try:
                raja = date.fromisoformat(a)
            except ValueError:
                pass
    return raja


def eb_nouda(account_uid, cfg, paivia=89, tili_alkaen=""):
    """Noutaa enintään `paivia` päivän historian. PSD2 sallii yli 90 pv:n
    historian vain tuoreen tunnistautumisen yhteydessä — pidempi pyyntö on
    tyypillinen 422-virheen syy (OP, Revolut). Jatkosivun virhe ei kaada
    noutoa vaan palauttaa siihen asti saadut."""
    tok = eb_token()
    raja = _eb_raja(paivia, cfg.get("alkaen", ""), tili_alkaen)
    kaikki = {"transactions": []}
    jatko = None
    while True:
        polku = (f"/accounts/{account_uid}/transactions?date_from={raja.isoformat()}"
                 + (f"&continuation_key={jatko}" if jatko else ""))
        try:
            data = _eb_kutsu(polku, tok)
        except EBVirhe as e:
            if jatko:
                print(f"⚠ jatkosivu katkesi ({e.koodi}) — {len(kaikki['transactions'])} "
                      f"tapahtumaa saatiin talteen. {e.runko}")
                break
            raise
        kaikki["transactions"] += data.get("transactions", []) or []
        jatko = data.get("continuation_key")
        if not jatko:
            break
    return kaikki


def _siivoa_koodi(s):
    """Poimii ?code=-arvon liimauksesta: kelpaa koko URL, code&state-pötkö tai paljas koodi."""
    s = siisti(s)
    if "code=" in s:
        s = s.split("code=", 1)[1]
    return s.split("&")[0].strip()


def eb_istunto(session_id):
    """Listaa istunnon tilit uid:einesi — valmiit config.jsonin account_id-arvoiksi."""
    tok = eb_token()
    data = _eb_kutsu(f"/sessions/{siisti(session_id)}", tok)
    tilit = data.get("accounts") or []
    if not tilit:
        print("istunnossa ei tilejä (tai vastausmuoto yllätti):")
        print(json.dumps(data, ensure_ascii=False)[:400])
        return
    print(f"Istunnon {siisti(session_id)[:8]}… tilit:")
    for acc in tilit:
        if isinstance(acc, str):
            uid = acc
            try:
                acc = _eb_kutsu(f"/accounts/{uid}/details", tok)
            except EBVirhe as e:
                print(f"  {uid}  (tietoja ei saatu: {e.koodi})")
                continue
        else:
            uid = str(acc.get("uid", "?"))
        aid = acc.get("account_id") or {}
        tunniste = aid.get("iban") or (aid.get("other") or {}).get("identification") or ""
        nimi = acc.get("name") or acc.get("product") or ""
        print(f"  {uid}  {tunniste}  {nimi}".rstrip())
    print('Lisää config.jsonin pankkihaku.tilit-listaan: {"tili": "…", "account_id": "<uid>", "alkaen": "…"}')


# ------------------------------------------- ohjattu käyttöönotto (velho)

EB_KIRJAUTUMINEN = "https://enablebanking.com/sign-in/"
EB_PORTAALI = "https://enablebanking.com/cp/applications"
EB_TESTIPALUU = "https://enablebanking.com/auth_redirect"
# Paikallinen kuuntelija tekee valtuutuksesta kopioinnittoman: pankki palaa
# tähän osoitteeseen, ja _odota_koodi nappaa koodin suoraan selaimesta.
EB_PAIKALLINEN = "http://localhost:8765/callback"
EHDOT = "https://github.com/vsalmens/rahaputki/blob/main/koodi/ehdot"
EB_KUVAUS = "Rahaputki - personal spending tracker running on the user's own computer"
UUID_HAKU = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                       r"[0-9a-f]{4}-[0-9a-f]{12}", re.I)
UUID_KUVIO = re.compile(UUID_HAKU.pattern + "$", re.I)


def _komentorivi():
    """Ohjeissa näytettävä komento sen mukaan, millä koneella ollaan."""
    return "py koodi\\kirjanpito.py" if os.name == "nt" else "python3 koodi/kirjanpito.py"


def _kysy(kysymys, oletus=""):
    """input(), joka ei kaadu putkitettuun tyhjään syötteeseen.

    Palvelimen säikeessä kysyminen on aina virhe: input() jäisi odottamaan
    vastausta, jota kukaan ei ole antamassa, ja pyyntö jäisi roikkumaan
    ikuisesti. Kaatuminen on siinä kohdassa parempi kuin jumi — se näkyy
    käyttäjälle ja korjattavana on yksi puuttuva parametri, ei mysteeri."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("kysymystä ei voi esittää palvelimen säikeessä: "
                           + siisti(str(kysymys))[:80])
    try:
        vastaus = siisti(input(kysymys))
    except EOFError:
        return oletus
    return vastaus or oletus


def _valikko(otsikko, vaihtoehdot, oletus=1):
    """Numeroitu valinta. Palauttaa valitun avaimen; Enter ottaa oletuksen."""
    print(f"\n{otsikko}")
    for i, (_, teksti) in enumerate(vaihtoehdot, 1):
        rivit = str(teksti).split("\n")
        merkki = "   (oletus)" if i == oletus else ""
        print(f"  {i}) {rivit[0]}{merkki}")
        for jatko in rivit[1:]:
            print(jatko)
    vastaus = _kysy(f"Valitse numero [{oletus}] ", str(oletus))
    if vastaus.isdigit() and 1 <= int(vastaus) <= len(vaihtoehdot):
        return vaihtoehdot[int(vastaus) - 1][0]
    return vaihtoehdot[oletus - 1][0]


def _kylla(kysymys, oletus=True):
    vastaus = _kysy(f"{kysymys} [{'K/e' if oletus else 'k/E'}] ").lower()
    return oletus if not vastaus else vastaus[0] in "kyj1"


def _odota_enter(teksti="Paina Enter kun olet valmis..."):
    _kysy(f"\n{teksti} ")


def _siivoa_polku(s):
    """Ikkunaan raahattu tiedosto tulee lainausmerkeissä tai kenoviivoin."""
    s = (s or "").strip()
    if len(s) > 1 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
    return s.replace("\\ ", " ").strip()


def _leikepoydalta():
    """Konsoliin liittäminen on monelle hankalaa (etenkin Windowsissa), joten
    luetaan mieluummin itse. Palauttaa None, jos leikepöytää ei saada auki
    lainkaan — silloin kysytään liittämistä eikä luvata mitään turhaan.

    tkinter kuuluu standardikirjastoon, mutta esim. Homebrew-Pythonista se
    puuttuu; siksi perässä on käyttöjärjestelmän oma komento."""
    try:
        import tkinter
        ikkuna = tkinter.Tk()
        ikkuna.withdraw()
        arvo = ikkuna.clipboard_get()
        ikkuna.destroy()
        return siisti(str(arvo))
    except ImportError:
        pass
    except Exception:
        return ""
    import subprocess
    komento = (["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
               if os.name == "nt" else ["pbpaste"] if sys.platform == "darwin"
               else ["xclip", "-selection", "clipboard", "-o"])
    try:
        tulos = subprocess.run(komento, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return siisti(tulos.stdout) if tulos.returncode == 0 else None


def _avaa_selain(url):
    try:
        import webbrowser
        if webbrowser.open(url):
            return True
    except (ImportError, OSError):
        pass
    return False


def _varmista_kirjastot():
    """pyjwt + cryptography ovat pankkihaun ainoa asennettava osa. Asennus
    ajetaan samalla tulkilla jolla ohjelma pyörii, jottei paketti eksy toiseen
    Python-asennukseen. Ei-tekninen käyttäjä ei osaa tehdä tätä käsin."""
    def _loytyy():
        try:
            import jwt  # noqa: F401
            import cryptography  # noqa: F401
            return True
        except ImportError:
            return False

    if _loytyy():
        return True
    print("\nPankkihaku tarvitsee kaksi lisäkirjastoa (pyjwt ja cryptography).")
    if not _kylla("Asennetaanko ne nyt puolestasi?"):
        print("  Voit asentaa ne itse komennolla:")
        print(f"  {Path(sys.executable).name} -m pip install pyjwt cryptography")
        return False
    import subprocess
    for lisa in ([], ["--user"], ["--user", "--break-system-packages"]):
        komento = [sys.executable, "-m", "pip", "install", "--quiet",
                   *lisa, "pyjwt", "cryptography"]
        try:
            tulos = subprocess.run(komento, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"⚠ asennus ei käynnistynyt: {e}")
            break
        if tulos.returncode == 0:
            import importlib
            import site
            try:
                omat = site.getusersitepackages()
            except AttributeError:
                omat = ""
            for polku in ([omat] if isinstance(omat, str) else list(omat or [])):
                if polku and polku not in sys.path:
                    sys.path.append(polku)
            importlib.invalidate_caches()
            if _loytyy():
                print("✓ kirjastot asennettu")
                return True
            print("✓ kirjastot asennettu — käynnistä Rahaputki uudelleen, "
                  "niin ne otetaan käyttöön")
            return False
    print("⚠ automaattinen asennus ei onnistunut. Asenna käsin:")
    print(f"  {Path(sys.executable).name} -m pip install pyjwt cryptography "
          "--break-system-packages")
    return False


AVAINKANSIOT_VIHJE = "asetukset/ tai ~/.rahaputki/"


def _konekansio():
    """Koneen yhteinen avainkansio. Sama kaikille tämän koneen asennuksille,
    joten täältä löytyvä avain ei ole välttämättä tämän asennuksen eikä edes
    saman Enable Banking -tunnuksen sovellus."""
    return Path.home() / ".rahaputki"


def _etsi_avaimet():
    """Etsi yksityisavain vain paikoista, joihin se kuuluu: tämän asennuksen
    asetukset/ ensin, sitten ~/.rahaputki/. Latauskansiota ja työpöytää ei
    kahlata läpi — siellä voi olla muiden palveluiden avaimia, eikä käyttäjän
    salaisuuksia ole syytä skannata. Muualta tulevan avaimen saa raahaamalla.

    Enable Banking nimeää selaimessa luodun avaimen sovelluksen id:llä
    (<uuid>.pem), joten sellainen kertoo myös EB_APP_ID:n — siksi ne ovat
    kansionsa sisällä kärjessä.

    Palauttaa parit (polku, oma): oma=True on tämän asennuksen oma avain.
    Koneen yhteisestä kansiosta löytynyt on jonkin toisen asennuksen, eikä
    sitä oteta käyttöön kysymättä."""
    loydot, nahdyt = [], set()
    for kansio, oma in ((ASETUKSET, True), (_konekansio(), False)):
        try:
            osumat = [p.resolve() for p in kansio.glob("*.pem") if p.is_file()]
        except OSError:
            continue
        osumat.sort(key=lambda p: (not UUID_KUVIO.match(p.stem), p.name))
        for polku in osumat:
            if polku not in nahdyt:
                nahdyt.add(polku)
                loydot.append((polku, oma))
    return loydot


def _kirjoita_env(arvot):
    """Päivitä avain=arvo-rivit pankkihaku.env:iin muuta sisältöä rikkomatta."""
    polku = _env_polku()
    rivit = polku.read_text(encoding="utf-8").splitlines() if polku.exists() else []
    jaljella = dict(arvot)
    ulos = []
    for rivi in rivit:
        avain = rivi.partition("=")[0].strip()
        if avain in jaljella and not rivi.lstrip().startswith("#"):
            ulos.append(f"{avain}={jaljella.pop(avain)}")
        else:
            ulos.append(rivi)
    if not ulos:
        ulos = ["# Rahaputki: pankkihaun tunnukset. Ei jaeta, ei versioida."]
    ulos += [f"{k}={v}" for k, v in jaljella.items()]
    turvakirjoita(polku, "\n".join(ulos) + "\n")
    try:
        os.chmod(polku, 0o600)
    except OSError:
        pass
    return polku


def _lyhenna_polku(polku):
    """Polku kirjoitetaan siirrettävässä muodossa: kansion sisällä olevat
    suhteellisena (kansion saa siirtää ja nimetä uudelleen), kotihakemiston
    alla olevat ~-muodossa. eb_token laajentaa molemmat takaisin."""
    polku = Path(polku)
    try:
        return str(polku.relative_to(DATAJUURI)).replace(os.sep, "/")
    except ValueError:
        pass
    try:
        return "~/" + str(polku.relative_to(Path.home())).replace(os.sep, "/")
    except ValueError:
        return str(polku)


def _avainpolku(arvo):
    """EB_KEY_PATH voi olla suhteellinen (asetukset/…), ~-alkuinen tai
    absoluuttinen. Suhteellinen tulkitaan aina Rahaputken kansiosta, ei
    työhakemistosta — muuten kaksoisklikkaus ja komentorivi eroaisivat.

    Erotetussa asennuksessa katsotaan ensin koneen omaa kansiota: avain on
    konekohtainen, joten sen suhteellinen polku tarkoittaa sielläkin konetta
    eikä jaettua kirjanpitokansiota. Vanha sijainti kelpaa yhä."""
    polku = Path(siisti(str(arvo or ""))).expanduser()
    if polku.is_absolute():
        return polku
    paikallinen = KOODIJUURI / polku
    if DATAJUURI != KOODIJUURI and paikallinen.exists():
        return paikallinen
    return DATAJUURI / polku


PILVIKANSIOT = ("google drive", "googledrive", "my drive", "onedrive", "dropbox",
                "icloud drive", "mobile documents", "nextcloud", "pcloud",
                "jottacloud", "sync.com", "yandexdisk")


def _pilvisynkassa(polku):
    """Karkea mutta riittävä tunnistus: pilvikansiot näkyvät polun nimissä."""
    nimi = str(polku).lower()
    return any(merkki in nimi for merkki in PILVIKANSIOT)


def _avaimen_kohde(pem):
    """Avain kuuluu oletuksena kansioon asetukset/: silloin kaikki on yhdessä
    paikassa ja seuraa kansiota, jos se siirretään tai nimetään uudelleen.

    Poikkeus on pilvisynkattu kansio (Drive, iCloud, OneDrive…): avain on
    lukupääsy tileihin, eikä sitä pidä synkata mihinkään. Silloin se jää
    kotihakemistoon — ja on olemassa vain sillä koneella, mikä on tarkoituskin."""
    if _pilvisynkassa(DATAJUURI):
        return _konekansio() / pem.name, True
    return ASETUKSET / pem.name, False


LATAUSKANSIOT = ("downloads", "lataukset", "desktop", "työpöytä", "tyopoyta")


def _vapaa_nimi(kohde, pem):
    """Portaali lataa avaimen usein nimellä enablebanking.pem, joten kahden
    eri sovelluksen avaimet törmäävät koneen yhteisessä kansiossa. Toisen
    asennuksen avainta ei kirjoiteta yli, vaan uusi saa numeron perään."""
    try:
        if not kohde.exists() or kohde.read_bytes() == pem.read_bytes():
            return kohde
    except OSError:
        return kohde
    for n in range(2, 100):
        ehdokas = kohde.with_name(f"{kohde.stem}-{n}{kohde.suffix}")
        if not ehdokas.exists():
            return ehdokas
    return kohde


def _talleta_avain(pem, siirra=None):
    """Siirrä avain pois Lataukset-kansiosta (jonka ihmiset tyhjentävät)
    sinne, minne se tässä asennuksessa kuuluu.

    siirra=None kysyy (terminaali), True/False päättää kysymättä. Selaimessa
    kysyminen ei ole vaihtoehto: input() jäisi odottamaan HTTP-säikeessä eikä
    kukaan olisi vastaamassa.

    Jos avain jo asuu järkevässä paikassa, se jätetään sinne: sama avain voi
    olla toisenkin asennuksen käytössä, eikä sitä saa siirtää sen alta."""
    kohde, pilvessa = _avaimen_kohde(pem)
    if pem.resolve() == kohde.resolve():
        return kohde
    kohde = _vapaa_nimi(kohde, pem)
    lataus = normalisoi(pem.parent.name) in LATAUSKANSIOT
    if not lataus and not _pilvisynkassa(pem):
        print(f"\n✓ avain on jo turvallisessa paikassa, käytetään sitä sieltä:")
        print(f"  {pem}")
        return pem
    if pilvessa and not _pilvisynkassa(pem) and not lataus:
        print(f"\n✓ avain on jo pilvisynkan ulkopuolella: {pem}")
        return pem
    print(f"\nAvain on nyt: {pem}")
    if pilvessa:
        print("Rahaputken kansio on pilvisynkassa, joten avainta EI tallenneta")
        print(f"sinne. Turvallinen paikka on {kohde} — vain tällä koneella,")
        print("vain sinun luettavissasi. Toisella koneella tarvitset oman kopion.")
    else:
        print(f"Se kuuluu kansioon {kohde.parent} — samaan paikkaan muiden")
        print("asetustesi kanssa, jolloin se seuraa kansiota mukana.")
        print("(Jos siirrät kansion pilvitallennukseen, siirrä avain pois sieltä.)")
    if not (siirra if siirra is not None else _kylla("Siirretäänkö avain sinne?")):
        return pem
    try:
        kohde.parent.mkdir(parents=True, exist_ok=True)
        turvakirjoita_kopio(pem, kohde)
        os.chmod(kohde, 0o600)
    except OSError as e:
        print(f"⚠ siirto ei onnistunut ({e}) — jätetään avain paikalleen")
        return pem
    try:
        os.remove(pem)
    except OSError:
        print(f"ℹ alkuperäistä ei voitu poistaa — poista se itse: {pem}")
    print(f"✓ avain siirretty: {kohde}")
    return kohde


def _talleta_uusi_avain(pem_teksti, app_id):
    """Itse luotu avain suoraan oikeaan paikkaan — se ei käy latauskansiossa."""
    kohde, _ = _avaimen_kohde(Path(f"{app_id}.pem"))
    kohde.parent.mkdir(parents=True, exist_ok=True)
    turvakirjoita(kohde, pem_teksti)
    try:
        os.chmod(kohde, 0o600)
    except OSError:
        pass
    return kohde


def _velho_rekisterointi():
    """Sovelluksen luonti hallintarajapinnan kautta: käyttäjä kopioi
    portaalista valmiin komennon, kaikki muu tapahtuu täällä."""
    print(f"""
Portaalissa on valmis komento, jonka avulla Rahaputki voi luoda sovelluksen
puolestasi. Se on nopein tapa, ja samalla turvallisin: yksityisavain syntyy
tällä koneella eikä käy selaimen tai Lataukset-kansion kautta.

  1. Selain avautuu sivulle {EB_PORTAALI}. Kirjaudu sähköpostiosoitteellasi —
     salasanaa ei ole, vaan saat sähköpostiisi linkin.
  2. Vieritä sivun alaosaan. Siellä lukee, että sovelluksen voi rekisteröidä
     rajapinnan kautta tai "command line interface" -tavalla. Klikkaa tuota
     korostettua tekstiä.
  3. Esiin tulee laatikko, jonka sisältö alkaa sanalla  curl
     Klikkaa laatikkoa, valitse kaikki (Cmd-A / Ctrl-A) ja kopioi (Cmd-C / Ctrl-C).

Komento sisältää kertakäyttöisen, tunnin voimassa olevan tunnuksen. Käsittele
sitä kuin salasanaa: älä lähetä sitä kenellekään.""")
    _avaa_selain(EB_PORTAALI)
    token = ""
    for _ in range(3):
        vastaus = _kysy("\nPaina Enter kun olet kopioinut (luen leikepöydän), "
                        "tai liitä komento tähän: ")
        if not vastaus:
            leike = _leikepoydalta()
            if leike is None:
                print("⚠ leikepöytää ei saada luettua — liitä komento alle")
                continue
            vastaus = leike
        token = _poimi_token(vastaus)
        if token:
            break
        print("⚠ en löytänyt komennosta tunnusta — varmista että kopioit "
              "koko komennon (se alkaa 'curl' ja sisältää 'Bearer')")
    if not token:
        return None
    # Tuotantosovellus vaatii yhteysosoitteen tietosuoja-asioihin. Portaalin
    # lomakkeella se on oma kenttänsä; tässä se on ainoa asia, jota emme voi
    # päätellä puolesta.
    sposti = _kysy("\nSähköpostiosoitteesi tietosuoja-asioita varten "
                   "(Enter = jätä täyttämättä): ")
    print("\nLuodaan avainpari tällä koneella…")
    pem_teksti, varmenne = _luo_avainpari()
    try:
        vastaus = _rekisteroi_sovellus(token, varmenne, gdpr_email=sposti)
    except EBVirhe as e:
        if e.koodi in (401, 403):
            print("⚠ tunnus ei kelvannut (se vanhenee tunnissa). Lataa "
                  "portaalin sivu uudelleen ja kopioi komento uudestaan.")
        else:
            print(f"⚠ sovelluksen luonti epäonnistui ({e.koodi}): {e.runko}")
        return None
    except (OSError, ValueError) as e:
        print(f"⚠ sovelluksen luonti epäonnistui: {e}")
        return None
    app_id = _sovellus_id(vastaus)
    if not app_id:
        print("ℹ sovellus luotiin, mutta en tunnistanut sen tunnusta vastauksesta.")
        app_id = _kysy("Kopioi sovelluksen tunnus (Application ID) portaalista: ")
        if not UUID_KUVIO.match(app_id):
            return None
    polku = _talleta_uusi_avain(pem_teksti, app_id)
    env = _kirjoita_env({"EB_APP_ID": app_id, "EB_KEY_PATH": _lyhenna_polku(polku),
                         "EB_SOVELLUS_OK": app_id})
    print(f"✓ sovellus Rahaputki luotu ({app_id})")
    print(f"✓ yksityisavain: {polku}")
    print(f"✓ tunnukset tallennettu tiedostoon {env.parent.name}/{env.name}")
    return app_id


def _velho_tunnukset(pakota=False):
    """Vaihe 1: sovellus Enable Bankingiin ja sen avain koneelle."""
    nyt = _eb_asetukset()
    if nyt["EB_APP_ID"] and nyt["EB_KEY_PATH"] and not pakota:
        polku = _avainpolku(nyt["EB_KEY_PATH"])
        if polku.exists():
            print(f"✓ tunnukset ovat jo tallessa ({_env_polku()})")
            print(f"  sovellus {nyt['EB_APP_ID']}, avain {polku}")
            if not _kylla("Vaihdetaanko ne toiseen sovellukseen?", oletus=False):
                return True
        else:
            print(f"⚠ avainta ei löydy polusta {polku} — etsitään uusi")
    print(f"""
VAIHE 1/4 — Enable Banking -sovellus (kerran, noin 5 minuuttia)

Enable Banking on suomalainen, Finanssivalvonnan valvoma yritys, jonka
rajapinnan kautta pankit luovuttavat sinulle omat tapahtumasi. Teet sinne
oman kehittäjätunnuksen: silloin tilitietosi kulkevat sinun sovelluksesi
kautta suoraan koneellesi eikä välissä ole muita palveluita.

Jos sinulla ei vielä ole tunnusta: selain avautuu osoitteeseen
{EB_KIRJAUTUMINEN} — anna sähköpostiosoitteesi ja klikkaa linkkiä, jonka saat
sähköpostiisi. Salasanaa ei ole.""")
    # Sovellus on voitu luoda jo aiemmin (toinen kansio, aiempi yritys,
    # portaalin lomake). Silloin ei pidä luoda uutta vaan ottaa se käyttöön.
    # Oletukseksi vanha avain kelpaa vain, jos se on tämän asennuksen oma:
    # ~/.rahaputki/ on koneen kaikkien asennusten yhteinen, ja sieltä poimittu
    # avain veisi uuden asennuksen huomaamatta toisen Enable Banking
    # -tunnuksen sovellukseen — mikä näkyy vasta siinä, ettei sovellusta löydy
    # portaalista eivätkä tilit aktivoidu.
    loydot = _etsi_avaimet()
    omat = [pol for pol, oma in loydot if oma]
    if loydot:
        polut = "\n".join(f"        {_lyhenna_polku(pol)}"
                          + ("" if oma else "   (koneen yhteinen kansio)")
                          for pol, oma in loydot[:3])
        if len(loydot) > 3:
            polut += f"\n        (ja {len(loydot) - 3} muuta)"
        olemassa = ("Käytä sovellusta, joka sinulla jo on\n"
                    "     Avaintiedosto löytyi koneelta:\n" + polut)
        if not omat:
            olemassa += ("\n     Avain ei ole tämän asennuksen vaan koneen yhteisessä"
                         "\n     kansiossa. Valitse tämä vain, jos loit sovelluksen itse"
                         "\n     samalla Enable Banking -tunnuksella, jolla juuri kirjauduit.")
    else:
        olemassa = ("Minulla on jo sovellus — raahaan sen .pem-avaintiedoston tähän\n"
                    f"     (kansioista {AVAINKANSIOT_VIHJE} ei löytynyt avainta)")
    vaihtoehdot = [
        ("uusi", "Luo minulle uusi sovellus (nopein — avain syntyy tällä koneella)"),
        ("olemassa", olemassa),
        ("lomake", "Luon sovelluksen itse portaalin lomakkeella"),
    ]
    valinta = _valikko("Mistä lähdetään liikkeelle?", vaihtoehdot,
                       oletus=2 if omat and not pakota else 1)
    if valinta == "uusi":
        if not _kylla("\nOletko kirjautunut Enable Bankingin portaaliin?", oletus=True):
            _avaa_selain(EB_KIRJAUTUMINEN)
            _odota_enter("Paina Enter kun olet kirjautunut portaaliin...")
        if _velho_rekisterointi():
            return True
        print("\nJatketaan lomakkeella.")
        valinta = "lomake"
    if valinta == "olemassa":
        return _ota_avain_kayttoon(kerro_lomake=False)
    _avaa_selain(EB_PORTAALI)
    print(f"""
Sovelluksen luonti lomakkeella (portaalin sivu API applications):

  1. Valitse ylhäältä "API applications" ja vieritä alas kohtaan
     "Add a new application".
  2. Environment: valitse "Production" (oikea pankki, oikeat tapahtumat).
  3. Avaimen luonti: jätä ensimmäinen vaihtoehto valituksi
     ("Generate in the browser ... and export private key").
  4. Application name: kirjoita  Rahaputki
  5. Allowed redirect URLs: kopioi tämä rivi sellaisenaan:

        {EB_TESTIPALUU}

     Tänne pankki palauttaa sinut tunnistautumisen jälkeen. Sivu näyttää
     tyhjältä lomakkeelta — se on kunnossa: koodi on selaimen
     osoiterivillä, ja Rahaputki kysyy sen sinulta.
  6. Loput kentät ovat vapaaehtoisia, mutta kannattaa täyttää:

        Application description:
          {EB_KUVAUS}
        Email for data protection matters:
          oma sähköpostiosoitteesi (sovellus on sinun, ei kenenkään muun)
        Privacy URL of the application:
          {EHDOT}/tietosuoja.md
        Terms URL of the application:
          {EHDOT}/kayttoehdot.md

  7. Klikkaa "Register". Selain lataa tiedoston, jonka nimi on pitkä
     tunnus ja pääte .pem — se on sovelluksesi salainen avain.
     Älä avaa sitä äläkä lähetä sitä kenellekään.
  8. Siirrä ladattu tiedosto kansioon  {ASETUKSET}
     (tai raahaa se hetken päästä tähän ikkunaan).
""")
    _odota_enter("Paina Enter, kun .pem-tiedosto on latautunut...")
    return _ota_avain_kayttoon(kerro_lomake=True)


def _kysy_sovellus(app_id, pem):
    """Kysy rajapinnalta, mikä sovellus tästä avaimesta ja tunnuksesta avautuu.

    Tiedostonimi ja kansio ovat arvauksia; GET /application on ainoa lähde,
    joka kertoo sovelluksen nimen, ympäristön ja tilan — ja samalla sen, että
    avain ja tunnus ovat samasta sovelluksesta.

    Palauttaa (app, virhe). app on None vain, kun rajapinta torjui parin
    (401/403): silloin tunnuksia ei pidä tallentaa lainkaan. Verkkokatko tai
    vanha rajapintaversio antaa tyhjän app:n ja virheilmoituksen — käyttöönotto
    saa silti jatkua, koska tarkistus tehdään vielä vaiheessa 2."""
    try:
        token = eb_jwt(app_id, pem.read_text(encoding="utf-8"))
        return _eb_kutsu("/application", token), ""
    except EBVirhe as e:
        if e.koodi in (401, 403):
            return None, "avain ja sovelluksen tunnus eivät ole samasta sovelluksesta"
        return {}, f"rajapinta vastasi {e.koodi}"
    except OSError as e:
        return {}, f"yhteyttä ei saatu ({e})"
    except Exception as e:
        return {}, f"avainta ei voitu käyttää ({e})"


def _hyvaksy_sovellus(app, app_id, oma):
    """Näytä, MIKÄ sovellus ollaan ottamassa käyttöön, ennen kuin tunnukset
    kirjoitetaan. Rajapinta ei kerro, kenen Enable Banking -tunnukselle
    sovellus kuuluu — sen tietää vain käyttäjä, joten se kysytään aina kun
    avain ei ole tämän asennuksen oma. Väärä sovellus paljastuisi muuten vasta
    siinä, ettei portaalin tililtä löydy sovellusta eivätkä tilit aktivoidu."""
    nimi = _kentta(app, "name") or "(nimetön)"
    ymparisto = str(_kentta(app, "environment") or "?").upper()
    print(f"\nAvain avaa sovelluksen: {nimi} ({ymparisto})")
    print(f"  sovelluksen tunnus: {app_id}")
    if _kentta(app, "active") is False:
        print("  tilejä ei ole vielä liitetty (sovellus ei ole aktiivinen)")
    paluut = [siisti(str(u)) for u in (_kentta(app, "redirect_urls", "redirectUrls") or [])]
    varoitukset = []
    if paluut and EB_TESTIPALUU not in paluut:
        varoitukset.append(f"""
⚠ Sovelluksen paluuosoite ei ole Rahaputken vaan toisen palvelun:
    {", ".join(paluut)}
  Sovellus on siis luotu jotain muuta ohjelmaa varten. Pankista palaava
  kertakäyttöinen tunnistautumiskoodi ohjautuisi sen palvelimelle.""")
    if ymparisto not in ("PRODUCTION", "?"):
        varoitukset.append(f"""
⚠ Sovellus on {ymparisto}-ympäristössä. Sandbox on kehittäjien leikkikenttä:
  sieltä saa keksittyjä mock-pankkeja ja testitilejä, ei sinun tapahtumiasi.
  Ympäristöä ei voi vaihtaa jälkikäteen — tuotantoa varten on luotava uusi
  sovellus.""")
    for varoitus in varoitukset:
        print(varoitus)
    if varoitukset:
        return _kylla("Otetaanko se silti käyttöön?", oletus=False)
    if not oma:
        print("Sen pitää olla sinun sovelluksesi, luotu sillä Enable Banking")
        print("-tunnuksella, jolla juuri kirjauduit.")
        return _kylla("Onko tämä sinun sovelluksesi?", oletus=False)
    return True


def _ota_avain_kayttoon(kerro_lomake=True):
    """Etsi ja ota käyttöön olemassa oleva .pem-avain sovelluksineen."""
    if not kerro_lomake:
        print(f"\nEtsitään avaintiedostoa kansiosta {AVAINKANSIOT_VIHJE}. Se on se "
              "\n.pem-tiedosto, jonka sait sovellusta luodessasi. Jos se on muualla, "
              "\nvoit raahata sen tähän ikkunaan.")
    pem, oma = None, False
    for _ in range(3):
        loydot = _etsi_avaimet()
        if loydot:
            print("\nLöytyi avaintiedosto:")
            for i, (polku, oma) in enumerate(loydot[:5], 1):
                lisa = "" if oma else "   (koneen yhteinen kansio — toisen asennuksen)"
                print(f"  {i}) {polku}{lisa}")
            # Enter poimii ensimmäisen vain, jos se on tämän asennuksen oma.
            oletus = "1" if loydot[0][1] else ""
            valinta = _kysy("Valitse numero, tai raahaa oikea tiedosto tähän "
                            f"ikkunaan ja paina Enter{' [1]' if oletus else ''} ", oletus)
            if not valinta:
                print("⚠ valitse numero tai raahaa tiedosto ikkunaan.")
                continue
            if valinta.isdigit() and 1 <= int(valinta) <= len(loydot[:5]):
                pem, oma = loydot[int(valinta) - 1]
            else:
                pem, oma = Path(_siivoa_polku(valinta)).expanduser(), False
        else:
            print(f"\nEn löytänyt .pem-tiedostoa kansiosta {AVAINKANSIOT_VIHJE}.")
            annettu = _siivoa_polku(_kysy("Raahaa tiedosto tähän ikkunaan ja "
                                          "paina Enter (tai Enter = etsi uudelleen): "))
            if not annettu:
                continue
            pem = Path(annettu).expanduser()
        if pem and pem.is_file():
            break
        print(f"⚠ tiedostoa ei löydy: {pem}")
        pem = None
    if not pem:
        print("Avainta ei löytynyt. Aja komento uudelleen, kun tiedosto on koneella.")
        return False
    if not UUID_KUVIO.match(pem.stem):
        print(f"\nℹ tiedoston nimi ei ole sovelluksen tunnus ({pem.name}).")
        app_id = _kysy("Kopioi sovelluksen tunnus (Application ID) portaalista tähän: ")
        if not app_id:
            return False
    else:
        app_id = pem.stem
    app, virhe = _kysy_sovellus(app_id, pem)
    if app is None:
        print(f"\n⚠ {virhe}.")
        print("  Sovelluksen tunnus löytyy portaalista sen sovelluksen kohdalta,")
        print("  jonka .pem-tiedoston valitsit. Tunnuksia ei tallennettu.")
        return False
    if virhe:
        print(f"ℹ sovellusta ei voitu tarkistaa nyt: {virhe} — jatketaan silti")
    elif not _hyvaksy_sovellus(app, app_id, oma):
        print("\nPeruttu — tunnuksia ei tallennettu. Luo oma sovellus valitsemalla")
        print("'Luo minulle uusi sovellus'.")
        return False
    pem = _talleta_avain(pem)
    env = _kirjoita_env({"EB_APP_ID": app_id, "EB_KEY_PATH": _lyhenna_polku(pem),
                         "EB_SOVELLUS_OK": app_id})
    print(f"✓ tunnukset tallennettu tiedostoon {env.parent.name}/{env.name}")
    return True


EB_HALLINTA = "https://enablebanking.com/api/applications"


def _luo_avainpari(nimi="Rahaputki"):
    """RSA-avain ja itse allekirjoitettu varmenne tällä koneella.

    Enable Bankingin selainlomake luo avaimen selaimessa ja pudottaa sen
    latauskansioon; tässä yksityisavain syntyy koneella eikä käy missään —
    rajapinnalle lähtee vain julkinen varmenne."""
    from datetime import timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    avain = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nimio = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nimi)])
    nyt = datetime.now(timezone.utc)
    varmenne = (x509.CertificateBuilder()
                .subject_name(nimio).issuer_name(nimio)
                .public_key(avain.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(nyt - timedelta(days=1))
                .not_valid_after(nyt + timedelta(days=3650))
                .sign(avain, hashes.SHA256()))
    return (avain.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode(),
            varmenne.public_bytes(serialization.Encoding.PEM).decode())


def _poimi_token(teksti):
    """Portaalin valmis komento sisältää 'Authorization: Bearer <token>'.
    Hyväksytään myös paljas token, jos käyttäjä kopioi vain sen."""
    osuma = re.search(r"Bearer\s+([A-Za-z0-9._\-]{100,})", teksti or "")
    if osuma:
        return osuma.group(1)
    ehdokas = siisti(teksti or "")
    return ehdokas if ehdokas.count(".") == 2 and len(ehdokas) > 100 else ""


def _hallintakutsu(token, runko):
    import urllib.error
    import urllib.request
    pyynto = urllib.request.Request(
        EB_HALLINTA, data=json.dumps(runko).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pyynto, timeout=30) as vastaus:
            return json.loads(vastaus.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            teksti = e.read().decode()[:400]
        except OSError:
            teksti = ""
        raise EBVirhe(e.code, teksti) from e


def _rekisteroi_sovellus(token, varmenne, nimi="Rahaputki", gdpr_email=""):
    """Luo tuotantosovellus hallintarajapinnan kautta.

    Paluuosoitteita pyydetään kaksi: portaalin oma sivu ja paikallinen
    kuuntelija. Jälkimmäinen on ainoa tapa päästä eroon osoiterivin
    kopioinnista jokaisen valtuutuksen yhteydessä, mutta rajapinta ei
    välttämättä hyväksy http-skeemaa — silloin se pudotetaan. Samoin
    valinnaiset kentät: ne lähetetään ensin, ja jos rajapinta ei niitä tunne,
    yritetään ilman. Rekisteröinti on kertaluontoinen, joten kannattaa
    yrittää parasta ensin ja tyytyä vähempään vasta jos on pakko."""
    perus = {"name": nimi, "certificate": varmenne, "environment": "PRODUCTION",
             "redirect_urls": [EB_TESTIPALUU]}
    laaja = dict(perus, description=EB_KUVAUS,
                 privacy_url=f"{EHDOT}/tietosuoja.md",
                 terms_url=f"{EHDOT}/kayttoehdot.md")
    if gdpr_email:
        laaja["gdpr_email"] = gdpr_email
    # Paikallista http://localhost-osoitetta ei enää yritetä rekisteröidä.
    # Enable Banking ei hyväksy http-skeemaa, joten yritys epäonnistui joka
    # kerta ja tulosti rivin, joka selitti saman asian uudelleen — kohina,
    # joka opettaa ohittamaan myös ne rivit, jotka kertovat jotain.
    yritykset = [laaja, perus]
    for i, runko in enumerate(yritykset):
        try:
            return _hallintakutsu(token, runko)
        except EBVirhe as e:
            if e.koodi not in (400, 422) or i + 1 == len(yritykset):
                raise
            print("ℹ rajapinta ei ottanut valinnaisia kenttiä vastaan — "
                  "täytä kuvaus ja URLit portaalissa myöhemmin")


def _sovellus_id(vastaus):
    """Sovelluksen tunnus voi tulla eri nimisenä kentässä; etsitään uuid."""
    if isinstance(vastaus, dict):
        for avain in ("id", "application_id", "uid", "kid", "app_id", "applicationId"):
            arvo = siisti(str(vastaus.get(avain, "")))
            if UUID_KUVIO.match(arvo):
                return arvo
    osuma = UUID_HAKU.search(json.dumps(vastaus)) if vastaus else None
    return osuma.group(0) if osuma else ""


def eb_sovellus():
    """GET /application — sovelluksen nimi, ympäristö, tila ja paluuosoitteet."""
    return _eb_kutsu("/application", eb_token())


def _kentta(data, *nimet):
    for nimi in nimet:
        if isinstance(data, dict) and data.get(nimi) not in (None, ""):
            return data[nimi]
    return None


def _velho_tarkista():
    """Vaihe 2: toimiiko avain, ja onko sovellus aktivoitu omilla tileillä."""
    print("\nVAIHE 2/4 — yhteyden ja sovelluksen tarkistus")
    try:
        app = eb_sovellus()
    except EBVirhe as e:
        print(f"⚠ Enable Banking ei hyväksynyt tunnuksia (virhe {e.koodi}).")
        if e.koodi == 404:
            print("  Vanhempi rajapintaversio ei tunne /application-kutsua — "
                  "jatketaan ilman tarkistusta.")
            return {}
        if e.koodi in (401, 403):
            print("  Yleisin syy: avaintiedosto ja sovelluksen tunnus eivät ole")
            print("  samasta sovelluksesta. Aja komento uudelleen valitsemalla")
            print("  'vaihdetaanko toiseen sovellukseen' ja valitse oikea .pem.")
        else:
            print(f"  {e.runko}")
        return None
    except (OSError, ValueError) as e:
        print(f"⚠ yhteys ei toiminut: {e}")
        return None
    except Exception as e:  # avaintiedosto voi olla rikki tai väärää tyyppiä
        print(f"⚠ avainta ei voitu käyttää: {e}")
        print("  Tarkista, että valitsit Enable Bankingin lataaman .pem-tiedoston.")
        return None
    asetukset = _eb_asetukset()
    hyvaksytty = bool(asetukset["EB_APP_ID"]) and (
        asetukset["EB_SOVELLUS_OK"] == asetukset["EB_APP_ID"])
    nimi = _kentta(app, "name") or "(nimetön)"
    ymparisto = str(_kentta(app, "environment") or "?").upper()
    aktiivinen = _kentta(app, "active")
    paluut = _kentta(app, "redirect_urls", "redirectUrls") or []
    print(f"✓ yhteys toimii — sovellus: {nimi} ({ymparisto})")
    if paluut:
        print("  paluuosoitteet: " + ", ".join(str(u) for u in paluut))
    # Vieras paluuosoite tarkoittaa, että käytössä on toisen ohjelman sovellus:
    # pankista palaava kertakäyttöinen koodi kulkisi sen palvelimen kautta.
    if not hyvaksytty and paluut and EB_TESTIPALUU not in [siisti(str(u)) for u in paluut]:
        print(f"""
⚠ SOVELLUS ON LUOTU TOISTA OHJELMAA VARTEN.

Sen paluuosoite ei ole Rahaputken {EB_TESTIPALUU}, vaan
{", ".join(str(u) for u in paluut)}. Pankista palaava tunnistautumiskoodi
ohjautuisi sinne. Lisää portaalissa tälle sovellukselle Rahaputken
paluuosoite, tai luo Rahaputkelle oma sovellus:

  {_komentorivi()} pankkihaku --uusi-sovellus
""")
        if not _kylla("Jatketaanko silti tällä sovelluksella?", oletus=False):
            return None
        _kirjoita_env({"EB_SOVELLUS_OK": asetukset["EB_APP_ID"]})
    # Ympäristöä ei voi vaihtaa jälkikäteen, joten väärä valinta portaalin
    # lomakkeella (tai vanha sandbox-sovellus) kannattaa kertoa heti eikä
    # vasta siinä, että tapahtumat ovat keksittyjä.
    if not hyvaksytty and ymparisto not in ("PRODUCTION", "?"):
        print(f"""
⚠ SOVELLUS ON {ymparisto}-YMPÄRISTÖSSÄ, EI TUOTANNOSSA.

Sandbox on kehittäjien leikkikenttä: sieltä saa keksittyjä mock-pankkeja ja
testitilejä, ei sinun tilejäsi eikä sinun tapahtumiasi. Ympäristöä ei voi
vaihtaa jälkikäteen — tarvitset uuden sovelluksen, jonka Environment on
Production:

  {_komentorivi()} pankkihaku --uusi-sovellus
""")
        if not _kylla("Jatketaanko silti tällä sovelluksella?", oletus=False):
            return None
        _kirjoita_env({"EB_SOVELLUS_OK": asetukset["EB_APP_ID"]})
    if aktiivinen is False:
        print("""
Sovellus ei ole vielä aktiivinen. Se aktivoituu, kun liität siihen omat
tilisi — henkilökäytössä tämä on ilmainen tapa saada tuotantoyhteys.

  1. Selain avautuu sovelluslistaan.
  2. Klikkaa sovelluksesi kohdalta "Activate by linking accounts"
     (tai "Link accounts").
  3. Valitse pankki ja tunnistaudu pankkitunnuksillasi.
  4. TOISTA kohdat 2–3 jokaiselle tilille ja kortille, jonka haluat mukaan —
     myös eri pankeille erikseen. Liittämättömästä tilistä ei saa
     tapahtumia myöhemminkään; rajapinta palauttaa siitä tyhjää.
""")
        _avaa_selain(EB_PORTAALI)
        _odota_enter("Paina Enter, kun tilit on liitetty...")
        try:
            app = eb_sovellus()
        except (EBVirhe, OSError, ValueError):
            pass
        if _kentta(app, "active") is False:
            print("ℹ sovellus näkyy yhä ei-aktiivisena. Voit jatkaa silti, "
                  "mutta valtuutus todennäköisesti palauttaa tyhjän tililistan.")
    return app


def _paluuosoitteet(app):
    return [siisti(str(u)) for u in (_kentta(app, "redirect_urls", "redirectUrls") or [])]


def _on_paikallinen(osoite):
    """Paikallinen kuuntelija on käytettävissä vain http-osoitteelle omalla
    koneella: https vaatisi varmenteen, jota emme voi tarjota."""
    osoite = siisti(str(osoite or "")).lower()
    return osoite.startswith("http://") and ("localhost" in osoite
                                             or "127.0.0.1" in osoite)


def _valitse_paluuosoite(app, cfg):
    """Sovellukselle rekisteröity https-paluuosoite.

    Paikallista http://localhost-osoitetta ei enää kokeilla. Se olisi paras
    ratkaisu — koodi napattaisiin selaimesta eikä käyttäjän tarvitsisi kopioida
    mitään — mutta Enable Banking ei hyväksy http-skeemaa, ja https vaatisi
    varmenteen jota emme voi tarjota. Yritys epäonnistui siis joka kerta,
    kulutti yhden rajapintakutsun ja tulosti rivin, joka selitti saman asian
    uudelleen. Osoitteet suodatetaan siksi jo tässä."""
    paluut = [u for u in _paluuosoitteet(app) if not _on_paikallinen(u)]
    nykyinen = siisti((cfg.get("pankkihaku") or {}).get("redirect_url", ""))
    if _on_paikallinen(nykyinen):
        nykyinen = ""
    if nykyinen and (not paluut or nykyinen in paluut):
        return nykyinen
    if paluut:
        return paluut[0]
    return EB_TESTIPALUU


def _odota_koodi(redirect, aikaraja=300):
    """Kuuntelee paikallista paluuosoitetta ja nappaa ?code=-arvon selaimesta,
    jottei käyttäjän tarvitse kopioida mitään."""
    import http.server
    import urllib.parse
    osat = urllib.parse.urlsplit(redirect)
    if osat.scheme != "http" or osat.hostname not in ("localhost", "127.0.0.1"):
        return ""
    saalis = {}

    class Kasittelija(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            kysely = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            saalis["code"] = (kysely.get("code") or [""])[0]
            saalis["error"] = (kysely.get("error") or [""])[0]
            onnistui = bool(saalis["code"])
            runko = ("<!doctype html><meta charset=\"utf-8\">"
                     "<body style=\"font-family:system-ui,sans-serif;padding:3em;"
                     "max-width:32em;margin:auto\">"
                     + ("<h2>Valmis ✓</h2><p>Pankki on valtuutettu."
                        if onnistui else
                        "<h2>Valtuutus keskeytyi</h2><p>Palaa Rahaputkeen ja "
                        "yritä uudelleen.")
                     + "</p><p>Voit sulkea tämän välilehden ja palata "
                       "Rahaputken ikkunaan.</p>").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(runko)))
            self.end_headers()
            self.wfile.write(runko)

        def log_message(self, *a):
            pass

    portti = osat.port or 80
    try:
        palvelin = http.server.HTTPServer(("127.0.0.1", portti), Kasittelija)
    except OSError as e:
        print(f"⚠ porttia {portti} ei voitu avata ({e}) — käytetään kopiointitapaa")
        return ""
    palvelin.timeout = 1.0
    loppuu = time.time() + aikaraja
    try:
        while not saalis and time.time() < loppuu:
            palvelin.handle_request()
    except KeyboardInterrupt:
        return ""
    finally:
        palvelin.server_close()
    if saalis.get("error"):
        print(f"⚠ pankki palautti virheen: {saalis['error']}")
    return saalis.get("code", "")


def _koodi_kelpaa(syote, koodi):
    """Osoiteliitos tunnistetaan 'code=' -osasta; paljas liitos hyväksytään
    vain jos se näyttää koodilta (pitkä, yhtenäinen) eikä sekalaiselta
    leikepöydän sisällöltä."""
    if not koodi:
        return False
    return "code=" in syote or (len(koodi) >= 16 and " " not in koodi)


def _kysy_koodi(redirect):
    """Pankista palataan osoitteeseen, jonka perässä koodi on. Sivu itse voi
    näyttää tyhjältä lomakkeelta — koodi on osoiterivillä, ei sivulla."""
    print("\nKun olet tunnistautunut, selain palaa osoitteeseen")
    print(f"  {redirect}?code=…")
    print("Sivu voi näyttää tyhjältä tai oudolta — se ei haittaa. Tarvittava")
    print("koodi on selaimen OSOITERIVILLÄ. Kopioi osoiterivi kokonaan")
    print("(macOS: Cmd-L, Cmd-C — Windows: Ctrl-L, Ctrl-C).")
    leikepoyta = True
    for _ in range(3):
        vastaus = _kysy("\nPaina Enter kun olet kopioinut (luen leikepöydän), "
                        "tai liitä osoite tähän: " if leikepoyta
                        else "\nLiitä kopioitu osoite tähän: ")
        if not vastaus:
            leike = _leikepoydalta()
            if leike is None:
                leikepoyta = False
                print("⚠ leikepöytää ei saada luettua tällä koneella — "
                      "liitä osoite alle (macOS: Cmd-V, Windows: Ctrl-V "
                      "tai hiiren oikea nappi)")
                continue
            if "code=" not in leike:
                print("⚠ leikepöydällä ei ole valtuutusosoitetta — "
                      "kopioi selaimen osoiterivi ja yritä uudelleen")
                continue
            vastaus = leike
        koodi = _siivoa_koodi(vastaus)
        if _koodi_kelpaa(vastaus, koodi):
            return koodi
        print("⚠ tuo ei näytä valtuutuskoodilta — odotin osoitetta, jossa on "
              "'?code=' -osa")
    return ""


def _eb_pankit(tok, maa="FI"):
    kaikki = _eb_kutsu(f"/aspsps?country={maa}", tok).get("aspsps", [])
    nimet = {}
    for a in kaikki:
        nimet.setdefault(siisti(a.get("name", "")), a)
    return [nimet[n] for n in sorted(nimet) if n]


def _psu_tyypit(aspsp):
    """Pankki kertoo, kelpaako sille henkilö- vai yritystunnistautuminen.
    Väärä tyyppi kaatuu virheeseen 422 (WRONG_ASPSP_PROVIDED)."""
    tyypit = [siisti(str(t)).lower() for t in (aspsp.get("psu_types") or []) if siisti(str(t))]
    return tyypit or ["personal"]


def _psu_valinta(aspsp):
    """Valitse psu_type: yksikäsitteinen menee suoraan, muuten kysytään."""
    tyypit = _psu_tyypit(aspsp)
    if len(tyypit) == 1:
        if tyypit[0] != "personal":
            print(f"  ({aspsp.get('name', '')} tunnistaa vain yritystilit)")
        return tyypit[0]
    return "business" if _kylla("  Onko kyseessä yritystili?", oletus=False) else "personal"


def _valitse_pankki(pankit, hakusana=""):
    if hakusana:
        osuvat = [a for a in pankit if normalisoi(hakusana) in normalisoi(a.get("name", ""))]
        if len(osuvat) == 1:
            return osuvat[0]
        if not osuvat:
            print(f"⚠ pankkia '{hakusana}' ei löytynyt")
            osuvat = pankit
        pankit = osuvat
    print("\nPankit:")
    for i, a in enumerate(pankit, 1):
        tyypit = _psu_tyypit(a)
        merkki = "  (yritystilit)" if tyypit == ["business"] else ""
        print(f"  {i:2}) {a.get('name', '')}{merkki}")
    valinta = _kysy("Valitse numero (tai kirjoita osa pankin nimestä, "
                    "Enter = peruuta): ")
    if not valinta:
        return None
    if valinta.isdigit() and 1 <= int(valinta) <= len(pankit):
        return pankit[int(valinta) - 1]
    return _valitse_pankki(pankit, valinta)


def _ehdota_tilinimi(pankki, acc):
    """Tilin nimi ohjaa CSV-muodon, joten se kannattaa osua vakionimiin."""
    aid = acc.get("account_id") or {}
    iban = siisti(aid.get("iban") or "")
    p = normalisoi(pankki)
    if "revolut" in p:
        return "Revolut"
    if "s-pankki" in p or "s pankki" in p or "spankki" in p:
        perus, kortti = "S-Pankki", "S-Pankki kortti"
    elif p.startswith("op") or "osuuspankki" in p or "pohjola" in p:
        perus, kortti = "OP-tili", "OP-kortti"
    else:
        perus = siisti(pankki) or "Pankki"
        kortti = f"{perus} kortti"
    return perus if iban else kortti


def _on_paikanpitaja(account_id):
    """config.esimerkki.json:in mallirivi ei ole tili — sitä ei haeta eikä
    säilytetä, kun velho kirjoittaa oikeat tunnukset tilalle."""
    aid = siisti(str(account_id or "")).upper()
    return not aid or "VELHOLTA" in aid or aid.startswith("TILIN-UID")


def _viimeinen_pvm(tilinimi):
    """Katkopäiväsääntö: uusi reitti aloitetaan viimeisen tuodun päivän
    PÄÄLTÄ, ei sen jälkeen — limitys on ilmaista, aukko on äänetön."""
    paivat = [siisti(r.get("pvm", "")) for r in lue_ledger()
              if siisti(r.get("tili", "")) == tilinimi]
    return max((p for p in paivat if p), default="")


def _tunniste(acc):
    """Tilin pysyvä tunniste: IBAN, tai kortin kohdalla sen oma tunnus."""
    aid = acc.get("account_id") or {}
    return siisti(aid.get("iban") or (aid.get("other") or {}).get("identification") or "")


def _tallenna_tilit(cfg, pankki, tilit, istunto=None):
    """Nimeä noudetut tilit ja kirjoita ne config.jsoniin.

    Suostumus uusitaan pankeittain 90–180 päivän välein, ja tilin uid voi
    vaihtua sen mukana. Rivi tunnistetaan siksi ensisijaisesti IBANista:
    uusinta päivittää vanhan rivin sen sijaan että kasvattaisi listaa
    kuolleilla tunnuksilla."""
    ph = cfg.setdefault("pankkihaku", {})
    ph["palvelu"] = "enablebanking"
    lista = ph.setdefault("tilit", [])
    lista[:] = [t for t in lista if not _on_paikanpitaja(t.get("account_id"))]
    print(f"\nValtuutus onnistui: {len(tilit)} tiliä. Nimeä ne niin kuin haluat "
          "niiden näkyvän raportissa.")
    print("Nimet OP-tili ja S-Pankki kirjoitetaan pankin omassa CSV-muodossa; "
          "muut (Revolut, kortit) yleisessä muodossa.")
    # Käsin asetettu alkupäivä ei saa kadota, kun vanha rivi korvautuu.
    vanhat_alkaen = {t.get("tili"): t.get("alkaen") for t in lista if t.get("alkaen")}
    nahdyt, uusia = [], 0
    for acc in tilit:
        uid = str(acc.get("uid", ""))
        if not uid:
            continue
        tunniste = _tunniste(acc)
        vanha = (next((t for t in lista if tunniste
                       and siisti(str(t.get("tunniste", ""))) == tunniste), None)
                 or next((t for t in lista if t.get("account_id") == uid), None))
        kuvaus = siisti(" ".join(str(x) for x in [acc.get("name"), acc.get("product"),
                                                  acc.get("usage")] if x))
        ehdotus = (vanha or {}).get("tili") or _ehdota_tilinimi(pankki, acc)
        print(f"\n  tili {tunniste or uid}  {kuvaus}".rstrip())
        nimi = _kysy(f"  Nimi raportissa [{ehdotus}]: ", ehdotus)
        rivi = {"tili": nimi, "account_id": uid, "tunniste": tunniste,
                "pankki": siisti(pankki)}
        # Voimassaolo on pankin antama, ei meidän pyyntömme: tallennetaan se
        # mitä vastauksessa lukee. Pankki voi myöntää pyydettyä lyhyemmän.
        paasy = ((istunto or {}).get("access") or {})
        paivita_pankkitila(uid, pankki=siisti(pankki), tili=nimi,
                           session_id=str((istunto or {}).get("session_id") or "") or None,
                           valtuutus_asti=str(paasy.get("valid_until") or "")[:10] or None,
                           valtuutettu=date.today().isoformat(), virhe="")
        if vanha is None:
            rivi["alkaen"] = _viimeinen_pvm(nimi) or vanhat_alkaen.get(nimi, "")
            if rivi["alkaen"]:
                print(f"  ℹ pääkirjassa on tätä nimeä viimeksi {rivi['alkaen']} — "
                      "nouto aloitetaan siitä päivästä (limitys on turvallinen)")
            lista.append(rivi)
            uusia += 1
        else:
            if vanha.get("account_id") != uid:
                print("  ↻ valtuutus uusittu — tilin tunnus päivitetty vanhalle riville")
            vanha.update(rivi)
        nahdyt.append(uid)
    # Vanhat rivit (ennen tunniste-kenttää) eivät tiedä pankkiaan, joten
    # tunnistetaan ne juuri tallennetun tilinimen perusteella — ja kysytään.
    nimet = {t.get("tili") for t in lista if t.get("account_id") in nahdyt}
    vanhentuneet = [t for t in lista if t.get("account_id") not in nahdyt
                    and (siisti(str(t.get("pankki", ""))) == siisti(pankki)
                         or (not t.get("pankki") and t.get("tili") in nimet))]
    if vanhentuneet:
        print("\nNämä saman pankin rivit eivät olleet mukana tässä valtuutuksessa:")
        for t in vanhentuneet:
            print(f"  {t.get('tili', '')}  {t.get('tunniste') or t.get('account_id')}")
        if _kylla("Poistetaanko ne? (vanhentunut tunnus tuottaa vain virheitä)"):
            poistetut = {id(t) for t in vanhentuneet}
            lista[:] = [t for t in lista if id(t) not in poistetut]
    turvakirjoita_json(CONFIG, cfg)
    print(f"\n✓ tilit tallennettu asetukset/config.json:iin "
          f"({uusia} uutta, {len(nahdyt) - uusia} päivitettyä)")


# --- valtuutuksen osat ilman dialogia -----------------------------------
# Terminaali kysyy kysymykset jonossa, selain pitää tilaa jota voi muokata.
# Kumpikin tarvitsee saman tekemisen, joten tekeminen on täällä ja kysyminen
# kutsujassa. Ilman tätä jakoa selainvelho perisi terminaalin lineaarisuuden:
# kysymys, johon on jo vastattu, ei ole enää olemassa eikä sitä voi vaihtaa.

def eb_pankkilista(maa="FI"):
    """Maan pankit valintaa varten."""
    return _eb_pankit(eb_token(), maa)


def eb_aloita_valtuutus(cfg, aspsp, psu_tyyppi, app=None):
    """Käynnistä pankin tunnistautuminen. Palauttaa (url, redirect).

    Paluuosoite valitaan samalla logiikalla kuin ennen: paikallinen ensin, ja
    jos rajapinta ei sitä hyväksy, pudotaan sovelluksen https-osoitteeseen —
    hylkäys tulee vastaan kerran eikä joka kerta."""
    import uuid
    tok = eb_token()
    maa = aspsp.get("country") or (cfg.get("pankkihaku") or {}).get("maa") or "FI"
    redirect = _valitse_paluuosoite(app, cfg)
    vaihtoehdot = [redirect]
    if _on_paikallinen(redirect):
        vaihtoehdot += [u for u in _paluuosoitteet(app)
                        if not _on_paikallinen(u)] or [EB_TESTIPALUU]
    viimeisin = None
    for i, osoite in enumerate(vaihtoehdot):
        try:
            vastaus = _eb_kutsu("/auth", tok, {
                "access": {"valid_until": (datetime.now().astimezone()
                                           + timedelta(days=90)).isoformat()},
                "aspsp": {"name": aspsp["name"], "country": maa},
                "psu_type": psu_tyyppi,
                "state": str(uuid.uuid4()),
                "redirect_url": osoite})
            ph = cfg.setdefault("pankkihaku", {})
            if ph.get("redirect_url") != osoite:
                ph["redirect_url"] = osoite
            return str(vastaus.get("url", "")), osoite
        except EBVirhe as e:
            viimeisin = e
            if e.koodi == 400 and i + 1 < len(vaihtoehdot):
                continue
            raise
    raise viimeisin


def eb_viimeistele_valtuutus(koodi):
    """Vaihda pankista palannut koodi istunnoksi. Palauttaa (istunto, tilit)."""
    istunto = _eb_kutsu("/sessions", eb_token(), {"code": _siivoa_koodi(koodi)})
    return istunto, (istunto.get("accounts") or [])


def tilien_ehdotukset(cfg, pankki, tilit):
    """Ehdotettu nimi ja tunniste jokaiselle tilille — se, mitä käyttäjältä
    kysytään. Vanha nimi voittaa ehdotuksen, jottei uusinta nimeä tilejä
    uudelleen käyttäjän selän takana."""
    lista = ((cfg.get("pankkihaku") or {}).get("tilit") or [])
    ulos = []
    for acc in tilit:
        uid = str(acc.get("uid", ""))
        if not uid:
            continue
        tunniste = _tunniste(acc)
        vanha = (next((t for t in lista if tunniste
                       and siisti(str(t.get("tunniste", ""))) == tunniste), None)
                 or next((t for t in lista if t.get("account_id") == uid), None))
        ulos.append({
            "uid": uid, "tunniste": tunniste,
            "kuvaus": siisti(" ".join(str(x) for x in [acc.get("name"), acc.get("product"),
                                                       acc.get("usage")] if x)),
            "ehdotus": (vanha or {}).get("tili") or _ehdota_tilinimi(pankki, acc),
            "tuttu": vanha is not None})
    return ulos


def tallenna_tilit_nimilla(cfg, pankki, valinnat, istunto=None):
    """Kirjoita valitut tilit config.jsoniin annetuilla nimillä.

    valinnat: [{"uid", "tili", "tunniste", "mukaan"}]. Ei kysy mitään — nimet
    on jo päätetty, ja päättäminen kuuluu käyttöliittymälle."""
    ph = cfg.setdefault("pankkihaku", {})
    ph["palvelu"] = "enablebanking"
    lista = ph.setdefault("tilit", [])
    lista[:] = [t for t in lista if not _on_paikanpitaja(t.get("account_id"))]
    vanhat_alkaen = {t.get("tili"): t.get("alkaen") for t in lista if t.get("alkaen")}
    paasy = ((istunto or {}).get("access") or {})
    uusia, nahdyt = 0, []
    for v in valinnat:
        uid, nimi = str(v.get("uid", "")), siisti(str(v.get("tili", "")))
        if not uid or not nimi or not v.get("mukaan", True):
            continue
        tunniste = siisti(str(v.get("tunniste", "")))
        vanha = (next((t for t in lista if tunniste
                       and siisti(str(t.get("tunniste", ""))) == tunniste), None)
                 or next((t for t in lista if t.get("account_id") == uid), None))
        rivi = {"tili": nimi, "account_id": uid, "tunniste": tunniste,
                "pankki": siisti(pankki)}
        if vanha is None:
            rivi["alkaen"] = _viimeinen_pvm(nimi) or vanhat_alkaen.get(nimi, "")
            lista.append(rivi)
            uusia += 1
        else:
            vanha.update(rivi)
        nahdyt.append(uid)
        paivita_pankkitila(uid, pankki=siisti(pankki), tili=nimi,
                           session_id=str((istunto or {}).get("session_id") or "") or None,
                           valtuutus_asti=str(paasy.get("valid_until") or "")[:10] or None,
                           valtuutettu=date.today().isoformat(), virhe="", virhekoodi=0)
    turvakirjoita_json(CONFIG, cfg)
    return {"uusia": uusia, "yhteensa": len(nahdyt)}


def eb_valtuuta(cfg, hakusana="", app=None):
    """Yhdistämisvelho: valitse pankki, tunnistaudu, tallenna tilit.
    Sandboxissa pankin nimeksi käy 'mock'."""
    import uuid
    tok = eb_token()
    if app is None:
        try:
            app = eb_sovellus()
        except (EBVirhe, OSError, ValueError):
            app = {}
    maa = siisti((cfg.get("pankkihaku") or {}).get("maa", "")) or "FI"
    pankit = _eb_pankit(tok, maa)
    if not pankit:
        print(f"⚠ maalle {maa} ei löytynyt pankkeja")
        return False
    a = _valitse_pankki(pankit, hakusana)
    if not a:
        return False
    redirect = _valitse_paluuosoite(app, cfg)
    # Paikallinen paluuosoite säästää osoiterivin kopioinnin, mutta kaikki
    # rajapinnan versiot eivät hyväksy http-skeemaa. Jos se torjutaan, ei
    # kaaduta siihen vaan pudotaan sovelluksen https-osoitteeseen — ja se
    # jää talteen, joten hylkäys tulee vastaan kerran eikä joka kerta.
    vaihtoehdot = [redirect]
    if _on_paikallinen(redirect):
        vaihtoehdot += [u for u in _paluuosoitteet(app)
                        if not _on_paikallinen(u)] or [EB_TESTIPALUU]
    ph = cfg.setdefault("pankkihaku", {})
    vastaus = None
    for i, redirect in enumerate(vaihtoehdot):
        try:
            vastaus = _eb_kutsu("/auth", tok, {
                "access": {"valid_until": (datetime.now().astimezone()
                                           + timedelta(days=90)).isoformat()},
                "aspsp": {"name": a["name"], "country": a.get("country", maa)},
                "psu_type": _psu_valinta(a),
                "state": str(uuid.uuid4()),
                "redirect_url": redirect})
            break
        except EBVirhe as e:
            if e.koodi == 400 and i + 1 < len(vaihtoehdot):
                print(f"ℹ paluuosoitetta {redirect} ei hyväksytty — "
                      f"käytetään osoitetta {vaihtoehdot[i + 1]}")
                continue
            vastaus = e
            break
    if isinstance(vastaus, EBVirhe):
        e = vastaus
        if e.koodi == 422 and "ASPSP" in str(e.runko).upper():
            print(f"⚠ Enable Banking ei hyväksynyt pankkivalintaa (422): {e.runko}")
            print(f"  Pankki: {a.get('name', '')} ({a.get('country', maa)}), "
                  f"tunnistautumistyypit: {', '.join(_psu_tyypit(a))}")
            print("  Yleisin syy on väärä tilityyppi (henkilö vs. yritys). "
                  "Yritä uudelleen ja vastaa tilityyppikysymykseen toisin.")
            return False
        if e.koodi == 400:
            print(f"⚠ Enable Banking hylkäsi valtuutuspyynnön (400): {e.runko}")
            print(f"  Käytetty paluuosoite: {redirect}")
            print("  Osoitteen pitää olla täsmälleen sama kuin sovelluksesi")
            print("  'Allowed redirect URLs' -listalla portaalissa. Lisää se")
            print(f"  sinne ({EB_PORTAALI}) tai vaihda osoite config.jsonista:")
            print('    "pankkihaku": { "redirect_url": "https://..." }')
            return False
        raise e
    if ph.get("redirect_url") != redirect:
        ph["redirect_url"] = redirect
    url = str(vastaus.get("url", ""))
    print(f"\nTunnistaudu pankkiisi selaimessa. Jos selain ei avaudu, "
          f"kopioi osoite:\n  {url}")
    _avaa_selain(url)
    # Paikallinen kuuntelija toimii vain http-paluuosoitteella, jota Enable
    # Banking ei hyväksy. Ehto on siis käytännössä aina epätosi — mutta se on
    # rehellisempi kuin kuuntelijan käynnistäminen osoitteelle, joka osoittaa
    # jonnekin muualle kuin tälle koneelle.
    koodi = _odota_koodi(redirect) if _on_paikallinen(redirect) else ""
    if koodi:
        print("✓ paluu napattu automaattisesti")
    else:
        koodi = _kysy_koodi(redirect)
    if not koodi:
        print("⚠ valtuutus keskeytyi")
        return False
    istunto = _eb_kutsu("/sessions", tok, {"code": koodi})
    tilit = istunto.get("accounts") or []
    if not tilit:
        print("⚠ istunto syntyi, mutta siinä ei ole yhtään tiliä.")
        print("  Tuotantosovelluksessa tämä tarkoittaa lähes aina, ettei tiliä")
        print("  ole liitetty sovellukseen. Käy portaalissa klikkaamassa")
        print(f"  'Link accounts' ja liitä kyseinen tili: {EB_PORTAALI}")
        return False
    _tallenna_tilit(cfg, a.get("name", ""), tilit, istunto)
    return True


def eb_yhdista(nimi, cfg):
    """Vanha `hae --yhdista PANKKI` -sisäänkäynti samaan velhoon."""
    eb_valtuuta(cfg, nimi)


def cmd_pankkihaku(args):
    """Yksi komento, joka vie käyttöönoton alusta loppuun."""
    cfg = lue_config()
    print("""
Rahaputken automaattinen pankkihaku
===================================
Tämän jälkeen tapahtumat tulevat pankista suoraan koneellesi ilman
CSV-vientejä. Käyttöönotto on neljä vaihetta ja vie noin 15 minuuttia.
Voit keskeyttää milloin tahansa (Ctrl-C) ja jatkaa myöhemmin samasta
komennosta — tehty ei katoa.""")
    if not _varmista_kirjastot():
        return
    if not _velho_tunnukset(pakota=getattr(args, "uusi_sovellus", False)):
        return
    app = _velho_tarkista()
    if app is None:
        return
    print("""
VAIHE 3/4 — pankkien valtuutus

Kyllä, pankki valitaan ja tunnistaudutaan toistamiseen. Vaiheet tekevät eri
asian, ja Enable Banking vaatii molemmat:

  vaihe 2 (portaalissa)  kertoo MITÄ TILEJÄ sovellus ylipäätään saa koskea
  vaihe 3 (tässä)        antaa sille LUVAN HAKEA niiltä tapahtumia

Liittäminen ei siis valtuuta hakua eikä valtuutus liitä tiliä. Tämä koskee
ilmaista, omiin tileihin rajattua tuotantosovellusta; rajoituksen poisto
vaatisi sopimuksen ja yritystaustojen tarkistuksen Enable Bankingin kanssa.

Valtuutus on voimassa pankista riippuen 90–180 päivää, ja vain se uusitaan
jatkossa — vaihetta 2 ei tarvitse toistaa.""")
    yhdistetty = False
    while True:
        try:
            yhdistetty = eb_valtuuta(cfg, "", app) or yhdistetty
        except EBVirhe as e:
            print(f"⚠ valtuutus epäonnistui ({e.koodi}): {e.runko}")
        except (OSError, ValueError) as e:
            print(f"⚠ valtuutus epäonnistui: {e}")
        except Exception as e:
            print(f"⚠ valtuutus epäonnistui odottamattomaan virheeseen: {e}")
        if not _kylla("\nYhdistetäänkö vielä toinen pankki?", oletus=False):
            break
    if not yhdistetty:
        print("\nYhtään tiliä ei tallennettu. Voit jatkaa myöhemmin komennolla:")
        print(f"  {_komentorivi()} pankkihaku")
        return
    print("""
VAIHE 4/4 — valmista

Jatkossa riittää yksi komento (tai Pankkihaku-käynnistimen kaksoisklikkaus):
tapahtumat noudetaan, luokitellaan ja raportti avautuu.""")
    if _kylla("Haetaanko tapahtumat heti ja avataan raportti?"):
        args.palvelu = "enablebanking"
        args.ei_velhoa = True
        cmd_hae(args)
        cmd_aja(args)



def nouda_tapahtumat(palvelu, account_id, cfg, paivia=89, tili_alkaen=""):
    if palvelu == "mock":
        polku = LEDGER.parent / "mock_pankki" / f"{account_id}.json"
        if polku.exists():
            with open(polku, encoding="utf-8") as f:
                return json.load(f)
        # Sisäänrakennettu demo: päivätty ennen config:n 'alkaen'-rajaa,
        # joten aja näyttää koko putken kirjaamatta riviäkään pääkirjaan.
        return {"transactions": {"booked": [
            {"bookingDate": "2025-07-10", "transactionAmount": {"amount": "-12.34", "currency": "EUR"},
             "creditorName": "DEMO KAUPPA", "remittanceInformationUnstructured": "kuivaharjoittelu"},
            {"bookingDate": "2025-07-11", "transactionAmount": {"amount": "-3.21", "currency": "EUR"},
             "creditorName": "DEMO KAHVILA", "remittanceInformationUnstructured": "kuivaharjoittelu"}]}}
    if palvelu == "gocardless":
        return gc_nouda(account_id, cfg)
    if palvelu == "enablebanking":
        return eb_nouda(account_id, cfg, paivia, tili_alkaen)
    raise ValueError(f"tuntematon palvelu '{palvelu}'")


def gc_riveiksi(data):
    """PSD2-muotoiset tapahtumat -> {pvm, summa, saaja, selite} pankin etumerkein."""
    ulos = []
    for tx in (data.get("transactions", {}).get("booked", []) or []):
        try:
            pvm = date.fromisoformat(str(tx.get("bookingDate") or tx.get("valueDate")))
            summa = round(float(tx.get("transactionAmount", {}).get("amount")), 2)
        except (TypeError, ValueError):
            continue
        saaja = siisti((tx.get("creditorName") if summa < 0 else tx.get("debtorName")) or
                       tx.get("creditorName") or tx.get("debtorName") or "")
        osat = [tx.get("remittanceInformationUnstructured", ""),
                " ".join(tx.get("remittanceInformationUnstructuredArray", []) or []),
                tx.get("additionalInformation", ""),
                tx.get("proprietaryBankTransactionCode", "")]
        selite = siisti(" ".join(str(x) for x in osat if x))
        if not saaja:
            saaja = selite[:40]
        ulos.append({"pvm": pvm, "summa": summa, "saaja": saaja, "selite": selite})
    return ulos


def kirjoita_pankkicsv(tili, rivit, polku):
    """Kirjoittaa noudetut tapahtumat CSV:ksi, jonka aja-putki lukee samoilla
    lähdemäärittelyillä kuin verkkopankista viedyt tiedostot.

    OP ja S-Pankki kirjoitetaan pankin omassa muodossa, jossa on viestikenttä.
    Revolut ja kortit käyttävät yleistä muotoa (Ostopäivä;Summa;Ostopaikka;
    Selite;Tili): Revolutin oma vientimuoto ei kanna viestiä lainkaan, ja
    juuri viestissä on usein ainoa tieto vastapuolesta."""
    puskuri = io.StringIO()
    w = csv.writer(puskuri, delimiter=";")
    if tili == "S-Pankki":
        w.writerow(["Kirjauspäivä", "Summa", "Saajan nimi", "Maksaja", "Viesti",
                    "Saajan tilinumero"])
        for r in rivit:
            w.writerow([r["pvm"].strftime("%d.%m.%Y"),
                        f"{r['summa']:.2f}".replace(".", ","),
                        r["saaja"], "", r["selite"], ""])
    elif tili == "OP-tili":
        w.writerow(["Kirjauspäivä", "Määrä EUROA", "Saaja/Maksaja", "Selitys", "Viesti",
                    "Saajan tilinumero ja pankin BIC"])
        for r in rivit:
            w.writerow([r["pvm"].strftime("%d.%m.%Y"),
                        f"{r['summa']:.2f}".replace(".", ","),
                        r["saaja"], r["selite"], "", ""])
    else:
        # Kortit, Revolut ja muut tilit: kortti_pdf-muoto, jossa on oma
        # Selite-sarake ja Tili-sarake kantaa tilin nimen pääkirjaan asti
        # (sama muoto kuin laskusta_csv kirjoittaa).
        #
        # Revolutin oma vientimuoto oli tässä aiemmin, mutta siinä ei ole
        # viestikenttää lainkaan: pankin remittance_information — usein
        # ainoa tieto vastapuolesta — katosi kokonaan matkalla pääkirjaan.
        w.writerow(["Ostopäivä", "Summa", "Ostopaikka", "Selite", "Tili"])
        for r in rivit:
            w.writerow([r["pvm"].isoformat(), f"{r['summa']:.2f}",
                        r["saaja"], r["selite"], tili])
    turvakirjoita(polku, puskuri.getvalue())


def _hae_saldo(aid, tili, raaka=False):
    """Saldo talteen. Kutsutaan vain kun käyttäjä on pyytänyt täsmäytystä.

    Palauttaa "" onnistuessaan ja virheen kuvauksen muuten. Kutsujan on
    kerrottava epäonnistuminen eteenpäin: vanha saldo jää tallessa, ja jos sen
    näyttäisi tuoreena, täsmäytys valehtelisi juuri siinä kohdassa jossa sen
    pitäisi olla luotettavin."""
    try:
        vastaus = eb_saldot(aid)
    except EBVirhe as e:
        if e.koodi == 429:
            viesti = ("pankin päivittäinen hakuraja tuli vastaan — "
                      "saldo yritetään myöhemmin uudelleen")
        else:
            viesti = f"pankki vastasi {e.koodi}"
        print(f"  ℹ {tili}: saldoa ei saatu — {viesti}")
        return viesti
    except (OSError, ValueError) as e:
        print(f"  ℹ {tili}: saldoa ei saatu — {e}")
        return str(e)
    if raaka:
        try:
            kansio = DATA / "raaka"
            kansio.mkdir(parents=True, exist_ok=True)
            turvakirjoita_json(kansio / f"saldot_{tili.replace(' ', '_')}_"
                                        f"{date.today().isoformat()}.json", vastaus)
        except (OSError, RuntimeError):
            pass
    poimittu = _poimi_saldo(vastaus)
    if not poimittu:
        print(f"  ℹ {tili}: saldovastauksesta ei löytynyt saldoa lainkaan")
        return "pankki ei palauttanut saldoa"
    paivita_pankkitila(aid, saldo_haettu=datetime.now().isoformat(timespec="seconds"),
                       **poimittu)
    tyyppi = poimittu["saldo_tyyppi"]
    lisa = "" if tyyppi.startswith(("ITBD", "CLBD")) else "  (sisältää varaukset)"
    print(f"  · {tili}: saldo {fmt_eur(poimittu['saldo'])} "
          f"{poimittu['saldo_valuutta']} ({tyyppi}){lisa}")
    return ""


def cmd_hae(args):
    cfg = lue_config()
    ph = cfg.get("pankkihaku") or {}
    palvelu = getattr(args, "palvelu", None) or ph.get("palvelu", "mock")
    if getattr(args, "istunto", None):
        try:
            eb_istunto(args.istunto)
        except (OSError, ValueError) as e:
            print(f"⚠ istunnon luku epäonnistui — {e}")
        return
    if getattr(args, "yhdista", None):
        try:
            eb_yhdista(args.yhdista, cfg)
        except (OSError, ValueError) as e:
            print(f"⚠ yhdistäminen epäonnistui — {e}")
        return
    # Mallipohjan pankkihaku-lohko näyttää asetetulta, vaikka mitään ei ole
    # vielä tehty. Käyttöönotto on tehty vasta kun on oikeita tilejä JA avain.
    tilit = [t for t in (ph.get("tilit") or []) if not _on_paikanpitaja(t.get("account_id"))]
    tunnukset = bool(_eb_asetukset()["EB_APP_ID"]) if palvelu == "enablebanking" else True
    nimenomaan_mock = "mock" in (getattr(args, "palvelu", None), ph.get("palvelu"))
    if not nimenomaan_mock and (not tilit or not tunnukset):
        # Kaksoisklikkaajan reitti velhoon: käyttöönottoa ei tarvitse tietää
        # erilliseksi komennoksi, se tarjotaan siinä missä sitä kaivataan.
        if not getattr(args, "ei_velhoa", False) and sys.stdin.isatty():
            print("Automaattista pankkihakua ei ole vielä otettu käyttöön.")
            if _kylla("Otetaanko se käyttöön nyt? (ohjattu, noin 15 min)"):
                args.ei_velhoa = True
                return cmd_pankkihaku(args)
        palvelu = "mock"
        print("Automaattista pankkihakua ei ole otettu käyttöön — "
              "alla on kuivaharjoittelu.")
        print(f"Ota se käyttöön ohjatusti: {_komentorivi()} pankkihaku\n")
    tilit = tilit or [{"tili": "OP-tili", "account_id": "mock-op"},
                      {"tili": "S-Pankki", "account_id": "mock-s"},
                      {"tili": "Revolut", "account_id": "mock-rev"}]
    INBOX.mkdir(exist_ok=True)
    yhteensa = 0
    varaukset = {}
    # Saman nimiset tilit (esim. Revolutin monta taskua) kirjoitetaan samaan
    # tiedostoon: yksi tiedosto per tilinimi, ei päällekirjoitusta.
    kertyma = {}
    for t in tilit:
        tili, aid = t.get("tili", ""), t.get("account_id", "")
        if _on_paikanpitaja(aid):
            print(f"· {tili}: mallipohjan paikanpitäjä, ohitetaan "
                  f"(oikea tunnus tulee komennosta '{_komentorivi()} pankkihaku')")
            continue
        try:
            data = nouda_tapahtumat(palvelu, aid, cfg, getattr(args, "paivia", None) or 89,
                                    t.get("alkaen", ""))
        except NotImplementedError as e:
            print(f"⚠ {tili}: {e}")
            continue
        except (OSError, ValueError) as e:
            koodi = getattr(e, "koodi", 0)
            paivita_pankkitila(aid, virhe=str(e)[:200], virhekoodi=koodi,
                               virhe_pvm=date.today().isoformat())
            print(f"⚠ {tili}: nouto epäonnistui — {e}")
            if koodi in (401, 403):
                print("  Valtuutus on todennäköisesti vanhentunut. Uusi se: "
                      f"{_komentorivi()} pankkihaku (tai raportin Pankkiyhteys-nappi).")
            continue
        if getattr(args, "raaka", False):
            raakakansio = DATA / "raaka"
            raakakansio.mkdir(parents=True, exist_ok=True)
            # Tilin tunnus mukaan nimeen: saman nimiset tilit (esim. Revolutin
            # taskut) eivät saa kirjoittaa toistensa raakadumppia yli.
            # Alkuosa on luettava, tiiviste erottaa samalta näyttävät uid:t
            # toisistaan (uid-tasku-eur / uid-tasku-sek).
            tunnus = (re.sub(r"[^A-Za-z0-9]", "", str(aid))[:8]
                      + hashlib.sha1(str(aid).encode()).hexdigest()[:4])
            rpolku = (raakakansio / f"raaka_{palvelu}_{tili.replace(' ', '_')}_"
                      f"{tunnus}_{date.today().isoformat()}.json")
            with open(rpolku, "w", encoding="utf-8") as rf:
                json.dump(data, rf, ensure_ascii=False, indent=2)
            n = len((data or {}).get("transactions", []) or [])
            print(f"  \u2699 {tili}: raaka \u2192 data/raaka/{rpolku.name} ({n} objektia)")
        paivita_pankkitila(aid, haettu=date.today().isoformat(), virhe="",
                           virhekoodi=0, tili=tili)
        if palvelu == "enablebanking" and getattr(args, "saldot", False):
            _hae_saldo(aid, tili, getattr(args, "raaka", False))
        ohitetut = Counter()
        tilin_varaukset = []
        rivit = (eb_riveiksi(data, ohitetut, tilin_varaukset)
                 if palvelu == "enablebanking" else gc_riveiksi(data))
        varaukset.setdefault(tili, []).extend(tilin_varaukset)
        for laji, teksti in (("varaus", "odottavaa veloitusta (näkyvät raportissa "
                                        "varauksina, tarkentuvat kun pankki kirjaa ne)"),
                             ("kirjautumaton", "vielä kirjautumatonta (tulevat mukaan "
                                               "seuraavassa haussa)"),
                             ("nollasumma", "rauennutta 0,00 € varausta"),
                             ("muu_valuutta", "muun valuutan kuin euron tapahtumaa "
                                              "— summat luetaan sellaisenaan, tarkista"),
                             ("tulkitsematon", "tapahtumaa joita ei voitu tulkita")):
            if ohitetut.get(laji):
                print(f"  ℹ {tili}: {ohitetut[laji]} {teksti}")
        if not rivit:
            print(f"· {tili}: ei tapahtumia")
            continue
        kertyma.setdefault(tili, []).extend(rivit)
        print(f"✓ {tili}: {len(rivit)} tapahtumaa")
        yhteensa += len(rivit)
    for tili, rivit in kertyma.items():
        polku = INBOX / f"hae_{palvelu}_{tili.replace(' ', '_')}_{date.today().isoformat()}.csv"
        kirjoita_pankkicsv(tili, sorted(rivit, key=lambda r: r["pvm"]), polku)
        print(f"  → inbox/{polku.name} ({len(rivit)} riviä)")
    if varaukset:
        kirjoita_varaukset(varaukset)
    if yhteensa:
        print("\nSeuraavaksi: python3 kirjanpito.py aja   (dedupe ohittaa jo tuodut)")


def kirjoita_varaukset(tilikohtaiset):
    """Varaukset elävät pääkirjan ulkopuolella siihen asti, että aja poimii ne.
    Tiedosto kirjoitetaan aina kokonaan uusiksi: haku on tuorein totuus."""
    DATA.mkdir(exist_ok=True)
    ulos = {"haettu": date.today().isoformat(), "tilit": {}}
    for tili, rivit in tilikohtaiset.items():
        ulos["tilit"][tili] = [{"pvm": r["pvm"].isoformat(), "summa": round(r["summa"], 2),
                                "saaja": r["saaja"], "selite": r["selite"],
                                "laji": r.get("laji", "")} for r in rivit]
    turvakirjoita_json(VARAUKSET, ulos)


def lue_varaukset():
    """Palauttaa (tilit, vanhentunut). Vanhentunut = haku on liian vanha, jolloin
    varauksiin ei voi luottaa eikä niitä pidetä yllä."""
    if not VARAUKSET.exists():
        return {}, False
    try:
        with open(VARAUKSET, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}, False
    haettu = siisti(str(data.get("haettu", "")))
    vanhentunut = True
    try:
        vanhentunut = (date.today() - date.fromisoformat(haettu)).days > VARAUS_VANHENEE_PV
    except ValueError:
        pass
    return (data.get("tilit") or {}), vanhentunut


def poista_varaukset(ledger):
    """Varausrivit pois ennen tuontia: muuten sama tapahtuma kirjautuneena
    törmäisi omaan varaukseensa dedupessa eikä päätyisi pääkirjaan."""
    poistettavat = {id(r) for r in ledger if r.get("tila") == VARAUS}
    if poistettavat:
        ledger[:] = [r for r in ledger if id(r) not in poistettavat]
    return len(poistettavat)


def tasmaa_varaukset(ledger, saannot, cfg):
    """Lisää tuoreet varausrivit pääkirjaan.

    Varaus on määritelmällisesti väliaikainen: summa, päivä ja saajan nimi
    voivat vielä muuttua, ja koko veloitus voi raueta. Siksi niitä ei
    yritetä tunnistaa yksitellen — jokainen haku kertoo, mitkä varaukset ovat
    juuri nyt voimassa, ja loput poistetaan. Kirjautuessaan tapahtuma tulee
    normaalina rivinä inboxin kautta.
    """
    tilit, vanhentunut = lue_varaukset()
    if vanhentunut:
        if tilit:
            print(f"ℹ varaustieto on yli {VARAUS_VANHENEE_PV} vrk vanhaa — "
                  "varaukset jätetään pois. Tuoreet saat komennolla 'hae'.")
        return 0
    lisatyt = 0
    for tili, rivit in tilit.items():
        for jarjestys, r in enumerate(rivit, 1):
            try:
                summa = round(float(r["summa"]), 2)
            except (TypeError, ValueError):
                continue
            pvm = siisti(str(r.get("pvm", "")))
            av = avain(tili, pvm, summa, r.get("saaja", ""))
            tulos = luokittele({"saaja": r.get("saaja", ""), "selite": r.get("selite", ""),
                                "summa": summa}, saannot, cfg.get("omat_ibanit", []))
            kategoria, peruste = tulos
            kategoria, _, tarkenne = kategoria.partition(":")
            ledger.append({
                "id": tee_id(av + "#varaus", jarjestys),
                "pvm": pvm, "tili": tili, "summa": f"{summa:.2f}",
                "saaja": r.get("saaja", ""), "selite": r.get("selite", ""),
                "kategoria": kategoria, "tarkenne": tarkenne.strip().lower(),
                "peruste": peruste, "lahde": VARAUKSET.name, "tila": VARAUS})
            lisatyt += 1
    return lisatyt


def cmd_aja(args):
    cfg = lue_config()
    saannot = lue_saannot()
    ledger = lue_ledger()
    vanhat_varaukset = poista_varaukset(ledger)
    olemassa = Counter(avain(r["tili"], r["pvm"], float(r["summa"]), r["saaja"]) for r in ledger)

    INBOX.mkdir(exist_ok=True)
    ARKISTO.mkdir(exist_ok=True)
    tiedostot = sorted(p for p in INBOX.iterdir() if p.is_file()
                       and p.suffix.lower() in (".csv", ".txt") and p.name != "LUE.txt")
    if not tiedostot:
        print(f"inbox/ on tyhjä — vie tiliotteet CSV:nä kansioon {INBOX}")
        if not ledger:
            print("Pääkirja on vielä tyhjä, joten raporttia ei ole mistä rakentaa.\n"
                  "Vie tiliotteet inbox-kansioon ja aja uudelleen.")
            return
    alkaen = siisti(cfg.get("alkaen", ""))
    uudet, tarkistettavia, varoitukset = [], 0, []
    aiemmat = Counter()  # tässä ajossa AIEMMISTA tiedostoista jo lisätyt
    for polku in tiedostot:
        try:
            nimi, rivit, var = parsi_tiedosto(polku, cfg)
        except ValueError as e:
            print(f"⚠ {e}")
            continue
        varoitukset += var
        era = Counter()
        tasta = Counter()
        lisatty = rajattu = 0
        for r in rivit:
            if alkaen and r["pvm"].isoformat() < alkaen:
                rajattu += 1
                continue
            av = avain(r["tili"], r["pvm"].isoformat(), r["summa"], r["saaja"])
            era[av] += 1
            # sama tapahtuma voi esiintyä aidosti monta kertaa samana päivänä:
            # tuodaan vain se määrä, joka ylittää jo kirjatut
            if era[av] <= olemassa[av] + aiemmat[av]:
                continue
            kategoria, peruste = luokittele(r, saannot, cfg.get("omat_ibanit", []))
            kategoria, _, tarkenne = kategoria.partition(":")
            tarkenne = tarkenne.strip().lower()
            if kategoria == "TARKISTA":
                tarkistettavia += 1
            uudet.append({
                "id": tee_id(av, era[av]),
                "pvm": r["pvm"].isoformat(),
                "tili": r["tili"],
                "summa": f"{r['summa']:.2f}",
                "saaja": r["saaja"],
                "selite": r["selite"],
                "kategoria": kategoria,
                "tarkenne": tarkenne,
                "peruste": peruste,
                "lahde": polku.name,
            })
            tasta[av] += 1
            lisatty += 1
        aiemmat.update(tasta)
        raja_info = f" · {rajattu} ennen {alkaen} jätetty pois" if rajattu else ""
        print(f"✓ {polku.name} [{nimi}]: {lisatty} uutta / {len(rivit)} riviä{raja_info}")
        shutil.move(str(polku), ARKISTO / f"{date.today().isoformat()}_{polku.name}")

    for v in varoitukset:
        print(f"⚠ {v}")
    ledger += uudet
    if alkaen:
        vanhoja = [r for r in ledger if r["pvm"] < alkaen]
        if vanhoja and getattr(args, "siivoa_alkaen", False):
            ledger[:] = [r for r in ledger if r["pvm"] >= alkaen]
            print(f"Poistettu pääkirjasta {len(vanhoja)} riviä ennen {alkaen} "
                  f"(varmuuskopio kansiossa data/varmuuskopiot).")
        elif vanhoja:
            print(f"⚠ Pääkirjassa on {len(vanhoja)} riviä ennen alkupäivää {alkaen} — "
                  f"säilytetty koskematta. Poisto vaatii: python3 kirjanpito.py aja --siivoa-alkaen")
    n_rev = _korjaa_revolut_selitteet(ledger)
    if n_rev:
        m_u, _ = uudelleenluokittele_saantorivit(ledger, cfg)
        print(f"Korjattu Revolut-selitteet {n_rev} riviltä; {m_u} luokiteltu uudelleen.")
    n_per = taydenna_perusteet(ledger, cfg)
    if n_per:
        print(f"Täydennetty luokitteluperuste {n_per} vanhalle riville.")
    n_var = tasmaa_varaukset(ledger, saannot, cfg)
    if n_var or vanhat_varaukset:
        print(f"Odottavia veloituksia {n_var} (edellisestä ajosta poistettu "
              f"{vanhat_varaukset}).")
    kirjoita_ledger(ledger)
    kirjoita_tarkistettavat(ledger)
    rakenna_raportit(ledger, cfg, kk=13)
    print(f"\nPääkirjassa {len(ledger)} tapahtumaa, uusia {len(uudet)}.")
    avoimia = sum(1 for r in ledger if r["kategoria"] == "TARKISTA")
    if avoimia:
        print(f"→ {avoimia} riviä odottaa luokittelua: täytä {TARKISTETTAVAT.relative_to(DATAJUURI)} ja aja 'opi'.")
    print(f"→ Raportti: {(RAPORTIT / 'raportti.html').relative_to(DATAJUURI)}")


def kirjoita_tarkistettavat(ledger):
    RAPORTIT.mkdir(exist_ok=True)
    # Varaukset ovat väliaikaisia: niiden luokittelu menisi hukkaan seuraavassa
    # haussa, joten niitä ei pyydetä käyttäjältä.
    rivit = [r for r in ledger if r["kategoria"] == "TARKISTA" and r.get("tila") != VARAUS]
    with open(TARKISTETTAVAT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "pvm", "tili", "summa", "saaja", "selite", "kategoria", "saanto"])
        for r in sorted(rivit, key=lambda x: x["pvm"], reverse=True):
            w.writerow([r["id"], r["pvm"], r["tili"], r["summa"], r["saaja"], r["selite"], "", ""])


def cmd_opi(args):
    cfg = lue_config()
    kategoriat = set(cfg["kategoriat"])
    if not TARKISTETTAVAT.exists():
        print("Ei tarkistettavat.csv-tiedostoa — aja ensin 'aja'.")
        return
    ledger = lue_ledger()
    idx = {r["id"]: r for r in ledger}
    paivitetty, uusia_saantoja, virheet = 0, 0, []
    kat_haku = {k.lower(): k for k in kategoriat}
    teksti_t, _ = lue_teksti(TARKISTETTAVAT)
    t_rivit = teksti_t.splitlines()
    erotin_t = ";" if (t_rivit and t_rivit[0].count(";") >= t_rivit[0].count(",")) else ","
    taytettyja = 0
    for rivi in csv.DictReader(t_rivit, delimiter=erotin_t):
            raaka_kat = siisti(rivi.get("kategoria", ""))
            if not raaka_kat:
                continue
            taytettyja += 1
            # "Pääkategoria;tarkenne" tai "Pääkategoria:tarkenne" -> kaksi tasoa
            for erotin in (";", ":"):
                if erotin in raaka_kat:
                    paa, tarkenne = (osa.strip() for osa in raaka_kat.split(erotin, 1))
                    break
            else:
                paa, tarkenne = raaka_kat, ""
            kat = kat_haku.get(paa.lower())
            if not kat:
                virheet.append(f"tuntematon kategoria '{paa}' (rivi {rivi['id']}) — lisää config.json:iin tai korjaa")
                continue
            if rivi["id"] in idx:
                idx[rivi["id"]]["kategoria"] = kat
                idx[rivi["id"]]["tarkenne"] = tarkenne.lower()
                idx[rivi["id"]]["peruste"] = "käsin"
                paivitetty += 1
            malli = normalisoi(rivi.get("saanto", ""))
            if malli:
                if lisaa_saanto(malli, kat + (f":{tarkenne.lower()}" if tarkenne else "")):
                    uusia_saantoja += 1
    # uudet säännöt kiinni myös muihin vielä avoimiin riveihin
    saannot = lue_saannot()
    for r in ledger:
        if r["kategoria"] == "TARKISTA":
            uusi, per = luokittele({"saaja": r["saaja"], "selite": r["selite"], "iban": "",
                                    "summa": float(r["summa"])},
                                   saannot, cfg.get("omat_ibanit", []))
            if uusi != "TARKISTA":
                r["kategoria"], _, r["tarkenne"] = uusi.partition(":")
                r["tarkenne"] = r["tarkenne"].strip().lower()
                r["peruste"] = per
                paivitetty += 1
    if getattr(args, "oletus", None):
        kat = siisti(args.oletus)
        if kat not in kategoriat:
            print(f"⚠ tuntematon oletuskategoria '{kat}' — ei niputettu")
        else:
            n = sum(1 for r in ledger if r["kategoria"] == "TARKISTA")
            for r in ledger:
                if r["kategoria"] == "TARKISTA":
                    r["kategoria"] = kat
                    r["peruste"] = "oletus"
            print(f"Niputettu {n} jäljellä ollutta riviä kategoriaan {kat}.")
    # raportin tiedostotilassa lataamat muutokset (myös Downloads-kansiosta)
    kat_haku2 = {k.lower(): k for k in kategoriat}
    for kansio in (RAPORTIT, DATAJUURI, Path.home() / "Downloads"):
        try:
            loydot = sorted(kansio.glob("muutokset*.csv"))
        except OSError:
            continue
        for polku_m in loydot:
            if ".kasitelty" in polku_m.name:
                continue
            teksti_m, _ = lue_teksti(polku_m)
            n_m, n_s = 0, 0
            for rivi in csv.DictReader(teksti_m.splitlines(), delimiter=";"):
                kat = kat_haku2.get(siisti(rivi.get("kategoria", "")).lower())
                if not kat and siisti(rivi.get("toiminto", "")).lower() != "poista":
                    continue
                tarkenne = siisti(rivi.get("tarkenne", ""))
                malli = normalisoi(rivi.get("malli", ""))
                rid = siisti(rivi.get("id", ""))
                toiminto = siisti(rivi.get("toiminto", "")).lower()
                if toiminto == "poista" and malli:
                    n_s += poista_saanto(malli, siisti(rivi.get("kategoria", "")))
                    print(f"  − sääntö poistettu: {malli}")
                elif rid and rid in idx:
                    idx[rid]["kategoria"] = kat
                    idx[rid]["tarkenne"] = tarkenne.lower()
                    idx[rid]["peruste"] = "käsin"
                    n_m += 1
                elif malli:
                    if lisaa_saanto(malli, kat + (f":{tarkenne.lower()}" if tarkenne else "")):
                        n_s += 1
            paivitetty += n_m
            uusia_saantoja += n_s
            uusi_nimi = polku_m.with_name(polku_m.stem + ".kasitelty.csv")
            try:
                os.replace(polku_m, uusi_nimi)
            except OSError:
                pass
            print(f"✓ {polku_m} luettu: {n_m} riviä, {n_s} sääntöä (→ {uusi_nimi.name})")
    n_rev = _korjaa_revolut_selitteet(ledger)
    if uusia_saantoja or n_rev:
        m_u, m_a = uudelleenluokittele_saantorivit(ledger, cfg)
        paivitetty += m_u
        if m_u:
            print(f"Sääntö-/selitemuutosten myötä {m_u} riviä luokiteltu uudelleen ({m_a} palasi avoimeksi).")
    taydenna_perusteet(ledger, cfg)
    kirjoita_ledger(ledger)
    kirjoita_tarkistettavat(ledger)
    rakenna_raportit(ledger, cfg, kk=13)
    for v in virheet:
        print(f"⚠ {v}")
    if taytettyja == 0:
        print("Huom: tarkistettavat.csv:ssä ei ollut yhtään täytettyä kategoria-solua — "
              "jos juuri täytit sen, varmista että tallensit muutokset (kansioon raportit/).")
    print(f"Päivitetty {paivitetty} riviä, lisätty {uusia_saantoja} uutta sääntöä.")
    avoimia = sum(1 for r in ledger if r["kategoria"] == "TARKISTA")
    print(f"Luokittelematta enää {avoimia} riviä." if avoimia else "Kaikki luokiteltu. ✓")


def _liukuva3(arvot):
    """Jälkijättöinen 3 kk liukuva keskiarvo; kaksi ensimmäistä pistettä None."""
    return [None if i < 2 else (arvot[i] + arvot[i - 1] + arvot[i - 2]) / 3
            for i in range(len(arvot))]


def _trendi3(arvot):
    """(viim. 3 kk ka) - (edeltävän 3 kk ka), tai None jos dataa alle 6 kk."""
    if len(arvot) < 6:
        return None
    return sum(arvot[-3:]) / 3 - sum(arvot[-6:-3]) / 3


def _spark(arvot):
    """Pieni inline-käyrä: kk-pylväät + 3 kk liukuvan keskiarvon viiva."""
    if not arvot or max(abs(a) for a in arvot) == 0:
        return ""
    W, H, POHJA = 150, 34, 30
    lev = W / len(arvot)
    maksimi = max(abs(a) for a in arvot)
    osat = []
    for i, a in enumerate(arvot):
        h = max(a, 0) / maksimi * (POHJA - 3)
        osat.append(f'<rect x="{i * lev + lev * 0.15:.1f}" y="{POHJA - h:.1f}" '
                    f'width="{lev * 0.7:.1f}" height="{h:.1f}" fill="#d8cfc0"/>')
    pisteet = " ".join(f"{i * lev + lev / 2:.1f},{POHJA - max(v, 0) / maksimi * (POHJA - 3):.1f}"
                       for i, v in enumerate(_liukuva3(arvot)) if v is not None)
    if pisteet:
        osat.append(f'<polyline points="{pisteet}" fill="none" stroke="#26241f" stroke-width="1.6"/>')
    return f'<svg viewBox="0 0 {W} {H}">' + "".join(osat) + "</svg>"


def _korjaa_revolut_selitteet(ledger):
    """Poista jäsentimen aiemmin lisäämä 'Revolut '-etuliite selitteistä —
    se sai revolut→Siirto-säännön nielemään kaiken Revolut-kulutuksen."""
    n = 0
    for r in ledger:
        if r.get("tili") == "Revolut" and r.get("selite", "").startswith("Revolut "):
            r["selite"] = r["selite"][len("Revolut "):]
            n += 1
    return n


def taydenna_perusteet(ledger, cfg):
    """Päättele peruste riveille, joilta se puuttuu: jos nykyiset säännöt
    tuottaisivat saman luokan, merkitään säännöllä tehdyksi; muuten käsin."""
    saannot = lue_saannot()
    n = 0
    for r in ledger:
        if r.get("peruste") or r["kategoria"] == "TARKISTA":
            continue
        u, per = luokittele({"saaja": r["saaja"], "selite": r["selite"], "iban": "",
                             "summa": float(r["summa"])}, saannot, cfg.get("omat_ibanit", []))
        paa, _, tark = u.partition(":")
        if paa == r["kategoria"] and (not tark or tark.strip().lower() == r.get("tarkenne", "")):
            r["peruste"] = per
        else:
            r["peruste"] = "käsin"
        n += 1
    return n


def sovella_avoimiin(ledger, cfg):
    """Luokittele TARKISTA-rivit uudelleen nykyisillä säännöillä. Palauttaa määrän."""
    saannot = lue_saannot()
    n = 0
    for r in ledger:
        if r["kategoria"] == "TARKISTA":
            u, per = luokittele({"saaja": r["saaja"], "selite": r["selite"], "iban": "",
                                 "summa": float(r["summa"])}, saannot, cfg.get("omat_ibanit", []))
            if u != "TARKISTA":
                r["kategoria"], _, r["tarkenne"] = u.partition(":")
                r["tarkenne"] = r["tarkenne"].strip().lower()
                r["peruste"] = per
                n += 1
    return n


def _saanto_tuple(malli, kategoria, ehto=""):
    m = normalisoi(malli)
    if m.startswith("re:"):
        return ("re", re.compile(m[3:], re.IGNORECASE), kategoria, ehto, m)
    return ("osa", m, kategoria, ehto, m)


def laske_osumat(ledger, malli, ehto=""):
    """Montako riviä malli matchaa tässä muodossaan (+ enintään 3 esimerkkiä)."""
    t = _saanto_tuple(malli, "x", ehto)
    osuu, esim = 0, []
    for r in ledger:
        teksti = normalisoi(f"{r['saaja']} {r['selite']}")
        osuiko = t[1].search(teksti) if t[0] == "re" else (t[1] in teksti)
        if osuiko and _ehto_ok(t[3], float(r["summa"])):
            osuu += 1
            if len(esim) < 3:
                esim.append((r["saaja"] or r["selite"])[:30])
    return osuu, esim


def saanto_vaikutus(ledger, cfg, malli, kategoria_full, ehto="", poistaen=None):
    """Esikatselu uudelle säännölle: mihin osuisi, mikä muuttuisi, mitkä vanhat
    säännöt estävät sen vaikutuksen. poistaen = säännöt, jotka simuloidaan
    poistetuiksi ennen uuden lisäystä. Ei kirjoita mitään."""
    poistaen = poistaen or []

    def _pois(t):
        for p in poistaen:
            if (normalisoi(p.get("malli", "")) == t[4]
                    and (not siisti(p.get("kategoria", ""))
                         or siisti(p.get("kategoria", "")).lower() == t[2].lower())):
                return True
        return False

    pohja = [t for t in lue_saannot() if not _pois(t)]
    t0 = _saanto_tuple(malli, kategoria_full, ehto)
    testi = (t0[0], t0[1], t0[2], t0[3], "__uusi__")  # tunnistelippu simulaatioon
    kohta = _sijoituskohta([t[4] for t in pohja], malli)
    saannot = (pohja + [testi]) if kohta is None else (pohja[:kohta] + [testi] + pohja[kohta:])
    kat_haku = {t[4]: t[2] for t in reversed(pohja)}
    osuu = muuttuu = avoimia = suojattu = kasin_voisi = 0
    esim_laskuri = Counter()
    kasin_esim = []
    estajat = Counter()
    for r in ledger:
        teksti = normalisoi(f"{r['saaja']} {r['selite']}")
        osuiko = testi[1].search(teksti) if testi[0] == "re" else (testi[1] in teksti)
        if osuiko and ehto:
            try:
                osuiko = _ehto_ok(ehto, float(r["summa"]))
            except (TypeError, ValueError):
                pass
        if not osuiko:
            continue
        osuu += 1
        per = r.get("peruste", "")
        u, p2 = luokittele({"saaja": r["saaja"], "selite": r["selite"], "iban": "",
                            "summa": float(r["summa"])}, saannot, cfg.get("omat_ibanit", []))
        paa, _, tark = u.partition(":")
        tark = tark.strip().lower()
        if per in ("käsin", "oletus", "oma tili"):
            suojattu += 1
            if (per != "oma tili" and p2 == "sääntö: __uusi__"
                    and (paa != r["kategoria"] or tark != r.get("tarkenne", ""))):
                kasin_voisi += 1
                if len(kasin_esim) < 3:
                    kasin_esim.append(f"{(r['saaja'] or r['selite'])[:28]}: {r['kategoria']} → "
                                      f"{paa}{(':' + tark) if tark else ''}")
            continue
        if paa != r["kategoria"] or tark != r.get("tarkenne", ""):
            muuttuu += 1
            if r["kategoria"] == "TARKISTA":
                avoimia += 1
            if p2.startswith("sääntö: ") and p2 != "sääntö: __uusi__":
                estajat[p2[len("sääntö: "):]] += 1
            esim = (f"{(r['saaja'] or r['selite'])[:30]}: {r['kategoria']} → "
                    f"{paa}{(':' + tark) if tark else ''}")
            esim_laskuri[esim] += 1
        elif p2.startswith("sääntö: ") and p2 != "sääntö: __uusi__":
            estajat[p2[len("sääntö: "):]] += 1
    est_lista = [{"malli": m, "kategoria": kat_haku.get(m, ""), "rivit": n}
                 for m, n in estajat.most_common(6)]
    esimerkit = [(e if n == 1 else f"{e} (×{n})")
                 for e, n in esim_laskuri.most_common(4)]
    return {"osuu": osuu, "muuttuu": muuttuu, "avoimia": avoimia,
            "suojattu": suojattu, "esimerkit": esimerkit, "estajat": est_lista,
            "kasin_voisi": kasin_voisi, "kasin_esim": kasin_esim}


def uudelleenluokittele_saantorivit(ledger, cfg, vain_peruste=None, pakota_saannolle=None):
    """Aja säännöt uudelleen sääntöperusteisille ja avoimille riveille.
    Käsin-, oletus- ja oma tili -rivejä ei kosketa. vain_peruste rajaa
    poistetun säännön riveihin. Palauttaa (muuttui, avoimeksi)."""
    saannot = lue_saannot()
    muuttui = avoimeksi = 0
    for r in ledger:
        per = r.get("peruste", "")
        kasin_tila = per in ("käsin", "oletus")
        if vain_peruste is not None:
            if per != vain_peruste:
                continue
        elif per == "oma tili" or (kasin_tila and not pakota_saannolle):
            continue
        u, p2 = luokittele({"saaja": r["saaja"], "selite": r["selite"], "iban": "",
                            "summa": float(r["summa"])}, saannot, cfg.get("omat_ibanit", []))
        if kasin_tila and vain_peruste is None and p2 != f"sääntö: {pakota_saannolle}":
            continue  # käsin siirtyy vain jos JUURI uusi sääntö voittaa
        paa, _, tark = u.partition(":")
        tark = tark.strip().lower()
        if paa == r["kategoria"] and tark == r.get("tarkenne", ""):
            if u != "TARKISTA":
                r["peruste"] = p2  # sama luokka, mahdollisesti eri sääntö
            continue
        r["kategoria"], r["tarkenne"], r["peruste"] = paa, tark, (p2 if paa != "TARKISTA" else "")
        muuttui += 1
        if paa == "TARKISTA":
            avoimeksi += 1
    return muuttui, avoimeksi


def lue_kertyvat():
    """Kertyvät erät budjetti.csv:stä: vuosilaskut, matkat, isot hankinnat.

    Sarakkeet: kategoria;kk_raami;tavoite;erapaiva;kertynyt. Rivi on kertyvä
    erä silloin kun sillä on tavoite. Kuukausiraami jää tyhjäksi, koska erä ei
    ole kuukausikulu vaan kertyy kohti kertasummaa:

        Autovakuutus;;969;2027-04-01;240

    Raha ei liiku minnekään — tämä on korvamerkintä, ja kertynyt-sarake on
    käsin ylläpidetty. Jos pidät summan omalla tilillä tai pocketissa, kirjaa
    sen saldo siihen.

    Erillinen nimi on tarkoituksella: varaus (lue_varaukset) on pankin
    odottava veloitus, joka on jo tapahtunut mutta ei vielä kirjautunut.
    Kertyvä erä on päinvastainen — tulevaa menoa varten sivuun pantava summa,
    jota mikään pankki ei tiedä."""
    ulos = []
    if not BUDJETTI.exists():
        return ulos
    teksti, _ = lue_teksti(BUDJETTI)
    for rivi in csv.DictReader(teksti.splitlines(), delimiter=";"):
        nimi = siisti(str(rivi.get("kategoria", "") or ""))
        try:
            tavoite = parsi_summa(siisti(str(rivi.get("tavoite", "") or "")))
        except ValueError:
            continue
        if not nimi or tavoite <= 0:
            continue
        try:
            kertynyt = parsi_summa(siisti(str(rivi.get("kertynyt", "") or "0")))
        except ValueError:
            kertynyt = 0.0
        ulos.append({"nimi": nimi, "tavoite": tavoite, "kertynyt": max(0.0, kertynyt),
                     "erapaiva": siisti(str(rivi.get("erapaiva", "") or ""))})
    return ulos


def kertyva_laske(k, tanaan=None):
    """Erän tila: paljonko puuttuu, montako kuukautta eräpäivään ja mikä on
    kuukausisiirto, jolla tavoite ehtii täyttyä."""
    tanaan = tanaan or date.today()
    puuttuu = max(0.0, k["tavoite"] - k["kertynyt"])
    kk, erap = None, None
    if k.get("erapaiva"):
        try:
            erap = date.fromisoformat(k["erapaiva"])
            kk = (erap.year - tanaan.year) * 12 + (erap.month - tanaan.month)
        except ValueError:
            erap = None
    kk_jaljella = max(1, kk) if kk is not None else None
    return {"puuttuu": puuttuu, "kk_jaljella": kk_jaljella,
            "per_kk": puuttuu / kk_jaljella if kk_jaljella else None,
            "osuus": (k["kertynyt"] / k["tavoite"]) if k["tavoite"] else 0.0,
            "erap": erap, "myohassa": kk is not None and kk < 0}


def lue_budjetti():
    raamit = {}
    if BUDJETTI.exists():
        teksti, _ = lue_teksti(BUDJETTI)
        if True:
            for rivi in csv.DictReader(teksti.splitlines(), delimiter=";"):
                arvo = siisti(rivi.get("kk_raami", ""))
                if arvo:
                    try:
                        raamit[siisti(rivi["kategoria"])] = parsi_summa(arvo)
                    except ValueError:
                        pass
    return raamit


def koosta(ledger, cfg):
    """Palauttaa (kuukaudet, taulu[kategoria][kk], tulot[kk], menot[kk])."""
    tyypit = cfg["kategoriat"]
    taulu = defaultdict(lambda: defaultdict(float))
    tulot, menot = defaultdict(float), defaultdict(float)
    for r in ledger:
        kk = r["pvm"][:7]
        kat = r["kategoria"]
        summa = float(r["summa"])
        tyyppi = tyypit.get(kat, "meno")
        if tyyppi == "pois":
            continue
        if tyyppi == "tulo":
            taulu[kat][kk] += summa
            tulot[kk] += summa
        else:
            taulu[kat][kk] += -summa  # menot positiivisina
            menot[kk] += -summa
    kuukaudet = sorted(set(list(tulot) + list(menot)))
    return kuukaudet, taulu, tulot, menot


def _oly_polku():
    uusi = LEDGER.parent / "yhteistalous.json"
    vanha = LEDGER.parent / "olympos.json"
    if vanha.exists() and not uusi.exists():
        try:
            vanha.rename(uusi)
        except OSError:
            return vanha
    return uusi


def lue_olympos():
    pohja = {"jasenet": [{"nimi": "Jäsen 1", "haku": []},
                         {"nimi": "Jäsen 2", "haku": []}],
             "pankkiiri": "Jäsen 1",
             "kategoria": "Yhteistalous",
             "viikkojako": ["ruokaboksi"],
             "palautustarkenteet": ["palautus", "yhteiskulupalautus"],
             "tasattu": "",
             "hyvitykset": [], "lasna": {}, "kirjaukset": []}
    p = _oly_polku()
    if not p.exists():
        return pohja
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return pohja
    for k, v in pohja.items():
        data.setdefault(k, v)
    return data


def kirjoita_olympos(data):
    varmuuskopioi(_oly_polku())
    turvakirjoita_json(_oly_polku(), data)


def olympos_laskelma(ledger, oly, tanaan=None, alku_yli=None):
    """Kotitalouden reskontra: boksi viikoittain läsnäolijoille, netti tasan,
    palautukset siirtoina jäseneltä pankkiirille, kk-hyvitykset saldosiirtoina."""
    tanaan = tanaan or date.today()
    try:
        alku = date.fromisoformat(str(alku_yli or oly.get("tasattu", "")))
    except ValueError:
        alku = date(2000, 1, 1)
    jasenet = oly.get("jasenet", [])
    nimet = [j["nimi"] for j in jasenet]
    n = max(len(nimet), 1)
    pankkiiri = oly.get("pankkiiri", nimet[0] if nimet else "")
    lasna = oly.get("lasna", {})

    def vkavain(p):
        iso = p.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    def lasnaolijat(vk):
        m = lasna.get(vk, {})
        ulos = [nm for nm in nimet if m.get(nm, 1)]
        return ulos or list(nimet)

    osuus = {nm: 0.0 for nm in nimet}
    boksi_osuus = {nm: 0.0 for nm in nimet}
    maksettu = {nm: 0.0 for nm in nimet}
    viikot = {}
    boksi_yht = palautus_yht = 0.0
    jaetut = {}
    oly_kat = siisti(str(oly.get("kategoria", "") or ""))
    viikkotark = {siisti(str(x)).lower() for x in oly.get("viikkojako", ["ruokaboksi"])
                  if siisti(str(x))}
    palautustark = {siisti(str(x)).lower() for x in
                    oly.get("palautustarkenteet", ["palautus", "yhteiskulupalautus"])
                    if siisti(str(x))}

    poimitut = []
    poissuljetut_rivit = []
    poisjoukko = {str(x) for x in oly.get("poissuljetut", [])}

    def _rid(r):
        return str(r.get("id") or avain(r.get("tili", ""), r.get("pvm", ""),
                                        float(r.get("summa", 0) or 0), r.get("saaja", "")))

    def viikkojako(p, m, kuvaus="", rid=""):
        # Ruokaboksi veloittaa 2-5 pv ennen maanantaitoimitusta; kulu kuuluu
        # toimitusviikolle eli maksua seuraavalle maanantaille.
        siirto = (8 - p.isoweekday()) % 7 or 7
        vk = vkavain(p + timedelta(days=siirto))
        lo = lasnaolijat(vk)
        for nm in lo:
            osuus[nm] += m / len(lo)
            boksi_osuus[nm] += m / len(lo)
        if pankkiiri in maksettu:
            maksettu[pankkiiri] += m
        viikot.setdefault(vk, {"boksi": 0.0})["boksi"] += m
        poimitut.append({"pvm": p.isoformat(), "kuvaus": kuvaus, "summa": m,
                         "tyyppi": "boksi", "vk": vk, "rid": rid})
        return m

    def tasajako(m, tark, pvm="", kuvaus="", rid=""):
        for nm in nimet:
            osuus[nm] += m / n
        if pankkiiri in maksettu:
            maksettu[pankkiiri] += m
        jaetut[tark or "(muu)"] = jaetut.get(tark or "(muu)", 0.0) + m
        poimitut.append({"pvm": pvm, "kuvaus": kuvaus, "summa": m,
                         "tyyppi": tark or "(muu)", "rid": rid})

    for r in ledger:
        try:
            p = date.fromisoformat(r.get("pvm", ""))
            s = float(r.get("summa", ""))
        except ValueError:
            continue
        if p <= alku or p > tanaan:
            continue
        teksti = normalisoi(f"{r.get('saaja', '')} {r.get('selite', '')}")
        tark = siisti(r.get("tarkenne", "")).lower()
        omassa = bool(oly_kat) and r.get("kategoria") == oly_kat
        on_palautus = s > 0 and (tark in palautustark
                                 or (not omassa and r.get("kategoria") == "Henkil\u00f6maksut"))
        on_boksi = (not on_palautus) and ((omassa and tark in viikkotark)
                                          or "ruokaboksi" in teksti or tark == "ruokaboksi")
        on_tasan = (not on_palautus and not on_boksi) and (omassa or tark == "netti")
        if not (on_palautus or on_boksi or on_tasan):
            continue
        rid = _rid(r)
        if rid in poisjoukko:
            poissuljetut_rivit.append({"pvm": p.isoformat(), "kuvaus": r.get("saaja", ""),
                                       "summa": s,
                                       "tyyppi": ("palautus" if on_palautus else
                                                  "boksi" if on_boksi else (tark or "(muu)")),
                                       "rid": rid})
            continue
        if on_palautus:
            for j in jasenet:
                if j["nimi"] == pankkiiri:
                    continue
                if any(normalisoi(h) in teksti for h in j.get("haku", []) if h):
                    maksettu[j["nimi"]] += s
                    if pankkiiri in maksettu:
                        maksettu[pankkiiri] -= s
                    palautus_yht += s
                    poimitut.append({"pvm": p.isoformat(), "kuvaus": r.get("saaja", ""),
                                     "summa": s, "tyyppi": "palautus", "jasen": j["nimi"], "rid": rid})
                    break
            continue
        if on_boksi:
            boksi_yht += viikkojako(p, -s, r.get("saaja", ""), rid)
        elif on_tasan:
            tasajako(-s, tark, p.isoformat(), r.get("saaja", ""), rid)
    for k in oly.get("kirjaukset", []):
        try:
            p = date.fromisoformat(str(k.get("pvm", "")))
            s = float(k.get("summa", 0) or 0)
        except ValueError:
            continue
        if p <= alku or p > tanaan or s <= 0:
            continue
        osallistujat = [x for x in (k.get("osallistujat") or []) if x in nimet]
        if osallistujat:
            lo = osallistujat
        elif k.get("jako") == "lasna":
            lo = lasnaolijat(vkavain(p))
        else:
            lo = list(nimet)
        for nm in lo:
            osuus[nm] += s / max(len(lo), 1)
        poimitut.append({"pvm": str(k.get("pvm", "")), "kuvaus": k.get("kuvaus", ""),
                         "summa": s, "tyyppi": "kirjaus",
                         "jasen": k.get("maksaja", ""), "jako": ", ".join(lo)})
        mk = k.get("maksaja", "")
        if mk in maksettu:
            maksettu[mk] += s
    velka = {nm: osuus[nm] - maksettu[nm] for nm in nimet}
    kk_lkm = max(0, (tanaan.year - alku.year) * 12 + tanaan.month - alku.month)
    for h in oly.get("hyvitykset", []):
        kk_h = kk_lkm
        try:
            mx = int(h.get("kk_max") or 0)
        except (TypeError, ValueError):
            mx = 0
        if mx > 0:
            kk_h = min(kk_lkm, mx)
        s = float(h.get("summa_kk", 0) or 0) * kk_h
        ja = h.get("jasenelta", "")
        if not s or ja not in velka or n < 2:
            continue
        velka[ja] += s
        for nm in nimet:
            if nm != ja:
                velka[nm] -= s / (n - 1)
    vk_lista = set(viikot)
    p = alku + timedelta(days=1)
    p = p - timedelta(days=p.isocalendar()[2] - 1)
    loppu = tanaan + timedelta(days=21)
    while p <= loppu:
        vk_lista.add(vkavain(p))
        p += timedelta(days=7)
    return {"alku": alku.isoformat(), "loppu": tanaan.isoformat(), "kk": kk_lkm,
            "nimet": nimet, "pankkiiri": pankkiiri,
            "osuus": osuus, "maksettu": maksettu, "velka": velka,
            "viikot": viikot, "vk_lista": sorted(vk_lista),
            "boksi_yht": boksi_yht, "boksi_osuus": boksi_osuus,
            "jaetut": jaetut, "tasan_yht": sum(jaetut.values()),
            "palautus_yht": palautus_yht, "kategoria": oly_kat,
            "viikkojako": sorted(viikkotark), "palautustarkenteet": sorted(palautustark),
            "poimitut": sorted(poimitut, key=lambda x: x.get("pvm", "")),
            "poissuljetut_rivit": sorted(poissuljetut_rivit, key=lambda x: x.get("pvm", ""))}


def olympos_erittely_html(ledger):
    """Itsenäinen, tulostusystävällinen erittely (selaimesta: tulosta → PDF)."""
    oly = lue_olympos()
    L = olympos_laskelma(ledger, oly)
    e = html.escape

    def eur2(v):
        return f"{v:,.2f}".replace(",", " ").replace(".", ",")

    def viikkovali(vk):
        try:
            ma = date.fromisocalendar(int(vk[:4]), int(vk[6:]), 1)
            su = ma + timedelta(days=6)
            if ma.month == su.month:
                return f"{ma.day}.–{su.day}.{su.month}.{su.year}"
            return f"{ma.day}.{ma.month}.–{su.day}.{su.month}.{su.year}"
        except ValueError:
            return vk

    # Valinnainen paikallinen taustakuva: raportit/tausta.(jpg|jpeg|png|webp)
    tausta = ""
    for nimi in ("tausta.jpg", "tausta.jpeg", "tausta.png", "tausta.webp"):
        if (RAPORTIT / nimi).exists():
            tausta = nimi
            break
    otsikko = (siisti(str(oly.get("otsikko", "")))
               or siisti(str(oly.get("kategoria", ""))) or "Yhteistalous")
    if tausta:
        banneri = (f'<div class="banneri" style="background-image:url(\'{e(tausta)}\')">'
                   f'<div class="bannerivarjo"><h1>{e(otsikko)}</h1>'
                   f'<p class="bannerimeta">jaettujen kulujen erittely · {e(L["alku"])} → {e(L["loppu"])}</p>'
                   f'</div></div>')
    else:
        banneri = (f'<h1>{e(otsikko)} — jaettujen kulujen erittely</h1>')
    o = ['<!DOCTYPE html><html lang="fi"><head><meta charset="utf-8">',
         f'<title>{e(otsikko)}-erittely {e(L["alku"])} – {e(L["loppu"])}</title>',
         '<style>body{font:13px/1.45 Georgia,serif;color:#26241f;max-width:52rem;'
         'margin:2rem auto;padding:0 1rem}h1{font-size:1.4rem}h2{font-size:1.05rem;'
         'margin:1.6rem 0 .4rem;border-bottom:1px solid #c9c3b8}table{border-collapse:'
         'collapse;width:100%}td,th{padding:.18rem .5rem;text-align:left;border-bottom:'
         '1px solid #eee7db}.num{text-align:right;font-variant-numeric:tabular-nums}'
         '.pieni{color:#7a7466;font-size:.85em}'
         '.banneri{background-size:cover;background-position:center;border-radius:8px;'
         'overflow:hidden;margin-bottom:1rem}.bannerivarjo{background:linear-gradient('
         'transparent,rgba(0,0,0,.55));padding:5rem 1.2rem 1rem;color:#fff}'
         '.banneri h1{margin:0;text-shadow:0 1px 4px rgba(0,0,0,.6)}'
         '.bannerimeta{margin:.2rem 0 0;color:#f0ece4;font-size:.9em}'
         '@media print{body{margin:0;max-width:none}a{display:none}'
         '.banneri{-webkit-print-color-adjust:exact;print-color-adjust:exact}}'
         '</style></head><body>',
         banneri,
         f'<p class="pieni">Kausi {e(L["alku"])} → {e(L["loppu"])} · jäsenet: '
         f'{e(", ".join(L["nimet"]))} · pankkiiri: {e(L["pankkiiri"])} · '
         f'tulostettu {date.today().isoformat()}</p>']
    o.append('<h2>Saldot</h2><table><tr><th>jäsen</th><th class="num">osuus</th>'
             '<th class="num">maksanut</th><th class="num">saldo</th></tr>')
    for nm in L["nimet"]:
        o.append(f'<tr><td>{e(nm)}</td><td class="num">{eur2(L["osuus"][nm])}</td>'
                 f'<td class="num">{eur2(L["maksettu"][nm])}</td>'
                 f'<td class="num"><b>{eur2(L["velka"][nm])}</b></td></tr>')
    o.append('</table>')
    # Toimenpiteet: kuka maksaa pankkiirille ja mihin tiliin (tilit oly.jasenet[].tili)
    pankkiiri = L["pankkiiri"]
    tili_map = {}
    for j in oly.get("jasenet", []):
        t = siisti(str(j.get("tili", "")))
        if t:
            tili_map[j.get("nimi", "")] = t
    toimet = []
    for nm in L["nimet"]:
        v = L["velka"][nm]
        if nm == pankkiiri or abs(v) <= 0.005:
            continue
        if v > 0:
            kohde = tili_map.get(pankkiiri, "")
            kohde_txt = f' tilille {e(kohde)}' if kohde else ""
            toimet.append(f'<li><b>{e(nm)}</b> maksaa <b>{eur2(v)} €</b> '
                          f'{e(pankkiiri)}lle{kohde_txt}.</li>')
        else:
            kohde = tili_map.get(nm, "")
            kohde_txt = f' tilille {e(kohde)}' if kohde else ""
            toimet.append(f'<li><b>{e(pankkiiri)}</b> palauttaa <b>{eur2(-v)} €</b> '
                          f'{e(nm)}lle{kohde_txt}.</li>')
    o.append('<h2>Toimenpiteet</h2>')
    if toimet:
        o.append('<ul>' + "".join(toimet) + '</ul>')
        puuttuu = [nm for nm in L["nimet"] if nm != pankkiiri
                   and abs(L["velka"][nm]) > 0.005 and nm not in tili_map and L["velka"][nm] < 0]
        if pankkiiri not in tili_map and any(L["velka"][nm] > 0.005 for nm in L["nimet"] if nm != pankkiiri):
            o.append(f'<p class="pieni">Lisää maksutili {e(pankkiiri)}lle '
                     f'(data/yhteistalous.json → jasenet[].tili), niin se näkyy tässä.</p>')
    else:
        o.append('<p class="pieni">Kaikki tasan — ei siirrettävää.</p>')
    boksit = [x for x in L["poimitut"] if x["tyyppi"] == "boksi"]
    if boksit:
        o.append(f'<h2>Boksi viikoittain — yht. {eur2(L["boksi_yht"])} €</h2>'
                 '<table><tr><th>viikko</th><th>pvm</th><th>kuvaus</th>'
                 '<th>läsnä</th><th class="num">€</th><th class="num">€/osallinen</th></tr>')
        lasna = oly.get("lasna", {})
        for x in boksit:
            lo = [nm for nm in L["nimet"] if lasna.get(x["vk"], {}).get(nm, 1)] or L["nimet"]
            o.append(f'<tr><td>{e(viikkovali(x["vk"]))}</td>'
                     f'<td>{e(x["pvm"])}</td><td>{e(str(x["kuvaus"]))}</td>'
                     f'<td class="pieni">{e(", ".join(lo))}</td>'
                     f'<td class="num">{eur2(x["summa"])}</td>'
                     f'<td class="num">{eur2(x["summa"] / len(lo))}</td></tr>')
        o.append('</table>')
        o.append('<table style="width:auto;margin-top:.6rem"><tr><th>Yhteensä €</th>'
                 + "".join(f'<th class="num">{e(nm)}</th>' for nm in L["nimet"])
                 + '<th class="num">yht.</th></tr><tr><td class="pieni">koko kausi, läsnäolo huomioitu</td>'
                 + "".join(f'<td class="num"><b>{eur2(L["boksi_osuus"][nm])}</b></td>' for nm in L["nimet"])
                 + f'<td class="num"><b>{eur2(L["boksi_yht"])}</b></td></tr></table>')
    if oly.get("hyvitykset"):
        o.append('<h2>Vakiot (kk-hyvitykset)</h2><table><tr><th>kuvaus</th>'
                 '<th>jäseneltä</th><th class="num">€/kk</th><th class="num">kk</th>'
                 '<th class="num">yht.</th></tr>')
        for h in oly["hyvitykset"]:
            s_kk = float(h.get("summa_kk", 0) or 0)
            try:
                mx = int(h.get("kk_max") or 0)
            except (TypeError, ValueError):
                mx = 0
            kk_h = min(L["kk"], mx) if mx > 0 else L["kk"]
            o.append(f'<tr><td>{e(str(h.get("kuvaus", "")))}</td>'
                     f'<td>{e(str(h.get("jasenelta", "")))}</td>'
                     f'<td class="num">{eur2(s_kk)}</td><td class="num">{kk_h}</td>'
                     f'<td class="num">{eur2(s_kk * kk_h)}</td></tr>')
        o.append('</table>')
    tasan = [x for x in L["poimitut"] if x["tyyppi"] not in ("boksi", "palautus", "kirjaus")]
    if tasan:
        o.append(f'<h2>Tasan jaetut — yht. {eur2(L["tasan_yht"])} €</h2>'
                 '<table><tr><th>pvm</th><th>kuvaus</th><th>tarkenne</th>'
                 '<th class="num">€</th><th class="num">€/osallinen</th></tr>')
        n = max(len(L["nimet"]), 1)
        for x in tasan:
            o.append(f'<tr><td>{e(str(x["pvm"]))}</td><td>{e(str(x["kuvaus"]))}</td>'
                     f'<td>{e(str(x["tyyppi"]))}</td><td class="num">{eur2(x["summa"])}</td>'
                     f'<td class="num">{eur2(x["summa"] / n)}</td></tr>')
        o.append('</table>')
    kirj = [x for x in L["poimitut"] if x["tyyppi"] == "kirjaus"]
    if kirj:
        o.append('<h2>Käsikirjaukset</h2><table><tr><th>pvm</th><th>kuvaus</th>'
                 '<th>maksaja</th><th>jaetaan</th><th class="num">€</th>'
                 '<th class="num">€/osallinen</th></tr>')
        for x in kirj:
            jako = str(x.get("jako", ""))
            m = len([t for t in jako.split(",") if t.strip()]) or 1
            o.append(f'<tr><td>{e(str(x["pvm"]))}</td><td>{e(str(x["kuvaus"]))}</td>'
                     f'<td>{e(str(x.get("jasen", "")))}</td><td class="pieni">{e(jako)}</td>'
                     f'<td class="num">{eur2(x["summa"])}</td>'
                     f'<td class="num">{eur2(x["summa"] / m)}</td></tr>')
        o.append('</table>')
    pal = [x for x in L["poimitut"] if x["tyyppi"] == "palautus"]
    if pal:
        o.append(f'<h2>Palautukset pankkiirille — yht. {eur2(L["palautus_yht"])} €</h2>'
                 '<table><tr><th>pvm</th><th>jäsen</th><th>kuvaus</th><th class="num">€</th></tr>')
        for x in pal:
            o.append(f'<tr><td>{e(str(x["pvm"]))}</td><td>{e(str(x.get("jasen", "")))}</td>'
                     f'<td>{e(str(x["kuvaus"]))}</td><td class="num">{eur2(x["summa"])}</td></tr>')
        o.append('</table>')
    o.append('</body></html>')
    return "".join(o)


def olympos_osio(ledger, cfg=None):
    oly = lue_olympos()
    n_alku = siisti(str(oly.get("nayta_alku", "")))
    n_loppu = siisti(str(oly.get("nayta_loppu", "")))
    tan = None
    try:
        tan = date.fromisoformat(n_loppu) if n_loppu else None
    except ValueError:
        tan = None
    L = olympos_laskelma(ledger, oly, tanaan=tan, alku_yli=(n_alku or None))
    e = html.escape

    def eur2(v):
        return f"{v:,.2f}".replace(",", " ").replace(".", ",")

    nimet, pankkiiri, lasna = L["nimet"], L["pankkiiri"], oly.get("lasna", {})
    maksaja_optiot = "".join(f"<option>{e(nm)}</option>" for nm in nimet)
    rt = ['<table><tr><th>pvm</th><th>kuvaus</th><th>tyyppi</th><th class="num">€</th><th></th></tr>']
    for x in L["poimitut"]:
        if x["tyyppi"] == "palautus" or not x.get("rid"):
            continue
        rt.append(f'<tr><td>{e(str(x["pvm"]))}</td><td>{e(str(x["kuvaus"]))}</td>'
                  f'<td>{e(str(x["tyyppi"]))}</td><td class="num">{eur2(abs(x["summa"]))}</td>'
                  f'<td><a href="#" class="olpoissulje" data-rid="{e(str(x["rid"]))}">sulje pois</a></td></tr>')
    for x in L.get("poissuljetut_rivit", []):
        rt.append(f'<tr style="opacity:.5"><td>{e(str(x["pvm"]))}</td>'
                  f'<td><s>{e(str(x["kuvaus"]))}</s></td><td>{e(str(x["tyyppi"]))}</td>'
                  f'<td class="num">{eur2(abs(x["summa"]))}</td>'
                  f'<td><a href="#" class="olotamukaan" data-rid="{e(str(x["rid"]))}">ota mukaan</a></td></tr>')
    if len(rt) == 1:
        rt.append('<tr><td colspan="5" class="pikkuteksti">ei poimittuja rivejä</td></tr>')
    rt.append("</table>")
    rivitaulu = "".join(rt)
    st = ['<table><tr><th>jäsen</th><th class="num">osuus kuluista</th>'
          '<th class="num">maksanut</th><th class="num">saldo</th><th></th></tr>']
    for nm in nimet:
        v = L["velka"][nm]
        if abs(v) <= 0.005:
            sanoitus = "tasan"
        elif nm == pankkiiri:
            sanoitus = "saatavaa muilta" if v < 0 else "velkaa yhteisölle"
        else:
            sanoitus = f"maksettava {pankkiiri}lle" if v > 0 else "etukäteen maksettua"
        st.append(f'<tr><td>{e(nm)}</td><td class="num">{eur2(L["osuus"][nm])}</td>'
                  f'<td class="num">{eur2(L["maksettu"][nm])}</td>'
                  f'<td class="num"><b>{eur2(v)}</b></td><td class="pikkuteksti">{sanoitus}</td></tr>')
    st.append("</table>")
    n_j = max(len(nimet), 1)
    vt = ['<table><tr><th>kuvaus</th><th>jäseneltä</th><th class="num">€/kk</th>'
          '<th class="num">kk</th><th class="num">yht. kaudella</th>'
          '<th class="num">muille / jäsen</th><th></th></tr>']
    for i, h in enumerate(oly.get("hyvitykset", [])):
        s_kk = float(h.get("summa_kk", 0) or 0)
        try:
            mx = int(h.get("kk_max") or 0)
        except (TypeError, ValueError):
            mx = 0
        kk_h = min(L["kk"], mx) if mx > 0 else L["kk"]
        kk_n = f'{kk_h}{f" / {mx}" if mx > 0 else ""}'
        yht_h = s_kk * kk_h
        per_muu = yht_h / (n_j - 1) if n_j > 1 else 0.0
        muut = [nm for nm in nimet if nm != siisti(str(h.get("jasenelta", "")))]
        selite = (" · ".join(f"{e(nm)} +{eur2(per_muu)}" for nm in muut)) if muut else "—"
        vt.append(f'<tr><td>{e(str(h.get("kuvaus", "")))}</td><td>{e(str(h.get("jasenelta", "")))}</td>'
                  f'<td class="num">{eur2(s_kk)}</td><td class="num">{kk_n}</td>'
                  f'<td class="num">{eur2(yht_h)}</td>'
                  f'<td class="num">{eur2(per_muu)} <span class="pikkuteksti">{selite}</span></td>'
                  f'<td><a href="#" class="olvakiopoisto" data-i="{i}">poista</a></td></tr>')
    if len(vt) == 1:
        vt.append('<tr><td colspan="7" class="pikkuteksti">ei vakioita</td></tr>')
    vt.append("</table>")
    lt = ['<table><tr><th>viikko</th>'] + [f"<th>{e(nm)}</th>" for nm in nimet]
    lt.append('<th class="num">boksi €</th><th class="num">€/läsnäolija</th></tr>')
    for vk in L["vk_lista"]:
        raw = lasna.get(vk, {})
        lo = [nm for nm in nimet if raw.get(nm, 1)] or nimet
        solut = ""
        for nm in nimet:
            a = 1 if raw.get(nm, 1) else 0
            merkki = "✓" if a else "–"
            solut += (f'<td class="olpres" data-vk="{e(vk)}" data-nimi="{e(nm)}" data-arvo="{a}" '
                      f'style="cursor:pointer;text-align:center">{merkki}</td>')
        try:
            ma = date.fromisocalendar(int(vk[:4]), int(vk[6:]), 1)
            su = ma + timedelta(days=6)
            if ma.month == su.month:
                vali = f"{ma.day}.–{su.day}.{su.month}.{su.year}"
            else:
                vali = f"{ma.day}.{ma.month}.–{su.day}.{su.month}.{su.year}"
            nimio = e(vali)
        except ValueError:
            nimio = e(vk)
        b = L["viikot"].get(vk, {}).get("boksi", 0.0)
        lt.append(f'<tr><td>{nimio}</td>{solut}<td class="num">{eur2(b) if b else ""}</td>'
                  f'<td class="num">{eur2(b / len(lo)) if b else ""}</td></tr>')
    if L["boksi_yht"]:
        summat = "".join(f'<td class="num"><b>{eur2(L["boksi_osuus"][nm])}</b></td>' for nm in nimet)
        lt.append(f'<tr><td><b>Yhteensä €</b></td>{summat}'
                  f'<td class="num"><b>{eur2(L["boksi_yht"])}</b></td><td></td></tr>')
    lt.append("</table>")
    kt = ['<table><tr><th>pvm</th><th>kuvaus</th><th>maksaja</th><th class="num">€</th><th>jaetaan</th><th class="num">€/osallinen</th><th></th></tr>']
    for i, k in enumerate(oly.get("kirjaukset", [])):
        merkinta = ""
        try:
            if date.fromisoformat(str(k.get("pvm", ""))) <= date.fromisoformat(L["alku"]):
                merkinta = ' <span class="pikkuteksti">(ennen kautta)</span>'
        except ValueError:
            pass
        k_summa = float(k.get("summa", 0) or 0)
        osall = [x for x in (k.get("osallistujat") or []) if x in nimet]
        if osall:
            m_jako = len(osall)
        elif k.get("jako") == "lasna":
            try:
                pk = date.fromisoformat(str(k.get("pvm", "")))
                iso = pk.isocalendar()
                vkey = f"{iso[0]}-W{iso[1]:02d}"
                raw = oly.get("lasna", {}).get(vkey, {})
                m_jako = len([nm for nm in nimet if raw.get(nm, 1)]) or len(nimet)
            except ValueError:
                m_jako = len(nimet)
        else:
            m_jako = max(len(nimet), 1)
        per = eur2(k_summa / m_jako) if m_jako else ""
        kt.append(f'<tr><td>{e(str(k.get("pvm", "")))}{merkinta}</td><td>{e(str(k.get("kuvaus", "")))}</td>'
                  f'<td>{e(str(k.get("maksaja", "")))}</td><td class="num">{eur2(k_summa)}</td>'
                  f'<td>{e(", ".join(k.get("osallistujat") or []) or ("läsnäviikko" if k.get("jako") == "lasna" else "kaikki"))}</td>'
                  f'<td class="num">{per}</td>'
                  f'<td><a href="#" class="olpoisto" data-i="{i}">poista</a></td></tr>')
    if len(kt) == 1:
        kt.append('<tr><td colspan="7" class="pikkuteksti">ei kirjauksia</td></tr>')
    kt.append("</table>")
    osallistujaruudut = "".join(f'<label style="margin-right:.5rem"><input type="checkbox" '
                                f'class="ol-osall" value="{e(nm)}" checked> {e(nm)}</label>'
                                for nm in nimet)
    jaot = " + ".join(f"{e(t)} {eur2(v)}" for t, v in
                      sorted(L["jaetut"].items(), key=lambda x: -abs(x[1]))) or "—"
    nykyinen = L["kategoria"]
    if cfg:
        optiot = [f'<option value=""{"" if nykyinen else " selected"}>— ei käytössä —</option>']
        loytyi = False
        for k in sorted(cfg.get("kategoriat", {}), key=str.lower):
            sel = " selected" if k == nykyinen else ""
            loytyi = loytyi or bool(sel)
            optiot.append(f"<option{sel}>{e(k)}</option>")
        if nykyinen and not loytyi:
            optiot.append(f"<option selected>{e(nykyinen)}</option>")
        optiot.append('<option value="__uusi__">+ uusi kategoria…</option>')
        katvalinta = f'<select id="ol-kat">{"".join(optiot)}</select>'
        puuttuu = ("" if (not nykyinen or loytyi) else
                   ' <span class="pikkuteksti">⚠ kategoriaa ei vielä ole pääkirjassa — '
                   "rivit poimitaan toistaiseksi vain vanhoilla tunnisteilla</span>")
    else:
        katvalinta = f'"{e(nykyinen)}"'
        puuttuu = ""
    vihje = "" if L["boksi_yht"] else ('<p class="pikkuteksti">⚠ Kaudelta ei löytynyt Ruokaboksi-rivejä '
                                      "pääkirjasta — tarkista kauden alkupäivä.</p>")
    otsikko = (siisti(str(oly.get("otsikko", "")))
               or siisti(str(oly.get("kategoria", ""))) or "Yhteistalous")
    return (f'<details id="yhteistalous"><summary><h2 style="display:inline">{e(otsikko)} \u2014 jaettujen kulujen reskontra '
            f'({e(L["alku"])} →)</h2></summary><div class="pkortti">'
            f'<p class="pikkuteksti"><a href="yhteistalous_erittely.html" target="_blank" '
            f'rel="noopener" style="font-size:1.05em">🖨 Avaa tulostettava erittely uuteen '
            f'välilehteen</a> — selaimen tulostuksesta (⌘P) saat PDF:n. '
            f'Taustakuva: pudota kuva tiedostoksi raportit/tausta.jpg</p>'
            f'<p class="pikkuteksti">Kausi {e(L["alku"])} → {e(L["loppu"])} · boksi {eur2(L["boksi_yht"])} € '
            f'· tasan jaetut: {jaot} · palautukset {eur2(L["palautus_yht"])} €</p>'
            f'<p class="pikkuteksti">Näytettävä nimi: '
            f'<input id="ol-otsikko" size="16" value="{e(otsikko)}" '
            f'title="näkyy raportin ja erittelyn otsikossa"> '
            f'(tyhjä = poimintakategorian nimi)</p>'
            f'<p class="pikkuteksti">Poiminta pääkirjasta: kategorian {katvalinta} rivit{puuttuu} — '
            f'<input id="ol-viikkotark" size="14" value="{e(", ".join(L["viikkojako"]))}" '
            f'title="pilkuin eroteltuna"> jaetaan läsnäoloviikon mukaan, '
            f'<input id="ol-palautustark" size="24" value="{e(", ".join(L["palautustarkenteet"]))}" '
            f'title="pilkuin eroteltuna"> ovat jäsenten maksuja pankkiirille, '
            f'muut tarkenteet (netti, sähkö, …) jaetaan tasan. Ruokaboksi tunnistetaan lisäksi '
            f'nimestä kategoriasta riippumatta. Asetukset: data/yhteistalous.json.</p>'
            f'{vihje}<h3>Saldot</h3>{"".join(st)}'
            f'<h3>Läsnäolo viikoittain</h3><p class="pikkuteksti">Klikkaa solua: ✓ läsnä / – poissa. '
            f'Viikon boksi jaetaan läsnäolijoiden kesken (jos kaikki poissa, jaetaan kaikille).</p>{"".join(lt)}'
            f'<h3>Vakiot (kk-hyvitykset)</h3>'
            f'<p class="pikkuteksti">Jäsenen saldoa veloitetaan summa joka kuukausi ja muille '
            f'hyvitetään tasan — esim. autolataus: Ville korvaa yhteisölle sähköstä. '
            f'Kaudella {L["kk"]} kk.</p>{"".join(vt)}'
            f'<p>uusi vakio: <input id="ol-vk-kuvaus" placeholder="kuvaus" size="14"> '
            f'<select id="ol-vk-jasen">{maksaja_optiot}</select> '
            f'<input id="ol-vk-summa" placeholder="€/kk" size="6"> '
            f'<input id="ol-vk-kk" placeholder="kk (tyhjä = rajaton)" size="12"> '
            f'<button id="ol-vk-lisaa">lisää vakio</button></p>'
            f'<h3>Kirjaukset</h3><p class="pikkuteksti">Yhteiskulut, jotka joku maksoi omasta pussistaan '
            f'(esim. puutarhuri).</p>{"".join(kt)}'
            f'<h3>Poimitut rivit</h3><p class="pikkuteksti">Nämä rivit luetaan pääkirjasta jakoon. '
            f'Jos jokin kuuluu eri kaudelle (esim. tasauspäivän jälkeen veloittunut edellisen '
            f'kuun lasku), sulje se pois — se ei tuolloin vaikuta saldoihin.</p>{rivitaulu}'
            f'<p>uusi: <input type="date" id="ol-pvm" value="{date.today().isoformat()}"> '
            f'<input id="ol-kuvaus" placeholder="kuvaus" size="18"> '
            f'<select id="ol-maksaja">{maksaja_optiot}</select> '
            f'<input id="ol-summa" placeholder="summa" size="7"> '
            f'jaetaan: {osallistujaruudut} '
            f'<button id="ol-lisaa">lisää kirjaus</button></p>'
            f'<p>Tarkastelujakso: <input type="date" id="ol-nayta-alku" value="{e(L["alku"])}"> – '
            f'<input type="date" id="ol-nayta-loppu" value="{e(L["loppu"])}"> '
            f'<button id="ol-nayta">näytä jakso</button> '
            f'<span class="pikkuteksti">— rajaa laskennan valituille päiville (ei muuta tasausta). '
            f'Tyhjä alku = viimeisin tasaus, tyhjä loppu = tänään.</span></p>'
            f'<p>Uusi tasaus: <input type="date" id="ol-tasattu" value="{e(L["loppu"])}"> '
            f'<button id="ol-tasaa">aloita uusi kausi tästä päivästä</button> '
            f'<span class="pikkuteksti">— nollaa laskennan; paina kun rahat on siirretty.</span></p>'
            f"</div></details>")


def pankkiyhteydet_html(cfg):
    """Taulukko pankkiyhteyksien tilasta ja varoitusrivi, jos jokin kaipaa
    huomiota.

    Ilman tätä "ei tapahtumia" ja "yhteys katkennut" näyttävät samalta:
    molemmissa raportti vain lakkaa täyttymästä. Valtuutus vanhenee pankista
    riippuen 90–180 päivän välein, eikä siitä varoita kukaan.

    Sarakkeet on nimetty sen mukaan mitä niissä oikeasti on: "haettu" ilman
    kohdetta oli epäselvä, koska tapahtumat ja saldo haetaan eri hetkinä ja
    eri syistä."""
    tilit = ((cfg.get("pankkihaku") or {}).get("tilit") or [])
    tila = lue_pankkitila()
    if not tilit or not tila:
        return "", ""
    rivit, varoitukset = [], []
    for indeksi, t in enumerate(tilit):
        aid = str(t.get("account_id", ""))
        if _on_paikanpitaja(aid):
            continue
        tt = tila.get(aid, {})
        nimi = t.get("tili", "") or tt.get("tili", "")
        pankki = str(tt.get("pankki", "") or t.get("pankki", ""))

        # --- valtuutus ---
        paivia = _paivia_jaljella(tt.get("valtuutus_asti"))
        uusittava = False
        if tt.get("virhekoodi") in (401, 403):
            valtuutus, valt_luokka, uusittava = "ei kelpaa", "huono", True
        elif paivia is None:
            valtuutus, valt_luokka = "ei tiedossa", ""
        elif paivia < 0:
            valtuutus, valt_luokka, uusittava = f"vanhentui {tt['valtuutus_asti']}", "huono", True
        elif paivia <= 14:
            valtuutus, valt_luokka, uusittava = f"{paivia} pv jäljellä", "huono", True
        else:
            valtuutus, valt_luokka = f"{paivia} pv ({tt['valtuutus_asti']})", ""
        if uusittava:
            varoitukset.append(f"{nimi}: valtuutus {valtuutus}")
            valtuutus += (f' <a href="velho?pankki={html.escape(pankki, quote=True)}"'
                          f' class="uusilinkki">uusi</a>')

        # --- saldo ---
        saldo = tt.get("saldo")
        if isinstance(saldo, (int, float)):
            valuutta = str(tt.get("saldo_valuutta", "")) or "EUR"
            merkki = "€" if valuutta == "EUR" else html.escape(valuutta)
            # Varauksellinen saldo ei ole vertailukelpoinen kirjattujen rivien
            # kanssa; tähti kertoo sen siinä missä luku näkyy.
            tahti = "" if _vertailukelpoinen(tt.get("saldo_tyyppi")) else " *"
            saldoteksti = f'{fmt_eur(saldo)} {merkki}{tahti}'
            saldo_pvm = str(tt.get("saldo_haettu", ""))[:10] or "—"
        else:
            saldoteksti, saldo_pvm = "—", "—"

        # --- täsmäytys ---
        ero = tt.get("ankkuri_ero")
        if not isinstance(tt.get("ankkuri_saldo"), (int, float)):
            tasm, tasm_luokka = "ei täsmäytetty", ""
        elif ero:
            tasm, tasm_luokka = f'ero {fmt_eur(ero)} €', "huono"
        else:
            tasm, tasm_luokka = f'täsmäsi {tt.get("tasmaytetty", "")}', ""

        rivit.append(
            f'<tr data-tili-idx="{indeksi}">'
            f'<td>{html.escape(str(nimi))}</td>'
            f'<td>{html.escape(pankki)}</td>'
            f'<td>{html.escape(str(tt.get("haettu", "—")))}</td>'
            f'<td class="num">{saldoteksti}</td>'
            f'<td>{html.escape(saldo_pvm)}</td>'
            f'<td class="{valt_luokka}">{valtuutus}</td>'
            f'<td class="{tasm_luokka}">{html.escape(tasm)}'
            f'<button type="button" class="tasmnappi" hidden>Täsmäytä</button></td></tr>')
    if not rivit:
        return "", ""
    taulu = ('<h2>Pankkiyhteydet</h2>\n<div style="overflow-x:auto"><table>'
             '<tr><th>Tili</th><th>Pankki</th><th>Tapahtumat haettu</th>'
             '<th class="num">Saldo pankissa</th><th>Saldo haettu</th>'
             '<th>Valtuutus voimassa</th><th>Täsmäytys</th></tr>'
             + "".join(rivit) + '</table></div>\n'
             '<p class="pikkuteksti">Tapahtumat haetaan Hae pankkitapahtumat '
             '-napista, saldo vain Täsmäytä-napista — kumpikin kuluttaa yhden '
             'pankin neljästä vuorokausihausta. Täsmäytys vertaa saldoa '
             'kirjanpitoon ankkurista: hyväksytystä saldosta ja sen hetken '
             'pääkirjan summasta, jolloin jälkikäteen ilmestyvät takautuvat '
             'tapahtumat siirtävät odotusta oikein. Tähdellä (*) merkitty saldo '
             'sisältää odottavat korttivaraukset. Valtuutus uusitaan rivin omasta '
             '<em>uusi</em>-linkistä; uusiminen koskee koko pankkia, ei yksittäistä '
             'tiliä, eikä tilejä tarvitse liittää portaalissa uudelleen.</p>')
    varoitus = (f'<p class="huomio">⚠ Pankkiyhteys kaipaa huomiota — '
                f'{html.escape("; ".join(varoitukset))}.</p>') if varoitukset else ""
    return taulu, varoitus


def rakenna_raportit(ledger, cfg, kk=13, kirjoita_sivu=True):
    """Rakentaa raportit ja palauttaa raporttisivun HTML:n.

    kirjoita_sivu=False jättää raportti.html:n levylle kirjoittamatta. Sitä
    käyttää selaa-tila, joka rakentaa sivun joka pyynnöllä: kirjoitus tarkoittaa
    pilvikansiossa lähes megatavun latausta jokaisesta sivunlatauksesta, eikä
    kukaan lue sitä tiedostoa juuri silloin. Tiedosto syntyy ajossa (aja,
    raportti), jolloin se on olemassa myös ilman palvelinta."""
    RAPORTIT.mkdir(exist_ok=True)
    kuukaudet, taulu, tulot, menot = koosta(ledger, cfg)
    kaikki_kk = list(kuukaudet)
    if kk and len(kuukaudet) > kk:
        kuukaudet = kuukaudet[-kk:]
    tyypit = cfg["kategoriat"]
    menokat = [k for k in taulu if tyypit.get(k, "meno") == "meno"]
    menokat.sort(key=lambda k: -sum(taulu[k][m] for m in kuukaudet))
    tulokat = [k for k in taulu if tyypit.get(k) == "tulo"]
    raamit = lue_budjetti()

    # --- koko historian koonti: yhteensä + keskim./kk + keskim./v ---
    tanaan_kk = date.today().isoformat()[:7]
    taydet = [m for m in kaikki_kk if m < tanaan_kk] or list(kaikki_kk)
    n_kk = len(taydet)
    tayset = set(taydet)
    menokat_koko = sorted((kx for kx in taulu if tyypit.get(kx, "meno") == "meno"),
                          key=lambda kx: -sum(taulu[kx].values()))

    def rivi_koonti(nimi, sarja_kk, yht, tyyppi):
        arvot = [sarja_kk.get(m, 0.0) for m in taydet]
        ka = sum(arvot) / n_kk if n_kk else 0.0
        med = statistics.median(arvot) if arvot else 0.0
        delta = _trendi3(arvot)
        hyva = None if delta is None else (delta > 0 if tyyppi == "tulo" else delta < 0)
        return {"nimi": nimi, "yht": yht, "ka": ka, "kav": ka * 12, "med": med,
                "delta": delta, "hyva": hyva, "spark": _spark(arvot)}

    koonti = [rivi_koonti(kx, taulu[kx], sum(taulu[kx].values()), tyypit.get(kx, "meno"))
              for kx in menokat_koko + tulokat]
    m_yht, t_yht = sum(menot.values()), sum(tulot.values())
    saasto_kk = {m: tulot.get(m, 0.0) - menot.get(m, 0.0) for m in taydet}
    koonti_summat = [rivi_koonti("Menot yhteensä", menot, m_yht, "meno"),
                     rivi_koonti("Tulot yhteensä", tulot, t_yht, "tulo"),
                     rivi_koonti("Säästö", saasto_kk, t_yht - m_yht, "tulo")]
    jakso = (min(r["pvm"] for r in ledger), max(r["pvm"] for r in ledger)) if ledger else ("", "")
    with open(RAPORTIT / "yhteenveto_koko.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Kategoria", "Yhteensä", "Keskim./kk", "Mediaani/kk", "Keskim./v",
                    "Trendi 3kk vs ed. 3kk (€/kk)"])
        for r in koonti + koonti_summat:
            w.writerow([r["nimi"], fmt_eur(r["yht"]), fmt_eur(r["ka"]), fmt_eur(r["med"]),
                        fmt_eur(r["kav"]), "" if r["delta"] is None else f"{r['delta']:+.0f}".replace(".", ",")])

    # --- yhteenveto_kk.csv (liitä sellaisenaan Google Sheetsiin) ---
    with open(RAPORTIT / "yhteenveto_kk.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Kategoria"] + kuukaudet)
        for k in menokat:
            w.writerow([k] + [fmt_eur(taulu[k][m]) if taulu[k][m] else "" for m in kuukaudet])
        w.writerow(["MENOT YHT"] + [fmt_eur(menot[m]) for m in kuukaudet])
        for k in tulokat:
            w.writerow([k] + [fmt_eur(taulu[k][m]) if taulu[k][m] else "" for m in kuukaudet])
        w.writerow(["TULOT YHT"] + [fmt_eur(tulot[m]) for m in kuukaudet])
        w.writerow(["Säästö €"] + [fmt_eur(tulot[m] - menot[m]) for m in kuukaudet])
        w.writerow(["Säästö %"] + [f"{(tulot[m] - menot[m]) / tulot[m] * 100:.1f}".replace(".", ",")
                                   if tulot[m] > 0 else "" for m in kuukaudet])
    sivu = tee_html(cfg, kuukaudet, taulu, tulot, menot, menokat, tulokat, raamit,
                    ledger, koonti, koonti_summat, jakso, n_kk, kaikki_kk, tyypit)
    if kirjoita_sivu:
        (RAPORTIT / "raportti.html").write_text(sivu, encoding="utf-8")
    return sivu


def tee_html(cfg, kuukaudet, taulu, tulot, menot, menokat, tulokat, raamit, ledger,
             koonti, koonti_summat, jakso, n_kk, kaikki_kk, tyypit):
    e = html.escape
    tanaan = date.today().isoformat()[:7]
    taydet = [m for m in kuukaudet if m < tanaan]
    kohde = taydet[-1] if taydet else (kuukaudet[-1] if kuukaudet else None)

    # --- porautumisdata: kategoria -> kk -> [pvm, summa(näyttö), saaja, tarkenne, tili] ---
    naytto = {}
    for r in ledger:
        kat = r["kategoria"]
        ty = tyypit.get(kat, "meno")
        s = float(r["summa"])
        if ty == "pois":
            disp = round(s, 2)  # siirrot raakamerkillä: negatiivinen = rahaa lähti
        else:
            disp = round(-s if ty == "meno" else s, 2)
        teksti = r["saaja"] or r["selite"][:60]
        naytto.setdefault(kat, {}).setdefault(r["pvm"][:7], []).append(
            [r["pvm"], disp, teksti, r.get("tarkenne", "").lower(), r["tili"], r["id"],
             r.get("peruste", ""), siisti(r["selite"])[:220], r.get("tila", "")])
    for kat in naytto.values():
        for lista in kat.values():
            lista.sort(key=lambda x: x[0], reverse=True)
    data_js = json.dumps({"kk": kaikki_kk, "kat": naytto}, ensure_ascii=False,
                         separators=(",", ":")).replace("</", "<\\/")
    def _aakkoset(tyyppi):
        return sorted((k for k, ty in tyypit.items() if ty == tyyppi and k != "TARKISTA"),
                      key=str.lower)
    kat_js = json.dumps({"menot": _aakkoset("meno"), "tulot": _aakkoset("tulo"),
                         "pois": _aakkoset("pois") + ["TARKISTA"]}, ensure_ascii=False)
    tarkenteet_js = json.dumps(sorted({r.get("tarkenne", "").lower() for r in ledger} - {""}), ensure_ascii=False)
    tark_kat = {}
    for r in ledger:
        t = r.get("tarkenne", "").lower()
        if t:
            tark_kat.setdefault(r["kategoria"], set()).add(t)
    tarkkat_js = json.dumps({k: sorted(v) for k, v in tark_kat.items()}, ensure_ascii=False)
    ehdot_map = {}
    for s_ in lue_saannot_raaka():
        ehdot_map.setdefault(normalisoi(s_["malli"]), []).append(
            (s_.get("ehto", ""), s_.get("kategoria", "")))
    saantoehdot_js = json.dumps(
        {m: "; ".join((e or "ei ehtoa") + " → " + k for e, k in v)
         for m, v in ehdot_map.items() if any(e for e, _ in v)}, ensure_ascii=False)
    # Rivin §-merkistä pääsee muokkaamaan juuri sitä sääntöä, joka rivin
    # luokitteli — siihen tarvitaan mallin lisäksi kategoria ja ehto.
    saantotiedot = {}
    for s_ in lue_saannot_raaka():
        saantotiedot.setdefault(normalisoi(s_["malli"]),
                                {"malli": s_["malli"], "kategoria": s_.get("kategoria", ""),
                                 "ehto": s_.get("ehto", "")})
    saantotiedot_js = json.dumps(saantotiedot, ensure_ascii=False)

    # --- ylägraafi: tulot ja menot per kk ---
    maksimi = max([menot[m] for m in kuukaudet] + [tulot[m] for m in kuukaudet] + [1])
    W, H, POHJA = 900, 260, 220
    lev = W / max(len(kuukaudet), 1)
    palkit = []
    for i, m in enumerate(kuukaudet):
        x = i * lev
        mh = menot[m] / maksimi * (POHJA - 20)
        th = tulot[m] / maksimi * (POHJA - 20)
        palkit.append(
            f'<rect data-laji="tulot" data-kkm="{m}" style="cursor:pointer" '
            f'x="{x + lev * 0.14:.1f}" y="{POHJA - th:.1f}" width="{lev * 0.3:.1f}" height="{th:.1f}" '
            f'fill="#2e7d5b"><title>{m} tulot {fmt_eur(tulot[m])} € — klikkaa avataksesi</title></rect>'
            f'<rect data-laji="menot" data-kkm="{m}" style="cursor:pointer" '
            f'x="{x + lev * 0.5:.1f}" y="{POHJA - mh:.1f}" width="{lev * 0.3:.1f}" height="{mh:.1f}" '
            f'fill="#b3502d"><title>{m} menot {fmt_eur(menot[m])} € — klikkaa avataksesi</title></rect>'
            f'<text x="{x + lev / 2:.1f}" y="{POHJA + 16}" text-anchor="middle" class="aks">{m[5:]}/{m[2:4]}</text>'
        )
        saasto = tulot[m] - menot[m]
        if tulot[m] > 0:
            palkit.append(f'<text x="{x + lev / 2:.1f}" y="{POHJA + 32}" text-anchor="middle" '
                          f'class="aks {"plus" if saasto >= 0 else "miinus"}">{saasto / tulot[m] * 100:+.0f}%</text>')
    ma_menot = _liukuva3([menot[m] for m in kuukaudet])
    ma_pisteet = " ".join(f"{i * lev + lev * 0.65:.1f},{POHJA - v / maksimi * (POHJA - 20):.1f}"
                          for i, v in enumerate(ma_menot) if v is not None)
    ma_viiva = (f'<polyline points="{ma_pisteet}" fill="none" stroke="#26241f" stroke-width="2"/>'
                if ma_pisteet else "")
    kaavio = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Tulot ja menot kuukausittain">'
              f'<line x1="0" y1="{POHJA}" x2="{W}" y2="{POHJA}" stroke="#8a857c" stroke-width="1"/>'
              + "".join(palkit) + ma_viiva + "</svg>")

    def kat_attr(nimi, mkk=None):
        if nimi not in naytto:
            return ""
        lisa = f' data-kk="{mkk}"' if mkk else ""
        return f' class="klik" data-kat="{e(nimi)}"{lisa}'

    # --- koko historian koonti ---
    def koonti_rivi(r, luokka=""):
        if r["delta"] is None:
            trendi = '<td class="num">–</td>'
        else:
            vari = "" if r["hyva"] is None else (" plus" if r["hyva"] else " miinus")
            nuoli = "↘" if r["delta"] < -1 else ("↗" if r["delta"] > 1 else "→")
            trendi = f'<td class="num{vari}">{nuoli} {r["delta"]:+.0f}</td>'.replace(".", ",")
        attr = kat_attr(r["nimi"]) if not luokka else ""
        return (f'<tr class="{luokka}"><td{attr}>{e(r["nimi"])}</td><td class="spark">{r["spark"]}</td>'
                f'<td class="num">{fmt_eur(r["yht"])}</td><td class="num">{fmt_eur(r["ka"])}</td>'
                f'<td class="num">{fmt_eur(r["med"])}</td><td class="num">{fmt_eur(r["kav"])}</td>{trendi}</tr>')

    koonti_html = "".join(koonti_rivi(r) for r in koonti)
    koonti_html += "".join(koonti_rivi(r, "summa") for r in koonti_summat)
    t_yht_kaikki = sum(tulot.values())
    saasto_rivi = ""
    if t_yht_kaikki > 0:
        saasto_rivi = ("Säästöaste koko jaksolta " +
                       f"{(1 - sum(menot.values()) / t_yht_kaikki) * 100:.1f}".replace(".", ",") + " %. ")

    # --- kohdekuukauden budjettivertailu ---
    rivit_html = []
    if kohde:
        for k in menokat:
            tot = taulu[k][kohde]
            raami = raamit.get(k)
            if not tot and not raami:
                continue
            if raami:
                osuus = min(tot / raami, 1.5) if raami else 0
                palkki = (f'<div class="palkki"><div class="taytto {"yli" if tot > raami else ""}" '
                          f'style="width:{osuus / 1.5 * 100:.0f}%"></div><i style="left:{100 / 1.5:.1f}%"></i></div>')
                erotus = f'<td class="num {"plus" if raami - tot >= 0 else "miinus"}">{fmt_eur(raami - tot)}</td>'
                raami_s = f'<td class="num">{fmt_eur(raami)}</td>'
                pros = f'<td class="num {"miinus" if tot > raami else ""}">{tot / raami * 100:.0f} %</td>'
            else:
                palkki, erotus, raami_s = '<div class="palkki tyhja"></div>', '<td class="num">–</td>', '<td class="num">–</td>'
                pros = '<td class="num">–</td>'
            rivit_html.append(f'<tr><td{kat_attr(k, kohde)}>{e(k)}</td><td class="num">{fmt_eur(tot)}</td>{raami_s}{erotus}'
                              f'{pros}<td>{palkki}</td></tr>')

    # --- kertyvät erät: vuosilaskut ja muut kertasummat, joita säästetään kokoon ---
    kertyva_rivit = []
    for kohta in lue_kertyvat():
        tila = kertyva_laske(kohta)
        palkki = (f'<div class="palkki"><div class="taytto" '
                  f'style="width:{min(tila["osuus"], 1.0) * 100:.0f}%"></div></div>')
        if tila["per_kk"] is None:
            kk_s = '<td class="num">–</td>'
            era_s = '<td class="pikkuteksti">ei eräpäivää</td>'
        else:
            kk_s = f'<td class="num"><b>{fmt_eur(tila["per_kk"])}</b></td>'
            d = tila["erap"]
            era_txt = f"{d.day}.{d.month}.{d.year}"
            era_s = (f'<td class="miinus">{era_txt} (mennyt)</td>' if tila["myohassa"]
                     else f'<td>{era_txt} <span class="pikkuteksti">'
                          f'({tila["kk_jaljella"]} kk)</span></td>')
        kertyva_rivit.append(
            f'<tr><td>{e(kohta["nimi"])}</td><td class="num">{fmt_eur(kohta["tavoite"])}</td>'
            f'<td class="num">{fmt_eur(kohta["kertynyt"])}</td>'
            f'<td class="num">{tila["osuus"] * 100:.0f} %</td>'
            f'<td class="num">{fmt_eur(tila["puuttuu"])}</td>{kk_s}{era_s}'
            f'<td>{palkki}</td></tr>')
    kertyvat_html = ""
    if kertyva_rivit:
        kertyvat_html = (
            '<h2>Kertyvät erät <span class="pikkuteksti">(vuosilaskut, matkat, '
            'isot hankinnat)</span></h2>'
            '<div style="overflow-x:auto"><table>'
            '<tr><th>Erä</th><th>Tavoite €</th><th>Kertynyt €</th><th>%</th>'
            '<th>Puuttuu €</th><th>Siirrä €/kk</th><th>Eräpäivä</th><th></th></tr>'
            + "".join(kertyva_rivit) + '</table></div>'
            '<p class="pikkuteksti">Raha ei liiku minnekään — tämä on korvamerkintä. '
            'Siirrä €/kk kertoo, paljonko kuussa pitää panna sivuun, jotta tavoite '
            'täyttyy eräpäivään mennessä. Rivi tiedostoon asetukset/budjetti.csv: '
            '<code>kategoria;kk_raami;tavoite;erapaiva;kertynyt</code> — esimerkiksi '
            '<code>Autovakuutus;;969;2027-04-01;240</code>. Kertynyt-sarake on omissa '
            'käsissäsi: jos pidät summan omalla tilillä tai pocketissa, kirjaa sen saldo '
            'siihen. Nämä eivät ole odottavia korttivarauksia — ne näkyvät pääkirjassa '
            'omilla riveillään.</p>')

    # --- kategoriat × kuukaudet -matriisi (klikattavat solut) ---
    def matriisirivi(nimi, arvot, luokka="", klik=False):
        solut = []
        for a, mkk in zip(arvot, kuukaudet):
            attr = kat_attr(nimi, mkk) if (klik and a) else ' class="num"'
            if klik and a:
                attr = attr.replace('class="klik"', 'class="klik num"')
            solut.append(f'<td{attr}>{fmt_eur(a) if a else ""}</td>')
        nimi_attr = kat_attr(nimi) if klik else ""
        return f'<tr class="{luokka}"><td{nimi_attr}>{e(nimi)}</td>{"".join(solut)}</tr>'

    matriisi = [f'<tr><th>Kategoria</th>{"".join(f"<th>{m[5:]}/{m[2:4]}</th>" for m in kuukaudet)}</tr>']
    matriisi += [matriisirivi(k, [taulu[k][m] for m in kuukaudet], klik=True) for k in menokat]
    matriisi.append(matriisirivi("Menot yhteensä", [menot[m] for m in kuukaudet], "summa"))
    matriisi += [matriisirivi(k, [taulu[k][m] for m in kuukaudet], klik=True) for k in tulokat]
    matriisi.append(matriisirivi("Tulot yhteensä", [tulot[m] for m in kuukaudet], "summa"))
    matriisi.append(matriisirivi("Säästö €", [tulot[m] - menot[m] for m in kuukaudet], "summa"))

    saannot_raaka = lue_saannot_raaka()
    saanto_n = len(saannot_raaka)
    kaytto = Counter(r.get("peruste", "") for r in ledger)
    tekstit = [(normalisoi(f"{r['saaja']} {r['selite']}"), float(r["summa"])) for r in ledger]

    def _osumia(s):
        try:
            t = _saanto_tuple(s["malli"], "x", s["ehto"])
        except re.error:
            return "–"
        return sum(1 for tx, sm in tekstit
                   if (t[1].search(tx) if t[0] == "re" else t[1] in tx) and _ehto_ok(t[3], sm))

    olympos_html = olympos_osio(ledger, cfg)
    with open(RAPORTIT / "yhteistalous_erittely.html", "w", encoding="utf-8") as f_oe:
        f_oe.write(olympos_erittely_html(ledger))
    # Säännön tiedot kerran rivillä, ei jokaisessa linkissä: seitsemän linkkiä
    # × kolme data-attribuuttia teki 280 säännöstä 325 kilotavua, eli kolmasosan
    # koko sivusta. JS lukee ne nyt riviltä (closest('tr')).
    saannot_html = "".join(
        f'<tr class="saantorivi" data-malli="{e(s["malli"])}" '
        f'data-kategoria="{e(s["kategoria"])}" data-ehto="{e(s["ehto"])}" '
        f'data-n="{kaytto.get("sääntö: " + normalisoi(s["malli"]), 0)}">'
        f'<td class="num"><a href="#" class="saantosija" '
        f'title="klikkaa: siirrä numeroituun sijaintiin">{i}</a></td>'
        f'<td>{e(s["malli"])}</td><td>{e(s["kategoria"])}</td>'
        f'<td>{e(s["ehto"])}</td><td class="num">{_osumia(s)}</td>'
        f'<td class="num">{kaytto.get("sääntö: " + normalisoi(s["malli"]), 0) or ""}</td>'
        f'<td><a href="#" class="saantopoisto">poista</a> · '
        f'<a href="#" class="saantomuokkaus">muokkaa</a> · '
        f'<a href="#" class="saantosiirto" data-suunta="-1" title="askel ylös">↑</a>'
        f'<a href="#" class="saantosiirto" data-suunta="1" title="askel alas">↓</a>'
        f'<a href="#" class="saantosiirto" data-suunta="alkuun" title="siirrä ylimmäksi">⤒</a>'
        f'<a href="#" class="saantosiirto" data-suunta="loppuun" title="siirrä alimmaksi">⤓</a>'
        f'</td></tr>'
        for i, s in enumerate(saannot_raaka, 1))
    avoimia = sum(1 for r in ledger if r["kategoria"] == "TARKISTA")
    # --- saldot & kulukatsaus ---
    saatava_kat = list(dict.fromkeys(
        [k for k, t in tyypit.items()
         if t == "pois" and k not in ("Siirto", "Sijoitukset", "Luoton lyhennys")]
        + (["Laina"] if "Laina" in tyypit else [])))
    saldo_rivit = []
    tasatut_rivit = []
    for k in saatava_kat:
        ryhmat = defaultdict(lambda: [0.0, 0])
        for r in ledger:
            if r["kategoria"] == k:
                g = ryhmat[r.get("tarkenne", "")]
                g[0] += float(r["summa"])
                g[1] += 1
        for tark, (netto, n) in sorted(ryhmat.items()):
            nimi = f"{k} · {tark}" if tark else k
            if netto < -1:
                teksti = f"avointa saatavaa {fmt_eur(-netto)} €"
            elif netto > 1:
                teksti = f"saldo +{fmt_eur(netto)} € (saatu enemmän kuin maksettu)"
            elif n >= 2:
                tasatut_rivit.append(f'<tr><td><a href="#" class="klik" data-kat="{e(k)}">{e(nimi)}</a></td>'
                                     f'<td>✓ tasan — maksettu takaisin</td></tr>')
                continue
            else:
                continue
            saldo_rivit.append(f'<tr><td><a href="#" class="klik" data-kat="{e(k)}">{e(nimi)}</a></td>'
                               f'<td>{teksti}</td></tr>')
    def _seuraava_era(paiva):
        tanaan = date.today()
        if paiva == "loppu":
            viim = calendar.monthrange(tanaan.year, tanaan.month)[1]
            if tanaan.day <= viim:
                d = date(tanaan.year, tanaan.month, viim)
            else:
                v, k2 = (tanaan.year + 1, 1) if tanaan.month == 12 else (tanaan.year, tanaan.month + 1)
                d = date(v, k2, calendar.monthrange(v, k2)[1])
        else:
            if tanaan.day <= paiva:
                d = date(tanaan.year, tanaan.month, paiva)
            else:
                v, k2 = (tanaan.year + 1, 1) if tanaan.month == 12 else (tanaan.year, tanaan.month + 1)
                d = date(v, k2, paiva)
        return f"{d.day}.{d.month}."

    for nimi, (maksut, tuodut) in kortti_summat(ledger).items():
        ero = round(sum(maksut.values()) - sum(t[1] for t in tuodut.values()), 2)
        if ero < -5:
            spec = KORTIT_SPEC.get(nimi, {})
            era = _seuraava_era(spec.get("era_paiva", "loppu"))
            minimi = -ero * spec.get("minimi_pct", 2) / 100
            teksti = (f"avointa korttivelkaa ~{fmt_eur(-ero)} € · seuraava eräpäivä ~{era} "
                      f"(minimierä ~{fmt_eur(max(30.0, minimi))} €)")
        elif ero > 5:
            teksti = f"täsmäytysvakio +{fmt_eur(ero)} € (rajapäivä/ennakot)"
        else:
            teksti = "✓ maksut ja ostot täsmäävät"
        saldo_rivit.append(f'<tr><td>{e(nimi)} (kortti)</td><td>{teksti}</td></tr>')

    korko_kaikki = korko_viim3 = 0.0
    raja3 = sorted({r["pvm"][:7] for r in ledger})[-3:]
    for r in ledger:
        t = normalisoi(f"{r['saaja']} {r['selite']}")
        if r["tili"] in ("OP-kortti", "S-Pankki Visa") and ("korko" in t or "tilinhoito" in t):
            korko_kaikki += -float(r["summa"])
            if r["pvm"][:7] in raja3:
                korko_viim3 += -float(r["summa"])
    til_kk = defaultdict(float)
    til_saajat = Counter()
    for r in ledger:
        if r["kategoria"] == "Tilaukset & liittymät":
            til_kk[r["pvm"][:7]] += -float(r["summa"])
            til_saajat[r["saaja"][:24]] += -float(r["summa"])
    til_taso = (sum(til_kk.values()) / len(til_kk)) if til_kk else 0.0
    vinkit = []
    if korko_kaikki > 1:
        vinkit.append(f"Luottokulut (korot + tilinhoidot) yhteensä {fmt_eur(korko_kaikki)} €, "
                      f"viim. 3 kk tasolla ~{fmt_eur(korko_viim3 / 3)} €/kk — "
                      f"poistuu kokonaan kuittaamalla avoimen korttisaldon.")
    til_lkm = Counter()
    for r in ledger:
        if r["kategoria"] == "Tilaukset & liittymät":
            til_lkm[r["saaja"][:24]] += 1
    if til_taso > 1:
        isoimmat = ", ".join(f"{n} ({fmt_eur(s / max(1, len(til_kk)))} €/kk)"
                             for n, s in til_saajat.most_common(3))
        vinkit.append(f"Tilaukset & liittymät ~{fmt_eur(til_taso)} €/kk — suurimmat: {isoimmat}.")
    til_lista = ""
    if til_saajat:
        kkia = max(1, len(til_kk))
        rivit_t = []
        for n, s in til_saajat.most_common():
            krt = til_lkm[n]
            if krt >= kkia - 2 and kkia >= 4:
                kuvaus = f"{fmt_eur(s / kkia)} €/kk"
            elif krt <= 2 and s > 20:
                kuvaus = f"vuosittainen ~{fmt_eur(s)} €/v"
            else:
                kuvaus = f"{fmt_eur(s)} € / {krt} krt"
            rivit_t.append(f'<tr><td>{e(n)}</td><td class="num">{fmt_eur(s)}</td>'
                           f'<td>{kuvaus}</td></tr>')
        til_lista = (f'<details class="pikkuteksti"><summary>kaikki tilaukset '
                     f'({len(til_saajat)} kpl · {fmt_eur(sum(til_saajat.values()))} € jaksolla) '
                     f'— vuositilaukset tunnistettu rytmistä</summary>'
                     f'<table><tr><th>Saaja</th><th>Yht €</th><th>Rytmi</th></tr>'
                     + "".join(rivit_t) + '</table></details>')
    tasatut_html = ""
    if tasatut_rivit:
        tasatut_html = (f'<details class="pikkuteksti"><summary>✓ tasatut lainat ja saatavat '
                        f'({len(tasatut_rivit)})</summary><table>'
                        + "".join(tasatut_rivit) + '</table></details>')
    saldot_html = ""
    if saldo_rivit or vinkit or tasatut_rivit:
        saldot_html = ('<h2>Saldot & kulukatsaus</h2><table>'
                       '<tr><th>Kohde</th><th>Tilanne</th></tr>'
                       + "".join(saldo_rivit) + '</table>'
                       + tasatut_html
                       + "".join(f'<p class="pikkuteksti">\U0001f4a1 {v}</p>' for v in vinkit)
                       + til_lista)

    huomio = (f'<p class="huomio">⚠ {avoimia} tapahtumaa luokittelematta (kategoria TARKISTA) — '
              f'luvut tarkentuvat kun täytät tarkistettavat.csv ja ajat <code>opi</code>.</p>') if avoimia else ""
    yhteydet_html, yhteysvaroitus = pankkiyhteydet_html(cfg)
    # Ilman pankkiyhteyttä haku ei voi tehdä mitään järkevää, joten nappi on
    # pois käytöstä ja kertoo miksi. Vaihtoehto olisi nappi, joka näyttää
    # toimivalta ja tulostaa sitten kuivaharjoittelun.
    on_pankkitileja = any(not _on_paikanpitaja(t.get("account_id"))
                          for t in ((cfg.get("pankkihaku") or {}).get("tilit") or []))
    hae_pois = ("" if on_pankkitileja else
                ' disabled class="pois" title="Yhdistä ensin pankkeihin — '
                'ilman pankkiyhteyttä ei ole mistä hakea"')
    huomio = yhteysvaroitus + huomio
    varausrivit = [r for r in ledger if r.get("tila") == VARAUS]
    if varausrivit:
        v_summa = sum(-float(r["summa"]) for r in varausrivit)
        summa_txt = f"{v_summa:,.2f}".replace(",", " ").replace(".", ",")
        huomio += (f'<p class="huomio varaushuomio">⏳ {len(varausrivit)} odottavaa '
                   f'veloitusta ({summa_txt} €) on mukana luvuissa. Pankki ei ole '
                   f'vielä kirjannut niitä: summa tai päivä voi muuttua, ja veloitus voi '
                   f'myös raueta. Jokainen <code>hae</code> päivittää ne.</p>')

    skripti = """
<script>
const DATA=__DATA__;
const KAT=__KAT__;
const TARKENTEET=__TARKENTEET__;
const TARKKAT=__TARKKAT__;
const SAANTOEHDOT=__SAANTOEHDOT__;
const SAANTOTIEDOT=__SAANTOTIEDOT__;
let SF_KORVAA=null;
// ---- Tutki-graafi: kk × kategoria × tarkenne, koottu DATA.kat-riveistä ----
const TUTKI={valitut:[], varit:{}, tila:'stacked'};
const TUTKIVARIT=['#c0532b','#2e7d5b','#3a6ea5','#9a6b2f','#7d4f9c','#b5893a','#4a8a8a',
  '#a8476b','#5f7d3a','#8a5a3c','#d08a2e','#556b8d','#6b8e4e','#a05a7a','#3f7a6b','#8d6a9c'];
function tutkiVari(avain){
  if(!TUTKI.varit[avain]){
    TUTKI.varit[avain]=TUTKIVARIT[Object.keys(TUTKI.varit).length % TUTKIVARIT.length];
  }
  return TUTKI.varit[avain];
}
function tutkiSarja(avain){
  // avain = "Kategoria" tai "Kategoria \u203a tarkenne"
  const osat=avain.split(' \u203a ');
  const kat=osat[0], tark=osat.length>1?osat[1]:null;
  // Jos koko kategoria on valittu JA sen tarkenteita on erikseen valittu,
  // vähennä ne pois kategoriapalkista — muuten osa laskettaisiin kahdesti.
  let poisTark=null;
  if(tark===null){
    poisTark={};
    TUTKI.valitut.forEach(function(v){
      const o=v.split(' \u203a ');
      if(o.length>1 && o[0]===kat){ poisTark[o[1]]=1; }
    });
  }
  const perKk={};
  const kdata=(DATA.kat||{})[kat]||{};
  for(const kk in kdata){
    let summa=0;
    for(const rivi of kdata[kk]){
      const rtark=(rivi[3]||'');
      if(tark===null){
        if(poisTark[rtark]) continue;   // tämä tarkenne on jo omana sarjanaan
        summa+=Math.abs(rivi[1]);
      }else if(rtark===tark){
        summa+=Math.abs(rivi[1]);
      }
    }
    if(summa) perKk[kk]=summa;
  }
  return perKk;
}
function tutkiOnkoOsittainen(avain){
  // tosi, jos tämä on kategoria jonka tarkenteita on erikseen valittu (= "muut"-jäännös)
  if(avain.indexOf(' \u203a ')>=0) return false;
  return TUTKI.valitut.some(function(v){
    const o=v.split(' \u203a '); return o.length>1 && o[0]===avain;
  });
}
function tutkiPiirra(){
  const svgHolder=document.getElementById('tutki-svg');
  const leg=document.getElementById('tutki-legenda');
  if(!TUTKI.valitut.length){
    svgHolder.innerHTML='<p class="pikkuteksti">Valitse vasemmalta kategorioita tai tarkenteita.</p>';
    leg.innerHTML=''; return;
  }
  const kuut=DATA.kk||[];
  const sarjat=TUTKI.valitut.map(function(av){
    return {avain:av, vari:tutkiVari(av), data:tutkiSarja(av)};
  });
  // maksimi: stacked = pinon summa, grouped = yksittäinen
  let maksimi=1;
  for(const kk of kuut){
    if(TUTKI.tila==='stacked'){
      let s=0; sarjat.forEach(function(sr){s+=sr.data[kk]||0;});
      if(s>maksimi)maksimi=s;
    }else{
      sarjat.forEach(function(sr){ if((sr.data[kk]||0)>maksimi)maksimi=sr.data[kk]||0; });
    }
  }
  const W=900,H=300,POHJA=250,VASEN=4;
  const lev=(W-VASEN)/Math.max(kuut.length,1);
  let parts=['<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Kategoriat kuukausittain">'];
  parts.push('<line x1="0" y1="'+POHJA+'" x2="'+W+'" y2="'+POHJA+'" stroke="#8a857c"/>');
  kuut.forEach(function(kk,i){
    const x0=VASEN+i*lev;
    if(TUTKI.tila==='stacked'){
      let y=POHJA;
      sarjat.forEach(function(sr){
        const v=sr.data[kk]||0; if(!v)return;
        const h=v/maksimi*(POHJA-20);
        parts.push('<rect x="'+(x0+lev*0.15).toFixed(1)+'" y="'+(y-h).toFixed(1)+
          '" width="'+(lev*0.7).toFixed(1)+'" height="'+h.toFixed(1)+'" fill="'+sr.vari+
          '"><title>'+esc(kk)+' · '+esc(sr.avain)+': '+eur(v)+' \u20ac</title></rect>');
        y-=h;
      });
    }else{
      const n=sarjat.length, bw=lev*0.7/n;
      sarjat.forEach(function(sr,j){
        const v=sr.data[kk]||0; if(!v)return;
        const h=v/maksimi*(POHJA-20);
        parts.push('<rect x="'+(x0+lev*0.15+j*bw).toFixed(1)+'" y="'+(POHJA-h).toFixed(1)+
          '" width="'+(bw*0.92).toFixed(1)+'" height="'+h.toFixed(1)+'" fill="'+sr.vari+
          '"><title>'+esc(kk)+' · '+esc(sr.avain)+': '+eur(v)+' \u20ac</title></rect>');
      });
    }
    const lyhyt=kk.slice(2);
    parts.push('<text x="'+(x0+lev/2).toFixed(1)+'" y="'+(POHJA+16)+'" text-anchor="middle" '+
      'style="font-size:11px;fill:#6b6459">'+esc(lyhyt)+'</text>');
  });
  parts.push('</svg>');
  svgHolder.innerHTML=parts.join('');
  leg.innerHTML=sarjat.map(function(sr){
    const yht=Object.values(sr.data).reduce(function(a,b){return a+b;},0);
    const nimi=esc(sr.avain)+(tutkiOnkoOsittainen(sr.avain)?' <span class="pikkuteksti">(muut)</span>':'');
    return '<span><span class="tutki-lammas" style="background:'+sr.vari+'"></span>'+
      nimi+' <span class="pikkuteksti">'+eur(yht)+' \u20ac</span></span>';
  }).join('');
}
function tutkiToggle(avain){
  const i=TUTKI.valitut.indexOf(avain);
  if(i>=0){ TUTKI.valitut.splice(i,1); }
  else { TUTKI.valitut.push(avain); tutkiVari(avain); }
  tutkiPaivitaLamput(); tutkiPiirra();
}
// Päivitä vain valintalamppujen värit paikallaan (ei koko puun uudelleenrakennusta -> ei skrollihyppyä).
function tutkiPaivitaLamput(){
  const puu=document.getElementById('tutki-puu'); if(!puu)return;
  const rivit=puu.querySelectorAll('[data-tkat],[data-av]');
  for(let i=0;i<rivit.length;i++){
    const el=rivit[i];
    const av=el.getAttribute('data-av')||el.getAttribute('data-tkat');
    const lammas=el.querySelector('.tutki-lammas'); if(!lammas)continue;
    if(TUTKI.valitut.indexOf(av)>=0){
      lammas.style.background=tutkiVari(av); lammas.style.border='none';
    }else{
      lammas.style.background='transparent'; lammas.style.border='1px solid #c9c3b8';
    }
  }
}
function tutkiRakennaPuu(){
  const puu=document.getElementById('tutki-puu');
  if(!puu)return;
  const menot=(KAT.menot||[]).concat(KAT.tulot||[]);
  const tarkPerKat={};
  for(const kat in (DATA.kat||{})){
    const setti={};
    for(const kk in DATA.kat[kat]){
      for(const rivi of DATA.kat[kat][kk]){ if(rivi[3]) setti[rivi[3]]=1; }
    }
    tarkPerKat[kat]=Object.keys(setti).sort();
  }
  const auki=TUTKI._auki||(TUTKI._auki={});
  function lammas(av){
    return TUTKI.valitut.indexOf(av)>=0
      ? '<span class="tutki-lammas" style="background:'+tutkiVari(av)+'"></span>'
      : '<span class="tutki-lammas" style="background:transparent;border:1px solid #c9c3b8"></span>';
  }
  let h=[];
  menot.forEach(function(kat){
    if(!(DATA.kat||{})[kat])return;
    const tarkit=tarkPerKat[kat]||[];
    const nuoli=tarkit.length?(auki[kat]?'\\u25be':'\\u25b8'):'\\u00a0';
    h.push('<div class="tutki-katrivi" data-tkat="'+esc(kat)+'">'+
      '<span class="tutki-nuoli" data-toggle="'+esc(kat)+'">'+nuoli+'</span>'+
      lammas(kat)+'<span>'+esc(kat)+'</span></div>');
    tarkit.forEach(function(t){
      const av=kat+' \\u203a '+t;
      h.push('<div class="tutki-tark'+(auki[kat]?'':' piilossa')+'" data-av="'+esc(av)+'" '+
        'data-kat-ryhma="'+esc(kat)+'">'+lammas(av)+'<span>'+esc(t)+'</span></div>');
    });
  });
  puu.innerHTML=h.join('');
}
function tutkiAvaa(kat){
  TUTKI._auki=TUTKI._auki||{}; TUTKI._auki[kat]=!TUTKI._auki[kat];
  const auki=TUTKI._auki[kat];
  const puu=document.getElementById('tutki-puu'); if(!puu)return;
  const rivit=puu.querySelectorAll('[data-kat-ryhma]');
  for(let i=0;i<rivit.length;i++){
    if(rivit[i].getAttribute('data-kat-ryhma')!==kat)continue;
    if(auki)rivit[i].classList.remove('piilossa'); else rivit[i].classList.add('piilossa');
  }
  const nuolet=puu.querySelectorAll('.tutki-nuoli');
  for(let i=0;i<nuolet.length;i++){
    if(nuolet[i].getAttribute('data-toggle')===kat){ nuolet[i].textContent=auki?'\\u25be':'\\u25b8'; }
  }
}
let SERVER=false;
const MUUT={rivit:{},saannot:[],poistot:[]};
const PSP=['klarna','paytrail','trustly','zettle','sumup','vfi*','ptl*','mob.pay','vipps','mobilepay','epassi','nyx*','adyen','stripe'];
function eur(x){return x.toLocaleString('fi-FI',{minimumFractionDigits:2,maximumFractionDigits:2});}
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function sulje(){
  document.getElementById('paneeli').style.display='none';
  if(PANEELI&&PANEELI.haku){
    const k=document.getElementById('haku');
    if(k){k.value='';}
  }
  PANEELI=null;
}
let MUOKKAUS=null;
let PANEELI=null;
let VALINTA=[];
let ANKKURI=null;
function soveltaKasin(id,kat,tark){
  const s=etsiTuple(id);
  if(s){
    s.t[3]=tark;s.t[6]='k\u00e4sin';
    if(s.kat!==kat){
      DATA.kat[s.kat][s.kk].splice(s.i,1);
      if(!DATA.kat[kat]){DATA.kat[kat]={};}
      if(!DATA.kat[kat][s.kk]){DATA.kat[kat][s.kk]=[];}
      DATA.kat[kat][s.kk].unshift(s.t);
    }
  }
  const tr=document.getElementById('rivi-'+id);
  if(tr){
    tr.classList.add('tallennettu');
    const pm=tr.querySelector('.perus');
    if(pm){pm.textContent='\u270e';pm.title='k\u00e4sin';}
    const sel=tr.querySelector('.katsel'); if(sel){sel.value=kat;}
    const ip=tr.querySelector('.tarkinp'); if(ip){ip.value=tark;}
  }
}
function paivitaSivu(kohde,viesti){
  if(viesti){try{sessionStorage.setItem('rahaputki_viesti',viesti);}catch(err){}}
  if(kohde==='saannot'){location.hash='saannot';}
  else if(kohde==='yhteistalous'){location.hash='yhteistalous';}
  else if(PANEELI&&PANEELI.haku){location.hash='haku='+encodeURIComponent(PANEELI.haku);}
  else if(PANEELI&&PANEELI.kk_laji){location.hash='kklaji='+PANEELI.kk_laji+'&kkm='+PANEELI.kk_kk;}
  else if(PANEELI&&PANEELI.kat){location.hash='kat='+encodeURIComponent(PANEELI.kat)+(PANEELI.kk?'&kk='+PANEELI.kk:'')+(PANEELI.tark?'&tark='+encodeURIComponent(PANEELI.tark):'');}
  location.reload();
}
function riviLista(){
  return Array.prototype.slice.call(document.querySelectorAll('#paneeli tr')).filter(function(x){
    return x.id&&x.id.indexOf('rivi-')===0;});
}
function paivitaValinta(){
  riviLista().forEach(function(tr){
    tr.classList.toggle('valittu',VALINTA.indexOf(tr.id.slice(5))>=0);});
  const p=document.getElementById('massapalkki');
  if(p){
    const ns=document.getElementById('massa-n');
    if(ns){ns.textContent=VALINTA.length;}
    p.style.display=VALINTA.length>1?'flex':'none';
  }
}
function massaMuuta(){
  const sel=document.querySelector('.katsel[data-id="__massa__"]');
  const kat=sel?sel.value:'';
  const tark=(document.getElementById('massa-tark')||{value:''}).value.trim().toLowerCase();
  if(!kat||kat==='__uusi__'){alert('valitse kategoria');return;}
  const idt=VALINTA.slice();
  if(!idt.length){return;}
  const kuvat=idt.map(tilannekuva).filter(function(x){return x;});
  if(SERVER){
    fetch('api/muutos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({idt:idt,kategoria:kat,tarkenne:tark})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        idt.forEach(function(id){soveltaKasin(id,kat,tark);});
        VALINTA=[];ANKKURI=null;paivitaValinta();
        KUMOA=kuvat;
        naytaKumoa(v.paivitetty+' rivi\u00e4 muutettu k\u00e4sin \u2713');
      });
  }else{
    idt.forEach(function(id){
      MUUT.rivit[id]={kategoria:kat,tarkenne:tark};
      soveltaKasin(id,kat,tark);
    });
    KUMOA=kuvat;
    VALINTA=[];ANKKURI=null;paivitaValinta();paivitaPalkki();
    naytaKumoa(idt.length+' rivi\u00e4 jonossa');
  }
}
function saannonTiedot(el){
  // Säännön tiedot ovat rivillä kerran, eivät jokaisessa linkissä.
  const tr=el.closest('tr');
  return {malli:tr.getAttribute('data-malli'),kategoria:tr.getAttribute('data-kategoria'),
          ehto:tr.getAttribute('data-ehto')};
}
function muokkaaRivi(tr, a){
  if(MUOKKAUS){MUOKKAUS.tr.innerHTML=MUOKKAUS.html;}
  MUOKKAUS={tr:tr,html:tr.innerHTML,vanha:saannonTiedot(a)};
  const osat=MUOKKAUS.vanha.kategoria.split(':');
  tr.innerHTML='<td class="num"></td>'+
    '<td><input id="mk-malli" class="minp" size="20" value="'+esc(MUOKKAUS.vanha.malli)+'"></td>'+
    '<td>'+katvalikko('__muok__',osat[0])+' <input id="mk-tark" class="tarkinp" data-id="__muok2__" '+
    'list="tarklist" placeholder="tarkenne" value="'+esc(osat.slice(1).join(':'))+'"></td>'+
    '<td><input id="mk-ehto" class="minp" size="8" value="'+esc(MUOKKAUS.vanha.ehto)+'"></td>'+
    '<td class="num"><span id="mk-osuma" class="pikkuteksti"></span></td>'+
    '<td><a href="#" id="mk-tallenna"><b>tallenna</b></a> \u00b7 <a href="#" id="mk-peru">peru</a></td>';
  osumalaskuri(MUOKKAUS.vanha.malli,'mk-osuma');
}
let OSUMA_AJASTIN=null;
function osumalaskuri(teksti, kohde, viive){
  if(OSUMA_AJASTIN){clearTimeout(OSUMA_AJASTIN);}
  const heti=document.getElementById(kohde);
  if(heti&&teksti.trim()){heti.textContent='lasketaan\u2026';}
  OSUMA_AJASTIN=setTimeout(function(){
    const el=document.getElementById(kohde);
    if(!el){return;}
    const malli=teksti.trim().toLowerCase();
    if(!malli){el.textContent='';return;}
    if(SERVER){
      fetch('api/saanto-osuma',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({malli:malli})})
        .then(function(r){return r.json();}).then(function(v){
          if(v.ok){el.textContent='osuu '+v.osuu+' riviin';
            el.title=(v.esimerkit||[]).join(' | ');}
          else{el.textContent=v.virhe||'';}
        });
    }else{
      let n=0, re2=null;
      const os=malli.indexOf('re:')===0?null:malli;
      if(!os){try{re2=new RegExp(malli.slice(3),'i');}catch(err){el.textContent='regex-virhe';return;}}
      for(const k in DATA.kat){const kuut=DATA.kat[k];
        for(const m in kuut){kuut[m].forEach(function(t){
          const tx=(String(t[2])+' '+String(t[7]||'')).toLowerCase();
          if(os?tx.indexOf(os)>=0:re2.test(tx)){n++;}
        });}}
      el.textContent='~'+n+' rivi\u00e4 (porattavista)';
    }
  },viive===0?0:2000);
}
function kysyPakota(v){
  if(!v.kasin_voisi){return false;}
  let m='Uusi s\u00e4\u00e4nt\u00f6 osuisi ensimm\u00e4isen\u00e4 my\u00f6s '+v.kasin_voisi+
    ' k\u00e4sin/oletus-luokiteltuun riviin';
  if(v.kasin_esim&&v.kasin_esim.length){m+=' (esim. '+v.kasin_esim.join(' | ')+')';}
  return confirm(m+'.'+String.fromCharCode(10)+
    'OK = my\u00f6s ne siirtyv\u00e4t noudattamaan s\u00e4\u00e4nt\u00f6\u00e4. '+
    'Peruuta = ne pysyv\u00e4t k\u00e4sivalinnoissaan.');
}
function toteutaSaanto(malli,kat,tark,ehto,poistaen,valmisTeksti,pakota,kohde){
  fetch('api/saanto',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({malli:malli,kategoria:kat,tarkenne:tark,ehto:ehto,poistaen:poistaen,
      pakota:!!pakota})})
    .then(function(r){return r.json();}).then(function(w){
      if(w.ok){
        let vt=valmisTeksti+' \u2014 '+w.muuttui+' rivi\u00e4 luokiteltu uudelleen';
        if(!w.muuttui){vt+=' \u26a0 jos odotit muutoksia, aikaisempi s\u00e4\u00e4nt\u00f6 '+
          'todenn\u00e4k\u00f6isesti varjostaa uutta \u2014 katso S\u00e4\u00e4nn\u00f6t-taulukon Osuu/Perusteena-sarakkeet';}
        paivitaSivu(kohde||'paneeli',vt);
      }
      else{alert(w.virhe||'virhe');}
    });
}
function perusSymboli(p){
  if(!p)return '\u00b7';
  if(p.indexOf('s\u00e4\u00e4nt\u00f6')===0)return '\u00a7';
  if(p==='k\u00e4sin')return '\u270e';
  if(p==='oletus')return '\u25e6';
  if(p==='oma tili')return '\u21c4';
  return '\u00b7';
}
function perus(p){
  if(!p)return '';
  let t=p, lisa='';
  if(p.indexOf('s\u00e4\u00e4nt\u00f6: ')===0){
    const eh=SAANTOEHDOT[p.slice(8)];
    if(eh){t=p+' \u00b7 '+eh;}
    if(SAANTOTIEDOT[p.slice(8)]){
      const st=SAANTOTIEDOT[p.slice(8)];
      t=p+' \u2192 '+st.kategoria+(st.ehto?' ('+st.ehto+')':'')+
        String.fromCharCode(10)+'klikkaa: muokkaa t\u00e4t\u00e4 s\u00e4\u00e4nt\u00f6\u00e4';
      lisa=' saantoperus';
    }
  }
  return '<span class="perus'+lisa+'" title="'+esc(t)+'">'+perusSymboli(p)+'</span> ';
}
function muokkaaSaantoaLomakkeella(mallinorm){
  const st=SAANTOTIEDOT[mallinorm];
  const f=document.getElementById('sf-malli');
  if(!st||!f){return false;}
  const osat=String(st.kategoria).split(':');
  f.value=st.malli;
  const sel=document.querySelector('.katsel[data-id="__saanto__"]');
  if(sel){
    if(!Array.prototype.some.call(sel.options,function(o){return o.value===osat[0];})){
      const o=document.createElement('option');o.value=osat[0];o.textContent=osat[0];sel.appendChild(o);
    }
    sel.value=osat[0];
  }
  const tark=document.getElementById('sf-tark');
  if(tark){tark.value=osat.slice(1).join(':');}
  const eh=document.getElementById('sf-ehto');
  if(eh){eh.value=st.ehto||'';}
  SF_KORVAA={malli:st.malli,kategoria:st.kategoria,ehto:st.ehto||''};
  paivitaLomakkeenTila();
  f.scrollIntoView({block:'center'});
  f.focus();
  osumalaskuri(f.value,'sf-osuma',0);
  return true;
}
function paivitaLomakkeenTila(){
  const otsikko=document.getElementById('sf-otsikko');
  const nappi=document.getElementById('sf-nappi');
  const peru=document.getElementById('sf-peru');
  if(!otsikko||!nappi){return;}
  if(SF_KORVAA){
    otsikko.textContent='Muokataan s\u00e4\u00e4nt\u00f6\u00e4 '+SF_KORVAA.malli+
      ' \u2192 '+SF_KORVAA.kategoria+':';
    nappi.textContent='Tallenna muutos';
    if(peru){peru.style.display='';}
  }else{
    otsikko.textContent='Uusi s\u00e4\u00e4nt\u00f6:';
    nappi.textContent='Lis\u00e4\u00e4 s\u00e4\u00e4nt\u00f6';
    if(peru){peru.style.display='none';}
  }
}
function peruSaantomuokkaus(){
  SF_KORVAA=null;
  const f=document.getElementById('sf-malli');
  if(f){f.value='';}
  const tark=document.getElementById('sf-tark');
  if(tark){tark.value='';}
  const eh=document.getElementById('sf-ehto');
  if(eh){eh.value='';}
  const os=document.getElementById('sf-osuma');
  if(os){os.textContent='';}
  paivitaLomakkeenTila();
}
let KUMOA=null;
function tilannekuva(id){
  const s=etsiTuple(id);
  if(!s)return null;
  return {id:id,kategoria:s.kat,tarkenne:s.t[3],peruste:s.t[6]};
}
function soveltaPalautus(rp){
  const s=etsiTuple(rp.id);
  if(s){
    s.t[3]=rp.tarkenne;s.t[6]=rp.peruste;
    if(s.kat!==rp.kategoria){
      DATA.kat[s.kat][s.kk].splice(s.i,1);
      if(!DATA.kat[rp.kategoria]){DATA.kat[rp.kategoria]={};}
      if(!DATA.kat[rp.kategoria][s.kk]){DATA.kat[rp.kategoria][s.kk]=[];}
      DATA.kat[rp.kategoria][s.kk].unshift(s.t);
    }
  }
  const tr=document.getElementById('rivi-'+rp.id);
  if(tr){
    const pm=tr.querySelector('.perus');
    if(pm){pm.textContent=perusSymboli(rp.peruste);pm.title=rp.peruste||'';}
    const sel=tr.querySelector('.katsel'); if(sel){sel.value=rp.kategoria;}
    const ip=tr.querySelector('.tarkinp'); if(ip){ip.value=rp.tarkenne;}
    tr.classList.remove('tallennettu');
  }
}
function vapautaRivi(vid){
  fetch('api/vapauta',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:vid})})
    .then(function(r){return r.json();}).then(function(v){
      if(!v.ok){alert(v.virhe||'virhe');return;}
      soveltaPalautus({id:vid,kategoria:v.kategoria,tarkenne:v.tarkenne,peruste:v.peruste});
      merkitse(null,'vapautettu \u2713 \u2014 rivi luokittui: '+v.kategoria+
        (v.tarkenne?':'+v.tarkenne:'')+' ('+(v.peruste||'avoin')+')');
    });
}
function naytaKumoa(teksti){
  const t=document.getElementById('tila');
  if(!t)return;
  t.innerHTML=esc(teksti)+' \u00b7 <a href="#" id="kumoa-linkki">kumoa</a>';
}
function katvalikko(id,valittu){
  let h='<select class="katsel" data-id="'+id+'">';
  const ryhmat=[['Menot',KAT.menot],['Tulot',KAT.tulot],['Siirrot ym.',KAT.pois]];
  ryhmat.forEach(function(g){
    h+='<optgroup label="'+g[0]+'">';
    g[1].forEach(function(k){h+='<option'+(k===valittu?' selected':'')+'>'+esc(k)+'</option>';});
    h+='</optgroup>';
  });
  h+='<option value="__uusi__">+ uusi kategoria\u2026</option></select>';
  return h;
}
function etsiTuple(id){
  for(const k in DATA.kat){const kuut=DATA.kat[k];
    for(const m in kuut){const l=kuut[m];
      for(let i=0;i<l.length;i++){if(l[i][5]===id){return {kat:k,kk:m,i:i,t:l[i]};}}}}
  return null;
}
const KKNIMET=['tammikuu','helmikuu','maaliskuu','huhtikuu','toukokuu','kes\u00e4kuu',
  'hein\u00e4kuu','elokuu','syyskuu','lokakuu','marraskuu','joulukuu'];
function kkOtsikko(m){return KKNIMET[parseInt(m.slice(5,7),10)-1]+' '+m.slice(0,4);}
function riviHtml(t,katR){
  const selite=(t[7]&&t[7]!==t[2])?'<div class="selite2'+(katR==='TARKISTA'?' tarkselite':'')+
    '">'+esc(t[7])+'</div>':'';
  const etu=t[1]<0?(KAT.tulot.indexOf(katR)>=0?' miinus':' plus'):'';
  const var_=t[8]==='varaus'?'<span class="varausmerkki" title="Pankki ei ole viel\u00e4 '+
    'kirjannut t\u00e4t\u00e4 \u2014 summa tai p\u00e4iv\u00e4 voi viel\u00e4 muuttua, '+
    'ja veloitus voi my\u00f6s raueta">varaus</span> ':'';
  return '<tr id="rivi-'+t[5]+'" class="'+(t[8]==='varaus'?'varausrivi':'')+
    '"><td class="pvm2" title="'+t[0]+'">'+
    parseInt(t[0].slice(8),10)+'.'+parseInt(t[0].slice(5,7),10)+'.</td><td>'+var_+perus(t[6])+esc(t[2])+
    ' <a href="#" class="saantolinkki" data-saaja="'+esc(t[2])+'">s\u00e4\u00e4nt\u00f6</a>'+selite+'</td>'+
    '<td>'+katvalikko(t[5],katR)+' <input class="tarkinp" list="tarklist" data-id="'+t[5]+
    '" value="'+esc(t[3])+'" placeholder="tarkenne"></td>'+
    '<td class="tili2">'+esc(t[4])+'</td><td class="num'+etu+'">'+eur(t[1])+'</td></tr>';
}
function lomakeJaMassa(katX){
  return '<div class="sform"><b id="sf-otsikko">Uusi s\u00e4\u00e4nt\u00f6:</b>'+
    '<input id="sf-malli" placeholder="osamerkkijono, esim. brang" size="22">'+
    '<span>\u2192</span>'+katvalikko('__saanto__',katX)+
    '<input id="sf-tark" class="tarkinp" list="tarklist" placeholder="tarkenne">'+
    '<input id="sf-ehto" placeholder="ehto: min=50 / max=50" size="12" title="summaraja itseisarvosta; tyhj\u00e4 = ei rajaa">'+
    '<span id="sf-osuma" class="pikkuteksti"></span>'+
    '<button id="sf-nappi">Lis\u00e4\u00e4 s\u00e4\u00e4nt\u00f6</button>'+
    '<a href="#" id="sf-peru" style="display:none">peru muokkaus</a>'+
    '<span class="pikkuteksti">osuu saajaan/selitteeseen, luokittelee my\u00f6s avoimet rivit</span></div>'+
    '<div id="massapalkki"><b><span id="massa-n"></span> rivi\u00e4 valittu:</b>'+
    katvalikko('__massa__','TARKISTA')+
    '<input id="massa-tark" class="tarkinp" data-id="__massa9__" list="tarklist" placeholder="tarkenne">'+
    '<button id="massa-nappi">Muuta valitut</button>'+
    '<a href="#" id="massa-tyhjenna">tyhjenn\u00e4</a>'+
    '<span class="pikkuteksti">\u2318/Ctrl = lis\u00e4\u00e4, Shift = v\u00e4li</span></div>';
}
function avaa(kat, kk, tark){
  SF_KORVAA=null;
  const p=document.getElementById('paneeli');
  const kdata0=DATA.kat[kat]||{};
  let kdata=kdata0;
  if(tark){
    kdata={};
    Object.keys(kdata0).forEach(function(m){
      const ts=kdata0[m].filter(function(t){
        return ((t[3]||'').trim()||'(ei tarkennetta)')===tark;});
      if(ts.length){kdata[m]=ts;}});
  }
  const kaikki=DATA.kk;
  const summat=kaikki.map(function(m){return (kdata[m]||[]).reduce(function(a,t){return a+t[1];},0);});
  const max=Math.max.apply(null, summat.map(Math.abs).concat([1]));
  const W=880,H=160,POHJA=126,lev=W/kaikki.length;
  let svg='<svg viewBox="0 0 '+W+' '+H+'"><line x1="0" y1="'+POHJA+'" x2="'+W+'" y2="'+POHJA+'" stroke="#8a857c"/>';
  kaikki.forEach(function(m,i){
    const h=Math.abs(summat[i])/max*(POHJA-12);
    const y=summat[i]>=0?POHJA-h:POHJA;
    const vari=(m===kk)?'#26241f':'#b3502d';
    svg+='<rect data-kat="'+esc(kat)+'"'+(tark?' data-tark="'+esc(tark)+'"':'')+' data-kk="'+m+'" x="'+(i*lev+lev*0.18).toFixed(1)+'" y="'+y.toFixed(1)+
      '" width="'+(lev*0.64).toFixed(1)+'" height="'+h.toFixed(1)+'" fill="'+vari+'" style="cursor:pointer">'+
      '<title>'+m+': '+eur(summat[i])+' \u20ac</title></rect>';
    if(kaikki.length<=16||i%2===0){svg+='<text x="'+(i*lev+lev/2).toFixed(1)+'" y="'+(POHJA+15)+
      '" text-anchor="middle" class="aks">'+m.slice(5)+'/'+m.slice(2,4)+'</text>';}
  });
  const MA=summat.map(function(v,i){return i<2?null:(summat[i]+summat[i-1]+summat[i-2])/3;});
  let pts='';
  MA.forEach(function(v,i){if(v===null)return;
    pts+=(i*lev+lev/2).toFixed(1)+','+(POHJA-Math.max(v,0)/max*(POHJA-12)).toFixed(1)+' ';});
  if(pts){svg+='<polyline points="'+pts+'" fill="none" stroke="#26241f" stroke-width="2"/>';}
  svg+='</svg>';
  svg+='<p class="pikkuteksti" style="margin:.2rem 0 0">tumma viiva = 3 kk liukuva keskiarvo '+
    '\u00b7 luokitteluperuste: \u00a7 s\u00e4\u00e4nt\u00f6 \u2014 klikkaa rivin merkki\u00e4 n\u00e4hd\u00e4ksesi mik\u00e4 s\u00e4\u00e4nt\u00f6 '+
    '\u270e k\u00e4sin \u25e6 oletus \u21c4 oma tili \u00b7 klikkaa rivi\u00e4 valitaksesi '+
    '(\u2318/Ctrl lis\u00e4\u00e4, Shift ottaa v\u00e4lin)</p>';
  const lomake=lomakeJaMassa(kat);
  let tarkTaulu='';
  (function(){
    if(tark){tarkTaulu='<p class="pikkuteksti"><a href="#" class="klik" data-kat="'+esc(kat)+
      '">\u2190 kaikki tarkenteet</a></p>';return;}
    const perT={},jarj=[];
    kaikki.forEach(function(m){(kdata0[m]||[]).forEach(function(t){
      const tk=(t[3]||'').trim()||'(ei tarkennetta)';
      if(!perT[tk]){perT[tk]={yht:0};jarj.push(tk);}
      perT[tk][m]=(perT[tk][m]||0)+t[1];perT[tk].yht+=t[1];});});
    const aidot=jarj.filter(function(x){return x!=='(ei tarkennetta)';});
    if(!aidot.length){return;}
    jarj.sort(function(a,b){return Math.abs(perT[b].yht)-Math.abs(perT[a].yht);});
    let h='<details'+(aidot.length<=8?' open':'')+'><summary>Tarkenteet kuukausittain ('+aidot.length+')</summary>'+
      '<table><tr><th>tarkenne</th>';
    kaikki.forEach(function(m){h+='<th class="num">'+m.slice(5)+'/'+m.slice(2,4)+'</th>';});
    h+='<th class="num">yht</th></tr>';
    jarj.forEach(function(tk){
      h+='<tr><td><a href="#" class="klik" data-kat="'+esc(kat)+'" data-tark="'+esc(tk)+'">'+esc(tk)+'</a></td>';
      kaikki.forEach(function(m){const v=perT[tk][m];
        h+='<td class="num">'+(v?'<a href="#" class="klik" data-kat="'+esc(kat)+'" data-kk="'+m+
          '" data-tark="'+esc(tk)+'">'+eur(v)+'</a>':'')+'</td>';});
      h+='<td class="num"><b>'+eur(perT[tk].yht)+'</b></td></tr>';});
    h+='</table></details>';
    tarkTaulu=h;
  })();

  const kuut=kk?[kk]:kaikki.slice().reverse();
  let rivit='';
  kuut.forEach(function(m){
    const ts=kdata[m]||[]; if(!ts.length)return;
    const sum=ts.reduce(function(a,t){return a+t[1];},0);
    rivit+='<tr class="kkots"><td colspan="4">'+kkOtsikko(m)+'</td><td class="num">'+eur(sum)+'</td></tr>';
    ts.forEach(function(t){rivit+=riviHtml(t,kat);});
  });
  p.innerHTML='<div class="pkortti"><div class="privi"><h2 style="margin:0">'+esc(kat)+(tark?' \u00b7 '+esc(tark):'')+(kk?' \u00b7 '+kk:'')+
    '</h2><span class="pikkuteksti">'+(kk?'<a href="#" data-kat="'+esc(kat)+'"'+(tark?' data-tark="'+esc(tark)+'"':'')+'>kaikki kuukaudet</a> \u00b7 ':'')+
    '<a href="#" class="katpoisto" data-kat="'+esc(kat)+'">poista kategoria\u2026</a> \u00b7 '+
    '<a href="#" id="psulje">sulje \u2715</a></span></div>'+svg+tarkTaulu+lomake+
    '<table><tr><th>Pvm</th><th>Saaja</th><th>Kategoria \u00b7 tarkenne</th><th>Tili</th><th>\u20ac</th></tr>'+
    (rivit||'<tr><td colspan="5">ei tapahtumia</td></tr>')+'</table></div>';
  p.style.display='block';
  PANEELI={kat:kat,kk:kk||'',tark:tark||''};
  VALINTA=[];ANKKURI=null;
  p.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function haku(termi){
  const t0=termi.trim().toLowerCase();
  if(t0.length<2){
    if(t0.length===1){merkitse(null,'kirjoita v\u00e4hint\u00e4\u00e4n 2 merkki\u00e4');}
    if(PANEELI&&PANEELI.haku){sulje();}
    return;
  }
  const p=document.getElementById('paneeli');
  const kuut={};
  let n=0,summa=0;
  for(const k in DATA.kat){const kk=DATA.kat[k];
    for(const m in kk){kk[m].forEach(function(t){
      const teksti=(String(t[2])+' '+String(t[3])+' '+String(t[4])+' '+String(t[7]||'')+' '+k+
        ' '+String(t[1])+' '+String(t[1]).replace('.',',')).toLowerCase();
      if(teksti.indexOf(t0)>=0){
        if(!kuut[m]){kuut[m]=[];}
        kuut[m].push([t,k]);n++;summa+=t[1];
      }});}}
  const kkLista=Object.keys(kuut).sort().reverse();
  let rivit='',naytetty=0;
  kkLista.forEach(function(m){
    if(naytetty>=400){return;}
    const ts=kuut[m];
    ts.sort(function(a,b){return a[0][0]<b[0][0]?1:-1;});
    const sum=ts.reduce(function(a,x){return a+x[0][1];},0);
    rivit+='<tr class="kkots"><td colspan="4">'+kkOtsikko(m)+'</td><td class="num">'+eur(sum)+'</td></tr>';
    ts.forEach(function(x){if(naytetty<400){rivit+=riviHtml(x[0],x[1]);naytetty++;}});
  });
  p.innerHTML='<div class="pkortti"><div class="privi"><h2 style="margin:0">Haku: \u201d'+esc(t0)+
    '\u201d</h2><span class="pikkuteksti"><a href="#" id="psulje">sulje \u2715</a></span></div>'+
    '<p class="pikkuteksti">'+n+' rivi\u00e4 \u00b7 nettosumma '+eur(summa)+' \u20ac'+
    (n>400?' \u00b7 n\u00e4ytet\u00e4\u00e4n 400 ensimm\u00e4ist\u00e4':'')+
    ' \u00b7 valinta ja massamuutos toimivat my\u00f6s t\u00e4\u00e4ll\u00e4</p>'+
    lomakeJaMassa('TARKISTA')+
    '<table><tr><th>Pvm</th><th>Saaja</th><th>Kategoria \u00b7 tarkenne</th><th>Tili</th><th>\u20ac</th></tr>'+
    (rivit||'<tr><td colspan="5">ei osumia</td></tr>')+'</table></div>';
  p.style.display='block';
  PANEELI={haku:t0};
  VALINTA=[];ANKKURI=null;
}
function kuukausi(kk, laji){
  const p=document.getElementById('paneeli');
  const katLista=(laji==='menot')?KAT.menot.concat(['TARKISTA']):KAT.tulot;
  const ryhmat=[];
  let n=0,summa=0;
  katLista.forEach(function(k){
    const ts=(DATA.kat[k]&&DATA.kat[k][kk])?DATA.kat[k][kk].slice():[];
    if(!ts.length){return;}
    ts.sort(function(a,b){return a[0]<b[0]?1:-1;});
    const sum=ts.reduce(function(a,t){return a+t[1];},0);
    ryhmat.push([k,sum,ts]);
    n+=ts.length;summa+=sum;
  });
  ryhmat.sort(function(a,b){return b[1]-a[1];});
  let rivit='';
  ryhmat.forEach(function(g){
    rivit+='<tr class="kkots"><td colspan="4" class="klik" data-kat="'+esc(g[0])+
      '" data-kk="'+kk+'">'+esc(g[0])+'</td><td class="num">'+eur(g[1])+'</td></tr>';
    g[2].forEach(function(t){rivit+=riviHtml(t,g[0]);});
  });
  p.innerHTML='<div class="pkortti"><div class="privi"><h2 style="margin:0">'+
    (laji==='menot'?'Menot \u00b7 ':'Tulot \u00b7 ')+kkOtsikko(kk)+'</h2><span class="pikkuteksti">'+
    '<a href="#" id="psulje">sulje \u2715</a></span></div>'+
    '<p class="pikkuteksti">'+n+' rivi\u00e4 \u00b7 yhteens\u00e4 '+eur(summa)+
    ' \u20ac \u00b7 kategoriat suurimmasta pienimp\u00e4\u00e4n \u00b7 klikkaa rivi\u00e4 valitaksesi</p>'+
    lomakeJaMassa('TARKISTA')+
    '<table><tr><th>Pvm</th><th>Saaja</th><th>Kategoria \u00b7 tarkenne</th><th>Tili</th><th>\u20ac</th></tr>'+
    (rivit||'<tr><td colspan="5">ei tapahtumia</td></tr>')+'</table></div>';
  p.style.display='block';
  PANEELI={kk_laji:laji,kk_kk:kk};
  VALINTA=[];ANKKURI=null;
  p.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function haeRivi(id){
  const sel=document.querySelector('.katsel[data-id="'+id+'"]');
  const inp=document.querySelector('.tarkinp[data-id="'+id+'"]');
  return {kategoria:sel?sel.value:'',tarkenne:inp?inp.value.trim().toLowerCase():''};
}
function merkitse(id,teksti){
  const tr=document.getElementById('rivi-'+id);
  if(tr){tr.classList.add('tallennettu');}
  const t=document.getElementById('tila');
  if(t&&teksti){t.textContent=teksti;}
}
function paivitaPalkki(){
  const n=Object.keys(MUUT.rivit).length+MUUT.saannot.length+MUUT.poistot.length;
  const palkki=document.getElementById('muutospalkki');
  document.getElementById('muutosteksti').textContent=n+' tallentamatonta muutosta';
  palkki.style.display=n?'block':'none';
}
function tallennaRivi(id){
  const m=haeRivi(id);
  if(m.kategoria==='__uusi__'){
    const nimi=prompt('Uuden kategorian nimi:');
    if(!nimi){avaa(document.querySelector('#paneeli h2').textContent);return;}
    if(SERVER){
      fetch('api/kategoria',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({nimi:nimi})}).then(function(r){return r.json();}).then(function(v){
          if(!v.ok){alert(v.virhe||'virhe');return;}
          KAT.menot.push(nimi);
          KAT.menot.sort(function(a,b){return a.toLowerCase()<b.toLowerCase()?-1:1;});
          const sel=document.querySelector('.katsel[data-id="'+id+'"]');
          const o=document.createElement('option');o.textContent=nimi;
          sel.querySelector('optgroup').appendChild(o);sel.value=nimi;
          tallennaRivi(id);
        });
    }else{alert('Uusi kategoria lis\u00e4t\u00e4\u00e4n config.json:iin (tai k\u00e4yt\u00e4 selaa-tilaa).');}
    return;
  }
  const kuva=tilannekuva(id);
  if(SERVER){
    fetch('api/muutos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:id,kategoria:m.kategoria,tarkenne:m.tarkenne})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'tallennus ep\u00e4onnistui');return;}
        soveltaKasin(id,m.kategoria,m.tarkenne);
        if(kuva){KUMOA=[kuva];}
        naytaKumoa('tallennettu k\u00e4sin \u2713 (s\u00e4\u00e4nn\u00f6t eiv\u00e4t koske t\u00e4h\u00e4n en\u00e4\u00e4)');
      }).catch(function(){alert('yhteys palvelimeen katkesi \u2014 k\u00e4ynnist\u00e4 selaa uudelleen');});
  }else{
    MUUT.rivit[id]=m;
    soveltaKasin(id,m.kategoria,m.tarkenne);
    if(kuva){KUMOA=[kuva];}
    paivitaPalkki();
  }
}
function lisaaSaanto(){
  const korvaa=SF_KORVAA?[{malli:SF_KORVAA.malli,kategoria:SF_KORVAA.kategoria,
                           ehto:SF_KORVAA.ehto}]:null;
  const malli=document.getElementById('sf-malli').value.trim().toLowerCase();
  const kat=document.querySelector('.katsel[data-id="__saanto__"]').value;
  const tark=document.getElementById('sf-tark').value.trim().toLowerCase();
  const ehto=document.getElementById('sf-ehto').value.trim().toLowerCase();
  if(!malli||kat==='__uusi__'){alert('anna malli ja kategoria');return;}
  const psp=PSP.find(function(x){return malli.indexOf(x)>=0;});
  if(psp&&!confirm('"'+malli+'" on maksunv\u00e4litt\u00e4j\u00e4 ('+psp+') \u2014 s\u00e4\u00e4nt\u00f6 osuisi moniin eri kauppoihin. Tehd\u00e4\u00e4nk\u00f6 silti?')){return;}
  if(korvaa&&SERVER){
    // Muokkaus: vanha sääntö korvataan uudella samassa kohdassa listaa.
    fetch('api/saanto',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({malli:malli,kategoria:kat,tarkenne:tark,ehto:ehto,
                           esikatselu:true,poistaen:korvaa})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        let m='Korvataan  '+korvaa[0].malli+' \u2192 '+korvaa[0].kategoria+
          '  s\u00e4\u00e4nn\u00f6ll\u00e4  '+malli+' \u2192 '+kat+(tark?':'+tark:'')+
          (ehto?' ('+ehto+')':'')+'.'+String.fromCharCode(10)+
          v.muuttuu+' rivi\u00e4 luokittuu uudelleen';
        if(v.suojattu){m+='; '+v.suojattu+' k\u00e4sin-luokiteltua ei muuteta';}
        if(v.esimerkit&&v.esimerkit.length){m+='. Esim: '+v.esimerkit.join(' | ');}
        if(!confirm(m+'. Toteutetaanko?')){return;}
        SF_KORVAA=null;
        toteutaSaanto(malli,kat,tark,ehto,korvaa,'s\u00e4\u00e4nt\u00f6 korvattu \u2713',
                      kysyPakota(v));
      });
    return;
  }
  if(korvaa&&!SERVER){
    MUUT.poistot.push({malli:korvaa[0].malli,kategoria:korvaa[0].kategoria});
    MUUT.saannot.push({malli:malli,kategoria:kat,tarkenne:tark});
    SF_KORVAA=null;paivitaLomakkeenTila();paivitaPalkki();
    return;
  }
  if(SERVER){
    fetch('api/saanto',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({malli:malli,kategoria:kat,tarkenne:tark,ehto:ehto,esikatselu:true})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        const perhe=function(x){return x.malli.indexOf(malli)>=0||malli.indexOf(x.malli)>=0;};
        const korvattavat=(v.estajat||[]).filter(perhe);
        const vieraat=(v.estajat||[]).filter(function(x){return !perhe(x);});
        if(korvattavat.length){
          const lista=korvattavat.map(function(x){return x.malli+' \u2192 '+x.kategoria+' ('+x.rivit+' r.)';}).join('; ');
          let vm='Saman s\u00e4\u00e4nt\u00f6perheen vanhat s\u00e4\u00e4nn\u00f6t est\u00e4v\u00e4t uuden: '+lista+'.';
          if(vieraat.length){vm+=' (Muut p\u00e4\u00e4llekk\u00e4isyydet j\u00e4tet\u00e4\u00e4n rauhaan: '+
            vieraat.map(function(x){return x.malli;}).join(', ')+'.)';}
          if(!confirm(vm+String.fromCharCode(10)+'OK = korvataan ne uudella s\u00e4\u00e4nn\u00f6ll\u00e4 (rivit '+
            'luokitellaan uudelleen). Peruuta = ei tehd\u00e4 mit\u00e4\u00e4n.')){return;}
          const poistaen=korvattavat.map(function(x){return {malli:x.malli,kategoria:x.kategoria};});
          fetch('api/saanto',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({malli:malli,kategoria:kat,tarkenne:tark,esikatselu:true,poistaen:poistaen})})
            .then(function(r){return r.json();}).then(function(v2){
              if(!v2.ok){alert(v2.virhe||'virhe');return;}
              let m2='Korvauksen vaikutus: '+v2.muuttuu+' rivi\u00e4 luokittuu uudelleen';
              if(v2.suojattu){m2+='; '+v2.suojattu+' k\u00e4sin/oletus-luokiteltua ei muuteta';}
              if(v2.estajat&&v2.estajat.length){
                m2+='.'+String.fromCharCode(10)+
                  '\u26a0 HUOM: korvauksenkin j\u00e4lkeen AIKAISEMPI s\u00e4\u00e4nt\u00f6 voittaisi uuden s\u00e4\u00e4nt\u00f6si ('+
                  v2.estajat.map(function(e){return "'"+e.malli+"'";}).join(', ')+
                  ') \u2014 esimerkit n\u00e4ytt\u00e4v\u00e4t mihin rivit OIKEASTI menisiv\u00e4t';
              }
              if(v2.esimerkit&&v2.esimerkit.length){m2+='.'+String.fromCharCode(10)+'Esim: '+v2.esimerkit.join(' | ');}
              if(!confirm(m2+'. Toteutetaanko?')){return;}
              toteutaSaanto(malli,kat,tark,ehto,poistaen,
                v.estajat.length+' s\u00e4\u00e4nt\u00f6\u00e4 korvattu \u2713',kysyPakota(v2));
            });
          return;
        }
        let viesti='S\u00e4\u00e4nt\u00f6 osuu '+v.osuu+' riviin. '+v.muuttuu+
          ' luokittuu uudelleen (joista '+v.avoimia+' avointa saa luokan).';
        if(v.suojattu){viesti+=' '+v.suojattu+' k\u00e4sin/oletus-luokiteltua ei muuteta.';}
        if(v.esimerkit&&v.esimerkit.length){viesti+=' Esim: '+v.esimerkit.join(' | ')+'.';}
        if(!confirm(viesti+' Lis\u00e4t\u00e4\u00e4nk\u00f6 s\u00e4\u00e4nt\u00f6?')){return;}
        toteutaSaanto(malli,kat,tark,ehto,[], 's\u00e4\u00e4nt\u00f6 lis\u00e4tty \u2713',kysyPakota(v));
      });
  }else{
    MUUT.saannot.push({malli:malli,kategoria:kat,tarkenne:tark});paivitaPalkki();
  }
}
function lataaMuutokset(){
  const NL=String.fromCharCode(10);
  let csv='id;kategoria;tarkenne;malli;toiminto'+NL;
  Object.keys(MUUT.rivit).forEach(function(id){
    const m=MUUT.rivit[id];
    csv+=id+';'+m.kategoria+';'+m.tarkenne+';;'+NL;
  });
  MUUT.saannot.forEach(function(s){csv+=';'+s.kategoria+';'+s.tarkenne+';'+s.malli+';'+NL;});
  MUUT.poistot.forEach(function(s){csv+=';'+s.kategoria+';;'+s.malli+';poista'+NL;});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  a.download='muutokset.csv';a.click();
  document.getElementById('tila').textContent='muutokset.csv ladattu \u2014 aja: python3 kirjanpito.py opi';
}
function siivoaTarkenne(kat, inp){
  if(!inp||!inp.value||kat==='__uusi__'){return;}
  const lista=TARKKAT[kat]||[];
  if(lista.indexOf(inp.value.trim().toLowerCase())<0){inp.value='';}
}
function tutkiSailyta(fn){
  // Säilytä sivun pystyskrollaus ja puun oma skrollaus DOM-uudelleenrakennuksen yli.
  const y=window.pageYOffset||document.documentElement.scrollTop||0;
  const puu=document.getElementById('tutki-puu');
  const py=puu?puu.scrollTop:0;
  fn();
  // Palauta heti ja uudelleen seuraavalla ruudulla (reflow'n jälkeen), ettei selain hyppää.
  window.scrollTo(0,y);
  if(puu)puu.scrollTop=py;
  if(typeof requestAnimationFrame==='function'){
    requestAnimationFrame(function(){
      window.scrollTo(0,y);
      const p2=document.getElementById('tutki-puu'); if(p2)p2.scrollTop=py;
    });
  }
}
document.addEventListener('toggle',function(ev){
  if(ev.target && ev.target.id==='tutki-details' && ev.target.open){
    tutkiRakennaPuu(); tutkiPiirra();
  }
},true);
document.addEventListener('click',function(ev){
  const nuoli=ev.target.closest('.tutki-nuoli');
  if(nuoli && nuoli.getAttribute('data-toggle')){
    ev.preventDefault();
    tutkiSailyta(function(){ tutkiAvaa(nuoli.getAttribute('data-toggle')); }); return;
  }
  const krivi=ev.target.closest('.tutki-katrivi');
  if(krivi && !ev.target.closest('.tutki-nuoli')){
    ev.preventDefault();
    tutkiSailyta(function(){ tutkiToggle(krivi.getAttribute('data-tkat')); }); return;
  }
  const trivi=ev.target.closest('.tutki-tark');
  if(trivi){
    ev.preventDefault();
    tutkiSailyta(function(){ tutkiToggle(trivi.getAttribute('data-av')); }); return;
  }
  if(ev.target.id==='tutki-tila'){
    ev.preventDefault();
    TUTKI.tila=(TUTKI.tila==='stacked')?'grouped':'stacked';
    document.getElementById('tutki-selite').textContent=
      TUTKI.tila==='stacked'?'pinottu':'rinnakkain';
    tutkiSailyta(tutkiPiirra); return;
  }
  if(ev.target.id==='tutki-tyhjaa'){
    ev.preventDefault();
    TUTKI.valitut=[]; TUTKI.varit={};
    tutkiSailyta(function(){ tutkiPaivitaLamput(); tutkiPiirra(); }); return;
  }
});
document.addEventListener('change',function(ev){
  const el=ev.target;
  if(el.id==='ol-otsikko'){
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({otsikko:el.value})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','nimi p\u00e4ivitetty \u2713');});
    return;
  }
  if(el.id==='ol-viikkotark'||el.id==='ol-palautustark'){
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    const runko={};runko[el.id==='ol-viikkotark'?'viikkojako':'palautustarkenteet']=el.value;
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(runko)})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','poiminta p\u00e4ivitetty \u2713');});
    return;
  }
  if(el.id==='ol-kat'){
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    const arvo=el.value;
    if(arvo==='__uusi__'){
      const nimi=prompt('Poimintakategorian nimi:','');
      if(!nimi||!nimi.trim()){paivitaSivu('yhteistalous');return;}
      fetch('api/kategoria',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({nimi:nimi.trim()})})
        .then(function(r){return r.json();}).then(function(v){
          if(!v.ok){alert(v.virhe||'virhe');return;}
          fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({kategoria:nimi.trim()})})
            .then(function(r){return r.json();}).then(function(w){
              if(!w.ok){alert(w.virhe||'virhe');return;}
              paivitaSivu('yhteistalous','kategoria luotu ja kytketty \u2713');});
        });
      return;
    }
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kategoria:arvo})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','poimintakategoria: '+(arvo||'ei k\u00e4yt\u00f6ss\u00e4')+' \u2713');});
    return;
  }
  if(el.classList&&el.classList.contains('katsel')){
    if(el.value==='__uusi__'){
      const nimi=prompt('Uuden kategorian nimi:');
      if(!nimi||!nimi.trim()){el.value=el.dataset.edellinen||'';return;}
      const n2=nimi.trim();
      if(!SERVER){alert('Uuden kategorian luonti vaatii selaa-tilan.');el.value=el.dataset.edellinen||'';return;}
      fetch('api/kategoria',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({nimi:n2})})
        .then(function(r){return r.json();}).then(function(v){
          if(!v||!v.ok){alert((v&&v.virhe)||'virhe');el.value=el.dataset.edellinen||'';return;}
          KAT.menot.push(n2);
          KAT.menot.sort(function(a,b){return a.toLowerCase()<b.toLowerCase()?-1:1;});
          document.querySelectorAll('select.katsel').forEach(function(s){
            const o=document.createElement('option');o.textContent=n2;
            const g=s.querySelector('optgroup');if(g){g.appendChild(o);}});
          el.value=n2;el.dataset.edellinen=n2;
          if(el.dataset.id&&el.dataset.id.indexOf('__')!==0){tallennaRivi(el.dataset.id);}
        });
      return;
    }
    el.dataset.edellinen=el.value;
    let inp=null;
    if(el.dataset.id==='__saanto__'){inp=document.getElementById('sf-tark');}
    else if(el.dataset.id==='__muok__'){inp=document.getElementById('mk-tark');}
    else if(el.dataset.id==='__massa__'){inp=document.getElementById('massa-tark');}
    else{inp=document.querySelector('.tarkinp[data-id="'+el.dataset.id+'"]');}
    siivoaTarkenne(el.value,inp);
  }
  if(el.id==='sf-malli'){osumalaskuri(el.value,'sf-osuma',0);return;}
  if(el.id==='mk-malli'){osumalaskuri(el.value,'mk-osuma',0);return;}
  if(el.dataset&&el.dataset.id&&el.dataset.id.indexOf('__')!==0){tallennaRivi(el.dataset.id);}
});
document.addEventListener('keydown',function(ev){
  if(ev.key==='Escape'&&ev.target&&ev.target.id==='haku'){
    ev.target.value='';sulje();
  }
});
document.addEventListener('mousedown',function(ev){
  if(ev.shiftKey&&ev.target.closest('#paneeli tr')){ev.preventDefault();}
});
document.addEventListener('click',function(ev){
  if(ev.target.id==='sf-nappi'){lisaaSaanto();return;}
  if(ev.target.id==='massa-nappi'){massaMuuta();return;}
  if(ev.target.id==='kumoa-linkki'){
    ev.preventDefault();
    if(!KUMOA){return;}
    const jono=KUMOA;KUMOA=null;
    if(SERVER){
      fetch('api/muutos',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({rivit:jono})})
        .then(function(r){return r.json();}).then(function(v){
          if(!v.ok){alert(v.virhe||'virhe');return;}
          jono.forEach(soveltaPalautus);
          merkitse(null,'kumottu \u2713 \u2014 '+v.paivitetty+' rivi\u00e4 palautettu');
        });
    }else{
      jono.forEach(function(rp){
        MUUT.rivit[rp.id]={kategoria:rp.kategoria,tarkenne:rp.tarkenne};
        soveltaPalautus(rp);
      });
      paivitaPalkki();
      merkitse(null,'kumottu jonossa \u2713');
    }
    return;
  }
  if(ev.target.id==='massa-tyhjenna'){ev.preventDefault();VALINTA=[];ANKKURI=null;paivitaValinta();return;}
  const rtr=ev.target.closest('#paneeli tr');
  if(rtr&&rtr.id&&rtr.id.indexOf('rivi-')===0&&!ev.target.closest('select,input,a,button,.perus')){
    const id=rtr.id.slice(5);
    const lista=riviLista();
    const idx=lista.indexOf(rtr);
    if(ev.shiftKey&&ANKKURI!==null){
      const a=Math.min(ANKKURI,idx),b=Math.max(ANKKURI,idx);
      VALINTA=lista.slice(a,b+1).map(function(x){return x.id.slice(5);});
    }else if(ev.ctrlKey||ev.metaKey){
      const p=VALINTA.indexOf(id);
      if(p>=0){VALINTA.splice(p,1);}else{VALINTA.push(id);}
      ANKKURI=idx;
    }else{
      VALINTA=(VALINTA.length===1&&VALINTA[0]===id)?[]:[id];
      ANKKURI=idx;
    }
    paivitaValinta();
    return;
  }
  if(ev.target.id==='lataamuutokset'){lataaMuutokset();return;}
  if(ev.target.id==='mk-peru'||ev.target.closest('#mk-peru')){
    ev.preventDefault();
    if(MUOKKAUS){MUOKKAUS.tr.innerHTML=MUOKKAUS.html;MUOKKAUS=null;}
    return;}
  if(ev.target.id==='mk-tallenna'||ev.target.closest('#mk-tallenna')){
    ev.preventDefault();
    if(!MUOKKAUS)return;
    const um=document.getElementById('mk-malli').value.trim().toLowerCase();
    const uk=document.querySelector('.katsel[data-id="__muok__"]').value;
    const ut=document.getElementById('mk-tark').value.trim().toLowerCase();
    const ue=document.getElementById('mk-ehto').value.trim();
    if(!um||uk==='__uusi__'){alert('anna malli ja kategoria');return;}
    if(!SERVER){
      MUUT.poistot.push({malli:MUOKKAUS.vanha.malli,kategoria:MUOKKAUS.vanha.kategoria});
      MUUT.saannot.push({malli:um,kategoria:uk,tarkenne:ut});
      MUOKKAUS.tr.innerHTML=MUOKKAUS.html;MUOKKAUS.tr.classList.add('poistettu');
      MUOKKAUS=null;paivitaPalkki();return;}
    const poistaen=[{malli:MUOKKAUS.vanha.malli,kategoria:MUOKKAUS.vanha.kategoria,
                     ehto:MUOKKAUS.vanha.ehto}];
    fetch('api/saanto',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({malli:um,kategoria:uk,tarkenne:ut,ehto:ue,esikatselu:true,poistaen:poistaen})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        let m='Korvataan  '+MUOKKAUS.vanha.malli+' \u2192 '+MUOKKAUS.vanha.kategoria+
          '  s\u00e4\u00e4nn\u00f6ll\u00e4  '+um+' \u2192 '+uk+(ut?':'+ut:'')+'.'+
          String.fromCharCode(10)+v.muuttuu+' rivi\u00e4 luokittuu uudelleen';
        if(v.suojattu){m+='; '+v.suojattu+' k\u00e4sin-luokiteltua ei muuteta';}
        if(v.esimerkit&&v.esimerkit.length){m+='. Esim: '+v.esimerkit.join(' | ');}
        if(!confirm(m+'. Toteutetaanko?')){return;}
        const trx=MUOKKAUS.tr;
        toteutaSaanto(um,uk,ut,ue,poistaen,'s\u00e4\u00e4nt\u00f6 korvattu \u2713',kysyPakota(v),'saannot');
        trx.innerHTML='<td>'+esc(um)+'</td><td>'+esc(uk+(ut?':'+ut:''))+'</td><td>'+esc(ue)+
          '</td><td class="num">\u2026</td><td class="pikkuteksti">p\u00e4ivit\u00e4 sivu</td>';
        MUOKKAUS=null;
      });
    return;}
  if(ev.target.id==='ol-lisaa'){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kirjaus:{pvm:document.getElementById('ol-pvm').value,
        kuvaus:document.getElementById('ol-kuvaus').value,
        maksaja:document.getElementById('ol-maksaja').value,
        summa:document.getElementById('ol-summa').value,
        osallistujat:Array.prototype.slice.call(document.querySelectorAll('.ol-osall'))
          .filter(function(x){return x.checked;}).map(function(x){return x.value;})}})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','kirjaus lis\u00e4tty \u2713');});
    return;}
  if(ev.target.id==='ol-nayta'){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nayta_alku:document.getElementById('ol-nayta-alku').value,
        nayta_loppu:document.getElementById('ol-nayta-loppu').value})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','jakso rajattu \u2713');});
    return;}
  if(ev.target.id==='ol-tasaa'){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    const tp=document.getElementById('ol-tasattu').value;
    if(!tp){alert('anna p\u00e4iv\u00e4m\u00e4\u00e4r\u00e4');return;}
    if(!confirm('Aloitetaanko uusi kausi '+tp+' alkaen? Aiempi kausi katsotaan tasatuksi.')){return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({tasattu:tp})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','uusi kausi aloitettu \u2713');});
    return;}
  if(ev.target.id==='ol-vk-lisaa'){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({hyvitys:{kuvaus:document.getElementById('ol-vk-kuvaus').value,
        jasenelta:document.getElementById('ol-vk-jasen').value,
        summa_kk:document.getElementById('ol-vk-summa').value,
        kk_max:document.getElementById('ol-vk-kk').value}})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','vakio lis\u00e4tty \u2713');});
    return;}
  const ops=ev.target.closest('.olpoissulje');
  if(ops){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({poissulje:ops.getAttribute('data-rid')})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','rivi suljettu pois \u2713');});
    return;}
  const oom=ev.target.closest('.olotamukaan');
  if(oom){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ota_mukaan:oom.getAttribute('data-rid')})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','rivi otettu mukaan \u2713');});
    return;}
  const ov=ev.target.closest('.olvakiopoisto');
  if(ov){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    if(!confirm('Poistetaanko vakio?')){return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({hyvitys_poista:parseInt(ov.getAttribute('data-i'),10)})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','vakio poistettu \u2713');});
    return;}
  const op=ev.target.closest('.olpres');
  if(op){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({lasna_vk:op.getAttribute('data-vk'),lasna_nimi:op.getAttribute('data-nimi'),
        lasna_arvo:op.getAttribute('data-arvo')==='1'?0:1})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous');});
    return;}
  const od=ev.target.closest('.olpoisto');
  if(od){ev.preventDefault();
    if(!SERVER){alert('Muokkaus vaatii selaa-tilan.');return;}
    if(!confirm('Poistetaanko kirjaus?')){return;}
    fetch('api/olympos',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kirjaus_poista:parseInt(od.getAttribute('data-i'),10)})})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        paivitaSivu('yhteistalous','kirjaus poistettu \u2713');});
    return;}
  const kp=ev.target.closest('.katpoisto');
  if(kp){ev.preventDefault();
    if(!SERVER){alert('Poisto vaatii selaa-tilan.');return;}
    const pkat=kp.getAttribute('data-kat');
    const kd=DATA.kat[pkat]||{};let pn=0;Object.keys(kd).forEach(function(m){pn+=kd[m].length;});
    let korvaava='';
    if(pn>0){
      korvaava=prompt('Kategoriassa "'+pkat+'" on '+pn+' rivi\u00e4 \u2014 anna korvaava kategoria '+
        '(Kategoria tai Kategoria:tarkenne, tai TARKISTA = rivit avoimeksi):','TARKISTA');
      if(korvaava===null||!korvaava.trim()){return;}
    }else if(!confirm('Poistetaanko tyhj\u00e4 kategoria "'+pkat+'"?')){return;}
    fetch('api/kategoria-poista',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({nimi:pkat,korvaava:korvaava.trim()})})
      .then(function(r){return r.json();}).then(function(v){
        if(v.tarvitaan_korvaava){alert('Kategoriassa on '+v.rivit+' rivi\u00e4 \u2014 anna korvaava kategoria.');return;}
        if(!v.ok){alert(v.virhe||'virhe');return;}
        try{sessionStorage.setItem('rahaputki_viesti','kategoria "'+pkat+'" poistettu \u2713'+
          (v.siirretty?' \u2014 '+v.siirretty+' rivi\u00e4 siirretty':''));}catch(err){}
        location.hash='';location.reload();
      });
    return;}
  const sj=ev.target.closest('.saantosija');
  const ss=ev.target.closest('.saantosiirto')||sj;
  if(ss){ev.preventDefault();
    if(!SERVER){alert('J\u00e4rjestely vaatii selaa-tilan (tai muokkaa saannot.csv:t\u00e4 suoraan).');return;}
    const runko=saannonTiedot(ss);
    const n=document.querySelectorAll('.saantorivi').length;
    if(sj){
      const uusiSija=prompt('Siirr\u00e4 s\u00e4\u00e4nt\u00f6 sijaintiin (1\u2013'+n+'):',
        ss.textContent.trim());
      if(uusiSija===null){return;}
      const luku=parseInt(uusiSija,10);
      if(!luku||luku<1){alert('anna numero 1\u2013'+n);return;}
      runko.kohde=luku;
    }else{
      const st=ss.getAttribute('data-suunta');
      if(st==='alkuun'){runko.kohde=1;}
      else if(st==='loppuun'){runko.kohde=n;}
      else{runko.suunta=parseInt(st,10);}
    }
    fetch('api/saanto-siirra',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(runko)})
      .then(function(r){return r.json();}).then(function(v){
        if(!v.ok){alert(v.virhe||'virhe');return;}
        try{sessionStorage.setItem('rahaputki_korosta',runko.malli);}catch(err){}
        paivitaSivu('saannot','j\u00e4rjestys muutettu \u2713'+
          (v.muuttui?' \u2014 '+v.muuttui+' rivi\u00e4 luokittui uudelleen':''));
      });
    return;}
  const sm=ev.target.closest('.saantomuokkaus');
  if(sm){ev.preventDefault();muokkaaRivi(sm.closest('tr'),sm);return;}
  const sp=ev.target.closest('.saantopoisto');
  if(sp){ev.preventDefault();
    const tiedot=saannonTiedot(sp);
    const malli=tiedot.malli,katr=tiedot.kategoria,ehto=tiedot.ehto;
    const kayttoja=sp.closest('tr').getAttribute('data-n')||'0';
    if(!confirm('Poistetaanko s\u00e4\u00e4nt\u00f6  '+malli+' \u2192 '+katr+'  ?'+
      String.fromCharCode(10)+'Se on perusteena '+kayttoja+' rivill\u00e4 \u2014 ne arvioidaan '+
      'uudelleen ja voivat palata avoimiksi. K\u00e4sin luokiteltuja ei muuteta.')){return;}
    const tr=sp.closest('tr');
    if(SERVER){
      fetch('api/saanto-poista',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({malli:malli,kategoria:katr,ehto:ehto})})
        .then(function(r){return r.json();}).then(function(v){
          if(v.ok){paivitaSivu('saannot','s\u00e4\u00e4nt\u00f6 poistettu \u2713 \u2014 '+
            v.muuttui+' rivi\u00e4 arvioitu uudelleen, '+v.avoimeksi+' palasi avoimeksi');}
          else{alert(v.virhe||'virhe');}
        });
    }else{
      MUUT.poistot.push({malli:malli,kategoria:katr});
      tr.classList.add('poistettu');paivitaPalkki();
    }
    return;}
  const sl=ev.target.closest('.saantolinkki');
  if(sl){ev.preventDefault();
    const f=document.getElementById('sf-malli');
    if(f){f.value=sl.getAttribute('data-saaja').toLowerCase();f.scrollIntoView({block:'center'});f.focus();
      osumalaskuri(f.value,'sf-osuma',0);}
    return;}
  const spe=ev.target.closest('#sf-peru');
  if(spe){ev.preventDefault();peruSaantomuokkaus();return;}
  const pr=ev.target.closest('.perus');
  if(pr){
    const pt=pr.getAttribute('title')||'?';
    const ptr=pr.closest('tr');
    if(pr.classList.contains('saantoperus')){
      ev.preventDefault();
      const malli=pt.split(String.fromCharCode(10))[0].split(' \u2192 ')[0].slice(8);
      if(muokkaaSaantoaLomakkeella(malli)){return;}
    }
    if(SERVER&&(pt==='k\u00e4sin'||pt==='oletus')&&ptr&&ptr.id&&ptr.id.indexOf('rivi-')===0){
      if(confirm('peruste: '+pt+String.fromCharCode(10)+
        'Vapautetaanko rivi s\u00e4\u00e4nn\u00f6ille? K\u00e4sin-suoja poistuu ja rivi '+
        'luokittuu heti sen hetken s\u00e4\u00e4nt\u00f6jen mukaan (tai palaa avoimeksi).')){
        vapautaRivi(ptr.id.slice(5));
      }
    }else{merkitse(null,'peruste: '+pt);}
    return;
  }
  const su=ev.target.closest('#psulje');
  if(su){ev.preventDefault();sulje();return;}
  const kb=ev.target.closest('[data-laji]');
  if(kb){kuukausi(kb.getAttribute('data-kkm'), kb.getAttribute('data-laji'));return;}
  const el=ev.target.closest('[data-kat]');
  if(!el)return;
  if(el.closest('#tutki-details'))return;
  if(el.tagName==='A'){ev.preventDefault();}
  avaa(el.getAttribute('data-kat'), el.getAttribute('data-kk')||undefined,
    el.getAttribute('data-tark')||undefined);
});
let HAKU_AJASTIN=null;
document.addEventListener('input',function(ev){
  if(ev.target.id==='haku'){
    if(HAKU_AJASTIN){clearTimeout(HAKU_AJASTIN);}
    const arvo=ev.target.value;
    HAKU_AJASTIN=setTimeout(function(){haku(arvo);},400);
    return;
  }
  if(ev.target.id==='sf-malli'){osumalaskuri(ev.target.value,'sf-osuma');return;}
  if(ev.target.id==='mk-malli'){osumalaskuri(ev.target.value,'mk-osuma');return;}
  if(ev.target.id!=='sf-suodata')return;
  const suodatin=ev.target.value.toLowerCase();
  document.querySelectorAll('#saantotaulu tr.saantorivi').forEach(function(tr){
    tr.style.display=tr.textContent.toLowerCase().indexOf(suodatin)>=0?'':'none';
  });
});
window.addEventListener('beforeunload',function(ev){
  const n=Object.keys(MUUT.rivit).length+MUUT.saannot.length+MUUT.poistot.length;
  if(!SERVER&&n){ev.preventDefault();ev.returnValue='';}
});
window.addEventListener('DOMContentLoaded',function(){
  try{
    const vm=sessionStorage.getItem('rahaputki_viesti');
    if(vm){merkitse(null,vm);sessionStorage.removeItem('rahaputki_viesti');}
  }catch(err){}
  const h=location.hash.slice(1);
  if(h==='yhteistalous'){const d=document.getElementById('yhteistalous');
    if(d){d.open=true;if(d.scrollIntoView){d.scrollIntoView();}}}
  if(h==='saannot'){
    const d=document.getElementById('saannot');
    if(d){d.open=true;
      let km=null;
      try{km=sessionStorage.getItem('rahaputki_korosta');sessionStorage.removeItem('rahaputki_korosta');}catch(err){}
      let loytyi=false;
      if(km){
        document.querySelectorAll('tr.saantorivi').forEach(function(rt){
          if(!loytyi&&rt.getAttribute('data-malli')===km){
            rt.classList.add('korostettu');rt.scrollIntoView({block:'center'});loytyi=true;
          }
        });
      }
      if(!loytyi){d.scrollIntoView();}
    }
  }else if(h.indexOf('haku=')===0){
    const ht=decodeURIComponent(h.slice(5));
    const kentta=document.getElementById('haku');
    if(kentta){kentta.value=ht;}
    haku(ht);
  }else if(h.indexOf('kklaji=')===0){
    const osat=h.split('&');
    kuukausi((osat[1]||'').slice(4), osat[0].slice(7));
  }else if(h.indexOf('kat=')===0){
    const osat=h.split('&');
    const hk=decodeURIComponent(osat[0].slice(4));
    let hkk,htark;
    osat.slice(1).forEach(function(o){
      if(o.slice(0,3)==='kk='){hkk=o.slice(3);}
      else if(o.slice(0,5)==='tark='){htark=decodeURIComponent(o.slice(5));}});
    if(DATA.kat[hk]){avaa(hk,hkk,htark);}
  }
  document.addEventListener('focusin',function(ev){
    const el=ev.target;
    if(!el.classList||!el.classList.contains('tarkinp')){return;}
    let s=null;const ymp=el.closest?el.closest('tr'):null;
    if(ymp){s=ymp.querySelector('select.katsel');}
    if(!s&&el.id==='sf-tark'){s=document.querySelector('.katsel[data-id="__saanto__"]');}
    if(!s&&el.id==='mk-tark'){s=document.querySelector('.katsel[data-id="__muok__"]');}
    if(!s&&el.id==='massa-tark'){s=document.querySelector('.katsel[data-id="__massa__"]');}
    if(!s&&el.dataset.id){s=document.querySelector('.katsel[data-id="'+el.dataset.id+'"]');}
    const dl=document.getElementById('tarklist');dl.innerHTML='';
    const kat=s?s.value:'';
    (TARKKAT[kat]||[]).forEach(function(t){const o=document.createElement('option');o.value=t;dl.appendChild(o);});
  });
  function palvelinSuljettu(){
    if(document.getElementById('suljettu'))return;
    SERVER=false;
    document.getElementById('tila').textContent='selaa-tila p\u00e4\u00e4ttyi';
    window.close();  // toimii vain jos selain on itse avannut t\u00e4m\u00e4n ikkunan
    var d=document.createElement('div');d.id='suljettu';
    d.setAttribute('style','position:fixed;inset:0;z-index:9999;display:flex;'+
      'align-items:center;justify-content:center;background:rgba(0,0,0,.72)');
    d.innerHTML='<div style="background:#fff;color:#222;max-width:30em;padding:2em;'+
      'border-radius:12px;font:16px/1.5 system-ui,sans-serif;text-align:center">'+
      '<h2 style="margin:0 0 .5em">Rahaputki suljettu</h2>'+
      '<p style="margin:0 0 .5em">Selaa-tila p\u00e4\u00e4ttyi, eiv\u00e4tk\u00e4 '+
      'muutokset en\u00e4\u00e4 tallennu.</p>'+
      '<p style="margin:0">Voit sulkea t\u00e4m\u00e4n v\u00e4lilehden.</p></div>';
    document.body.appendChild(d);
  }
  function valvoPalvelinta(){
    // Ctrl-C lopettaa palvelimen, mutta selain j\u00e4\u00e4 auki n\u00e4ytt\u00e4m\u00e4\u00e4n
    // sivua, joka ei en\u00e4\u00e4 tallenna mit\u00e4\u00e4n. Kysyt\u00e4\u00e4n kahden sekunnin
    // v\u00e4lein; kun vastaus j\u00e4\u00e4 kahdesti tulematta, kerrotaan se heti eik\u00e4
    // vasta seuraavan klikkauksen ep\u00e4onnistuessa.
    var hukassa=0;
    setInterval(function(){
      fetch('api/ping',{cache:'no-store'}).then(function(r){
        hukassa=r.ok?0:hukassa+1;
      }).catch(function(){hukassa++;}).then(function(){
        if(hukassa>=2)palvelinSuljettu();
      });
    },2000);
  }
  function lokiPaneeli(){return document.getElementById('ajoloki');}
  function naytaLoki(otsikko){
    var p=lokiPaneeli();p.hidden=false;
    document.getElementById('ajoloki-otsikko').textContent=otsikko;
  }
  function seuraaAjoa(komento,alkaen){
    fetch('api/loki?alkaen='+alkaen,{cache:'no-store'}).then(function(r){return r.json();})
      .then(function(v){
        if(!v.ok)return;
        var teksti=document.getElementById('ajoloki-teksti');
        if(v.rivit.length){teksti.textContent+=v.rivit.join('\\n')+'\\n';
          teksti.scrollTop=teksti.scrollHeight;}
        if(v.kaynnissa){setTimeout(function(){seuraaAjoa(komento,v.seuraava);},700);return;}
        const nimi=komento==='hae'?'Haku':'Tiliotteiden luku';
        naytaLoki(v.virhe?(nimi+' keskeytyi'):(nimi+' valmis'));
        document.getElementById('ajoloki-nappi').hidden=false;
        napitKaytossa(true);
      }).catch(function(){
        // Palvelin katosi kesken ajon — valvoPalvelinta kertoo sen omalla tavallaan.
        napitKaytossa(true);
      });
  }
  function napitKaytossa(paalle){
    ['nappi-hae','nappi-aja'].forEach(function(id){
      const n=document.getElementById(id);
      if(n.classList.contains('pois'))return;  // ei pankkiyhteyttä: pysyy poissa
      n.disabled=!paalle;});
  }
  function kaynnista(komento){
    napitKaytossa(false);
    document.getElementById('ajoloki-teksti').textContent='';
    document.getElementById('ajoloki-nappi').hidden=true;
    naytaLoki(komento==='hae'?'Haetaan pankista…':'Luetaan inbox-kansiota…');
    fetch('api/komento',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({komento:komento})}).then(function(r){return r.json();})
      .then(function(v){
        if(!v.ok){naytaLoki(v.virhe||'ei onnistunut');napitKaytossa(true);return;}
        seuraaAjoa(komento,0);
      }).catch(function(e){naytaLoki('ei onnistunut: '+e);napitKaytossa(true);});
  }
  function eur(n){return (Math.round(n*100)/100).toFixed(2).replace('.',',');}
  function tasmaytysteksti(v){
    if(v.ankkuri===null||v.ankkuri===undefined){
      return 'Pankissa '+eur(v.pankissa)+' \u20ac. Ensimm\u00e4inen t\u00e4sm\u00e4ytys asettaa '+
             'ankkurin \u2014 vertailu alkaa siit\u00e4.';}
    if(v.ero===0){return '\u2713 T\u00e4sm\u00e4\u00e4: pankissa '+eur(v.pankissa)+' \u20ac.';}
    return 'Pankissa '+eur(v.pankissa)+' \u20ac, odotettu '+eur(v.odotettu)+
           ' \u20ac \u2014 ero '+eur(v.ero)+' \u20ac.';
  }
  function tasmayta(tr,idx){
    const solu=tr.lastElementChild;
    solu.textContent='haetaan saldoa\u2026';
    fetch('api/tasmayta',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({idx:idx})}).then(function(r){return r.json();}).then(function(v){
        if(!v.ok){solu.textContent=v.virhe||'ei onnistunut';return;}
        solu.textContent=tasmaytysteksti(v)+(v.varaukset_mukana?
          ' (saldo sis\u00e4lt\u00e4\u00e4 varaukset, ne ovat mukana my\u00f6s vertailussa)':'');
        const b=document.createElement('button');
        b.type='button';b.className='tasmnappi';
        b.textContent=(v.ero===0||v.ankkuri==null)?'Ankkuroi':'Hyv\u00e4ksy ero ja ankkuroi';
        b.onclick=function(){
          solu.textContent='ankkuroidaan\u2026';
          fetch('api/ankkuroi',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({idx:idx})}).then(function(r){return r.json();}).then(function(w){
              solu.textContent=w.ok?('ankkuroitu '+eur(w.pankissa)+' \u20ac'):(w.virhe||'virhe');
            });
        };
        solu.appendChild(document.createTextNode(' '));solu.appendChild(b);
      }).catch(function(e){solu.textContent='ei onnistunut: '+e;});
  }
  document.addEventListener('click',function(ev){
    const n=ev.target.closest('.tasmnappi');
    if(!n||!n.closest('tr[data-tili-idx]'))return;
    if(n.onclick)return;
    ev.preventDefault();
    const tr=n.closest('tr[data-tili-idx]');
    tasmayta(tr,parseInt(tr.getAttribute('data-tili-idx'),10));
  });
  document.getElementById('nappi-hae').addEventListener('click',function(){kaynnista('hae');});
  document.getElementById('nappi-aja').addEventListener('click',function(){kaynnista('aja');});
  document.getElementById('ajoloki-nappi').addEventListener('click',function(){location.reload();});
  document.getElementById('ajoloki-piilota').addEventListener('click',function(){
    lokiPaneeli().hidden=true;});
  fetch('api/ping').then(function(r){return r.json();}).then(function(v){
    if(v.ok){SERVER=true;document.getElementById('tila').textContent=
      'selaa-tila \u2713 muutokset tallentuvat heti';
      document.getElementById('ajonapit').hidden=false;
      document.querySelectorAll('.tasmnappi').forEach(function(b){b.hidden=false;});
      valvoPalvelinta();}
  }).catch(function(){
    document.getElementById('tila').textContent=
      'tiedostotila: muokkaukset ker\u00e4t\u00e4\u00e4n ja ladataan muutokset.csv:n\u00e4';
  });
});
</script>"""
    skripti = (skripti.replace("__DATA__", data_js)
               .replace("__KAT__", kat_js)
               .replace("__TARKENTEET__", tarkenteet_js)
               .replace("__TARKKAT__", tarkkat_js)
               .replace("__SAANTOEHDOT__", saantoehdot_js)
               .replace("__SAANTOTIEDOT__", saantotiedot_js))

    sivu = f"""<!DOCTYPE html>
<html lang="fi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rahaputki — kuukausiraportti</title>
<style>
:root {{ --muste:#26241f; --paperi:#f7f5f0; --vaalea:#eae6dd; --tulo:#2e7d5b; --meno:#b3502d; }}
* {{ box-sizing:border-box }}
body {{ font:15px/1.5 "Iowan Old Style","Palatino Linotype",Georgia,serif; color:var(--muste);
       background:var(--paperi); margin:0; padding:2rem 1rem 4rem; }}
main {{ max-width:980px; margin:0 auto }}
h1 {{ font-size:1.7rem; margin:0 0 .2rem; letter-spacing:.01em }}
h2 {{ font-size:1.05rem; margin:2.2rem 0 .6rem; text-transform:uppercase; letter-spacing:.09em }}
.meta {{ color:#6b665c; margin:0 0 1.4rem }}
svg {{ width:100%; height:auto; display:block }}
.aks {{ font:11px ui-monospace,Menlo,monospace; fill:#6b665c }}
table {{ border-collapse:collapse; width:100%; font-size:.92rem;
         font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace }}
th,td {{ padding:.3rem .55rem; text-align:left; border-bottom:1px solid var(--vaalea) }}
td.num,th {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap }}
.pvm2 {{ white-space:nowrap; color:#6b665c }}
.tili2 {{ color:#a39d92; font-size:.74rem; white-space:nowrap }}
th:first-child,td:first-child {{ text-align:left; font-family:inherit }}
tr.summa td {{ border-top:2px solid var(--muste); font-weight:700 }}
.plus {{ color:var(--tulo) }} .miinus {{ color:var(--meno) }}
text.plus {{ fill:var(--tulo) }} text.miinus {{ fill:var(--meno) }}
.klik {{ cursor:pointer; text-decoration:underline dotted 1px; text-underline-offset:3px }}
.klik:hover {{ background:#efe9df }}
td.num.klik {{ text-decoration:none }}
#paneeli {{ display:none; margin:1rem 0 }}
.pkortti {{ background:#fffdf8; border:1px solid var(--vaalea); border-left:4px solid var(--meno);
            padding:1rem 1.1rem; }}
.privi {{ display:flex; justify-content:space-between; align-items:baseline; gap:1rem; margin-bottom:.5rem }}
.kkots td {{ font-weight:700; background:#f1ede4 }}
.tark {{ color:#6b665c }}
.selite2 {{ color:#a39d92; font-size:.62rem; line-height:1.15; margin-top:.05rem }}
.selite2.tarkselite {{ color:#4a463f; font-size:.78rem }}
#tutki {{ display:flex; gap:1rem; align-items:flex-start; flex-wrap:wrap }}
#tutki-puu {{ flex:0 0 15rem; height:26rem; overflow-y:auto; border:1px solid #d9d3c8;
  border-radius:8px; padding:.5rem .6rem; background:#fbf9f5 }}
#tutki-kuva {{ flex:1 1 26rem; min-width:22rem }}
#tutki-svg {{ min-height:19rem }}
@media (max-width:640px) {{
  body {{ padding:1rem .6rem 3rem }}
  h2 {{ margin:1.6rem 0 .5rem }}
  table {{ font-size:.86rem }}
  .palkki {{ min-width:70px }}
  #tutki {{ flex-direction:column }}
  #tutki-puu {{ flex:1 1 auto; width:100%; height:14rem }}
  #tutki-kuva {{ flex:1 1 auto; width:100%; min-width:0 }}
  #tutki-svg {{ min-height:12rem }}
}}
#tutki-ohjaus {{ display:flex; gap:.5rem; align-items:center; margin-bottom:.4rem; flex-wrap:wrap }}
#tutki-ohjaus button {{ font:inherit; padding:.2rem .6rem; border:1px solid #c9c3b8;
  background:#fff; border-radius:6px; cursor:pointer }}
#tutki-ohjaus button:hover {{ background:#f0ece4 }}
.tutki-katrivi {{ display:flex; align-items:center; gap:.3rem; padding:.1rem 0; cursor:pointer }}
.tutki-katrivi:hover {{ background:#f0ece4 }}
.tutki-nuoli {{ width:1rem; color:#8a857c; user-select:none }}
.tutki-tark {{ margin-left:1.3rem; font-size:.85em; color:#5a554c; cursor:pointer;
  padding:.05rem 0; display:flex; align-items:center; gap:.3rem }}
.tutki-tark:hover {{ background:#f0ece4 }}
.tutki-lammas {{ width:.7rem; height:.7rem; border-radius:2px; display:inline-block; flex:0 0 auto }}
#tutki-legenda {{ display:flex; flex-wrap:wrap; gap:.4rem .8rem; margin-top:.5rem; font-size:.82em }}
#tutki-legenda span {{ display:inline-flex; align-items:center; gap:.3rem }}
.tutki-tark.piilossa {{ display:none }}
.palkki {{ position:relative; background:var(--vaalea); height:10px; min-width:120px; border-radius:5px }}
.palkki .taytto {{ background:var(--tulo); height:100%; border-radius:5px }}
.palkki .taytto.yli {{ background:var(--meno) }}
.palkki i {{ position:absolute; top:-2px; width:2px; height:14px; background:var(--muste) }}
.palkki.tyhja {{ opacity:.35 }}
.huomio {{ background:#f3e3c8; padding:.6rem .9rem; border-radius:6px }}
.huono {{ color:#b3502d; font-weight:bold }}
/* Sääntötaulu: toimintosarake yhdelle riville, pitkä regex katkeaa —
   muuten rivi venyy kolmen tekstirivin korkuiseksi ja taulu vaakavieritykseen. */
#saantotaulu td:nth-child(2) {{ word-break:break-word; max-width:24rem }}
#saantotaulu td:last-child {{ white-space:nowrap }}
#saantotaulu td:last-child a {{ text-decoration:none }}
#saantotaulu td:last-child a.saantopoisto,
#saantotaulu td:last-child a.saantomuokkaus {{ text-decoration:underline }}
.varaushuomio {{ background:#e6eef5 }}
.perus.saantoperus {{ cursor:pointer; border-bottom:1px dotted #9a8f7d }}
.perus.saantoperus:hover {{ color:#1a5fa8; border-bottom-color:#1a5fa8 }}
#sf-peru {{ margin-left:.4rem; font-size:.8rem }}
.varausmerkki {{ background:#dbe6f0; color:#2c4a63; font-size:.68rem;
                 padding:.05rem .35rem; border-radius:4px; vertical-align:.08em;
                 letter-spacing:.02em }}
tr.varausrivi td {{ background:#f7fafc }}
.pikkuteksti {{ color:#6b665c; font-size:.85rem }}
.tyokalut {{ display:flex; gap:.8rem; align-items:baseline; flex-wrap:wrap; margin:.6rem 0 }}
#ajonapit button, #ajonapit a, #ajoloki button {{ font:inherit; font-size:.85em;
       padding:.2rem .7rem; border:1px solid #c9c3b8; border-radius:5px; background:#fff;
       cursor:pointer; text-decoration:none; color:inherit; display:inline-block }}
#ajonapit button:hover:enabled, #ajonapit a:hover, #ajoloki button:hover {{ background:var(--vaalea) }}
#ajonapit button:disabled {{ opacity:.45; cursor:not-allowed }}
.tasmnappi {{ font:inherit; font-size:.8em; padding:.1rem .5rem; margin-left:.5rem;
       border:1px solid #c9c3b8; border-radius:5px; background:#fff; cursor:pointer }}
.tasmnappi:hover {{ background:var(--vaalea) }}
.uusilinkki {{ margin-left:.4rem; font-size:.85em }}
#ajoloki {{ border:1px solid #c9c3b8; border-radius:8px; background:#fff;
       padding:.7rem .9rem; margin:.6rem 0 }}
#ajoloki-teksti {{ font:12px/1.5 ui-monospace,Menlo,monospace; white-space:pre-wrap;
       max-height:14rem; overflow:auto; margin:.3rem 0 .6rem }}
.katsel {{ font-size:.78rem; max-width:11em }}
.spark svg {{ width:150px; height:34px; display:block }}
.tarkinp {{ font-size:.78rem; width:7em; text-transform:lowercase }}
.minp {{ font-size:.78rem }}
.perus {{ color:#8a857c; cursor:help }}
.saantolinkki {{ font-size:.78rem }}
tr.tallennettu td {{ background:#e4efe7 }}
tr.valittu td {{ background:#e3ddcf }}
#massapalkki {{ display:none; gap:.5rem; align-items:center; flex-wrap:wrap;
  margin:.5rem 0; font-size:.85rem; position:sticky; top:0; z-index:5;
  background:#fffdf8; padding:.4rem 0; border-bottom:1px solid var(--vaalea) }}
#massapalkki button {{ font-size:.82rem }}
#muutospalkki {{ display:none; position:fixed; left:0; right:0; bottom:0; background:var(--muste);
  color:var(--paperi); padding:.6rem 1rem; text-align:center; font-size:.9rem }}
#muutospalkki button {{ font-size:.9rem; margin-left:.8rem }}
#saannot summary, #yhteistalous summary {{ cursor:pointer; margin:2.2rem 0 .6rem }}
#sf-suodata {{ font-size:.85rem; margin:.4rem 0 }}
#haku {{ font-size:.85rem }}
tr.poistettu td {{ text-decoration:line-through; opacity:.5 }}
.sform {{ display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; margin:.6rem 0;
  font-size:.85rem }}
.sform input,.sform select,.sform button {{ font-size:.82rem }}
code {{ font-family:ui-monospace,Menlo,monospace }}
</style></head><body><main>
<h1>Rahaputki</h1>
<p class="meta">Rahaputki {VERSIO} · päivitetty {date.today().strftime('%d.%m.%Y')} · {len(ledger)} tapahtumaa ·
kategorian nimeä, matriisin solua tai kaavion palkkia klikkaamalla pääset katsomaan ja muokkaamaan rivejä</p>
{huomio}
<div class="tyokalut"><input id="haku" type="search" placeholder="hae tapahtumia… (Esc tyhjentää)" size="26"><span id="tila" class="pikkuteksti"></span><span id="ajonapit" hidden> <button type="button" id="nappi-hae"{hae_pois}>Hae pankkitapahtumat</button> <button type="button" id="nappi-aja">Lue tiliotteet</button> <a href="velho" id="nappi-velho">Yhdistä pankkeihin</a></span></div>
<div id="ajoloki" hidden><div id="ajoloki-otsikko" class="pikkuteksti"></div><pre id="ajoloki-teksti"></pre><button type="button" id="ajoloki-nappi" hidden>Päivitä raportti</button> <button type="button" id="ajoloki-piilota">Piilota</button></div>
<div id="paneeli"></div>
<h2>Tulot ja menot kuukausittain <span class="pikkuteksti">(vihreä = tulot, ruskea = menot, tumma viiva = menojen 3 kk liukuva keskiarvo, % = säästöaste)</span></h2>
{kaavio}
<details id="tutki-details"><summary><h2 style="display:inline">Tutki kategorioita</h2> <span class="pikkuteksti">— valitse puusta kategorioita ja tarkenteita, piirtyvät kuukausien yli omilla väreillään</span></summary>
<div id="tutki">
  <div id="tutki-puu"></div>
  <div id="tutki-kuva">
    <div id="tutki-ohjaus">
      <button id="tutki-tila" data-tila="stacked">Pinottu ↔ Rinnakkain</button>
      <button id="tutki-tyhjaa">Tyhjennä</button>
      <span id="tutki-selite" class="pikkuteksti"></span>
    </div>
    <div id="tutki-svg"></div>
    <div id="tutki-legenda"></div>
  </div>
</div>
</details>
<h2>Koko historia {jakso[0]} – {jakso[1]}</h2>
<div style="overflow-x:auto"><table><tr><th>Kategoria</th><th>Kehitys</th><th>Yhteensä €</th>
<th>Keskim. €/kk</th><th>Mediaani €/kk</th><th>Keskim. €/v</th><th>Trendi €/kk</th></tr>
{koonti_html}</table></div>
<p class="pikkuteksti">Keskiarvot ja mediaanit on laskettu {n_kk} täydeltä kuukaudelta (kuluva kuukausi
ei mukana); Yhteensä-sarake sisältää kaiken. Kehitys-käyrän tumma viiva = 3 kk liukuva keskiarvo.
Mediaani = tyypillinen kuukausi — jos keskiarvo on selvästi mediaania suurempi, kategoria elää
piikeistä (vakuutukset, matkat) ja sitä kannattaa arvioida vuositasolla. Trendi = viimeisen 3 kk
keskiarvo miinus edeltävän 3 kk keskiarvo. {saasto_rivi}Sama taulukko: raportit/yhteenveto_koko.csv.</p>
<h2>{'Kuukausi ' + kohde[5:] + '/' + kohde[:4] + ' · toteuma vs. raami' if kohde else ''}</h2>
<div style="overflow-x:auto"><table><tr><th>Kategoria</th><th>Toteuma €</th><th>Raami €</th>
<th>Jäljellä €</th><th>%</th><th></th></tr>
{''.join(rivit_html)}</table></div>
<p class="pikkuteksti">Pystyviiva palkissa = raami. Raamit asetetaan tiedostossa budjetti.csv
(ehdotus toteumasta: <code>python3 kirjanpito.py budjetti-ehdotus</code>).</p>
{kertyvat_html}
{saldot_html}
<h2>Kategoriat × kuukaudet</h2>
<div style="overflow-x:auto"><table>{''.join(matriisi)}</table></div>
{olympos_html}
{yhteydet_html}
<details id="saannot"><summary><h2 style="display:inline">Säännöt ({saanto_n} kpl)</h2></summary>
<p class="pikkuteksti">Poisto arvioi säännön luokittelemat rivit uudelleen (voivat palata avoimiksi tai siirtyä toiselle säännölle); käsin luokiteltuja ei kosketa.
Uudet säännöt tehdään porautumisnäkymän lomakkeella.</p>
<input id="sf-suodata" placeholder="suodata sääntöjä…" size="28">
<div style="overflow-x:auto"><table id="saantotaulu"><tr><th>#</th><th>Malli</th><th>Kategoria</th><th>Ehto</th><th>Osuu</th><th>Perusteena</th><th></th></tr>
{saannot_html}</table></div></details>
<p class="pikkuteksti">Sama taulukko Sheets-liitosta varten: raportit/yhteenveto_kk.csv.
Siirrot omien tilien välillä, sijoitukset ja pois-tyyppiset kategoriat eivät ole mukana luvuissa.</p>
<datalist id="tarklist"></datalist>
<div id="muutospalkki"><span id="muutosteksti"></span> <button id="lataamuutokset">Lataa muutokset.csv</button></div>
</main>
{skripti}
</body></html>"""
    return sivu


def cmd_raportti(args):
    cfg = lue_config()
    ledger = lue_ledger()
    n_rev = _korjaa_revolut_selitteet(ledger)
    if n_rev:
        m_u, m_a = uudelleenluokittele_saantorivit(ledger, cfg)
        print(f"Korjattu Revolut-selitteet {n_rev} riviltä; {m_u} luokiteltu uudelleen "
              f"({m_a} palasi avoimeksi).")
    n_per = taydenna_perusteet(ledger, cfg)
    if n_per:
        print(f"Täydennetty luokitteluperuste {n_per} riville.")
    if n_rev or n_per:
        kirjoita_ledger(ledger)
        kirjoita_tarkistettavat(ledger)
    rakenna_raportit(ledger, cfg, kk=(0 if args.kaikki else args.kk))
    print(f"Raportti: {(RAPORTIT / 'raportti.html')}")


def cmd_budjetti(args):
    cfg = lue_config()
    ledger = lue_ledger()
    kuukaudet, taulu, tulot, menot = koosta(ledger, cfg)
    tanaan = date.today().isoformat()[:7]
    taydet = [m for m in kuukaudet if m < tanaan][-12:]
    if len(taydet) < 2:
        print("Tarvitaan vähintään kaksi täyttä kuukautta dataa ennen raamiehdotusta.")
        return
    tyypit = cfg["kategoriat"]
    print(f"Ehdotus {len(taydet)} täyden kuukauden mediaanista ({taydet[0]}…{taydet[-1]}):\n")
    rivit = []
    for k in sorted((k for k in taulu if tyypit.get(k, "meno") == "meno"),
                    key=lambda k: -statistics.median([taulu[k][m] for m in taydet])):
        med = statistics.median([taulu[k][m] for m in taydet])
        if med <= 0:
            continue
        ehdotus = round(med / 10) * 10 or 10
        rivit.append((k, ehdotus))
        print(f"  {k:<24} {fmt_eur(ehdotus):>10} €/kk   (mediaani {fmt_eur(med)})")
    polku = ASETUKSET / "budjetti_ehdotus.csv"
    puskuri = io.StringIO()
    w = csv.writer(puskuri, delimiter=";")
    w.writerow(["kategoria", "kk_raami"])
    w.writerows(rivit)
    turvakirjoita(polku, puskuri.getvalue())
    print(f"\nTallennettu: asetukset/{polku.name} — kopioi haluamasi rivit "
          "tiedostoon asetukset/budjetti.csv (ja muokkaa vapaasti).")


def cmd_kurkista(args):
    polku = Path(args.tiedosto)
    if not polku.exists():
        polku = INBOX / args.tiedosto
    teksti, enc = lue_teksti(polku)
    rivit = teksti.splitlines()
    erotin = ";" if rivit[0].count(";") >= rivit[0].count(",") else ","
    print(f"Tiedosto : {polku}\nEnkoodaus: {enc}\nErotin   : '{erotin}'\nOtsikot  :")
    for o in next(csv.reader([rivit[0]], delimiter=erotin)):
        print(f"  - {o}")
    cfg = lue_config()
    nimi, _ = tunnista_lahde(next(csv.reader([rivit[0]], delimiter=erotin)), cfg)
    print(f"Tunnistettu lähde: {nimi or 'EI TUNNISTETTU — lisää lähde config.json:iin yllä olevilla sarakenimillä'}")
    print("\nEnsimmäiset rivit:")
    for r in rivit[1:4]:
        print(f"  {r[:160]}")


def cmd_luokittele(args):
    """Aja säännöt uudelleen koko pääkirjalle (esim. saannot.csv:n käsimuokkauksen
    jälkeen). Käsin- ja oletus-luokiteltuja ei siirretä — niiden pakottamiseen
    käytä selaimen sääntölomaketta."""
    cfg = lue_config()
    ledger = lue_ledger()
    muuttui, avoimeksi = uudelleenluokittele_saantorivit(ledger, cfg)
    if not muuttui and not avoimeksi:
        print("Säännöt ajettu — mikään rivi ei muuttunut (käsin/oletus-rivejä ei siirretä).")
        return
    kirjoita_ledger(ledger)
    kirjoita_tarkistettavat(ledger)
    rakenna_raportit(ledger, cfg, kk=13)
    print(f"Säännöt ajettu: {muuttui} riviä luokittui uudelleen, {avoimeksi} palasi avoimeksi.")
    print("Huom: käsin (✎) ja oletus (◦) -rivejä ei siirretä — pakotus selaimen sääntölomakkeella.")


def cmd_siivoa_kopiot(args):
    """Poista rivit, jotka tulivat tiedostonimen '(1)'-kopiosta ja joilla on
    vastinpari alkuperäisestä lähteestä (sama tili+pvm+summa+saaja)."""
    ledger = lue_ledger()
    kopio_re = re.compile(r"\s\(\d+\)(?=\.\w+$|$)")
    avaimet_alkup = Counter()
    for r in ledger:
        if not kopio_re.search(r.get("lahde", "")):
            avaimet_alkup[avain(r["tili"], r["pvm"], float(r["summa"]), r["saaja"])] += 1
    poistetaan, kaytetty = [], Counter()
    for r in ledger:
        if not kopio_re.search(r.get("lahde", "")):
            continue
        av = avain(r["tili"], r["pvm"], float(r["summa"]), r["saaja"])
        if kaytetty[av] < avaimet_alkup[av]:
            kaytetty[av] += 1
            poistetaan.append(r)
    if not poistetaan:
        print("Kopiolähteiden tuplarivejä ei löytynyt — mitään ei muutettu.")
        return
    print(f"Poistetaan {len(poistetaan)} kopiolähteestä tuotua tuplariviä:")
    kuut = Counter((r["pvm"][:7], r["tili"]) for r in poistetaan)
    for (kk, tili), n in sorted(kuut.items()):
        summa = sum(float(r["summa"]) for r in poistetaan if r["pvm"][:7] == kk and r["tili"] == tili)
        print(f"  {kk} {tili:14} {n:>3} riviä {summa:>10.2f} €")
    idt = {id(r) for r in poistetaan}
    ledger[:] = [r for r in ledger if id(r) not in idt]
    cfg = lue_config()
    kirjoita_ledger(ledger)
    kirjoita_tarkistettavat(ledger)
    rakenna_raportit(ledger, cfg, kk=13)
    print(f"Valmis — pääkirjassa nyt {len(ledger)} riviä (varmuuskopio kansiossa data/varmuuskopiot).")


KORTIT_SPEC = {
    "OP Visa": {"tili_kortti": "OP-kortti", "era_paiva": "loppu", "minimi_pct": 2,
                "maksu_avaimet": ["vähittäisasiakkaat"]},
    "S-Pankki Visa": {"tili_kortti": "S-Pankki Visa", "era_paiva": 15, "minimi_pct": 4,
                      "maksu_avaimet": ["1194426", "s-pankki visa", "visa credit",
                                        "visa-luotto", "luoton maksu", "s-pankki oyj",
                                        "s-pankki ville",
                                        "55843 90027", "5584390027",
                                        "3939 0008 2005", "393900082005"]},
}


def kortti_summat(ledger):
    """Kortti -> (maksut_kk, tuodut_kk) täsmäytystä varten."""
    tulos = {}
    for nimi, k in KORTIT_SPEC.items():
        maksut = defaultdict(float)
        tuodut = defaultdict(lambda: [0, 0.0])
        for r in ledger:
            teksti = normalisoi(f"{r['saaja']} {r['selite']}")
            summa = float(r["summa"])
            if (r["tili"] in ("OP-tili", "S-Pankki") and summa < 0
                    and any(a in teksti for a in k["maksu_avaimet"])):
                maksut[r["pvm"][:7]] += -summa
            if r["tili"] == k["tili_kortti"]:
                t = tuodut[r["pvm"][:7]]
                t[0] += 1
                t[1] += -summa
        tulos[nimi] = (maksut, tuodut)
    return tulos


def cmd_tarkista_kortit(args):
    """Täsmäytä korttilaskujen maksut tileillä vs. tuodut korttirivit."""
    ledger = lue_ledger()
    summat = kortti_summat(ledger)
    kaikki_kk = sorted({r["pvm"][:7] for r in ledger})
    for nimi, (maksut, tuodut) in summat.items():
        print(f"\n═══ {nimi} ═══")
        if not maksut and not tuodut:
            print("  ei maksuja eikä tuotuja rivejä — jos kortti on käytössä, maksurivin "
                  "nimi ei osu hakusanoihin (kerro miltä maksu näyttää tiliotteella).")
            continue
        m_yht = t_yht = 0.0
        print(f"  {'kuukausi':10} {'maksettu €':>11} {'tuotu € (rivit)':>18}   huomio")
        for m in kaikki_kk:
            mk = maksut.get(m, 0.0)
            tn, ts = tuodut.get(m, [0, 0.0])
            m_yht += mk
            t_yht += ts
            huomio = ""
            edell = kaikki_kk[kaikki_kk.index(m) - 1] if kaikki_kk.index(m) > 0 else ""
            if mk > 0 and tn == 0 and tuodut.get(edell, [0, 0])[0] == 0:
                huomio = "⚠ maksu ilman tuotuja ostoja — lasku-PDF ajamatta?"
            elif tn > 0 and mk == 0:
                huomio = "(ostoja tuotu; lasku maksettaneen myöhemmin)"
            if mk or tn:
                print(f"  {m:10} {mk:>11.2f} {ts:>10.2f} ({tn:>3})   {huomio}")
        ero = m_yht - t_yht
        print(f"  {'YHTEENSÄ':10} {m_yht:>11.2f} {t_yht:>14.2f}")
        if abs(ero) > 5:
            print(f"  → täsmäyttämättä {ero:,.2f} € — noin tämän verran laskuja on vielä "
                  f"tuomatta (tai avointa saldoa).".replace(",", " "))
        else:
            print("  ✓ maksut ja tuodut rivit täsmäävät (±5 €).")
    print("\nHuom: laskutuskausi ei ole kalenterikuukausi, joten kuukausirivit ovat "
          "suuntaa-antavia — YHTEENSÄ-rivin erotus on luotettava mittari.")


def _kysely_luku(polku, nimi):
    """Yksi kokonaisluku osoitteen kyselyosasta. urllib.parse olisi tähän
    järeä, ja se tuotaisiin vain tämän takia."""
    for pala in polku.partition("?")[2].split("&"):
        avain, _, arvo = pala.partition("=")
        if avain == nimi and arvo.isdigit():
            return int(arvo)
    return 0


VELHO_SIVU = r"""<!doctype html>
<html lang="fi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rahaputki — pankkiyhteys</title>
<style>
:root { --muste:#26241f; --paperi:#f7f5f0; --vaalea:#eae6dd; --raja:#c9c3b8;
        --hyva:#2e7d5b; --huono:#b3502d; }
* { box-sizing:border-box }
body { font:15px/1.55 "Iowan Old Style","Palatino Linotype",Georgia,serif;
       color:var(--muste); background:var(--paperi); margin:0; padding:2rem 1rem 5rem }
main { max-width:900px; margin:0 auto; display:grid; grid-template-columns:210px 1fr;
       gap:2.5rem; align-items:start }
h1 { font-size:1.45rem; margin:0 0 .2rem; grid-column:1/-1 }
.johdanto { color:#6b665c; margin:0 0 1.6rem; grid-column:1/-1; max-width:62ch }
nav ol { list-style:none; margin:0; padding:0 }
nav li { margin:0 0 .2rem }
nav button { width:100%; text-align:left; font:inherit; background:none; cursor:pointer;
             line-height:1.3;
             border:1px solid transparent; border-radius:8px; padding:.55rem .7rem;
             display:flex; gap:.6rem; align-items:baseline }
nav button:hover { background:var(--vaalea) }
nav button[aria-current="step"] { background:#fff; border-color:var(--raja); font-weight:bold }
nav .nro { font:12px ui-monospace,Menlo,Consolas,monospace; color:#8a8578 }
nav .tila { display:block; font-size:.78em; color:#8a8578; font-weight:normal }
nav .valmis .tila { color:var(--hyva) }
nav .kesken .tila { color:var(--huono) }
section.paneeli { background:#fff; border:1px solid var(--raja); border-radius:10px;
                  padding:1.4rem 1.6rem }
h2 { font-size:1.05rem; margin:0 0 .25rem }
.selite { color:#6b665c; font-size:.92em; margin:0 0 1.1rem; max-width:60ch }
h3 { font-size:.95rem; margin:1.4rem 0 .4rem }
p { max-width:62ch }
button.toiminto { font:inherit; padding:.4rem .9rem; border:1px solid var(--raja);
                  border-radius:6px; background:#fff; cursor:pointer }
button.toiminto:hover:enabled { background:var(--vaalea) }
button.toiminto:disabled { opacity:.45; cursor:not-allowed }
button.paa { background:var(--muste); color:var(--paperi); border-color:var(--muste) }
button.paa:hover:enabled { background:#3d3a33 }
a.paalinkki { display:inline-block; text-decoration:none; color:var(--paperi);
              background:var(--muste); border-radius:6px; padding:.45rem 1rem }
input[type=text], textarea, select { font:inherit; width:100%; padding:.45rem .6rem;
       border:1px solid var(--raja); border-radius:6px; background:#fff }
textarea { min-height:5.5rem; font:12.5px/1.5 ui-monospace,Menlo,Consolas,monospace }
label { display:block; margin:.8rem 0 .3rem; font-size:.9em; color:#6b665c }
.rivi { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap; margin:.8rem 0 0 }
.viesti, .virhe { padding:.6rem .8rem; border-radius:6px; margin:0 0 1rem }
.viesti { background:#e6f0e9; border:1px solid #b7d4c3 }
.virhe { background:#f6e3dc; border:1px solid #dcae98 }
.kortti { border:1px solid var(--raja); border-radius:8px; padding:.8rem 1rem; margin:0 0 .6rem }
.kortti h4 { margin:0 0 .2rem; font-size:.95rem }
.kortti p { margin:0; font-size:.9em; color:#6b665c }
.valinta { cursor:pointer } .valinta:hover { background:var(--vaalea) }
.valinta[aria-pressed="true"] { border-color:var(--muste); background:#fbfaf7 }
table { width:100%; border-collapse:collapse; margin:.6rem 0 }
th, td { text-align:left; padding:.35rem .5rem .35rem 0; border-bottom:1px solid var(--vaalea) }
.pikku { font-size:.85em; color:#6b665c }
.ohjeet { margin:.4rem 0 .8rem; padding-left:1.3rem }
.ohjeet li { margin:0 0 .45rem; max-width:60ch }
.pankkilista { max-height:19rem; overflow:auto; border:1px solid var(--raja);
               border-radius:8px; margin:.6rem 0 }
.pankkilista button { display:block; width:100%; text-align:left; font:inherit;
       background:none; border:0; border-bottom:1px solid var(--vaalea);
       padding:.5rem .8rem; cursor:pointer }
.pankkilista button:hover { background:var(--vaalea) }
:focus-visible { outline:2px solid var(--muste); outline-offset:2px }
@media (max-width:720px) { main { grid-template-columns:1fr; gap:1.2rem } }
</style></head><body><main>
<h1>Pankkiyhteys</h1>
<p class="johdanto">Tapahtumat tulevat pankista suoraan koneellesi. Voit palata
mihin tahansa vaiheeseen ja muuttaa valintaa — mikään ei lukitu.</p>
<nav><ol id="rail"></ol></nav>
<section class="paneeli" id="paneeli"></section>
</main>
<script>
var T = null, kesken = false;
/* Avattu alilomake ja kenttien sisällöt pidetään muuttujissa, ei DOMissa:
   jokainen toiminto piirtää paneelin uusiksi, ja DOMiin jätetty tila katoaisi
   sen mukana. Juuri niin kävi: "Etsi koneelta" sulki lomakkeen ennen kuin
   löytynyttä avainta ehti valita. Kenttien arvot säilyvät samasta syystä —
   pitkää liitettyä komentoa ei saa joutua liittämään uudelleen virheen takia. */
var AVATTU = '';
var SYOTE = {curl:'', sposti:'', polku:'', haku:'', koodi:'', psu:'', appid:''};

function e(s){ var d=document.createElement('div'); d.textContent=s==null?'':String(s);
               return d.innerHTML; }
function el(id){ return document.getElementById(id); }

function toiminto(nimi, data){
  if(kesken) return;
  kesken = true; piirra();
  return fetch('api/velho', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(Object.assign({toiminto:nimi}, data||{}))})
    .then(function(r){ return r.json(); })
    .then(function(v){ T = v; kesken = false; piirra(); })
    .catch(function(err){ kesken = false;
      if(T) T.virhe = 'Yhteys palvelimeen katkesi: ' + err; piirra(); });
}

/* Vaiheen nimi kertoo mitä käyttäjä tekee, ei mitä ohjelma tallentaa.
   "Sovellus" oli toteutuksen sana: se on Enable Bankingin käsite, ei sen
   ihmisen, joka haluaa tilitapahtumansa näkyviin. Selite kertoo saman
   pidemmin, ja se näkyy paneelin otsikon alla — samasta listasta, jottei
   kahta kuvausta samasta vaiheesta pääse ajautumaan eri linjoille. */
var VAIHEET = [
  {avain:'sovellus', nimi:'Yhdistä Enable Banking',
   selite:'Rekisteröi Rahaputki-sovellus Enable Bankingin rajapintaan. Tehdään kerran.'},
  {avain:'pankit', nimi:'Yhdistä pankit',
   selite:'Valtuuta tapahtumien haku pankeistasi. Valtuutus uusitaan 90–180 päivän välein.'},
  {avain:'valmis', nimi:'Valmis',
   selite:'Pankkiyhteys on kytketty ja tapahtumat voi hakea.'}
];

function vaiheOtsikko(avain){
  var v = VAIHEET.filter(function(x){ return x.avain === avain; })[0];
  return '<h2>' + e(v.nimi) + '</h2><p class="selite">' + e(v.selite) + '</p>';
}

function vaiheenTila(v){
  if(v === 'sovellus'){
    if(T.sovellus.varmistettu) return ['valmis', 'yhteys toimii'];
    if(T.sovellus.app_id) return ['kesken', 'tarkistamatta'];
    return ['', 'ei vielä tehty'];
  }
  if(v === 'pankit'){
    var n = T.yhdistetyt.length;
    if(!n) return ['', 'ei pankkeja'];
    var huono = T.yhdistetyt.filter(function(p){ return p.paivia !== null && p.paivia <= 14; });
    return huono.length ? ['kesken', huono.length + ' kaipaa uusintaa']
                        : ['valmis', n + (n===1?' pankki':' pankkia')];
  }
  return T.yhdistetyt.length ? ['valmis', 'voit hakea'] : ['', 'odottaa pankkeja'];
}

function piirraRail(){
  el('rail').innerHTML = VAIHEET.map(function(v, i){
    var t = vaiheenTila(v.avain);
    return '<li class="' + t[0] + '"><button type="button" data-vaihe="' + v.avain + '"' +
      (T.vaihe === v.avain ? ' aria-current="step"' : '') + '>' +
      '<span class="nro">' + (i+1) + '</span><span>' + e(v.nimi) +
      '<span class="tila">' + e(t[1]) + '</span></span></button></li>';
  }).join('');
  Array.prototype.forEach.call(el('rail').querySelectorAll('button'), function(b){
    b.onclick = function(){ toiminto('vaihe', {vaihe: b.dataset.vaihe}); };
  });
}

function ilmoitukset(){
  var h = '';
  if(T.virhe) h += '<p class="virhe">' + e(T.virhe) + '</p>';
  if(T.viesti) h += '<p class="viesti">' + e(T.viesti) + '</p>';
  return h;
}

/* ---------------- vaihe 1: sovellus ---------------- */
function paneeliSovellus(){
  var s = T.sovellus, h = vaiheOtsikko('sovellus');
  h += '<p>Tapahtumat haetaan <em>sinun omalla</em> Rahaputki-sovelluksellasi: ' +
       'tilitietosi kulkevat suoraan koneellesi eikä välissä ole muita palveluita. ' +
       'Sovelluksen avain jää tälle koneelle.</p>';
  h += ilmoitukset();

  h += '<h3>Kirjastot</h3>';
  if(T.kirjastot === null){
    h += '<p class="pikku">Pankkihaku tarvitsee kirjastot pyjwt ja cryptography.</p>' +
         '<div class="rivi"><button class="toiminto" data-t="kirjastot">Tarkista</button></div>';
  } else if(T.kirjastot){
    h += '<p class="pikku">✓ Kirjastot ovat asennettuna.</p>';
  } else {
    h += '<p class="pikku">Kirjastot puuttuvat. Asennus tehdään samalla Pythonilla, ' +
         'jolla tämä ohjelma pyörii.</p>' +
         '<div class="rivi"><button class="toiminto paa" data-t="asenna">Asenna nyt</button></div>';
  }

  if(s.app_id){
    h += '<h3>Rekisteröinti käytössä</h3><div class="kortti">' +
         '<h4>' + e(s.nimi || 'Rahaputki') + (s.ymparisto ? ' (' + e(s.ymparisto) + ')' : '') +
         '</h4><p>Tunnus: ' + e(s.app_id) + '<br>Avain: ' + e(s.avain || '—') + '<br>' +
         (s.varmistettu ? '✓ Yhteys toimii ja haku on käytettävissä'
                        : 'Yhteyttä ei ole vielä tarkistettu') +
         '</p></div><div class="rivi">' +
         '<button class="toiminto ' + (s.varmistettu ? '' : 'paa') + '" data-t="varmista">' +
         'Tarkista yhteys</button></div>';
  }

  h += '<h3>' + (s.app_id ? 'Rekisteröi uudelleen tai vaihda avainta' : 'Aloita') + '</h3>';
  h += '<div class="kortti valinta" role="button" tabindex="0" data-avaa="uusi"' +
       (AVATTU === 'uusi' ? ' aria-pressed="true"' : '') +
       '><h4>Rekisteröi Rahaputki puolestani</h4><p>Nopein tapa. Rahaputki ' +
       'rekisteröityy sinun omaksi sovelluksekseksi, ja avain syntyy tällä ' +
       'koneella eikä käy selaimen kautta.</p></div>' +
       '<div class="kortti valinta" role="button" tabindex="0" data-avaa="avain"' +
       (AVATTU === 'avain' ? ' aria-pressed="true"' : '') +
       '><h4>Rahaputki on jo rekisteröity</h4><p>Otetaan käyttöön rekisteröinnin ' +
       '.pem-avaintiedosto.</p></div>';

  if(AVATTU === 'uusi'){ h += alilomakeUusi(); }
  else if(AVATTU === 'avain'){ h += alilomakeAvain(); }
  return h;
}

function alilomakeUusi(){
  return '<h3>Rekisteröi Rahaputki</h3>' +
    '<ol class="ohjeet">' +
    '<li>Avaa portaali alta ja <strong>kirjaudu sähköpostiosoitteellasi</strong>. ' +
      'Salasanaa ei ole — saat sähköpostiisi linkin, jota klikkaamalla pääset sisään.</li>' +
    '<li>Vieritä sivun alaosaan. Siellä lukee, että sovelluksen voi rekisteröidä ' +
      'rajapinnan kautta tai <strong>command line interface</strong> -tavalla. ' +
      'Klikkaa tuota korostettua tekstiä.</li>' +
    '<li>Esiin tulee laatikko, jonka sisältö alkaa sanalla <code>curl</code>. ' +
      'Klikkaa laatikkoa, valitse kaikki (Cmd-A / Ctrl-A) ja kopioi (Cmd-C / Ctrl-C).</li>' +
    '<li>Liitä komento alla olevaan kenttään.</li></ol>' +
    '<p class="pikku">Komento sisältää tunnin voimassa olevan tunnuksen. Käsittele ' +
    'sitä kuin salasanaa: se ei mene minnekään muualle kuin tälle koneelle.</p>' +
    '<div class="rivi"><a class="paalinkki" target="_blank" rel="noopener" ' +
    'href="https://enablebanking.com/cp/applications">Avaa portaali</a></div>' +
    '<label for="curl">Portaalista kopioitu komento</label>' +
    '<textarea id="curl" data-syote="curl" placeholder="curl -X POST https://enablebanking.com/api/applications ...">' + e(SYOTE.curl) + '</textarea>' +
    '<label for="sposti">Sähköpostiosoitteesi tietosuoja-asioita varten (vapaaehtoinen)</label>' +
    '<input type="text" id="sposti" data-syote="sposti" value="' + e(SYOTE.sposti) + '" placeholder="oma@osoite.fi">' +
    '<div class="rivi"><button class="toiminto paa" data-t="luo_sovellus">Rekisteröi</button></div>';
}

function alilomakeAvain(){
  var h = '<h3>Olemassa oleva avain</h3>' +
    '<p>Avaintiedoston nimi on sovelluksen tunnus, esimerkiksi ' +
    '<code>590999ea-….pem</code>.</p>' +
    '<div class="rivi"><button class="toiminto" data-t="avaimet">Etsi koneelta</button></div>';
  if(T.avainehdokkaat.length){
    h += '<table><tbody>' + T.avainehdokkaat.map(function(a){
      return '<tr><td>' + e(a.lyhyt) + (a.oma ? '' :
        ' <span class="pikku">(koneen yhteinen kansio)</span>') + '</td>' +
        '<td style="text-align:right"><button class="toiminto" data-t="kayta_avainta" ' +
        'data-polku="' + e(a.polku) + '">Käytä tätä</button></td></tr>';
    }).join('') + '</tbody></table>';
  }
  if(T.avain_odottaa){
    h += '<div class="kortti"><h4>' + e(T.avain_odottaa.nimi) + '</h4>' +
      '<p>Tiedoston nimi ei kerro sovelluksen tunnusta. Löydät sen ' +
      'portaalin sovellussivulta kohdasta Application ID.</p>' +
      '<label for="appid">Sovelluksen tunnus (Application ID)</label>' +
      '<input type="text" id="appid" data-syote="appid" value="' + e(SYOTE.appid) +
      '" placeholder="590999ea-6025-4378-8b24-fcb3d8b99804">' +
      '<div class="rivi"><button class="toiminto paa" data-t="kayta_avainta" ' +
      'data-polku="' + e(T.avain_odottaa.polku) + '">Käytä tätä avainta</button>' +
      '<a class="pikku" target="_blank" rel="noopener" ' +
      'href="https://enablebanking.com/cp/applications">Avaa portaali</a></div></div>';
  }
  h += '<label for="polku">tai kirjoita polku</label>' +
       '<input type="text" id="polku" data-syote="polku" value="' + e(SYOTE.polku) + '" placeholder="~/Lataukset/590999ea-….pem">' +
       '<div class="rivi"><button class="toiminto" data-t="kayta_avainta">Käytä</button></div>';
  return h;
}

/* ---------------- vaihe 2: pankit ---------------- */
function paneeliPankit(){
  var h = vaiheOtsikko('pankit') + ilmoitukset();
  if(!T.sovellus.app_id){
    // Ei piiloteta sitä mitä käyttäjällä jo on: yhdistetyt pankit ovat
    // tosiasia configissa, vaikka tämän koneen tunnukset puuttuisivat.
    h += '<p class="virhe">Sovellus ja avain puuttuvat tältä koneelta, joten uutta ' +
         'pankkia ei voi nyt yhdistää eikä valtuutusta uusia.</p>' +
         '<div class="rivi"><button class="toiminto paa" data-t="vaihe" data-vaihe="sovellus">' +
         'Tee vaihe 1</button></div>';
  }
  if(T.yhdistetyt.length){
    h += '<h3>Yhdistetyt</h3><table><thead><tr><th>Pankki</th><th>Tilit</th>' +
         '<th>Valtuutus</th><th></th></tr></thead><tbody>' +
      T.yhdistetyt.map(function(p){
        var tila = p.paivia === null ? 'ei tiedossa'
                 : (p.paivia < 0 ? 'vanhentui ' + p.asti : p.paivia + ' pv jäljellä');
        return '<tr><td>' + e(p.pankki) + '</td><td class="pikku">' + e(p.tilit.join(', ')) +
          '</td><td' + (p.paivia !== null && p.paivia <= 14 ? ' style="color:var(--huono)"' : '') +
          '>' + e(tila) + '</td><td style="text-align:right">' +
          '<button class="toiminto" data-t="valitse-haku" data-pankki="' + e(p.pankki) +
          '">Uusi valtuutus</button></td></tr>';
      }).join('') + '</tbody></table>';
  }

  if(T.pankkivaihe === 'valinta' && T.sovellus.app_id){
    h += '<h3>' + (T.yhdistetyt.length ? 'Lisää pankki' : 'Yhdistä ensimmäinen pankki') + '</h3>';
    h += '<label for="haku">Hae pankkia</label>' +
         '<input type="text" id="haku" data-syote="haku" value="' + e(SYOTE.haku || T.haku) + '" placeholder="esim. OP">' +
         '<div class="rivi"><button class="toiminto" data-t="pankit">Hae lista</button>' +
         '<span class="pikku">maa: ' + e(T.maa) + '</span></div>';
    var lista = T.pankit;
    if(T.haku){
      var hs = T.haku.toLowerCase();
      lista = lista.filter(function(a){ return a.name.toLowerCase().indexOf(hs) >= 0; });
    }
    if(lista.length){
      h += '<div class="pankkilista">' + lista.map(function(a){
        var yritys = (a.psu.length === 1 && a.psu[0] !== 'personal') ? ' — vain yritystilit' : '';
        return '<button type="button" data-t="valitse" data-pankki="' + e(a.name) + '">' +
               e(a.name) + '<span class="pikku">' + e(yritys) + '</span></button>';
      }).join('') + '</div>';
    }
  }

  if(T.pankkivaihe === 'tunnistaudu' && T.valinta){
    h += '<h3>' + e(T.valinta.name) + '</h3>';
    if(!T.auth.url){
      if(T.valinta.psu.length > 1){
        h += '<label for="psu">Tilityyppi</label><select id="psu">' +
          T.valinta.psu.map(function(x){
            return '<option value="' + e(x) + '">' +
              (x === 'business' ? 'Yritystili' : x === 'personal' ? 'Henkilötili' : e(x)) +
              '</option>'; }).join('') + '</select>';
      } else {
        h += '<p class="pikku">Tilityyppi: ' +
             e(T.valinta.psu[0] === 'business' ? 'yritystili' : 'henkilötili') + '</p>';
      }
      h += '<div class="rivi"><button class="toiminto paa" data-t="aloita">' +
           'Aloita tunnistautuminen</button>' +
           '<button class="toiminto" data-t="peru_pankki">Valitse toinen pankki</button></div>';
    } else {
      h += '<p>Avaa tunnistautuminen ja kirjaudu pankkiisi. Pankki palauttaa sinut ' +
           'sivulle, joka näyttää tyhjältä — se on kunnossa. <strong>Kopioi silloin ' +
           'selaimen osoiterivi</strong> ja liitä se tähän.</p>' +
           '<div class="rivi"><a class="paalinkki" target="_blank" rel="noopener" href="' +
           e(T.auth.url) + '">Avaa pankin tunnistautuminen</a></div>' +
           '<label for="koodi">Osoiterivi pankista palanneelta sivulta</label>' +
           '<input type="text" id="koodi" data-syote="koodi" value="' + e(SYOTE.koodi) + '" placeholder="https://…?code=…">' +
           '<div class="rivi"><button class="toiminto paa" data-t="viimeistele">Jatka</button>' +
           '<button class="toiminto" data-t="peru_pankki">Peru</button></div>';
    }
  }

  if(T.pankkivaihe === 'nimet' && T.tilit.length){
    h += '<h3>Nimeä tilit</h3><p>Nimi näkyy raportissa. Nimet OP-tili ja S-Pankki ' +
         'tulkitaan pankin omassa CSV-muodossa, muut yleisessä.</p>' +
         '<table><thead><tr><th>Mukaan</th><th>Tili</th><th>Nimi raportissa</th></tr></thead><tbody>' +
      T.tilit.map(function(t, i){
        return '<tr><td><input type="checkbox" class="mukaan" data-i="' + i + '" checked></td>' +
          '<td class="pikku">' + e(t.tunniste || t.uid.slice(0,8)) + '<br>' + e(t.kuvaus) +
          (t.tuttu ? '<br>tuttu tili' : '') + '</td>' +
          '<td><input type="text" class="nimi" data-i="' + i + '" value="' + e(t.ehdotus) + '"></td></tr>';
      }).join('') + '</tbody></table>' +
      '<div class="rivi"><button class="toiminto paa" data-t="tallenna">Tallenna tilit</button>' +
      '<button class="toiminto" data-t="peru_pankki">Peru</button></div>';
  }
  return h;
}

/* ---------------- vaihe 3: valmis ---------------- */
function paneeliValmis(){
  var h = vaiheOtsikko('valmis') + ilmoitukset();
  if(!T.yhdistetyt.length){
    return h + '<p>Yhtään pankkia ei ole vielä yhdistetty.</p>' +
      '<div class="rivi"><button class="toiminto paa" data-t="vaihe" data-vaihe="pankit">' +
      'Yhdistä pankki</button></div>';
  }
  h += '<p>Pankkiyhteys on kytketty. Raportissa <strong>Hae pankkitapahtumat</strong> ' +
       'noutaa tapahtumat ja lukee ne kirjanpitoon.</p>' +
       '<table><tbody>' + T.yhdistetyt.map(function(p){
         return '<tr><td>' + e(p.pankki) + '</td><td class="pikku">' +
                e(p.tilit.join(', ')) + '</td></tr>'; }).join('') + '</tbody></table>' +
       '<div class="rivi"><a class="paalinkki" href="raportti.html">Takaisin raporttiin</a></div>';
  return h;
}

function piirra(){
  if(!T){ el('paneeli').innerHTML = '<p>Ladataan…</p>'; return; }
  piirraRail();
  var p = T.vaihe === 'pankit' ? paneeliPankit()
        : T.vaihe === 'valmis' ? paneeliValmis() : paneeliSovellus();
  el('paneeli').innerHTML = p;
  if(kesken){
    Array.prototype.forEach.call(document.querySelectorAll('button.toiminto'),
      function(b){ b.disabled = true; b.textContent = b.textContent; });
  }
  sido();
}

function sido(){
  Array.prototype.forEach.call(document.querySelectorAll('[data-syote]'), function(kentta){
    kentta.oninput = function(){ SYOTE[kentta.dataset.syote] = kentta.value; };
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-avaa]'), function(k){
    k.onclick = function(){ AVATTU = k.dataset.avaa; piirra(); };
    k.onkeydown = function(ev){ if(ev.key === 'Enter' || ev.key === ' '){ ev.preventDefault(); k.onclick(); } };
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-t]'), function(b){
    b.onclick = function(){
      var t = b.dataset.t, d = {};
      if(t === 'vaihe'){ d.vaihe = b.dataset.vaihe; }
      else if(t === 'valitse'){ d.pankki = b.dataset.pankki; }
      else if(t === 'valitse-haku'){
        // Uusi valtuutus: haetaan lista ja valitaan sama pankki
        toiminto('pankit', {haku: b.dataset.pankki, maa: T.maa}).then(function(){
          toiminto('valitse', {pankki: b.dataset.pankki});
        });
        return;
      }
      else if(t === 'kayta_avainta'){
        d.polku = b.dataset.polku || SYOTE.polku; d.app_id = SYOTE.appid;
      }
      else if(t === 'luo_sovellus'){
        d.curl = SYOTE.curl; d.sposti = SYOTE.sposti;
      }
      else if(t === 'pankit'){ d.haku = SYOTE.haku; d.maa = T.maa; }
      else if(t === 'aloita'){ d.psu = el('psu') ? el('psu').value : ''; }
      else if(t === 'viimeistele'){ d.koodi = SYOTE.koodi; }
      else if(t === 'tallenna'){
        d.valinnat = T.tilit.map(function(x, i){
          var n = document.querySelector('.nimi[data-i="' + i + '"]');
          var m = document.querySelector('.mukaan[data-i="' + i + '"]');
          return {uid: x.uid, tunniste: x.tunniste,
                  tili: n ? n.value : x.ehdotus, mukaan: m ? m.checked : true};
        });
      }
      toiminto(t, d);
    };
  });
}

fetch('api/velho', {method:'POST', headers:{'Content-Type':'application/json'},
  body: JSON.stringify({toiminto:'kirjastot'})})
  .then(function(r){ return r.json(); })
  .then(function(v){
    T = v;
    var p = new URLSearchParams(location.search).get('pankki');
    if(p){ T.vaihe = 'pankit';
      toiminto('pankit', {haku:p, maa:T.maa}).then(function(){ toiminto('valitse', {pankki:p}); });
    } else { piirra(); }
  });
</script></body></html>
"""


# ============ selainvelho: tila jota voi muuttaa, ei kysymysjono ==========
# Terminaalivelho kysyy kysymykset jonossa, ja jonossa mennyttä kysymystä ei
# ole enää olemassa: tehtyä valintaa ei voi vaihtaa katsomatta sitä uudelleen.
# Selaimessa se on väärä malli. Täällä on tila, johon jokainen vaihe kirjoittaa
# ja josta jokainen vaihe voi lukea — mihin tahansa vaiheeseen voi palata, ja
# valinnan muuttaminen mitätöi vain ne vaiheet, jotka siitä oikeasti riippuvat.

def _velho_alkutila():
    return {"vaihe": "sovellus",
            "kirjastot": None,
            "sovellus": {"app_id": "", "avain": "", "varmistettu": False,
                         "nimi": "", "reitti": "", "ymparisto": "", "aktiivinen": None},
            "avainehdokkaat": [], "avain_odottaa": None,
            "maa": "FI", "haku": "", "pankit": [],
            "pankkivaihe": "valinta", "valinta": None,
            "auth": {"url": "", "redirect": ""},
            "istunto": None, "tilit": [],
            "viesti": "", "virhe": "", "tekeilla": ""}


VELHO = _velho_alkutila()
VELHO_LUKKO = threading.Lock()


def _kirjastot_ok():
    try:
        import jwt  # noqa: F401
        import cryptography  # noqa: F401
        return True
    except ImportError:
        return False


def _asenna_kirjastot():
    """pip samalla tulkilla jolla ohjelma pyörii, jottei paketti eksy toiseen
    Python-asennukseen. Palauttaa virheen kuvauksen tai tyhjän."""
    import subprocess
    viimeisin = ""
    for lisa in ([], ["--user"], ["--user", "--break-system-packages"]):
        try:
            tulos = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                                    *lisa, "pyjwt", "cryptography"],
                                   capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as e:
            return f"asennus ei käynnistynyt: {e}"
        if tulos.returncode == 0 and _kirjastot_ok():
            return ""
        viimeisin = siisti(tulos.stderr or tulos.stdout)[:200]
    return viimeisin or "asennus ei onnistunut"


def _velho_yhdistetyt(cfg):
    """Jo yhdistetyt pankit tiliriveineen — se, mitä käyttäjä on jo tehnyt."""
    tila = lue_pankkitila()
    pankit = {}
    for t in ((cfg.get("pankkihaku") or {}).get("tilit") or []):
        aid = str(t.get("account_id", ""))
        if _on_paikanpitaja(aid):
            continue
        tt = tila.get(aid, {})
        nimi = siisti(str(tt.get("pankki", "") or t.get("pankki", ""))) or "?"
        p = pankit.setdefault(nimi, {"pankki": nimi, "tilit": [], "asti": "", "paivia": None})
        p["tilit"].append(t.get("tili", ""))
        asti = tt.get("valtuutus_asti")
        if asti and (not p["asti"] or asti < p["asti"]):
            p["asti"] = asti
            p["paivia"] = _paivia_jaljella(asti)
    return sorted(pankit.values(), key=lambda x: x["pankki"].lower())


def velho_julkinen():
    """Tila selaimelle. Salaisuuksia ei lähetetä: avaimesta vain polku."""
    cfg = lue_config() or {}
    v = VELHO
    return {"ok": True, "vaihe": v["vaihe"], "kirjastot": v["kirjastot"],
            "sovellus": v["sovellus"], "avainehdokkaat": v["avainehdokkaat"],
            "avain_odottaa": v["avain_odottaa"],
            "maa": v["maa"], "haku": v["haku"],
            "pankit": [{"name": a.get("name", ""), "country": a.get("country", ""),
                        "psu": _psu_tyypit(a)} for a in v["pankit"]],
            "pankkivaihe": v["pankkivaihe"], "valinta": v["valinta"],
            "auth": v["auth"], "tilit": v["tilit"],
            "yhdistetyt": _velho_yhdistetyt(cfg),
            "viesti": v["viesti"], "virhe": v["virhe"]}


def _velho_nollaa_pankki():
    VELHO.update(pankkivaihe="valinta", valinta=None,
                 auth={"url": "", "redirect": ""}, istunto=None, tilit=[])


def velho_toiminto(nimi, p):
    """Yksi toiminto, uusi tila. Jokainen palaa samaan muotoon, joten sivu ei
    tarvitse tietoa siitä mikä onnistui — se piirtää tilan uudelleen."""
    v = VELHO
    v["viesti"] = v["virhe"] = ""

    if nimi == "vaihe":
        v["vaihe"] = siisti(str(p.get("vaihe", ""))) or v["vaihe"]

    elif nimi == "kirjastot":
        v["kirjastot"] = _kirjastot_ok()

    elif nimi == "asenna":
        virhe = _asenna_kirjastot()
        v["kirjastot"] = _kirjastot_ok()
        v["virhe"] = virhe
        v["viesti"] = "" if virhe else "Kirjastot asennettu."

    elif nimi == "avaimet":
        v["avainehdokkaat"] = [{"polku": str(polku), "lyhyt": _lyhenna_polku(polku),
                                "oma": bool(oma)} for polku, oma in _etsi_avaimet()]
        if not v["avainehdokkaat"]:
            v["viesti"] = "Avaintiedostoa ei löytynyt tavallisista kansioista."

    elif nimi == "kayta_avainta":
        polku = Path(_siivoa_polku(str(p.get("polku", "")))).expanduser()
        annettu = siisti(str(p.get("app_id", "")))
        if not polku.is_file():
            v["virhe"] = f"Tiedostoa ei löydy: {polku}"
        else:
            # Portaalin lomakkeesta ladatun avaimen nimi on sovelluksen tunnus,
            # mutta rajapinnan kautta luodun tai käsin uudelleennimetyn ei ole.
            # Silloin tunnus kysytään sen sijaan että avain hylättäisiin — juuri
            # se avain, joka käyttäjällä on, ei saa olla se jota ei kelpuuteta.
            app_id = polku.stem if UUID_KUVIO.match(polku.stem) else annettu
            if not app_id:
                v["avain_odottaa"] = {"polku": str(polku), "nimi": polku.name}
                v["viesti"] = ("Tiedoston nimi ei ole sovelluksen tunnus. "
                               "Kopioi tunnus (Application ID) portaalista alle.")
            elif not UUID_KUVIO.match(app_id):
                v["avain_odottaa"] = {"polku": str(polku), "nimi": polku.name}
                v["virhe"] = ("Tunnus ei näytä sovelluksen tunnukselta. Se on "
                              "muotoa 590999ea-6025-4378-8b24-fcb3d8b99804.")
            else:
                kohde = _talleta_avain(polku, siirra=True)
                _kirjoita_env({"EB_APP_ID": app_id, "EB_KEY_PATH": _lyhenna_polku(kohde)})
                v["sovellus"].update(app_id=app_id, avain=_lyhenna_polku(kohde),
                                     reitti="avain", varmistettu=False, nimi="")
                v["avain_odottaa"] = None
                v["viesti"] = "Avain otettu käyttöön. Tarkista vielä yhteys."

    elif nimi == "luo_sovellus":
        token = _poimi_token(str(p.get("curl", "")))
        if not token:
            v["virhe"] = ("Komennosta ei löytynyt tunnusta. Kopioi koko komento "
                          "portaalista — se alkaa sanalla curl ja sisältää sanan Bearer.")
        else:
            try:
                pem_teksti, varmenne = _luo_avainpari()
                vastaus = _rekisteroi_sovellus(token, varmenne,
                                               gdpr_email=siisti(str(p.get("sposti", ""))))
                app_id = _sovellus_id(vastaus)
                if not app_id:
                    v["virhe"] = ("Rekisteröinti meni läpi, mutta tunnusta ei "
                                  "löytynyt vastauksesta.")
                else:
                    polku = _talleta_uusi_avain(pem_teksti, app_id)
                    _kirjoita_env({"EB_APP_ID": app_id,
                                   "EB_KEY_PATH": _lyhenna_polku(polku),
                                   "EB_SOVELLUS_OK": app_id})
                    v["sovellus"].update(app_id=app_id, avain=_lyhenna_polku(polku),
                                         reitti="uusi", varmistettu=False, nimi="")
                    v["viesti"] = ("Rahaputki rekisteröity. Avain tallennettu "
                                   "tälle koneelle.")
            except EBVirhe as e:
                v["virhe"] = ("Tunnus ei kelvannut (se vanhenee tunnissa). Lataa "
                              "portaalin sivu uudelleen ja kopioi komento uudestaan."
                              if e.koodi in (401, 403) else
                              f"Rekisteröinti epäonnistui ({e.koodi}): {e.runko}")
            except (OSError, ValueError) as e:
                v["virhe"] = f"Rekisteröinti epäonnistui: {e}"

    elif nimi == "varmista":
        # Sovelluksen lukeminen onnistuu myös aktivoimattomalta sovellukselta,
        # joten pelkkä /application ei kerro toimiiko haku. Se pitää kokeilla:
        # pankkilista on kevyin oikea kutsu eikä kuluta tilikohtaista
        # hakubudjettia. Ensimmäinen versio ilmoitti "yhteys toimii" pelkän
        # sovelluksen luvun perusteella, ja seuraava ruutu kaatui virheeseen
        # "Application is not active" — väärä vastaus väärään kysymykseen.
        v["sovellus"]["varmistettu"] = False
        try:
            app = eb_sovellus() or {}
            v["sovellus"]["nimi"] = siisti(str(_kentta(app, "name") or ""))
            v["sovellus"]["ymparisto"] = str(_kentta(app, "environment") or "").upper()
            aktiivinen = _kentta(app, "active")
            v["sovellus"]["aktiivinen"] = aktiivinen
        except EBVirhe as e:
            v["virhe"] = ("Avain ja sovelluksen tunnus eivät ole samasta "
                          "sovelluksesta. Valitse oikea avain uudelleen."
                          if e.koodi in (401, 403) else
                          f"Enable Banking vastasi {e.koodi}: {e.runko}")
            return velho_julkinen()
        except Exception as e:
            v["virhe"] = f"Avainta ei voitu käyttää: {e}"
            return velho_julkinen()
        try:
            eb_pankkilista(v["maa"])
        except EBVirhe as e:
            if e.koodi == 403 and "not active" in str(e.runko).lower():
                v["virhe"] = (
                    "Avain kelpaa, mutta Enable Banking ei ole aktivoinut "
                    "sovellusta: haku ei vielä toimi. Käy portaalin "
                    "sovellussivulla ja liitä tilisi sovellukseen (Link "
                    "accounts) — ilmaisessa, omiin tileihin rajatussa tilassa "
                    "se on se vaihe, joka puuttuu useimmiten. Tarkista sitten "
                    "yhteys uudelleen.")
            else:
                v["virhe"] = f"Haku ei toimi vielä ({e.koodi}): {e.runko}"
            return velho_julkinen()
        except (OSError, ValueError) as e:
            v["virhe"] = f"Yhteys ei toiminut: {e}"
            return velho_julkinen()
        v["sovellus"]["varmistettu"] = True
        v["viesti"] = "Yhteys toimii ja haku on käytettävissä."

    elif nimi == "pankit":
        v["maa"] = (siisti(str(p.get("maa", ""))) or v["maa"]).upper()[:2]
        v["haku"] = siisti(str(p.get("haku", "")))
        try:
            v["pankit"] = eb_pankkilista(v["maa"])
        except (EBVirhe, OSError, ValueError) as e:
            v["virhe"] = f"Pankkilistaa ei saatu: {e}"

    elif nimi == "valitse":
        haettu = siisti(str(p.get("pankki", "")))
        osuma = next((a for a in v["pankit"] if a.get("name") == haettu), None)
        if osuma is None:
            v["virhe"] = "Pankkia ei löytynyt listalta."
        else:
            v["valinta"] = {"name": osuma.get("name", ""),
                            "country": osuma.get("country", v["maa"]),
                            "psu": _psu_tyypit(osuma), "raaka": osuma}
            v["pankkivaihe"] = "tunnistaudu"
            v["auth"] = {"url": "", "redirect": ""}

    elif nimi == "aloita":
        if not v["valinta"]:
            v["virhe"] = "Valitse ensin pankki."
        else:
            psu = siisti(str(p.get("psu", ""))) or (v["valinta"]["psu"] or ["personal"])[0]
            try:
                cfg = lue_config()
                url, redirect = eb_aloita_valtuutus(cfg, v["valinta"]["raaka"], psu)
                turvakirjoita_json(CONFIG, cfg)
                v["auth"] = {"url": url, "redirect": redirect}
            except EBVirhe as e:
                v["virhe"] = (f"Enable Banking ei hyväksynyt valintaa ({e.koodi}). "
                              "Yleisin syy on väärä tilityyppi — kokeile toista."
                              if e.koodi == 422 else
                              f"Valtuutus ei käynnistynyt ({e.koodi}): {e.runko}")
            except (OSError, ValueError) as e:
                v["virhe"] = f"Valtuutus ei käynnistynyt: {e}"

    elif nimi == "viimeistele":
        koodi = _siivoa_koodi(str(p.get("koodi", "")))
        if not koodi:
            v["virhe"] = ("Liitä koko osoiterivi pankista palanneelta sivulta — "
                          "siinä on kohta code=…")
        else:
            try:
                istunto, tilit = eb_viimeistele_valtuutus(koodi)
                if not tilit:
                    v["virhe"] = ("Istunto syntyi, mutta siinä ei ollut yhtään tiliä. "
                                  "Käy liittämässä tili portaalissa (Link accounts).")
                else:
                    v["istunto"] = istunto
                    v["tilit"] = tilien_ehdotukset(lue_config(),
                                                   v["valinta"]["name"], tilit)
                    v["pankkivaihe"] = "nimet"
            except (EBVirhe, OSError, ValueError) as e:
                v["virhe"] = f"Valtuutus ei valmistunut: {e}"

    elif nimi == "tallenna":
        valinnat = p.get("valinnat") or []
        if not any(x.get("mukaan", True) and siisti(str(x.get("tili", "")))
                   for x in valinnat):
            v["virhe"] = "Anna vähintään yhdelle tilille nimi."
        else:
            cfg = lue_config()
            tulos = tallenna_tilit_nimilla(cfg, v["valinta"]["name"], valinnat, v["istunto"])
            v["viesti"] = (f"{v['valinta']['name']}: {tulos['yhteensa']} tiliä tallennettu"
                           + (f", {tulos['uusia']} uutta." if tulos["uusia"] else "."))
            _velho_nollaa_pankki()

    elif nimi == "peru_pankki":
        _velho_nollaa_pankki()

    elif nimi == "alusta":
        VELHO.update(_velho_alkutila())

    else:
        v["virhe"] = f"tuntematon toiminto {nimi}"
    return velho_julkinen()


# Selaimesta käynnistetty komento ajetaan tässä prosessissa, ei uutena
# prosessina. Silloin se käyttää jo otettua pääkirjalukkoa eikä joudu
# kilpailemaan siitä itsensä kanssa — kahden käynnistimen mallissa juuri se
# oli päivittäisen käytön ikävin sudenkuoppa.
SELAIN_AJO = {"komento": None, "loki": [], "virhe": ""}
SELAIN_AJO_LUKKO = threading.Lock()


class _Haarukka:
    """Tuloste kahteen paikkaan: konsoliin kuten ennenkin ja selaimen lokiin.

    Komennot kertovat edistymisestään printillä, ja se on niiden ainoa
    käyttöliittymä. Jotta selain näkee saman, stdout haaroitetaan ajon ajaksi —
    konsoli säilyy, koska se on yhä oikea paikka katsoa mitä tapahtui."""

    def __init__(self, konsoli, rivit):
        self.konsoli, self.rivit, self.kesken = konsoli, rivit, ""

    def write(self, teksti):
        self.konsoli.write(teksti)
        self.kesken += teksti
        while "\n" in self.kesken:
            rivi, _, self.kesken = self.kesken.partition("\n")
            self.rivit.append(rivi)
        return len(teksti)

    def flush(self):
        self.konsoli.flush()

    def isatty(self):
        return False  # estää komentoja kysymästä mitään: kukaan ei ole vastaamassa


def _aja_selaimesta(komento):
    """Aja hae tai aja taustasäikeessä ja kerää tuloste selaimen luettavaksi."""
    args = argparse.Namespace(
        palvelu=None, paivia=89, istunto=None, yhdista=None, raaka=False,
        siivoa_alkaen=False, pakota=False, ei_velhoa=True, kk=13, kaikki=False)
    konsoli, rivit = sys.stdout, SELAIN_AJO["loki"]
    sys.stdout = _Haarukka(konsoli, rivit)
    try:
        # "Hae pankkitapahtumat" tarkoittaa käyttäjälle valmista lopputulosta,
        # ei puolikasta: nouto jättää tiedostot inboxiin, ja pelkkä nouto
        # jättäisi tehtäväksi toisen napin painamisen ilman että siitä seuraa
        # mitään uutta päätettävää.
        if komento == "hae":
            cmd_hae(args)
            print()
            cmd_aja(args)
        else:
            cmd_aja(args)
    except SystemExit as e:
        rivit.append(f"Keskeytyi: {e}")
        SELAIN_AJO["virhe"] = str(e)
    except Exception as e:
        rivit.append(f"⚠ {komento} epäonnistui: {e}")
        SELAIN_AJO["virhe"] = str(e)
    finally:
        sys.stdout = konsoli
        with SELAIN_AJO_LUKKO:
            SELAIN_AJO["komento"] = None


def cmd_selaa(args):
    import http.server
    import webbrowser

    portti = args.portti

    class Kasittelija(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(RAPORTIT), **k)

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass  # selain katkaisi pyynnön kesken (esim. sivun automaattipäivitys) — harmiton

        def end_headers(self):
            # raportti muuttuu joka operaatiolla — välimuisti aiheuttaisi vanhentuneita näkymiä
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass

        def _json(self, obj, koodi=200):
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(koodi)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if "If-Modified-Since" in self.headers:
                del self.headers["If-Modified-Since"]  # aina tuore sivu, ei 304-oikotietä
            if self.path == "/api/ping":
                return self._json({"ok": True})
            # Osoitteessa voi olla ?pankki=… (valtuutuksen uusinta), joten
            # kyselyosa pudotetaan ennen vertailua.
            if self.path.partition("?")[0].rstrip("/") == "/velho":
                sivu = VELHO_SIVU.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(sivu)))
                self.end_headers()
                self.wfile.write(sivu)
                return
            if self.path.startswith("/api/loki"):
                alkaen = _kysely_luku(self.path, "alkaen")
                rivit = SELAIN_AJO["loki"]
                return self._json({"ok": True, "rivit": rivit[alkaen:],
                                   "seuraava": len(rivit),
                                   "kaynnissa": SELAIN_AJO["komento"],
                                   "virhe": SELAIN_AJO["virhe"]})
            if self.path in ("/", "/raportti.html"):
                sivu = rakenna_raportit(lue_ledger(), lue_config(), kk=13,
                                        kirjoita_sivu=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(sivu)))
                self.end_headers()
                self.wfile.write(sivu)
                return
            return super().do_GET()

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                pyynto = json.loads(self.rfile.read(n) or b"{}")
                cfg = lue_config()
                if self.path == "/api/muutos":
                    kat = siisti(pyynto.get("kategoria", ""))
                    if kat not in cfg["kategoriat"] and not pyynto.get("rivit"):
                        return self._json({"ok": False, "virhe": f"tuntematon kategoria {kat}"})
                    ledger = lue_ledger()
                    idx = {r["id"]: r for r in ledger}
                    rivit_p = pyynto.get("rivit")
                    if rivit_p:
                        n = 0
                        for rp in rivit_p:
                            kat2 = siisti(rp.get("kategoria", ""))
                            r = idx.get(siisti(rp.get("id", "")))
                            if r and kat2 in cfg["kategoriat"]:
                                r["kategoria"] = kat2
                                r["tarkenne"] = siisti(rp.get("tarkenne", "")).lower()
                                r["peruste"] = siisti(rp.get("peruste", "")) or "käsin"
                                n += 1
                        if not n:
                            return self._json({"ok": False, "virhe": "rivejä ei löydy"})
                        kirjoita_ledger(ledger)
                        kirjoita_tarkistettavat(ledger)
                        return self._json({"ok": True, "paivitetty": n})
                    idt = pyynto.get("idt") or [siisti(pyynto.get("id", ""))]
                    tarkenne = siisti(pyynto.get("tarkenne", "")).lower()
                    n = 0
                    for rid in idt:
                        r = idx.get(siisti(rid))
                        if r:
                            r["kategoria"], r["tarkenne"], r["peruste"] = kat, tarkenne, "käsin"
                            n += 1
                    if not n:
                        return self._json({"ok": False, "virhe": "rivejä ei löydy"})
                    kirjoita_ledger(ledger)
                    kirjoita_tarkistettavat(ledger)
                    return self._json({"ok": True, "paivitetty": n})
                if self.path == "/api/saanto":
                    kat = siisti(pyynto.get("kategoria", ""))
                    malli = normalisoi(pyynto.get("malli", ""))
                    if kat not in cfg["kategoriat"] or not malli:
                        return self._json({"ok": False, "virhe": "puuttuva malli tai kategoria"})
                    tarkenne = siisti(pyynto.get("tarkenne", "")).lower()
                    ehto = siisti(pyynto.get("ehto", ""))
                    poistaen = pyynto.get("poistaen") or []
                    kategoria_full = kat + (f":{tarkenne}" if tarkenne else "")
                    ledger = lue_ledger()
                    vaikutus = saanto_vaikutus(ledger, cfg, malli, kategoria_full,
                                               ehto=ehto, poistaen=poistaen)
                    if pyynto.get("esikatselu"):
                        return self._json({"ok": True, **vaikutus})
                    for p in poistaen:
                        poista_saanto(p.get("malli", ""), p.get("kategoria", ""),
                                      p.get("ehto", ""))
                    lisaa_saanto(malli, kategoria_full, ehto)
                    m_u, m_a = uudelleenluokittele_saantorivit(
                        ledger, cfg,
                        pakota_saannolle=(malli if pyynto.get("pakota") else None))
                    kirjoita_ledger(ledger)
                    kirjoita_tarkistettavat(ledger)
                    return self._json({"ok": True, "muuttui": m_u, "avoimeksi": m_a, **vaikutus})
                if self.path == "/api/vapauta":
                    ledger = lue_ledger()
                    idx = {r["id"]: r for r in ledger}
                    r = idx.get(siisti(pyynto.get("id", "")))
                    if not r:
                        return self._json({"ok": False, "virhe": "riviä ei löydy"})
                    if r.get("peruste", "") not in ("käsin", "oletus"):
                        return self._json({"ok": False,
                                           "virhe": "rivi ei ole käsin/oletus-luokiteltu"})
                    saannot = lue_saannot()
                    u, p2 = luokittele({"saaja": r["saaja"], "selite": r["selite"],
                                        "iban": "", "summa": float(r["summa"])},
                                       saannot, cfg.get("omat_ibanit", []))
                    paa, _, tark = u.partition(":")
                    r["kategoria"] = paa
                    r["tarkenne"] = tark.strip().lower()
                    r["peruste"] = p2 if paa != "TARKISTA" else ""
                    kirjoita_ledger(ledger)
                    kirjoita_tarkistettavat(ledger)
                    return self._json({"ok": True, "kategoria": r["kategoria"],
                                       "tarkenne": r["tarkenne"], "peruste": r["peruste"]})
                if self.path == "/api/saanto-osuma":
                    malli = normalisoi(pyynto.get("malli", ""))
                    if not malli:
                        return self._json({"ok": False, "virhe": "tyhjä malli"})
                    try:
                        osuu, esim = laske_osumat(lue_ledger(), malli,
                                                  siisti(pyynto.get("ehto", "")))
                    except re.error:
                        return self._json({"ok": False, "virhe": "regex-virhe"})
                    return self._json({"ok": True, "osuu": osuu, "esimerkit": esim})
                if self.path == "/api/saanto-poista":
                    malli = siisti(pyynto.get("malli", ""))
                    if not malli:
                        return self._json({"ok": False, "virhe": "tyhjä malli"})
                    n_p = poista_saanto(malli, siisti(pyynto.get("kategoria", "")),
                                        siisti(pyynto.get("ehto", "")))
                    m_u = m_a = 0
                    if n_p:
                        ledger = lue_ledger()
                        m_u, m_a = uudelleenluokittele_saantorivit(
                            ledger, cfg, vain_peruste=f"sääntö: {normalisoi(malli)}")
                        kirjoita_ledger(ledger)
                        kirjoita_tarkistettavat(ledger)
                    return self._json({"ok": bool(n_p), "poistettu": n_p,
                                       "muuttui": m_u, "avoimeksi": m_a,
                                       **({} if n_p else {"virhe": "sääntöä ei löytynyt"})})
                if self.path == "/api/saanto-siirra":
                    malli = siisti(pyynto.get("malli", ""))
                    ok = siirra_saanto(malli, siisti(pyynto.get("kategoria", "")),
                                       siisti(pyynto.get("ehto", "")),
                                       suunta=int(pyynto.get("suunta", -1)),
                                       kohde_sija=pyynto.get("kohde"))
                    m_u = m_a = 0
                    if ok:
                        ledger = lue_ledger()
                        m_u, m_a = uudelleenluokittele_saantorivit(ledger, cfg)
                        kirjoita_ledger(ledger)
                        kirjoita_tarkistettavat(ledger)
                    return self._json({"ok": ok, "muuttui": m_u, "avoimeksi": m_a,
                                       **({} if ok else {"virhe": "siirto ei onnistunut"})})
                if self.path == "/api/olympos":
                    oly = lue_olympos()
                    if "lasna_vk" in pyynto:
                        vk = siisti(str(pyynto.get("lasna_vk", "")))
                        nimi = siisti(str(pyynto.get("lasna_nimi", "")))
                        if vk and nimi:
                            oly.setdefault("lasna", {}).setdefault(vk, {})[nimi] = \
                                1 if pyynto.get("lasna_arvo") else 0
                    if pyynto.get("kirjaus"):
                        k = pyynto["kirjaus"]
                        try:
                            summa = float(str(k.get("summa", "")).replace(",", "."))
                        except ValueError:
                            return self._json({"ok": False, "virhe": "summa ei ole luku"})
                        if not siisti(str(k.get("pvm", ""))) or summa <= 0:
                            return self._json({"ok": False,
                                               "virhe": "pvm ja positiivinen summa vaaditaan"})
                        oly.setdefault("kirjaukset", []).append(
                            {"pvm": siisti(str(k.get("pvm", ""))),
                             "kuvaus": siisti(str(k.get("kuvaus", ""))),
                             "maksaja": siisti(str(k.get("maksaja", ""))),
                             "summa": summa,
                             "jako": siisti(str(k.get("jako", "tasan"))) or "tasan",
                             "osallistujat": [siisti(str(x)) for x in (k.get("osallistujat") or [])
                                              if siisti(str(x))]})
                    if pyynto.get("hyvitys"):
                        hv = pyynto["hyvitys"]
                        try:
                            s_kk = float(str(hv.get("summa_kk", "")).replace(",", "."))
                        except ValueError:
                            return self._json({"ok": False, "virhe": "€/kk ei ole luku"})
                        if not siisti(str(hv.get("kuvaus", ""))) or s_kk <= 0:
                            return self._json({"ok": False,
                                               "virhe": "kuvaus ja positiivinen €/kk vaaditaan"})
                        uusi_h = {"kuvaus": siisti(str(hv.get("kuvaus", ""))),
                                  "jasenelta": siisti(str(hv.get("jasenelta", ""))),
                                  "summa_kk": s_kk}
                        try:
                            mx = int(str(hv.get("kk_max", "")).strip() or 0)
                        except ValueError:
                            return self._json({"ok": False, "virhe": "kk ei ole kokonaisluku"})
                        if mx > 0:
                            uusi_h["kk_max"] = mx
                        oly.setdefault("hyvitykset", []).append(uusi_h)
                    if "hyvitys_poista" in pyynto:
                        i = int(pyynto["hyvitys_poista"])
                        if 0 <= i < len(oly.get("hyvitykset", [])):
                            oly["hyvitykset"].pop(i)
                    if pyynto.get("poissulje"):
                        rid = siisti(str(pyynto["poissulje"]))
                        lista = oly.setdefault("poissuljetut", [])
                        if rid and rid not in lista:
                            lista.append(rid)
                    if pyynto.get("ota_mukaan"):
                        rid = siisti(str(pyynto["ota_mukaan"]))
                        oly["poissuljetut"] = [x for x in oly.get("poissuljetut", [])
                                               if str(x) != rid]
                    if "kirjaus_poista" in pyynto:
                        i = int(pyynto["kirjaus_poista"])
                        if 0 <= i < len(oly.get("kirjaukset", [])):
                            oly["kirjaukset"].pop(i)
                    for kentta in ("viikkojako", "palautustarkenteet"):
                        if kentta in pyynto:
                            oly[kentta] = [siisti(str(x)).lower()
                                           for x in str(pyynto[kentta]).split(",") if siisti(str(x))]
                    if "otsikko" in pyynto:
                        oly["otsikko"] = siisti(str(pyynto.get("otsikko", "")))
                    if "kategoria" in pyynto and pyynto.get("kategoria") != "__uusi__":
                        oly["kategoria"] = siisti(str(pyynto.get("kategoria", "")))
                    if "nayta_alku" in pyynto or "nayta_loppu" in pyynto:
                        oly["nayta_alku"] = siisti(str(pyynto.get("nayta_alku", "")))
                        oly["nayta_loppu"] = siisti(str(pyynto.get("nayta_loppu", "")))
                    if pyynto.get("tasattu"):
                        oly["tasattu"] = siisti(str(pyynto["tasattu"]))
                        oly["nayta_alku"] = oly["nayta_loppu"] = ""
                    kirjoita_olympos(oly)
                    return self._json({"ok": True})
                if self.path == "/api/kategoria":
                    nimi = siisti(pyynto.get("nimi", ""))
                    if not nimi:
                        return self._json({"ok": False, "virhe": "tyhjä nimi"})
                    if nimi not in cfg["kategoriat"]:
                        cfg["kategoriat"][nimi] = siisti(pyynto.get("tyyppi", "")) or "meno"
                        turvakirjoita_json(CONFIG, cfg)
                    return self._json({"ok": True})
                if self.path == "/api/kategoria-poista":
                    nimi = siisti(pyynto.get("nimi", ""))
                    korvaava = siisti(pyynto.get("korvaava", ""))
                    if nimi not in cfg["kategoriat"]:
                        return self._json({"ok": False, "virhe": "tuntematon kategoria"})
                    saantoja = sum(1 for s in lue_saannot_raaka()
                                   if siisti(s["kategoria"]).partition(":")[0] == nimi)
                    if saantoja:
                        return self._json({"ok": False, "virhe":
                                           f"{saantoja} sääntöä osoittaa kategoriaan '{nimi}' — "
                                           "poista tai muokkaa ne ensin (säännöt-välilehti)"})
                    ledger = lue_ledger()
                    osuvat = [r for r in ledger if r["kategoria"] == nimi]
                    if osuvat and not korvaava:
                        return self._json({"ok": False, "tarvitaan_korvaava": True,
                                           "rivit": len(osuvat)})
                    siirretty = 0
                    if osuvat:
                        if korvaava.upper() == "TARKISTA":
                            for r in osuvat:
                                r["kategoria"], r["tarkenne"], r["peruste"] = "TARKISTA", "", ""
                                siirretty += 1
                        else:
                            kat2, _, tark2 = korvaava.partition(":")
                            kat2 = siisti(kat2)
                            if kat2 not in cfg["kategoriat"] or kat2 == nimi:
                                return self._json({"ok": False,
                                                   "virhe": f"tuntematon korvaava kategoria '{kat2}'"})
                            for r in osuvat:
                                r["kategoria"], r["tarkenne"], r["peruste"] = kat2, siisti(tark2).lower(), "käsin"
                                siirretty += 1
                        kirjoita_ledger(ledger)
                        kirjoita_tarkistettavat(ledger)
                    del cfg["kategoriat"][nimi]
                    turvakirjoita_json(CONFIG, cfg)
                    return self._json({"ok": True, "siirretty": siirretty})
                if self.path in ("/api/tasmayta", "/api/ankkuroi"):
                    tilit = ((cfg.get("pankkihaku") or {}).get("tilit") or [])
                    try:
                        t = tilit[int(pyynto.get("idx"))]
                    except (TypeError, ValueError, IndexError):
                        return self._json({"ok": False, "virhe": "tuntematon tili"})
                    aid = str(t.get("account_id", ""))
                    if self.path == "/api/tasmayta":
                        # Yksi haku, yksi tili, käyttäjän pyynnöstä.
                        try:
                            virhe = _hae_saldo(aid, t.get("tili", ""))
                        except (EBVirhe, OSError, ValueError) as e:
                            virhe = str(e)
                        if virhe:
                            return self._json({"ok": False,
                                               "virhe": f"saldoa ei saatu: {virhe}"})
                        return self._json(tasmayta(lue_ledger(), cfg, aid))
                    return self._json(ankkuroi(lue_ledger(), cfg, aid))
                if self.path == "/api/velho":
                    with VELHO_LUKKO:
                        # Sivu piirtää aina koko tilan, joten sen on saatava
                        # koko tila myös silloin kun toiminto kaatuu.
                        try:
                            return self._json(velho_toiminto(
                                siisti(str(pyynto.get("toiminto", ""))), pyynto))
                        except Exception as e:
                            VELHO["virhe"] = f"Toiminto epäonnistui: {e}"
                            return self._json(velho_julkinen())
                if self.path == "/api/komento":
                    komento = siisti(pyynto.get("komento", ""))
                    if komento not in ("hae", "aja"):
                        return self._json({"ok": False, "virhe": f"tuntematon komento {komento}"})
                    with SELAIN_AJO_LUKKO:
                        if SELAIN_AJO["komento"]:
                            return self._json({"ok": False,
                                               "virhe": f"{SELAIN_AJO['komento']} on jo käynnissä"})
                        SELAIN_AJO.update(komento=komento, loki=[], virhe="")
                    saie = threading.Thread(target=_aja_selaimesta, args=(komento,),
                                            daemon=True)
                    saie.start()
                    return self._json({"ok": True, "komento": komento})
                return self._json({"ok": False, "virhe": "tuntematon polku"}, 404)
            except Exception as e:
                return self._json({"ok": False, "virhe": str(e)}, 500)

    cfg0 = lue_config()
    ledger0 = lue_ledger()
    n_rev = _korjaa_revolut_selitteet(ledger0)
    if n_rev:
        m_u, m_a = uudelleenluokittele_saantorivit(ledger0, cfg0)
        print(f"Korjattu Revolut-selitteet {n_rev} riviltä; {m_u} luokiteltu uudelleen "
              f"({m_a} palasi avoimeksi).")
    n_per = taydenna_perusteet(ledger0, cfg0)
    if n_per:
        print(f"Täydennetty luokitteluperuste {n_per} riville.")
    if n_rev or n_per:
        kirjoita_ledger(ledger0)
        kirjoita_tarkistettavat(ledger0)
    rakenna_raportit(ledger0, cfg0, kk=13)
    osoite = f"http://127.0.0.1:{portti}/raportti.html"
    print(f"Selaa-tila {VERSIO}: {osoite}  (muutokset tallentuvat heti pääkirjaan; Ctrl-C lopettaa)")
    try:
        webbrowser.open(osoite)
    except Exception:
        pass
    global SELAA_KAYNNISSA
    SELAA_KAYNNISSA = True
    try:
        with http.server.ThreadingHTTPServer(("127.0.0.1", portti), Kasittelija) as srv:
            srv.serve_forever()
    except KeyboardInterrupt:
        print("\nSuljetaan\u2026")
        SELAA_KAYNNISSA = False
        with _raportti_lukko:
            odottaa = _raportti_ajastin is not None and _raportti_ajastin.is_alive()
            if odottaa:
                _raportti_ajastin.cancel()
        if odottaa:
            _kirjoita_raportti_taustalla()  # viimeisin muutos myös levylle


def cmd_onko_dataa(args):
    """Käynnistimen kysymys: avataanko raportti vai näytetäänkö aloitusohje?

    Käynnistin ei voi katsoa tiedostoa itse, koska pääkirja voi olla aivan eri
    kansiossa kuin ohjelma (datakansio.txt). Aiemmin se katsoi polkua
    data/tapahtumat.csv omasta kansiostaan, mikä erotetussa asennuksessa on
    aina väärä paikka — raportti jäi avaamatta, vaikka ajo onnistui.

    Vastaus on paluuarvo eikä tuloste: 0 = pääkirjassa on rivejä."""
    try:
        rivit = LEDGER.read_text(encoding="utf-8").splitlines()
    except OSError:
        rivit = []
    sys.exit(0 if len(rivit) > 1 else 1)


def main():
    p = argparse.ArgumentParser(description="Kevyt henkilökohtainen rahaputki")
    ala = p.add_subparsers(dest="komento", required=True)
    aj = ala.add_parser("aja", help="lue inbox/, luokittele, raportoi")
    aj.add_argument("--siivoa-alkaen", action="store_true", dest="siivoa_alkaen",
                    help="poista pääkirjasta alkupäivää vanhemmat rivit (muuten vain varoitetaan)")
    p.add_argument("--pakota", action="store_true",
                   help="ohita toisen koneen lukko (vain jos olet varma ettei ajo ole kesken)")
    pv = ala.add_parser("pankkihaku",
                        help="ohjattu käyttöönotto: Enable Banking -sovellus, avain ja pankit")
    pv.add_argument("--uusi-sovellus", action="store_true", dest="uusi_sovellus",
                    help="kysy tunnukset uudelleen, vaikka ne olisi jo tallennettu")
    pv.add_argument("--paivia", type=int, default=89,
                    help="montako päivää historiaa lopuksi noudetaan (oletus 89)")
    h = ala.add_parser("hae", help="nouda tilitapahtumat pankkirajapinnasta inboxiin")
    h.add_argument("--palvelu", choices=["mock", "gocardless", "enablebanking"])
    h.add_argument("--paivia", type=int, default=89,
                   help="montako päivää historiaa noudetaan (oletus 89)")
    h.add_argument("--istunto", metavar="SESSION_ID",
                   help="listaa olemassa olevan EB-istunnon tilit ja uid:t")
    h.add_argument("--yhdista", metavar="PANKKI",
                   help="Enable Banking: valtuuta pankki ja tallenna tilit (sandboxissa: mock)")
    h.add_argument("--saldot", action="store_true",
                   help="hae myös tilien saldot täsmäytystä varten (yksi lisähaku "
                        "per tili pankin neljän vuorokausihaun budjetista)")
    h.add_argument("--raaka", action="store_true",
                   help="tallenna pankin täydet raakavastaukset tiedostoon (data/raaka/) diagnoosia varten")
    o = ala.add_parser("opi", help="lue täytetty tarkistettavat.csv")
    o.add_argument("--oletus", help="niputa loput luokittelemattomat tähän kategoriaan (esim. Henkilömaksut)")
    r = ala.add_parser("raportti", help="rakenna raportit uudelleen")
    r.add_argument("--kk", type=int, default=13, help="montako kuukautta (oletus 13)")
    r.add_argument("--kaikki", action="store_true", help="kaikki kuukaudet")
    ala.add_parser("budjetti-ehdotus", help="ehdota raamit toteuman mediaanista")
    ala.add_parser("tarkista-kortit", help="täsmäytä korttilaskujen maksut vs. tuodut korttirivit")
    ala.add_parser("siivoa-kopiot", help="poista tiedostokopioista ((1).pdf) kahteen kertaan tuodut rivit")
    ala.add_parser("luokittele", help="aja säännöt uudelleen koko pääkirjalle (saannot.csv:n käsimuokkauksen jälkeen)")
    s = ala.add_parser("selaa", help="avaa raportti muokattavana selaimessa (paikallinen palvelin)")
    s.add_argument("--portti", type=int, default=8765)
    k = ala.add_parser("kurkista", help="näytä miten CSV tulkittaisiin")
    k.add_argument("tiedosto")
    ala.add_parser("onko-dataa", help=argparse.SUPPRESS)  # käynnistimen sisäinen
    args = p.parse_args()
    # Käynnistys koskee tietokansiota ensimmäistä kertaa: kansiot, config ja
    # lukko. Pilvikansiossa juuri se on hitain hetki, ja siihen asti ruudulla
    # ei ole mitään. Vahti kertoo, mitä odotetaan, jos odotus venyy.
    vahti = _hidas_vahti(f"\u23f3 Odotetaan tietokansiota: {DATAJUURI}\n"
                         "   Pilvikansio hakee tiedostoja \u2014 t\u00e4m\u00e4 ei ole jumi. "
                         "Anna sille hetki.")
    with ExitStack() as pino:
        with vahti:
            varmista_aloitus()
            pino.enter_context(paakirjalukko(args.komento,
                                             getattr(args, "pakota", False)))
        {"aja": cmd_aja, "hae": cmd_hae, "opi": cmd_opi, "raportti": cmd_raportti,
         "pankkihaku": cmd_pankkihaku,
         "budjetti-ehdotus": cmd_budjetti, "kurkista": cmd_kurkista,
         "selaa": cmd_selaa, "tarkista-kortit": cmd_tarkista_kortit,
         "siivoa-kopiot": cmd_siivoa_kopiot, "luokittele": cmd_luokittele,
         "onko-dataa": cmd_onko_dataa}[args.komento](args)


if __name__ == "__main__":
    _varmista_python()
    _siisti_konsoli()
    try:
        main()
    except KeyboardInterrupt:
        # Ctrl-C on käyttäjän tapa lopettaa, ei virhe. Traceback näyttäisi
        # siltä kuin jokin olisi mennyt rikki — eikä mikään mennyt.
        print("\nKeskeytetty.")
        sys.exit(130)
