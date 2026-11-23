"""cli_avatars.redaction: the shared redactor (harness hook commands, board text)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import harness  # noqa: E402
from cli_avatars.redaction import REDACTED, redact  # noqa: E402

# Shape-only fakes; none of these is a real credential.
# Built from parts so secret scanners do not flag the fixture itself.
AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/" + "bPxRfiCYFAKEKEY123"


class Shared(unittest.TestCase):
    def test_harness_reexports_the_same_function(self):
        self.assertIs(harness.redact, redact)
        self.assertEqual(harness.REDACTED, REDACTED)


class Aws(unittest.TestCase):
    def test_secret_access_key_forms(self):
        for text in (
            f"export AWS_SECRET_ACCESS_KEY={AWS_SECRET}",
            f"aws_secret_access_key = {AWS_SECRET}",
            f'{{"aws_secret_access_key": "{AWS_SECRET}"}}',
            f"the key {AWS_SECRET} was pasted",
            f"AWS_SECRET_ACCESS_KEY='{AWS_SECRET}' aws s3 ls",
        ):
            with self.subTest(text=text):
                out = redact(text)
                self.assertNotIn(AWS_SECRET, out)
                self.assertNotIn("FAKEKEY", out)
                self.assertIn(REDACTED, out)

    def test_key_ids(self):
        for key_id in ("AKIA" + "ABCDEFGHIJKLMNOP", "ASIA" + "ABCDEFGHIJKLMNOP"):
            self.assertEqual(redact(f"id {key_id} here"), f"id {REDACTED} here")


class Prose(unittest.TestCase):
    def test_password_is(self):
        cases = {
            "the password is hunter2-fake": "hunter2-fake",
            "Password was 'two words'": "two words",
            "passwd = s3cr3t-fake": "s3cr3t-fake",
            "my pwd is fake.pass.9": "fake.pass.9",
            "la contraseña es falsa123": "falsa123",
            'PASSWORD is "fake pass"': "fake pass",
        }
        for text, secret in cases.items():
            with self.subTest(text=text):
                out = redact(text)
                self.assertNotIn(secret, out)
                self.assertIn(REDACTED, out)


class LeftAlone(unittest.TestCase):
    def test_ordinary_text_unchanged(self):
        for text in (
            "Merge 731b0599cdcca8543878cb81d1a3a7768b95e5d0 into daily",
            "Hotkey: F5 reloads",
            "python -u hooks/emit.py --event stop",
            "curl https://example.invalid:8080/x",
            "Wire the registry and add tests",
            "docs/task-backend-and-memory-map.md section 2.6",
            "abcdefghijklmnopqrstuvwxyzabcdefghijklmn",
        ):
            with self.subTest(text=text):
                self.assertEqual(redact(text), text)

    def test_earlier_shapes_still_hidden(self):
        for text, secret in (
            ("curl -H 'Authorization: Bearer fake-tok-1' x", "fake-tok-1"),
            ("GITHUB_TOKEN=ghp_" + "a" * 36, "ghp_"),
            ("https://demo:fake-pw@example.invalid/", "fake-pw"),
        ):
            with self.subTest(text=text):
                self.assertNotIn(secret, redact(text))


if __name__ == "__main__":
    unittest.main()
