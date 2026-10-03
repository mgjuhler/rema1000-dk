#!/usr/bin/env python3
"""Unofficial Python client for the backend of the Danish REMA 1000 app.

The endpoints and the login flow were observed from the Android app
(dk.iroots.rema1000 6.9.0). Nothing here is supported by REMA 1000 and it can
stop working whenever the app is updated. See README.md and API.md.

Login is OAuth 2 authorization code with PKCE. The app's callback is a custom
URL scheme, so `login` drives a browser window with Playwright and picks the
code out of the final redirect. Tokens are kept in
~/.config/rema1000/tokens.json (mode 600) unless another file is given.

Only `requests` is needed, plus `playwright` for the `login` command.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

__version__ = "0.1.0"

API = "https://api.digital.rema1000.dk/api/"
CLIENT_ID = "rema1000-app"
REDIRECT_URI = "dk.rema1000.vigo://logincallback"
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "rema1000" / "tokens.json"
TOKEN_FILE_ENV = "REMA1000_TOKEN_FILE"
USER_AGENT = f"rema1000-dk/{__version__} (unofficial Python client)"
ITEM_SOURCE = "android_search"
DEFAULT_STORE_ID = 1
# Refresh this many seconds before the access token actually expires.
EXPIRY_MARGIN = 120
LOGIN_TIMEOUT = 600
MAX_SUGGESTION_PAGES = 20


class RemaError(RuntimeError):
    """The backend answered with something we cannot use."""


class LoginRequired(RemaError):
    """There is no usable token; the user has to run `login` again."""


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def default_token_file() -> Path:
    """The token file: $REMA1000_TOKEN_FILE when set, else the default path."""
    override = os.environ.get(TOKEN_FILE_ENV)
    return Path(override).expanduser() if override else DEFAULT_TOKEN_FILE


def pkce_challenge(verifier: str) -> str:
    """The S256 code challenge for a PKCE verifier (RFC 7636)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorize_url(verifier: str, state: str) -> str:
    """The URL that starts the login in a browser."""
    query = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "scope": "",
        "response_type": "code",
        "theme": "light",
    }
    return API + "oauth2/authorize?" + urlencode(query)


def code_from_callback(url: str, state: str) -> str:
    """Pick the authorization code out of the final redirect, checking the state."""
    query = parse_qs(urlsplit(url).query)
    if query.get("state", [""])[0] != state:
        raise RemaError("login callback carried an unexpected state")
    code = query.get("code", [""])[0]
    if not code:
        raise RemaError("login callback carried no authorization code")
    return code


def token_from_body(body: dict) -> dict:
    """The token object from a token response (wrapped in "tokens", or bare)."""
    token = body.get("tokens") or body
    if not isinstance(token, dict) or not token.get("access_token"):
        raise RemaError("token response carried no access token")
    return token


def new_item(name: str, store_item_id: int, amount: int = 1, store_id: int = DEFAULT_STORE_ID) -> dict:
    """The item change that adds a catalogue product to a list."""
    return {
        "offlineId": str(uuid.uuid4()),
        "name": name,
        "source": ITEM_SOURCE,
        "amount": amount,
        "bought": False,
        "store_id": store_id,
        "store_item_id": store_item_id,
    }


def amount_change(item_id: int, amount: int) -> dict:
    return {"id": item_id, "source": ITEM_SOURCE, "amount": amount}


def delete_change(item_id: int) -> dict:
    return {"id": item_id, "source": ITEM_SOURCE, "deleted": True}


def list_change(list_id: int, list_name: str, items: list[dict]) -> dict:
    """One entry of the "changes" array: a list and the item changes for it."""
    return {"id": list_id, "name": list_name, "items": items}


def flatten_catalog(catalog: dict) -> list[dict]:
    """Flatten the catalogue to one dict per product.

    Hidden categories are skipped, and a product that is listed in several
    categories keeps the first one.
    """
    products: dict[int, dict] = {}
    for department in catalog.get("departments") or []:
        for category in department.get("categories") or []:
            if category.get("hidden"):
                continue
            for item in category.get("items") or []:
                if item.get("id") in products or not item.get("name"):
                    continue
                pricing = item.get("pricing") or {}
                images = item.get("images") or []
                products[item["id"]] = {
                    "id": item["id"],
                    "name": item["name"],
                    "underline": item.get("underline") or "",
                    "department": department.get("name") or "",
                    "category": category.get("name") or "",
                    "price": pricing.get("price"),
                    "normal_price": pricing.get("normal_price"),
                    "is_on_discount": bool(pricing.get("is_on_discount")),
                    "deposit": pricing.get("deposit") or 0,
                    "image": (images[0].get("small") or "") if images else "",
                    "popularity": int((item.get("extra") or {}).get("popularity") or 0),
                }
    return list(products.values())


def search_products(products: list[dict], text: str) -> list[dict]:
    """Products whose name or underline contains every word of `text`, most popular first."""
    words = text.casefold().split()
    hits = [
        product for product in products
        if all(word in f"{product['name']} {product['underline']}".casefold() for word in words)
    ]
    return sorted(hits, key=lambda product: -product["popularity"])


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

class Rema1000:
    """A client for one REMA 1000 account, backed by one token file.

    The refresh token rotates on every refresh, so a token file must not be
    copied to a second place: whichever copy refreshes first invalidates the
    other one.
    """

    def __init__(self, token_file: str | os.PathLike | None = None, session: requests.Session | None = None,
                 user_agent: str = USER_AGENT, timeout: float = 30):
        self.token_file = Path(token_file).expanduser() if token_file else default_token_file()
        self.session = session or requests.Session()
        self.headers = {"Accept": "application/json", "User-Agent": user_agent}
        self.timeout = timeout
        self._user_id: int | None = None

    # ---- tokens ----------------------------------------------------------

    def save_tokens(self, token: dict) -> None:
        """Write the token file atomically with mode 600, adding "expires_at"."""
        directory = self.token_file.parent
        if not directory.exists():
            directory.mkdir(parents=True, mode=0o700)
        data = {**token, "expires_at": time.time() + int(token.get("expires_in") or 0)}
        tmp = self.token_file.with_name(self.token_file.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, self.token_file)

    def load_tokens(self) -> dict:
        if not self.token_file.exists():
            raise LoginRequired(f"no token file at {self.token_file}")
        return json.loads(self.token_file.read_text(encoding="utf-8"))

    def exchange_code(self, code: str, verifier: str) -> dict:
        """Swap an authorization code for tokens and store them."""
        response = self.session.post(
            API + "oauth2/token",
            json={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "code": code,
                "code_verifier": verifier,
            },
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        token = token_from_body(response.json())
        self.save_tokens(token)
        return token

    def access_token(self) -> str:
        """A valid access token; refreshes (and stores) it when it is about to expire."""
        token = self.load_tokens()
        if token.get("access_token") and time.time() + EXPIRY_MARGIN < float(token.get("expires_at") or 0):
            return token["access_token"]
        if not token.get("refresh_token"):
            raise LoginRequired("the access token has expired and there is no refresh token")
        response = self.session.post(
            API + "oauth2/token/refresh",
            json={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": token["refresh_token"]},
            headers=self.headers,
            timeout=self.timeout,
        )
        if response.status_code in (400, 401):
            raise LoginRequired("the refresh token was rejected")
        response.raise_for_status()
        fresh = token_from_body(response.json())
        # Keep the old refresh token if the server does not hand out a new one.
        fresh.setdefault("refresh_token", token["refresh_token"])
        self.save_tokens(fresh)
        return fresh["access_token"]

    def login(self, timeout: int = LOGIN_TIMEOUT) -> None:
        """Open a browser window, let the user log in, and store the tokens."""
        from playwright.sync_api import sync_playwright

        verifier = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(48)
        callback: list[str] = []

        def seen(url: str | None) -> None:
            if url and url.startswith(REDIRECT_URI) and not callback:
                callback.append(url)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            # The final hop is a redirect to the app's own URL scheme, which a
            # browser cannot open: catch it as a redirect header or as the
            # request that fails.
            page.on("response", lambda r: seen(r.headers.get("location")))
            page.on("request", lambda r: seen(r.url))
            page.on("requestfailed", lambda r: seen(r.url))
            page.goto(authorize_url(verifier, state))
            deadline = time.time() + timeout
            while not callback and time.time() < deadline and not page.is_closed():
                page.wait_for_timeout(300)
            browser.close()

        if not callback:
            raise RemaError("the login was not completed")
        self.exchange_code(code_from_callback(callback[0], state), verifier)

    # ---- HTTP ------------------------------------------------------------

    def _request(self, method: str, path: str, *, auth: bool = True, timeout: float | None = None, **kwargs):
        headers = dict(self.headers)
        if auth:
            headers["Authorization"] = "Bearer " + self.access_token()
        response = self.session.request(method, API + path, headers=headers, timeout=timeout or self.timeout, **kwargs)
        if auth and response.status_code == 401:
            raise LoginRequired("the backend rejected the access token")
        response.raise_for_status()
        return response

    # ---- account ---------------------------------------------------------

    def user(self) -> dict:
        """The logged-in user's profile."""
        return self._request("GET", "v1/user").json()

    def user_id(self) -> int:
        if self._user_id is None:
            user_id = self.user().get("id")
            if not user_id:
                raise RemaError("the user profile carried no id")
            self._user_id = int(user_id)
        return self._user_id

    # ---- shopping lists --------------------------------------------------

    def lists(self) -> list[dict]:
        """All shopping lists with their items."""
        return self._request("GET", "v1/shoppinglists/polling", params={"unixtime": 0}).json().get("response") or []

    def find_list(self, list_id: int) -> dict:
        for shopping_list in self.lists():
            if shopping_list.get("id") == list_id:
                return shopping_list
        raise RemaError(f"no shopping list with id {list_id}")

    def sync(self, changes: list[dict]) -> list[dict]:
        """Push list changes the way the app syncs them; returns the updated lists."""
        body = self._request("POST", "v1/sync/shoppinglists-v2", json={"changes": changes}).json()
        if body.get("error_code"):
            raise RemaError(f"the change was rejected: {body.get('error_message') or body.get('error_code')}")
        return body.get("response") or []

    def add_item(self, list_id: int, list_name: str, name: str, store_item_id: int, amount: int = 1,
                 store_id: int = DEFAULT_STORE_ID) -> list[dict]:
        """Add one catalogue product to a shopping list."""
        return self.sync([list_change(list_id, list_name, [new_item(name, store_item_id, amount, store_id)])])

    def set_amount(self, list_id: int, list_name: str, item_id: int, amount: int) -> list[dict]:
        """Change how many of a product the list asks for (item_id is the list item's id)."""
        return self.sync([list_change(list_id, list_name, [amount_change(item_id, amount)])])

    def remove_item(self, list_id: int, list_name: str, item_id: int) -> list[dict]:
        """Remove an item from a list (item_id is the list item's id)."""
        return self.sync([list_change(list_id, list_name, [delete_change(item_id)])])

    # ---- favourites ------------------------------------------------------

    def favorites(self, store_id: int = DEFAULT_STORE_ID) -> list[int]:
        """Catalogue ids of the products marked as favourites."""
        return [int(item["id"]) for item in self._request("GET", f"v1/favorites/{store_id}").json() if item.get("id")]

    def add_favorite(self, product_id: int) -> None:
        self._request("POST", f"v3/users/{self.user_id()}/favorites", params={"product_id": product_id})

    def remove_favorite(self, product_id: int, store_id: int = DEFAULT_STORE_ID) -> None:
        self._request("DELETE", f"v1/favorites/{store_id}/{product_id}")

    def favorite_suggestions(self, max_pages: int = MAX_SUGGESTION_PAGES) -> list[int]:
        """Catalogue ids of products the account often buys but has not made favourites, best first."""
        ids: list[int] = []
        page = 1
        while page <= max_pages:
            body = self._request("GET", f"v3/users/{self.user_id()}/favorite-suggestions",
                                 params={"per_page": 50, "page": page}).json()
            ids += [int(item["id"]) for item in body.get("data") or [] if item.get("id")]
            if page >= int(((body.get("meta") or {}).get("pagination") or {}).get("last_page") or 1):
                break
            page += 1
        return ids

    # ---- public endpoints (no login) -------------------------------------

    def catalog(self, store_id: int = DEFAULT_STORE_ID) -> dict:
        """The whole product catalogue (departments > categories > items), about 10 MB."""
        return self._request("GET", f"v1/catalog/store/{store_id}/withchildren", auth=False, timeout=120).json()

    def catalog_modified(self, store_id: int = DEFAULT_STORE_ID) -> int:
        """Unix time of the last catalogue change; poll this instead of the catalogue."""
        body = self._request("GET", f"v1/catalog/store/{store_id}/last_modified", auth=False).json()
        return int(body.get("last_modified") or 0)

    def list_suggestions(self) -> list[dict]:
        """The generic words the app suggests while typing on a list ({title, category})."""
        return self._request("GET", "v1/shoppinglistsuggestions", auth=False).json()

    def settings(self) -> dict:
        """The app's global settings (closed flags, status text and so on)."""
        return self._request("GET", "v1/settings", auth=False).json()


# --------------------------------------------------------------------------
# Command line (user-facing text is Danish)
# --------------------------------------------------------------------------

def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=1))


def _print_products(products: list[dict]) -> None:
    for product in products:
        price = "" if product["price"] is None else f"{product['price']:.2f} kr."
        offer = " (tilbud)" if product["is_on_discount"] else ""
        print(f"{product['id']:>8}  {price:>11}{offer}  {product['name']}  [{product['underline']}]")


def _cmd_login(client: Rema1000, args) -> int:
    print("Log ind med din REMA 1000-konto i browservinduet ...")
    client.login()
    print(f"Logget ind. Adgangsbeviset er gemt i {client.token_file}")
    return 0


def _cmd_lists(client: Rema1000, args) -> int:
    lists = client.lists()
    if args.json:
        _print_json(lists)
        return 0
    for shopping_list in lists:
        print(f"{shopping_list.get('name')}  (liste-id {shopping_list.get('id')})")
        for item in shopping_list.get("items") or []:
            mark = "x" if item.get("bought") else " "
            print(f"  [{mark}] {item.get('amount')} x {item.get('name')}  "
                  f"(punkt-id {item.get('id')}, vare-id {item.get('store_item_id')})")
    return 0


def _cmd_add(client: Rema1000, args) -> int:
    shopping_list = client.find_list(args.list_id)
    name = args.name
    if not name:
        matches = [p for p in flatten_catalog(client.catalog(args.store)) if p["id"] == args.product_id]
        if not matches:
            print(f"Varen {args.product_id} findes ikke i kataloget. Angiv navnet med --name.", file=sys.stderr)
            return 1
        name = matches[0]["name"]
    client.add_item(shopping_list["id"], shopping_list["name"], name, args.product_id, args.amount, args.store)
    print(f"Tilføjet: {args.amount} x {name} på {shopping_list['name']}")
    return 0


def _cmd_amount(client: Rema1000, args) -> int:
    shopping_list = client.find_list(args.list_id)
    client.set_amount(shopping_list["id"], shopping_list["name"], args.item_id, args.amount)
    print(f"Antal sat til {args.amount}")
    return 0


def _cmd_remove(client: Rema1000, args) -> int:
    shopping_list = client.find_list(args.list_id)
    client.remove_item(shopping_list["id"], shopping_list["name"], args.item_id)
    print("Fjernet")
    return 0


def _cmd_favorites(client: Rema1000, args) -> int:
    if args.add is not None:
        client.add_favorite(args.add)
        print("Tilføjet som favorit")
    elif args.remove is not None:
        client.remove_favorite(args.remove, args.store)
        print("Fjernet som favorit")
    else:
        _print_json(client.favorites(args.store))
    return 0


def _cmd_suggestions(client: Rema1000, args) -> int:
    _print_json(client.favorite_suggestions())
    return 0


def _cmd_catalog(client: Rema1000, args) -> int:
    if args.modified:
        print(client.catalog_modified(args.store))
        return 0
    catalog = client.catalog(args.store)
    if args.raw:
        _print_json(catalog)
        return 0
    products = flatten_catalog(catalog)
    if args.search:
        products = search_products(products, args.search)
    if args.json:
        _print_json(products)
    else:
        _print_products(products)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rema1000.py",
        description="Uofficiel klient til den danske REMA 1000-apps backend.",
    )
    parser.add_argument("--token-file", metavar="FIL",
                        help=f"fil med adgangsbeviser (standard: ${TOKEN_FILE_ENV} eller {DEFAULT_TOKEN_FILE})")
    parser.add_argument("--store", type=int, default=DEFAULT_STORE_ID, metavar="ID",
                        help="butiks-id i API'et (standard: 1)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="kommando")

    p = sub.add_parser("login", help="log ind i et browservindue (kræver playwright)")
    p.set_defaults(func=_cmd_login)

    p = sub.add_parser("lists", help="vis indkøbslisterne")
    p.add_argument("--json", action="store_true", help="skriv API'ets svar som JSON")
    p.set_defaults(func=_cmd_lists)

    p = sub.add_parser("add", help="læg en vare fra kataloget på en liste")
    p.add_argument("list_id", type=int, help="listens id")
    p.add_argument("product_id", type=int, help="varens id i kataloget")
    p.add_argument("--amount", type=int, default=1, help="antal (standard: 1)")
    p.add_argument("--name", help="varens navn (slås ellers op i kataloget)")
    p.set_defaults(func=_cmd_add)

    p = sub.add_parser("amount", help="ret antallet på et punkt på en liste")
    p.add_argument("list_id", type=int, help="listens id")
    p.add_argument("item_id", type=int, help="punktets id på listen")
    p.add_argument("amount", type=int, help="nyt antal")
    p.set_defaults(func=_cmd_amount)

    p = sub.add_parser("remove", help="fjern et punkt fra en liste")
    p.add_argument("list_id", type=int, help="listens id")
    p.add_argument("item_id", type=int, help="punktets id på listen")
    p.set_defaults(func=_cmd_remove)

    p = sub.add_parser("favorites", help="vis, tilføj eller fjern favoritter")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--add", type=int, metavar="VARE_ID", help="gør varen til favorit")
    group.add_argument("--remove", type=int, metavar="VARE_ID", help="fjern varen som favorit")
    p.set_defaults(func=_cmd_favorites)

    p = sub.add_parser("suggestions", help="varer I ofte køber, som ikke er favoritter endnu")
    p.set_defaults(func=_cmd_suggestions)

    p = sub.add_parser("catalog", help="varekataloget (offentligt, kræver ikke login)")
    p.add_argument("--search", metavar="TEKST", help="vis kun varer, der indeholder alle ordene")
    p.add_argument("--json", action="store_true", help="skriv varerne som JSON")
    p.add_argument("--raw", action="store_true", help="skriv API'ets fulde svar (ca. 10 MB)")
    p.add_argument("--modified", action="store_true", help="vis kun tidspunktet for seneste ændring")
    p.set_defaults(func=_cmd_catalog)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = Rema1000(token_file=args.token_file)
    try:
        return args.func(client, args)
    except LoginRequired as error:
        print(f"REMA kræver login (kør: rema1000.py login). [{error}]", file=sys.stderr)
        return 1
    except (RemaError, requests.RequestException) as error:
        print(f"Fejl: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
