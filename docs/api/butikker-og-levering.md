# Butikker, levering ("Vigo"), ordrer, Scan Selv, betaling og bedømmelser

Uofficielle noter om REMA 1000-appens backend-API. Kilden er dels egne kald til de
endpoints, der ikke kræver login, dels en gennemlæsning af Android-appen
(`dk.iroots.rema1000`, version 6.9.0). Intet her er dokumenteret af REMA 1000, og
alt kan ændre sig uden varsel.

- Basis-URL: `https://api.digital.rema1000.dk/api/`
- Adresseopslag ligger på en separat host: `https://dawa-proxy.digital.rema1000.dk/`
- Alle stier herunder er relative til basis-URL'en, medmindre andet står.

> **Vigo-levering er lukket.** REMAs eget kampagnebanner i API'et (`GET v1/campaigns`) siger
> "Vigo lukker pr. 1. december 2025", og appens feature-flag for Vigo er slået fra. Alt om
> bestilling, levering, indkøbere ("shoppere"), kørebog og udbetaling herunder er beskrevet,
> som det står i appens kode, men er efter alt at dømme ude af drift. Butikker, åbningstider,
> adresseopslag og Scan Selv hører ikke under Vigo.

## Statusmarkører

| Markør | Betydning |
|---|---|
| **Afprøvet** | Kaldt uden login i forbindelse med denne gennemgang (oktober 2026), og svaret er set. |
| **Set i appens kode** | Kun udledt af appens kode. Ikke kaldt. Feltnavne og typer stammer fra appens datamodeller; hvad serveren faktisk svarer, er ikke kontrolleret. |

Der er udelukkende lavet `GET`-kald uden login. Ingen ordre er oprettet, ændret,
betalt eller annulleret, og intet endpoint, der kræver login, er afprøvet.

## Generelt

**HTTP-metoder.** Appen bruger `GET`, `POST`, `PATCH` og `DELETE`. `PUT` forekommer
ikke i de endpoints, der er beskrevet her; alle opdateringer sker med `PATCH`.

**Login.** Næsten alt i dette dokument kræver et adgangstoken (se dokumentet om
konto og login). Uden token er der set tre forskellige afvisninger:

- `401` med `{"error":"access_denied", ...}` (fx `v1/rating-tags`)
- `401` med `{"message":"An error occured","error_type":"Unauthorized"}` (`v3/stores/{store_id}/time-slots`)
- `405` med `{"error":"system_error","error_message":"Method not allowed"}` (`v3/banks`)

**Svarformater.** Der er to generationer:

- `v1`-endpoints svarer typisk med objektet eller listen direkte.
- `v3`-endpoints pakker svaret ind i `{"data": ...}`. Lister har desuden
  `meta.pagination` med `current_page`, `from`, `to`, `last_page`, `per_page`,
  `total` samt (set i svaret fra `v3/stores`) `links` og `path`.

**Enum-værdier.** Appens modeller rummer en række opremsninger (fx ordrestatus).
Konstanternes navne kendes fra koden, men den præcise stavemåde i JSON kunne ikke
aflæses. De værdier, appen sender som faste tekster, er alle små bogstaver med
understreg (fx `available_for_shoppers`, `in_progress`, `collect`), og
adresseopslaget svarer med små bogstaver. I dette dokument er enum-værdier derfor
skrevet med små bogstaver, men det er en **antagelse** for alle værdier, der ikke
udtrykkeligt er markeret som set.

**Ordforklaring.**

| Begreb i API'et | Betyder |
|---|---|
| job | En ordre – enten levering til døren eller afhentning i butik |
| user / kunde | Den, der bestiller (`as=user`) |
| delivery_guy / shopper / "Vigo-indkøber" | Den, der køber ind og leverer (`as=delivery_guy`) |
| delivery | Leveringen (tidsrum og pris) – og i `v3` også selve afleveringen med foto |
| collect / click and collect | Afhentning i butik |
| basket | Scan Selv-kurv, knyttet til et job |
| route / trip | "Kørebog": en indkøbers kørte ture til brug for kørselsregnskab |

## Oversigt

| # | Metode | Sti | Formål | Status |
|---|---|---|---|---|
| 1 | GET | `v3/stores?per_page=1000` | Alle butikker | Afprøvet |
| 2 | GET | `v3/stores/?filter[...]` | Nærmeste butikker, evt. kun med afhentning | Afprøvet |
| 3 | GET | `v3/users/{user_id}/suggested-stores` | Foreslåede butikker til brugeren | Set i appens kode |
| 4 | GET | `v3/stores/{store_id}/time-slots` | Ledige afhentningstider i en butik | Set i appens kode |
| 5 | GET | `autocomplete` (dawa-proxy) | Adresseforslag | Afprøvet |
| 6 | GET | `v1/settings` | Globale indstillinger for levering | Afprøvet |
| 7 | GET | `v3/shopping-lists/{id}?include=logistic_options` | Kan listen leveres/afhentes, og til hvilken pris | Set i appens kode |
| 8 | POST | `v1/jobs/times-v2` | Mulige leveringstider for en indkøbsliste eller genbestilling | Set i appens kode |
| 9 | POST | `v1/job` | Opret ordre | Set i appens kode |
| 10 | POST | `v1/jobs/create-from-existing` | Opret ordre ud fra en tidligere ordre | Set i appens kode |
| 11 | GET | `v1/jobs-v2` | Aktive ordrer/opgaver | Set i appens kode |
| 12 | GET | `v1/get-inactive-jobs` | Afsluttede ordrer/opgaver (sideinddelt) | Set i appens kode |
| 13 | GET | `v3/users/{user_id}/jobs/{job_id}` | Ekstra oplysninger om en ordre | Set i appens kode |
| 14 | POST | `v1/jobs/find` | Ledige opgaver for indkøbere, evt. nær en position | Set i appens kode |
| 15 | POST | `v1/job/{job_id}/cancel` | Annullér ordre | Set i appens kode |
| 16 | POST | `v1/job/{job_id}/extend-delivery-time` | Vælg nyt leveringstidsrum | Set i appens kode |
| 17 | POST | `v1/job/{job_id}/coupon` | Brug rabat-/gavekode på en ordre | Set i appens kode |
| 18 | PATCH | `v3/jobs/{job_id}/deliveries/{delivery_id}` | Kunden bekræfter eller gør indsigelse mod en aflevering | Set i appens kode |
| 19 | POST | `v1/job/{job_id}/user_orderer` | Kaldes efter betaling, mens appen venter på bekræftelse | Set i appens kode |
| 20 | POST | `v1/job/{job_id}/start` | Indkøber starter indkøbet (evt. som Scan Selv) | Set i appens kode |
| 21 | POST | `v1/job/sync` | Indkøber melder varer købt/udsolgt/erstattet | Set i appens kode |
| 22 | POST | `v1/job/{job_id}/add-coordinate` | Indkøber sender position | Set i appens kode |
| 23 | PATCH | `v3/users/{user_id}/jobs/{job_id}` | Indkøber melder "fremme hos kunden" | Set i appens kode |
| 24 | POST | `v3/jobs/{job_id}/deliveries` | Indkøber registrerer afleveringen (type, foto, position) | Set i appens kode |
| 25 | PATCH | `v3/jobs/{job_id}` | Sæt job tilbage til "ledig for indkøbere" | Set i appens kode |
| 26 | GET | `v3/jobs/{job_id}/payments` | Igangværende betalinger på et job | Set i appens kode |
| 27 | POST | `v3/jobs/{job_id}/payments` | Start en betaling (MobilePay eller kort) | Set i appens kode |
| 28 | DELETE | `v3/jobs/{job_id}/payments/{payment_id}` | Annullér en igangværende betaling | Set i appens kode |
| 29 | GET | `v3/jobs/{job_id}/cash-register-token` | Token til betaling ved kassen (vises som QR-kode) | Set i appens kode |
| 30 | POST | `v3/jobs/{job_id}/scanned-receipt-barcode` | Registrér stregkoden fra kassebonen | Set i appens kode |
| 31 | GET | `v3/jobs/{job_id}/baskets/{basket_id}` | Hent Scan Selv-kurv | Set i appens kode |
| 32 | POST | `v3/jobs/{job_id}/baskets/{basket_id}/items` | Læg scannet vare i kurven | Set i appens kode |
| 33 | PATCH | `v3/jobs/{job_id}/baskets/{basket_id}/items/{item_id}` | Ret antal på en kurvlinje | Set i appens kode |
| 34 | DELETE | `v3/jobs/{job_id}/baskets/{basket_id}/items/{item_id}` | Fjern kurvlinje | Set i appens kode |
| 35 | GET | `v1/rating-tags` | Mulige mærkater til en bedømmelse | Set i appens kode |
| 36 | POST | `v1/ratings` | Afgiv bedømmelse af en ordre | Set i appens kode |
| 37 | GET | `v3/users/{user_id}/routes` | Kørebog: liste over ruter | Set i appens kode |
| 38 | GET | `v3/users/{user_id}/routes/{route_id}` | Kørebog: én rute med ture | Set i appens kode |
| 39 | PATCH | `v3/users/{user_id}/routes/{route_id}` | Kørebog: skift transportform | Set i appens kode |
| 40 | POST | `v3/users/{user_id}/routes/{route_id}/trips` | Kørebog: tilføj tur | Set i appens kode |
| 41 | PATCH | `v3/users/{user_id}/routes/{route_id}/trips/{trip_id}` | Kørebog: ret note på tur | Set i appens kode |
| 42 | GET | `v3/banks` | Liste over banker (til udbetalingskonto) | Set i appens kode |
| 43 | POST | `v3/users/{user_id}/bank-accounts` | Opret udbetalingskonto | Set i appens kode |
| 44 | PATCH | `v3/users/{user_id}/bank-accounts/{account_id}` | Bekræft udbetalingskonto med kode | Set i appens kode |

I alt 44 endpoints: 4 afprøvet, 40 set i appens kode.

Grænsetilfælde: nr. 6 (`v1/settings`) og nr. 42-44 (bankkonti) hører lige så meget
til konto-området; nr. 7 hører også til indkøbslister. Brugerens gemte adresser
(`v3/users/{user_id}/addresses`) bruges ved bestilling (`address_id`), men er
beskrevet under konto-området.

---

## 1. Butikker

### 1.1 `GET v3/stores` — alle butikker

**Status: Afprøvet.** Kræver ikke login.

Appen henter hele listen i ét kald med `per_page=1000` og gemmer den lokalt i 12 timer.

| Query-parameter | Type | Beskrivelse |
|---|---|---|
| `per_page` | heltal | Antal pr. side. Appen bruger 1000. |
| `page` | heltal | Sidenummer. Fremgår af `meta.pagination.links`; appen bruger det ikke. |

Ved afprøvningen var `meta.pagination.total` 439.

Felter pr. butik (alle set i svaret):

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Butikkens id i API'et. Det er dette id, der bruges som `store_id` i andre kald. |
| `internal_id` | heltal | REMA's eget butiksnummer |
| `name` | tekst | Butikkens navn |
| `address` | tekst | Gade og nummer |
| `postal_code` | tekst | Postnummer |
| `city` | tekst | By |
| `phone` | tekst | Telefon med landekode |
| `opening_date` | dato eller null | Formentlig åbningsdato for nye butikker (var null i de sete svar) |
| `smiley_report_url` | tekst | Link til kontrolrapport |
| `facebook_page_url` | tekst | Link til butikkens Facebook-side |
| `is_click_and_collect_active` | boolesk | Om butikken tilbyder afhentning |
| `merchant.name` | tekst | Købmandens navn |
| `merchant.photo_url` | tekst | Billede af købmanden |
| `location.latitude`, `location.longitude` | decimaltal | Position |
| `geofence.distance` | tal | Radius i meter (100 i de sete svar). Appen bruger den til at afgøre, om man står i butikken (Scan Selv). |
| `opening_hours[]` | liste | Åbningstider for i dag og seks dage frem (7 poster i de sete svar) |
| `opening_hours[].date` | dato `ÅÅÅÅ-MM-DD` | Dagen |
| `opening_hours[].label` | tekst eller null | Var null i de sete svar; formentlig tekst ved særlige dage |
| `opening_hours[].opening_at`, `.closing_at` | tidspunkt (ISO 8601, UTC) | Åbner/lukker. Bemærk at tiderne er i UTC. |
| `collect_pre_order_message` | tekst eller null | Var null i de sete svar |

Appens model kender ikke `opening_date`, `smiley_report_url`, `facebook_page_url`,
`label` og `collect_pre_order_message` – de findes i svaret, men bruges ikke af
Android-appen i denne version.

Eksempel (forkortet, opdigtede værdier):

```json
{
  "data": [
    {
      "id": 9001,
      "internal_id": 999,
      "name": "Eksempelby, Eksempelvej",
      "address": "Eksempelvej 1",
      "postal_code": "0000",
      "city": "Eksempelby",
      "phone": "+4500000000",
      "is_click_and_collect_active": false,
      "merchant": { "name": "Fornavn Efternavn", "photo_url": "https://example.invalid/foto.jpg" },
      "location": { "latitude": 55.0, "longitude": 10.0 },
      "geofence": { "distance": 100 },
      "opening_hours": [
        { "date": "2030-01-01", "label": null,
          "opening_at": "2030-01-01T06:00:00+00:00",
          "closing_at": "2030-01-01T20:00:00+00:00" }
      ]
    }
  ],
  "meta": { "pagination": { "current_page": 1, "from": 1, "to": 1, "last_page": 1, "per_page": 1000, "total": 1 } }
}
```

Et opslag på en enkelt butik (`GET v3/stores/{store_id}`) findes ikke i appen, og
et forsøg gav `405 Method not allowed`. Enkeltbutikker må altså findes i listen.

### 1.2 `GET v3/stores/` med filtre — nærmeste butikker

**Status: Afprøvet.** Kræver ikke login (appen kalder det dog kun, når man er logget ind).

Bruges i bestillingsforløbet til at foreslå afhentningsbutikker nær brugerens position.

| Query-parameter | Type | Beskrivelse |
|---|---|---|
| `filter[near_coordinates]` | tekst | `breddegrad,længdegrad`, fx `55.0,10.0` |
| `filter[is_click_and_collect_active]` | `true`/`false` | Appen sender altid `true`. Ved afprøvning gav `true` kun butikker med afhentning. |
| `per_page` | heltal | Appen bruger 3 |

Svaret har samme form som 1.1. Ved afprøvningen kom butikker tæt på den angivne
position først; at listen er sorteret efter afstand, er en rimelig, men ikke
bevist, slutning.

### 1.3 `GET v3/users/{user_id}/suggested-stores` — foreslåede butikker

**Status: Set i appens kode.** Kræver login.

| Parameter | Hvor | Type | Beskrivelse |
|---|---|---|---|
| `user_id` | sti | heltal | Den indloggede brugers id |
| `per_page` | query | heltal | Antal forslag |

Svar: `{"data": [butik, ...], "meta": {...}}` med butikker som i 1.1. Hvad
forslagene bygger på (adresse, tidligere køb), fremgår ikke af appen.

Et særskilt endpoint for *favoritbutik* er ikke fundet i dette område; se "Uafklaret".

### 1.4 `GET v3/stores/{store_id}/time-slots` — afhentningstider

**Status: Set i appens kode.** Kræver login (uden token: 401, afprøvet).

Bruges, når en indkøbsliste skal bestilles til afhentning i en bestemt butik.

| Parameter | Hvor | Type | Beskrivelse |
|---|---|---|---|
| `store_id` | sti | heltal | Butikkens `id` |
| `shopping_list_id` | query | heltal | Indkøbslistens id på serveren |

Svar: `data` er et objekt, hvor nøglen er en dato og værdien en liste af tidsrum.

| Felt | Type | Beskrivelse |
|---|---|---|
| `from` | tidspunkt | Tidsrummets start |
| `to` | tidspunkt | Tidsrummets slutning |
| `is_available` | boolesk | Om tidsrummet kan vælges |

```json
{
  "data": {
    "2030-01-01": [
      { "from": "2030-01-01T10:00:00+00:00", "to": "2030-01-01T11:00:00+00:00", "is_available": true }
    ]
  }
}
```

(Tidsformatet i eksemplet er et gæt ud fra butikkernes åbningstider.)

### 1.5 `GET https://dawa-proxy.digital.rema1000.dk/autocomplete` — adresseforslag

**Status: Afprøvet.** Kræver ikke login.

En proxy foran det offentlige danske adresseregisters autocomplete-tjeneste
(DAWA). Appen bruger den, når brugeren taster en leveringsadresse. Det valgte
forslags `data.id` er den værdi, der sendes som `dawa_address_id`, når en adresse
gemmes på brugeren (konto-området).

| Query-parameter | Type | Beskrivelse |
|---|---|---|
| `q` | tekst | Det indtastede |
| `caretpos` | heltal | Markørens position i teksten |
| `startfra` | tekst, valgfri | `vejnavn`, `adgangsadresse` eller `adresse` – hvor i forløbet søgningen starter (stavemåden er antaget; parameteren blev ikke afprøvet) |
| `multilinje` | boolesk | Appen sender `true` (giver linjeskift i `forslagstekst`) |
| `type` | tekst | Appen sender `adresse` |
| `fuzzy` | boolesk | Appen sender `true` |
| `side` | heltal | Sidenummer |
| `per_side` | heltal | Antal pr. side; appen bruger 20 |

Appen sender desuden headeren `Accept-Encoding: identity`.

Svar: en liste direkte (ingen `data`-indpakning).

| Felt | Type | Beskrivelse |
|---|---|---|
| `type` | tekst | `vejnavn`, `adgangsadresse` eller `adresse` (`adgangsadresse` set i svaret) |
| `tekst` | tekst | Teksten, der skal stå i søgefeltet, hvis forslaget vælges |
| `forslagstekst` | tekst | Teksten til visning |
| `caretpos` | heltal | Ny markørposition |
| `data.id` | tekst (UUID) | Adressens id |
| `data.x`, `data.y` | decimaltal | Koordinater. Kendes af appens model, men var ikke med i det sete svar. |

```json
[
  {
    "type": "adgangsadresse",
    "tekst": "Eksempelvej 1, 0000 Eksempelby",
    "forslagstekst": "Eksempelvej 1\n0000 Eksempelby",
    "caretpos": 30,
    "data": { "id": "00000000-0000-0000-0000-000000000000" }
  }
]
```

### 1.6 `GET v1/settings` — globale indstillinger

**Status: Afprøvet.** Kræver ikke login. (Grænsetilfælde – også relevant for konto-området.)

Fortæller bl.a., om bestilling er lukket lige nu. Felter set i svaret:

| Felt | Type | Beskrivelse |
|---|---|---|
| `closed` | boolesk | Om bestilling er lukket generelt |
| `closed_android`, `closed_ios`, `closed_web` | boolesk | Lukket pr. platform |
| `closed_reason` | tekst | Forklaring til brugeren |
| `closed_order_button_text` | tekst | Tekst på bestil-knappen, når der er lukket |
| `show_coupon_code` | boolesk | Om en kampagnekode skal vises |
| `coupon_code` | tekst | Kampagnekoden |
| `coupon_code_text_line_1`, `coupon_code_text_line_2` | tekst | Tekst omkring koden |
| `status_text_enabled` | boolesk | Om en driftsbesked skal vises |
| `status_text` | tekst (HTML) | Driftsbeskeden |
| `welcome_page_feature_1` … `_3` | heltal | Styrer velkomstsiden |
| `current_user_agreement_version` | heltal | Gældende version af brugervilkår |
| `current_competition_agreement_version` | heltal eller null | Gældende version af konkurrencevilkår |
| `competition_agreement_active` | boolesk | Om konkurrencevilkår er aktive |

Bemærk, at tekstfelterne kan indeholde gammelt indhold, selv om det tilhørende
flag er `false` (fx en lukketekst fra en tidligere højtid).

---

## 2. Ordrer ("jobs")

### 2.1 Ordrens forløb, som appen viser det

En ordre hedder et *job*. Der er to typer: `delivery` (levering til døren) og
`collect` (afhentning i butik). To roller ser på det samme job: kunden, der har
bestilt, og indkøberen ("Vigo"), der køber ind og leverer. Samme app og samme
API dækker begge roller; parameteren `as` (`user` eller `delivery_guy`) afgør,
hvilken side man ser listerne fra.

Forløbet for kunden, så langt koden viser det:

1. **Kan listen bestilles?** Appen spørger på indkøbslisten, om levering og
   afhentning er mulig og hvad det koster (2.2).
2. **Hvornår?** Ved levering hentes mulige datoer og tidsrum for listen og
   adressen (2.3). Ved afhentning hentes butikkens ledige tider (1.4).
3. **Opret.** Ordren oprettes (2.4) – eller genbestilles ud fra en tidligere (2.5).
4. **Vent.** Ordren ligger og venter på, at en indkøber tager den. Finder ingen
   den i tide, kan kunden vælge et nyt tidsrum (3.2) eller annullere (3.1).
5. **Indkøb.** Indkøberen starter, melder varer købt, udsolgt eller erstattet og
   betaler i butikken (afsnit 4 og 5).
6. **Aflevering.** Indkøberen melder sig fremme og registrerer afleveringen, evt.
   med foto. Kunden kan bekræfte modtagelsen eller gøre indsigelse (3.4).
7. **Bedømmelse.** Begge parter kan bedømme hinanden (afsnit 7).

Appens model har disse ordrestatusser, i denne rækkefølge:

| Status (navn i appen) | Betydning, som koden lader forstå |
|---|---|
| `inactive` | Ikke aktiv |
| `pending` | Venter på en indkøber |
| `expires_soon` | Venter, men tidsrummet er ved at udløbe |
| `expired` | Ingen tog ordren i tide |
| `accepted` | En indkøber har taget ordren |
| `started` | Indkøbet er i gang |
| `ready_for_payment` | Alle varer er håndteret; klar til betaling i butikken |
| `payment_complete` | Betalt |
| `payment_validation_required` | Betalingen skal kontrolleres (behandles som hastende i appen) |
| `bought` | Indkøbet er afsluttet |
| `at_customer_address` | Indkøberen er fremme |
| `delivered` | Afleveret |
| `objection` | Kunden har gjort indsigelse mod afleveringen |
| `completed` | Afsluttet |

Vigtigt forbehold: ikke alle disse kommer nødvendigvis fra serveren. Appen
udleder selv mindst tre af dem efter at have læst svaret – `ready_for_payment`
(en lokal beregning, formentlig ud fra om alle varer er håndteret), `at_customer_address` (leveringsjob uden
registreret aflevering) og `objection` (afleveringen har et indsigelsestidspunkt).
Statussen står i feltet `status_v2`. Hvilke værdier serveren selv sender, er ikke
kontrolleret.

For afhentningsjob beregner appen desuden en afhentningsstatus lokalt
(ikke aktiv, accepteret, klar til afhentning, afhentet, afsluttet) ud fra
`status_v2`, `bought` og tidsrummet. Den findes ikke som felt i API'et.

### 2.2 `GET v3/shopping-lists/{id}?include=logistic_options` — leveringsmuligheder for en liste

**Status: Set i appens kode.** Kræver login. (Grænsetilfælde til indkøbslister.)

| Parameter | Hvor | Type | Beskrivelse |
|---|---|---|---|
| `id` | sti | heltal | Indkøbslistens id på serveren |
| `include` | query | tekst | Fast `logistic_options` |

Svar (`data`):

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Listens id |
| `logistic_options.delivery.is_available` | boolesk | Om listen kan leveres |
| `logistic_options.delivery.price` | decimaltal eller null | Pris for levering |
| `logistic_options.collect.is_available` | boolesk | Om listen kan afhentes |
| `logistic_options.collect.price` | decimaltal eller null | Pris for afhentning |

### 2.3 `POST v1/jobs/times-v2` — mulige leveringstider

**Status: Set i appens kode.** Kræver login.

Fungerer som validering før bestilling: serveren svarer med de tidsrum, ordren
kan leveres i, og appen viser en fejl, hvis kaldet afvises. Ændrer så vidt
koden viser ingenting, selv om metoden er `POST`.

Request-body (JSON) – enten indkøbsliste eller tidligere ordre:

| Felt | Type | Beskrivelse |
|---|---|---|
| `shoppinglist_id` | heltal | Indkøbslisten, der skal bestilles – eller |
| `job_id` | heltal | En tidligere ordre, der skal genbestilles |
| `address_id` | heltal | Brugerens gemte leveringsadresse |

Svar (direkte objekt):

| Felt | Type | Beskrivelse |
|---|---|---|
| `can_deliver_immediately` | boolesk | Om "hurtigst muligt" tilbydes |
| `default_step` | heltal | Forvalgt længde på tidsrummet (antal trin) ved planlagt levering |
| `default_immediately_step` | heltal | Tilsvarende ved "hurtigst muligt" |
| `times[]` | liste | Mulige dage |
| `times[].date` | dato | Dagen |
| `times[].string` | tekst | Dagen som visningstekst |
| `times[].is_holiday` | boolesk | Helligdag |
| `times[].intervals_from_times[]` | liste af tekst | Mulige starttidspunkter |
| `times[].intervals_to_times[]` | liste af tekst | Mulige sluttidspunkter |
| `times[].price.new_price` | decimaltal | Leveringspris for dagen |
| `times[].price.difference` | decimaltal | Forskel til den tidligere pris |
| `times[].price.price_changed` | boolesk | Om prisen er ændret |

### 2.4 `POST v1/job` — opret ordre

**Status: Set i appens kode.** Kræver login. **Opretter en rigtig ordre.**

Request-body (JSON):

| Felt | Type | Beskrivelse |
|---|---|---|
| `shoppinglist_id` | heltal | Indkøbslisten, der bestilles |
| `job_type` | tekst | `collect` ved afhentning. Ved levering sætter appen ikke feltet. |
| `store_id` | heltal | Butik (bruges ved afhentning; modellen sender altid feltet, 0 hvis ikke sat) |
| `address_id` | heltal | Leveringsadresse (ved levering) |
| `date` | tekst `ÅÅÅÅ-MM-DD` | Leveringsdag |
| `time` | tekst `fra-til` | Tidsrum, sat sammen af et start- og et sluttidspunkt med bindestreg |
| `is_immediate_delivery` | boolesk | `true` ved "hurtigst muligt". Appen sender også `true` ved afhentning. |
| `comment` | tekst | Besked til indkøberen (udelades, hvis tom) |
| `phone_number` | tekst | Telefonnummer (appen sætter det ved afhentning) |
| `phone_country_code` | tekst | Landekode med `+` foran (ved afhentning) |
| `job_id` | heltal | Kun ved genbestilling, se 2.5 |

Svar: et job-objekt (2.9).

```json
{
  "shoppinglist_id": 123456,
  "address_id": 111,
  "store_id": 0,
  "date": "2030-01-01",
  "time": "16:00-18:00",
  "is_immediate_delivery": false,
  "comment": "Eksempelbesked"
}
```

### 2.5 `POST v1/jobs/create-from-existing` — genbestil

**Status: Set i appens kode.** Kræver login. **Opretter en rigtig ordre.**

Samme body som 2.4, men med `job_id` sat til den tidligere ordre (og uden
indkøbsliste). Svar: et job-objekt.

### 2.6 `GET v1/jobs-v2` — aktive job

**Status: Set i appens kode.** Kræver login.

| Query-parameter | Type | Beskrivelse |
|---|---|---|
| `as` | tekst | `user` = mine ordrer som kunde; `delivery_guy` = opgaver, jeg har taget som indkøber |
| `limited` | heltal | Appen sender 1. Betydningen er ikke afklaret (formentlig et forkortet svar). |

Svar: en liste af job-objekter direkte. Appen henter listerne igen med faste
mellemrum, mens den er åben.

### 2.7 `GET v1/get-inactive-jobs` — afsluttede job

**Status: Set i appens kode.** Kræver login.

| Query-parameter | Type | Beskrivelse |
|---|---|---|
| `as` | tekst | `user` eller `delivery_guy` |
| `page` | heltal | Sidenummer, fra 1 |

Svar: `data` med job-objekter samt `current_page`, `last_page`, `per_page` og
`total` (ifølge appens model på øverste niveau, ikke under `meta`).

### 2.8 `GET v3/users/{user_id}/jobs/{job_id}` — ekstra oplysninger

**Status: Set i appens kode.** Kræver login.

| Parameter | Hvor | Type | Beskrivelse |
|---|---|---|---|
| `user_id`, `job_id` | sti | heltal | Bruger og ordre |
| `include` | query | tekst | Appen sender `is_customer_cancellation_available` |

Svar (`data`): appen læser kun `is_customer_cancellation_available` (boolesk) –
om kunden selv kan annullere ordren lige nu. Om endpointet kan levere mere, er ukendt.

### 2.9 Job-objektet

Felter, som appens model kender. **Set i appens kode** – intet er kontrolleret mod et rigtigt svar.

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Ordrens id (`job_id`) |
| `name` | tekst | Navn (indkøbslistens navn) |
| `type` | tekst | `delivery` eller `collect` |
| `status_v2` | tekst | Status, se 2.1 |
| `comment` | tekst | Kundens besked |
| `bought` | boolesk | Om indkøbet er gennemført |
| `total_items` | heltal | Antal varer |
| `total_price` | decimaltal | Samlet pris |
| `total_weight`, `total_weight_unit` | heltal, tekst | Anslået vægt |
| `amount_of_bags`, `estimated_bags_string` | heltal, tekst | Anslået antal poser |
| `min_age` | heltal | Aldersgrænse, hvis ordren rummer aldersbegrænsede varer |
| `enable_replacement_items` | boolesk | Om erstatningsvarer er tilladt |
| `delivery_is_free` | boolesk | Gratis levering |
| `reserve_amount`, `reservation_extra`, `reservation_text` | decimaltal, decimaltal, tekst | Beløb, der reserveres hos kunden, og forklaring |
| `sort_type` | tekst | Transportform: `walk`, `bike`, `car`, `distance_location`, `undefined` |
| `basket_id` | heltal eller null | Scan Selv-kurv, hvis der er en |
| `user_payment_id`, `delivery_guy_payment_id`, `dibs_order_id` | tekst | Betalingsreferencer |
| `delivery_guy_basket_amount` | decimaltal | Beløb i indkøberens kurv |
| `delivery_guy_paid_amount` (ældre: `delivery_guy_payed_amount`) | decimaltal | Beløb, indkøberen har betalt |
| `delivery_guy_scanned_receipt_amount` | decimaltal | Beløb fra den scannede bon |
| `did_delivery_guy_exceeded_max_amount` | boolesk | Indkøberen har overskredet det tilladte beløb |
| `offered_at`, `taken_at`, `accepted_at`, `started_at`, `bought_at`, `delivered_at` | tidspunkt | Tidsstempler for forløbet |
| `store` | objekt | `id`, `name` |
| `address` | objekt | `id`, `street`, `postal_code`, `city`, `lat`, `long`, `distance`, `distance_unit` |
| `user` | objekt | Kunden: `id`, `name`, `phone`, `photo`, `rating_float`, `hasRated` |
| `delivery_guy` | objekt | Indkøberen, samme felter som `user` |
| `delivery` | objekt | Tidsrum og pris, se nedenfor |
| `job_delivery` | objekt eller null | Den registrerede aflevering, se nedenfor |
| `items[]` | liste | Varelinjer, se nedenfor |
| `extra_items[]` | liste | Tillæg (fx gebyrer): `name`, `description`, `amount`, `price`, `sort` |

`delivery`:

| Felt | Type | Beskrivelse |
|---|---|---|
| `date` | tekst `ÅÅÅÅ-MM-DD` | Leveringsdag |
| `from_time`, `to_time` | tekst `TT:MM` | Tidsrum |
| `date_string` | tekst | Dagen som visningstekst |
| `is_immediate_delivery` | boolesk | "Hurtigst muligt" |
| `delivery_cost` | heltal | Leveringspris |
| `delivery_cost_including_fees` | heltal | Leveringspris inkl. gebyrer |
| `original_delivery_cost_including_fees` | heltal | Pris før evt. rabat |
| `premature_shopping_margin` | heltal | Hvor tidligt indkøbet må begynde (enhed ukendt, formentlig minutter) |
| `extending` | objekt | Tilbud om nyt tidsrum: `message`, `timestamp`, `is_external_delivery_available`, `dates[]` (samme form som `times[]` i 2.3) |

`job_delivery`:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | `delivery_id` til 3.4 |
| `type` | tekst | `delivery` eller `collect` ifølge modellen |
| `photo_url` | tekst | Indkøberens foto af afleveringen |
| `confirmed_at` | tidspunkt | Kunden har bekræftet |
| `objection_at` | tidspunkt | Kunden har gjort indsigelse |
| `objection_window_expires_at` | tidspunkt | Frist for indsigelse |

`items[]`:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Varelinjens id i jobbet |
| `item_id` | heltal | Varens id |
| `name`, `underline` | tekst | Navn og undertekst |
| `amount` | heltal | Antal |
| `total_price` | decimaltal | Linjens pris |
| `sub_price` | tekst | Enhedspris som tekst |
| `status` | tekst | `on_list`, `bought`, `replaced`, `sold_out` |
| `bought`, `soldout` | boolesk | Købt / udsolgt |
| `replacement_id`, `replacement_item`, `replacements[]` | heltal, varelinje, liste af heltal | Erstatningsvare og mulige erstatninger |
| `is_on_discount` | boolesk | På tilbud |
| `price_changed`, `price_changes_on`, `price_changes_type` | boolesk, tekst, tekst | Varslet prisændring |
| `assortment_code` | heltal | Sortimentskode |
| `department_id`, `department_name`, `department_sort`, `sorting` | heltal/tekst | Afdeling og sortering |
| `store_item` | objekt | Varen fra kataloget (se dokumentet om katalog og produkter) |

---

## 3. Kundens handlinger på en ordre

### 3.1 `POST v1/job/{job_id}/cancel` — annullér

**Status: Set i appens kode.** Kræver login. Ingen body. Svar: det opdaterede job.

Appen viser kun muligheden, når `is_customer_cancellation_available` (2.8) er sand.

### 3.2 `POST v1/job/{job_id}/extend-delivery-time` — nyt tidsrum

**Status: Set i appens kode.** Kræver login.

Bruges, når ordren ikke er blevet taget, og serveren har tilbudt nye tider i
`delivery.extending.dates`.

| Felt | Type | Beskrivelse |
|---|---|---|
| `date` | tekst (dato) | Ny dag |
| `time` | tekst `fra-til` | Nyt tidsrum |

Svar: det opdaterede job.

### 3.3 `POST v1/job/{job_id}/coupon` — rabatkode

**Status: Set i appens kode.** Kræver login.

| Felt | Type | Beskrivelse |
|---|---|---|
| `coupon` | tekst | Koden |

Svar: det opdaterede job (med ændret pris).

### 3.4 `PATCH v3/jobs/{job_id}/deliveries/{delivery_id}` — bekræft eller gør indsigelse

**Status: Set i appens kode.** Kræver login. `delivery_id` er `job_delivery.id`.

Appen sender præcis ét af felterne:

| Felt | Type | Beskrivelse |
|---|---|---|
| `is_confirmed` | boolesk | `true`: kunden bekræfter, at varerne er modtaget |
| `request_objection` | boolesk | `true`: kunden gør indsigelse mod afleveringen |

Intet svarindhold bruges; appen henter ordrelisten igen bagefter.

### 3.5 `POST v1/job/{job_id}/user_orderer`

**Status: Set i appens kode.** Kræver login. Ingen body, intet svarindhold bruges.

Det eneste sted, appen kalder dette, er i betalingsforløbet: efter at en betaling
er sat i gang, kaldes endpointet gentagne gange, indtil det lykkes, mens appen
viser skiftende statustekster ("bekræfter betaling ..."). Et vellykket svar
behandles som "betalingen er bekræftet". Hvad serveren præcis gør ved kaldet, og
hvorfor navnet er `user_orderer`, kan ikke aflæses af appen.

---

## 4. Indkøberens ("Vigo") handlinger

Disse kald hører til indkøber-rollen. De er med for helhedens skyld; en
almindelig kundekonto har formentlig ikke adgang til dem.

### 4.1 `POST v1/jobs/find` — ledige opgaver

**Status: Set i appens kode.** Kræver login.

Uden body: ledige opgaver generelt. Med body: ledige opgaver nær en position.

| Felt | Type | Beskrivelse |
|---|---|---|
| `lat` | decimaltal | Breddegrad |
| `long` | decimaltal | Længdegrad |

Svar: liste af job-objekter.

### 4.2 `POST v1/job/{job_id}/start` — start indkøb

**Status: Set i appens kode.** Kræver login.

Uden body: almindeligt indkøb. Med body: indkøb som Scan Selv.

| Felt | Type | Beskrivelse |
|---|---|---|
| `flow_type` | tekst | `scan_and_pay` (eneste værdi i appen; stavemåden antaget) |
| `store_id` | heltal | Butikken, indkøbet foregår i |

Svar: det opdaterede job.

### 4.3 `POST v1/job/sync` — meld varer købt, udsolgt eller erstattet

**Status: Set i appens kode.** Kræver login.

| Felt | Type | Beskrivelse |
|---|---|---|
| `changes[]` | liste | Ændringer pr. job |
| `changes[].id` | heltal | Job |
| `changes[].items[]` | liste | Ændrede varelinjer |
| `changes[].items[].id` | heltal | Varelinjens id |
| `changes[].items[].bought` | boolesk | Købt |
| `changes[].items[].soldout` | boolesk | Udsolgt |
| `changes[].items[].replacement_id` | heltal | Valgt erstatningsvare |
| `single` | heltal | Betydning ikke afklaret |

Svar: et job-objekt.

### 4.4 `POST v1/job/{job_id}/add-coordinate` — send position

**Status: Set i appens kode.** Kræver login.

| Felt | Type | Beskrivelse |
|---|---|---|
| `type` | tekst | `in_progress`, `bought` eller `completed` – hvor i forløbet positionen er taget |
| `latitude`, `longitude` | decimaltal | Position |
| `accuracy` | heltal | Nøjagtighed (formentlig meter) |

### 4.5 `PATCH v3/users/{user_id}/jobs/{job_id}` — fremme hos kunden

**Status: Set i appens kode.** Kræver login.

| Felt | Type | Beskrivelse |
|---|---|---|
| `status` | tekst | `at_customer_address` (eneste værdi i appen; stavemåden antaget) |

### 4.6 `POST v3/jobs/{job_id}/deliveries` — registrér aflevering

**Status: Set i appens kode.** Kræver login. Sendes som `multipart/form-data`.

| Del | Type | Beskrivelse |
|---|---|---|
| `type` | tekst | `customer_home`, `customer_not_home` eller `collect` |
| `photo` | fil (billede) | Foto af de afleverede varer; kan udelades |
| `location[latitude]` | tekst | Breddegrad; udelades, hvis position ikke kendes |
| `location[longitude]` | tekst | Længdegrad; udelades, hvis position ikke kendes |

### 4.7 `PATCH v3/jobs/{job_id}` — giv jobbet tilbage

**Status: Set i appens kode.** Kræver login.

| Felt | Type | Beskrivelse |
|---|---|---|
| `status` | tekst | Fast `available_for_shoppers` |

Svar: job-objekt. Ud fra værdien ser det ud til, at indkøberen hermed frigiver
en opgave, så andre kan tage den; det er en tolkning.

---

## 5. Betaling

Kun dokumenteret – intet her er afprøvet.

Betalingen i dette område er den, der sker i butikken for et job: indkøberen
(eller en Scan Selv-kunde) betaler kurven. Kundens egen betaling for en
leveringsordre (reservation på kort) ses i job-objektets beløbsfelter, men appen
har ikke særskilte endpoints for kundens kortoplysninger i det materiale, der er
gennemgået; kort håndteres på en ekstern betalingsside.

### 5.1 `POST v3/jobs/{job_id}/payments` — start betaling

**Status: Set i appens kode.** Kræver login.

Appen kender to betalingsformer:

| Felt | MobilePay | Kort |
|---|---|---|
| `provider` | `mobilepay_app_payment` | `worldline` |
| `redirect_uri` | `dk.rema1000.vigo://vigo.dk/mobilepay_callback` | `https://shop.rema1000.dk/redirect` |
| `cancel_uri` | (udelades) | `https://shop.rema1000.dk/cancel` |
| `exclude_payment_methods` | (udelades) | `["mobilepay"]` |

"MobilePay-callback" er altså ikke et endpoint på serveren, men en adresse med
appens eget URL-skema, som MobilePay-appen sender brugeren tilbage til, når
betalingen er godkendt eller afbrudt.

Svar:

| Felt | Type | Beskrivelse |
|---|---|---|
| `meta.vendor.url` | tekst | Adressen, brugeren skal sendes til (MobilePay-appen eller betalingsvinduet) |
| `meta.vendor.redirect_uri` | tekst | Adressen, betalingen vender tilbage til |

Derefter venter appen på bekræftelse, jf. 3.5.

### 5.2 `GET v3/jobs/{job_id}/payments` — igangværende betalinger

**Status: Set i appens kode.** Kræver login.

Svar: `data[]` med `id` (betalingens id). Appen bruger det til at finde en
hængende betaling, før en ny startes.

### 5.3 `DELETE v3/jobs/{job_id}/payments/{payment_id}` — annullér betaling

**Status: Set i appens kode.** Kræver login. Intet svarindhold bruges.

### 5.4 `GET v3/jobs/{job_id}/cash-register-token` — betaling ved kassen

**Status: Set i appens kode.** Kræver login.

Svar: `data.token` (tekst). Appen viser værdien som QR-kode, der scannes ved kassen.

### 5.5 `POST v3/jobs/{job_id}/scanned-receipt-barcode` — registrér kassebon

**Status: Set i appens kode.** Kræver login.

Indkøberen scanner stregkoden nederst på kassebonen. Appen accepterer kun en
kode på 20 cifre, der begynder med `0`, og deler den selv op:

| Position | Indhold | Felt i body |
|---|---|---|
| 2.-4. ciffer | Butiksnummer (100-999) | `store_id` (heltal) |
| 5.-14. ciffer | Bonnummer | `receipt_number` (heltal) |
| 15.-20. ciffer | Beløb | `amount` (heltal; formentlig i øre) |

Svar (`data`):

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Registreringens id |
| `amount` | decimaltal | Beløb |
| `receipt.number` | tekst | Bonnummer |
| `receipt.total_price` | decimaltal | Bonens total |
| `receipt.items[]` | liste | Bonlinjer: `name`, `amount`, `price`, `total_price` |

### 5.6 Udbetalingskonto (grænsetilfælde til konto-området)

Bruges af indkøbere til at angive, hvor udlæg skal udbetales.

**`GET v3/banks?page={n}`** — **Set i appens kode.** Liste over banker:
`data[]` med `id` og `name`. Uden login svarede serveren `405`.

**`POST v3/users/{user_id}/bank-accounts`** — **Set i appens kode.**

| Felt | Type | Beskrivelse |
|---|---|---|
| `bank_id` | heltal | Bank fra listen |
| `registration_number` | tekst | Registreringsnummer |
| `account_number` | tekst | Kontonummer |

**`PATCH v3/users/{user_id}/bank-accounts/{account_id}`** — **Set i appens kode.**

| Felt | Type | Beskrivelse |
|---|---|---|
| `verification_code` | tekst | Kode, som brugeren har modtaget |
| `is_verified` | boolesk | Appen sender altid `true` |

Svar på begge (`data`): `id`, `bank` (`id`, `name`), `registration_number`,
`account_number`, `is_verified`, `created_at`, `updated_at`.

---

## 6. Scan Selv

Scan Selv er bygget oven på job: der hører en kurv (`basket_id`) til et job, og
alle kurv-kald går gennem `v3/jobs/{job_id}/baskets/{basket_id}`. Et endpoint,
der *opretter* en kurv, findes ikke i appen; kurvens id kommer med job-objektet,
efter at jobbet er startet med `flow_type` = `scan_and_pay` (4.2). Appen bruger
butikkens `geofence.distance` til at afgøre, om man befinder sig i butikken.

### 6.1 `GET v3/jobs/{job_id}/baskets/{basket_id}` — hent kurv

**Status: Set i appens kode.** Kræver login.

| Parameter | Hvor | Type | Beskrivelse |
|---|---|---|---|
| `job_id`, `basket_id` | sti | heltal | Job og kurv |
| `include` | query | tekst, valgfri | Appen sender enten intet eller `items,items.job_item` |

Svar (`data`):

| Felt | Type | Beskrivelse |
|---|---|---|
| `order_id` | tekst | Kurvens ordrenummer |
| `status` | tekst | `started`, `awaiting_control`, `awaiting_qr`, `fetched`, `completed`, `cancelled` |
| `total_price` | decimaltal | Kurvens total |
| `items[]` | liste | Kurvlinjer (kun med `include`), se 6.2 |

Statusnavnene antyder forløbet: i gang → evt. udtaget til kontrol → venter på
QR-kode ved kassen → hentet af kassen → afsluttet. Det er en tolkning af navnene.

### 6.2 `POST v3/jobs/{job_id}/baskets/{basket_id}/items` — tilføj vare

**Status: Set i appens kode.** Kræver login.

| Felt | Type | Beskrivelse |
|---|---|---|
| `barcode` | tekst | Den scannede stregkode |
| `amount` | heltal | Antal |
| `job_item_id` | heltal, valgfri | Varelinjen på indkøbslisten, som den scannede vare dækker eller erstatter |

Svar (`data`) – en kurvlinje:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Kurvlinjens id (`item_id`) |
| `product_id` | heltal | Produkt |
| `barcode` | tekst | Stregkode |
| `name` | tekst | Varenavn |
| `amount` | heltal | Antal |
| `price` | decimaltal | Pris |
| `type` | tekst | `default`, `weight` (vægtvare) eller `self_scale` (vejes selv) |
| `job_item` | objekt eller null | Tilknyttet varelinje: `id`, `product_id`, `amount`, `is_sold_out` |

Til at slå en stregkode op uden at lægge varen i kurven findes
`v3/product-barcode/{barcode}` (se dokumentet om katalog og produkter).

### 6.3 `PATCH v3/jobs/{job_id}/baskets/{basket_id}/items/{item_id}` — ret antal

**Status: Set i appens kode.** Kræver login.

| Felt | Type | Beskrivelse |
|---|---|---|
| `amount` | heltal | Nyt antal |

Svar (`data`): den opdaterede kurvlinje.

### 6.4 `DELETE v3/jobs/{job_id}/baskets/{basket_id}/items/{item_id}` — fjern vare

**Status: Set i appens kode.** Kræver login. Intet svarindhold bruges.

Kvittering og betaling for Scan Selv går gennem afsnit 5 (QR-kode ved kassen
eller betaling i appen, og registrering af bonens stregkode).

---

## 7. Bedømmelser

### 7.1 `GET v1/rating-tags` — mærkater

**Status: Set i appens kode.** Kræver login (uden token: 401, afprøvet).

Svar: `data[]`.

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Mærkatens id |
| `name` | tekst | Tekst, fx en ros eller et kritikpunkt |
| `rating_from`, `rating_to` | heltal | Mærkaten tilbydes, når den valgte stjernebedømmelse ligger i dette interval |
| `user_type` | tekst | `customer` eller `delivery_guy` – hvem mærkaten handler om |

### 7.2 `POST v1/ratings` — afgiv bedømmelse

**Status: Set i appens kode.** Kræver login.

| Felt | Type | Beskrivelse |
|---|---|---|
| `job_id` | heltal | Ordren, der bedømmes |
| `rating` | heltal | Antal stjerner |
| `comment` | tekst | Fri kommentar |
| `rating_tags` | liste af heltal | Valgte mærkater |

Hvem der bedømmes, følger af rollen: kunden bedømmer indkøberen og omvendt.
`hasRated` på `user`/`delivery_guy` i job-objektet viser, om der allerede er bedømt.

```json
{ "job_id": 123456, "rating": 5, "comment": "Eksempelkommentar", "rating_tags": [1, 2] }
```

---

## 8. Kørebog (ruter og ture)

Indkøbere kan føre regnskab over kørsel. En *rute* samler dagens *ture*.

### 8.1 `GET v3/users/{user_id}/routes` — ruter

**Status: Set i appens kode.** Kræver login.

| Query-parameter | Type | Beskrivelse |
|---|---|---|
| `page[size]` | heltal | Antal pr. side |
| `page[number]` | heltal | Sidenummer |
| `filter[date]` | dato | Kun ruter for denne dag |

Bemærk, at sideinddelingen her hedder `page[size]`/`page[number]` og ikke
`per_page`/`page` som i resten af `v3`.

Svar: `data[]` med ruter plus sideoplysninger.

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Rutens id |
| `transport_type` | tekst | `bike` eller `car` |
| `trips[]` | liste | Ture, se 8.4 |

### 8.2 `GET v3/users/{user_id}/routes/{route_id}` — én rute

**Status: Set i appens kode.** Svar (`data`): en rute som i 8.1.

### 8.3 `PATCH v3/users/{user_id}/routes/{route_id}` — skift transportform

**Status: Set i appens kode.** Body: `transport_type` (`bike` eller `car`).

### 8.4 `POST v3/users/{user_id}/routes/{route_id}/trips` — tilføj tur

**Status: Set i appens kode.**

| Felt | Type | Beskrivelse |
|---|---|---|
| `trip_type` | tekst | `shopper_to_shop`, `shop_to_customer`, `customer_to_shop`, `customer_to_shopper`, `customer_to_customer`, `no_origin`, `no_destination` |
| `from_address_id` | heltal, valgfri | Startadresse |
| `to_address_id` | heltal, valgfri | Slutadresse |

En tur i svarene har felterne `id`, `job_id`, `trip_type`, `address_from`,
`address_to`, `distance` (heltal, enhed ukendt) og `note`.

### 8.5 `PATCH v3/users/{user_id}/routes/{route_id}/trips/{trip_id}` — ret note

**Status: Set i appens kode.** Body: `note` (tekst).

---

## Uafklaret

1. **Enum-værdiernes stavemåde.** Statusser, typer og roller er her skrevet med
   små bogstaver og understreg. Det er sikkert for de værdier, appen sender som
   faste tekster (`collect`, `available_for_shoppers`, `in_progress`, `bought`,
   `completed`, `customer_home`, `customer_not_home`, `mobilepay_app_payment`,
   `worldline`, `user`, `delivery_guy`), men en antagelse for resten – herunder
   hele `status_v2`-rækken, `flow_type`, `transport_type`, `trip_type`, kurvstatus
   og `user_type`.
2. **Hvilke statusser serveren selv sender.** Appen udleder nogle af dem lokalt
   (2.1). Den faktiske værdimængde i `status_v2` kendes først, når et rigtigt svar er set.
3. **`user_orderer`.** Kaldes kun i forbindelse med bekræftelse af betaling.
   Hvad det gør på serveren, og om det har noget med en rolle at gøre, er ukendt.
4. **`limited=1` på `v1/jobs-v2` og `single` i `v1/job/sync`.** Betydningen fremgår ikke.
5. **Favoritbutik.** Der er ikke fundet et endpoint til at gemme en foretrukken
   butik i dette område. Enten ligger valget kun i appen, eller også sættes det
   via brugeropdateringen (konto-området).
6. **Hvordan en Scan Selv-kurv opstår** for en almindelig kunde uden
   leveringsordre – altså hvordan jobbet bag kurven oprettes. Appen har intet
   særskilt "opret kurv"-kald; formentlig sker det via 2.4 eller 4.2, men det er ikke eftervist.
7. **Kundens kortbetaling for leveringsordrer.** Ingen endpoints for gemte kort
   er fundet. Felterne `user_payment_id`, `dibs_order_id` og `reserve_amount`
   tyder på en reservation hos en ekstern betalingsudbyder, men forløbet er ikke kortlagt.
8. **Beløbsenheder.** `amount` i bon-stregkoden (formentlig øre),
   `delivery_cost` (heltal – kroner eller øre?), `distance` på ture og
   `premature_shopping_margin` er ikke afklaret.
9. **Tidsformater.** `from_time`/`to_time` og de mulige tider i 2.3 antages at
   være `TT:MM`; formatet af `from`/`to` i afhentningstider (1.4) er ikke set.
10. **`times-v2` som validering.** Koden bruger kaldet som kontrol før bestilling,
    men om serveren også kontrollerer varernes tilgængelighed, minimumsbeløb
    eller leveringsområde her, vides ikke.
11. **Indkøber-endpoints og almindelige konti.** Det er ikke kontrolleret, hvad
    en kundekonto får som svar på afsnit 4 og 8.
12. **Forskellige afvisninger uden login.** `v3/banks` svarer `405` og
    `v3/stores/{store_id}/time-slots` svarer med en anden 401-form end resten.
    Årsagen er ukendt; det kan være forskellige lag i serveren.
13. **Butiksfelter uden for appens model** (`opening_date`, `label`,
    `collect_pre_order_message`) var null i alle sete svar; betydningen er gættet ud fra navnene.
