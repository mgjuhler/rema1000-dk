# rema1000-dk

Uofficiel Python-klient og API-noter til backenden bag den **danske** REMA 1000-app
(`dk.iroots.rema1000`, Android-version 6.9.0).

Med klienten kan du fra et script eller en terminal:

- logge ind med din egen REMA 1000-konto (OAuth 2 med PKCE, præcis som appen gør det)
- læse dine indkøbslister
- lægge varer på en liste, rette antal og fjerne punkter
- læse, tilføje og fjerne favoritter
- hente REMAs forslag til varer, du ofte køber
- hente hele varekataloget med priser (offentligt, kræver ikke login)

Selve HTTP-API'et er beskrevet i [API.md](API.md).

## Vigtigt at vide

- **Uofficielt.** Projektet har intet med REMA 1000 at gøre og er ikke godkendt eller
  understøttet af dem. API'et er ikke dokumenteret offentligt; beskrivelsen her bygger på,
  hvad appen sender og modtager, afprøvet mod det rigtige API 3. oktober 2026.
- **Kan gå i stykker.** Når REMA opdaterer appen eller backenden, kan endpoints, felter og
  login-flow ændre sig uden varsel.
- **Kun Danmark.** Den norske REMA-app bruger en helt anden backend (`api.rema.no`).
  [Alfredvc/rema1000-cli](https://github.com/Alfredvc/rema1000-cli) dækker den norske og
  virker **ikke** til den danske — og omvendt virker dette projekt ikke i Norge.
- **Brug det med omtanke.** Brug din egen konto, og lad være med at hamre på API'et.
  Kataloget fylder ca. 10 MB; spørg på `last_modified` først, og hent kun kataloget igen,
  når det har ændret sig.

## Installation

Kræver Python 3.9 eller nyere.

```bash
git clone https://github.com/mgjuhler/rema1000-dk.git
cd rema1000-dk
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

`requests` er den eneste afhængighed til daglig brug. `playwright` bruges kun af `login`
og skal have en browser installeret én gang:

```bash
playwright install chromium
```

## Login

```bash
python rema1000.py login
```

Der åbner et browservindue med REMAs egen login-side (`login.rema1000.dk`). Log ind med
e-mail og adgangskode. Klienten ser aldrig adgangskoden; den opfanger kun den sidste
omdirigering til appens eget URL-skema og bytter koden til et adgangsbevis.

Adgangsbeviserne gemmes i `~/.config/rema1000/tokens.json` med rettighederne `600`.
En anden placering vælges med `--token-file FIL` eller miljøvariablen
`REMA1000_TOKEN_FILE`.

Login kræver en maskine med skærm. Skal klienten køre på en server, så log ind på din
egen maskine og **flyt** (ikke kopiér) token-filen derhen — se næste afsnit.

### Fornyelses-beviset roterer

Adgangsbeviset gælder en time og fornyes automatisk. **Hver fornyelse udsteder et nyt
fornyelses-bevis (refresh token) og gør det gamle ugyldigt.** Derfor må token-filen kun
ligge ét sted:

- Kopierer du filen til to maskiner, virker den kun på den, der fornyer først. Den anden
  skal logge ind igen.
- Lad ikke to processer forny samtidig med samme fil.
- Læg aldrig filen i git. `.gitignore` i dette repo udelukker `tokens.json`.

## Eksempler

Fra kommandolinjen:

```bash
# Indkøbslisterne med liste-id, punkt-id og vare-id
python rema1000.py lists
python rema1000.py lists --json

# Find en vare i kataloget (kræver ikke login)
python rema1000.py catalog --search "letmælk"
python rema1000.py catalog --modified

# Læg 2 stk. af vare 123456 på liste 1001
python rema1000.py add 1001 123456 --amount 2

# Ret antallet på punkt 900001 til 3, og fjern det igen
python rema1000.py amount 1001 900001 3
python rema1000.py remove 1001 900001

# Favoritter og forslag
python rema1000.py favorites
python rema1000.py favorites --add 123456
python rema1000.py favorites --remove 123456
python rema1000.py suggestions
```

Tallene ovenfor er opdigtede eksempler. `add` tager varens id fra kataloget, mens
`amount` og `remove` tager punktets id på listen (det, `lists` viser som punkt-id).
Uden `--name` slår `add` varens navn op i kataloget, hvilket henter hele kataloget.

Som modul:

```python
from rema1000 import Rema1000, flatten_catalog, search_products

rema = Rema1000()                      # eller Rema1000(token_file="/sti/til/tokens.json")

for shopping_list in rema.lists():
    print(shopping_list["name"], len(shopping_list["items"]))

products = flatten_catalog(rema.catalog())          # offentligt, kræver ikke login
milk = search_products(products, "letmælk")[0]

first = rema.lists()[0]
rema.add_item(first["id"], first["name"], milk["name"], milk["id"], amount=2)
```

| Metode | Gør |
|---|---|
| `login()` | Åbner browseren og gemmer adgangsbeviserne |
| `lists()` | Alle indkøbslister med punkter |
| `add_item(list_id, list_name, name, store_item_id, amount=1)` | Lægger en vare på en liste |
| `set_amount(list_id, list_name, item_id, amount)` | Retter antallet på et punkt |
| `remove_item(list_id, list_name, item_id)` | Fjerner et punkt |
| `sync(changes)` | Sender flere ændringer i ét kald |
| `favorites()`, `add_favorite(id)`, `remove_favorite(id)` | Favoritter |
| `favorite_suggestions()` | Varer, kontoen ofte køber, som ikke er favoritter |
| `user()` | Den indloggede brugers profil |
| `catalog()`, `catalog_modified()` | Varekataloget og tidspunktet for seneste ændring |
| `list_suggestions()`, `settings()` | Appens søgeforslag og globale indstillinger |

Mangler der et gyldigt adgangsbevis, kastes `LoginRequired`; andre fejl fra backenden
kastes som `RemaError` eller `requests.HTTPError`.

## Test

Testene kører uden netværk og uden login:

```bash
python -m unittest discover -s tests -v
```

## Hvad er ikke med

- Bestilling, betaling, kuponer og kvitteringer er ikke undersøgt.
- `GET v3/users/{user_id}/frequently-bought-products` svarede 403 for vores konto og er
  derfor ikke med i klienten.
- Oprettelse, omdøbning og deling af lister er ikke undersøgt.

## Licens

MIT — se [LICENSE](LICENSE). REMA 1000 er et varemærke tilhørende dets ejer; projektet
bruger kun navnet til at beskrive, hvad klienten taler med.
