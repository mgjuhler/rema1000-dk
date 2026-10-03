# Konto, login og brugerindstillinger

Kortlægning af den del af REMA 1000-appens backend-API, der handler om *hvem brugeren er*:
login, profil, samtykker, nyhedsbreve, push, bankkonto og app-konfiguration.

Kilde: Android-appen `dk.iroots.rema1000` version 6.9.0 (dekompileret) samt nogle få
GET-kald uden login mod det rigtige API. Der er ikke logget ind, og der er ikke sendt
POST/PATCH/DELETE under denne kortlægning.

**Statusmarkører**

- **Afprøvet** — kaldt mod det rigtige API (kun kald uden login), eller verificeret
  tidligere i projektet (OAuth-flowet og `GET v1/user`).
- **Set i appens kode** — fundet i den dekompilerede app, ikke kaldt. Felter og typer
  stammer fra appens modeller; serveren kan sende flere felter, end appen læser.

## Grundlæggende

| | |
|---|---|
| Base-URL | `https://api.digital.rema1000.dk/api/` |
| Godkendelse | `Authorization: Bearer <access_token>` (OAuth2 authorization code + PKCE) |
| `client_id` | `rema1000-app` |
| Redirect | `dk.rema1000.vigo://logincallback` |
| Login-side | `login.rema1000.dk` |
| Format | JSON, medmindre andet er nævnt (enkelte kald er form-url-encoded) |

**HTTP-metoder.** Appens PATCH/PUT-annotation er afklaret ved at læse Retrofits
request-fabrik i appen: den annotation, der bruges på alle "opdatér"-kald i dette
dokument, er bundet til metoden `PATCH`. Appen har også en PUT-annotation, men den bruges
ikke på noget endpoint i appen. Alle opdateringer herunder er altså **PATCH**.

**Svar-konvolutter.** v3-endpoints pakker svaret ind:

- Enkelt objekt: `{"data": {...}}`
- Liste: `{"data": [...], "meta": {"pagination": {...}}}` hvor `pagination` har
  `current_page`, `from`, `last_page`, `per_page`, `to`, `total` (int). Det rigtige API
  sender desuden `links` (`first`, `last`, `prev`, `next`) og `path` (afprøvet).
- v1-endpoints svarer med objektet/listen direkte uden konvolut.

**Fejl.** Beskyttede kald uden token giver 401 (afprøvet):

```json
{"error_code": 101, "translate": false, "error": "access_denied",
 "error_message": "The resource owner or authorization server denied the request",
 "status_code": 401}
```

`identity-verification/*` bruger et andet fejlformat (afprøvet uden token, 401):
`{"message": "An error occured", "error_type": "Unauthorized"}`.

**Bruger-id.** `v3/users/{user_id}/…` kræver brugerens numeriske `id`, som fås fra
`GET v1/user`.

## Oversigt

| Metode | Sti | Formål | Status |
|---|---|---|---|
| GET | `oauth2/authorize` | Starter login (browser) | Afprøvet |
| POST | `oauth2/token` | Veksler kode til tokens | Afprøvet |
| POST | `oauth2/token/refresh` | Fornyer tokens | Afprøvet |
| POST | `v1/oauth/logout` | Logger ud og afmelder push | Set i appens kode |
| GET | `identity-verification/token` | Henter engangstoken til MitID-validering | Set i appens kode |
| GET | `identity-verification/login` | MitID-side, åbnes i browser | Set i appens kode |
| GET | `v1/user` | Henter profilen | Afprøvet |
| POST | `v1/user` | Opdaterer profil og indstillinger | Set i appens kode |
| POST | `v1/user/photo` | Sætter profilbillede | Set i appens kode |
| POST | `v1/user/delete` | Sletter kontoen | Set i appens kode |
| POST | `v1/user/gdpr-export` | Bestiller eksport af persondata | Set i appens kode |
| POST | `v1/user/friends/emails` | Finder brugere ud fra e-mails | Set i appens kode |
| POST | `v1/user/friends/numbers` | Finder brugere ud fra telefonnumre | Set i appens kode |
| GET | `v1/user/campaigns` | Kampagnebannere til den indloggede bruger | Set i appens kode |
| GET | `v3/users/{user_id}` | Udvidet profil (type, notifikationer, forening, bankkonto) | Set i appens kode |
| PATCH | `v3/users/{user_id}` | Ændrer notifikationer, kørebog, fjerner bankkonto | Set i appens kode |
| POST | `v3/users/{user_id}/addresses` | Opretter adresse | Set i appens kode |
| PATCH | `v3/users/{user_id}/addresses/{address_id}` | Ændrer adresse | Set i appens kode |
| DELETE | `v3/users/{user_id}/addresses/{address_id}` | Sletter adresse | Set i appens kode |
| GET | `v3/policies` | Politikker/samtykker og deres gældende version | Afprøvet |
| POST | `v3/users/{user_id}/policy-versions` | Giver samtykke til en politikversion | Set i appens kode |
| DELETE | `v3/users/{user_id}/policy-versions/{policy_version_id}` | Trækker samtykke tilbage | Set i appens kode |
| GET | `v3/newsletters` | Liste over nyhedsbreve | Afprøvet |
| GET | `v3/users/{user_id}/newsletter-subscriptions` | Brugerens tilmeldinger | Set i appens kode |
| POST | `v3/users/{user_id}/newsletter-subscriptions` | Tilmelder nyhedsbrev | Set i appens kode |
| DELETE | `v3/users/{user_id}/newsletter-subscriptions/{newsletter_subscription_id}` | Afmelder nyhedsbrev | Set i appens kode |
| POST | `v1/push/register` | Registrerer enhedens push-token | Set i appens kode |
| GET | `v3/banks` | Liste over banker (til udbetalingskonto) | Set i appens kode |
| POST | `v3/users/{user_id}/bank-accounts` | Opretter bankkonto | Set i appens kode |
| PATCH | `v3/users/{user_id}/bank-accounts/{account_id}` | Verificerer bankkonto | Set i appens kode |
| GET | `v1/settings` | Global app-konfiguration | Afprøvet |
| GET | `v3/feature-flags` | Feature flags | Afprøvet |
| GET | `v1/campaigns` | Kampagnebannere uden login | Afprøvet |
| GET | `v3/users/{user_id}/routes` | Kørebog: ruter | Set i appens kode |
| GET | `v3/users/{user_id}/routes/{route_id}` | Kørebog: én rute | Set i appens kode |
| PATCH | `v3/users/{user_id}/routes/{route_id}` | Kørebog: ændrer transporttype | Set i appens kode |
| POST | `v3/users/{user_id}/routes/{route_id}/trips` | Kørebog: opretter tur | Set i appens kode |
| PATCH | `v3/users/{user_id}/routes/{route_id}/trips/{trip_id}` | Kørebog: ændrer note på tur | Set i appens kode |
| POST | `v3/batch` | Flere API-kald i ét | Set i appens kode |

39 endpoints: 9 afprøvet, 30 set i appens kode.

---

## 1. Login (OAuth2 + PKCE)

### GET `oauth2/authorize` — Afprøvet

Åbnes i en browser (appen bruger en Custom Tab). Sender brugeren til login-siden på
`login.rema1000.dk` og ender med et redirect til `redirect_uri` med `code` og `state`.

Query-parametre, som appen sender:

| Navn | Værdi |
|---|---|
| `client_id` | `rema1000-app` |
| `redirect_uri` | `dk.rema1000.vigo://logincallback` |
| `state` | tilfældig streng (appen: 64 tilfældige bytes, base64url uden padding) |
| `code_challenge` | base64url(SHA-256(`code_verifier`)) uden padding |
| `code_challenge_method` | `S256` (appen falder tilbage til `plain`, hvis SHA-256 mangler) |
| `scope` | tom streng |
| `response_type` | `code` |
| `theme` | `light` |
| `screen` | valgfri; `register` åbner opret-bruger-siden i stedet for login |

### POST `oauth2/token` — Afprøvet

Veksler autorisationskoden til tokens. Kræver ikke login.

Body (JSON):

| Felt | Type | Bemærkning |
|---|---|---|
| `grant_type` | string | `authorization_code` |
| `client_id` | string | `rema1000-app` |
| `code` | string | koden fra redirectet |
| `code_verifier` | string | PKCE-verifier |
| `redirect_uri` | string | samme som i authorize-kaldet |

Svar:

```json
{"tokens": {"access_token": "FAKE-ACCESS", "refresh_token": "FAKE-REFRESH",
            "token_type": "Bearer", "expires_in": 3600}}
```

`access_token`, `refresh_token`, `token_type` er strenge, `expires_in` er int (sekunder).
Tallet 3600 er et eksempel, ikke en målt værdi.

### POST `oauth2/token/refresh` — Afprøvet

Fornyer tokens. Refresh-tokenet roterer: det gamle kan ikke bruges igen, og det nye skal
gemmes.

Body (JSON): `client_id` (string), `refresh_token` (string), `grant_type` (string).
Bemærk: appen sender `grant_type` = `authorization_code` også her. Klienten i dette repo sender
`refresh_token`, og det er den form, der er afprøvet (se `API.md`).

Svar: samme `tokens`-objekt som `oauth2/token`.

### POST `v1/oauth/logout` — Set i appens kode

Logger ud på serveren og afmelder enhedens push-registrering. Kræver login.

Body (JSON):

| Felt | Type | Bemærkning |
|---|---|---|
| `device_token` | string eller null | push-tokenet (FCM), som enheden blev registreret med |
| `push_id` | int | id fra `v1/push/register`; appen sender `-1`, hvis den ikke har et |

Svar: appen læser ikke noget indhold. Om kaldet også ugyldiggør access/refresh-tokens på
serveren, fremgår ikke af appen.

---

## 2. MitID / identitetsvalidering

Bruges til aldersbegrænsede varer, til "shoppere" (Vigo) og til DAC7-oplysninger.
Felterne hedder stadig `nemid` i API'et (`is_nemid_validated`,
`is_nemid_validation_required` på profilen).

Flow, som appen gør det:

1. `GET identity-verification/token` med de fire retur-URI'er → engangstoken.
2. Åbn `identity-verification/login?token=<token>&platform=android` i en browser.
3. MitID gennemføres på websiden, som til sidst sender brugeren til en af retur-URI'erne.
4. Appen henter profilen igen og læser `is_nemid_validated`.

### GET `identity-verification/token` — Set i appens kode

Kræver login. (Uden token svarer det 401 i det afvigende fejlformat — afprøvet.)

Query-parametre:

| Navn | Type | Værdi i appen |
|---|---|---|
| `redirect_uri` | string | `dk.rema1000.vigo://apps/rema1000/user/identity/verified` |
| `failed_uri` | string | `dk.rema1000.vigo://apps/rema1000/user/identity/failed` |
| `cancelled_uri` | string | `dk.rema1000.vigo://apps/rema1000/user/identity/cancelled` |
| `resume_uri` | string | `https://shop.rema1000.dk/apps/rema1000/user/resume` |

URL-skemaet `dk.rema1000.vigo` står i appens ressourcer og er det samme som i login-redirectet.

Svar: `{"token": "FAKE-MITID-TOKEN"}` (string).

### GET `identity-verification/login` — Set i appens kode

Ikke et API-kald, men en webside, der åbnes i browser. Query: `token` (fra kaldet ovenfor)
og `platform` (`android`). Appens tekster viser, at valideringen kan ende med bl.a.
"allerede i brug af anden konto", "tidligere brugt som virksomhed", "bopæl kan ikke
bestemmes" og "under aldersgrænsen"; hvordan de udfald signaleres teknisk, er ikke
kortlagt.

---

## 3. Profil (`v1/user`)

### GET `v1/user` — Afprøvet

Henter den indloggede brugers profil. Ingen parametre.

Svarfelter (ingen konvolut):

| Felt | Type | Bemærkning |
|---|---|---|
| `id` | int | bruges som `user_id` i v3-stierne |
| `name` | string | låses efter MitID-validering |
| `email` | string | |
| `phone_country_code` | string eller null | |
| `phone_number` | string eller null | |
| `photo` | string eller null | formentlig URL til profilbillede |
| `birthday` | dato eller null | |
| `rating_float` | float eller null | brugerens bedømmelse (Vigo) |
| `favorite_meta_store` | int eller null | id på favoritbutik |
| `favorite_meta_store_address` | string eller null | |
| `transport_method` | enum eller null | appens værdier: `WALK`, `BIKE`, `CAR`, `DISTANCE_LOCATION`; stavemåden i JSON er ikke bekræftet |
| `accepted_user_agreement_version` | int | sammenlignes med `current_user_agreement_version` i `v1/settings` |
| `accepted_competition_agreement_version` | int | tilsvarende for konkurrencebetingelser |
| `approved_policy_gdpr` | bool | |
| `is_nemid_validated` | bool | MitID gennemført |
| `is_nemid_validation_required` | bool | |
| `acceptNotifications` | bool | bemærk camelCase |
| `enable_replacement_items` | bool | erstatningsvarer tilladt (grænser til levering) |
| `settings.is_delivery` | bool | om brugeren er "shopper" (leverer for andre) |
| `settings.addresses` | liste af adresser | se adresseobjektet i afsnit 5 |

Eksempel (opdigtede værdier, forkortet):

```json
{"id": 123456, "name": "Test Testesen", "email": "test@example.invalid",
 "phone_country_code": "45", "phone_number": "00000000", "photo": null,
 "favorite_meta_store": 1, "accepted_user_agreement_version": 1,
 "approved_policy_gdpr": true, "is_nemid_validated": false,
 "acceptNotifications": true,
 "settings": {"is_delivery": false, "addresses": []}}
```

### POST `v1/user` — Set i appens kode

Opdaterer profilen. Appen sender kun de felter, der skal ændres (resten udelades), og får
hele profilen tilbage i samme form som `GET v1/user`. Metoden er POST, ikke PATCH.

Body-felter (alle valgfrie):

| Felt | Type | Bruges til |
|---|---|---|
| `name` | string | navn |
| `email` | string | e-mail |
| `phone_country_code` | string | |
| `phone_number` | string | |
| `acceptNotifications` | bool | push/notifikationer til og fra |
| `approved_policy_gdpr` | bool | accept af persondatapolitik |
| `update_accepted_user_agreement_version` | bool | `true` = "jeg accepterer den gældende brugeraftale" |
| `update_accepted_competition_agreement_version` | bool | tilsvarende for konkurrencebetingelser |
| `enable_replacement_items` | bool | erstatningsvarer |
| `favorite_meta_store` | int | favoritbutik |
| `transport_method` | enum | se ovenfor |
| `settings.is_delivery` | bool | `true` opgraderer brugeren til shopper |

Appen bruger kaldet i disse kombinationer: færdiggør oprettelse (navn, telefon,
samtykker), ret profil (navn/e-mail/telefon), accepter GDPR, accepter brugeraftale,
notifikationer til/fra, erstatningsvarer til/fra, vælg favoritbutik, vælg transportmiddel,
bliv shopper.

### POST `v1/user/photo` — Set i appens kode

Sætter profilbilledet. Body: `{"photo": "<string>"}`. Appen komprimerer billedet til JPEG
og sender det som tekst; at det er base64, er en rimelig antagelse, men kodningen er ikke
læst direkte i koden. Appen læser intet svarindhold og henter profilen igen bagefter.

### POST `v1/user/delete` — Set i appens kode

Sletter den indloggede brugers konto. Ingen body, intet svarindhold læses. **Destruktivt
og sandsynligvis uigenkaldeligt** — må ikke kaldes i test.

### POST `v1/user/gdpr-export` — Set i appens kode

Bestiller en eksport af brugerens persondata. Ingen body, intet svarindhold læses. Hvordan
eksporten leveres (formentlig e-mail), fremgår ikke af appen.

### POST `v1/user/friends/emails` og `v1/user/friends/numbers` — Set i appens kode

Slår andre brugere op ud fra kontaktoplysninger (bruges til at dele indkøbslister — grænser
til indkøbsliste-området). Body er **form-url-encoded**, ikke JSON:

- `friends/emails`: gentaget felt `emails[]` (string)
- `friends/numbers`: gentaget felt `numbers[]` (string)

Svar: liste (uden konvolut) af brugere:

| Felt | Type |
|---|---|
| `id` | int |
| `name` | string |
| `email` | string |
| `phone_number` | string |
| `phone_country_code` | string |
| `photo` | string eller null |
| `approved` | bool |
| `is_self` | bool |
| `found_by_phone_number` | liste af string |

### GET `v1/user/campaigns` — Set i appens kode

Kampagnebannere målrettet den indloggede bruger. Samme objekt som `v1/campaigns`
(afsnit 9). Grænser til tilbud/indhold.

---

## 4. Udvidet profil (`v3/users/{user_id}`)

### GET `v3/users/{user_id}` — Set i appens kode

Path: `user_id` (int). Query: `include` — kommasepareret liste. Appen beder om
`sponsor-club,active_bank_account,pending_shopper_suspension,type`.

Svar `{"data": {...}}`:

| Felt | Type | Bemærkning |
|---|---|---|
| `id` | int | |
| `type` | enum | appen kender `Store` og `Customer`; stavemåden i JSON er ikke bekræftet |
| `is_driving_book_enabled` | bool | kørebog (shoppere) |
| `is_favorite_notification_enabled` | bool | e-mail, når favoritvarer er på tilbud |
| `is_favorite_push_notification_enabled` | bool | push, når favoritvarer er på tilbud |
| `sponsor_club` | objekt eller null | `id` (int), `name` (string), `invitation_code` (int) — forening, som shopperens aktivitet støtter |
| `active_bank_account` | objekt eller null | se afsnit 8 |
| `pending_shopper_suspension` | objekt eller null | `is_pending_suspension` (bool), `next_suspension_duration` (int) |

Bemærk forskellen: include-nøglen hedder `sponsor-club` (bindestreg), svarfeltet
`sponsor_club` (understreg).

### PATCH `v3/users/{user_id}` — Set i appens kode

Body (kun de felter, der ændres); svar som GET:

| Felt | Type | Bemærkning |
|---|---|---|
| `is_favorite_notification_enabled` | bool | tilbuds-e-mail om favoritter |
| `is_favorite_push_notification_enabled` | bool | tilbuds-push om favoritter |
| `is_driving_book_enabled` | bool | kørebog til/fra |
| `active_bank_account_id` | null | sendes som eksplicit `null` for at fjerne bankkontoen |

---

## 5. Adresser

Grænseområde til levering: adresserne er leveringsadresser, men ligger på profilen.
Adresser læses via `settings.addresses` i `GET v1/user`; der er ikke fundet et særskilt
GET-endpoint for dem.

Adresseobjekt: `id` (int), `street` (string), `postal` (string; appen accepterer også
`postal_code`), `city` (string), `country` (string), `description` (string eller null),
`latitude` (float), `longitude` (float), `is_primary` (bool; appen accepterer også
`primary`).

### POST `v3/users/{user_id}/addresses` — Set i appens kode

Body (JSON): `dawa_address_id` (string, adressens id fra DAWA/Danmarks Adressers Web API),
`description` (string, fx "2. sal, kode 1234"), `is_primary` (bool).
Svar: `{"data": <adresse>}`.

### PATCH `v3/users/{user_id}/addresses/{address_id}` — Set i appens kode

Body er **form-url-encoded**: `description` (valgfri string), `dawa_address_id` (valgfri
string). Svar: `{"data": <adresse>}`.

### DELETE `v3/users/{user_id}/addresses/{address_id}` — Set i appens kode

Ingen body, intet svarindhold læses.

Appen slår adresser op mod DAWA's `autocomplete`-endpoint (ekstern tjeneste, ikke REMA).

---

## 6. Politikker og samtykker

### GET `v3/policies` — Afprøvet

Liste over de politikker, brugeren kan/skal acceptere. Virker uden login.

Query:

| Navn | Type | Bemærkning |
|---|---|---|
| `include` | string | `current_version` uden login; appen sender `accepted_version,current_version`, når brugeren er logget ind |
| `per_page` | int | |

Svar `{"data": [...], "meta": {...}}`, hvert element:

| Felt | Type | Bemærkning |
|---|---|---|
| `type` | string | set: `gdpr`, `personalization`, `terms_of_service` |
| `name` | string | fx "Persondatapolitik" |
| `description` | string | |
| `url` | string | link til den fulde tekst |
| `revoke_title` | string eller null | overskrift i "træk tilbage"-dialogen |
| `revoke_description` | string eller null | |
| `is_revocable` | bool | |
| `current_version` | objekt | `id` (int), `description` (string) |
| `accepted_version` | objekt eller mangler | `id` (int), `accepted_at` (string, tidsstempel) — kun med login og `include=accepted_version`; ikke afprøvet |

Eksempel (forkortet, fra det rigtige svar):

```json
{"data": [{"type": "personalization", "name": "Personalisering",
           "description": "…", "url": "https://rema1000.dk/information/persondatapolitik",
           "revoke_title": "Er du sikker?", "revoke_description": "…",
           "is_revocable": true,
           "current_version": {"id": 4, "description": "Initial version"}}],
 "meta": {"pagination": {"current_page": 1, "last_page": 1, "per_page": 100, "total": 3}}}
```

Appen bruger `personalization` til at afgøre, om personlige anbefalinger må vises: ikke
accepteret, accepteret, eller "ny version afventer" (accepteret version ≠ gældende
version).

### POST `v3/users/{user_id}/policy-versions` — Set i appens kode

Giver samtykke. Body: `{"policy_version_id": 4}` (int — id'et fra `current_version.id`).
Intet svarindhold læses.

### DELETE `v3/users/{user_id}/policy-versions/{policy_version_id}` — Set i appens kode

Trækker et samtykke tilbage. Path: `user_id` (int), `policy_version_id` (int). Ingen body.
Ifølge politikkens egen tekst betyder tilbagetrækning af `terms_of_service`, at Vigo,
Køb & Hent og Scan Selv ikke kan bruges, og af `personalization`, at indkøbshistorik
slettes.

Ældre samtykkefelter findes desuden på `v1/user` (`approved_policy_gdpr`,
`accepted_user_agreement_version`, `accepted_competition_agreement_version`) og sættes via
`POST v1/user`.

---

## 7. Nyhedsbreve og notifikationer

### GET `v3/newsletters` — Afprøvet

Liste over nyhedsbreve, der kan tilmeldes. Virker uden login. Appen sender
`per_page=100`. Element: `id` (int), `name` (string), `description` (string).

```json
{"data": [{"id": 5, "name": "Næste uges tilbud og avisvarer", "description": "…"}],
 "meta": {"pagination": {"current_page": 1, "last_page": 1, "per_page": 100, "total": 4}}}
```

### GET `v3/users/{user_id}/newsletter-subscriptions` — Set i appens kode

Brugerens tilmeldinger. Appen sender `per_page=100`. Element: `id` (int — tilmeldingens
id, ikke nyhedsbrevets) og `newsletter` (objekt som ovenfor).

### POST `v3/users/{user_id}/newsletter-subscriptions` — Set i appens kode

Body: `{"newsletter_id": 5}` (int). Svar: `{"data": <tilmelding>}`.

### DELETE `v3/users/{user_id}/newsletter-subscriptions/{newsletter_subscription_id}` — Set i appens kode

Afmelder. Bemærk at stien bruger tilmeldingens id. Intet svarindhold læses.

### Øvrige notifikationsindstillinger

Der er ikke ét samlet endpoint. Indstillingerne er spredt:

| Indstilling | Hvor |
|---|---|
| Notifikationer generelt | `acceptNotifications` via `POST v1/user` |
| E-mail om favoritter på tilbud | `is_favorite_notification_enabled` via `PATCH v3/users/{user_id}` |
| Push om favoritter på tilbud | `is_favorite_push_notification_enabled` via `PATCH v3/users/{user_id}` |
| Nyhedsbreve | endpoints ovenfor |

### POST `v1/push/register` — Set i appens kode

Registrerer enhedens push-token, så serveren kan sende push. Kræver login.

Body (JSON):

| Felt | Type | Værdi i appen |
|---|---|---|
| `service` | string | `fcm` |
| `app_identifier` | string | appens pakkenavn |
| `app_version` | string | appens versionsnavn |
| `token` | string | FCM-token |
| `language` | string | `da` |

Svar: et objekt med push-registreringens id (int), som appen gemmer og sender med som
`push_id` ved logout. Feltnavnet er sandsynligvis `pushId` (appens model har intet
eksplicit JSON-navn) — ikke bekræftet.

---

## 8. Bankkonto (udbetaling til shoppere)

Bruges til udbetalingskonto for brugere, der leverer for andre (Vigo). Ifølge
feature-flaget `app.android.vigo` (= `false`, afprøvet) og et kampagnebanner er Vigo
lukket, så disse endpoints er muligvis ude af drift. Grænser til levering/betaling.

Der er **ikke** fundet endpoints for betalingskort på profilen; kort og MobilePay
håndteres pr. ordre (se dokumentet om ordrer og betaling).

### GET `v3/banks` — Set i appens kode

Query: `page` (int). Element: `id` (int), `name` (string). Kræver login i appen.
Afprøvet uden login: svarer **405** `{"error":"system_error","error_message":"Method not
allowed",…}` i stedet for den sædvanlige 401 — om endpointet stadig findes, er uvist.

### POST `v3/users/{user_id}/bank-accounts` — Set i appens kode

Body: `bank_id` (int), `registration_number` (string), `account_number` (string).
Svar: `{"data": <bankkonto>}`.

Bankkonto-objekt: `id` (int), `bank` (`id`, `name`), `registration_number` (string),
`account_number` (string), `is_verified` (bool), `created_at` og `updated_at`
(tidsstempler).

### PATCH `v3/users/{user_id}/bank-accounts/{account_id}` — Set i appens kode

Bekræfter kontoen med en kode. Body: `is_verified` (bool, altid `true`),
`verification_code` (string eller null). Svar: `{"data": <bankkonto>}`.

Kontoen fjernes igen med `PATCH v3/users/{user_id}` og `active_bank_account_id: null`.

---

## 9. App-konfiguration (uden login)

### GET `v1/settings` — Afprøvet

Global konfiguration. Ingen parametre, ingen konvolut.

| Felt | Type | Læses af appen |
|---|---|---|
| `closed` | bool | nej |
| `closed_android`, `closed_ios`, `closed_web` | bool | kun `closed_android` |
| `closed_reason` | string | ja |
| `closed_order_button_text` | string | ja |
| `show_coupon_code` | bool | nej |
| `coupon_code`, `coupon_code_text_line_1`, `coupon_code_text_line_2` | string | nej |
| `welcome_page_feature_1` … `_3` | int | nej |
| `status_text_enabled` | bool | nej |
| `status_text` | string (HTML) | nej |
| `current_user_agreement_version` | int | ja |
| `current_competition_agreement_version` | int eller null | ja |
| `competition_agreement_active` | bool | ja |

"Lukket"-felterne handler om bestilling/levering, ikke om appen som helhed.

### GET `v3/feature-flags` — Afprøvet

Appen sender `per_page=1000`; serveren begrænser til 100 pr. side (svaret viste
`per_page: 100`). Element: `id` (string), `is_enabled` (bool).

Flag set i svaret (for både `app.android.*` og `app.ios.*`): `payments.mobilePay`,
`payments.scan_and_pay.card`, `payments.scan_and_pay.mobilePay`, `payments.worldline`,
`pop`, `vigo`. Alle var `true` undtagen `vigo`.

```json
{"data": [{"id": "app.android.vigo", "is_enabled": false}],
 "meta": {"pagination": {"current_page": 1, "last_page": 1, "per_page": 100, "total": 12}}}
```

### GET `v1/campaigns` — Afprøvet

Kampagnebannere uden login (grænser til tilbud/indhold). Liste uden konvolut:

| Felt | Type | Bemærkning |
|---|---|---|
| `id` | int | |
| `priority` | int | |
| `type` | string | set: `available_jobs_list`; appen kender bannertyper for indkøbsliste, ledige opgaver og katalog |
| `codename` | string | fritekst i praksis; appen reagerer kun på en "gå til tilbud"-værdi |
| `banner_text` | string | |
| `web_banner_text` | string | læses ikke af appen |
| `subtitle` | string | |
| `expires_at` | string | format `dd.mm.åååå` |
| `image` | string eller null | |
| `link` | string eller null | |
| `is_dismissable` | bool | i appens model; var ikke med i det sete svar |

---

## 10. Kørebog (grænseområde til levering)

Kørselsregnskab for shoppere, slået til med `is_driving_book_enabled`. Hører funktionelt
til Vigo, men ligger under `v3/users/{user_id}`. Alle: set i appens kode.

| Metode | Sti | Body / query | Svar |
|---|---|---|---|
| GET | `v3/users/{user_id}/routes` | `page[number]` (int), `page[size]` (int), `filter[date]` (dato) — bemærk at sideinddelingen her afviger fra `page`/`per_page` | sideinddelt liste af ruter |
| GET | `v3/users/{user_id}/routes/{route_id}` | — | `{"data": <rute>}` |
| PATCH | `v3/users/{user_id}/routes/{route_id}` | `transport_type` (`BIKE`/`CAR`, stavemåde i JSON ikke bekræftet) | intet læses |
| POST | `v3/users/{user_id}/routes/{route_id}/trips` | `from_address_id` (int/null), `to_address_id` (int/null), `trip_type` (enum) | intet læses |
| PATCH | `v3/users/{user_id}/routes/{route_id}/trips/{trip_id}` | `note` (string) | intet læses |

Rute: `id` (int), `transport_type` (enum), `trips` (liste). Tur: `id` (int), `job_id`
(int), `address_from` (string), `address_to` (string), `distance` (int), `note` (string),
`trip_type` (appens værdier: `SHOPPER_TO_SHOP`, `SHOP_TO_CUSTOMER`, `CUSTOMER_TO_SHOP`,
`CUSTOMER_TO_SHOPPER`, `CUSTOMER_TO_CUSTOMER`, `NO_ORIGIN`, `NO_DESTINATION`).

---

## 11. Batch

### POST `v3/batch` — Set i appens kode

Generelt endpoint til at sende flere API-kald i én forespørgsel. Appen bruger det kun til
opgaver/ordrer (grænseområde), men det er ikke bundet til et bestemt emne.

Body: `{"requests": [{"method": "PATCH", "uri": "/api/v3/users/123456/jobs/1", "parameters": {"status": "taken"}}]}`
— `method` (string), `uri` (string, absolut sti inkl. `/api/`), `parameters` (objekt med
string-værdier).

Svar: liste med ét element pr. delkald: `status` (int, HTTP-status) og `body` (objekt;
appen læser `error_type` og `message` ved fejl).

---

## 12. Ikke fundet som API i appen

Disse ting blev eftersøgt, men findes ikke som endpoints i app-version 6.9.0:

- **Baby- og børneklubben**: kun et link til websiden
  `https://www.rema1000.dk/auth/profile?baby-og-borneklubben`, som åbnes i browser.
- **Donationer**: ingen spor.
- **Konkurrencer**: kun versionsfelterne for konkurrencebetingelser (`v1/settings` og
  `v1/user`); intet endpoint for deltagelse.
- **Betalingskort / betalingsmetoder på profilen**: ingen; kun bankkonto (afsnit 8).
- **Foreninger ("sponsor club")**: profilen kan vise en tilknyttet forening
  (`sponsor_club`), og appen har tekster til at søge på klub-id og til-/afmelde samt en
  ubrugt body-model med feltet `sponsor_club_id` — men intet endpoint, der bruger den.
- **Skift af adgangskode**: intet endpoint fundet; sker formentlig på login-siden (antagelse).

## Uafklaret

1. **MitID-udfald**: hvordan "allerede i brug", "under alder" m.fl. signaleres (query på
   retur-URI, eller felter på profilen) er ikke kortlagt.
2. **Enum-stavemåder i JSON** (`transport_method`, `type` på v3-brugeren,
   `transport_type`, `trip_type`): appens interne navne er kendt, men `v1/campaigns`
   viste, at serverens værdier kan afvige (små bogstaver, andre navne), så
   stavemåden skal bekræftes med et rigtigt svar.
3. **`grant_type` ved refresh**: `refresh_token` virker (afprøvet); om appens egen værdi
   `authorization_code` også accepteres, er ikke undersøgt.
4. **Logout**: om `v1/oauth/logout` tilbagekalder tokens eller kun afmelder push.
5. **`v1/user/photo`**: billedets kodning (antaget base64-JPEG) og evt. størrelsesgrænse.
6. **`v1/push/register`**: svarfeltets præcise navn (`pushId` antaget).
7. **`v1/user/gdpr-export`**: leveringsform og om der er begrænsning på hyppighed.
8. **`v1/user/delete`**: om sletning sker straks eller efter en fortrydelsesperiode.
9. **`v3/banks`**: 405 uden login — uvist om endpointet stadig er aktivt, nu hvor Vigo
    er slået fra. Det samme gælder bankkonto- og kørebogs-endpoints.
10. **`accepted_version`** i `v3/policies`: formen er kun kendt fra appens model.
11. **Svarkoder og fejlformater** for alle "Set i appens kode"-endpoints (valideringsfejl,
    403 ved forkert `user_id` osv.) er ikke observeret.
12. **Token-levetid**: `expires_in` er ikke målt i denne kortlægning.
13. **Flere felter**: serveren kan returnere felter, appen ikke læser (som set i
    `v1/settings`); tabellerne for ikke-afprøvede endpoints er derfor minimumslister.
