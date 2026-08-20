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
PDF-muunnin (`pdfplumber`). Pankkihaun kirjastot asentaa ohjattu käyttöönotto
puolestasi, joten niistä ei tarvitse tietää mitään.

## Tapahtumat suoraan pankista (valinnainen)

CSV-vientien sijaan tapahtumat voi noutaa suoraan pankeistasi PSD2-rajapinnan
kautta — myös luottokorteilta, joiden tapahtumia ei saa CSV:nä lainkaan.
Käyttöönotto on ohjattu ja vie noin 15 minuuttia:

- macOS: kaksoisklikkaa `Pankkihaku.command`
- Windows: kaksoisklikkaa `Pankkihaku.bat`
- tai komentoriviltä: `python3 koodi/kirjanpito.py pankkihaku`

Velho hoitaa kaiken teknisen puolestasi: asentaa puuttuvat kirjastot, etsii
latautuneen avaintiedoston, avaa oikeat sivut selaimeen, nappaa pankista
palaavan tunnistautumiskoodin ja kirjoittaa asetukset. Sinä teet vain sen,
mitä kukaan ei voi tehdä puolestasi: luot ilmaisen kehittäjätunnuksen
[Enable Bankingiin](https://enablebanking.com/) (suomalainen,
Finanssivalvonnan valvoma) ja tunnistaudut pankkiisi.

Tilitietosi kulkevat silloin sinun oman sovelluksesi kautta suoraan
koneellesi — ei kuukausimaksua eikä välikäsiä. Maksullisetkin vaihtoehdot
(esim. [Syncbank](https://syncbank.app)) edellyttävät saman Enable
Banking -tunnuksen ja sovelluksen luomisen; niissä maksat ohjelmasta, et
siitä että välttyisit rekisteröinniltä.

Jatkossa sama `Pankkihaku`-käynnistin noutaa tuoreet tapahtumat, luokittelee
ne ja avaa raportin yhdellä kaksoisklikkauksella. Rautalankaohje kaikista
vaiheista on [koodi/OHJE.md](koodi/OHJE.md).

## Rituaali jatkossa (~15–30 min, milloin huvittaa)

1. Vie tuoreet tiliotteet kansioon `inbox/`
2. Kaksoisklikkaa käynnistintä
3. Luokittele avoimet rivit selaimessa — toistuvasta kauppiaasta tee sääntö,
   niin se hoituu jatkossa itsestään

Ensimmäinen kierros on työläin (vuoden datalle ehkä 30–60 min). Sen jälkeen
säännöt kattavat tyypillisesti noin 90 % riveistä.

## Mitä kansiossa on

Juuressa on vain käynnistimet ja neljä kansiota. Jokaisella on yksi tehtävä:

```
Rahaputki/
  Aloita.command  Aloita.bat        kaksoisklikkaa nailla
  Pankkihaku.command  .bat          sama, mutta hakee tapahtumat pankista
  inbox/          ← TÄNNE pankkien CSV-tiedostot
  koodi/          ohjelma — päivitys korvaa vain tämän
  asetukset/      config.json, saannot.csv, budjetti.csv, pankkihaku.env
  data/           kirjanpitosi (tapahtumat.csv) ja varmuuskopiot
  raportit/       raportti.html — syntyy uudelleen joka ajolla
```

`inbox/` on tarkoituksella juuressa: se on ainoa kansio, johon kosket joka
kerta. Kaikki muu saa jäädä taustalle.

| Kansio | Sinun vai ohjelman | Mitä sisällä |
|---|---|---|
| `koodi/` | **ohjelman** — korvataan päivityksessä | molemmat skriptit, `OHJE.md`, mallipohjat |
| `asetukset/` | sinun | kategoriat ja lähteet (`config.json`), kauppiassäännöt (`saannot.csv`), kuukausiraamit (`budjetti.csv`), pankkihaun tunnukset (`pankkihaku.env`) |
| `data/` | sinun | `tapahtumat.csv` on koko totuus — pelkkää tekstiä. Lisäksi varmuuskopiot ja yhteistalouden tila. |
| `inbox/` | sinun | pankkien CSV:t; käsitellyt siirtyvät `inbox/arkisto/` |
| `raportit/` | syntyy ajossa | raportti, yhteenvedot, `tarkistettavat.csv` |

Varmuuskopiointi on kansion kopioimista. Jos haluat kirjanpitosi useammalle
koneelle, pidä kansio pilvitallennuksessa (esim. iCloud, OneDrive, Google
Drive) — mutta aja putki vain yhdellä koneella kerrallaan, jotta synkronointi
ei tuota ristiriitaisia kopioita. Pankkihaun yksityisavain on tästä ainoa
poikkeus: se ei kuulu pilveen, ja Rahaputki sijoittaa sen automaattisesti
kotihakemistoon, jos huomaa kansion olevan synkassa.

## Päivittäminen

1. Lataa ja pura uusi ZIP
2. Vedä sen **`koodi`-kansio** oman Rahaputki-kansiosi päälle
3. Vastaa **Korvaa** (Replace)
4. Poista purkamasi paketti

Siinä kaikki. `koodi/`-kansiossa ei ole yhtään sinun tiedostoasi, joten sen
korvaaminen kokonaan on turvallista — se on itse asiassa toivottavaa, koska
näin vanhat tiedostot eivät jää roikkumaan. Kaikki omasi on kansioissa
`asetukset/`, `data/` ja `inbox/`, eikä päivitys kosketa niitä.

Juuren käynnistimiä (`Aloita…`, `Pankkihaku…`) ei tarvitse päivittää: ne ovat
muutaman rivin tynkiä, jotka vain käynnistävät `koodi/`-kansion sisällön.
Jos päivität vanhasta versiosta, kopioi `Pankkihaku.command` /
`Pankkihaku.bat` paketista juureen kerran — tai aja pankkihaku komentoriviltä.

## Lisenssi ja ehdot

MIT-lisenssi ([`LICENSE`](LICENSE)) — käytä, muokkaa ja jaa vapaasti.
[Tietosuojaseloste](koodi/ehdot/tietosuoja.md) ja
[käyttöehdot](koodi/ehdot/kayttoehdot.md) kertovat lyhyesti sen, mikä tässä
on olennaista: ohjelmalla ei ole palvelinta, eikä sen tekijä näe tilitietojasi.
Samat osoitteet kelpaavat Enable Bankingin rekisteröintilomakkeen
Privacy- ja Terms-kenttiin.

## Tarkemmat ohjeet

[**koodi/OHJE.md**](koodi/OHJE.md) kertoo kaiken muun: pankkikohtaiset vientiohjeet,
korttilaskujen PDF-muunnin, automaattinen pankkihaku PSD2-rajapinnan kautta,
budjetti, yhteistalouden kulujenjako, sääntöjen hienosäätö ja tunnetut
sudenkuopat.

## Komentoriviltä

Käynnistin riittää useimpiin tarpeisiin, mutta kaikki toimii myös suoraan:

```
python3 koodi/kirjanpito.py pankkihaku # ohjattu käyttöönotto: haku suoraan pankista
python3 koodi/kirjanpito.py hae        # nouda tuoreet tapahtumat pankeista
python3 koodi/kirjanpito.py aja        # lue inbox/, luokittele, raportoi
python3 koodi/kirjanpito.py selaa      # avaa raportti muokattavana selaimeen
python3 koodi/kirjanpito.py opi        # lue täytetty tarkistettavat.csv takaisin
```

Windowsissa komento on `py` eikä `python3`.
