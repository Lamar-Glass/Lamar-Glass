#!/usr/bin/env python3
"""Offline unit tests for the achievement generator."""

import json
import unittest
from pathlib import Path

import github_achievements as ga


class AchievementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((Path(__file__).parent / "config.json").read_text())

    def test_evaluate_unlocks_only_reached_tiers(self):
        stats = {
            "username": "test-user",
            "public_repos": 55,
            "followers": 0,
            "total_stars": 3,
            "recent_commits": 12,
        }
        result = ga.evaluate(stats, self.config)
        titles = {item["title"] for item in result["achievements"]}
        self.assertIn("50 repos", titles)
        self.assertNotIn("100 repos", titles)
        self.assertIn("1 star", titles)
        self.assertNotIn("10 followers", titles)
        self.assertEqual(result["unlocked_count"], len(result["achievements"]))

    def test_evaluate_sorts_higher_tiers_first(self):
        result = ga.evaluate({"public_repos": 55, "followers": 100}, self.config, limit=50)
        tiers = [item["tier"] for item in result["achievements"]]
        self.assertEqual(tiers, sorted(tiers, reverse=True))

    def test_render_svg_escapes_text_and_includes_titles(self):
        result = ga.evaluate({"username": "<script>x</script>", "public_repos": 5}, self.config)
        svg = ga.render_svg(result)
        self.assertIn("5 repos", svg)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertTrue(svg.startswith("<svg"))

    def test_inject_block_replaces_existing_markers(self):
        text = "intro\n" + ga.MARKER_START + "\nold\n" + ga.MARKER_END + "\nend\n"
        block = ga.MARKER_START + "\nnew\n" + ga.MARKER_END
        updated = ga.inject_block(text, block)
        self.assertEqual(updated, "intro\n" + block + "\nend\n")
        self.assertEqual(updated.count(ga.MARKER_START), 1)

    def test_inject_block_appends_when_no_markers(self):
        updated = ga.inject_block("hello\n", ga.MARKER_START + "\nx\n" + ga.MARKER_END)
        self.assertIn("hello\n", updated)
        self.assertIn(ga.MARKER_START, updated)


if __name__ == "__main__":
    unittest.main()
