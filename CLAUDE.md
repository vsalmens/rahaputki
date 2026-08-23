# CLAUDE.md

Ohjeet Claude Codelle tässä repossa. `.github/README.md` ja `koodi/OHJE.md` kertovat
mitä ohjelma tekee ja miten sitä käytetään; tämä tiedosto kertoo sen, mitä
koodiin koskiessa pitää tietää eikä koodista näe.

Ohjelma on käytännössä yksi tiedosto, `koodi/kirjanpito.py`.
`koodi/laskusta_csv.py` on erillinen korttilaskujen PDF-muunnin.

## Rajat, joita ei ylitetä

- Koodin ja olennaisten toimintojen on toimittava sekä Mac OS X-ympäristössä, 
  että Windowsilla. Lisäksi ainakin perusraportin/selauksen tulisi toimia 
  webbiselaimella (oletuksena Chrome, iOS:illa Chrome tai Safari ).
- **`koodi/` korvataan päivityksessä kokonaan.** Päivitysohje on "vedä uusi
  `koodi`-kansio vanhan päälle", joten sinne ei saa kirjoittaa mitään
  käyttäjän omaa. Kaikki käyttäjän tila menee kansioihin `asetukset/`
  (config, säännöt, budjetti, tunnukset), `data/` (pääkirja, varmuuskopiot)
  ja `inbox/`. Mallipohjat (`config.esimerkki.json`, `saannot.esimerkki.csv`)
  ovat `koodi/`-kansiossa, ja ensikäynnistys kopioi niistä käyttäjän omat.
- **Perustoiminnot pelkällä vakiokirjastolla.** Riippuvuuksia on kaksi, ja
  molemmat ovat valinnaisia lisäosia: `pyjwt` + `cryptography` (pankkihaku)
  ja `pdfplumber` (PDF-muunnin). Ne importoidaan funktion sisällä, ei
  tiedoston alussa, jotta ilman niitä muu ohjelma toimii normaalisti.
  Uutta riippuvuutta ei lisätä ilman erikseen sovittua syytä.
- **Python 3.9.** Ei `match`-lauseita eikä `int | None` -tyyppisyntaksia
  ajossa. Kohdeyleisöllä on se Python, joka koneessa sattuu olemaan.
- **Ei absoluuttisia polkuja mihinkään.** Kaikki johdetaan `__file__`:stä
  (`KOODI`, `JUURI`, `DATA`, …). Kansion pitää olla siirrettävissä ja
  uudelleennimettävissä milloin tahansa, myös kesken kaiken.
- **Idempotenssi.** Saman tapahtuman voi tuoda montaa kertaa: päällekkäiset
  rivit ohitetaan. Tämä on koko työkalun lupaus käyttäjälle — jos muutat
  tuontia tai rivin tunnistetta (`avain`, `tee_id`), varmista se erikseen.
- **Ei komentoriviä käyttäjälle.** Kaikki toimii kaksoisklikkauksella
  (`Aloita`, `Pankkihaku`). Uusi toiminto ei saa olla vain komentorivillä
  saavutettavissa, ellei se ole nimenomaan tehty niitä varten, jotka
  komentoriviä haluavat käyttää.

## Data ja salaisuudet

Repo on julkinen, ja työkansio on samalla elävä asennus oikealla
kirjanpidolla. `.gitignore` kattaa `asetukset/`, `data/`, `inbox/`,
`raportit/`, kaikki `*.csv`- ja `*.env`- ja `*.pem`-tiedostot — mutta se
suojaa vain siltä mitä osaa odottaa. Älä kirjoita testiaineistoa, debug-
tulostetta tai näytekuvia `koodi/`-kansioon, äläkä liitä oikeita tapahtumia
committiviesteihin tai koodin kommentteihin. Aja kehitysversio erillisessä
hiekkalaatikossa, ei oman kirjanpidon päällä (ks. Testaus).

## Tyyli

- **Kaikki suomeksi**: käyttöliittymä, virheilmoitukset, ohjeet, koodin
  kommentit ja docstringit, muuttujien ja funktioiden nimet. Ääkköset
  kuuluvat myös kommentteihin.
- **Committiviesti** on suomea, otsikko kertoo vaikutuksen eikä mekaniikkaa
  ("Avainta etsitään vain sieltä minne se kuuluu"), ei prefiksejä eikä
  imperatiivia. Leipäteksti kertoo, mikä oli väärin ja miksi ratkaisu on
  tämä — kappaleina, ei ranskalaisina viivoina.
- **Selittävä kommentti kuuluu sinne, missä päätös on.** Koodissa on paljon
  kommentteja, jotka kertovat miksi jokin on juuri näin (pankkien muodot,
  pilvisynkka, rajapinnan oikut). Ne ovat tarkoituksellisia; säilytä ne, kun
  muutat ympäröivää koodia.

## Muutamia sisäisiä sopimuksia

- **Kaikki käyttäjän totuutta koskeva tallennus** menee `turvakirjoita`- tai
  `turvakirjoita_json`-funktion kautta (atominen kirjoitus). Raportit ovat
  poikkeus: ne syntyvät joka ajossa uudelleen.
- **Uusi kirjoittava komento** lisätään `KIRJOITTAVAT`-joukkoon, jotta
  `paakirjalukko` suojaa sen. Pelkkä katselu ei lukitse mitään.
- **Sääntötiedostoa kirjoitetaan vain `kirjoita_saannot`-funktiolla**, joka
  ottaa varmuuskopion.
- **`varaus`** tarkoittaa tässä ohjelmassa pankin odottavaa korttiveloitusta
  (`tila`-sarake, `data/varaukset.json`). Budjetin *kertyvä erä*
  (`lue_kertyvat`) on eri asia; älä sekoita nimiä.

## Testaus

Testipakettia ei ole. Muutokset varmistetaan ajamalla ohjelma
hiekkalaatikossa: kopioi `koodi/` tilapäiseen juureen, tee `asetukset/`
esimerkkipohjista ja `data/tapahtumat.csv` synteettisestä aineistosta, ja aja
`aja`, `raportti`, `luokittele` ja `selaa` sitä vasten. Tarkista lopuksi
vähintään `python3 -m py_compile koodi/kirjanpito.py`.
