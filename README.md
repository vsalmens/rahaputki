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
2. **Pura** ZIP haluamaasi kansioon (esim. Tiedostot tai Työpöytä)
3. **Kaksoisklikkaa** käynnistintä:
   - macOS: `Aloita.command`
   - Windows: `Aloita.bat`

Ensimmäinen käynnistys luo kansiot ja mallitiedostot puolestasi ja kertoo mitä
tehdä seuraavaksi. Vie sitten verkkopankeistasi tiliotteet CSV-muodossa
kansioon `inbox/` ja kaksoisklikkaa käynnistintä uudelleen — raportti aukeaa
selaimeen, ja voit luokitella tapahtumat suoraan siinä.

### Ensimmäisellä kerralla käyttöjärjestelmä varoittaa

Molemmat suojaavat internetistä ladatuilta tiedostoilta. Tämä on normaalia:

- **macOS**: jos kaksoisklikkaus ei avaa mitään, klikkaa `Aloita.command`
  hiiren oikealla → **Avaa** → **Avaa**. Tämä tarvitaan vain kerran.
- **Windows**: jos näet "Windows protected your PC", klikkaa **Lisätietoja** →
  **Suorita silti**.

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
