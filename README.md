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
2. **Pura** ZIP ja **siirrä kansio pysyvään paikkaan** — esimerkiksi
   Tiedostot-kansioon (`Documents`). Voit myös nimetä sen uudelleen vaikka
   `Rahaputki`. **Älä jätä sitä Lataukset-kansioon**: kirjanpitosi jää
   asumaan tähän kansioon, ja Lataukset on paikka, jonka ihmiset tyhjentävät.
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

| Tiedosto | Mikä |
|---|---|
| `inbox/` | tänne pankkien CSV:t; käsitellyt siirtyvät `inbox/arkisto/` |
| `data/tapahtumat.csv` | kirjanpitosi — koko totuus, pelkkää tekstiä |
| `saannot.csv` | kauppias → kategoria -säännöt |
| `config.json` | kategoriat, lähteiden sarakekartat, omat IBANit |
| `raportit/raportti.html` | kuukausigraafi, budjettivertailu, matriisi |

Varmuuskopiointi on kansion kopioimista. Jos haluat kirjanpitosi useammalle
koneelle, pidä kansio pilvitallennuksessa (esim. iCloud, OneDrive, Google
Drive) — mutta aja putki vain yhdellä koneella kerrallaan, jotta synkronointi
ei tuota ristiriitaisia kopioita.

## Päivittäminen

Kun työkalusta ilmestyy uusi versio, **älä siirrä kirjanpitoasi uuteen
kansioon** — tee päinvastoin. Lataa uusi ZIP, pura se, ja kopioi sieltä
**vain nämä tiedostot** vanhan kansiosi päälle:

```
kirjanpito.py   laskusta_csv.py   Aloita.command   Aloita.bat   OHJE.md   README.md
```

Näin datasi (`data/`, `inbox/`, `config.json`, `saannot.csv`, `budjetti.csv`)
pysyy koskemattomana paikallaan. Voit sen jälkeen poistaa purkamasi uuden
kansion. Kirjanpitosi ei ole koskaan noissa ohjelmatiedostoissa.

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
