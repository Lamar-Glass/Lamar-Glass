# GitHub Achievements

A small Python tool that turns public GitHub data into achievement cards for a
profile README. It uses only the standard library.

## What it does

- Reads your public profile, repositories, and recent public events.
- With an optional `GITHUB_TOKEN`, also reads the last year's contribution
  calendar (total contributions and longest streak) via GraphQL.
- Scores achievement tiers from `config.json` (repos, followers, stars, forks,
  commits, active days, PRs, issues, tenure, contributions).
- Writes `assets/achievements.svg` and `assets/achievements.json`.
- Optionally refreshes the README section between the
  `<!-- ACHIEVEMENTS:START -->` / `<!-- ACHIEVEMENTS:END -->` markers.

## Usage

From the profile repository root:

```bash
python3 github-achievements/github_achievements.py --update-readme
```

With full contribution metrics:

```bash
GITHUB_TOKEN=ghp_... python3 github-achievements/github_achievements.py --update-readme
```

Useful flags:

- `--username NAME` — profile to score (default: `Lamar-Glass`).
- `--config PATH` — alternative tier configuration.
- `--output-dir PATH` — where the SVG/JSON are written.
- `--readme PATH` — README to update.
- `--update-readme` — inject/refresh the README section.

## Configuration

Edit `config.json` to change thresholds, labels, units, or tier colors. Each
metric has a `key`, `label`, `unit`, `singular`, and a list of `tiers`; the
highest reached tier becomes the achievement. Only the 12 highest-tier cards
are rendered to keep the image compact.

## Automation

`.github/workflows/achievements.yml` runs the generator weekly and commits any
changes, so the profile badges stay current without manual runs. The workflow
uses the repository's built-in `GITHUB_TOKEN`.

## Tests

```bash
python3 -m unittest discover -s github-achievements
```

## Notes

- Public events only cover ~90 days, so commit/PR/issue metrics reflect recent
  activity, not lifetime totals.
- Followers/stars/forks come directly from the public API.
- If the GraphQL call is unavailable or unauthorized, the tool prints a warning
  and continues with the REST-based achievements.
