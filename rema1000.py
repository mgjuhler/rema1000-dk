#!/usr/bin/env python3
"""Unofficial Python client for the backend of the Danish REMA 1000 app.

The endpoints and the login flow were observed from the Android app
(dk.iroots.rema1000 6.9.0). Nothing here is supported by REMA 1000 and it can
stop working whenever the app is updated. See README.md, API.md and docs/api/.

The `Rema1000` class has one method for every call the app makes: account,
shopping lists, favourites, products, search, offers, the weekly newspaper
(served by Tjek), recipes, front page content, stores and address lookup. The
"Vigo" delivery service closed on 1 December 2025, so its calls (orders,
payment, self-scan baskets, ratings, driving log, payout accounts) have no
methods here. Every method docstring ends with a status tag:

    [Verified]       called against the live API
    [From app code]  read out of the app, never called
    [Helper]         makes no call of its own

Calls that delete, pay, order or log out refuse to run without `confirm=True`.
Anything that has no wrapper can be reached with `Rema1000.request()` or the
`api` command.

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
import re
import secrets
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import requests

__version__ = "0.2.0"

API = "https://api.digital.rema1000.dk/api/"
API_HOST = "api.digital.rema1000.dk"
# Editorial content (front page, recipes) lives under its own prefix.
CONTENT_API = API + "rema1000dk/"
# REMA's proxy in front of the public Danish address register (DAWA).
ADDRESS_API = "https://dawa-proxy.digital.rema1000.dk/"
SHOP_URL = "https://shop.rema1000.dk"
URL_SCHEME = "dk.rema1000.vigo"

# The weekly newspaper is not served by REMA but by Tjek (formerly eTilbudsavis).
# The four values below are the public client values shipped inside the REMA
# 1000 app: every installed copy of the app sends them, and the same kind of
# key sits in any web page that embeds a Tjek publication. They identify the
# REMA 1000 app towards Tjek; they are not tied to a user and give access to
# nothing but the published newspapers.
TJEK_API = "https://squid-api.tjek.com"
TJEK_VIEWER = "https://publication-viewer.tjek.com"
TJEK_API_KEY = "bf2ff457a2a43daf4ea30dc158438719"  # sent as the x-api-key header
TJEK_TRACK_ID = "AAAAGw=="  # string resource in the app; no call in the app sends it
TJEK_DEALER_ID = "11deC"  # REMA 1000 Denmark at Tjek ("dealer" in API v2)
TJEK_BUSINESS_ID = TJEK_DEALER_ID  # the same id is called "business" in API v4

CLIENT_ID = "rema1000-app"
REDIRECT_URI = URL_SCHEME + "://logincallback"
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "rema1000" / "tokens.json"
TOKEN_FILE_ENV = "REMA1000_TOKEN_FILE"
USER_AGENT = f"rema1000-dk/{__version__} (unofficial Python client)"
ITEM_SOURCE = "android_search"
DEFAULT_STORE_ID = 1
# Refresh this many seconds before the access token actually expires.
EXPIRY_MARGIN = 120
LOGIN_TIMEOUT = 600
MAX_SUGGESTION_PAGES = 20
MAX_PAGES = 50

# Calls that delete, pay, order or log out. `Rema1000.request` refuses them
# unless it is given confirm=True (the CLI: --yes). The order and payment
# calls have no methods of their own (Vigo is closed) but stay guarded, because
# `request` and the `api` command can still reach them.
GUARDED = (
    ("POST", r"v1/user/delete"),
    ("POST", r"v1/oauth/logout"),
    ("POST", r"v1/job"),
    ("POST", r"v1/jobs/create-from-existing"),
    ("POST", r"v1/job/[^/]+/cancel"),
    ("POST", r"v3/jobs/[^/]+/payments"),
    ("DELETE", r"v3/jobs/[^/]+/payments/[^/]+"),
    ("DELETE", r"v3/users/[^/]+/policy-versions/[^/]+"),
)


class RemaError(RuntimeError):
    """The backend answered with something we cannot use."""


class LoginRequired(RemaError):
    """There is no usable token; the user has to run `login` again."""


class ConfirmationRequired(RemaError):
    """A destructive or expensive call was made without confirm=True."""


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


def api_url(path: str, base: str = API) -> str:
    """The full URL for a path; "v1/user", "/v1/user" and "/api/v1/user" all work."""
    if path.startswith(("http://", "https://")):
        return path
    path = path.lstrip("/")
    if base == API and path.startswith("api/"):
        path = path[len("api/"):]
    return base + path


def is_guarded(method: str, path: str) -> bool:
    """Whether a call deletes, pays, orders or logs out (see GUARDED)."""
    relative = api_url(path)
    if not relative.startswith(API):
        return False
    relative = relative[len(API):].split("?")[0].strip("/")
    return any(method.upper() == verb and re.fullmatch(pattern, relative) for verb, pattern in GUARDED)


def query_flag(value) -> str | None:
    """A boolean the way the API wants it in a query string ("true"/"false")."""
    if value is None:
        return None
    return "true" if value else "false"


def without_none(**fields) -> dict:
    """The given fields minus the ones that are None."""
    return {key: value for key, value in fields.items() if value is not None}


def newspaper_viewer_url(publication_id: str) -> str:
    """The web page that shows a newspaper, as the app opens it in a web view."""
    query = urlencode({"enable_zoom": "true", "api_key": TJEK_API_KEY, "context": "webview",
                       "view_direction": "horizontal", "view_mode": "paged", "ui": "regular"})
    return f"{TJEK_VIEWER}/v1/embeds/{quote(str(publication_id), safe='')}?{query}"


def current_price(product: dict) -> dict:
    """The price period in force on a v3 product (the first entry of "prices")."""
    prices = product.get("prices") or []
    return prices[0] if prices else {}


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

    Unless a docstring says otherwise, a method returns the JSON body the API
    answered with (v3 endpoints wrap theirs in {"data": ..., "meta": ...}) and
    None when the answer has no body.
    """

    def __init__(self, token_file: str | os.PathLike | None = None, session: requests.Session | None = None,
                 user_agent: str = USER_AGENT, timeout: float = 30):
        self.token_file = Path(token_file).expanduser() if token_file else default_token_file()
        self.session = session or requests.Session()
        self.headers = {"Accept": "application/json", "User-Agent": user_agent}
        self.timeout = timeout
        self._user_id: int | None = None

    # ======================================================================
    # Tokens and login
    # ======================================================================

    def save_tokens(self, token: dict) -> None:
        """Write the token file atomically with mode 600, adding "expires_at". [Helper]"""
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
        """The stored tokens; raises LoginRequired when there is no token file. [Helper]"""
        if not self.token_file.exists():
            raise LoginRequired(f"no token file at {self.token_file}")
        return json.loads(self.token_file.read_text(encoding="utf-8"))

    def exchange_code(self, code: str, verifier: str) -> dict:
        """Swap an authorization code for tokens (POST oauth2/token) and store them. [Verified]"""
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
        """A valid access token; refreshes it (POST oauth2/token/refresh) when it is about to expire. [Verified]"""
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
        """Open a browser window on oauth2/authorize, let the user log in, and store the tokens. [Verified]"""
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

    def logout(self, device_token: str | None = None, push_id: int = -1, *, confirm: bool = False):
        """Log out on the server and drop the device's push registration; needs confirm=True. [From app code]"""
        return self._json("POST", "v1/oauth/logout", json={"device_token": device_token, "push_id": push_id},
                          confirm=confirm)

    # ======================================================================
    # HTTP
    # ======================================================================

    def request(self, method: str, path: str, *, auth: bool = True, confirm: bool = False, check: bool = True,
                base: str = API, timeout: float | None = None, headers: dict | None = None, **kwargs):
        """Call any endpoint and return the raw response: the escape hatch for what has no wrapper. [Helper]

        `path` is relative to the API base ("v3/products"; a leading "/" or
        "/api/" is fine) or a full URL. The remaining keyword arguments go to
        `requests` (params=, json=, data=, files=). `auth=False` leaves the
        token out, `check=False` returns error answers instead of raising, and
        guarded calls (see GUARDED) need `confirm=True`.
        """
        method = method.upper()
        url = api_url(path, base)
        if is_guarded(method, url) and not confirm:
            raise ConfirmationRequired(f"{method} {path} deletes, pays, orders or logs out: pass confirm=True")
        merged = {**self.headers, **(headers or {})}
        if auth:
            if urlsplit(url).hostname != API_HOST:
                raise RemaError("the access token is only sent to REMA's API; use auth=False for other hosts")
            merged["Authorization"] = "Bearer " + self.access_token()
        response = self.session.request(method, url, headers=merged, timeout=timeout or self.timeout, **kwargs)
        if check:
            if auth and response.status_code == 401:
                raise LoginRequired("the backend rejected the access token")
            response.raise_for_status()
        return response

    # The name the method had before it became public.
    _request = request

    def _json(self, method: str, path: str, **kwargs):
        """`request`, returning the parsed JSON body (None when there is none)."""
        response = self.request(method, path, **kwargs)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def _user_path(self, suffix: str = "") -> str:
        return f"v3/users/{self.user_id()}{suffix}"

    def pages(self, path: str, params: dict | None = None, *, auth: bool = True, per_page: int = 100,
              max_pages: int = MAX_PAGES, base: str = API) -> list:
        """Every item of a paginated v3 listing, following meta.pagination.last_page. [Helper]"""
        items: list = []
        page = 1
        while page <= max_pages:
            body = self._json("GET", path, auth=auth, base=base,
                              params={**(params or {}), "per_page": per_page, "page": page}) or {}
            items += body.get("data") or []
            if page >= int(((body.get("meta") or {}).get("pagination") or {}).get("last_page") or 1):
                break
            page += 1
        return items

    def batch(self, requests_: list[dict], *, confirm: bool = False):
        """Several API calls in one request: [{"method", "uri": "/api/...", "parameters": {...}}]. [From app code]"""
        if not confirm and any(is_guarded(str(r.get("method") or ""), str(r.get("uri") or "")) for r in requests_):
            raise ConfirmationRequired("the batch holds a call that deletes, pays, orders or logs out: "
                                       "pass confirm=True")
        return self._json("POST", "v3/batch", json={"requests": requests_})

    # ======================================================================
    # Account and profile
    # ======================================================================

    def user(self) -> dict:
        """The logged-in user's profile (GET v1/user). [Verified]"""
        return self._json("GET", "v1/user")

    def user_id(self) -> int:
        """The numeric id of the logged-in user, fetched once and cached. [Helper]"""
        if self._user_id is None:
            user_id = self.user().get("id")
            if not user_id:
                raise RemaError("the user profile carried no id")
            self._user_id = int(user_id)
        return self._user_id

    def update_user(self, **fields) -> dict:
        """Change profile fields (name, email, phone_number, acceptNotifications, favorite_meta_store ...). [From app code]"""
        return self._json("POST", "v1/user", json=fields)

    def set_user_photo(self, photo: bytes | str):
        """Set the profile picture; bytes are sent base64-encoded, a string as it is. [From app code]"""
        if isinstance(photo, (bytes, bytearray)):
            photo = base64.b64encode(photo).decode("ascii")
        return self._json("POST", "v1/user/photo", json={"photo": photo})

    def delete_account(self, *, confirm: bool = False):
        """Delete the logged-in user's account for good; needs confirm=True. [From app code]"""
        return self._json("POST", "v1/user/delete", confirm=confirm)

    def gdpr_export(self):
        """Order an export of the account's personal data (it arrives by e-mail). [From app code]"""
        return self._json("POST", "v1/user/gdpr-export")

    def find_friends_by_email(self, emails: list[str]) -> list[dict]:
        """REMA users behind the given e-mail addresses (used when sharing a list). [From app code]"""
        return self._json("POST", "v1/user/friends/emails", data=[("emails[]", email) for email in emails])

    def find_friends_by_number(self, numbers: list[str]) -> list[dict]:
        """REMA users behind the given phone numbers (used when sharing a list). [From app code]"""
        return self._json("POST", "v1/user/friends/numbers", data=[("numbers[]", number) for number in numbers])

    def user_details(self, include: str = "sponsor-club,active_bank_account,pending_shopper_suspension,type") -> dict:
        """The extended profile: type, notification switches, club, bank account. [From app code]"""
        return self._json("GET", self._user_path(), params={"include": include})

    def update_user_details(self, **fields) -> dict:
        """Change the extended profile (is_favorite_notification_enabled, is_driving_book_enabled ...). [From app code]"""
        return self._json("PATCH", self._user_path(), json=fields)

    # ---- identity verification (MitID) -----------------------------------

    def identity_token(self, redirect_uri: str = URL_SCHEME + "://apps/rema1000/user/identity/verified",
                       failed_uri: str = URL_SCHEME + "://apps/rema1000/user/identity/failed",
                       cancelled_uri: str = URL_SCHEME + "://apps/rema1000/user/identity/cancelled",
                       resume_uri: str = SHOP_URL + "/apps/rema1000/user/resume") -> dict:
        """A one-time token for the MitID validation page. [From app code]"""
        return self._json("GET", "identity-verification/token", params={
            "redirect_uri": redirect_uri, "failed_uri": failed_uri, "cancelled_uri": cancelled_uri,
            "resume_uri": resume_uri})

    def identity_login_url(self, token: str, platform: str = "android") -> str:
        """The MitID page to open in a browser with a token from identity_token(). [From app code]"""
        return API + "identity-verification/login?" + urlencode({"token": token, "platform": platform})

    # ---- addresses -------------------------------------------------------

    def add_address(self, dawa_address_id: str, description: str = "", is_primary: bool = False) -> dict:
        """Save a delivery address; the id comes from address_autocomplete(). [From app code]"""
        return self._json("POST", self._user_path("/addresses"), json={
            "dawa_address_id": dawa_address_id, "description": description, "is_primary": is_primary})

    def update_address(self, address_id: int, description: str | None = None,
                       dawa_address_id: str | None = None) -> dict:
        """Change the note on a saved address, or point it at another address. [From app code]"""
        return self._json("PATCH", self._user_path(f"/addresses/{address_id}"),
                          data=without_none(description=description, dawa_address_id=dawa_address_id))

    def delete_address(self, address_id: int):
        """Remove a saved address. [From app code]"""
        return self._json("DELETE", self._user_path(f"/addresses/{address_id}"))

    # ---- policies and consents -------------------------------------------

    def policies(self, include: str = "current_version", per_page: int = 100, auth: bool = False) -> dict:
        """The policies a user can accept; with auth=True and include="accepted_version,current_version" also what is accepted. [Verified]"""
        return self._json("GET", "v3/policies", auth=auth, params={"include": include, "per_page": per_page})

    def accept_policy(self, policy_version_id: int):
        """Give consent to a policy version (the id from current_version.id). [From app code]"""
        return self._json("POST", self._user_path("/policy-versions"), json={"policy_version_id": policy_version_id})

    def revoke_policy(self, policy_version_id: int, *, confirm: bool = False):
        """Withdraw a consent, which can erase purchase history or close services; needs confirm=True. [From app code]"""
        return self._json("DELETE", self._user_path(f"/policy-versions/{policy_version_id}"), confirm=confirm)

    # ---- newsletters and push --------------------------------------------

    def newsletters(self, per_page: int = 100) -> dict:
        """The newsletters one can subscribe to (no login). [Verified]"""
        return self._json("GET", "v3/newsletters", auth=False, params={"per_page": per_page})

    def newsletter_subscriptions(self, per_page: int = 100) -> dict:
        """The account's newsletter subscriptions. [From app code]"""
        return self._json("GET", self._user_path("/newsletter-subscriptions"), params={"per_page": per_page})

    def subscribe_newsletter(self, newsletter_id: int) -> dict:
        """Subscribe the account to a newsletter. [From app code]"""
        return self._json("POST", self._user_path("/newsletter-subscriptions"), json={"newsletter_id": newsletter_id})

    def unsubscribe_newsletter(self, subscription_id: int):
        """Cancel a subscription (the subscription's id, not the newsletter's). [From app code]"""
        return self._json("DELETE", self._user_path(f"/newsletter-subscriptions/{subscription_id}"))

    def register_push(self, token: str, app_identifier: str = "dk.iroots.rema1000", app_version: str = "6.9.0",
                      service: str = "fcm", language: str = "da") -> dict:
        """Register a device's push token so the server can send notifications. [From app code]"""
        return self._json("POST", "v1/push/register", json={
            "service": service, "app_identifier": app_identifier, "app_version": app_version,
            "token": token, "language": language})

    # ---- app configuration (no login) ------------------------------------

    def settings(self) -> dict:
        """The app's global settings (closed flags, status text and so on). [Verified]"""
        return self._json("GET", "v1/settings", auth=False)

    def feature_flags(self, per_page: int = 1000) -> dict:
        """The app's feature flags. [Verified]"""
        return self._json("GET", "v3/feature-flags", auth=False, params={"per_page": per_page})

    def campaigns(self) -> list[dict]:
        """Campaign banners and service messages shown to everybody. [Verified]"""
        return self._json("GET", "v1/campaigns", auth=False)

    def user_campaigns(self) -> list[dict]:
        """Campaign banners for the logged-in user. [From app code]"""
        return self._json("GET", "v1/user/campaigns")

    # ======================================================================
    # Shopping lists
    # ======================================================================

    def poll_lists(self, unixtime: int = 0) -> dict:
        """The polling answer as it is: {"response": lists, "unixtime", "wait", "settings"}. [Verified]"""
        return self._json("GET", "v1/shoppinglists/polling", params={"unixtime": unixtime})

    def lists(self) -> list[dict]:
        """All shopping lists with their items. [Verified]"""
        return self.poll_lists().get("response") or []

    def find_list(self, list_id: int) -> dict:
        """The shopping list with the given id, or RemaError. [Helper]"""
        for shopping_list in self.lists():
            if shopping_list.get("id") == list_id:
                return shopping_list
        raise RemaError(f"no shopping list with id {list_id}")

    def sync(self, changes: list[dict]) -> list[dict]:
        """Push list changes the way the app syncs them; returns the updated lists. [Verified]"""
        body = self._json("POST", "v1/sync/shoppinglists-v2", json={"changes": changes}) or {}
        if body.get("error_code"):
            raise RemaError(f"the change was rejected: {body.get('error_message') or body.get('error_code')}")
        return body.get("response") or []

    def create_list(self, name: str, items: list[dict] | None = None) -> dict:
        """Create a shopping list, optionally with items (see new_item); returns the new list. [Verified]"""
        offline_id = str(uuid.uuid4())
        change = {"offlineId": offline_id, "name": name}
        if items:
            change["items"] = items
        for shopping_list in self.sync([change]):
            if shopping_list.get("offlineId") == offline_id:
                return shopping_list
        raise RemaError("the new list did not come back in the answer")

    def rename_list(self, list_id: int, name: str) -> dict:
        """Give a shopping list a new name; returns the list. [Verified]"""
        # A change to a list the account does not own is ignored without an
        # error, so the answer has to be checked.
        for shopping_list in self.sync([{"id": list_id, "name": name}]):
            if shopping_list.get("id") == list_id and shopping_list.get("name") == name:
                return shopping_list
        raise RemaError(f"the list {list_id} was not renamed (is it one of the account's lists?)")

    def delete_list(self, list_id: int) -> list[dict]:
        """Delete a shopping list with its items, at once and for good; returns the remaining lists. [Verified]"""
        known = any(shopping_list.get("id") == list_id for shopping_list in self.lists())
        if not known:
            raise RemaError(f"no shopping list with id {list_id}")
        remaining = self.sync([{"id": list_id, "deleted": True}])
        if any(shopping_list.get("id") == list_id for shopping_list in remaining):
            raise RemaError(f"the list {list_id} was not deleted")
        return remaining

    def add_item(self, list_id: int, list_name: str, name: str, store_item_id: int, amount: int = 1,
                 store_id: int = DEFAULT_STORE_ID) -> list[dict]:
        """Add one catalogue product to a shopping list. [Verified]"""
        return self.sync([list_change(list_id, list_name, [new_item(name, store_item_id, amount, store_id)])])

    def set_amount(self, list_id: int, list_name: str, item_id: int, amount: int) -> list[dict]:
        """Change how many of a product the list asks for (item_id is the list item's id). [Verified]"""
        return self.sync([list_change(list_id, list_name, [amount_change(item_id, amount)])])

    def remove_item(self, list_id: int, list_name: str, item_id: int) -> list[dict]:
        """Remove an item from a list (item_id is the list item's id). [Verified]"""
        return self.sync([list_change(list_id, list_name, [delete_change(item_id)])])

    def set_bought(self, list_id: int, list_name: str, item_id: int, bought: bool = True) -> list[dict]:
        """Tick an item off (or untick it). [From app code]"""
        return self.sync([list_change(list_id, list_name, [
            {"id": item_id, "source": ITEM_SOURCE, "bought": bought}])])

    def set_primary_list(self, list_id: int):
        """Make a list the primary one, the list the app opens by default. [From app code]"""
        return self._json("PATCH", f"v2/shoppinglists/{list_id}", json={"primary": True})

    def invite_to_list(self, list_id: int, emails: list[str]):
        """Invite people to a shopping list by e-mail. [From app code]"""
        return self._json("POST", f"v1/shoppinglist/{list_id}/invite", data=[("emails[]", email) for email in emails])

    def list_recommended_products(self, list_id: int, per_page: int = 20, page: int = 1) -> dict:
        """Products recommended from what is on a list. [Verified]"""
        return self._json("GET", f"v3/shopping-lists/{list_id}/recommended-products",
                          params={"per_page": per_page, "page": page})

    def list_suggestions(self) -> list[dict]:
        """The generic words the app suggests while typing on a list ({title, category}). [Verified]"""
        return self._json("GET", "v1/shoppinglistsuggestions", auth=False)

    # ======================================================================
    # Favourites and personal suggestions
    # ======================================================================

    def favorites(self, store_id: int = DEFAULT_STORE_ID) -> list[int]:
        """Catalogue ids of the products marked as favourites. [Verified]"""
        return [int(item["id"]) for item in self._json("GET", f"v1/favorites/{store_id}") or [] if item.get("id")]

    def add_favorite(self, product_id: int) -> None:
        """Mark a product as a favourite. [Verified]"""
        self.request("POST", self._user_path("/favorites"), params={"product_id": product_id})

    def add_favorites(self, product_ids: list[int]):
        """Mark several products as favourites in one batch call, as the app does. [From app code]"""
        uri = f"/api/{self._user_path('/favorites')}"
        return self.batch([{"method": "POST", "uri": uri, "parameters": {"product_id": str(product_id)}}
                           for product_id in product_ids])

    def remove_favorite(self, product_id: int, store_id: int = DEFAULT_STORE_ID) -> None:
        """Remove a product from the favourites. [Verified]"""
        self.request("DELETE", f"v1/favorites/{store_id}/{product_id}")

    def favorite_suggestions(self, max_pages: int = MAX_SUGGESTION_PAGES) -> list[int]:
        """Catalogue ids of products the account often buys but has not made favourites, best first. [Verified]"""
        items = self.pages(self._user_path("/favorite-suggestions"), per_page=50, max_pages=max_pages)
        return [int(item["id"]) for item in items if item.get("id")]

    def dismiss_favorite_suggestion(self, product_id: int):
        """Reject a favourite suggestion so it is not shown again. [From app code]"""
        return self._json("DELETE", self._user_path(f"/favorite-suggestions/{product_id}"))

    def frequently_bought(self, per_page: int = 20, page: int = 1) -> dict:
        """"You usually buy". [Verified: the test account got 403]"""
        return self._json("GET", self._user_path("/frequently-bought-products"),
                          params={"per_page": per_page, "page": page})

    def inspiration_products(self, per_page: int = 20, page: int = 1) -> dict:
        """"Maybe you would like". [From app code]"""
        return self._json("GET", self._user_path("/inspiration-products"), params={"per_page": per_page, "page": page})

    def dismiss_inspiration_product(self, product_id: int):
        """Reject an inspiration product. [From app code]"""
        return self._json("DELETE", self._user_path(f"/inspiration-products/{product_id}"))

    # ======================================================================
    # Products, search and catalogue (no login)
    # ======================================================================

    def catalog(self, store_id: int = DEFAULT_STORE_ID) -> dict:
        """The whole product catalogue (departments > categories > items), about 10 MB. [Verified]"""
        return self._json("GET", f"v1/catalog/store/{store_id}/withchildren", auth=False, timeout=120)

    def catalog_modified(self, store_id: int = DEFAULT_STORE_ID) -> int:
        """Unix time of the last catalogue change; poll this instead of the catalogue. [Verified]"""
        body = self._json("GET", f"v1/catalog/store/{store_id}/last_modified", auth=False)
        return int(body.get("last_modified") or 0)

    def products(self, per_page: int = 20, page: int = 1, sort: str | None = None, include: str | None = None,
                 advertised: bool | None = None, age_restricted: bool | None = None,
                 filters: dict | None = None) -> dict:
        """The paginated product list; sort is -popularity, -created_at, title or department_order. [Verified]"""
        params = without_none(per_page=per_page, page=page, sort=sort, include=include)
        named = {"is_advertised": query_flag(advertised), "age_restricted": query_flag(age_restricted),
                 **(filters or {})}
        params.update({f"filter[{key}]": value for key, value in named.items() if value is not None})
        return self._json("GET", "v3/products", auth=False, params=params)

    def offers(self, per_page: int = 100, page: int = 1) -> dict:
        """This week's advertised products, with their department. [Verified]"""
        return self.products(per_page=per_page, page=page, include="department", advertised=True)

    def all_offers(self) -> list[dict]:
        """Every advertised product, all pages. [Verified]"""
        return self.pages("v3/products", {"filter[is_advertised]": "true", "include": "department"}, auth=False)

    def product(self, product_id: int) -> dict:
        """One product. [Verified]"""
        return self._json("GET", f"v3/products/{product_id}", auth=False)

    def departments(self, categories: bool = True, per_page: int = 100, page: int = 1) -> dict:
        """The departments, with their categories unless categories=False. [Verified]"""
        params = {"per_page": per_page, "page": page}
        if categories:
            params["include"] = "categories"
        return self._json("GET", "v3/departments", auth=False, params=params)

    def category_products(self, department_id: int, category_id: int, per_page: int = 100, page: int = 1) -> dict:
        """The products in one category (v3 ids; the old catalogue calls the category's "id_v3"). [Verified]"""
        return self._json("GET", f"v3/departments/{department_id}/categories/{category_id}/products",
                          auth=False, params={"per_page": per_page, "page": page})

    def barcode(self, barcode: str, store_id: int | None = None) -> dict:
        """Look a barcode (EAN) up: name, product id and price. [Verified]"""
        return self._json("GET", f"v3/product-barcode/{quote(str(barcode), safe='')}", auth=False,
                          params=without_none(store_id=store_id))

    def search(self, query: str, per_page: int = 20, page: int = 1, filters: dict | None = None) -> dict:
        """The app's product search. [Verified]"""
        params = {"query": query, "per_page": per_page, "page": page}
        params.update({f"filter[{key}]": value for key, value in (filters or {}).items()})
        return self._json("GET", "search/products", auth=False, params=params)

    # ======================================================================
    # The weekly newspaper (Tjek, not REMA's own API)
    # ======================================================================

    def _tjek(self, method: str, path: str, **kwargs):
        headers = {**self.headers, "content-type": "application/json; charset=utf-8", "x-api-key": TJEK_API_KEY}
        response = self.session.request(method, TJEK_API + path, headers=headers, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json()

    def newspapers(self, dealer_id: str = TJEK_DEALER_ID) -> list[dict]:
        """The newspapers in force now and coming (GET /v2/catalogs at Tjek). [Verified]"""
        return self._tjek("GET", "/v2/catalogs", params={"dealer_id": dealer_id})

    def newspaper_pages(self, catalog_id: str) -> list[dict]:
        """The page images of a newspaper: [{thumb, view, zoom}]. [Verified: not used by the app]"""
        return self._tjek("GET", f"/v2/catalogs/{quote(str(catalog_id), safe='')}/pages")

    def newspaper_offers(self, catalog_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        """The offers printed in a newspaper (at most 100 per call). [Verified: not used by the app]"""
        return self._tjek("GET", "/v2/offers", params={"catalog_id": catalog_id, "limit": limit, "offset": offset})

    def newspaper_offer(self, offer_id: str) -> dict:
        """One offer from a newspaper. [Verified]"""
        return self._tjek("GET", f"/v2/offers/{quote(str(offer_id), safe='')}")

    def newspaper_offer_products(self, offer_id: str) -> dict:
        """The products behind an offer; "external_id" is REMA's product id. [From app code]"""
        return self._tjek("POST", "/v4/rpc/get_offer_products", json={"id": offer_id})

    def newspaper_viewer_url(self, publication_id: str) -> str:
        """The web page that shows a newspaper (the id from newspapers()). [Verified]"""
        return newspaper_viewer_url(publication_id)

    # ======================================================================
    # Front page content and recipes (no login unless noted)
    # ======================================================================

    def entities(self, type: str | None = None, slug: str | None = None, tag_id: str | None = None,
                 per_page: int = 20, page: int = 1, sort: str | None = None) -> dict:
        """Editorial content by type: appConfiguration, recipe or recipeTag. [Verified]"""
        params = without_none(**{"filter[type]": type, "filter[slug]": slug, "filter[tags.sys.id]": tag_id,
                                 "per_page": per_page, "page": page, "sort": sort})
        return self._json("GET", "entities", auth=False, base=CONTENT_API, params=params)

    def app_configuration(self) -> dict:
        """The building plan of the app's front page, pre-search screen and recipe screen. [Verified]"""
        return self.entities(type="appConfiguration", per_page=1)

    def recipes(self, per_page: int = 20, page: int = 1, sort: str | None = None, tag_id: str | None = None) -> dict:
        """Recipes, optionally only those carrying a tag. [Verified]"""
        return self.entities(type="recipe", tag_id=tag_id, per_page=per_page, page=page, sort=sort)

    def recipe(self, slug: str) -> dict:
        """One recipe by its slug. [From app code]"""
        return self.entities(type="recipe", slug=slug, per_page=1)

    def recipe_tags(self, per_page: int = 100, page: int = 1) -> dict:
        """The recipe tags. [Verified]"""
        return self.entities(type="recipeTag", per_page=per_page, page=page)

    def featured_recipes(self, group_id: str) -> dict:
        """The recipes in a featured group of the recipe screen. [Verified: only the answer to a missing group id]"""
        return self._json("GET", "featured-recipes", auth=False, base=CONTENT_API,
                          params={"filter[group_id]": group_id})

    def search_recipes(self, query: str, per_page: int = 20, page: int = 1, sort: str | None = None) -> dict:
        """The app's recipe search. [Verified]"""
        return self._json("GET", "search/recipes", auth=False,
                          params=without_none(query=query, per_page=per_page, page=page, sort=sort))

    def favorite_recipes(self, full: bool = False, per_page: int = 100, page: int = 1) -> dict:
        """The account's favourite recipes: only ids, or whole recipes with full=True. [From app code]"""
        params = {"include": "instructions"} if full else {"fields": "id"}
        return self._json("GET", self._user_path("/favorite-recipes"),
                          params={**params, "per_page": per_page, "page": page})

    def add_favorite_recipe(self, recipe_id: str):
        """Mark a recipe as a favourite (recipe_id is the entity's text id). [From app code]"""
        return self._json("POST", self._user_path("/favorite-recipes"), json={"recipe_id": recipe_id})

    def remove_favorite_recipe(self, recipe_id: str):
        """Remove a recipe from the favourites. [From app code]"""
        return self._json("DELETE", self._user_path(f"/favorite-recipes/{quote(str(recipe_id), safe='')}"))

    # ======================================================================
    # Stores and addresses
    # ======================================================================

    def stores(self, per_page: int = 1000, page: int = 1) -> dict:
        """All stores with address, opening hours and position (no login). [Verified]"""
        return self._json("GET", "v3/stores", auth=False, params={"per_page": per_page, "page": page})

    def stores_near(self, latitude: float, longitude: float, per_page: int = 3,
                    click_and_collect: bool | None = None) -> dict:
        """The stores closest to a position, optionally only those with click and collect. [Verified]"""
        params = without_none(**{"filter[near_coordinates]": f"{latitude},{longitude}",
                                 "filter[is_click_and_collect_active]": query_flag(click_and_collect),
                                 "per_page": per_page})
        return self._json("GET", "v3/stores", auth=False, params=params)

    def address_autocomplete(self, text: str, caretpos: int | None = None, start_from: str | None = None,
                             page: int = 1, per_page: int = 20) -> list[dict]:
        """Address suggestions from REMA's proxy for the Danish address register. [Verified]"""
        params = without_none(q=text, caretpos=len(text) if caretpos is None else caretpos, startfra=start_from,
                              multilinje="true", type="adresse", fuzzy="true", side=page, per_side=per_page)
        return self._json("GET", "autocomplete", auth=False, base=ADDRESS_API, params=params)


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


def _print_v3_products(products: list[dict]) -> None:
    for product in products:
        current = current_price(product)
        price = "" if current.get("price") is None else f"{current['price']:.2f} kr."
        offer = " (tilbud)" if current.get("is_advertised") or current.get("is_campaign") else ""
        print(f"{product.get('id'):>8}  {price:>11}{offer}  {product.get('name')}  [{product.get('underline') or ''}]")


def _print_page_note(body: dict) -> None:
    pagination = ((body or {}).get("meta") or {}).get("pagination") or {}
    if int(pagination.get("last_page") or 1) > 1:
        print(f"Side {pagination.get('current_page')} af {pagination.get('last_page')} "
              f"({pagination.get('total')} i alt)", file=sys.stderr)


def _cmd_login(client: Rema1000, args) -> int:
    print("Log ind med din REMA 1000-konto i browservinduet ...")
    client.login()
    print(f"Logget ind. Adgangsbeviset er gemt i {client.token_file}")
    return 0


def _cmd_logout(client: Rema1000, args) -> int:
    client.logout(confirm=args.yes)
    print("Logget ud på serveren")
    return 0


def _cmd_user(client: Rema1000, args) -> int:
    _print_json(client.user())
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


def _cmd_list_create(client: Rema1000, args) -> int:
    shopping_list = client.create_list(args.name)
    print(f"Oprettet: {shopping_list.get('name')}  (liste-id {shopping_list.get('id')})")
    return 0


def _cmd_list_rename(client: Rema1000, args) -> int:
    client.rename_list(args.list_id, args.name)
    print(f"Listen hedder nu {args.name}")
    return 0


def _cmd_list_delete(client: Rema1000, args) -> int:
    client.delete_list(args.list_id)
    print("Listen er slettet")
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


def _cmd_search(client: Rema1000, args) -> int:
    body = client.search(" ".join(args.text), per_page=args.per_page, page=args.page)
    if args.json:
        _print_json(body)
        return 0
    _print_v3_products(body.get("data") or [])
    _print_page_note(body)
    return 0


def _cmd_offers(client: Rema1000, args) -> int:
    if args.all:
        products = client.all_offers()
        body = {"data": products}
    else:
        body = client.offers(per_page=args.per_page, page=args.page)
        products = body.get("data") or []
    if args.json:
        _print_json(body)
        return 0
    _print_v3_products(products)
    _print_page_note(body)
    return 0


def _cmd_product(client: Rema1000, args) -> int:
    _print_json(client.product(args.product_id))
    return 0


def _cmd_barcode(client: Rema1000, args) -> int:
    _print_json(client.barcode(args.barcode))
    return 0


def _cmd_departments(client: Rema1000, args) -> int:
    body = client.departments()
    if args.json:
        _print_json(body)
        return 0
    for department in body.get("data") or []:
        print(f"{department.get('id'):>6}  {department.get('name')}")
        for category in department.get("categories") or []:
            hidden = "  (skjult)" if category.get("is_hidden") else ""
            print(f"        {category.get('id'):>6}  {category.get('name')}{hidden}")
    return 0


def _cmd_stores(client: Rema1000, args) -> int:
    if args.near:
        try:
            latitude, longitude = (float(part) for part in args.near.split(","))
        except ValueError:
            print("--near skal være BREDDEGRAD,LÆNGDEGRAD, fx 55.0,10.0", file=sys.stderr)
            return 2
        body = client.stores_near(latitude, longitude, per_page=args.limit or 3,
                                  click_and_collect=True if args.collect else None)
        stores = body.get("data") or []
    else:
        body = client.stores()
        stores = body.get("data") or []
        if args.collect:
            stores = [store for store in stores if store.get("is_click_and_collect_active")]
    if args.search:
        words = args.search.casefold().split()
        stores = [store for store in stores if all(
            word in " ".join(str(store.get(key) or "") for key in ("name", "address", "postal_code", "city")).casefold()
            for word in words)]
    if args.limit:
        stores = stores[:args.limit]
    if args.json:
        _print_json(stores)
        return 0
    for store in stores:
        print(f"{store.get('id'):>6}  {store.get('name')}  –  {store.get('address')}, "
              f"{store.get('postal_code')} {store.get('city')}")
    return 0


def _cmd_newspaper(client: Rema1000, args) -> int:
    if args.url:
        print(client.newspaper_viewer_url(args.url))
        return 0
    if args.offer:
        _print_json(client.newspaper_offer(args.offer))
        return 0
    if args.pages:
        pages = client.newspaper_pages(args.pages)
        if args.json:
            _print_json(pages)
        else:
            for number, page in enumerate(pages, 1):
                print(f"{number:>3}  {page.get('zoom') or page.get('view')}")
        return 0
    if args.offers:
        offers = client.newspaper_offers(args.offers, limit=args.limit, offset=args.offset)
        if args.json:
            _print_json(offers)
        else:
            for offer in offers:
                price = (offer.get("pricing") or {}).get("price")
                price = "" if price is None else f"{price:.2f} kr."
                print(f"{offer.get('id')}  s. {offer.get('catalog_page')!s:>2}  {price:>11}  {offer.get('heading')}")
        return 0
    newspapers = client.newspapers()
    if args.json:
        _print_json(newspapers)
        return 0
    for newspaper in newspapers:
        print(f"{newspaper.get('id')}  {newspaper.get('label')}  "
              f"{str(newspaper.get('run_from'))[:10]} til {str(newspaper.get('run_till'))[:10]}  "
              f"({newspaper.get('page_count')} sider, {newspaper.get('offer_count')} tilbud)")
    return 0


def _cmd_recipes(client: Rema1000, args) -> int:
    if args.slug:
        _print_json(client.recipe(args.slug))
        return 0
    if args.tags:
        body = client.recipe_tags()
    elif args.search:
        body = client.search_recipes(args.search, per_page=args.per_page, page=args.page)
    else:
        body = client.recipes(per_page=args.per_page, page=args.page, sort=args.sort, tag_id=args.tag)
    if args.json:
        _print_json(body)
        return 0
    for entity in body.get("data") or []:
        fields = entity.get("fields") or {}
        if args.tags:
            print(f"{entity.get('id')}  {fields.get('title')}")
        else:
            print(f"{fields.get('slug')}  –  {fields.get('title')}")
    _print_page_note(body)
    return 0


def _cmd_api(client: Rema1000, args) -> int:
    kwargs = {}
    if args.query:
        pairs = [pair.partition("=") for pair in args.query]
        if any(not separator for _, separator, _ in pairs):
            print("--query skal være NAVN=VÆRDI", file=sys.stderr)
            return 2
        kwargs["params"] = [(key, value) for key, _, value in pairs]
    if args.json is not None:
        try:
            kwargs["json"] = json.loads(args.json)
        except ValueError as error:
            print(f"--json er ikke gyldig JSON: {error}", file=sys.stderr)
            return 2
    try:
        response = client.request(args.method, args.path, auth=not args.no_auth, confirm=args.yes, check=False,
                                  **kwargs)
    except ConfirmationRequired:
        print("Kaldet sletter, betaler, bestiller eller logger ud. Gentag med --yes, hvis det er meningen.",
              file=sys.stderr)
        return 2
    print(f"HTTP {response.status_code}", file=sys.stderr)
    try:
        _print_json(response.json())
    except ValueError:
        if response.text:
            print(response.text)
    return 0 if response.status_code < 400 else 1


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

    def paging(p, per_page: int) -> None:
        p.add_argument("--per-page", type=int, default=per_page, metavar="N", help=f"antal pr. side (standard: {per_page})")
        p.add_argument("--page", type=int, default=1, metavar="N", help="sidenummer (standard: 1)")

    p = sub.add_parser("login", help="log ind i et browservindue (kræver playwright)")
    p.set_defaults(func=_cmd_login)

    p = sub.add_parser("logout", help="log ud på serveren (kræver --yes)")
    p.add_argument("--yes", action="store_true", help="bekræft, at du vil logge ud")
    p.set_defaults(func=_cmd_logout)

    p = sub.add_parser("user", help="vis den indloggede brugers profil som JSON")
    p.add_argument("--json", action="store_true", help="(profilen skrives altid som JSON)")
    p.set_defaults(func=_cmd_user)

    p = sub.add_parser("lists", help="vis indkøbslisterne")
    p.add_argument("--json", action="store_true", help="skriv API'ets svar som JSON")
    p.set_defaults(func=_cmd_lists)

    p = sub.add_parser("list-create", help="opret en indkøbsliste")
    p.add_argument("name", help="listens navn")
    p.set_defaults(func=_cmd_list_create)

    p = sub.add_parser("list-rename", help="omdøb en indkøbsliste")
    p.add_argument("list_id", type=int, help="listens id")
    p.add_argument("name", help="det nye navn")
    p.set_defaults(func=_cmd_list_rename)

    p = sub.add_parser("list-delete", help="slet en indkøbsliste med alt, hvad der står på den")
    p.add_argument("list_id", type=int, help="listens id")
    p.set_defaults(func=_cmd_list_delete)

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

    p = sub.add_parser("search", help="søg efter varer med appens søgning (kræver ikke login)")
    p.add_argument("text", nargs="+", metavar="TEKST", help="søgeteksten")
    paging(p, 20)
    p.add_argument("--json", action="store_true", help="skriv API'ets svar som JSON")
    p.set_defaults(func=_cmd_search)

    p = sub.add_parser("offers", help="ugens avisvarer (kræver ikke login)")
    paging(p, 100)
    p.add_argument("--all", action="store_true", help="hent alle sider")
    p.add_argument("--json", action="store_true", help="skriv API'ets svar som JSON")
    p.set_defaults(func=_cmd_offers)

    p = sub.add_parser("product", help="vis én vare som JSON (kræver ikke login)")
    p.add_argument("product_id", type=int, help="varens id")
    p.set_defaults(func=_cmd_product)

    p = sub.add_parser("barcode", help="slå en stregkode op (kræver ikke login)")
    p.add_argument("barcode", help="stregkoden (EAN)")
    p.set_defaults(func=_cmd_barcode)

    p = sub.add_parser("departments", help="afdelinger og kategorier (kræver ikke login)")
    p.add_argument("--json", action="store_true", help="skriv API'ets svar som JSON")
    p.set_defaults(func=_cmd_departments)

    p = sub.add_parser("stores", help="butikker (kræver ikke login)")
    p.add_argument("--near", metavar="BREDDE,LÆNGDE", help="de nærmeste butikker til en position, fx 55.0,10.0")
    p.add_argument("--collect", action="store_true", help="kun butikker med afhentning")
    p.add_argument("--search", metavar="TEKST", help="kun butikker, hvor navn eller adresse indeholder alle ordene")
    p.add_argument("--limit", type=int, metavar="N", help="højst N butikker (standard ved --near: 3)")
    p.add_argument("--json", action="store_true", help="skriv butikkerne som JSON med åbningstider")
    p.set_defaults(func=_cmd_stores)

    p = sub.add_parser("newspaper", help="tilbudsavisen fra Tjek (kræver ikke login)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--pages", metavar="AVIS_ID", help="avisens sider som billed-links")
    group.add_argument("--offers", metavar="AVIS_ID", help="tilbuddene i avisen")
    group.add_argument("--offer", metavar="TILBUDS_ID", help="ét tilbud som JSON")
    group.add_argument("--url", metavar="AVIS_ID", help="link til at bladre i avisen i en browser")
    p.add_argument("--limit", type=int, default=100, metavar="N", help="antal tilbud ved --offers (højst 100)")
    p.add_argument("--offset", type=int, default=0, metavar="N", help="spring de første N tilbud over ved --offers")
    p.add_argument("--json", action="store_true", help="skriv Tjeks svar som JSON")
    p.set_defaults(func=_cmd_newspaper)

    p = sub.add_parser("recipes", help="opskrifter (kræver ikke login)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--search", metavar="TEKST", help="søg i opskrifterne")
    group.add_argument("--slug", metavar="SLUG", help="én opskrift som JSON")
    group.add_argument("--tags", action="store_true", help="vis opskrifts-tags med id")
    p.add_argument("--tag", metavar="TAG_ID", help="kun opskrifter med dette tag")
    p.add_argument("--sort", choices=["title", "-created_at", "-popularity"], help="sortering")
    paging(p, 20)
    p.add_argument("--json", action="store_true", help="skriv API'ets svar som JSON")
    p.set_defaults(func=_cmd_recipes)

    p = sub.add_parser("api", help="kald et vilkårligt endpoint og skriv svaret som JSON",
                       description="Kalder et vilkårligt endpoint. STI er relativ til "
                                   f"{API} (fx v3/products) eller en hel URL.")
    p.add_argument("method", metavar="METODE", help="GET, POST, PATCH eller DELETE")
    p.add_argument("path", metavar="STI", help="fx v3/products eller v1/user")
    p.add_argument("--query", nargs="*", default=[], metavar="NAVN=VÆRDI", help="query-parametre")
    p.add_argument("--json", metavar="JSON", help="body som JSON-tekst")
    p.add_argument("--no-auth", action="store_true", help="send ikke adgangsbeviset med (åbne endpoints)")
    p.add_argument("--yes", action="store_true", help="bekræft et kald, der sletter, betaler, bestiller eller logger ud")
    p.set_defaults(func=_cmd_api)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = Rema1000(token_file=args.token_file)
    try:
        return args.func(client, args)
    except LoginRequired as error:
        print(f"REMA kræver login (kør: rema1000.py login). [{error}]", file=sys.stderr)
        return 1
    except ConfirmationRequired:
        print("Kaldet sletter, betaler, bestiller eller logger ud. Gentag med --yes, hvis det er meningen.",
              file=sys.stderr)
        return 2
    except (RemaError, requests.RequestException) as error:
        print(f"Fejl: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
