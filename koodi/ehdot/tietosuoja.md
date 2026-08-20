# Rahaputki — tietosuojaseloste

*Päivitetty 20.8.2026*

## Lyhyesti

Rahaputki on avoimen lähdekoodin ohjelma, joka ajetaan **käyttäjän omalla
koneella**. Sillä ei ole palvelinta, tiliä eikä pilvipalvelua. Ohjelman
tekijä ei vastaanota, näe, tallenna eikä välitä kenenkään tilitietoja.

Jokainen käyttäjä rekisteröi **oman** Enable Banking -sovelluksensa ja liittää
siihen **omat** tilinsä. Tilitiedot kulkevat pankista käyttäjän oman
sovelluksen kautta suoraan hänen koneelleen.

## Kuka on rekisterinpitäjä

Käyttäjä itse. Rahaputki on työkalu, jolla hän käsittelee omia tietojaan
omalla laitteellaan — samaan tapaan kuin taulukkolaskentaohjelmalla. Ohjelman
tekijä ei ole rekisterinpitäjä eikä käsittelijä, koska hän ei missään
vaiheessa käsittele käyttäjän tietoja.

## Mitä tietoja käsitellään ja missä

Kaikki alla oleva sijaitsee **vain** käyttäjän omalla koneella, hänen
valitsemassaan kansiossa:

| Tieto | Missä |
|---|---|
| Tilitapahtumat (päivä, summa, saaja, viesti) | `data/tapahtumat.csv` |
| Tilien tunnisteet ja asetukset | `asetukset/config.json` |
| Enable Banking -sovelluksen tunnus ja avaimen polku | `asetukset/pankkihaku.env` |
| Sovelluksen yksityisavain (RSA) | oletuksena `~/.rahaputki/` |
| Raportit | `raportit/` |

Käyttäjä päättää itse, varmuuskopioiko hän kansion ja synkronoiko hän sen
pilvitallennukseen. Ohjelma ei tee kumpaakaan puolestaan.

## Verkkoyhteydet

Rahaputki ottaa yhteyden ainoastaan Enable Bankingin rajapintaan
(`api.enablebanking.com`) ja vain silloin, kun käyttäjä itse käynnistää
haun. Ohjelmassa ei ole analytiikkaa, seurantaa, mainoksia, telemetriaa
eikä automaattista päivitystä.

## Enable Bankingin rooli

Yhteys pankkeihin kulkee Enable Banking Oy:n (Espoo, Suomi) rajapinnan
kautta. Enable Banking on Finanssivalvonnan valvoma tilitietopalvelun
tarjoaja (AISP), ja siihen sovelletaan sen omaa tietosuojaselostetta:
<https://enablebanking.com/privacy-notice/>. Pankkitunnuksia ei anneta
Rahaputkelle eikä Enable Bankingille — tunnistautuminen tehdään aina pankin
omassa palvelussa.

## Säilytysaika ja poistaminen

Tiedot säilyvät niin kauan kuin käyttäjä pitää tiedostot koneellaan. Kaiken
voi poistaa poistamalla kansion ja avaintiedoston sekä perumalla suostumuksen
Enable Bankingin hallintapaneelista.

## Yhteystiedot

Ohjelmaa koskevat kysymykset: ville@salmensuu.fi
