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

5. Kun täysiä kuukausia on kertynyt, paina raportin **Alusta budjetti**
   -nappia. Rahaputki ehdottaa raamit viimeisten täysien kuukausien
   mediaanista ja kirjoittaa ne tiedostoon `asetukset/budjetti.csv`; sen
   jälkeen sivun yläreuna näyttää kuluvan kuukauden tilanteen palkkeina.
   Raameja voi muokata suoraan tiedostossa. (Komentoriviltä sama ehdotus
   erilliseen tiedostoon: `python3 koodi/kirjanpito.py budjetti-ehdotus`.)

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
ovat sen kautta luettavissa.

Tämä vaihe ei ole vältettävissä maksamalla. Myös maksulliset valmispalvelut
(esim. [Syncbank](https://syncbank.app)) ohjeistavat käyttäjän tekemään oman
Enable Banking -tunnuksensa ja rekisteröimään oman sovelluksensa — niissä
maksat ohjelmasta ja sen ylläpidosta, et rekisteröinnin ohittamisesta.
Rahaputkessa sama vaihe on automatisoitu velhoon.

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

Ensin tarvitset tunnuksen: velho avaa selaimeen osoitteen
`https://enablebanking.com/sign-in/`, jossa annat sähköpostiosoitteesi ja
klikkaat sähköpostiin tulevaa linkkiä. Salasanaa ei ole.

Sitten sovellus luodaan — tai otetaan käyttöön se, joka sinulla jo on.
Velho kysyy mistä lähdetään liikkeelle:

```
  1) Luo minulle uusi sovellus (nopein — avain syntyy tällä koneella)
  2) Minulla on jo sovellus ja sen .pem-avaintiedosto
  3) Luon sovelluksen itse portaalin lomakkeella
```

Velho etsii avainta vain kahdesta paikasta — tämän asennuksen `asetukset/`
ensin, sitten `~/.rahaputki/` — eikä kahlaa Lataukset-kansiota tai työpöytää
läpi. Muualla olevan avaimen saat käyttöön raahaamalla tiedoston
terminaali-ikkunaan. Tämä on se reitti, jota tarvitset esimerkiksi silloin,
kun otat Rahaputken käyttöön toisella koneella tai uudessa kansiossa: samaa
sovellusta voi käyttää monesta paikasta, eikä avainta silloin siirretä
paikaltaan — se voi olla toisenkin asennuksen käytössä.

**Kohta 2 on oletus vain, jos avain on tämän asennuksen omassa
`asetukset/`-kansiossa.** `~/.rahaputki/` on koneen kaikkien asennusten
yhteinen, joten sieltä löytyvä avain voi olla toisen asennuksen — ja toisen
Enable Banking -tunnuksen — sovellus. Sellainen näkyy listalla merkinnällä
*koneen yhteinen kansio*, se pitää valita itse, eikä sitä oteta käyttöön
ilman erillistä vahvistusta. Ennen kuin tunnukset tallennetaan, velho kysyy
rajapinnalta (`GET /application`) mikä sovellus avaimesta oikeasti avautuu ja
näyttää sen nimen ja ympäristön — samalla varmistuu, että avain ja sovelluksen
tunnus ovat samasta sovelluksesta. Väärä sovellus paljastuisi muuten vasta
siinä, ettei portaalin tililtä löydy sitä sovellusta, jota Rahaputki käyttää,
eivätkä tilit tunnu aktivoituvan. Samalla tarkistuu paluuosoite: jos sovellus
on luotu jotain muuta ohjelmaa varten (esimerkiksi Syncbankia), pankista
palaava kertakäyttöinen koodi ohjautuisi sen palvelimelle — velho varoittaa
siitäkin.

**Environment: Production, ei koskaan Sandbox.** Automaattinen tapa (A) luo
sovelluksen suoraan tuotantoon, joten siinä ei ole mitään valittavaa.
Lomakkeella (B) ympäristö valitaan itse — ja **väärää valintaa ei voi
korjata jälkikäteen**, vaan on luotava uusi sovellus. Sandbox on kehittäjien
leikkikenttä: siellä on keksittyjä mock-pankkeja ja testitilejä, ei sinun
rahojasi. Velho tarkistaa ympäristön ja varoittaa, jos se ei ole Production.

### Tapa A: automaattinen (suositus)

Portaalin sovellussivun alalaidassa on valmis komento, jolla sovelluksen voi
luoda rajapinnan kautta. Velho pyytää kopioimaan sen:

1. Sivulla `https://enablebanking.com/cp/applications`, vieritä kohtaan
   *"You can register your applications via an API or using command line
   interface"*.
2. Klikkaa sen alla olevaa laatikkoa (sisältö alkaa sanalla `curl`), valitse
   kaikki (Cmd-A / Ctrl-A) ja kopioi.
3. Palaa Rahaputkeen ja paina Enter — velho lukee komennon leikepöydältä.

Velho kysyy vain sähköpostiosoitteen tietosuoja-asioita varten (Enable
Banking vaatii sen tuotantosovellukselta). Loput tapahtuu itsestään:
**avainpari luodaan tällä koneella**, ja rajapinnalle lähtee vain julkinen
varmenne. Nimi, paluuosoitteet, kuvaus ja ehtojen URLit täyttyvät valmiiksi,
ja sovelluksen tunnus tallentuu suoraan asetuksiin.

Paluuosoitteita pyydetään kaksi: portaalin oma sivu ja `http://localhost:8765/
callback`. Jälkimmäinen on se, joka poistaa kopioinnin kokonaan — pankki palaa
omalle koneellesi, ja Rahaputki nappaa tunnistautumiskoodin suoraan
selaimesta. Jos rajapinta ei hyväksy http-osoitetta, se pudotetaan pois ja
koodi kopioidaan osoiteriviltä kuten ennenkin; valtuutus ei kaadu siihen.

Tämä on myös turvallisin tapa: lomakereitillä yksityisavain syntyy selaimessa
ja päätyy latauskansioon, tässä se ei käy missään. Komento sisältää
kertakäyttöisen, **tunnin voimassa olevan** tunnuksen — käsittele sitä kuin
salasanaa. Jos se ehtii vanheta, lataa portaalin sivu uudelleen ja kopioi
komento uudestaan.

### Tapa B: lomake

Jos automaattinen tapa ei jostain syystä toimi, sovelluksen voi luoda käsin
portaalin lomakkeella:

1. Valitse ylhäältä **API applications** ja vieritä alas kohtaan
   **Add a new application**.
2. **Environment: Production.** (Sandbox on kehittäjien leikkikenttä,
   siinä ei ole sinun rahojasi.)
3. Avaimen luonti: jätä **ensimmäinen** vaihtoehto valituksi
   (*Generate in the browser … and export private key*).
4. **Application name:** `Rahaputki`
5. **Allowed redirect URLs:** kopioi tämä rivi:

   ```
   https://enablebanking.com/auth_redirect
   ```

   Tähän osoitteeseen pankki palauttaa sinut tunnistautumisen jälkeen.
   Enable Banking hyväksyy vain `https`-osoitteita (`http://localhost/…`
   torjutaan viestillä *"uses unsupported scheme"*), joten paluukoodi
   kopioidaan kerran per pankki — ks. vaihe 3.
6. Muut kentät ovat vapaaehtoisia, mutta kannattaa täyttää. Valmiit arvot:

   | Kenttä | Arvo |
   |---|---|
   | Application description | `Rahaputki - personal spending tracker running on the user's own computer` |
   | Email for data protection matters | **oma sähköpostiosoitteesi** — sovellus on sinun, ei kenenkään muun |
   | Privacy URL of the application | `https://github.com/vsalmens/rahaputki/blob/main/koodi/ehdot/tietosuoja.md` |
   | Terms URL of the application | `https://github.com/vsalmens/rahaputki/blob/main/koodi/ehdot/kayttoehdot.md` |

   Tietosuojaseloste ja käyttöehdot kuvaavat sitä, mikä tekee Rahaputkesta
   poikkeuksellisen: ohjelmalla ei ole palvelinta, eikä sen tekijä näe
   tilitietojasi. Voit halutessasi osoittaa kentät omaan kopioosi.

7. Klikkaa **Register**.
8. Selain lataa tiedoston, jonka nimi on pitkä tunnus ja pääte `.pem`.
   **Tämä on sovelluksesi salainen avain** — se on lukupääsy tileihisi.
   Älä avaa sitä äläkä lähetä sitä kenellekään.

Palaa lopuksi Rahaputken ikkunaan ja paina Enter. Velho etsii `.pem`-tiedoston
Lataukset- ja Työpöytä-kansiosta ja lukee sovelluksesi tunnuksen suoraan
tiedostonimestä (Enable Banking nimeää avaimen sillä). Tunnukset kirjoitetaan
tiedostoon `asetukset/pankkihaku.env`.

**Minne avain menee.** Jos avain on jo järkevässä paikassa (`asetukset/` tai
`~/.rahaputki/`), se jätetään sinne ja asetuksiin kirjoitetaan vain polku —
näin sama avain palvelee useaa asennusta. Latauskansiosta raahattu avain sen
sijaan siirretään pois sieltä: oletuksena kansioon `asetukset/`, muiden
asetustesi viereen: silloin kaikki on yhdessä paikassa ja seuraa mukana, jos siirrät tai
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

Osa pankeista tunnistaa vain **yritystilejä** (esim. Holvi, Finom, Finductive
— Suomen 39 pankista 11) ja osa vain henkilötilejä. Velho lukee tämän
pankilta ja merkitsee yritystilipankit listaan; jos pankki tukee molempia, se
kysyy kummasta on kyse. Väärä valinta kaatuu virheeseen `422 Wrong ASPSP
name provided`, joka ei siis kerro nimestä vaan tilityypistä.

Tunnistautumisen jälkeen selain palaa Enable Bankingin paluusivulle, joka
näyttää **tyhjältä lomakkeelta** — se on kunnossa, äläkä klikkaa sen
nappia. Tarvittava koodi on selaimen **osoiterivillä** (`…?code=…`).
Kopioi osoiterivi kokonaan (macOS: Cmd-L, Cmd-C — Windows: Ctrl-L, Ctrl-C),
palaa Rahaputkeen ja paina Enter: velho lukee sen leikepöydältä. Voit myös
liittää osoitteen suoraan kysymykseen. Toista jokaiselle pankille.

**Miksi pankki valitaan ja tunnistaudutaan toiseen kertaan?** Koska vaiheet
tekevät eri asian ja Enable Banking vaatii molemmat: vaiheen 2 liittäminen
kertoo *mitä tilejä sovellus saa ylipäätään koskea*, tämä valtuutus antaa
sille *luvan hakea niiltä tapahtumia*. Liittäminen ei valtuuta hakua eikä
valtuutus liitä tiliä. Kaksivaiheisuus koskee ilmaista, omiin tileihin
rajattua tuotantosovellusta; rajoituksen poisto (jolloin liittämistä ei
tarvita) vaatii sopimuksen ja yritystaustojen tarkistuksen Enable Bankingin
kanssa.

Jatkossa vain valtuutus uusitaan: se vanhenee pankista riippuen 90–180 päivän
välein, ja silloin ajat velhon uudelleen. Vaihetta 2 ei toisteta.

**Vaihe 4 — tilien nimeäminen (~1 min)**

Velho näyttää löytyneet tilit ja ehdottaa jokaiselle nimeä. Enter hyväksyy
ehdotuksen. Nimi ohjaa CSV-muodon, joten vakionimet kannattaa pitää: `OP-tili` ja
`S-Pankki` kirjoitetaan pankin omassa muodossa, ja kaikki muut (Revolut,
luottokortit ym.) yleisessä muodossa, jossa tilin nimi kulkee pääkirjaan
asti. Sama nimi useammalla tilillä on sallittua —
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

### Odottavat veloitukset (varaukset)

Kun maksat kortilla, pankki tekee ensin **varauksen** ja kirjaa tapahtuman
vasta myöhemmin, kun kauppias hakee rahat. Varaus ei ole vielä totuus: summa
voi tarkentua (juomaraha, polttoaine), päivä muuttuu kirjaushetkeksi, ja koko
veloitus voi raueta.

Rahaputki näyttää varaukset heti, mutta merkitsee ne sellaisiksi:

- `hae` poimii ne omaan tiedostoonsa `data/varaukset.json`
- `aja` vie ne pääkirjaan merkinnällä `varaus` (sarake `tila`), ja ne
  **lasketaan mukaan lukuihin** — niin päivän kulutus näkyy oikein heti
- raportissa rivillä on `varaus`-merkintä ja ylälaidassa lukee, montako
  odottavaa veloitusta luvuissa on mukana
- varauksia **ei kysytä luokiteltavaksi** (`tarkistettavat.csv`), koska työ
  menisi hukkaan

**Täsmäytys tapahtuu itsestään.** Jokainen `hae` kertoo, mitkä varaukset ovat
juuri sillä hetkellä voimassa, ja `aja` korvaa pääkirjan varausrivit niillä.
Siksi:

- varaus, joka **kirjautui** → varausrivi katoaa ja tilalle tulee pankin
  kirjaama rivi oikealla summalla ja päivällä
- varaus, joka **raukesi** → rivi katoaa jäljettömiin

Tämä ei nojaa siihen, että pankki antaisi tapahtumalle pysyvän tunnisteen —
varaukset korvataan aina kokonaan, joten haamurivejä ei voi jäädä. Jos `hae`
ei ole käynyt kolmeen vuorokauteen, varaukset jätetään pois kokonaan
(vanhentunutta varaustietoa ei pidetä yllä), ja ne palaavat seuraavalla
hakukerralla.

Käytännössä varauksia on vähän: pankit kirjaavat korttiostot yleensä
vuorokaudessa. Jos haluat pitää pääkirjan puhtaasti kirjatuissa tapahtumissa,
poista `data/varaukset.json` — silloin seuraava `aja` poistaa varausrivit
eikä lisää uusia.

### Kun jokin menee pieleen

| Oire | Syy ja korjaus |
|---|---|
| `istunto syntyi, mutta siinä ei ole yhtään tiliä` | Tiliä ei ole liitetty sovellukseen (vaihe 2). Käy portaalissa klikkaamassa *Link accounts* juuri sille tilille. |
| `Enable Banking ei hyväksynyt tunnuksia (401)` | Avaintiedosto ja sovelluksen tunnus eivät ole samasta sovelluksesta. Aja `pankkihaku --uusi-sovellus` ja valitse oikea `.pem`. |
| `422 Wrong ASPSP name provided` | Nimi on oikein, tilityyppi ei: pankki tunnistaa vain henkilö- tai vain yritystilejä. Aja uudelleen ja vastaa tilityyppikysymykseen toisin. |
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

- `asetukset/pankkihaku.env`: `EB_APP_ID=…` ja `EB_KEY_PATH=…`. Lisäksi
  `EB_SOVELLUS_OK=…` kertoo, minkä sovelluksen olet nimenomaan hyväksynyt
  tälle asennukselle — sitä vasten vaiheen 2 varoitukset vaimennetaan,
  jotta tietoinen valinta kysytään kerran eikä joka ajolla.
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
   Rivin alussa oleva **§-merkki** kertoo, että rivin luokitteli sääntö —
   klikkaa sitä, niin juuri se sääntö avautuu samaan lomakkeeseen
   muokattavaksi (malli, kategoria, tarkenne, summaehto). Tallennus korvaa
   vanhan säännön sen omalla paikalla listassa, joten järjestys säilyy, ja
   kertoo etukäteen montako riviä luokittuu uudelleen. "Peru muokkaus"
   palauttaa lomakkeen uuden säännön tilaan.
   Valikon "+ uusi kategoria…" lisää kategorian asetukset/config.json:iin lennossa.
   Taulukot ja käyrät päivittyvät kun lataat sivun uudelleen. Ctrl-C sammuttaa.

   **Yhdistä pankkeihin** avaa pankkiyhteyssivun (`/velho`). Se ei ole
   kysymysjono vaan **tila, jota voi muuttaa**: vasemmalla on kolme vaihetta
   (Yhdistä Enable Banking, Yhdistä pankit, Valmis), joista jokaiseen voi
   palata milloin tahansa, ja
   tehdyn valinnan voi vaihtaa. Vaiheen tila näkyy rivin alla ("yhteys
   toimii", "2 kaipaa uusintaa"). Vaihe 2 näyttää aina jo yhdistetyt pankit ja
   kunkin valtuutuksen voimassaolon, ja rivin *Uusi valtuutus* vie suoraan sen
   pankin tunnistautumiseen.

   Terminaalivelho (`pankkihaku`) on ennallaan. Sivu ja terminaali käyttävät
   samoja funktioita (`eb_pankkilista`, `eb_aloita_valtuutus`,
   `eb_viimeistele_valtuutus`, `tallenna_tilit_nimilla`), jotka eivät kysy
   eivätkä tulosta mitään — kysyminen kuuluu käyttöliittymälle, tekeminen ei.

   Hakukentän vieressä on kolme toimintoa:

   - **Hae pankkitapahtumat** noutaa tapahtumat pankista *ja* lukee ne
     pääkirjaan (`hae` + `aja` yhtenä työnä — nouto ilman lukemista jättäisi
     tehtäväksi toisen napin painamisen ilman uutta päätettävää). Nappi on
     pois käytöstä, jos pankkiyhteyttä ei ole vielä kytketty.
   - **Lue tiliotteet** lukee vain `inbox/`-kansion tiedostot pääkirjaan
     (`aja`). Tätä tarvitset, jos tuot tiliotteita CSV:nä tai korttilaskujen
     PDF-muuntimella.
   - **Yhdistä pankkeihin** avaa ohjatun käyttöönoton.

   Tuloste näkyy sivulla rivi riviltä sitä mukaa kuin sitä syntyy (myös
   terminaalissa, jos sellainen on auki). Kun ajo on valmis, "Päivitä
   raportti" lataa sivun uusiksi. Komento ajetaan samassa prosessissa kuin
   selaa, joten se käyttää jo otettua pääkirjalukkoa eikä voi törmätä siihen —
   toisin kuin erikseen käynnistetty komento.
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

**Kaudet ja laskut.** Kun lasku on lähetetty, sulje kausi: anna sen alku- ja
loppupäivä ja paina *sulje kausi ja laskuta*. Kauden summat jäädytetään
saataviksi, ja jäsenten myöhemmin maksamat suoritukset kuitataan niitä
vastaan vanhimmasta laskusta alkaen — vasta yli menevä osa vaikuttaa uuteen
kauteen. Ilman sulkemista lähetetyn laskun maksu näyttäisi ennakkomaksulta
kaudella, jolla maksajalle ei ole vielä ehtinyt kertyä kuluja.

Jos samalle kaudelle ilmestyy pääkirjaan veloitus vasta laskun lähdettyä,
se siirtyy seuraavalle laskulle merkinnällä *↩ myöhässä kaudelta* — takautuvasti
ei enää laskuteta, mutta kulu ei myöskään katoa. Jokaisesta suljetusta
kaudesta syntyy oma tulostettava lasku (`raportit/yhteistalous_lasku_*.html`),
ja avoimet saatavat kulkevat mukana seuraavan laskun toimenpiteissä.
*Sulje ilman saatavia* on sitä varten, että rahat on jo siirretty. Väärään
päivään painettu sulkeminen perutaan napista *avaa viimeisin kausi*.

## Tiedostot

| Tiedosto | Mikä |
|---|---|
| `inbox/` | tänne pankkien CSV:t; käsitellyt siirtyvät `inbox/arkisto/` |
| `data/tapahtumat.csv` | pääkirja — koko totuus, pelkkää tekstiä, versioi/varmuuskopioi vapaasti (sarake `tila`: tyhjä = pankin kirjaama, `varaus` = odottava) |
| `data/varmuuskopiot/` | pääkirjan, sääntöjen ja yhteistalouden aiemmat versiot. Palautus = kopioi tiedosto takaisin oikealle nimelle. Säilytys: 10 tuoreinta sekä kunkin päivän (7), viikon (8) ja kuukauden (12) viimeisin — eilinen versio on siis tallessa, vaikka tänään olisi ajettu kymmenen kertaa |
| `asetukset/saannot.csv` | kauppias → kategoria -säännöt (syntyy ensikäynnistyksessä mallista, karttuu käytössä) |
| `koodi/` | **ohjelma** — päivitys korvaa tämän kansion kokonaan, muu jää koskematta |
| `koodi/laskusta_csv.py` | korttilaskujen PDF → CSV -muunnin (`--nayta` näyttää rivien tulkinnan) |
| `koodi/ehdot/` | tietosuojaseloste ja käyttöehdot — näihin osoitetaan Enable Bankingin lomakkeen URL-kentät |
| `Aloita.command` / `Aloita.bat` | kaksoisklikattava käynnistin (macOS / Windows) — tynkä, joka käynnistää `koodi/`-kansion logiikan |
| `Pankkihaku.command` / `Pankkihaku.bat` | sama, mutta noutaa tapahtumat ensin pankeista; ensimmäisellä kerralla ohjattu käyttöönotto |
| `asetukset/config.json` | lähteiden sarakekartat, kategoriat, omat IBANit |
| `koodi/config.esimerkki.json`, `koodi/saannot.esimerkki.csv` | riisutut aloituspohjat, joista ensikäynnistys tekee omasi juureen |
| `asetukset/budjetti.csv` | kk-raamit ja kertyvät erät (täytetään vasta kun toteumaa on) |
| `raportit/raportti.html` | kuukausigraafi + budjettivertailu + matriisi |
| `raportit/yhteenveto_kk.csv` | sama matriisi Sheets-liitosta varten |
| `raportit/yhteistalous_erittely.html` | tulostettava kotitalouserittely avoimelta kaudelta (selaimesta PDF) |
| `raportit/yhteistalous_lasku_<pvm>.html` | suljetun kauden lasku sellaisena kuin se lähetettiin |
| `koneen-asetukset.txt` | koneen omat asetukset (mm. `tietokansio`), koodin juuressa; syntyy vain jos jotain on asetettavaa (ks. Kustomointi) |
| `data/.lukko.<kone>.json` | ajonaikainen lukko, vain jaetussa tilassa (`"lukitus": "jaettu"`); katoaa itsestään |
| `data/pankkitila.json` | pankkiyhteyksien tila: saldo, milloin tililtä viimeksi saatiin tapahtumia ja mihin asti valtuutus on voimassa |
| `~/.rahaputki/tietokansio-<tiiviste>.txt` | asennuskohtainen muisti viimeksi toimineesta tietokansiosta; palauttaa osoittimen, jos koko kansio korvataan päivityksessä |
| `data/pankkiloki.csv` | rajapintakutsujen loki: aika, kohde, tulos, kesto. Ei tunnuksia eikä tilinumeroita; tilin tunnus on tiivisteenä |
| `data/varaukset.json` | odottavat korttivaraukset — `hae` kirjoittaa, `aja` täsmäyttää; poistettavissa milloin vain |
| `data/yhteistalous.json` | yhteistalouden tila: suljetut kaudet saatavineen, kk-vakiot, läsnäolot, kirjaukset — raportin osio ylläpitää tätä puolestasi |
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
- **Kertyvät erät**: kaikkea ei voi budjetoida kuukausittain. Vuosivakuutus,
  kesäloma tai renkaiden vaihto on kertasumma, joka romahduttaa yhden
  kuukauden ja jättää yksitoista muuta näyttämään paremmalta kuin ne ovat.
  Lisää tällainen erä `asetukset/budjetti.csv`:hen omalle rivilleen: sarakkeet
  ovat `kategoria;kk_raami;tavoite;erapaiva;kertynyt`, ja rivi tulkitaan
  kertyväksi eräksi silloin kun sillä on tavoite. Kuukausiraami jätetään
  tyhjäksi:

  ```
  kategoria;kk_raami;tavoite;erapaiva;kertynyt
  Päivittäistavarat;600;;;
  Autovakuutus;;969;2027-04-01;240
  Kesäloma;;2500;2027-06-15;300
  ```

  Raportti näyttää näistä oman taulukkonsa: paljonko puuttuu, montako
  kuukautta eräpäivään ja **paljonko kuussa pitää panna sivuun**, jotta summa
  on kasassa ajoissa. Eräpäivän voi jättää tyhjäksi — silloin kertyy ilman
  määräaikaa. Raha ei liiku minnekään eikä ohjelma siirrä mitään: `kertynyt`
  on omissa käsissäsi, ja jos pidät summan erillisellä tilillä tai
  pocketissa, kirjaa sen saldo siihen. Nämä eivät ole samaa kuin *varaukset*,
  jotka ovat pankin odottavia korttiveloituksia — kertyvä erä on tulevaa
  menoa varten, varaus jo tapahtunutta ostosta.
- **Koodi ja data eri paikkoihin** (`RAHAPUTKI_DATA`): oletuksena kaikki on
  yhdessä kansiossa, ja niin sen kuuluukin olla useimmille. Jos haluat pitää
  ohjelman git-checkouttina koneen omalla levyllä ja kirjanpidon jaetussa
  pilvikansiossa, kerro tietokansio koneen omissa asetuksissa:

  ```
  # koodin juureen, kerran per kone
  printf 'tietokansio = %s\n' "$HOME/…/Rahaputki" > koneen-asetukset.txt
  ```

  Polku kirjoitetaan kokonaisena tai `~/`-alkuisena. Ilman kumpaakaan se on
  suhteellinen ja luetaan **koodin juuresta**, jolloin kirjanpito osoittaisi
  ohjelmakansion sisään — tyypillinen erehdys, ja siksi virheilmoitus kertoo
  sen erikseen. Lainausmerkit, kenoviivoitetut välilyönnit ja `$HOME`
  siivotaan pois, joten leikepöydältä liimattu polku kelpaa sellaisenaan.

  Jako menee sen mukaan, kuka tiedoston omistaa ja kuka sitä tarvitsee:

  | Jaetussa kansiossa | Koneen omassa kansiossa |
  |---|---|
  | `data/` — pääkirja, varmuuskopiot, yhteistalous, varaukset, lukot | `inbox/` — tiliotteet ladataan sillä koneella jolla ollaan |
  | `asetukset/` — config, säännöt, budjetti | `pankkihaku.env` — osoittaa koneen omaan avaimeen |
  | `raportit/` — myös puhelimesta luettavissa Drive-apilla | `koneen-asetukset.txt` — koneen omat asetukset, mm. osoitin jaettuun kansioon |

  Yksityisavain (`.pem`) ei ole kummassakaan vaan kotihakemistossa
  `~/.rahaputki/`, jonne ohjelma sen itse sijoittaa, kun huomaa
  kirjanpitokansion olevan pilvisynkassa.

  Ohjelma päivittyy `git pull`illa. Suhteellinen polku tulkitaan koodin
  juuresta. Ilman asetusta mikään ei muutu: juuret ovat sama kansio.

  Osoitin on koodin juuressa eikä `asetukset/`-kansiossa yksinkertaisesta
  syystä: `asetukset/` on itse tietokansion sisällä, joten sieltä sitä ei voisi
  lukea tietämättä jo vastausta. Tiedosto on konekohtainen ja gitignoroitu.

  `koneen-asetukset.txt` on koneen omien asetusten tiedosto, ei pelkkä
  osoitin: muoto on `avain = arvo`, `#` aloittaa kommenttirivin, ja
  tuntemattomat avaimet säilyvät. Toistaiseksi tunnettuja avaimia on yksi,
  `tietokansio` — kansio, jonka **sisällä** `asetukset/`, `data/` ja
  `raportit/` ovat. Oletus on tiedoston oma kansio (`.`), eli kaikki yhdessä
  paikassa. Nimi on pari jaetulle `asetukset/`-kansiolle: siellä ovat
  asetukset jotka seuraavat kirjanpitoa, tässä tiedostossa ne jotka jäävät
  koneelle.

  Tiedoston lopussa on kommenttirivi `# --- Rahaputki v125 ---`. Se on
  ohjelman oma leima siitä, millä versiolla tiedosto on kirjoitettu, ja siksi
  se on kommentissa eikä avaimena: se ei ole asetus, eikä käsin muutettuna
  tee mitään. Kun versio vaihtuu, ohjelma lukee vanhan tiedoston ja
  kirjoittaa sen uudelleen käynnistyksen yhteydessä — samalla tavalla kuin
  asetukset ja pääkirja päivittyvät muodosta toiseen. Erillistä
  muotonumeroa ei ole, koska ohjelman versio on jo olemassa eikä kahden
  numeron tarvitse ajautua eri linjoille.

  Aiemmat nimet (`paikalliset.txt`, ja sitä ennen `datakansio.txt`, jossa oli
  pelkkä polku ilman avaimia) luetaan yhä ja kirjoitetaan uudella nimellä
  ensimmäisellä ajolla; vanha tiedosto poistetaan vasta kun uusi on
  kirjoitettu. Sama koskee avaimen vanhaa nimeä `datakansio`. Uudelleenkirjoitus rakentaa myös tiedoston sisällä olevan
  ohjeen, joten omat kommentit eivät säily version vaihtuessa — asetukset
  säilyvät.

  Saman voi kertoa myös ympäristömuuttujalla `RAHAPUTKI_DATA`, joka voittaa
  tiedoston — kätevä kertakokeiluun. Pysyvään käyttöön tiedosto on parempi,
  koska **kaksoisklikattu käynnistin ei lue `~/.zshrc`:tä** eikä siis näkisi
  muuttujaa lainkaan; tiedoston se lukee.

  Jos osoitettua kansiota ei löydy — pilvikansio ei ole latautunut, levy ei ole
  kiinni, polussa on kirjoitusvirhe — ohjelma pysähtyy virheilmoitukseen eikä
  aloita tyhjää kirjanpitoa väärään paikkaan.

  Pilvikansion sisään ei kannata laittaa `.git`-hakemistoa: synkka kopioi sen
  tiedosto kerrallaan ja voi rikkoa indeksin kesken commitin.

  Kaksi asiaa jää tässä mallissa konekohtaiseksi eikä siirry pilven kautta.
  Yksityisavain: ohjelma huomaa tietokansion olevan synkassa ja sijoittaa
  avaimen `~/.rahaputki/`-kansioon (ks. Pankkihaku). Pankkihaun tunnukset:
  `pankkihaku.env` luetaan silloin ensisijaisesti koodin juuresta, koska se
  osoittaa juuri siihen avaimeen. Jos tiedosto on jo `asetukset/`-kansiossa,
  sitä luetaan yhä — mutta erotetussa asennuksessa se kannattaa siirtää
  koodikansioon kummallakin koneella erikseen.
- **Kaksi konetta samaan kansioon**: `asetukset/config.json` →
  `"lukitus": "jaettu"`. Oletuksena Rahaputki varmistaa vain, ettei sama kone
  aja putkea kahdesti yhtä aikaa. Jaettu tila lisää siihen lukkotiedoston
  (`data/.lukko.<kone>.json`), jonka toinen kone näkee pilvisynkan kautta:
  päällekkäinen ajo kertoo kuka on liikkeellä ja millä komennolla sen sijaan,
  että kaksi versiota pääkirjasta törmäisivät äänettömästi. Yli 30 minuutin
  ikäistä lukkoa ei ohiteta puolestasi: ohjelma kertoo kenen lukko on ja kysyy
  luvan, oletuksena ei. Luvan saatuaan se poistaa roikkumaan jääneen
  lukkotiedoston, joten kysymys ei toistu joka ajolla. Kysymyksen ohi pääsee
  suoraan lipulla: `python3 koodi/kirjanpito.py --pakota aja`. Lukko vapautuu myös
  silloin kun ohjelma lopetetaan signaalilla (SIGTERM, SIGHUP) — esimerkiksi
  koneen sammutus tai `kill` — ei vain Ctrl-C:llä.

  Ohitus näkyy myös toiseen suuntaan: jos oma lukko katoaa kesken ajon (toinen
  kone otti sen, tai synkka vei tiedoston alta), kirjoitus pysähtyy ennen kuin
  se tapahtuu. Komentorivillä ohjelma kertoo syyn ja kysyy, keskeytetäänkö vai
  otetaanko lukko takaisin — oletus on keskeyttää. `selaa`-tilassa kysymystä ei
  voi esittää konsolissa, joten kirjoitus estetään ja syy näkyy selaimessa.
  Keskeytys ei riko mitään: pääkirjaan ei kirjoiteta, ja saman ajon voi toistaa
  sellaisenaan.

  Synkka ei ole hetkellinen,
  joten tämä on varoitin eikä tae — älä silti aloita ajoa toisella koneella
  ennen kuin edellinen on valmis. Lukkoon törmätessään käynnistin pysähtyy
  siihen: se ei jatka raportin avaamiseen, vaan jättää varoituksen ruudulle
  luettavaksi (paluuarvo 4 erottaa lukon muista virheistä).
- **Saldot ja täsmäytys**: `python3 koodi/kirjanpito.py hae --saldot` hakee myös
  tilien saldot ja näyttää ne raportin Pankkiyhteydet-taulukossa. Saldoa **ei
  haeta koskaan itsestään**: PSD2 velvoittaa pankin sallimaan vain neljä hakua
  vuorokaudessa tiliä kohden silloin kun et ole itse paikalla, ja saldo on oma
  pyyntönsä samasta budjetista. Täsmäytys on siis tietoinen toimitus, kuten
  YNABissa — ei taustalla jyskyttävä tarkistus. Vertailuun kelpaa vain kirjattu
  saldo (ITBD/CLBD); tähdellä merkitty sisältää myös odottavat korttivaraukset,
  joita kirjanpidossa ei vielä ole.

  **Täsmäytys** tehdään raportin Pankkiyhteydet-taulukosta: rivin
  *Täsmäytä*-nappi hakee **sen yhden tilin** saldon ja vertaa sitä
  kirjanpitoon. Vertailu ei ole absoluuttinen summa — pääkirja alkaa
  tilikohtaisesta alkupäivästä eikä tilin avaamisesta — vaan se tehdään
  *ankkurista*: hyväksytystä saldosta ja sen hetken pääkirjan summasta.

      odotettu = ankkurin saldo + (pääkirjan summa nyt − pääkirjan summa ankkurilla)

  Näin päivärajat eivät haittaa: jälkikäteen ilmestynyt vanhalla
  kirjauspäivällä varustettu tapahtuma siirtää odotusta oikein, vaikka se
  putoaisi keskelle historiaa. Ensimmäinen täsmäytys vain asettaa ankkurin.
  Jos eroa tulee myöhemmin, sen voi joko selvittää (rivi puuttuu, tuli
  kahdesti, tai putki ohitti sen) tai hyväksyä — hyväksyminen ankkuroi
  uudelleen ja jättää eron muistiin, jottei tieto selvittämättä jääneestä
  katoa. Jos saldo on tyyppiä ITAV, myös odottavat varaukset otetaan
  vertailuun mukaan, koska ne ovat mukana pankinkin luvussa.

  Jokainen rajapintakutsu kirjautuu tiedostoon `data/pankkiloki.csv`: aika,
  kohde, tulos, HTTP-koodi, kesto ja vastauksen koko. Rajan ylittyessä mukaan
  tulee pankin `Retry-After`-otsake, jos se on mukana. Näin hakurajan
  käyttäytymisen näkee jälkikäteen omasta datasta — säädös puhuu "24 tunnin
  jaksosta" muttei määrää, onko kyse liukuvasta ikkunasta vai keskiyöllä
  nollautuvasta kiintiöstä, ja pankit voivat toteuttaa sen eri tavoin. Lokiin ei
  kirjoiteta tunnuksia, pyyntöjen runkoja eikä tilinumeroita: tilin tunnus on
  tiivisteenä ja virheteksteistä siivotaan kaikki tunnukselta näyttävä.
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
