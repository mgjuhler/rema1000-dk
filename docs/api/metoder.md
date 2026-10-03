# Klientens metoder

Oversigt over alle metoder på klassen `Rema1000` i [`rema1000.py`](../../rema1000.py): hvilket kald hver
metode laver, og om kaldet er afprøvet mod det rigtige API. Felter og svar er beskrevet i
[konto-og-login.md](konto-og-login.md), [indkoeb-og-varer.md](indkoeb-og-varer.md) og
[butikker-og-levering.md](butikker-og-levering.md).

Tabellerne er dannet ud fra klientens docstrings og testtabellen i `tests/test_rema1000.py`; en test
kontrollerer, at hver metode og hvert kald står her.

**Status**

- **Afprøvet** — kaldet er lavet mod det rigtige API (docstring-mærket `[Verified]`).
- **Set i appens kode** — læst i appen, aldrig kaldt (`[From app code]`).
- **Hjælpemetode** — laver ikke selv et kald (`[Helper]`).

Stier er relative til `https://api.digital.rema1000.dk/api/`, medmindre der står et værtsnavn forrest.
`{user_id}` udfyldes af klienten selv ud fra `GET v1/user`.

89 metoder: 49 afprøvet, 34 set i appens kode, 6 hjælpemetoder.

## Login og adgangsbeviser

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `save_tokens` | – | – | Hjælpemetode | Gemmer adgangsbeviserne i token-filen (rettigheder 600) |
| `load_tokens` | – | – | Hjælpemetode | Læser token-filen |
| `exchange_code` | POST | `oauth2/token` | Afprøvet | Veksler login-koden til adgangsbeviser |
| `access_token` | POST | `oauth2/token/refresh` | Afprøvet | Giver et gyldigt adgangsbevis og fornyer det efter behov |
| `login` | GET | `oauth2/authorize` | Afprøvet | Åbner login-siden i en browser og gemmer adgangsbeviserne |
| `logout` | POST | `v1/oauth/logout` | Set i appens kode | Logger ud på serveren og afmelder push. Kræver `confirm=True` |

## Generelle kald

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `request` | – | – | Hjælpemetode | Kalder et vilkårligt endpoint og returnerer det rå svar |
| `pages` | – | – | Hjælpemetode | Henter alle sider af en sideinddelt v3-liste |
| `batch` | POST | `v3/batch` | Set i appens kode | Flere API-kald i én forespørgsel |

## Konto og profil

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `user` | GET | `v1/user` | Afprøvet | Den indloggede brugers profil |
| `user_id` | – | – | Hjælpemetode | Brugerens numeriske id (hentes én gang) |
| `update_user` | POST | `v1/user` | Set i appens kode | Retter profilfelter (navn, e-mail, telefon, notifikationer, favoritbutik …) |
| `set_user_photo` | POST | `v1/user/photo` | Set i appens kode | Sætter profilbilledet |
| `delete_account` | POST | `v1/user/delete` | Set i appens kode | Sletter kontoen. Kræver `confirm=True` |
| `gdpr_export` | POST | `v1/user/gdpr-export` | Set i appens kode | Bestiller en eksport af kontoens persondata |
| `find_friends_by_email` | POST | `v1/user/friends/emails` | Set i appens kode | Finder REMA-brugere ud fra e-mailadresser |
| `find_friends_by_number` | POST | `v1/user/friends/numbers` | Set i appens kode | Finder REMA-brugere ud fra telefonnumre |
| `user_details` | GET | `v3/users/{user_id}` | Set i appens kode | Udvidet profil (type, notifikationsvalg, forening, bankkonto) |
| `update_user_details` | PATCH | `v3/users/{user_id}` | Set i appens kode | Retter den udvidede profil |
| `identity_token` | GET | `identity-verification/token` | Set i appens kode | Engangstoken til MitID-validering |
| `identity_login_url` | GET | `identity-verification/login` | Set i appens kode | Bygger adressen på MitID-siden (åbnes i en browser, kaldes ikke af klienten) |
| `add_address` | POST | `v3/users/{user_id}/addresses` | Set i appens kode | Gemmer en adresse på profilen |
| `update_address` | PATCH | `v3/users/{user_id}/addresses/7` | Set i appens kode | Retter en gemt adresse |
| `delete_address` | DELETE | `v3/users/{user_id}/addresses/7` | Set i appens kode | Sletter en gemt adresse |
| `policies` | GET | `v3/policies` | Afprøvet | Politikker og samtykker med gældende version (uden login) |
| `accept_policy` | POST | `v3/users/{user_id}/policy-versions` | Set i appens kode | Giver samtykke til en politikversion |
| `revoke_policy` | DELETE | `v3/users/{user_id}/policy-versions/4` | Set i appens kode | Trækker et samtykke tilbage. Kræver `confirm=True` |
| `newsletters` | GET | `v3/newsletters` | Afprøvet | Nyhedsbreve, man kan tilmelde sig (uden login) |
| `newsletter_subscriptions` | GET | `v3/users/{user_id}/newsletter-subscriptions` | Set i appens kode | Kontoens tilmeldinger |
| `subscribe_newsletter` | POST | `v3/users/{user_id}/newsletter-subscriptions` | Set i appens kode | Tilmelder et nyhedsbrev |
| `unsubscribe_newsletter` | DELETE | `v3/users/{user_id}/newsletter-subscriptions/9` | Set i appens kode | Afmelder et nyhedsbrev |
| `register_push` | POST | `v1/push/register` | Set i appens kode | Registrerer en enheds push-token |
| `settings` | GET | `v1/settings` | Afprøvet | Appens globale indstillinger (uden login) |
| `feature_flags` | GET | `v3/feature-flags` | Afprøvet | Appens feature-flag (uden login) |
| `campaigns` | GET | `v1/campaigns` | Afprøvet | Kampagnebannere og driftsbeskeder (uden login) |
| `user_campaigns` | GET | `v1/user/campaigns` | Set i appens kode | Kampagnebannere til den indloggede bruger |

## Indkøbslister

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `poll_lists` | GET | `v1/shoppinglists/polling` | Afprøvet | Polling-svaret, som det er (`response`, `unixtime`, `wait`, `settings`) |
| `lists` | GET | `v1/shoppinglists/polling` | Afprøvet | Alle indkøbslister med punkter |
| `find_list` | – | – | Hjælpemetode | Finder én liste ud fra id |
| `sync` | POST | `v1/sync/shoppinglists-v2` | Afprøvet | Sender liste-ændringer; returnerer de opdaterede lister |
| `create_list` | POST | `v1/sync/shoppinglists-v2` | Afprøvet | Opretter en liste og returnerer den nye liste |
| `rename_list` | POST | `v1/sync/shoppinglists-v2` | Afprøvet | Omdøber en liste |
| `delete_list` | GET | `v1/shoppinglists/polling` | Afprøvet | Sletter en liste med alle punkter (kontrollerer først, at listen findes) |
| `delete_list` | POST | `v1/sync/shoppinglists-v2` | Afprøvet | Sletter en liste med alle punkter (kontrollerer først, at listen findes) |
| `add_item` | POST | `v1/sync/shoppinglists-v2` | Afprøvet | Lægger en vare på en liste |
| `set_amount` | POST | `v1/sync/shoppinglists-v2` | Afprøvet | Retter antallet på et punkt |
| `remove_item` | POST | `v1/sync/shoppinglists-v2` | Afprøvet | Fjerner et punkt |
| `set_bought` | POST | `v1/sync/shoppinglists-v2` | Set i appens kode | Krydser et punkt af (eller fjerner krydset) |
| `set_primary_list` | PATCH | `v2/shoppinglists/1001` | Set i appens kode | Gør en liste til den primære |
| `invite_to_list` | POST | `v1/shoppinglist/1001/invite` | Set i appens kode | Inviterer til en liste via e-mail |
| `list_recommended_products` | GET | `v3/shopping-lists/1001/recommended-products` | Afprøvet | Anbefalede varer ud fra listens indhold |
| `list_suggestions` | GET | `v1/shoppinglistsuggestions` | Afprøvet | Fritekstforslag til listen (uden login) |

## Favoritter og personlige forslag

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `favorites` | GET | `v1/favorites/1` | Afprøvet | Favoritvarernes id'er |
| `add_favorite` | POST | `v3/users/{user_id}/favorites` | Afprøvet | Gør en vare til favorit |
| `add_favorites` | POST | `v3/batch` | Set i appens kode | Gør flere varer til favoritter i ét batch-kald |
| `remove_favorite` | DELETE | `v1/favorites/1/11111` | Afprøvet | Fjerner en favorit |
| `favorite_suggestions` | GET | `v3/users/{user_id}/favorite-suggestions` | Afprøvet | Varer, kontoen ofte køber, som ikke er favoritter (alle sider) |
| `dismiss_favorite_suggestion` | DELETE | `v3/users/{user_id}/favorite-suggestions/11111` | Set i appens kode | Afviser et favoritforslag |
| `frequently_bought` | GET | `v3/users/{user_id}/frequently-bought-products` | Afprøvet | "Du plejer at købe". Svarede 403 for testkontoen |
| `inspiration_products` | GET | `v3/users/{user_id}/inspiration-products` | Set i appens kode | "Måske du synes om" |
| `dismiss_inspiration_product` | DELETE | `v3/users/{user_id}/inspiration-products/11111` | Set i appens kode | Afviser en inspirationsvare |

## Varer, søgning og katalog

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `catalog` | GET | `v1/catalog/store/1/withchildren` | Afprøvet | Hele varekataloget (ca. 10 MB, uden login) |
| `catalog_modified` | GET | `v1/catalog/store/1/last_modified` | Afprøvet | Tidspunkt for seneste katalogændring |
| `products` | GET | `v3/products` | Afprøvet | Sideinddelt vareliste med sortering og filtre |
| `offers` | GET | `v3/products` | Afprøvet | Ugens avisvarer, én side |
| `all_offers` | GET | `v3/products` | Afprøvet | Ugens avisvarer, alle sider |
| `product` | GET | `v3/products/11111` | Afprøvet | Én vare |
| `departments` | GET | `v3/departments` | Afprøvet | Afdelinger med kategorier |
| `category_products` | GET | `v3/departments/10/categories/1010/products` | Afprøvet | Varerne i én kategori |
| `barcode` | GET | `v3/product-barcode/5700000000000` | Afprøvet | Slår en stregkode op |
| `search` | GET | `search/products` | Afprøvet | Appens varesøgning |

## Tilbudsavisen (Tjek)

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `newspapers` | GET | `squid-api.tjek.com/v2/catalogs` | Afprøvet | Aktuelle og kommende tilbudsaviser (Tjek) |
| `newspaper_pages` | GET | `squid-api.tjek.com/v2/catalogs/abc123/pages` | Afprøvet | Avisens sider som billeder (Tjek; bruges ikke af appen) |
| `newspaper_offers` | GET | `squid-api.tjek.com/v2/offers` | Afprøvet | Tilbuddene i en avis (Tjek; bruges ikke af appen) |
| `newspaper_offer` | GET | `squid-api.tjek.com/v2/offers/offer1` | Afprøvet | Ét tilbud fra avisen (Tjek) |
| `newspaper_offer_products` | POST | `squid-api.tjek.com/v4/rpc/get_offer_products` | Set i appens kode | Varerne bag et tilbud; `external_id` er REMAs vare-id (Tjek) |
| `newspaper_viewer_url` | GET | `publication-viewer.tjek.com/v1/embeds/{publication_id}` | Afprøvet | Bygger adressen på webvisningen af avisen (kaldes ikke af klienten) |

## Forsideindhold og opskrifter

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `entities` | GET | `rema1000dk/entities` | Afprøvet | Redaktionelt indhold efter type |
| `app_configuration` | GET | `rema1000dk/entities` | Afprøvet | Opbygningen af appens forside, søgeskærm og opskriftsskærm |
| `recipes` | GET | `rema1000dk/entities` | Afprøvet | Opskrifter, evt. kun med et bestemt tag |
| `recipe` | GET | `rema1000dk/entities` | Set i appens kode | Én opskrift ud fra slug |
| `recipe_tags` | GET | `rema1000dk/entities` | Afprøvet | Opskrifts-tags |
| `featured_recipes` | GET | `rema1000dk/featured-recipes` | Afprøvet | Opskrifter i en fremhævet gruppe. Kun fejlsvaret uden gruppe-id er set |
| `search_recipes` | GET | `search/recipes` | Afprøvet | Appens opskriftssøgning |
| `favorite_recipes` | GET | `v3/users/{user_id}/favorite-recipes` | Set i appens kode | Kontoens favoritopskrifter |
| `add_favorite_recipe` | POST | `v3/users/{user_id}/favorite-recipes` | Set i appens kode | Gør en opskrift til favorit |
| `remove_favorite_recipe` | DELETE | `v3/users/{user_id}/favorite-recipes/recipe1` | Set i appens kode | Fjerner en favoritopskrift |

## Butikker og adresser

| Metode | HTTP | Sti | Status | Gør |
|---|---|---|---|---|
| `stores` | GET | `v3/stores` | Afprøvet | Alle butikker med adresse, åbningstider og position (uden login) |
| `stores_near` | GET | `v3/stores` | Afprøvet | De nærmeste butikker til en position |
| `address_autocomplete` | GET | `dawa-proxy.digital.rema1000.dk/autocomplete` | Afprøvet | Adresseforslag fra REMAs DAWA-proxy |

## Udeladt, fordi Vigo er lukket

Vigo-leveringen lukkede 1. december 2025. De 37 kald, der kun giver mening for Vigo-bestilling eller for
Vigo-indkøbere, har derfor ingen metode i klienten. De er beskrevet i
[butikker-og-levering.md](butikker-og-levering.md), som de står i appens kode; ingen af dem er nogensinde
kaldt. De kan stadig nås med `request()` eller kommandoen `api`.

| Område | Antal | Kald |
|---|---|---|
| Bestilling og ordrer (kunden) | 11 | `POST v1/jobs/times-v2`, `POST v1/job`, `POST v1/jobs/create-from-existing`, `GET v1/jobs-v2`, `GET v1/get-inactive-jobs`, `GET v3/users/{user_id}/jobs/{job_id}`, `POST v1/job/{job_id}/cancel`, `POST v1/job/{job_id}/extend-delivery-time`, `POST v1/job/{job_id}/coupon`, `PATCH v3/jobs/{job_id}/deliveries/{delivery_id}`, `POST v1/job/{job_id}/user_orderer` |
| Indkøberens handlinger | 7 | `POST v1/jobs/find`, `POST v1/job/{job_id}/start`, `POST v1/job/sync`, `POST v1/job/{job_id}/add-coordinate`, `PATCH v3/users/{user_id}/jobs/{job_id}`, `POST v3/jobs/{job_id}/deliveries`, `PATCH v3/jobs/{job_id}` |
| Betaling af et job | 5 | `GET`/`POST v3/jobs/{job_id}/payments`, `DELETE v3/jobs/{job_id}/payments/{payment_id}`, `GET v3/jobs/{job_id}/cash-register-token`, `POST v3/jobs/{job_id}/scanned-receipt-barcode` |
| Scan Selv-kurve (findes kun inde i et job) | 4 | `GET v3/jobs/{job_id}/baskets/{basket_id}`, `POST …/items`, `PATCH …/items/{item_id}`, `DELETE …/items/{item_id}` |
| Bedømmelser | 2 | `GET v1/rating-tags`, `POST v1/ratings` |
| Kørebog | 5 | `GET v3/users/{user_id}/routes`, `GET`/`PATCH v3/users/{user_id}/routes/{route_id}`, `POST …/trips`, `PATCH …/trips/{trip_id}` |
| Udbetalingskonto | 3 | `GET v3/banks`, `POST v3/users/{user_id}/bank-accounts`, `PATCH v3/users/{user_id}/bank-accounts/{account_id}` |

Tre kald mere er udeladt, fordi de kun bruges i bestillingsforløbet, og det ikke er afklaret, om de har en
funktion uden Vigo: `GET v3/shopping-lists/{id}?include=logistic_options` (kan listen leveres eller afhentes),
`GET v3/stores/{store_id}/time-slots` (afhentningstider) og `GET v3/users/{user_id}/suggested-stores`
(foreslåede afhentningsbutikker).

Kald, der sletter, betaler, bestiller eller logger ud, kræver `confirm=True` i `request()` og `--yes` i
`api`-kommandoen — også dem ovenfor, der ikke har en metode.
