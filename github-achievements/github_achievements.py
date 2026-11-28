#!/usr/bin/env python3
"""Generate GitHub achievement cards from public profile data.

Uses only the Python standard library. A GITHUB_TOKEN is optional: without one,
the tool uses public REST endpoints; with one, it also reads the contribution
calendar (total contributions and longest streak) through GraphQL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
USER_AGENT = "lamar-glass-github-achievements/1.0"
MARKER_START = "<!-- ACHIEVEMENTS:START -->"
MARKER_END = "<!-- ACHIEVEMENTS:END -->"


def fetch_json(url: str, token: str | None = None, method: str = "GET", payload: dict | None = None) -> tuple[object, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response), response.headers.get("Link", "")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"GitHub API returned HTTP {error.code} for {url}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach GitHub API ({url}): {error.reason}") from error


def fetch_all(url: str, token: str | None = None, max_pages: int = 10) -> list[dict]:
    results: list[dict] = []
    for page in range(1, max_pages + 1):
        separator = "&" if "?" in url else "?"
        batch, link = fetch_json(f"{url}{separator}per_page=100&page={page}", token)
        if not isinstance(batch, list):
            raise RuntimeError(f"Expected a list from {url}, got {type(batch).__name__}")
        results.extend(batch)
        if 'rel="next"' not in link or len(batch) < 100:
            break
    return results


def contribution_stats(username: str, token: str) -> dict:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }
    """
    response, _ = fetch_json(
        f"{API}/graphql",
        token,
        method="POST",
        payload={"query": query, "variables": {"login": username}},
    )
    try:
        calendar = response["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    except (KeyError, TypeError) as error:
        raise RuntimeError("Unexpected GraphQL response while reading contributions") from error

    days = sorted(
        (day for week in calendar["weeks"] for day in week["contributionDays"]),
        key=lambda day: day["date"],
    )
    longest = current = 0
    for day in days:
        current = current + 1 if day["contributionCount"] > 0 else 0
        longest = max(longest, current)
    return {
        "contributions": calendar.get("totalContributions", 0),
        "longest_streak": longest,
    }


def collect_stats(username: str, token: str | None = None) -> dict:
    user, _ = fetch_json(f"{API}/users/{username}", token)
    repos = fetch_all(f"{API}/users/{username}/repos?type=owner", token)
    events = fetch_all(f"{API}/users/{username}/events/public", token)

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)
    recent_events = []
    for event in events:
        try:
            created = dt.datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if created >= cutoff:
            recent_events.append(event)

    commits = sum(
        len(event.get("payload", {}).get("commits", []))
        for event in recent_events
        if event.get("type") == "PushEvent"
    )
    merged_prs = sum(
        1
        for event in recent_events
        if event.get("type") == "PullRequestEvent"
        and event.get("payload", {}).get("action") == "closed"
        and event.get("payload", {}).get("pull_request", {}).get("merged") is True
    )
    issues_opened = sum(
        1
        for event in recent_events
        if event.get("type") == "IssuesEvent"
        and event.get("payload", {}).get("action") == "opened"
    )

    try:
        created_at = dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
        account_age_days = max((dt.datetime.now(dt.timezone.utc) - created_at).days, 0)
    except (KeyError, ValueError):
        account_age_days = 0

    stats = {
        "username": user.get("login", username),
        "account_age_days": account_age_days,
        "public_repos": user.get("public_repos", 0),
        "followers": user.get("followers", 0),
        "total_stars": sum(repo.get("stargazers_count", 0) for repo in repos),
        "total_forks": sum(repo.get("forks_count", 0) for repo in repos),
        "recent_commits": commits,
        "active_days": len({event["created_at"][:10] for event in recent_events if "created_at" in event}),
        "merged_prs": merged_prs,
        "issues_opened": issues_opened,
        "contributions": 0,
        "longest_streak": 0,
    }

    if token:
        try:
            stats.update(contribution_stats(username, token))
        except RuntimeError as error:
            print(f"warning: skipping contribution metrics ({error})", file=sys.stderr)
    return stats


def evaluate(stats: dict, config: dict, limit: int = 12) -> dict:
    colors = config.get("tier_colors", ["#8A8A8A", "#FE6F00", "#D00100"])
    unlocked = []
    possible = 0
    for metric in config["metrics"]:
        value = int(stats.get(metric["key"], 0) or 0)
        tiers = metric["tiers"]
        possible += len(tiers)
        for index, tier in enumerate(tiers):
            if value < tier:
                break
            noun = metric.get("singular", metric["unit"]) if tier == 1 else metric["unit"]
            unlocked.append(
                {
                    "id": f"{metric['key']}-{tier}",
                    "title": f"{tier:,} {noun}",
                    "label": metric["label"],
                    "value": value,
                    "tier": index,
                    "color": colors[min(index, len(colors) - 1)],
                }
            )
    unlocked.sort(key=lambda item: (-item["tier"], item["title"]))
    return {
        "username": stats.get("username", ""),
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "unlocked_count": len(unlocked),
        "possible_count": possible,
        "stats": stats,
        "achievements": unlocked[:limit],
    }


def render_svg(result: dict) -> str:
    cards = result["achievements"]
    username = html.escape(str(result.get("username", "")))
    card_width, card_height, gap, padding, columns = 340, 92, 16, 24, 2
    rows = math.ceil(len(cards) / columns) if cards else 1
    width = padding * 2 + columns * card_width + gap
    height = padding * 2 + 58 + rows * card_height + (rows - 1) * gap

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="GitHub achievements">',
        f'<rect width="{width}" height="{height}" rx="10" fill="#000000"/>',
        f'<text x="{padding}" y="42" font-family="Segoe UI, Ubuntu, sans-serif" font-size="22" font-weight="700" fill="#FE6F00">GITHUB ACHIEVEMENTS</text>',
        f'<text x="{padding}" y="64" font-family="Segoe UI, Ubuntu, sans-serif" font-size="12" fill="#C9C9C9">@{username} · {result["unlocked_count"]} unlocked</text>',
    ]

    for index, achievement in enumerate(cards):
        x = padding + (index % columns) * (card_width + gap)
        y = padding + 58 + (index // columns) * (card_height + gap)
        color = html.escape(str(achievement["color"]))
        title = html.escape(str(achievement["title"]))
        label = html.escape(str(achievement["label"]))
        value = html.escape(f"{achievement['value']:,}")
        lines.extend(
            [
                f'<rect x="{x}" y="{y}" width="{card_width}" height="{card_height}" rx="8" fill="#0B0B0B" stroke="{color}" stroke-opacity="0.65"/>',
                f'<rect x="{x}" y="{y}" width="6" height="{card_height}" rx="3" fill="{color}"/>',
                f'<text x="{x + 22}" y="{y + 36}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="17" font-weight="700" fill="{color}">{title}</text>',
                f'<text x="{x + 22}" y="{y + 60}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="11" fill="#EAEAEA">{label}</text>',
                f'<text x="{x + card_width - 18}" y="{y + 80}" text-anchor="end" font-family="Segoe UI, Ubuntu, sans-serif" font-size="10" fill="#8A8A8A">current: {value}</text>',
            ]
        )

    if not cards:
        lines.append(
            f'<text x="{padding}" y="{padding + 90}" font-family="Segoe UI, Ubuntu, sans-serif" font-size="13" fill="#EAEAEA">No milestones unlocked yet.</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def achievement_block(readme_path: Path, output_dir: Path) -> str:
    relative = Path(os.path.relpath(output_dir / "achievements.svg", start=readme_path.parent)).as_posix()
    return "\n".join(
        [
            MARKER_START,
            "## Achievements",
            "",
            '<div align="center">',
            "",
            f'<img src="{relative}" alt="GitHub achievements">',
            "",
            "</div>",
            "",
            "_Refresh with `python3 github-achievements/github_achievements.py --update-readme`._",
            MARKER_END,
        ]
    )


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
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--config", type=Path, default=script_dir / "config.json")
    parser.add_argument("--output-dir", type=Path, default=script_dir / "assets")
    parser.add_argument("--readme", type=Path, default=script_dir.parent / "README.md")
    parser.add_argument("--update-readme", action="store_true", help="Insert/refresh the achievement section in the README")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        stats = collect_stats(args.username, args.token)
        result = evaluate(stats, config)

        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "achievements.svg").write_text(render_svg(result), encoding="utf-8")
        (args.output_dir / "achievements.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )

        if args.update_readme:
            original = args.readme.read_text(encoding="utf-8")
            updated = inject_block(original, achievement_block(args.readme, args.output_dir))
            if updated != original:
                args.readme.write_text(updated, encoding="utf-8")
                print(f"Updated {args.readme}")
            else:
                print(f"README already up to date ({args.readme})")

        print(
            f"@{result['username']}: {result['unlocked_count']} achievements unlocked "
            f"from {len(config['metrics'])} metrics (data: {result['generated_at']})"
        )
        print(f"Wrote {args.output_dir / 'achievements.svg'}")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
