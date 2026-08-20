# Rahaputki

Kevyt, pankkiriippumaton kulutusseuranta. Vie verkkopankkiesi CSV-tiedostot
yhteen kansioon, ja saat kuukausigraafin, budjettivertailun ja selaimessa
muokattavan erittelyn siitä, mihin rahasi menivät.

**Kaikki pysyy omalla koneellasi.** Ei tiliä, ei pilvipalvelua, ei tilitietojen
luovutusta kolmannelle. Kirjanpitosi on yksi tekstitiedosto omassa kansiossasi.

**Ei vakiopäivää, ei pakkoa, aina voi palata.** Putki on idempotentti: saman
tiliotteen voi tuoda vaikka kolmesti, päällekkäiset rivit ohitetaan. Jos pidät
kolmen kuukauden tauon, viet kolmen kuukauden otteet ja jatkat siitä mihin jäit.
Mikään ei mene rikki tauosta.

## Aloitus

1. **Lataa** työkalu: `Code` → `Download ZIP`
2. **Pura** ZIP ja siirrä kansio johonkin, missä se saa jäädä pysyvästi —
   esimerkiksi Tiedostot-kansioon (`Documents`). Voit myös nimetä sen
   uudelleen vaikka `Rahaputki`. Kirjanpitosi jää asumaan tähän kansioon,
   ja Lataukset on paikka, jonka ihmiset tyhjentävät.

   Kansion voi siirtää tai nimetä uudelleen myöhemminkin, milloin tahansa:
   siirrä vain koko kansio kerralla, niin kaikki pysyy tallessa. Mitään
   polkuja ei ole tallennettu minnekään.
3. **Kaksoisklikkaa** käynnistintä:
   - macOS: `Aloita.command`
   - Windows: `Aloita.bat`

Ensimmäinen käynnistys luo kansiot ja mallitiedostot puolestasi ja kertoo mitä
tehdä seuraavaksi. Vie sitten verkkopankeistasi tiliotteet CSV-muodossa
kansioon `inbox/` ja kaksoisklikkaa käynnistintä uudelleen — raportti aukeaa
selaimeen, ja voit luokitella tapahtumat suoraan siinä.

### Ensimmäisellä kerralla käyttöjärjestelmä estää käynnistimen

Tämä on normaalia eikä tarkoita, että jokin olisi vialla: käyttöjärjestelmät
estävät oletuksena kaikki internetistä ladatut ohjelmat, joita ei ole
allekirjoitettu maksullisella kehittäjätunnuksella. Sallit sen kerran, ja
jatkossa käynnistin toimii kaksoisklikkauksella.

**macOS** näyttää ilmoituksen *"Apple could not verify 'Aloita.command' is free
of malware…"*. Vanha kikka (oikea klikkaus → Avaa) **ei enää toimi** macOS
Sequoiassa (15) ja sitä uudemmissa. Tee näin:

1. Klikkaa ilmoituksesta **Done** / **Valmis** — älä valitse "Move to Bin"
2. Avaa **Järjestelmäasetukset** → **Tietosuoja ja turvallisuus**
   (System Settings → Privacy & Security)
3. Vieritä alas kohtaan **Turvallisuus**. Siellä lukee, että
   `Aloita.command` estettiin — klikkaa vieressä olevaa **Avaa silti**
   (Open Anyway) ja vahvista salasanalla tai Touch ID:llä
4. Kaksoisklikkaa `Aloita.command` uudelleen ja valitse **Avaa**

Jos "Avaa silti" ei jostain syystä näy, sama onnistuu Terminalissa yhdellä
rivillä. Avaa **Terminal** (Spotlight-haku: `terminal`), kirjoita `xattr -dr
com.apple.quarantine ` — **välilyönti perään** — vedä sitten purettu
rahaputki-kansio ikkunaan ja paina Enter:

```
xattr -dr com.apple.quarantine /polku/rahaputki-kansioon
```

**Windows** näyttää sinisen "Windows protected your PC" -ikkunan: klikkaa
**Lisätietoja** (More info) → **Suorita silti** (Run anyway).

### Vaatimukset

Python 3.9 tai uudempi. macOS:llä se on usein valmiina; jos ei, käynnistin
kertoo sen ja ohjaa lataussivulle. Windowsissa asenna Python osoitteesta
[python.org/downloads](https://www.python.org/downloads/) — **muista rastittaa
asennuksessa "Add python.exe to PATH"**.

Perustoiminnot eivät tarvitse mitään asennettavia kirjastoja. Lisäosat kyllä:
automaattinen pankkihaku (`pyjwt`, `cryptography`) ja korttilaskujen
PDF-muunnin (`pdfplumber`).

## Rituaali jatkossa (~15–30 min, milloin huvittaa)

1. Vie tuoreet tiliotteet kansioon `inbox/`
2. Kaksoisklikkaa käynnistintä
3. Luokittele avoimet rivit selaimessa — toistuvasta kauppiaasta tee sääntö,
   niin se hoituu jatkossa itsestään

Ensimmäinen kierros on työläin (vuoden datalle ehkä 30–60 min). Sen jälkeen
säännöt kattavat tyypillisesti noin 90 % riveistä.

## Mitä kansiossa on

Kansiossa on kahdenlaista tavaraa, ja jako ratkaisee kaiken päivittämisessä:
**ohjelma tulee paketista ja on korvattavissa, kaikki muu on sinun eikä ole
missään muualla.**

| Sinun — älä koskaan korvaa | Mikä |
|---|---|
| `data/tapahtumat.csv` | kirjanpitosi — koko totuus, pelkkää tekstiä |
| `data/` muuten | varmuuskopiot, yhteistalouden tila |
| `saannot.csv` | kauppias → kategoria -säännöt, karttuu käytössä |
| `config.json` | kategoriat, lähteiden sarakekartat, omat IBANit |
| `budjetti.csv` | kuukausiraamit |
| `inbox/` | pankkien CSV:t; käsitellyt siirtyvät `inbox/arkisto/` |
| `.env` | pankkihaun tunnukset — **piilotiedosto**, ei näy Finderissa |
| `raportit/` | syntyy uudelleen joka ajolla; ei tarvitse varjella |

| Ohjelma — tulee paketista | Mikä |
|---|---|
| `kirjanpito.py`, `laskusta_csv.py` | itse työkalu |
| `Aloita.command`, `Aloita.bat` | käynnistimet |
| `OHJE.md`, `README.md` | ohjeet |
| `config.esimerkki.json`, `saannot.esimerkki.csv` | mallipohjat, joista ensikäynnistys tekee omasi |

Varmuuskopiointi on kansion kopioimista. Jos haluat kirjanpitosi useammalle
koneelle, pidä kansio pilvitallennuksessa (esim. iCloud, OneDrive, Google
Drive) — mutta aja putki vain yhdellä koneella kerrallaan, jotta synkronointi
ei tuota ristiriitaisia kopioita.

## Päivittäminen

Kun työkalusta ilmestyy uusi versio, **älä siirrä kirjanpitoasi uuteen
kansioon** — tee päinvastoin:

1. Lataa ja pura uusi ZIP
2. Avaa purettu kansio, valitse **kaikki tiedostot** (⌘A / Ctrl+A) ja vedä ne
   vanhan kansiosi päälle
3. Vastaa **Korvaa** (Replace) — tämä on turvallista
4. Poista purkamasi uusi kansio

Ladattu paketti sisältää vain ohjelmatiedostot: `kirjanpito.py`,
`laskusta_csv.py`, käynnistimet, ohjeet ja `.esimerkki`-mallipohjat. Siinä ei
ole `data/`-kansiota, `config.json`:ia eikä `saannot.csv`:tä, joten mikään
omasi ei voi ylikirjoittua — ei edes vahingossa.

> **Vedä tiedostot, älä kansiota.** Jos vedät koko kansion toisen kansion
> päälle, macOS korvaa kohdekansion kokonaan sen sijaan että yhdistäisi
> sisällöt — ja veisi datasi mennessään. Tiedostojen vetäminen on turvallista.

### Miksi näin päin

Toinen suunta — purkaa uusi paketti tyhjäksi kansioksi ja siirtää oma data
sinne — kuulostaa siistimmältä, mutta on selvästi vaarallisempi:

- **`.env` on piilotiedosto.** Se ei näy Finderissa ilman erillistä
  näppäinyhdistelmää (⌘⇧.), joten pankkihaun tunnukset jäisivät helposti
  siirtämättä — ja huomaisit sen vasta kun haku lakkaa toimimasta.
- **Uusi kansio näyttää toimivalta myös tyhjänä.** Jos käynnistät sen ennen
  datan siirtoa, se luo mallipohjista uuden `config.json`:in ja tyhjän
  kirjanpidon eikä valita mistään. Sinulla olisi kaksi kansiota, joista
  kumpikin näyttää oikealta, ja vain toisessa on tapahtumasi.
- **Väärin menemisen hinta on eri.** Jos tässä suunnassa unohdat kopioida
  jonkin ohjelmatiedoston, jäät vanhaan versioon — se korjaantuu kopioimalla
  uudelleen. Toisessa suunnassa unohdus tarkoittaa, että kirjanpitosi jää
  toiseen kansioon.

Nyrkkisääntö: **data pysyy paikallaan, ohjelma vaihtuu sen ympärillä.**

## Tarkemmat ohjeet

[**OHJE.md**](OHJE.md) kertoo kaiken muun: pankkikohtaiset vientiohjeet,
korttilaskujen PDF-muunnin, automaattinen pankkihaku PSD2-rajapinnan kautta,
budjetti, yhteistalouden kulujenjako, sääntöjen hienosäätö ja tunnetut
sudenkuopat.

## Komentoriviltä

Käynnistin riittää useimpiin tarpeisiin, mutta kaikki toimii myös suoraan:

```
python3 kirjanpito.py aja        # lue inbox/, luokittele, raportoi
python3 kirjanpito.py selaa      # avaa raportti muokattavana selaimeen
python3 kirjanpito.py opi        # lue täytetty tarkistettavat.csv takaisin
```

Windowsissa komento on `py` eikä `python3`.
