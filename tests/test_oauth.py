import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from supportdesk.oauth import begin_oauth_install, list_oauth_providers


class OAuthTest(unittest.TestCase):
    def test_lists_provider_configuration_state(self) -> None:
        with patch.dict(os.environ, {"GMAIL_CLIENT_ID": "gmail-client"}, clear=False):
            providers = list_oauth_providers()

        gmail = next(provider for provider in providers if provider["provider"] == "gmail")
        self.assertTrue(gmail["configured"])
        self.assertIn("https://www.googleapis.com/auth/gmail.readonly", gmail["default_scopes"])

    def test_builds_authorization_url_with_state(self) -> None:
        with patch.dict(os.environ, {"GITHUB_CLIENT_ID": "github-client"}, clear=False):
            flow = begin_oauth_install(
                "github",
                "https://desk.example/api/oauth/github/callback",
                scopes=["repo"],
            )

        parsed = urlparse(flow["authorization_url"])
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "github.com")
        self.assertEqual(query["client_id"], ["github-client"])
        self.assertEqual(query["scope"], ["repo"])
        self.assertEqual(query["state"], [flow["state"]])

    def test_requires_client_id(self) -> None:
        with patch.dict(os.environ, {"DISCORD_CLIENT_ID": ""}, clear=False):
            with self.assertRaises(ValueError):
                begin_oauth_install("discord", "https://desk.example/callback")


if __name__ == "__main__":
    unittest.main()
