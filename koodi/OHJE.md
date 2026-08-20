# Rahaputki — kevyt, pankkiriippumaton kulutusseuranta

Suunnitteluperiaate on se, joka pitää kirjanpidon hengissä vuosia:
**ei vakiopäivää, ei pakkoa, aina voi palata.** Putki on idempotentti — saman
tiliotteen voi tuoda vaikka kolmesti, päällekkäiset rivit ohitetaan
automaattisesti. Jos pidät kolmen kuukauden tauon, viet vain kolmen kuukauden
otteet ja jatkat siitä mihin jäit. Mikään ei "mene rikki" tauosta.

Vaatimukset: Python 3.9+. Perusputki toimii ilman asennettavia kirjastoja;
lisäosat tarvitsevat omansa: automaattinen pankkihaku `pyjwt` + `cryptography`,
PDF-laskujen muunnin `pdfplumber`. Pankkihaun kirjastot asentuvat halutessasi
itsestään ohjatussa käyttöönotossa (`pankkihaku`), joten alla olevaa ei
tarvitse osata. Jos asennat käsin, tee se aina saman tulkin kautta jolla ajat:

- **macOS/Linux**: `python3 -m pip install pyjwt cryptography pdfplumber --break-system-packages`
  (Homebrew-Python vaatii tuon lipun; `python3 -m pip` takaa ettei paketti
  eksy toisen Python-asennuksen hyllyyn)
- **Windows**: `py -m pip install pyjwt cryptography pdfplumber`

**Käyttöjärjestelmät.** Putki toimii macOS:llä, Windowsissa ja Linuxissa —
se on pelkkää Pythonin standardikirjastoa, eikä kutsu käyttöjärjestelmän
komentoja. Tässä ohjeessa komennot on kirjoitettu muodossa `python3 …`;
**Windowsissa käytä sen sijaan `py …`** (esim. `py koodi/kirjanpito.py aja`).
Polut kirjoitetaan kauttaviivalla myös Windowsissa.

**Kansiorakenne.** Juuressa on vain käynnistimet ja neljä kansiota:
`koodi/` (ohjelma), `asetukset/` (config, säännöt, budjetti, pankkitunnukset),
`data/` (kirjanpito ja varmuuskopiot), `inbox/` (tänne tiliotteet) sekä
`raportit/` (syntyy ajossa). Päivitys korvaa vain `koodi/`-kansion, joten
sillä ei voi vahingossa hävittää mitään omaasi. Komennot ajetaan juuresta
muodossa `python3 koodi/kirjanpito.py …`.

**Et tarvitse komentoriviä lainkaan**, jos et halua: kaksoisklikkaa
`Aloita.command` (macOS) tai `Aloita.bat` (Windows) — se lukee inboxin ja avaa
raportin selaimeen. `Pankkihaku.command` / `Pankkihaku.bat` tekee saman, mutta
noutaa tapahtumat ensin suoraan pankeista (ks. oma lukunsa). Ensimmäinen
käynnistys luo kansiot ja mallitiedostot puolestasi. Jos latasit työkalun
ZIP-pakettina, käyttöjärjestelmä estää käynnistimen ensimmäisellä kerralla;
`README.md` kertoo miten se sallitaan kerralla kuntoon. Lyhyt aloitusopas on
niin ikään `README.md`; tämä tiedosto on koko kartta.

## Pikastartti: vuosi taaksepäin

1. Vie verkkopankeista CSV:t **vuosi taaksepäin tästä päivästä** kansioon
   `inbox/` (jos seuraat nettovarallisuuttasi muualla, valitse alkupäiväksi
   sama päivä — silloin voit ristiintarkistaa säästösumman varallisuuden
   muutosta vasten):
   - **OP-tili**: op.fi → tili → tapahtumat → lataa/vie CSV (aikaväli valittavissa)
   - **Luottokortit (OP & S-Pankki Visa)**: korttitapahtumia ei saa CSV:nä,
     joten historia tuodaan kuukausilaskujen PDF:istä muuntimella
     (jatkuvaan käyttöön kortitkin saa automaattihaulla, ks. oma lukunsa):
     `python3 koodi/laskusta_csv.py laskut/*.pdf` → tapahtumat ilmestyvät
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
   - **Yritystili, esim. Holvi** (valinnainen, vain jos sinulla on sellainen):
     henkilökohtaiseen budjettiin riittää yleensä se, mitä yrityksestä tulee
     *ulos sinulle* — ja se näkyy jo henkilökohtaisella tilillä saapuvana
     (palkka/osinko). Yritystilin voi siis jättää kokonaan yrityksen oman
     kirjanpidon puolelle. Tuo sen CSV vain jos haluat silmäillä myös
     yrityksen rahavirtaa.

2. Aja: `python3 koodi/kirjanpito.py aja`

3. Avaa `raportit/tarkistettavat.csv` (Sheets/Excel/editori kelpaa). Täytä
   `kategoria`-sarake tuntemattomille riveille. Jos sama kauppias toistuu,
   kirjoita `saanto`-sarakkeeseen osamerkkijono (esim. `kukkakauppa ruusu`) —
   sääntö tallentuu ja hoitaa jatkossa kaikki vastaavat rivit, myös vanhat.
   **Ensimmäinen kierros on työläin** (ehkä 30–60 min vuoden datalle); sen
   jälkeen säännöt kattavat tyypillisesti ~90 % riveistä.

4. Aja: `python3 koodi/kirjanpito.py opi` — ja avaa `raportit/raportti.html`.

5. Kun täysiä kuukausia on kertynyt: `python3 koodi/kirjanpito.py budjetti-ehdotus`
   ehdottaa raamit toteuman mediaanista. Kopioi/muokkaa haluamasi rivit
   tiedostoon `asetukset/budjetti.csv`, niin raportti alkaa näyttää toteuma vs. raami.

## Rituaali jatkossa (~15–30 min, milloin huvittaa)

1. Vie tuoreet otteet `inbox/`-kansioon — tai jos automaattinen pankkihaku on
   käytössä, pelkkä `python3 koodi/kirjanpito.py hae` (tai kaksoisklikkaus
   `Pankkihaku`-käynnistimestä, joka tekee kohdat 1–2 kerralla). Päällekkäisyys
   ei haittaa — hae mieluummin liikaa kuin liian vähän.
2. `python3 koodi/kirjanpito.py aja`
3. Täytä tarkistettavat → `python3 koodi/kirjanpito.py opi`
4. Katso `raportti.html`. Halutessasi liitä `raportit/yhteenveto_kk.csv`
   taulukkolaskentaan uudelle välilehdelle (suomalainen puolipiste+pilkku-
   muoto, liimautuu suoraan).

## Automaattinen pankkihaku — tapahtumat ilman CSV-vientejä

CSV-vientien sijaan tapahtumat voi noutaa suoraan pankeista PSD2-rajapinnan
kautta. Välissä on Enable Banking, suomalainen Finanssivalvonnan valvoma
palvelu, jonka kautta pankit luovuttavat tilitietosi. Teet sinne oman
kehittäjätunnuksen — silloin tilitietosi kulkevat *sinun* sovelluksesi kautta
suoraan koneellesi eikä välissä ole muita palveluita eikä kuukausimaksuja.

Omien tilien katselu on maksutonta: tuotantosovellus aktivoidaan
"rajoitettuna" (restricted) liittämällä siihen omat tilisi, ja vain ne tilit
ovat sen kautta luettavissa. Vaihtoehto on ostaa sama valmiina palveluna
(esim. [Syncbank](https://syncbank.app), kuukausi- tai vuosimaksu) — silloin
et tarvitse tätä lukua lainkaan, mutta tilitietosi kulkevat sen palvelun
kautta.

**Kaikki alla oleva on automatisoitu yhteen komentoon.** Velho asentaa
puuttuvat kirjastot, etsii avaintiedoston Lataukset-kansiosta, lukee
sovelluksen tunnuksen tiedostonimestä, avaa oikeat sivut selaimeen, nappaa
pankista palaavan tunnistautumiskoodin ja kirjoittaa asetukset puolestasi.
Sinä teet vain sen, mitä kukaan muu ei voi tehdä puolestasi: kirjaudut
pankkiisi.

```
python3 koodi/kirjanpito.py pankkihaku
```

Tai ilman komentoriviä: kaksoisklikkaa **`Pankkihaku.command`** (macOS) tai
**`Pankkihaku.bat`** (Windows). Sama käynnistin hoitaa jatkossa koko
rituaalin: nouto → luokittelu → raportti auki.

### Rautalankaversio: mitä ruudulla tapahtuu ja mitä sinä teet

**Vaihe 1 — Enable Banking -tunnus ja sovellus (~5 min, kerran)**

Velho avaa selaimeen osoitteen `https://enablebanking.com/sign-in/`.

1. Anna sähköpostiosoitteesi. Saat sähköpostiin kirjautumislinkin —
   salasanaa ei ole. Klikkaa linkkiä.
2. Valitse ylhäältä **API applications** ja vieritä alas kohtaan
   **Add a new application**.
3. **Environment: Production.** (Sandbox on kehittäjien leikkikenttä,
   siinä ei ole sinun rahojasi.)
4. Avaimen luonti: jätä **ensimmäinen** vaihtoehto valituksi
   (*Generate in the browser … and export private key*).
5. **Application name:** `Rahaputki`
6. **Allowed redirect URLs:** kopioi tämä rivi:

   ```
   https://enablebanking.com/auth_redirect
   ```

   Tähän osoitteeseen pankki palauttaa sinut tunnistautumisen jälkeen.
   Enable Banking hyväksyy vain `https`-osoitteita (`http://localhost/…`
   torjutaan viestillä *"uses unsupported scheme"*), joten paluukoodi
   kopioidaan kerran per pankki — ks. vaihe 3.
7. Muut kentät ovat vapaaehtoisia, mutta kannattaa täyttää. Valmiit arvot:

   | Kenttä | Arvo |
   |---|---|
   | Application description | `Rahaputki - personal spending tracker running on the user's own computer` |
   | Email for data protection matters | **oma sähköpostiosoitteesi** — sovellus on sinun, ei kenenkään muun |
   | Privacy URL of the application | `https://github.com/vsalmens/rahaputki/blob/main/koodi/ehdot/tietosuoja.md` |
   | Terms URL of the application | `https://github.com/vsalmens/rahaputki/blob/main/koodi/ehdot/kayttoehdot.md` |

   Tietosuojaseloste ja käyttöehdot kuvaavat sitä, mikä tekee Rahaputkesta
   poikkeuksellisen: ohjelmalla ei ole palvelinta, eikä sen tekijä näe
   tilitietojasi. Voit halutessasi osoittaa kentät omaan kopioosi.

8. Klikkaa **Register**.
9. Selain lataa tiedoston, jonka nimi on pitkä tunnus ja pääte `.pem`.
   **Tämä on sovelluksesi salainen avain** — se on lukupääsy tileihisi.
   Älä avaa sitä äläkä lähetä sitä kenellekään.

Palaa Rahaputken ikkunaan ja paina Enter. Velho etsii `.pem`-tiedoston
Lataukset- ja Työpöytä-kansiosta ja lukee sovelluksesi tunnuksen suoraan
tiedostonimestä (Enable Banking nimeää avaimen sillä). Tunnukset kirjoitetaan
tiedostoon `asetukset/pankkihaku.env`.

**Minne avain menee.** Oletuksena kansioon `asetukset/`, muiden asetustesi
viereen: silloin kaikki on yhdessä paikassa ja seuraa mukana, jos siirrät tai
nimeät kansion uudelleen (polku tallennetaan suhteellisena, joten se ei mene
rikki). Avain on kuitenkin lukupääsy tileihisi, joten **jos Rahaputken kansio
on pilvitallennuksessa** (Google Drive, iCloud, OneDrive, Dropbox), velho
huomaa sen ja sijoittaa avaimen sen sijaan hakemistoon `~/.rahaputki/`.
Silloin avain on olemassa vain sillä koneella — se on tarkoituskin, ja
toiselle koneelle tarvitset oman kopion samasta tiedostosta.

**Vaihe 2 — omien tilien liittäminen sovellukseen (~5 min, kerran)**

Velho tarkistaa yhteyden ja kertoo, onko sovellus jo aktiivinen. Jos ei,
se avaa selaimeen sovelluslistan:

1. Klikkaa sovelluksesi kohdalta **Activate by linking accounts**
   (tai **Link accounts**).
2. Valitse pankki ja tunnistaudu pankkitunnuksillasi.
3. **Toista jokaiselle tilille ja kortille, jonka haluat mukaan** — myös
   jokaiselle pankille erikseen.

Tämä on koko käyttöönoton tärkein kohta. Liittämätöntä tiliä ei saa mukaan
myöhemminkään: rajapinta palauttaa siitä yksinkertaisesti tyhjän listan,
ilman virheilmoitusta. Jos tilien listaus jää myöhemmin tyhjäksi, syy on
lähes aina tässä.

**Vaihe 3 — pankin valtuutus (~2 min per pankki)**

Velho listaa Suomen pankit numeroituna. Valitse numero ja tunnistaudu
avautuvassa selaimessa pankkitunnuksillasi.

Tunnistautumisen jälkeen selain palaa Enable Bankingin paluusivulle, joka
näyttää **tyhjältä lomakkeelta** — se on kunnossa, äläkä klikkaa sen
nappia. Tarvittava koodi on selaimen **osoiterivillä** (`…?code=…`).
Kopioi osoiterivi kokonaan (macOS: Cmd-L, Cmd-C — Windows: Ctrl-L, Ctrl-C),
palaa Rahaputkeen ja paina Enter: velho lukee sen leikepöydältä. Voit myös
liittää osoitteen suoraan kysymykseen. Toista jokaiselle pankille.

Tämä valtuutus on eri asia kuin vaiheen 2 liittäminen: liittäminen kertoo
*mitä tilejä sovellus saa ylipäätään koskea*, valtuutus antaa sille
*luvan hakea niiltä tapahtumia*. Valtuutus vanhenee pankista riippuen
90–180 päivän välein, ja silloin ajat velhon uudelleen.

**Vaihe 4 — tilien nimeäminen (~1 min)**

Velho näyttää löytyneet tilit ja ehdottaa jokaiselle nimeä. Enter hyväksyy
ehdotuksen. Nimi ohjaa CSV-muodon, joten vakionimet kannattaa pitää:
`OP-tili`, `S-Pankki` ja `Revolut` kirjoitetaan kunkin pankin omassa
muodossa, ja kaikki muut (luottokortit ym.) korttimuodossa, jossa tilin
nimi kulkee pääkirjaan asti. Sama nimi useammalla tilillä on sallittua —
esimerkiksi Revolutin taskut päätyvät silloin yhteen tiedostoon.

Jos pääkirjassa on jo rivejä samalle tilinimelle, velho asettaa noudon
alkupäiväksi viimeisen tuodun päivän. **Katkopäiväsääntö:** alkupäivä
asetetaan viimeisen muulla reitillä tuodun päivän *päälle*, ei sen
jälkeiselle päivälle — limitys on samalla lähteellä ilmaista (dedupe hoitaa
sen), mutta tunninkin aukko on äänetön reikä kirjanpidossa.

### Jatkossa

```
python3 koodi/kirjanpito.py hae     # tuoreet tapahtumat inboxiin
python3 koodi/kirjanpito.py aja     # luokittelu ja raportti
```

tai kaksoisklikkaa `Pankkihaku`-käynnistintä, joka tekee molemmat ja avaa
raportin. Nouto on idempotentti: tuplahaku ei koskaan tuota tuplarivejä,
joten hae mieluummin liikaa kuin liian vähän.

### Kun jokin menee pieleen

| Oire | Syy ja korjaus |
|---|---|
| `istunto syntyi, mutta siinä ei ole yhtään tiliä` | Tiliä ei ole liitetty sovellukseen (vaihe 2). Käy portaalissa klikkaamassa *Link accounts* juuri sille tilille. |
| `Enable Banking ei hyväksynyt tunnuksia (401)` | Avaintiedosto ja sovelluksen tunnus eivät ole samasta sovelluksesta. Aja `pankkihaku --uusi-sovellus` ja valitse oikea `.pem`. |
| `EB hylkäsi valtuutuspyynnön (400)` | Paluuosoite ei ole sovelluksen *Allowed redirect URLs* -listalla. Lisää se portaalissa täsmälleen samassa muodossa. |
| Paluusivu näyttää tyhjältä lomakkeelta | Näin sen kuuluukin näyttää: se on Enable Bankingin testisivu. Koodi on selaimen osoiterivillä, ei sivulla. |
| `tuo ei näytä valtuutuskoodilta` | Leikepöydällä oli jotain muuta. Kopioi selaimen osoiterivi kokonaan (Cmd-L / Ctrl-L, sitten Cmd-C / Ctrl-C). |
| `429` noudossa | Pankin kiintiö täynnä (tyypillisesti ~4 noutoa/vrk/tili ilman läsnäoloasi). Yritä huomenna. |
| `422` noudossa | Yli 90 päivän historiaa pyydetään ilman tuoretta tunnistautumista. `--paivia` pienemmäksi (oletus 89). |
| Tapahtumat loppuvat tiettyyn päivään | Suostumus on erääntynyt. Aja `pankkihaku` uudelleen ja valtuuta pankki uudestaan. |

Historiaa saa rajapinnasta noin 90 päivää taaksepäin. Sitä vanhempi
kirjanpito rakennetaan CSV-vienneillä ja korttilaskujen PDF-muuntimella,
kertaalleen — reitit deduplikoituvat keskenään.

### Asetukset käsin

Velho kirjoittaa nämä puolestasi, mutta ne ovat tavallista tekstiä ja
muokattavissa:

- `asetukset/pankkihaku.env`: `EB_APP_ID=…` ja `EB_KEY_PATH=…`
  (**ei jaeta, ei versioida**)
- `asetukset/config.json` → `pankkihaku`: `palvelu`, `redirect_url`, ja
  `tilit`-lista muotoa
  `{"tili": "OP-tili", "account_id": "<uid>", "alkaen": "YYYY-MM-DD"}`

Vanhat komennot toimivat yhä: `hae --yhdista PANKKI` valtuuttaa yhden pankin,
`hae --istunto SESSION_ID` listaa olemassa olevan istunnon tilit uid:einesi,
`hae --raaka` tallentaa pankin täydet vastaukset diagnoosia varten.

## Muokkaus suoraan raportista

Kaksi tapaa, sama näkymä:

1. **`python3 koodi/kirjanpito.py selaa`** käynnistää paikallisen palvelimen ja avaa
   raportin selaimeen. Jokaisen tapahtuman rivillä on kategoriavalikko ja
   tarkenne-kenttä — muutos **tallentuu pääkirjaan heti**. Rivin
   "sääntö"-linkki esitäyttää sääntölomakkeen (malli → kategoria:tarkenne);
   sääntö tallentuu asetukset/saannot.csv:hen ja luokittelee samalla avoimet rivit.
   Valikon "+ uusi kategoria…" lisää kategorian asetukset/config.json:iin lennossa.
   Taulukot ja käyrät päivittyvät kun lataat sivun uudelleen. Ctrl-C sammuttaa.
2. **Pelkkä raportti.html avattuna** (ilman palvelinta): samat muokkaukset
   kerätään muistiin ja alapalkin nappi lataa ne muutokset.csv-tiedostona.
   `python3 koodi/kirjanpito.py opi` etsii muutokset*.csv:t automaattisesti myös
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
| `asetukset/saannot.csv` | kauppias → kategoria -säännöt (syntyy ensikäynnistyksessä mallista, karttuu käytössä) |
| `koodi/` | **ohjelma** — päivitys korvaa tämän kansion kokonaan, muu jää koskematta |
| `koodi/laskusta_csv.py` | korttilaskujen PDF → CSV -muunnin (`--nayta` näyttää rivien tulkinnan) |
| `koodi/ehdot/` | tietosuojaseloste ja käyttöehdot — näihin osoitetaan Enable Bankingin lomakkeen URL-kentät |
| `Aloita.command` / `Aloita.bat` | kaksoisklikattava käynnistin (macOS / Windows) — tynkä, joka käynnistää `koodi/`-kansion logiikan |
| `Pankkihaku.command` / `Pankkihaku.bat` | sama, mutta noutaa tapahtumat ensin pankeista; ensimmäisellä kerralla ohjattu käyttöönotto |
| `asetukset/config.json` | lähteiden sarakekartat, kategoriat, omat IBANit |
| `koodi/config.esimerkki.json`, `koodi/saannot.esimerkki.csv` | riisutut aloituspohjat, joista ensikäynnistys tekee omasi juureen |
| `asetukset/budjetti.csv` | kk-raamit (täytetään vasta kun toteumaa on) |
| `raportit/raportti.html` | kuukausigraafi + budjettivertailu + matriisi |
| `raportit/yhteenveto_kk.csv` | sama matriisi Sheets-liitosta varten |
| `raportit/yhteistalous_erittely.html` | tulostettava kotitalouserittely (selaimesta PDF) |
| `data/yhteistalous.json` | yhteistalouden tila: tasauspäivä (mihin asti yhteiskulut on huomioitu), kk-vakiot, läsnäolot, kirjaukset — raportin osio ylläpitää tätä puolestasi |
| `asetukset/pankkihaku.env` | pankkihaun tunnukset — **ei jaeta, ei versioida** |
| `asetukset/*.pem` | pankkihaun yksityisavain (pilvisynkatussa kansiossa sen sijaan `~/.rahaputki/`) — **ei jaeta, ei versioida** |

## Kustomointi

- **Kategoriat**: `asetukset/config.json` → `kategoriat`. Tyypit: `meno`, `tulo`,
  `pois` (siirrot/sijoitukset — eivät näy luvuissa). Lisää, poista, nimeä
  vapaasti; `opi` validoi että käytät olemassa olevia nimiä.
- **Säännöt**: `asetukset/saannot.csv`, järjestys ratkaisee (ensimmäinen osuma voittaa).
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
  niputtaa oletuskategoriaan: `python3 koodi/kirjanpito.py opi --oletus Henkilömaksut`.
  Aja tämä vasta viimeisenä — se vie KAIKKI jäljellä olevat, myös ne jotka
  säännöt jättivät tahallaan listalle (esim. yli 50 € henkilömaksut).
- **Omat IBANit** `asetukset/config.json`:iin → siirrot omille tileille tunnistetaan
  automaattisesti Siirto-kategoriaan.
- **Alkupäivä**: `asetukset/config.json` → `alkaen` (muotoa `2025-07-01`) jättää sitä
  vanhemmat rivit tuomatta, vaikka ne olisivat tiedostossa — kätevä, jos et
  halua ottaa mukaan koko historiaa. Tuonti kertoo aina montako riviä rajaus
  pudotti. Tyhjä arvo (oletus) tarkoittaa, ettei mitään rajata pois.
- **Uusi pankki / muuttunut CSV-muoto**: aja
  `python3 koodi/kirjanpito.py kurkista tiedosto.csv` — se näyttää enkoodauksen,
  erottimen ja otsikot. Lisää/korjaa lähde `asetukset/config.json`:iin niillä
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
  kenelläkään. Valitse kategoria oman käytäntösi mukaan `asetukset/saannot.csv`:ssä.
- **Sijoitukset ja siirrot** eivät kuulu kulutuslukuihin (muuten "menot"
  pomppaa aina kun siirrät rahaa rahastoon). Ne kuuluvat varallisuuden
  seurantaan, eivät kulutusseurantaan.
- **TARKISTA-rivit** lasketaan menoihin ja raportti varoittaa niistä — luvut
  eivät siis koskaan hiljaa valehtele alakanttiin.

## Tunnetut rajoitteet

- OP:n, S-Pankin ja Holvin CSV-sarakenimet on asetettu parhaan tiedon mukaan
  (alkuvuosi 2026); jos vienti ei tunnistu, `kurkista` + yksi rivi
  asetukset/config.json:iin korjaa asian. Revolutin muoto on vakain.
- Korttilaskujen PDF-pohjat vaihtelevat pankeittain ja vuosittain; muuntimen
  rivikuvio on paras arvaus. `--nayta` paljastaa heti, jos jokin rivityyppi
  jää poimimatta — tulosteen (summat sotkettuina) perusteella kuvio säätyy
  yhdellä regex-muutoksella. Skannattuja (kuvapohjaisia) laskuja muunnin ei
  lue ilman OCR:ää.
