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


class CliTest(unittest.TestCase):
    def test_parser_accepts_the_documented_commands(self):
        parser = rema1000.build_parser()
        for argv in (["login"], ["lists", "--json"], ["add", "1001", "123456", "--amount", "2"],
                     ["amount", "1001", "900001", "3"], ["remove", "1001", "900001"],
                     ["favorites"], ["favorites", "--add", "123456"], ["suggestions"],
                     ["catalog", "--search", "milk"], ["--token-file", "x.json", "catalog", "--modified"]):
            self.assertTrue(callable(parser.parse_args(argv).func))


if __name__ == "__main__":
    unittest.main()
