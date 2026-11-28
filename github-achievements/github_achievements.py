#!/usr/bin/env python3
"""Fetch a GitHub user's official achievement badges and embed them in a README.

GitHub exposes unlocked achievements on ``https://github.com/<user>?tab=achievements``.
This tool reads that public page, downloads the real badge images, and refreshes a
marked section of the profile README. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

GITHUB = "https://github.com"
USER_AGENT = "lamar-glass-github-achievements/1.0"
MARKER_START = "<!-- ACHIEVEMENTS:START -->"
MARKER_END = "<!-- ACHIEVEMENTS:END -->"
CARD_PATTERN = re.compile(r'data-achievement-slug="([a-z0-9-]+)"(.*?)</details>', re.S)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code} while fetching {url}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach {url}: {error.reason}") from error


def parse_achievements(page: str, username: str) -> list[dict]:
    achievements = []
    for slug, block in CARD_PATTERN.findall(page):
        name_match = re.search(r'alt="Achievement: ([^"]+)"', block)
        image_match = re.search(r'<img[^>]+src="([^"]+)"', block)
        if not name_match or not image_match:
            continue
        achievements.append(
            {
                "slug": slug,
                "name": name_match.group(1),
                "badge_url": html.unescape(image_match.group(1)),
                "profile_url": f"{GITHUB}/{username}?achievement={slug}&tab=achievements",
            }
        )
    return achievements


def download_badges(achievements: list[dict], output_dir: Path) -> list[dict]:
    badges_dir = output_dir / "badges"
    badges_dir.mkdir(parents=True, exist_ok=True)
    for achievement in achievements:
        url = achievement["badge_url"]
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            if not data.startswith(b"\x89PNG"):
                raise ValueError("response is not a PNG image")
            (badges_dir / f"{achievement['slug']}.png").write_bytes(data)
            achievement["local_file"] = f"badges/{achievement['slug']}.png"
        except (OSError, ValueError, urllib.error.URLError) as error:
            print(f"warning: using remote badge for {achievement['slug']} ({error})", file=sys.stderr)
    return achievements


def build_block(
    achievements: list[dict],
    username: str,
    readme_path: Path,
    output_dir: Path,
    config: dict,
) -> str:
    width = int(config.get("badge_width", 90))
    show_names = bool(config.get("show_names", True))
    badges = []
    names = []
    for achievement in achievements:
        name = html.escape(achievement["name"], quote=True)
        url = html.escape(achievement["profile_url"], quote=True)
        if achievement.get("local_file"):
            badge_path = output_dir / achievement["local_file"]
            relative = Path(os.path.relpath(badge_path, start=readme_path.parent)).as_posix()
        else:
            relative = achievement["badge_url"]
        source = html.escape(relative, quote=True)
        badges.append(
            f'<a href="{url}" title="{name}">'
            f'<img src="{source}" width="{width}" alt="GitHub achievement: {name}">'
            "</a>"
        )
        names.append(achievement["name"])

    lines = [
        MARKER_START,
        "## GitHub Achievements",
        "",
        '<div align="center">',
        "",
        "&nbsp;&nbsp;".join(badges) if badges else "No achievements unlocked yet.",
        "",
    ]
    if show_names and names:
        lines.extend([f"<sub>{html.escape(' · '.join(names))}</sub>", ""])
    lines.extend(
        [
            "</div>",
            "",
            f"Official badges from [@{username}'s GitHub profile]({GITHUB}/{username}?tab=achievements).",
            MARKER_END,
        ]
    )
    return "\n".join(lines)


def inject_block(text: str, block: str) -> str:
    if MARKER_START in text and MARKER_END in text:
        before, rest = text.split(MARKER_START, 1)
        _, after = rest.split(MARKER_END, 1)
        return before + block + after
    footer = '<div align="center">\n\n<i>'
    if footer in text:
        return text.replace(footer, block + "\n\n---\n\n" + footer, 1)
    return text.rstrip() + "\n\n" + block + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=os.environ.get("GITHUB_USERNAME", "Lamar-Glass"))
    parser.add_argument("--config", type=Path, default=script_dir / "config.json")
    parser.add_argument("--output-dir", type=Path, default=script_dir / "assets")
    parser.add_argument("--readme", type=Path, default=script_dir.parent / "README.md")
    parser.add_argument("--update-readme", action="store_true", help="Insert/refresh the README section")
    parser.add_argument("--no-download", action="store_true", help="Keep remote badge URLs instead of saving PNGs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        page = fetch_html(f"{GITHUB}/{args.username}?tab=achievements")
        achievements = parse_achievements(page, args.username)
        if not achievements and "data-achievement-slug" not in page:
            raise RuntimeError("Could not find an achievements section on the profile page")

        args.output_dir.mkdir(parents=True, exist_ok=True)
        if not args.no_download:
            achievements = download_badges(achievements, args.output_dir)
        (args.output_dir / "achievements.json").write_text(
            json.dumps(
                {
                    "username": args.username,
                    "checked_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    "achievements": achievements,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if args.update_readme:
            original = args.readme.read_text(encoding="utf-8")
            block = build_block(achievements, args.username, args.readme, args.output_dir, config)
            updated = inject_block(original, block)
            if updated != original:
                args.readme.write_text(updated, encoding="utf-8")
                print(f"Updated {args.readme}")
            else:
                print(f"README already up to date ({args.readme})")

        names = ", ".join(item["name"] for item in achievements) or "none"
        print(f"@{args.username}: {len(achievements)} official badges — {names}")
        print(f"Wrote {args.output_dir / 'achievements.json'}")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
