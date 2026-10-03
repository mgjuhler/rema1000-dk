# API-noter: den danske REMA 1000-app

Vores egen beskrivelse af det HTTP-API, den danske REMA 1000-app taler med. Uofficielt,
ikke dokumenteret af REMA, og kan ændre sig uden varsel. Afprøvet mod det rigtige API
3. oktober 2026 (Android-appen `dk.iroots.rema1000` 6.9.0).

**Alle id'er, navne, koder og adgangsbeviser i eksemplerne er opdigtede**, og svarene er
forkortet til de felter, vi har brugt. Rigtige svar indeholder flere felter.

- Basis-URL: `https://api.digital.rema1000.dk/api/`
- Alle stier herunder er relative til basis-URL'en.
- Send `Accept: application/json`. Kroppe sendes som JSON.
- Beskyttede kald kræver `Authorization: Bearer <access_token>`.

Den norske REMA-app bruger en anden backend (`api.rema.no`); intet her gælder for den.

## Oversigt

| Metode | Sti | Login | Formål |
|---|---|---|---|
| GET | `oauth2/authorize` | nej | Starter login i en browser |
| POST | `oauth2/token` | nej | Bytter kode til adgangsbeviser |
| POST | `oauth2/token/refresh` | nej | Fornyer adgangsbeviset |
| GET | `v1/user` | ja | Brugerens profil (bl.a. bruger-id) |
| GET | `v1/shoppinglists/polling?unixtime=0` | ja | Alle indkøbslister |
| POST | `v1/sync/shoppinglists-v2` | ja | Ændringer på indkøbslister |
| GET | `v1/favorites/{store_id}` | ja | Favoritter |
| POST | `v3/users/{user_id}/favorites?product_id=…` | ja | Tilføj favorit |
| DELETE | `v1/favorites/{store_id}/{item_id}` | ja | Fjern favorit |
| GET | `v3/users/{user_id}/favorite-suggestions` | ja | Ofte købt, endnu ikke favorit |
| GET | `v3/users/{user_id}/frequently-bought-products` | ja | Svarede 403 for vores konto |
| GET | `v1/catalog/store/{store_id}/withchildren` | nej | Hele varekataloget (ca. 10 MB) |
| GET | `v1/catalog/store/{store_id}/last_modified` | nej | Hvornår kataloget sidst blev ændret |
| GET | `v1/shoppinglistsuggestions` | nej | Søgeforslag til indkøbslisten |
| GET | `v1/settings` | nej | Appens globale indstillinger |

`store_id` har været `1` i alt, hvad vi har set.

## Fejl

Et beskyttet kald uden gyldigt adgangsbevis svarer `401`:

```json
{
  "error_code": 101,
  "translate": false,
  "error": "access_denied",
  "error_message": "The resource owner or authorization server denied the request",
  "status_code": 401
}
```

`v1/sync/shoppinglists-v2` kan også melde fejl i kroppen med `error_code` og
`error_message`, så tjek kroppen og ikke kun statuskoden.

## Login

OAuth 2 authorization code med PKCE (S256).

1. Lav en tilfældig `code_verifier` og en tilfældig `state`.
   `code_challenge` = base64url uden `=` af SHA-256 af `code_verifier`.
2. Åbn i en browser:

   ```
   GET oauth2/authorize
       ?client_id=rema1000-app
       &redirect_uri=dk.rema1000.vigo://logincallback
       &state=<state>
       &code_challenge=<code_challenge>
       &code_challenge_method=S256
       &scope=
       &response_type=code
       &theme=light
   ```

3. Kaldet sender browseren videre til `login.rema1000.dk`, hvor brugeren logger ind med
   e-mail og adgangskode.
4. Til sidst omdirigeres der til appens eget URL-skema:

   ```
   dk.rema1000.vigo://logincallback?code=<kode>&state=<state>
   ```

   En almindelig browser kan ikke åbne det skema, så koden skal opfanges i selve
   omdirigeringen (klienten her gør det med Playwright). Kontrollér, at `state` er den,
   du selv sendte.

### Byt koden til adgangsbeviser

```
POST oauth2/token
```

```json
{
  "grant_type": "authorization_code",
  "client_id": "rema1000-app",
  "redirect_uri": "dk.rema1000.vigo://logincallback",
  "code": "EKSEMPEL-KODE",
  "code_verifier": "EKSEMPEL-VERIFIER"
}
```

Svar:

```json
{
  "tokens": {
    "access_token": "EKSEMPEL-ACCESS-TOKEN",
    "refresh_token": "EKSEMPEL-REFRESH-TOKEN",
    "expires_in": 3600,
    "token_type": "Bearer"
  }
}
```

### Forny adgangsbeviset

```
POST oauth2/token/refresh
```

```json
{
  "grant_type": "refresh_token",
  "client_id": "rema1000-app",
  "refresh_token": "EKSEMPEL-REFRESH-TOKEN"
}
```

Svaret har samme form som ovenfor. **`refresh_token` roterer ved hver fornyelse**: det
gamle bliver ugyldigt, og det nye skal gemmes med det samme. Hold derfor
adgangsbeviserne ét sted — to kopier af samme fil ender med, at den ene skal logge ind
igen.

## Bruger

```
GET v1/user
```

```json
{
  "id": 4242
}
```

Vi har kun brugt `id`, som indgår i `v3/users/{user_id}/…`-stierne. Svaret indeholder
også kontoens øvrige oplysninger.

## Indkøbslister

### Læs

```
GET v1/shoppinglists/polling?unixtime=0
```

`unixtime=0` giver alle lister med alt indhold.

```json
{
  "response": [
    {
      "id": 1001,
      "code": "ABC123",
      "name": "Eksempelliste",
      "approved": true,
      "active": true,
      "primary": true,
      "warning": null,
      "bags": 0,
      "members": [],
      "items": [
        {
          "id": 900001,
          "name": "Eksempelvare",
          "unit": "stk",
          "amount": "2",
          "bought": false,
          "total_price": 25.9,
          "store_id": 1,
          "store_item_id": 123456
        }
      ]
    }
  ]
}
```

Værd at bemærke:

- `amount` er en streng.
- `total_price` er normalprisen gange antal — uden rabat, også når varen er på tilbud.
- Et punkt har to id'er: `id` er punktet på listen, `store_item_id` er varen i kataloget.

### Ændr

```
POST v1/sync/shoppinglists-v2
```

Kroppen er en række ændringer, én pr. liste. Listen udpeges med `id` og `name`, og
`items` indeholder ændringerne på dens punkter. Flere lister og flere punkter kan sendes
i samme kald. Svaret er de opdaterede lister i samme form som ved læsning
(`{"response": [...]}`).

Ny vare — `offlineId` er en UUID, klienten selv finder på:

```json
{
  "changes": [
    {
      "id": 1001,
      "name": "Eksempelliste",
      "items": [
        {
          "offlineId": "00000000-0000-4000-8000-000000000000",
          "name": "Eksempelvare",
          "source": "android_search",
          "amount": 1,
          "bought": false,
          "store_id": 1,
          "store_item_id": 123456
        }
      ]
    }
  ]
}
```

Ret antal — `id` er punktets id på listen:

```json
{
  "changes": [
    {
      "id": 1001,
      "name": "Eksempelliste",
      "items": [
        { "id": 900001, "source": "android_search", "amount": 3 }
      ]
    }
  ]
}
```

Fjern et punkt:

```json
{
  "changes": [
    {
      "id": 1001,
      "name": "Eksempelliste",
      "items": [
        { "id": 900001, "source": "android_search", "deleted": true }
      ]
    }
  ]
}
```

## Favoritter

```
GET v1/favorites/{store_id}
```

```json
[
  { "id": 123456, "pricing": { "price": 12.95, "normal_price": 12.95, "is_on_discount": false } }
]
```

`id` er varens id i kataloget.

```
POST   v3/users/{user_id}/favorites?product_id=123456
DELETE v1/favorites/{store_id}/123456
```

Bemærk, at tilføjelse ligger under `v3` med bruger-id, mens læsning og sletning ligger
under `v1` med butiks-id.

### Ofte købt, endnu ikke favorit

```
GET v3/users/{user_id}/favorite-suggestions?per_page=50&page=1
```

```json
{
  "data": [
    { "id": 123456 },
    { "id": 234567 }
  ],
  "meta": {
    "pagination": { "last_page": 3 }
  }
}
```

Svaret er sideopdelt: hent `page=1`, `2`, … til og med `meta.pagination.last_page`.
Rækkefølgen er REMAs egen, bedste forslag først.

`GET v3/users/{user_id}/frequently-bought-products` findes, men svarede `403` for vores
konto.

## Offentlige kald (uden login)

### Varekatalog

```
GET v1/catalog/store/1/withchildren
```

Hele kataloget i ét svar på ca. 10 MB: afdelinger → kategorier → varer.

```json
{
  "departments": [
    {
      "name": "Eksempelafdeling",
      "categories": [
        {
          "name": "Eksempelkategori",
          "hidden": false,
          "items": [
            {
              "id": 123456,
              "name": "Eksempelvare",
              "underline": "1 l / Eksempelmærke",
              "pricing": {
                "price": 10.0,
                "normal_price": 12.95,
                "is_on_discount": true,
                "deposit": 0
              },
              "images": [
                {
                  "small": "https://example.invalid/123456-small.jpg",
                  "medium": "https://example.invalid/123456-medium.jpg",
                  "large": "https://example.invalid/123456-large.jpg"
                }
              ],
              "extra": { "popularity": 42 }
            }
          ]
        }
      ]
    }
  ]
}
```

- Samme vare kan stå i flere kategorier.
- Kategorier kan være markeret `hidden`.
- `pricing.deposit` er pant.
- `extra.popularity` er et tal, hvor højere er mere populært; det er praktisk til at
  sortere søgeresultater.

### Seneste ændring af kataloget

```
GET v1/catalog/store/1/last_modified
```

```json
{ "last_modified": 1700000000 }
```

Unix-tid. Svaret er på få bytes, så spørg her først, og hent kun kataloget igen, når
tallet har ændret sig.

### Søgeforslag til indkøbslisten

```
GET v1/shoppinglistsuggestions
```

En liste på ca. 30 KB med almindelige ord og den afdeling, de hører til:

```json
[
  { "title": "agurk", "category": "frugt & grønt" },
  { "title": "affaldsposer", "category": "nonfood" }
]
```

### Indstillinger

```
GET v1/settings
```

Appens globale indstillinger: om bestilling er lukket (`closed`, `closed_android`,
`closed_ios`, `closed_web`), statustekst (`status_text_enabled`, `status_text`) og
lignende.

```json
{
  "closed": false,
  "closed_android": false,
  "closed_ios": false,
  "closed_web": false,
  "status_text_enabled": false,
  "status_text": ""
}
```
