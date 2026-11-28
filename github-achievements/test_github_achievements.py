#!/usr/bin/env python3
"""Offline unit tests for the official GitHub badge fetcher."""

import json
import unittest
from pathlib import Path

import github_achievements as ga

FIXTURE = """
<html>
  <div class="border-top">
    <h2>Achievements</h2>
    <details data-view-component="true" data-achievement-slug="pull-shark">
      <summary><img src="https://github.githubassets.com/assets/pull-shark-default-498c279a747d.png" width="90" alt="Achievement: Pull Shark"></summary>
    </details>
    <details data-view-component="true" data-achievement-slug="quickdraw">
      <summary><img src="https://github.githubassets.com/assets/quickdraw-default-39c6aec8ff89.png" width="90" alt="Achievement: Quickdraw"></summary>
    </details>
  </div>
</html>
"""


class AchievementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((Path(__file__).parent / "config.json").read_text())

    def test_parse_achievements(self):
        found = ga.parse_achievements(FIXTURE, "test-user")
        self.assertEqual([item["slug"] for item in found], ["pull-shark", "quickdraw"])
        self.assertEqual(found[0]["name"], "Pull Shark")
        self.assertIn("pull-shark-default", found[0]["badge_url"])
        self.assertEqual(
            found[0]["profile_url"],
            "https://github.com/test-user?achievement=pull-shark&tab=achievements",
        )

    def test_parse_ignores_pages_without_cards(self):
        self.assertEqual(ga.parse_achievements("<html></html>", "test-user"), [])

    def test_build_block_uses_official_images_and_links(self):
        found = ga.parse_achievements(FIXTURE, "test-user")
        block = ga.build_block(
            found, "test-user", Path("/tmp/readme.md"), Path("/tmp/assets"), self.config
        )
        self.assertIn("https://github.githubassets.com/assets/pull-shark-default", block)
        self.assertIn("https://github.com/test-user?achievement=quickdraw&amp;tab=achievements", block)
        self.assertIn("Pull Shark · Quickdraw", block)
        self.assertIn(ga.MARKER_START, block)

    def test_build_block_escapes_names(self):
        found = ga.parse_achievements(
            FIXTURE.replace("Pull Shark", '<script>alert("x")</script>'), "test-user"
        )
        block = ga.build_block(found, "u", Path("/tmp/readme.md"), Path("/tmp/assets"), self.config)
        self.assertNotIn("<script>", block)
        self.assertIn("&lt;script&gt;", block)

    def test_inject_block_replaces_existing_markers(self):
        text = "intro\n" + ga.MARKER_START + "\nold\n" + ga.MARKER_END + "\nend\n"
        block = ga.MARKER_START + "\nnew\n" + ga.MARKER_END
        self.assertEqual(ga.inject_block(text, block), "intro\n" + block + "\nend\n")

    def test_inject_block_appends_when_no_markers(self):
        updated = ga.inject_block("hello\n", ga.MARKER_START + "\nx\n" + ga.MARKER_END)
        self.assertIn("hello\n", updated)
        self.assertIn(ga.MARKER_START, updated)


if __name__ == "__main__":
    unittest.main()
