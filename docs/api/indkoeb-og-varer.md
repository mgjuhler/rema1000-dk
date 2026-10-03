# Indkøb og varer

Kortlægning af den del af REMA 1000-appens backend, der handler om det, der ryger i kurven:
indkøbslister, favoritter, varer, katalog, søgning, tilbud, tilbudsavis, forsideindhold og opskrifter.

Kilde: Android-appen `dk.iroots.rema1000` version 6.9.0 (dekompileret) samt enkelte kald uden login
mod de åbne endpoints den 2026-10-03. Dokumentet er uofficielt, og API'et kan ændre sig uden varsel.

## Sådan læses dokumentet

Hvert endpoint har en statusmarkør:

- **Afprøvet** — kaldt mod det rigtige API (enten uden login som led i denne kortlægning, eller
  tidligere med login den 2026-10-03). Svarets form er set i virkeligheden.
- **Set i appens kode** — fundet i den dekompilerede app, men ikke kaldt. Feltnavne og typer
  stammer fra appens modeller; serveren kan sende flere felter, end appen læser.

Eksempler bruger opdigtede værdier.

### Baser og fælles forhold

| Base | Bruges til | Login |
|---|---|---|
| `https://api.digital.rema1000.dk/api/` | Alt under `v1/`, `v2/`, `v3/` samt `search/` | Afhænger af endpoint |
| `https://api.digital.rema1000.dk/api/rema1000dk/` | CMS-indhold: `entities`, `featured-recipes` | Nej |
| `https://squid-api.tjek.com` | Tilbudsavisen (Tjek, tidligere eTilbudsavis) | API-nøgle i header |
| `https://publication-viewer.tjek.com` | Webvisning af tilbudsavisen | API-nøgle i URL |

Appen sender disse headere på alle kald til REMA's API: `Accept: application/json`,
`X-Device: android`, `X-Locale`, `X-Timezone: Europe/Copenhagen` og en `User-Agent` på formen
`REMA1000App/<version> (Android <os-version>; <producent> <model>)`. De åbne endpoints svarede fint
med kun `Accept: application/json`.

Appen har to generationer af svarformater:

- **v1/v2**: rå JSON (liste eller objekt) uden indpakning. Indkøbslisterne har deres egen konvolut
  (`response`, `unixtime`, `wait`, `settings`).
- **v3, `search/` og `rema1000dk/`**: `{"data": …, "meta": {"pagination": {…}}}`. Pagineringen
  har `current_page`, `from`, `to`, `last_page`, `per_page`, `total` og på v3/search også `path`
  og `links{first,last,prev,next}`. Sider er 1-baserede og styres med `page` og `per_page`.

Fejl på v3-formatet set i praksis: `{"message": "...", "error_type": "InvalidFilter"}` (HTTP 400)
og `{"message": "Validation failed", "error_type": "Validation", "errors": {"felt": ["..."]}}`.

HTTP-metoder: appens Retrofit-annotationer er navneforvanskede. Ved at følge dem til Retrofits
request-fabrik er det fastslået, at den annotation, der bruges på bl.a. `v2/shoppinglists/{id}`,
er **PATCH** (ikke PUT). PUT findes som annotation, men bruges ikke på nogen endpoints i dette område.

## Oversigt

| # | Metode | Sti | Formål | Login | Status |
|---|---|---|---|---|---|
| 1 | GET | `v1/shoppinglists/polling` | Hent alle indkøbslister (long-poll-agtig løkke) | Ja | Afprøvet |
| 2 | POST | `v1/sync/shoppinglists-v2` | Opret/omdøb/slet lister og ændr varer på listen | Ja | Afprøvet |
| 3 | PATCH | `v2/shoppinglists/{id}` | Gør en liste til primær liste | Ja | Set i appens kode |
| 4 | POST | `v1/shoppinglist/{id}/invite` | Invitér medlemmer til en liste via e-mail | Ja | Set i appens kode |
| 5 | POST | `v1/user/friends/emails` | Slå brugere op ud fra e-mailadresser | Ja | Set i appens kode |
| 6 | POST | `v1/user/friends/numbers` | Slå brugere op ud fra telefonnumre | Ja | Set i appens kode |
| 7 | GET | `v3/shopping-lists/{id}?include=logistic_options` | Leverings-/afhentningsmuligheder for en liste (grænseområde) | Ja | Set i appens kode |
| 8 | GET | `v3/shopping-lists/{id}/recommended-products` | Anbefalede varer ud fra listens indhold | Ja | Afprøvet |
| 9 | GET | `v1/shoppinglistsuggestions` | Fritekstforslag til listen (titel + kategori) | Nej | Afprøvet |
| 10 | GET | `v1/favorites/{store_id}` | Hent favoritvarer | Ja | Afprøvet |
| 11 | POST | `v3/users/{user_id}/favorites` | Tilføj favoritvare | Ja | Afprøvet |
| 12 | DELETE | `v1/favorites/{store_id}/{item_id}` | Fjern favoritvare | Ja | Afprøvet |
| 13 | GET | `v3/users/{user_id}/favorite-suggestions` | Forslag til favoritter | Ja | Afprøvet |
| 14 | DELETE | `v3/users/{user_id}/favorite-suggestions/{product_id}` | Afvis et favoritforslag | Ja | Set i appens kode |
| 15 | GET | `v3/users/{user_id}/frequently-bought-products` | "Du plejer at købe" | Ja | Afprøvet (gav 403) |
| 16 | GET | `v3/users/{user_id}/inspiration-products` | "Måske du synes om" | Ja | Set i appens kode |
| 17 | DELETE | `v3/users/{user_id}/inspiration-products/{product_id}` | Afvis en inspirationsvare | Ja | Set i appens kode |
| 18 | POST | `v3/batch` | Flere API-kald i én forespørgsel (bl.a. mange favoritter ad gangen) | Ja | Set i appens kode |
| 19 | GET | `v1/catalog/store/{store_id}/withchildren` | Hele kataloget i ét svar | Nej | Afprøvet |
| 20 | GET | `v1/catalog/store/{store_id}/last_modified` | Tidsstempel for seneste katalogændring | Nej | Afprøvet |
| 21 | GET | `v3/products` | Pagineret vareliste med filtre og sortering | Nej | Afprøvet |
| 22 | GET | `v3/products/{id}` | Én vare | Nej | Afprøvet (bruges ikke af appen) |
| 23 | GET | `v3/departments` | Afdelinger, evt. med kategorier | Nej | Afprøvet (bruges ikke af appen) |
| 24 | GET | `v3/departments/{department_id}/categories/{category_id}/products` | Varer i en kategori | Nej | Afprøvet |
| 25 | GET | `v3/product-barcode/{barcode}` | Slå en stregkode op | Nej | Afprøvet |
| 26 | GET | `search/products` | Varesøgning | Nej | Afprøvet |
| 27 | GET | `v1/campaigns` | Kampagnebannere for alle | Nej | Afprøvet |
| 28 | GET | `v1/user/campaigns` | Kampagnebannere for den indloggede bruger | Ja | Set i appens kode |
| 29 | GET | `v3/newsletters` | Liste over nyhedsbreve | Nej | Afprøvet |
| 30 | GET | `v3/users/{user_id}/newsletter-subscriptions` | Brugerens tilmeldinger (grænseområde) | Ja | Set i appens kode |
| 31 | POST | `v3/users/{user_id}/newsletter-subscriptions` | Tilmeld nyhedsbrev (grænseområde) | Ja | Set i appens kode |
| 32 | DELETE | `v3/users/{user_id}/newsletter-subscriptions/{id}` | Afmeld nyhedsbrev (grænseområde) | Ja | Set i appens kode |
| 33 | GET | `v1/settings` | Globale app-indstillinger (grænseområde) | Nej | Afprøvet |
| 34 | GET | Tjek: `/v2/catalogs` | Aktive tilbudsaviser | API-nøgle | Set i appens kode |
| 35 | GET | Tjek: `/v2/offers/{offer_id}` | Ét tilbud fra avisen | API-nøgle | Set i appens kode |
| 36 | POST | Tjek: `/v4/rpc/get_offer_products` | Varerne bag et tilbud | API-nøgle | Set i appens kode |
| 37 | GET | Tjek-viewer: `/v1/embeds/{publication_id}` | Webvisning af avisen (ikke et API) | API-nøgle | Set i appens kode |
| 38 | GET | `rema1000dk/entities` | CMS-indhold: forside, opskrifter, opskrifts-tags | Nej | Afprøvet |
| 39 | GET | `rema1000dk/featured-recipes` | Opskrifter i en fremhævet gruppe | Nej | Afprøvet (kun fejlsvar uden parameter) |
| 40 | GET | `search/recipes` | Opskriftssøgning | Nej | Afprøvet |
| 41 | GET | `v3/users/{user_id}/favorite-recipes` | Favoritopskrifter | Ja | Set i appens kode |
| 42 | POST | `v3/users/{user_id}/favorite-recipes` | Tilføj favoritopskrift | Ja | Set i appens kode |
| 43 | DELETE | `v3/users/{user_id}/favorite-recipes/{recipe_id}` | Fjern favoritopskrift | Ja | Set i appens kode |

43 endpoints: 23 afprøvet, 20 kun set i appens kode.

---

## Indkøbslister

Appen holder indkøbslisterne i en lokal database og synkroniserer med to endpoints: ét til at
hente (polling) og ét til at sende ændringer (sync). Der findes ikke separate endpoints til at
oprette, omdøbe eller slette en liste — det hele går gennem sync-kaldet.

### 1. `GET v1/shoppinglists/polling` — Afprøvet

Henter brugerens indkøbslister.

Query:

| Parameter | Type | Beskrivelse |
|---|---|---|
| `unixtime` | heltal | Tidsstemplet fra forrige svar. `0` ved første kald. |

Svar:

| Felt | Type | Beskrivelse |
|---|---|---|
| `response` | liste af lister | Indkøbslisterne. Appen betragter svaret som mislykket, hvis feltet mangler. |
| `unixtime` | heltal | Gemmes og sendes med i næste kald. |
| `wait` | heltal | Hvor længe klienten skal vente før næste kald. Appen bruger værdien som **millisekunder**. |
| `settings` | objekt | Samme indhold som `v1/settings`; appen opdaterer sine indstillinger herfra. |
| `error_code`, `error_message` | heltal, tekst | Findes i appens model til fejlsvar; ikke set i praksis. |

Liste:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Listens id på serveren. |
| `code` | tekst | Delekode, bruges i invitationslinket (se nedenfor). |
| `name` | tekst | Listens navn. |
| `approved` | bool | Om brugeren har accepteret medlemskab af listen (formodet betydning). |
| `active` | bool | Aktiv liste. |
| `primary` | bool | Primær liste — den, appen viser som standard. |
| `items` | liste | Varelinjer, se nedenfor. |
| `members` | liste | Medlemmer, se nedenfor. |
| `warning`, `bags` | — | Set i svaret fra API'et, men læses ikke af appens model. Betydning ukendt. |

Varelinje:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Linjens id på serveren. |
| `name` | tekst | Varenavn eller fritekst. |
| `unit` | tekst | Enhed (set i svaret; læses ikke af appen). |
| `amount` | tekst i svaret (appen læser det som heltal) | Antal. |
| `bought` | bool | Krydset af. |
| `total_price` | tal | Normalpris gange antal (set i svaret; læses ikke af appen). |
| `store_id` | heltal | Katalogets butik-id, i praksis `1`. |
| `store_item_id` | heltal | Varens id i kataloget. Fritekstlinjer har ingen vare tilknyttet. |

Medlem:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Brugerens id. |
| `name` | tekst | Navn. |
| `email` | tekst | E-mail. |
| `phone_number`, `phone_country_code` | tekst | Telefon. |
| `photo` | tekst | URL til profilbillede. |
| `approved` | bool | Om medlemmet har accepteret invitationen. |
| `is_self` | bool | Om medlemmet er den indloggede bruger. |
| `found_by_phone_number` | liste af tekst | Udfyldes ved opslag på telefonnummer (endpoint 6). |

**Polling-semantik (fra appens kode):** appen kalder med det gemte `unixtime`, gemmer svarets
`unixtime` lokalt, venter `wait` millisekunder og kalder igen. Det gemte `unixtime` kan blive
nulstillet til 0 (ser ud til at ske, når de lokale lister ryddes, fx ved logout). Efter et
sync-kald fortsætter samme vente-og-poll-løkke. Om serveren sender alle lister hver gang, eller
kun dem, der er ændret siden `unixtime`, er ikke afklaret (se "Uafklaret").

```json
{
  "response": [
    {
      "id": 1234567, "code": "abc123", "name": "Indkøbsliste",
      "approved": true, "active": true, "primary": true,
      "items": [
        {"id": 987654321, "name": "EKSEMPELVARE", "unit": "stk", "amount": "2",
         "bought": false, "total_price": 21.0, "store_id": 1, "store_item_id": 11111}
      ],
      "members": [
        {"id": 111, "name": "Test Testesen", "email": "test@example.com",
         "approved": true, "is_self": true}
      ]
    }
  ],
  "unixtime": 1700000000,
  "wait": 5000,
  "settings": {}
}
```

### 2. `POST v1/sync/shoppinglists-v2` — Afprøvet

Sender lokale ændringer. Svaret har samme form som polling-svaret.

Body:

```json
{
  "changes": [
    {
      "id": 1234567,
      "name": "Indkøbsliste",
      "items": [
        {"offlineId": "00000000-0000-4000-8000-000000000000", "name": "EKSEMPELVARE",
         "source": "android_search", "amount": 1, "bought": false,
         "store_id": 1, "store_item_id": 11111}
      ]
    }
  ]
}
```

Liste-ændring:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Serverens liste-id. Bruges, når listen findes på serveren. |
| `offlineId` | tekst (UUID) | Bruges i stedet for `id`, når listen er ny. Klienten vælger selv værdien. |
| `name` | tekst | Listens navn. Appen sender det altid med; et ændret navn er en omdøbning. |
| `deleted` | bool | `true` sletter listen. |
| `items` | liste | Kun de linjer, der er nye eller ændrede. |

Linje-ændring:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Serverens linje-id (eksisterende linje). |
| `offlineId` | tekst (UUID) | Ny linje. |
| `name` | tekst | Sendes kun for nye linjer. |
| `source` | tekst | Hvor i appen linjen kom fra. Sendes altid. |
| `amount` | heltal | Sendes for nye linjer, og når antallet er ændret. |
| `bought` | bool | Sendes for nye linjer, og når afkrydsningen er ændret. |
| `store_id`, `store_item_id` | heltal | Sendes for nye linjer, og når linjens vare er ændret. |
| `deleted` | bool | `true` fjerner linjen; de øvrige felter udelades så. |

De tre grundoperationer, som er afprøvet:

- Ny linje: `{offlineId, name, source, amount, bought: false, store_id: 1, store_item_id}`
- Ændret antal: `{id, source, amount}`
- Fjern linje: `{id, source, deleted: true}`

Udledt af appens kode, ikke afprøvet:

- **Opret liste**: en ændring med `offlineId` og `name` (uden `id`).
- **Omdøb liste**: en ændring med `id` og nyt `name`.
- **Slet liste**: en ændring med `id` og `deleted: true`. Det er også sådan, man forlader en
  delt liste i appen, så vidt koden viser — der er ikke fundet et særskilt "forlad liste"-endpoint.
- **Kryds af**: `{id, source, bought: true}`.

Værdier for `source` set i appen: `android_newspaper`, `android_newspaper_list`,
`android_favorites`, `android_search`, `android_scanner`, `android_category`, `android_recipe`,
`android_trending`, `android_presearch_for_you`, `android_presearch_trending`,
`android_recommendations_from_active_list`, `android_inspiration`,
`android_shoppinglist_marked_unbought`.

En detalje fra appen: lægges en vare på listen, som allerede findes som købt eller slettet linje,
genbruges linjen med `bought: false`, `amount: 1` og `source: android_shoppinglist_marked_unbought`.
Findes den som aktiv linje, tælles `amount` én op.

### 3. `PATCH v2/shoppinglists/{id}` — Set i appens kode

Gør listen til brugerens primære liste. `{id}` er serverens liste-id.

Body: `{"primary": true}`. Svaret læses ikke af appen; bagefter henter den listerne igen.
Om endpointet accepterer andre felter (fx `name`) er ikke kendt.

### 4. `POST v1/shoppinglist/{id}/invite` — Set i appens kode

Inviterer medlemmer til listen. Bemærk ental i stien (`shoppinglist`).

Body er form-kodet (`application/x-www-form-urlencoded`), ikke JSON:

| Felt | Type | Beskrivelse |
|---|---|---|
| `emails[]` | tekst, gentages | E-mailadresser, der skal inviteres. |

Svaret læses ikke af appen.

### 5. `POST v1/user/friends/emails` og 6. `POST v1/user/friends/numbers` — Set i appens kode

Slår op, om nogen af de givne e-mailadresser eller telefonnumre tilhører REMA-brugere, så de kan
vises som mulige listemedlemmer. Form-kodet body med `emails[]` henholdsvis `numbers[]`
(gentages pr. værdi). Svaret er en liste af medlemsobjekter (samme form som `members` ovenfor);
ved telefonopslag angiver `found_by_phone_number`, hvilke af de sendte numre der gav træffet.

Disse to ligger på grænsen til konto-området, men bruges kun til deling af lister.

### Invitationslinks

Appen bygger selv et delelink ud fra listens `code` og sender det via e-mail, sms eller
delemenuen. Linket har formen (set i koden, ikke afprøvet):

```
https://api.digital.rema1000.dk/shoppinglist?code=<code>&by=<afsenders navn>
```

med enten `&email=<modtager>` eller `&phone=<nummer>&country=+45` tilføjet, når modtageren er
kendt. Appen er desuden registreret til at åbne links på `shop.rema1000.dk` med stierne
`/shopping-list-invitation-link/…` og `/shopping-lists/…`. Hvad der sker på serveren, når
linket åbnes, og hvordan en invitation accepteres via API'et, er ikke kortlagt.

### 7. `GET v3/shopping-lists/{id}?include=logistic_options` — Set i appens kode

Fortæller, om listen kan bestilles til levering eller afhentning. Hører reelt til
bestillingsområdet, men nævnes her, fordi det er en egenskab ved listen.

Svar: `data.id` (heltal) og `data.logistic_options` med `collect` og `delivery`, hver med
`is_available` (bool) og `price` (tal eller null).

### 8. `GET v3/shopping-lists/{id}/recommended-products` — Afprøvet

Anbefalede varer ud fra, hvad der ligger på listen ("Anbefalinger til din liste" på
søgeskærmen). Query: `per_page`, `page`. Svaret er en v3-vareliste (se "Vareobjektet (v3)").
Ved afprøvningen kom `data` tilbage som en tom liste.

### 9. `GET v1/shoppinglistsuggestions` — Afprøvet

Åben liste over fritekstforslag til indkøbslisten. Svaret er en rå liste af
`{"title": tekst, "category": tekst}`.

---

## Favoritter og personlige forslag

Der er ikke fundet noget bonus- eller "personlige tilbud"-API i appen. Det personlige indhold
består af favoritter, favoritforslag, "du plejer at købe" og inspirationsvarer.

### 10. `GET v1/favorites/{store_id}` — Afprøvet

Henter favoritvarer. `store_id` er katalogets butik-id (`1`). Appen læser kun `id` (varens id) på
hvert element i listen.

### 11. `POST v3/users/{user_id}/favorites?product_id={id}` — Afprøvet

Tilføjer en vare til favoritter. Vare-id'et sendes som query-parameter, ikke i en body.
Appen læser ikke svaret. Skal flere varer tilføjes på én gang, pakker appen kaldene i
`v3/batch` (endpoint 18).

### 12. `DELETE v1/favorites/{store_id}/{item_id}` — Afprøvet

Fjerner en favorit. Svaret er den opdaterede favoritliste (liste af objekter med `id`).

### 13. `GET v3/users/{user_id}/favorite-suggestions` — Afprøvet

Forslag til varer, brugeren kunne gøre til favoritter. Query: `per_page` (appen bruger 50) og
`page`. Svaret er på v3-formatet; appen læser kun `id` på hvert element.

### 14. `DELETE v3/users/{user_id}/favorite-suggestions/{product_id}` — Set i appens kode

Afviser et forslag, så det ikke vises igen. Ingen body; svaret læses ikke.

### 15. `GET v3/users/{user_id}/frequently-bought-products` — Afprøvet (gav 403)

"Du plejer at købe". Query: `per_page`, `page`. Efter appens kode er svaret en v3-vareliste.
Ved afprøvning med login svarede serveren 403; årsagen er ikke afklaret (se "Uafklaret").

### 16. `GET v3/users/{user_id}/inspiration-products` — Set i appens kode

"Måske du synes om". Query: `per_page`, `page`. Svaret er en v3-vareliste.

### 17. `DELETE v3/users/{user_id}/inspiration-products/{product_id}` — Set i appens kode

Afviser en inspirationsvare. Efter appens kode er svaret den opdaterede v3-vareliste.

### 18. `POST v3/batch` — Set i appens kode

Udfører flere API-kald i én forespørgsel. Generelt endpoint; i dette område bruges det til at
tilføje mange favoritter ad gangen. (Appen bruger det også til ordre- og scan selv-kald, som
hører til et andet område.)

Body:

```json
{
  "requests": [
    {"method": "POST", "uri": "/api/v3/users/111/favorites", "parameters": {"product_id": "11111"}},
    {"method": "POST", "uri": "/api/v3/users/111/favorites", "parameters": {"product_id": "22222"}}
  ]
}
```

| Felt | Type | Beskrivelse |
|---|---|---|
| `requests[].method` | tekst | HTTP-metode. Set i appen: `POST`, `PATCH`, `DELETE`. |
| `requests[].uri` | tekst | Absolut sti inklusive `/api/`. |
| `requests[].parameters` | objekt (tekst → tekst) eller udeladt | Parametre til delkaldet. |

Svaret er en liste med ét element pr. delkald: `status` (heltal, HTTP-status) og `body`
(objekt; appen læser `error_type` og `message` ved fejl).

---

## Katalog og varer

Varedata findes i to udgaver: det gamle samlede katalog (`v1/catalog/…`), som appen henter i ét
stykke og gemmer lokalt, og de nyere paginerede v3-endpoints. Vare-id'er er de samme i begge
(`store_item_id` på en indkøbsliste = `id` på en vare).

### 19. `GET v1/catalog/store/{store_id}/withchildren` — Afprøvet

Hele kataloget for butik `1` i ét svar på cirka 10 MB. Hent det sjældent, og brug
endpoint 20 til at afgøre, om det er nødvendigt.

Struktur: butik → `departments[]` → `categories[]` → `items[]`.

| Niveau | Felter (fra appens model, når ikke andet er nævnt) |
|---|---|
| Butik | `id`, `name`, `timestamp`, `departments` |
| Afdeling | `id`, `name`, `sort`, `image_url`, `important_information` (HTML), `categories` |
| Kategori | `id`, `id_v3` (kategoriens id i v3-API'et), `name`, `sort`, `hidden`, `important_information`, `items` |
| Vare | se nedenfor |

Varefelter, som appens model læser: `id`, `name`, `underline`, `description_short`,
`image_url`, `pricing`, `labels` (liste af tekst), `bar_codes` (liste af tekst), `search_words`,
`warnings`, `hp_statements`, `declaration`, `declaration_old`, `nutrition_info` og
`nutrition_info_old` (lister af `{name, value, sort}`), `temperature_zone`, `min_age`,
`is_weight_item`, `is_self_scale_item`, `median_weight`, `median_weight_unit`, `sorting`,
`assortment_code`, `assortment_label`, `assortment_disclaimer`, `item_label`, `item_disclaimer`,
`department{id, name}`, `category{id, name}` og `gpsr` (producentoplysninger: `name`, `street`,
`postal_code`, `city`, `county`, `state_code`, `country_code`, `email`, `website`,
`security_alert`).

Set i det rigtige svar, men ikke i appens model: `hf2`, `images[{small, medium, large}]`,
`description`, `extra.popularity`.

`pricing`:

| Felt | Type | Beskrivelse |
|---|---|---|
| `price` | tal | Aktuel pris. |
| `normal_price` | tal | Normalpris. |
| `is_on_discount` | bool | Nedsat lige nu. |
| `is_advertised` | bool | Med i tilbudsavisen. |
| `deposit` | tal | Pant. |
| `max_quantity` | heltal | Maks. antal til tilbudsprisen. |
| `price_over_max` | tal | Pris pr. stk. ud over `max_quantity`. |
| `price_per_kilogram` | tal | Kilopris. |
| `price_per_unit` | tekst | Enhedspris som tekst. |
| `price_changes_on`, `price_changes_type` | tekst | Kommende prisændring (i appens model; ikke nærmere undersøgt). |
| `store` | objekt | Butiksspecifik pris (i appens model; ikke nærmere undersøgt). |

### 20. `GET v1/catalog/store/{store_id}/last_modified` — Afprøvet

Svar: `{"last_modified": <heltal>}`. Appen sammenligner med sit gemte tidsstempel og henter kun
kataloget igen, hvis det er ændret.

### Vareobjektet (v3)

Fælles for endpoint 8, 15, 16, 21–24, 26 og for varer indlejret i CMS-indhold og opskrifter.
Set i rigtige svar:

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | Vare-id. |
| `name` | tekst | Varenavn (versaler). |
| `underline` | tekst | Undertekst, typisk mængde og mærke. |
| `description` | tekst eller null | Beskrivelse, kan indeholde HTML. |
| `info` | tekst | Supplerende oplysninger, fx oprindelse. |
| `age_limit` | heltal eller null | Aldersgrænse. |
| `labels` | liste af `{id, name, image}` | Mærkninger (økologi, nøglehul …) med ikon-URL. |
| `images` | liste af `{small, medium, large}` | Billed-URL'er på `rema-product-images.digital.rema1000.dk`. |
| `prices` | liste | Prisperioder, se nedenfor. |
| `temperature_zone` | tekst eller null | Fx `refrigerated_5_degrees_celsius`. |
| `hazard_precaution_statements` | liste | Faresætninger. |
| `is_self_scale_item`, `is_weight_item`, `is_batch_item` | bool | Vægt-/selvvejningsvare m.m. |
| `is_available_in_all_stores` | bool | Føres i alle butikker. |
| `origin_country` | tekst eller null | Oprindelsesland. |
| `wine_labels` | liste | Vinmærkater. |

Kun i søgesvar (endpoint 26): `department`, `category`, `barcodes` (liste af tekst),
`search_words`, `declaration` (HTML), `warnings`, `gpsr`, `surface_treatments`, `produce`.
På `v3/products` kommer `department` kun med, når man beder om `include=department`.

`prices[]`:

| Felt | Type | Beskrivelse |
|---|---|---|
| `price` | tal | Pris i perioden. |
| `starting_at`, `ending_at` | tekst (ISO 8601) | Periodens start og slut. Åben slutdato vises som år 2099. |
| `is_advertised` | bool | Avisvare i perioden. |
| `is_campaign` | bool | Kampagnepris i perioden. |
| `max_quantity` | heltal eller null | Maks. antal til prisen. |
| `price_over_max_quantity` | tal eller null | Pris ud over maks. antal. |
| `deposit` | tal eller null | Pant. |
| `compare_unit` | tekst | Enhed for sammenligningspris (`kg`, `ltr` …). |
| `compare_unit_price` | tal | Sammenligningspris. |
| `consumption_unit`, `consumption_quantity` | — | Altid null i de sete svar. |

En vare på tilbud havde to elementer i `prices`: først den aktuelle tilbudsperiode
(`is_advertised: true`), derefter den efterfølgende normalprisperiode. Det ser altså ud til, at
første element er den gældende pris, og resten er kommende perioder; det er en iagttagelse ud
fra ét svar, ikke en dokumenteret regel.

```json
{
  "id": 11111, "name": "EKSEMPELVARE", "underline": "1 LTR. / EKSEMPEL",
  "labels": [{"id": 5, "name": "Økologi", "image": "https://static-assets.digital.rema1000.dk/product/labels/5-64.webp"}],
  "images": [{"small": "https://…/1-small-x.webp", "medium": "https://…/1-medium-x.webp", "large": "https://…/1-large-x.webp"}],
  "prices": [{"price": 10.0, "is_advertised": false, "is_campaign": false,
              "starting_at": "2026-01-01T00:00:00+00:00", "ending_at": "2099-12-31T00:00:00+00:00",
              "max_quantity": null, "price_over_max_quantity": null, "deposit": null,
              "compare_unit": "ltr", "compare_unit_price": 10.0}],
  "temperature_zone": "refrigerated_5_degrees_celsius"
}
```

### 21. `GET v3/products` — Afprøvet

Pagineret liste over alle varer (godt 4.000 ved afprøvningen). Kræver ikke login.

| Parameter | Type | Beskrivelse | Status |
|---|---|---|---|
| `per_page`, `page` | heltal | Paginering. | Afprøvet |
| `sort` | tekst | `-created_at`, `-popularity`, `title` eller `department_order` (appens fire værdier). | `-popularity` afprøvet |
| `include` | tekst | `department` lægger afdelingen på hver vare. | Afprøvet |
| `filter[is_advertised]` | bool | `true` giver kun avisvarer (ugens tilbud). | Afprøvet |
| `filter[age_restricted]` | bool | `false` udelader aldersbegrænsede varer. | Afprøvet (sammen med ovenstående) |
| `filter[department]` | heltal | Findes i appens kode, men **serveren svarede 400 `InvalidFilter`**. | Afprøvet — virker ikke |
| `filter[category]` | heltal | Som ovenfor: 400 `InvalidFilter` (testet sammen med `filter[labels]`). | Afprøvet — virker ikke |
| `filter[labels]` | tekst | Findes i appens kode. Kun testet sammen med `filter[category]`, så det vides ikke, om den virker alene. | Uafklaret |

Appen bruger selv kun to kombinationer: populære varer (`sort=-popularity`, ingen
aldersbegrænsede) og avisvarer (`filter[is_advertised]=true`, `include=department`).
Avisvarerne er dermed den nemmeste vej til "ugens tilbud" som data:

```
GET /api/v3/products?filter[is_advertised]=true&include=department&per_page=100&page=1
```

### 22. `GET v3/products/{id}` — Afprøvet (bruges ikke af appen)

Én vare som `{"data": {…}}` med samme felter som i `v3/products`. Endpointet er ikke fundet i
appens kode, men svarede 200 ved afprøvning.

### 23. `GET v3/departments` — Afprøvet (bruges ikke af appen)

Afdelinger (15 ved afprøvningen). Ikke fundet i appens kode — appen får afdelinger og kategorier
fra det samlede katalog.

Felter: `id`, `name`, `slug`, `important_information` (HTML), `products_last_modified_at`
(ISO 8601). Med `include=categories` får hver afdeling desuden `categories[]` med `id`, `name`,
`slug`, `important_information`, `is_hidden`. `per_page` og `page` virker som ellers.

### 24. `GET v3/departments/{department_id}/categories/{category_id}/products` — Afprøvet

Varerne i én kategori. Det er sådan, appen henter varer pr. kategori (i stedet for filtrene på
`v3/products`). Query: `per_page`, `page`. Id'erne er v3-id'erne (kategoriens `id_v3` i det gamle
katalog). Svaret er en v3-vareliste.

### 25. `GET v3/product-barcode/{barcode}` — Afprøvet

Slår en stregkode (EAN) op — bruges af appens scanner.

Query: `store_id` (heltal, valgfri).

Svar:

```json
{"data": {"name": "EKSEMPELVARE", "product": {"id": 11111},
          "pricing": {"price": 10.0, "max_quantity": null, "store": null}}}
```

`product.id` er vare-id'et; `pricing` har samme felter som i det gamle katalog, men kun en
delmængde er udfyldt.

---

## Varesøgning

### 26. `GET search/products` — Afprøvet

Appen søger mod REMA's eget API — der er ingen separat søgetjeneste (ingen Algolia eller
lignende) i appen. Endpointet ligger direkte under `/api/` uden versionspræfiks og kræver ikke
login:

```
GET https://api.digital.rema1000.dk/api/search/products?query=mælk&per_page=20&page=1
```

| Parameter | Type | Beskrivelse | Status |
|---|---|---|---|
| `query` | tekst | Søgeteksten. | Afprøvet |
| `per_page`, `page` | heltal | Paginering. | Afprøvet |
| `filter[is_advertised]` | bool | I appens kode; appen sender den ikke ved almindelig søgning. | Kun testet sammen med `filter[department]`, som gav 400 |
| `filter[department]` | heltal | I appens kode. Serveren svarede 400 `InvalidFilter`. | Afprøvet — virker ikke |
| `filter[category]`, `filter[labels]` | heltal, tekst | I appens kode; ikke afprøvet her. | Set i appens kode |

Svaret er en v3-vareliste med de udvidede felter (`department`, `category`, `barcodes`,
`declaration` m.fl.) og almindelig paginering. En søgning på et almindeligt ord gav 79 træffere.

Ud over serversøgningen har det gamle katalog `search_words` pr. vare, og appen har en lokal
kopi af kataloget; scanneren bruger stregkodeopslaget (endpoint 25).

Før brugeren skriver noget, viser søgeskærmen blokke, der er styret af CMS-indholdet
(`preSearchScreen`, se endpoint 38): anbefalinger til den aktive liste (endpoint 8), "du plejer
at købe" (endpoint 15) og populære varer (endpoint 21 med `sort=-popularity`).

---

## Kampagner og nyhedsbreve

### 27. `GET v1/campaigns` — Afprøvet

Kampagnebannere, der vises for alle. Rå liste.

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | heltal | |
| `priority` | heltal | Rækkefølge. |
| `type` | tekst | Hvor banneret vises. Appen kender `shopping_list_banner`, `available_jobs_list_banner` og `catalog_list_banner` (formodet skrivemåde); svaret ved afprøvningen havde værdien `available_jobs_list`. |
| `codename` | tekst | Appen genkender kun `go_to_offers` (formodet skrivemåde); andre værdier behandles som ukendte. |
| `banner_text`, `subtitle` | tekst | Tekster. |
| `web_banner_text` | tekst | Set i svaret; læses ikke af appen. |
| `expires_at` | tekst | Udløbsdato som `dd.mm.åååå`. |
| `image` | tekst eller null | Billed-URL. |
| `link` | tekst | Link, der åbnes ved tryk. |
| `is_dismissable` | bool | I appens model; var ikke med i det sete svar. |

Det ene element, der kom tilbage ved afprøvningen, var en gammel driftsmeddelelse — endpointet
bruges altså til bannere og beskeder, ikke til egentlige varetilbud. Varetilbud findes via
`filter[is_advertised]` (endpoint 21) og tilbudsavisen.

### 28. `GET v1/user/campaigns` — Set i appens kode

Samme form som endpoint 27, men for den indloggede bruger (kræver login).

### 29. `GET v3/newsletters` — Afprøvet

De nyhedsbreve, man kan tilmelde sig (fire ved afprøvningen). Appen henter med `per_page=100`.
Felter: `id` (heltal), `name`, `description`.

### 30–32. `v3/users/{user_id}/newsletter-subscriptions` — Set i appens kode

Ligger på grænsen til konto-området.

- `GET …?per_page=100` — brugerens tilmeldinger. Element: `id` (tilmeldingens id) og
  `newsletter` (`id`, `name`, `description`).
- `POST …` med body `{"newsletter_id": <heltal>}` — tilmeld. Svar: `{"data": {tilmelding}}`.
- `DELETE …/{newsletter_subscription_id}` — afmeld. Bemærk, at id'et er tilmeldingens, ikke
  nyhedsbrevets.

### 33. `GET v1/settings` — Afprøvet

Globale indstillinger. Felter, appen læser: `closed_android`, `closed_reason`,
`closed_order_button_text`, `competition_agreement_active`,
`current_competition_agreement_version`, `current_user_agreement_version`. Samme objekt følger
med i polling-svaret. Hører primært til konto-området.

---

## Tilbudsavisen (Tjek)

Den ugentlige avis leveres ikke af REMA's eget API, men af Tjek (tidligere eTilbudsavis/ShopGun).
Appen taler med `https://squid-api.tjek.com` og sender en API-nøgle i headeren `x-api-key`
sammen med `content-type: application/json; charset=utf-8`. Nøglen ligger i appen og gengives
ikke her. Ingen af Tjek-kaldene er afprøvet i denne kortlægning.

### 34. `GET /v2/catalogs?dealer_id={id}` — Set i appens kode

Aktive aviser for en forhandler. Appen sender REMA 1000's forhandler-id hos Tjek (`11deC`).

Felter pr. avis (fra appens model): `id`, `label`, `run_from`, `run_till`, `page_count`,
`offer_count`, `dealer_id`, `store_id`, `all_stores`, `types`, `dimensions{width, height}`,
`images{thumb, view, zoom}`, `branding{name, color, logo, website, description}`.

### 35. `GET /v2/offers/{offer_id}` — Set i appens kode

Ét tilbud fra avisen. Felter: `id`, `heading`, `description`, `catalog_id`, `catalog_page`,
`catalog_view_id`, `dealer_id`, `store_id`, `run_from`, `run_till`, `publish`,
`pricing{price, pre_price, currency}`,
`quantity{pieces{from, to}, size{from, to}, unit{symbol, si{symbol, factor}}}`,
`images{thumb, view, zoom}`, `links{webshop}`, `branding`.

### 36. `POST /v4/rpc/get_offer_products` — Set i appens kode

Finder varerne bag et tilbud. Body: `{"id": "<offer_id>"}`.

Svaret har `offer_products[]`, hvor hvert element bl.a. har `id`, `name`, `external_id`,
`is_active`, `images` og et indlejret `product`. Appen tolker `external_id` som et heltal og slår
det op som **REMA-vare-id** i sit lokale katalog — det er broen fra avisen til en vare, der kan
lægges på indkøbslisten (med `source` `android_newspaper` eller `android_newspaper_list`).
Tilbud uden `external_id` vises kun med navn.

### 37. Webvisning af avisen — Set i appens kode

Selve bladringen sker i en webvisning, ikke via et API:

```
https://publication-viewer.tjek.com/v1/embeds/<publication_id>?enable_zoom=true&api_key=<nøgle>&context=webview&view_direction=horizontal&view_mode=paged&ui=regular
```

`publication_id` er avisens `id` fra endpoint 34.

---

## Forsideindhold ("entities")

Forsiden, skærmen før søgning og opskriftssektionen er redaktionelt styret fra et CMS (billed-URL'er
peger på Contentful). Indholdet hentes fra en særskilt base:
`https://api.digital.rema1000.dk/api/rema1000dk/`. Ingen af kaldene kræver login.

### 38. `GET rema1000dk/entities` — Afprøvet

| Parameter | Type | Beskrivelse | Status |
|---|---|---|---|
| `filter[type]` | tekst | `appConfiguration`, `recipe` eller `recipeTag` (de tre typer, appen spørger på). | Alle tre afprøvet |
| `filter[slug]` | tekst | Slå én opskrift eller ét tag op på slug. | Set i appens kode |
| `filter[tags.sys.id]` | tekst | Opskrifter med et bestemt tag (tag'ets `id`). | Set i appens kode |
| `per_page`, `page` | heltal | Paginering. | Afprøvet |
| `sort` | tekst | Samme værdier som på `v3/products`: `-created_at`, `-popularity`, `title`. | Set i appens kode |

Alle elementer har samme ydre form: `id` (tekst), `type` (tekst), `fields` (objekt, afhænger af
typen), `created_at`, `updated_at`. Elementer kan være indlejret i hinanden.

**`filter[type]=appConfiguration`** giver ét element på omkring 100 kB med tre skærme i
`fields`: `mainScreen` (forsiden), `preSearchScreen` (før søgning) og `recipesScreen`
(opskrifter). Hver skærm er en `appScreen` med `fields.title` og `fields.content[]` — en
ordnet liste af komponenter. Typer set i svaret:

| `type` | `fields` | Betydning |
|---|---|---|
| `staticComponent` | `title`, `variant` | Pladsholder for en blok, som appen selv fylder med data. Varianter set: `personalization_ad`, `delivery_status`, `active_shopping_list`, `favorite_products`, `active_publications`, `inspirational_products`, `popular_products`, `active_shopping_list_recommended_products`, `frequently_bought_products`. |
| `informationBox` | `title`, `text`, `image`, `cta`, `variant` | Infoboks. `variant` set: `neutral`; appen kender desuden standard-, advarsels- og kritisk-varianter. `cta` er en `externalLink` med `text` og `link`. |
| `productCollection` | `title`, `slug`, `subtitle`, `text` (HTML), `image`, `source`, `color`, `products[]` | Redaktionel varesamling (tema). `products` er fulde v3-vareobjekter; `color` har farvepar som `{light_vibrant: {background, foreground}}`. |
| `search` | `title`, `placeholder`, `content`, `searchResultType` | Søgefelt på opskriftsskærmen. |
| `recipeTagGroup` | `title`, `tag` | En række opskrifter med ét tag. |
| `recipeMultiTagGroup` | (ikke undersøgt nærmere) | Række baseret på flere tags. |
| `recipeThemeGroup` | `title`, `tags[]` | "Opskrifter efter tema". |
| `popularRecipes` | `title` | Populære opskrifter. |
| `allRecipes` | `title` | Alle opskrifter. |
| `Asset` | `id`, `mime`, `name`, `url`, `width`, `height` | Billede (ingen `fields`-indpakning). |

`appConfiguration` er altså en opskrift på, hvilke blokke skærmene består af, og hvilke af de
øvrige endpoints appen kalder for at fylde dem. Varesamlingerne er det eneste sted, hvor
redaktionelt udvalgte varer ("Meget mere weekend" og lignende) findes som data.

**`filter[type]=recipe`** og **`recipeTag`**: se opskrifter nedenfor.

---

## Opskrifter

Opskrifterne ligger i samme CMS. Appen linker desuden til webudgaven på
`https://madogdrikke.rema1000.dk/opskrifter/<slug>`.

### Opskrift-objektet

Set i rigtige svar (`type: "recipe"`), `fields`:

| Felt | Type | Beskrivelse |
|---|---|---|
| `title` | tekst | Titel. |
| `slug` | tekst | Bruges i web-URL og til opslag med `filter[slug]`. |
| `image` | Asset | Billede. |
| `tags[]` | liste af `recipeTag` | Tags med `fields{title, slug, description, image}`. |
| `popularity` | heltal | Popularitet. |
| `allProductsAvailable` | bool | Om alle koblede varer kan købes. |
| `allowSearchEngineIndexing` | bool eller null | Kun relevant for web. |
| `customForm.servings` | `{type, amount}` | Antal portioner/stk. |
| `customForm.totalTime` | heltal | Samlet tid (formodentlig minutter). |
| `customForm.ingredientGroups[]` | `{id, name, ingredients[]}` | Ingredienser i grupper. |
| `customForm.preparationGroups[]` | `{id, name, steps[{id, step}]}` | Fremgangsmåde. |
| `customForm.preparationTextBefore`, `preparationTextAfter` | tekst | Tekst før/efter fremgangsmåden. |

Ingrediens: `id`, `ingredient` (navn), `amountOfContent`, `unitOfContent`,
`isExcludedFromShoppingList` og `digitalProduct`. `digitalProduct` er koblingen til en vare:
`id`, `title`, `description`, `amount`, `amount_of_content`, `unit_of_content`, `price`,
`is_basic_ingredient`, `created_at` og `active_product` — et fuldt v3-vareobjekt, hvis `id` kan
lægges på indkøbslisten (appen bruger `source: android_recipe`).

### Opslag via `rema1000dk/entities` (endpoint 38) — Afprøvet

- `filter[type]=recipe&per_page=…&page=…` — alle opskrifter (692 ved afprøvningen), evt. med `sort`.
- `filter[type]=recipe&filter[tags.sys.id]=<tag-id>` — opskrifter med et tag (set i appens kode).
- `filter[type]=recipe&filter[slug]=<slug>` — én opskrift (set i appens kode).
- `filter[type]=recipeTag` — alle tags (30 ved afprøvningen).

### 39. `GET rema1000dk/featured-recipes` — Afprøvet (kun fejlsvar)

Opskrifterne i en fremhævet gruppe, fx blokken "Populære opskrifter".

Query: `filter[group_id]` (tekst, påkrævet). Uden parameteren svarede serveren 400 med en
valideringsfejl på `filter.group_id`, hvilket bekræfter endpoint og parameternavn. Efter appens
kode er værdien id'et på den CMS-komponent, gruppen hører til, og svaret er en liste af
opskrift-elementer som ovenfor. Et vellykket kald er ikke afprøvet.

### 40. `GET search/recipes` — Afprøvet

Opskriftssøgning; ligger ved siden af varesøgningen under `/api/` og kræver ikke login.

| Parameter | Type | Beskrivelse | Status |
|---|---|---|---|
| `query` | tekst | Søgetekst. | Afprøvet |
| `per_page`, `page` | heltal | Paginering. | Afprøvet |
| `sort` | tekst | `title`, `-created_at` eller `-popularity`; udelades for relevans. | Set i appens kode |

Svaret er `{"data": [opskrift…], "meta": {"pagination": …}}` med fulde opskrift-elementer
(inklusive ingredienser og koblede varer), så svarene er store — omkring 35 kB pr. opskrift.

### 41–43. Favoritopskrifter — Set i appens kode

Kræver login.

- `GET v3/users/{user_id}/favorite-recipes?fields=id&per_page=…&page=…` — kun id'er på
  favoritopskrifterne. Svar: `data[]` med `id` (tekst) samt `meta`.
- `GET v3/users/{user_id}/favorite-recipes?include=instructions&per_page=…&page=…` —
  favoritopskrifterne som fulde opskrift-elementer.
- `POST v3/users/{user_id}/favorite-recipes` med body `{"recipe_id": "<opskriftens id>"}` —
  tilføj. Svaret læses ikke.
- `DELETE v3/users/{user_id}/favorite-recipes/{recipe_id}` — fjern. Svaret læses ikke.

`recipe_id` er opskrift-elementets `id` (en tekststreng fra CMS'et), ikke et tal.

---

## Billeder og links

- Varebilleder: `https://rema-product-images.digital.rema1000.dk/<vare-id>/<n>-<small|medium|large>-<hash>.webp`
  (URL'erne står i `images` på varen; byg dem ikke selv).
- Mærkeikoner: `https://static-assets.digital.rema1000.dk/product/labels/<id>-64.webp`.
- CMS-billeder: URL'er i `Asset.url`. Appen har desuden `https://content-images.digital.rema1000.dk/`
  som base for opskriftsbilleder; hvordan de to hænger sammen, er ikke undersøgt.
- Dybe links, som appen åbner: `shop.rema1000.dk/varer/…` (vare), `…/opskrifter/…` (opskrift,
  også på `madogdrikke.rema1000.dk`), `…/shopping-lists/…` (indkøbsliste) og
  `…/shopping-list-invitation-link/…` (invitation).

---

## Uafklaret

- **Polling: fuldt svar eller ændringer?** Det er ikke fastslået, om `polling` med et nyere
  `unixtime` returnerer alle lister eller kun de ændrede, og om serveren holder forbindelsen åben
  (ægte long-poll) eller svarer med det samme. Enheden for `wait` er udledt af appens kode
  (millisekunder), ikke af dokumentation.
- **`warning` og `bags`** på en liste samt `unit` og `total_price` på en linje læses ikke af
  appen; betydningen af de to første er ukendt.
- **Opret, omdøb, slet og afkrydsning via sync** er udledt af appens kode og ikke afprøvet. Det
  samme gælder, hvordan serveren svarer på en ny liste (hvordan `offlineId` kobles til det nye `id`).
- **Invitationer**: hvad `v1/shoppinglist/{id}/invite` præcis udløser (mail?), hvordan en
  modtager accepterer via API'et, hvordan `approved` skifter, og om et medlem kan fjernes af
  listens ejer. Invitationslinkets format er kun set i koden.
- **`PATCH v2/shoppinglists/{id}`**: kun `primary` er set. Om `primary: false` eller andre felter
  accepteres, er ukendt.
- **`frequently-bought-products` gav 403** med login. Mulige forklaringer er manglende samtykke
  til personalisering eller en funktion, der ikke er slået til for kontoen — begge dele er gæt.
- **`recommended-products` gav tom liste**; uvist om det skyldes listens indhold eller samme
  forhold som ovenfor.
- **Filtrene `filter[department]`, `filter[category]` og `filter[labels]`** findes i appens kode
  for både `v3/products` og `search/products`, men serveren afviste `department` og `category`
  med `InvalidFilter`. Enten forventes et andet værdiformat (fx slug), eller også er filtrene
  fjernet på serveren; appen bruger dem ikke i praksis. `filter[labels]` er ikke testet alene.
- **`prices`-rækkefølgen** (første element = gældende pris) er en iagttagelse, ikke en regel.
  Der er heller ikke set et eksempel med pant eller `consumption_*` udfyldt.
- **Butiksspecifikke priser**: `pricing.store` og `store_id` på stregkodeopslaget antyder
  priser pr. butik, men kun katalogbutik `1` er set.
- **`v3/products/{id}` og `v3/departments`** virker, men bruges ikke af appen; de kan derfor
  ændres uden, at appen berøres.
- **`v1/user/campaigns`**: forskellen fra `v1/campaigns` i praksis er ikke set. Skrivemåden for
  `type`- og `codename`-værdierne i appen er udledt af enum-navne og passer ikke helt med den
  ene værdi, der er set i et rigtigt svar.
- **Tjek-API'et** er ikke afprøvet; feltlisterne er appens modeller. Det er ikke undersøgt, om
  nøglen er bundet til appen, eller hvilke vilkår Tjek har for brug.
- **`featured-recipes`**: et vellykket kald mangler; hvilken id der præcis skal bruges som
  `group_id`, er udledt af koden.
- **`recipeMultiTagGroup`** og de øvrige infoboks-varianter er kun set som typenavne.
- **Bonus/personlige tilbud**: intet sådant endpoint er fundet i appen. Komponenten
  `personalization_ad` på forsiden ser ud til at være en opfordring til at slå personalisering
  til, ikke et tilbuds-API.
