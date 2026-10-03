"""Offline unit tests: nothing here talks to the network."""

import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rema1000  # noqa: E402


def response(status=200, body=None):
    fake = mock.Mock()
    fake.status_code = status
    fake.json.return_value = body if body is not None else {}
    if status >= 400:
        fake.raise_for_status.side_effect = rema1000.requests.HTTPError(f"{status}")
    return fake


class ClientCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.token_file = Path(self.dir.name) / "conf" / "tokens.json"
        self.session = mock.Mock()
        self.client = rema1000.Rema1000(token_file=self.token_file, session=self.session)

    def write_tokens(self, expires_in=3600, **extra):
        self.client.save_tokens({"access_token": "old-access", "refresh_token": "old-refresh",
                                 "expires_in": expires_in, **extra})


class PkceTest(unittest.TestCase):
    def test_challenge_matches_rfc7636_example(self):
        # Appendix B of RFC 7636.
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        self.assertEqual(rema1000.pkce_challenge(verifier), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_challenge_has_no_padding(self):
        self.assertNotIn("=", rema1000.pkce_challenge("a" * 43))


class AuthorizeUrlTest(unittest.TestCase):
    def test_url_carries_the_expected_query(self):
        url = rema1000.authorize_url("verifier-value", "state-value")
        parts = urlsplit(url)
        self.assertEqual(f"{parts.scheme}://{parts.netloc}{parts.path}",
                         "https://api.digital.rema1000.dk/api/oauth2/authorize")
        query = parse_qs(parts.query, keep_blank_values=True)
        self.assertEqual(query, {
            "client_id": ["rema1000-app"],
            "redirect_uri": ["dk.rema1000.vigo://logincallback"],
            "state": ["state-value"],
            "code_challenge": [rema1000.pkce_challenge("verifier-value")],
            "code_challenge_method": ["S256"],
            "scope": [""],
            "response_type": ["code"],
            "theme": ["light"],
        })


class CallbackTest(unittest.TestCase):
    def test_code_is_extracted(self):
        url = "dk.rema1000.vigo://logincallback?code=abc123&state=s1"
        self.assertEqual(rema1000.code_from_callback(url, "s1"), "abc123")

    def test_wrong_state_is_rejected(self):
        with self.assertRaises(rema1000.RemaError):
            rema1000.code_from_callback("dk.rema1000.vigo://logincallback?code=abc123&state=other", "s1")

    def test_missing_code_is_rejected(self):
        with self.assertRaises(rema1000.RemaError):
            rema1000.code_from_callback("dk.rema1000.vigo://logincallback?state=s1", "s1")


class TokenBodyTest(unittest.TestCase):
    def test_wrapped_and_bare_tokens(self):
        token = {"access_token": "a", "refresh_token": "r"}
        self.assertEqual(rema1000.token_from_body({"tokens": token}), token)
        self.assertEqual(rema1000.token_from_body(token), token)

    def test_missing_access_token(self):
        with self.assertRaises(rema1000.RemaError):
            rema1000.token_from_body({"tokens": {"refresh_token": "r"}})


class TokenFileTest(ClientCase):
    def test_save_adds_expiry_and_restricts_mode(self):
        before = time.time()
        self.write_tokens(expires_in=3600)
        data = json.loads(self.token_file.read_text(encoding="utf-8"))
        self.assertEqual(data["access_token"], "old-access")
        self.assertAlmostEqual(data["expires_at"], before + 3600, delta=5)
        self.assertFalse(self.token_file.with_name("tokens.json.tmp").exists())
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.token_file.stat().st_mode), 0o600)

    def test_env_overrides_default_path(self):
        with mock.patch.dict(os.environ, {rema1000.TOKEN_FILE_ENV: "/somewhere/else.json"}):
            self.assertEqual(rema1000.Rema1000(session=self.session).token_file, Path("/somewhere/else.json"))
        with mock.patch.dict(os.environ):
            os.environ.pop(rema1000.TOKEN_FILE_ENV, None)
            self.assertEqual(rema1000.Rema1000(session=self.session).token_file, rema1000.DEFAULT_TOKEN_FILE)

    def test_missing_file_requires_login(self):
        with self.assertRaises(rema1000.LoginRequired):
            self.client.access_token()
        self.session.post.assert_not_called()

    def test_valid_token_is_used_without_refresh(self):
        self.write_tokens(expires_in=3600)
        self.assertEqual(self.client.access_token(), "old-access")
        self.session.post.assert_not_called()

    def test_expiring_token_is_refreshed_and_rotated(self):
        self.write_tokens(expires_in=rema1000.EXPIRY_MARGIN - 10)
        self.session.post.return_value = response(body={"tokens": {
            "access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600, "token_type": "Bearer"}})
        self.assertEqual(self.client.access_token(), "new-access")
        url = self.session.post.call_args.args[0]
        self.assertEqual(url, rema1000.API + "oauth2/token/refresh")
        self.assertEqual(self.session.post.call_args.kwargs["json"], {
            "grant_type": "refresh_token", "client_id": "rema1000-app", "refresh_token": "old-refresh"})
        stored = json.loads(self.token_file.read_text(encoding="utf-8"))
        self.assertEqual(stored["refresh_token"], "new-refresh")
        self.assertGreater(stored["expires_at"], time.time() + 3000)

    def test_refresh_keeps_old_refresh_token_when_none_is_returned(self):
        self.write_tokens(expires_in=0)
        self.session.post.return_value = response(body={"access_token": "new-access", "expires_in": 3600})
        self.client.access_token()
        self.assertEqual(json.loads(self.token_file.read_text(encoding="utf-8"))["refresh_token"], "old-refresh")

    def test_rejected_refresh_requires_login_and_keeps_file(self):
        self.write_tokens(expires_in=0)
        self.session.post.return_value = response(status=401, body={"error": "access_denied"})
        with self.assertRaises(rema1000.LoginRequired):
            self.client.access_token()
        self.assertEqual(json.loads(self.token_file.read_text(encoding="utf-8"))["refresh_token"], "old-refresh")

    def test_exchange_code_posts_pkce_verifier_and_saves(self):
        self.session.post.return_value = response(body={"tokens": {
            "access_token": "first-access", "refresh_token": "first-refresh", "expires_in": 3600}})
        self.client.exchange_code("the-code", "the-verifier")
        self.assertEqual(self.session.post.call_args.args[0], rema1000.API + "oauth2/token")
        self.assertEqual(self.session.post.call_args.kwargs["json"], {
            "grant_type": "authorization_code", "client_id": "rema1000-app",
            "redirect_uri": "dk.rema1000.vigo://logincallback", "code": "the-code", "code_verifier": "the-verifier"})
        self.assertEqual(self.client.load_tokens()["access_token"], "first-access")


class ChangeTest(unittest.TestCase):
    def test_new_item(self):
        item = rema1000.new_item("Example product", 123456, amount=2)
        self.assertEqual(len(item.pop("offlineId")), 36)
        self.assertEqual(item, {"name": "Example product", "source": "android_search", "amount": 2,
                                "bought": False, "store_id": 1, "store_item_id": 123456})

    def test_amount_and_delete(self):
        self.assertEqual(rema1000.amount_change(900001, 3), {"id": 900001, "source": "android_search", "amount": 3})
        self.assertEqual(rema1000.delete_change(900001), {"id": 900001, "source": "android_search", "deleted": True})


class RequestTest(ClientCase):
    def setUp(self):
        super().setUp()
        self.write_tokens()

    def test_lists_sends_bearer_token(self):
        self.session.request.return_value = response(body={"response": [{"id": 1001, "name": "Example list"}]})
        self.assertEqual(self.client.lists(), [{"id": 1001, "name": "Example list"}])
        args, kwargs = self.session.request.call_args
        self.assertEqual(args, ("GET", rema1000.API + "v1/shoppinglists/polling"))
        self.assertEqual(kwargs["params"], {"unixtime": 0})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer old-access")

    def test_remove_item_builds_sync_body(self):
        self.session.request.return_value = response(body={"response": []})
        self.client.remove_item(1001, "Example list", 900001)
        args, kwargs = self.session.request.call_args
        self.assertEqual(args, ("POST", rema1000.API + "v1/sync/shoppinglists-v2"))
        self.assertEqual(kwargs["json"], {"changes": [{"id": 1001, "name": "Example list", "items": [
            {"id": 900001, "source": "android_search", "deleted": True}]}]})

    def test_sync_error_body_raises(self):
        self.session.request.return_value = response(body={"error_code": 7, "error_message": "nope"})
        with self.assertRaises(rema1000.RemaError):
            self.client.set_amount(1001, "Example list", 900001, 2)

    def test_401_requires_login(self):
        self.session.request.return_value = response(status=401, body={"error": "access_denied"})
        with self.assertRaises(rema1000.LoginRequired):
            self.client.lists()

    def test_public_endpoint_sends_no_token(self):
        self.token_file.unlink()
        self.session.request.return_value = response(body={"last_modified": 1700000000})
        self.assertEqual(self.client.catalog_modified(), 1700000000)
        args, kwargs = self.session.request.call_args
        self.assertEqual(args, ("GET", rema1000.API + "v1/catalog/store/1/last_modified"))
        self.assertNotIn("Authorization", kwargs["headers"])

    def test_favorite_suggestions_follow_pagination(self):
        def page(n, last):
            return response(body={"data": [{"id": n * 10}, {"id": n * 10 + 1}],
                                  "meta": {"pagination": {"last_page": last}}})
        self.session.request.side_effect = [response(body={"id": 42}), page(1, 2), page(2, 2)]
        self.assertEqual(self.client.favorite_suggestions(), [10, 11, 20, 21])
        urls = [call.args[1] for call in self.session.request.call_args_list]
        self.assertEqual(urls, [rema1000.API + "v1/user"] + [rema1000.API + "v3/users/42/favorite-suggestions"] * 2)
        self.assertEqual(self.session.request.call_args.kwargs["params"], {"per_page": 50, "page": 2})

    def test_add_favorite_uses_user_id(self):
        self.session.request.side_effect = [response(body={"id": 42}), response()]
        self.client.add_favorite(123456)
        args, kwargs = self.session.request.call_args
        self.assertEqual(args, ("POST", rema1000.API + "v3/users/42/favorites"))
        self.assertEqual(kwargs["params"], {"product_id": 123456})


CATALOG = {"departments": [
    {"name": "Dairy", "categories": [
        {"name": "Milk", "items": [
            {"id": 1, "name": "Whole milk", "underline": "1 l / Example Dairy",
             "pricing": {"price": 12.5, "normal_price": 14.0, "is_on_discount": True, "deposit": 0},
             "images": [{"small": "https://example.invalid/1-small.jpg"}], "extra": {"popularity": 5}},
            {"id": 2, "name": "", "pricing": {"price": 1}},
        ]},
        {"name": "Hidden", "hidden": True, "items": [{"id": 3, "name": "Not shown"}]},
    ]},
    {"name": "Drinks", "categories": [
        {"name": "Soda", "items": [
            {"id": 1, "name": "Whole milk (duplicate)"},
            {"id": 4, "name": "Cola", "underline": "1.5 l", "pricing": {"price": 20, "deposit": 3},
             "extra": {"popularity": 9}},
        ]},
    ]},
]}


class CatalogTest(unittest.TestCase):
    def test_flatten(self):
        products = rema1000.flatten_catalog(CATALOG)
        self.assertEqual([p["id"] for p in products], [1, 4])
        self.assertEqual(products[0], {
            "id": 1, "name": "Whole milk", "underline": "1 l / Example Dairy", "department": "Dairy",
            "category": "Milk", "price": 12.5, "normal_price": 14.0, "is_on_discount": True, "deposit": 0,
            "image": "https://example.invalid/1-small.jpg", "popularity": 5})
        self.assertEqual(products[1]["deposit"], 3)
        self.assertEqual(products[1]["image"], "")

    def test_flatten_empty(self):
        self.assertEqual(rema1000.flatten_catalog({}), [])

    def test_search_matches_all_words_most_popular_first(self):
        products = rema1000.flatten_catalog(CATALOG)
        self.assertEqual([p["id"] for p in rema1000.search_products(products, "MILK example")], [1])
        self.assertEqual([p["id"] for p in rema1000.search_products(products, "l")], [4, 1])
        self.assertEqual(rema1000.search_products(products, "nothing"), [])


A = rema1000.API
C = rema1000.CONTENT_API
T = rema1000.TJEK_API
U = A + "v3/users/42"

# One row per method that makes exactly one call:
# (method name, positional args, keyword args, HTTP method, URL, the request kwargs that matter, sends the token).
# docs/api/metoder.md is generated from this table (see method_rows below).
CALLS = [
    # Account and profile
    ("logout", (), {"confirm": True}, "POST", A + "v1/oauth/logout",
     {"json": {"device_token": None, "push_id": -1}}, True),
    ("user", (), {}, "GET", A + "v1/user", {}, True),
    ("update_user", (), {"name": "Test Testesen"}, "POST", A + "v1/user", {"json": {"name": "Test Testesen"}}, True),
    ("set_user_photo", (b"\xff\xd8",), {}, "POST", A + "v1/user/photo", {"json": {"photo": "/9g="}}, True),
    ("delete_account", (), {"confirm": True}, "POST", A + "v1/user/delete", {}, True),
    ("gdpr_export", (), {}, "POST", A + "v1/user/gdpr-export", {}, True),
    ("find_friends_by_email", (["a@example.invalid", "b@example.invalid"],), {}, "POST", A + "v1/user/friends/emails",
     {"data": [("emails[]", "a@example.invalid"), ("emails[]", "b@example.invalid")]}, True),
    ("find_friends_by_number", (["00000000"],), {}, "POST", A + "v1/user/friends/numbers",
     {"data": [("numbers[]", "00000000")]}, True),
    ("user_details", (), {}, "GET", U,
     {"params": {"include": "sponsor-club,active_bank_account,pending_shopper_suspension,type"}}, True),
    ("update_user_details", (), {"is_favorite_notification_enabled": False}, "PATCH", U,
     {"json": {"is_favorite_notification_enabled": False}}, True),
    ("identity_token", (), {}, "GET", A + "identity-verification/token", {"params": {
        "redirect_uri": "dk.rema1000.vigo://apps/rema1000/user/identity/verified",
        "failed_uri": "dk.rema1000.vigo://apps/rema1000/user/identity/failed",
        "cancelled_uri": "dk.rema1000.vigo://apps/rema1000/user/identity/cancelled",
        "resume_uri": "https://shop.rema1000.dk/apps/rema1000/user/resume"}}, True),
    ("add_address", ("00000000-0000-0000-0000-000000000000", "2nd floor"), {}, "POST", U + "/addresses",
     {"json": {"dawa_address_id": "00000000-0000-0000-0000-000000000000", "description": "2nd floor",
               "is_primary": False}}, True),
    ("update_address", (7,), {"description": "Back door"}, "PATCH", U + "/addresses/7",
     {"data": {"description": "Back door"}}, True),
    ("delete_address", (7,), {}, "DELETE", U + "/addresses/7", {}, True),
    ("policies", (), {}, "GET", A + "v3/policies", {"params": {"include": "current_version", "per_page": 100}}, False),
    ("accept_policy", (4,), {}, "POST", U + "/policy-versions", {"json": {"policy_version_id": 4}}, True),
    ("revoke_policy", (4,), {"confirm": True}, "DELETE", U + "/policy-versions/4", {}, True),
    ("newsletters", (), {}, "GET", A + "v3/newsletters", {"params": {"per_page": 100}}, False),
    ("newsletter_subscriptions", (), {}, "GET", U + "/newsletter-subscriptions", {"params": {"per_page": 100}}, True),
    ("subscribe_newsletter", (5,), {}, "POST", U + "/newsletter-subscriptions", {"json": {"newsletter_id": 5}}, True),
    ("unsubscribe_newsletter", (9,), {}, "DELETE", U + "/newsletter-subscriptions/9", {}, True),
    ("register_push", ("fake-push-token",), {}, "POST", A + "v1/push/register", {"json": {
        "service": "fcm", "app_identifier": "dk.iroots.rema1000", "app_version": "6.9.0",
        "token": "fake-push-token", "language": "da"}}, True),
    ("settings", (), {}, "GET", A + "v1/settings", {}, False),
    ("feature_flags", (), {}, "GET", A + "v3/feature-flags", {"params": {"per_page": 1000}}, False),
    ("campaigns", (), {}, "GET", A + "v1/campaigns", {}, False),
    ("user_campaigns", (), {}, "GET", A + "v1/user/campaigns", {}, True),
    ("batch", ([{"method": "POST", "uri": "/api/v3/users/42/favorites", "parameters": {"product_id": "11111"}}],), {},
     "POST", A + "v3/batch", {"json": {"requests": [
         {"method": "POST", "uri": "/api/v3/users/42/favorites", "parameters": {"product_id": "11111"}}]}}, True),
    # Shopping lists
    ("poll_lists", (1700000000,), {}, "GET", A + "v1/shoppinglists/polling", {"params": {"unixtime": 1700000000}}, True),
    ("lists", (), {}, "GET", A + "v1/shoppinglists/polling", {"params": {"unixtime": 0}}, True),
    ("sync", ([{"id": 1001, "name": "Example list", "items": []}],), {}, "POST", A + "v1/sync/shoppinglists-v2",
     {"json": {"changes": [{"id": 1001, "name": "Example list", "items": []}]}}, True),
    ("set_amount", (1001, "Example list", 900001, 3), {}, "POST", A + "v1/sync/shoppinglists-v2",
     {"json": {"changes": [{"id": 1001, "name": "Example list", "items": [
         {"id": 900001, "source": "android_search", "amount": 3}]}]}}, True),
    ("remove_item", (1001, "Example list", 900001), {}, "POST", A + "v1/sync/shoppinglists-v2",
     {"json": {"changes": [{"id": 1001, "name": "Example list", "items": [
         {"id": 900001, "source": "android_search", "deleted": True}]}]}}, True),
    ("set_bought", (1001, "Example list", 900001), {}, "POST", A + "v1/sync/shoppinglists-v2",
     {"json": {"changes": [{"id": 1001, "name": "Example list", "items": [
         {"id": 900001, "source": "android_search", "bought": True}]}]}}, True),
    ("set_primary_list", (1001,), {}, "PATCH", A + "v2/shoppinglists/1001", {"json": {"primary": True}}, True),
    ("invite_to_list", (1001, ["a@example.invalid"]), {}, "POST", A + "v1/shoppinglist/1001/invite",
     {"data": [("emails[]", "a@example.invalid")]}, True),
    ("list_recommended_products", (1001,), {}, "GET", A + "v3/shopping-lists/1001/recommended-products",
     {"params": {"per_page": 20, "page": 1}}, True),
    ("list_suggestions", (), {}, "GET", A + "v1/shoppinglistsuggestions", {}, False),
    # Favourites and personal suggestions
    ("favorites", (), {}, "GET", A + "v1/favorites/1", {}, True),
    ("add_favorite", (11111,), {}, "POST", U + "/favorites", {"params": {"product_id": 11111}}, True),
    ("add_favorites", ([11111, 22222],), {}, "POST", A + "v3/batch", {"json": {"requests": [
        {"method": "POST", "uri": "/api/v3/users/42/favorites", "parameters": {"product_id": "11111"}},
        {"method": "POST", "uri": "/api/v3/users/42/favorites", "parameters": {"product_id": "22222"}}]}}, True),
    ("remove_favorite", (11111,), {}, "DELETE", A + "v1/favorites/1/11111", {}, True),
    ("favorite_suggestions", (), {}, "GET", U + "/favorite-suggestions", {"params": {"per_page": 50, "page": 1}}, True),
    ("dismiss_favorite_suggestion", (11111,), {}, "DELETE", U + "/favorite-suggestions/11111", {}, True),
    ("frequently_bought", (), {}, "GET", U + "/frequently-bought-products",
     {"params": {"per_page": 20, "page": 1}}, True),
    ("inspiration_products", (), {}, "GET", U + "/inspiration-products", {"params": {"per_page": 20, "page": 1}}, True),
    ("dismiss_inspiration_product", (11111,), {}, "DELETE", U + "/inspiration-products/11111", {}, True),
    # Products, search and catalogue
    ("catalog", (), {}, "GET", A + "v1/catalog/store/1/withchildren", {}, False),
    ("catalog_modified", (), {}, "GET", A + "v1/catalog/store/1/last_modified", {}, False),
    ("products", (), {"sort": "-popularity", "age_restricted": False}, "GET", A + "v3/products",
     {"params": {"per_page": 20, "page": 1, "sort": "-popularity", "filter[age_restricted]": "false"}}, False),
    ("offers", (), {}, "GET", A + "v3/products",
     {"params": {"per_page": 100, "page": 1, "include": "department", "filter[is_advertised]": "true"}}, False),
    ("all_offers", (), {}, "GET", A + "v3/products",
     {"params": {"filter[is_advertised]": "true", "include": "department", "per_page": 100, "page": 1}}, False),
    ("product", (11111,), {}, "GET", A + "v3/products/11111", {}, False),
    ("departments", (), {}, "GET", A + "v3/departments",
     {"params": {"per_page": 100, "page": 1, "include": "categories"}}, False),
    ("category_products", (10, 1010), {}, "GET", A + "v3/departments/10/categories/1010/products",
     {"params": {"per_page": 100, "page": 1}}, False),
    ("barcode", ("5700000000000",), {}, "GET", A + "v3/product-barcode/5700000000000", {"params": {}}, False),
    ("search", ("milk",), {}, "GET", A + "search/products",
     {"params": {"query": "milk", "per_page": 20, "page": 1}}, False),
    # The weekly newspaper (Tjek)
    ("newspapers", (), {}, "GET", T + "/v2/catalogs", {"params": {"dealer_id": "11deC"}}, False),
    ("newspaper_pages", ("abc123",), {}, "GET", T + "/v2/catalogs/abc123/pages", {}, False),
    ("newspaper_offers", ("abc123",), {}, "GET", T + "/v2/offers",
     {"params": {"catalog_id": "abc123", "limit": 100, "offset": 0}}, False),
    ("newspaper_offer", ("offer1",), {}, "GET", T + "/v2/offers/offer1", {}, False),
    ("newspaper_offer_products", ("offer1",), {}, "POST", T + "/v4/rpc/get_offer_products",
     {"json": {"id": "offer1"}}, False),
    # Front page content and recipes
    ("entities", ("recipeTag",), {}, "GET", C + "entities",
     {"params": {"filter[type]": "recipeTag", "per_page": 20, "page": 1}}, False),
    ("app_configuration", (), {}, "GET", C + "entities",
     {"params": {"filter[type]": "appConfiguration", "per_page": 1, "page": 1}}, False),
    ("recipes", (), {"tag_id": "tag1", "sort": "title"}, "GET", C + "entities", {"params": {
        "filter[type]": "recipe", "filter[tags.sys.id]": "tag1", "per_page": 20, "page": 1, "sort": "title"}}, False),
    ("recipe", ("example-recipe",), {}, "GET", C + "entities", {"params": {
        "filter[type]": "recipe", "filter[slug]": "example-recipe", "per_page": 1, "page": 1}}, False),
    ("recipe_tags", (), {}, "GET", C + "entities",
     {"params": {"filter[type]": "recipeTag", "per_page": 100, "page": 1}}, False),
    ("featured_recipes", ("group1",), {}, "GET", C + "featured-recipes",
     {"params": {"filter[group_id]": "group1"}}, False),
    ("search_recipes", ("soup",), {}, "GET", A + "search/recipes",
     {"params": {"query": "soup", "per_page": 20, "page": 1}}, False),
    ("favorite_recipes", (), {}, "GET", U + "/favorite-recipes",
     {"params": {"fields": "id", "per_page": 100, "page": 1}}, True),
    ("add_favorite_recipe", ("recipe1",), {}, "POST", U + "/favorite-recipes", {"json": {"recipe_id": "recipe1"}}, True),
    ("remove_favorite_recipe", ("recipe1",), {}, "DELETE", U + "/favorite-recipes/recipe1", {}, True),
    # Stores and addresses
    ("stores", (), {}, "GET", A + "v3/stores", {"params": {"per_page": 1000, "page": 1}}, False),
    ("stores_near", (55.0, 10.0), {"click_and_collect": True}, "GET", A + "v3/stores", {"params": {
        "filter[near_coordinates]": "55.0,10.0", "filter[is_click_and_collect_active]": "true", "per_page": 3}}, False),
    ("address_autocomplete", ("Eksempelvej 1",), {}, "GET", rema1000.ADDRESS_API + "autocomplete", {"params": {
        "q": "Eksempelvej 1", "caretpos": 13, "multilinje": "true", "type": "adresse", "fuzzy": "true",
        "side": 1, "per_side": 20}}, False),
]

# Public methods that are covered by their own tests instead of a CALLS row,
# with the calls they make (for the generated overview).
OTHER_METHODS = {
    "login": [("GET", "oauth2/authorize")],
    "exchange_code": [("POST", "oauth2/token")],
    "access_token": [("POST", "oauth2/token/refresh")],
    "create_list": [("POST", "v1/sync/shoppinglists-v2")],
    "rename_list": [("POST", "v1/sync/shoppinglists-v2")],
    "delete_list": [("GET", "v1/shoppinglists/polling"), ("POST", "v1/sync/shoppinglists-v2")],
    "add_item": [("POST", "v1/sync/shoppinglists-v2")],
    "identity_login_url": [("GET", "identity-verification/login")],
    "newspaper_viewer_url": [("GET", "publication-viewer.tjek.com/v1/embeds/{publication_id}")],
    "request": [], "pages": [], "save_tokens": [], "load_tokens": [], "find_list": [], "user_id": [],
}

STATUS_TAG = rema1000.re.compile(r"\[(Verified|From app code|Helper)(: [^\]]+)?\]$")


def public_methods():
    return sorted(name for name, value in vars(rema1000.Rema1000).items()
                  if callable(value) and not name.startswith("_"))


def status_of(name):
    """The status tag at the end of the first docstring paragraph: (tag, note)."""
    summary = (getattr(rema1000.Rema1000, name).__doc__ or "").strip().split("\n\n")[0]
    match = STATUS_TAG.search(" ".join(summary.split()))
    return (match.group(1), (match.group(2) or "")[2:]) if match else (None, "")


def method_rows():
    """(client method, HTTP method, path, status, note) for every public method that calls something."""
    rows = []
    for name, _, _, verb, url, _, _ in CALLS:
        path = url.replace(A, "").replace("https://", "") if not url.startswith(A) else url[len(A):]
        rows.append((name, verb, path.replace("/42", "/{user_id}"), *status_of(name)))
    for name, calls in OTHER_METHODS.items():
        rows += [(name, verb, path, *status_of(name)) for verb, path in calls]
    return rows


class EveryMethodTest(ClientCase):
    def setUp(self):
        super().setUp()
        self.write_tokens()
        self.client._user_id = 42

    def test_each_call_builds_the_expected_request(self):
        for name, args, kwargs, verb, url, expected, sends_token in CALLS:
            with self.subTest(method=name):
                self.session.request.reset_mock()
                self.session.request.return_value = response(body={})
                getattr(self.client, name)(*args, **kwargs)
                self.assertEqual(self.session.request.call_count, 1)
                call_args, call_kwargs = self.session.request.call_args
                self.assertEqual(call_args, (verb, url))
                for key in ("params", "json", "data", "files"):
                    self.assertEqual(call_kwargs.get(key), expected.get(key), key)
                headers = call_kwargs["headers"]
                self.assertEqual(headers.get("Authorization"), "Bearer old-access" if sends_token else None)
                self.assertEqual(headers.get("x-api-key"), rema1000.TJEK_API_KEY if url.startswith(T) else None)

    def test_every_public_method_is_exercised(self):
        covered = {row[0] for row in CALLS} | set(OTHER_METHODS)
        self.assertEqual(sorted(covered), public_methods())

    def test_every_public_method_carries_a_status_tag(self):
        for name in public_methods():
            with self.subTest(method=name):
                self.assertIsNotNone(status_of(name)[0])

    def test_the_method_overview_lists_every_method(self):
        overview = (Path(rema1000.__file__).parent / "docs" / "api" / "metoder.md").read_text(encoding="utf-8")
        for name in public_methods():
            with self.subTest(method=name):
                self.assertIn(f"`{name}`", overview)
        status = {"Verified": "Afprøvet", "From app code": "Set i appens kode"}
        for name, verb, path, tag, _ in method_rows():
            with self.subTest(row=name):
                self.assertIn(f"| `{name}` | {verb} | `{path}` | {status[tag]}", overview)


class ListManagementTest(ClientCase):
    def setUp(self):
        super().setUp()
        self.write_tokens()

    def change(self):
        return self.session.request.call_args.kwargs["json"]["changes"][0]

    def test_create_returns_the_list_that_echoes_the_offline_id(self):
        def answer(method, url, **kwargs):
            offline_id = kwargs["json"]["changes"][0]["offlineId"]
            return response(body={"response": [{"id": 1001, "name": "Old list"},
                                               {"id": 1002, "name": "New list", "offlineId": offline_id}]})
        self.session.request.side_effect = answer
        self.assertEqual(self.client.create_list("New list")["id"], 1002)
        self.assertEqual(set(self.change()), {"offlineId", "name"})
        self.assertEqual(len(self.change()["offlineId"]), 36)

    def test_create_can_carry_items(self):
        self.session.request.side_effect = lambda method, url, **kwargs: response(body={"response": [
            {"id": 1002, "offlineId": kwargs["json"]["changes"][0]["offlineId"]}]})
        item = rema1000.new_item("Example product", 11111)
        self.client.create_list("New list", [item])
        self.assertEqual(self.change()["items"], [item])

    def test_create_without_an_echo_raises(self):
        self.session.request.return_value = response(body={"response": [{"id": 1001, "name": "New list"}]})
        with self.assertRaises(rema1000.RemaError):
            self.client.create_list("New list")

    def test_rename(self):
        self.session.request.return_value = response(body={"response": [{"id": 1001, "name": "Renamed"}]})
        self.assertEqual(self.client.rename_list(1001, "Renamed"), {"id": 1001, "name": "Renamed"})
        self.assertEqual(self.change(), {"id": 1001, "name": "Renamed"})

    def test_rename_that_is_silently_ignored_raises(self):
        self.session.request.return_value = response(body={"response": [{"id": 1001, "name": "Mine"}]})
        with self.assertRaises(rema1000.RemaError):
            self.client.rename_list(2002, "Renamed")

    def test_delete(self):
        self.session.request.side_effect = [
            response(body={"response": [{"id": 1001}, {"id": 1002}]}), response(body={"response": [{"id": 1002}]})]
        self.assertEqual(self.client.delete_list(1001), [{"id": 1002}])
        self.assertEqual(self.change(), {"id": 1001, "deleted": True})

    def test_delete_of_an_unknown_list_sends_nothing(self):
        self.session.request.return_value = response(body={"response": [{"id": 1001}]})
        with self.assertRaises(rema1000.RemaError):
            self.client.delete_list(2002)
        self.assertEqual(self.session.request.call_count, 1)

    def test_delete_that_did_not_happen_raises(self):
        self.session.request.return_value = response(body={"response": [{"id": 1001}]})
        with self.assertRaises(rema1000.RemaError):
            self.client.delete_list(1001)

    def test_add_item(self):
        self.session.request.return_value = response(body={"response": []})
        self.client.add_item(1001, "Example list", "Example product", 11111, amount=2)
        item = self.change()["items"][0]
        self.assertEqual((item["name"], item["store_item_id"], item["amount"]), ("Example product", 11111, 2))


class GuardTest(ClientCase):
    def setUp(self):
        super().setUp()
        self.write_tokens()
        self.client._user_id = 42

    def test_guarded_paths(self):
        for verb, path in (("POST", "v1/user/delete"), ("post", "/api/v1/user/delete"), ("POST", "v1/oauth/logout"),
                           ("POST", "v1/job"), ("POST", "v1/jobs/create-from-existing"), ("POST", "v1/job/5/cancel"),
                           ("POST", A + "v3/jobs/5/payments?x=1"), ("DELETE", "v3/jobs/5/payments/6"),
                           ("DELETE", "v3/users/42/policy-versions/4")):
            self.assertTrue(rema1000.is_guarded(verb, path), path)
        for verb, path in (("GET", "v1/user"), ("POST", "v1/user"), ("GET", "v3/jobs/5/payments"),
                           ("POST", "v1/sync/shoppinglists-v2"), ("POST", T + "/v1/user/delete")):
            self.assertFalse(rema1000.is_guarded(verb, path), path)

    def test_guarded_methods_refuse_without_confirm(self):
        for call in (self.client.delete_account, self.client.logout, lambda: self.client.revoke_policy(4),
                     lambda: self.client.request("POST", "v1/job", json={}),
                     lambda: self.client.batch([{"method": "POST", "uri": "/api/v1/user/delete"}])):
            with self.assertRaises(rema1000.ConfirmationRequired):
                call()
        self.session.request.assert_not_called()

    def test_token_is_not_sent_to_other_hosts(self):
        with self.assertRaises(rema1000.RemaError):
            self.client.request("GET", "https://example.invalid/v1/user")
        self.session.request.assert_not_called()

    def test_request_accepts_the_path_spellings(self):
        self.session.request.return_value = response(body={})
        for path in ("v1/user", "/v1/user", "/api/v1/user", A + "v1/user"):
            self.client.request("GET", path)
            self.assertEqual(self.session.request.call_args.args, ("GET", A + "v1/user"))

    def test_check_false_returns_error_answers(self):
        self.session.request.return_value = response(status=404, body={"message": "nope"})
        self.assertEqual(self.client.request("GET", "v3/nothing", auth=False, check=False).status_code, 404)

    def test_empty_answer_is_none(self):
        empty = response()
        empty.content = b""
        self.session.request.return_value = empty
        self.assertIsNone(self.client.delete_address(7))


class UrlHelperTest(unittest.TestCase):
    def test_identity_login_url(self):
        client = rema1000.Rema1000(token_file="/nonexistent/tokens.json", session=mock.Mock())
        self.assertEqual(client.identity_login_url("fake-token"),
                         A + "identity-verification/login?token=fake-token&platform=android")

    def test_newspaper_viewer_url(self):
        client = rema1000.Rema1000(token_file="/nonexistent/tokens.json", session=mock.Mock())
        parts = urlsplit(client.newspaper_viewer_url("abc123"))
        self.assertEqual(f"{parts.scheme}://{parts.netloc}{parts.path}",
                         "https://publication-viewer.tjek.com/v1/embeds/abc123")
        self.assertEqual(parse_qs(parts.query), {
            "enable_zoom": ["true"], "api_key": [rema1000.TJEK_API_KEY], "context": ["webview"],
            "view_direction": ["horizontal"], "view_mode": ["paged"], "ui": ["regular"]})

    def test_current_price(self):
        self.assertEqual(rema1000.current_price({"prices": [{"price": 10.0}, {"price": 12.0}]}), {"price": 10.0})
        self.assertEqual(rema1000.current_price({}), {})


class PagesTest(ClientCase):
    def test_pages_follow_last_page_and_stop_at_max(self):
        self.session.request.side_effect = [
            response(body={"data": [1, 2], "meta": {"pagination": {"last_page": 3}}}),
            response(body={"data": [3], "meta": {"pagination": {"last_page": 3}}})]
        self.assertEqual(self.client.pages("v3/products", {"sort": "title"}, auth=False, max_pages=2), [1, 2, 3])
        self.assertEqual(self.session.request.call_args.kwargs["params"], {"sort": "title", "per_page": 100, "page": 2})


class CliTest(unittest.TestCase):
    def test_parser_accepts_the_documented_commands(self):
        parser = rema1000.build_parser()
        for argv in (["login"], ["lists", "--json"], ["add", "1001", "123456", "--amount", "2"],
                     ["amount", "1001", "900001", "3"], ["remove", "1001", "900001"],
                     ["favorites"], ["favorites", "--add", "123456"], ["suggestions"],
                     ["catalog", "--search", "milk"], ["--token-file", "x.json", "catalog", "--modified"],
                     ["search", "whole", "milk", "--per-page", "5"], ["offers", "--all"], ["product", "11111"],
                     ["barcode", "5700000000000"], ["departments", "--json"], ["stores", "--near", "55.0,10.0"],
                     ["stores", "--search", "example", "--collect"], ["newspaper"], ["newspaper", "--offers", "abc123"],
                     ["recipes", "--search", "soup"], ["recipes", "--tags"], ["user"], ["logout", "--yes"],
                     ["list-create", "New list"], ["list-rename", "1001", "Renamed"], ["list-delete", "1001"],
                     ["api", "GET", "v3/products", "--query", "per_page=1", "page=2", "--no-auth"],
                     ["api", "POST", "v1/user", "--json", '{"name": "Test Testesen"}']):
            self.assertTrue(callable(parser.parse_args(argv).func))

    def run_api(self, *argv, status=200):
        session = mock.Mock()
        session.request.return_value = response(status=status, body={"ok": True})
        client = rema1000.Rema1000(token_file="/nonexistent/tokens.json", session=session)
        args = rema1000.build_parser().parse_args(["api", *argv])
        with mock.patch("builtins.print"):
            return args.func(client, args), session

    def test_api_command_builds_the_request(self):
        code, session = self.run_api("get", "v3/products", "--query", "filter[is_advertised]=true", "per_page=1",
                                     "--no-auth")
        self.assertEqual(code, 0)
        self.assertEqual(session.request.call_args.args, ("GET", A + "v3/products"))
        self.assertEqual(session.request.call_args.kwargs["params"],
                         [("filter[is_advertised]", "true"), ("per_page", "1")])
        self.assertNotIn("Authorization", session.request.call_args.kwargs["headers"])

    def test_api_command_reports_errors_and_guards(self):
        self.assertEqual(self.run_api("GET", "v3/nothing", "--no-auth", status=404)[0], 1)
        code, session = self.run_api("POST", "v1/user/delete", "--no-auth")
        self.assertEqual(code, 2)
        session.request.assert_not_called()
        self.assertEqual(self.run_api("GET", "v1/user", "--no-auth", "--json", "{broken")[0], 2)


if __name__ == "__main__":
    unittest.main()
