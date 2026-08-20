# Rahaputki — kevyt, pankkiriippumaton kulutusseuranta

Suunnitteluperiaate on sama, joka piti Netto-välilehtesi hengissä 18 vuotta:
**ei vakiopäivää, ei pakkoa, aina voi palata.** Putki on idempotentti — saman
tiliotteen voi tuoda vaikka kolmesti, päällekkäiset rivit ohitetaan
automaattisesti. Jos pidät kolmen kuukauden tauon, viet vain kolmen kuukauden
otteet ja jatkat siitä mihin jäit. Mikään ei "mene rikki" tauosta.

Vaatimukset: Python 3.9+. Perusputki toimii ilman asennettavia kirjastoja;
lisäosat tarvitsevat omansa: automaattinen pankkihaku `pyjwt` + `cryptography`,
PDF-laskujen muunnin `pdfplumber`. Asenna aina saman tulkin kautta jolla ajat:
`python3 -m pip install pyjwt cryptography pdfplumber --break-system-packages`
(Homebrew-Python vaatii tuon lipun; `python3 -m pip` takaa ettei paketti
eksy toisen Python-asennuksen hyllyyn).

## Pikastartti: vuosi taaksepäin

1. Vie verkkopankeista CSV:t ajalta **1.7.2025 → tänään** kansioon `inbox/`
   (huomaa: sama alkupäivä kuin Netto-taulukkosi rivillä 1.7.2025 — voit
   ristiintarkistaa säästösumman nettovarallisuuden muutosta vasten):
   - **OP-tili**: op.fi → tili → tapahtumat → lataa/vie CSV (aikaväli valittavissa)
   - **Luottokortit (OP & S-Pankki Visa)**: korttitapahtumia ei saa CSV:nä,
     joten historia tuodaan kuukausilaskujen PDF:istä muuntimella
     (jatkuvaan käyttöön kortitkin saa automaattihaulla, ks. oma lukunsa):
     `python3 laskusta_csv.py laskut/*.pdf` → tapahtumat ilmestyvät
     `inbox/`-kansioon CSV:nä. Muunnin tunnistaa kortin (OP / S-Pankki)
     laskun tekstistä, hoitaa vuodenvaihteen, kirjaa hyvitykset oikein ja
     ohittaa laskun maksusuoritukset. **Aja ensin `--nayta`-tilassa yhtä
     laskua vasten** ja tarkista että jokainen ostorivi saa ✔-merkin —
     laskupohjat vaihtelevat, ja rivikuvio on säädettävissä. Vaatii:
     `pip install pdfplumber` (tai poppler-utilsin `pdftotext`).
     *Tärkeää:* tilillä näkyvä kuukausittainen korttilaskun veloitus
     ohitetaan siirtona, ettei sama raha näy kahdesti — säännöissä on
     tälle valmiit rivit (`korttien lasku`, `luottokort` → Siirto);
     tarkista että ne osuvat oman tiliotteesi sanamuotoon.
   - **S-Pankki**: verkkopankki → tili/kortti → tapahtumien vienti CSV
   - **Revolut**: sovellus → tili → Statement → CSV (Excel), valitse aikaväli.
     Vain `COMPLETED`-tilaiset rivit luetaan; Fee lisätään summaan. Myös
     "consolidated statement" käy sellaisenaan: pudota inboxiin, putki
     tunnistaa monilohkoisen rakenteen ja poimii vain Personal Account
     -taulukot (rahastotaskusiirrot luokittuvat Sijoituksiksi, eivät menoiksi).
   - **Holvi** (valinnainen): henkilökohtaiseen budjettiin riittää yleensä se,
     mitä firmasta tulee *ulos sinulle* — ja se näkyy jo OP-tilillä saapuvana
     (palkka/osinko). Holvin voi siis jättää kokonaan firman kirjanpidon
     puolelle. Tuo Holvi-CSV vain jos haluat silmäillä myös firman rahavirtaa.

2. Aja: `python3 kirjanpito.py aja`

3. Avaa `raportit/tarkistettavat.csv` (Sheets/Excel/editori kelpaa). Täytä
   `kategoria`-sarake tuntemattomille riveille. Jos sama kauppias toistuu,
   kirjoita `saanto`-sarakkeeseen osamerkkijono (esim. `kukkakauppa ruusu`) —
   sääntö tallentuu ja hoitaa jatkossa kaikki vastaavat rivit, myös vanhat.
   **Ensimmäinen kierros on työläin** (ehkä 30–60 min vuoden datalle); sen
   jälkeen säännöt kattavat tyypillisesti ~90 % riveistä.

4. Aja: `python3 kirjanpito.py opi` — ja avaa `raportit/raportti.html`.

5. Kun täysiä kuukausia on kertynyt: `python3 kirjanpito.py budjetti-ehdotus`
   ehdottaa raamit toteuman mediaanista. Kopioi/muokkaa haluamasi rivit
   tiedostoon `budjetti.csv`, niin raportti alkaa näyttää toteuma vs. raami.

## Rituaali jatkossa (~15–30 min, milloin huvittaa)

1. Vie tuoreet otteet `inbox/`-kansioon — tai jos pankkihaku on käytössä,
   pelkkä `python3 kirjanpito.py hae` (päällekkäisyys ei haittaa — vie
   mieluummin liikaa kuin liian vähän)
2. `python3 kirjanpito.py aja`
3. Täytä tarkistettavat → `python3 kirjanpito.py opi`
4. Katso `raportti.html`. Halutessasi liitä `raportit/yhteenveto_kk.csv`
   Kirjanpito-sheetin uudelle välilehdelle (suomalainen puolipiste+pilkku-
   muoto, liimautuu suoraan). Kvartaaleittain: päivitä samalla Netto.

## Automaattinen pankkihaku (`hae`)

CSV-vientien sijaan tapahtumat voi noutaa suoraan pankeista PSD2-rajapinnan
kautta (Enable Banking): `python3 kirjanpito.py hae` kirjoittaa tuoreet
tapahtumat inboxiin pankkinatiiveina CSV:inä, ja `aja` hoitaa loput samalla
putkella — dedupe tekee noudosta idempotentin, eli tuplahaku ei koskaan
tuota tuplarivejä.

Käyttöönotto kerran:

1. Luo Enable Banking -sovellus (app_id + RS256-yksityisavain `.pem`).
   Säilytä avain pilvisynkan **ulkopuolella** (esim. `~/.avaimet/`,
   `chmod 600`) — se on lukupääsy tileihisi.
2. `.env`-tiedosto putken kansioon: `EB_APP_ID=…` ja `EB_KEY_PATH=…`.
   Älä jaa äläkä versioi tätä tiedostoa.
3. `config.json` → `pankkihaku`: `palvelu`, sovellukselle rekisteröity
   `redirect_url`, ja `tilit`-lista muotoa
   `{"tili": "OP-tili", "account_id": "<uid>", "alkaen": "YYYY-MM-DD"}`.
   Tilin nimi ohjaa CSV-muodon: `OP-tili` / `S-Pankki` / `Revolut`
   kirjoitetaan tiliformaateissa, kaikki muut (luottokortit ym.)
   kortti-muodossa jossa Tili-sarake kantaa nimen pääkirjaan asti.
4. Pankkien valtuutus: `hae --yhdista PANKKI` avaa velhon (linkki →
   pankin oma vahva tunnistautuminen → liitä paluuosoitteen `?code=`).
   `hae --istunto SESSION_ID` listaa olemassa olevan istunnon tilit
   uid:einesi, jos valtuutus on jo tehty muualla samalla sovelluksella.

Katkopäiväsääntö reittiä vaihdettaessa: tilikohtainen `alkaen` asetetaan
viimeisen muulla reitillä tuodun päivän **päälle**, ei sen jälkeiselle
päivälle — limitys on samalla lähteellä ilmaista, mutta tunninkin aukko on
äänetön reikä. Reittien sauma tarkistetaan silmin kerran; sen jälkeen
API-rivit deduplikoituvat keskenään täydellisesti.

Hyvä tietää: pankit rajaavat noudot ilman asiakkaan läsnäoloa (~4/vrk/tili;
`429`-vastaus = kiintiö täynnä, yritä huomenna) ja historian ~90 päivään
(`--paivia` säätää, oletus 89). Suostumukset erääntyvät pankeittain
~90–180 päivän välein — silloin yksi `--yhdista`-kierros ja uid:ien
päivitys. Rituaali kevenee muotoon: `hae` → `aja` → avoimien kuittaus.

## Muokkaus suoraan raportista

Kaksi tapaa, sama näkymä:

1. **`python3 kirjanpito.py selaa`** käynnistää paikallisen palvelimen ja avaa
   raportin selaimeen. Jokaisen tapahtuman rivillä on kategoriavalikko ja
   tarkenne-kenttä — muutos **tallentuu pääkirjaan heti**. Rivin
   "sääntö"-linkki esitäyttää sääntölomakkeen (malli → kategoria:tarkenne);
   sääntö tallentuu saannot.csv:hen ja luokittelee samalla avoimet rivit.
   Valikon "+ uusi kategoria…" lisää kategorian config.json:iin lennossa.
   Taulukot ja käyrät päivittyvät kun lataat sivun uudelleen. Ctrl-C sammuttaa.
2. **Pelkkä raportti.html avattuna** (ilman palvelinta): samat muokkaukset
   kerätään muistiin ja alapalkin nappi lataa ne muutokset.csv-tiedostona.
   `python3 kirjanpito.py opi` etsii muutokset*.csv:t automaattisesti myös
   Downloads-kansiosta, vie ne pääkirjaan ja merkitsee käsitellyiksi.

### Säännöt raportissa

Raportin lopussa on avattava **Säännöt**-osio: suodata, katso ja **poista**
sääntöjä suoraan (selaa-tilassa heti, tiedostotilassa muutokset.csv:n kautta).
Poisto ei koske jo luokiteltuja rivejä — ne korjataan riviltä itseltään.
Sääntölomake varoittaa, jos malli on maksunvälittäjän nimi (Klarna, Paytrail,
Zettle, VFI*, …): välittäjä ei ansaitse sääntöä, kauppias ansaitsee.
Tarkenteet normalisoituvat aina pienaakkosiksi — myös vanha data siistiytyy
itsestään seuraavalla kirjoituskerralla.

## Yhteistalous — jaetut kotitalouskulut

Raportin **Yhteistalous**-osio on kimppatalouden reskontra: valitse valikosta
poimintakategoria (esim. `Yhteistalous`), niin sen rivit jaetaan tarkenteen
mukaan — viikkojako-tarkenteet (oletuksena `ruokaboksi`) painotetaan
klikattavan läsnäoloruudukon mukaan toimitusviikoille, palautus-tarkenteet
ovat jäsenten maksuja pankkiirille, ja kaikki muut tarkenteet (netti,
sähkö, …) jaetaan tasan. Kuukausittaiset vakiohyvitykset (esim. auton
lataussähkö) ja kertaluontoiset käsikirjaukset osallistujavalintoineen
lisätään lomakkeilla. Saldot summautuvat aina nollaan, ja 🖨-linkki avaa
tulostettavan erittelyn (selaimen tulostuksesta PDF). Asetukset ja
läsnäolot elävät tiedostossa `data/yhteistalous.json`.

## Tiedostot

| Tiedosto | Mikä |
|---|---|
| `inbox/` | tänne pankkien CSV:t; käsitellyt siirtyvät `inbox/arkisto/` |
| `data/tapahtumat.csv` | pääkirja — koko totuus, pelkkää tekstiä, versioi/varmuuskopioi vapaasti |
| `saannot.csv` | kauppias → kategoria -säännöt (esisiemennetty omista 2018–2020 luokistasi) |
| `laskusta_csv.py` | korttilaskujen PDF → CSV -muunnin (`--nayta` näyttää rivien tulkinnan) |
| `config.json` | lähteiden sarakekartat, kategoriat, omat IBANit |
| `config.esimerkki.json`, `saannot.esimerkki.csv` | riisutut aloituspohjat — kopioi ilman .esimerkki-päätettä ja muokkaa omiksesi |
| `budjetti.csv` | kk-raamit (täytetään vasta kun toteumaa on) |
| `raportit/raportti.html` | kuukausigraafi + budjettivertailu + matriisi |
| `raportit/yhteenveto_kk.csv` | sama matriisi Sheets-liitosta varten |
| `raportit/yhteistalous_erittely.html` | tulostettava kotitalouserittely (selaimesta PDF) |
| `data/yhteistalous.json` | yhteistalouden tila: tasauspäivä (mihin asti yhteiskulut on huomioitu), kk-vakiot, läsnäolot, kirjaukset — raportin osio ylläpitää tätä puolestasi |
| `.env` | pankkihaun avaimet — **ei jaeta, ei versioida** |

## Kustomointi

- **Kategoriat**: `config.json` → `kategoriat`. Tyypit: `meno`, `tulo`,
  `pois` (siirrot/sijoitukset — eivät näy luvuissa). Lisää, poista, nimeä
  vapaasti; `opi` validoi että käytät olemassa olevia nimiä.
- **Säännöt**: `saannot.csv`, järjestys ratkaisee (ensimmäinen osuma voittaa).
  Lisäys sijoittaa tarkemman mallin automaattisesti yleisemmän edelle
  (esim. `uber * eats` → Ravintolat asettuu `uber` → Liikkuminen -säännön
  yläpuolelle, jolloin poikkeus voittaa). Raportin Säännöt-osiossa on lisäksi
  ↑/↓-nuolet käsijärjestelyyn (selaa-tilassa; siirron jälkeen rivit
  luokitellaan uudelleen automaattisesti). `re:`-etuliitteellä regex, esim.
  `re:\bhus\b;Palkka` (pelkkä `hus` osuisi Bauhausiin). Valinnainen kolmas
  sarake on summaehto: `max=50` tai `min=50` (itseisarvo euroina). Esim.
  `maarit;Päivittäistavarat;max=50` ja perään `maarit;TARKISTA` → pienet
  ruokarahat luokittuvat itsestään, isommat jäävät aina käsin katsottaviksi.
- **Loppujen niputus**: kun tarkistettavat on käyty läpi, jäljelle jääneet voi
  niputtaa oletuskategoriaan: `python3 kirjanpito.py opi --oletus Henkilömaksut`.
  Aja tämä vasta viimeisenä — se vie KAIKKI jäljellä olevat, myös ne jotka
  säännöt jättivät tahallaan listalle (esim. yli 50 € henkilömaksut).
- **Omat IBANit** `config.json`:iin → siirrot omille tileille tunnistetaan
  automaattisesti Siirto-kategoriaan.
- **Uusi pankki / muuttunut CSV-muoto**: aja
  `python3 kirjanpito.py kurkista tiedosto.csv` — se näyttää enkoodauksen,
  erottimen ja otsikot. Lisää/korjaa lähde `config.json`:iin niillä
  sarakenimillä. Sarakenimet voi antaa listana vaihtoehtoja, ensimmäinen
  löytyvä voittaa. *(Pankit muuttavat vientimuotojaan aika ajoin — tämä on
  putken ainoa liikkuva osa, ja siksi se on konfiguraatiota eikä koodia.)*

## Sudenkuopat, jotka on jo mietitty (mutta hyvä tietää)

- **Kahdenkertainen laskenta**: kun korttitapahtumat ja tiliote tuodaan
  molemmat, korttilaskun veloitus tilillä on merkittävä siirroksi. Sama
  koskee Revolut-latauksia (OP-puolen `revolut`-rivi → Siirto; kulutus
  lasketaan Revolutin omista riveistä).
- **Käteisnostot** kannattaa ohjata säännöllä johonkin kategoriaan jo
  nostohetkellä — käteisen jälkikäteisseuranta ei toimi käytännössä
  kenelläkään. Valitse kategoria oman käytäntösi mukaan `saannot.csv`:ssä.
- **Sijoitukset ja siirrot** eivät kuulu kulutuslukuihin (muuten "menot"
  pomppaa aina kun siirrät rahaa Seligsoniin). Ne elävät Netto-välilehdellä.
- **TARKISTA-rivit** lasketaan menoihin ja raportti varoittaa niistä — luvut
  eivät siis koskaan hiljaa valehtele alakanttiin.

## Tunnetut rajoitteet

- OP:n, S-Pankin ja Holvin CSV-sarakenimet on asetettu parhaan tiedon mukaan
  (alkuvuosi 2026); jos vienti ei tunnistu, `kurkista` + yksi rivi
  config.json:iin korjaa asian. Revolutin muoto on vakain.
- Korttilaskujen PDF-pohjat vaihtelevat pankeittain ja vuosittain; muuntimen
  rivikuvio on paras arvaus. `--nayta` paljastaa heti, jos jokin rivityyppi
  jää poimimatta — tulosteen (summat sotkettuina) perusteella kuvio säätyy
  yhdellä regex-muutoksella. Skannattuja (kuvapohjaisia) laskuja muunnin ei
  lue ilman OCR:ää.
