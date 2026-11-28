# GitHub Achievement Badges

Fetches your **real, official GitHub achievement badges** (Pull Shark,
Quickdraw, YOLO, Starstruck, etc.) from your public profile and embeds them in
your profile README. Standard library only — no dependencies.

## Where the badges come from

GitHub lists unlocked achievements at:

```text
https://github.com/<username>?tab=achievements
```

Each unlocked achievement includes an official badge image hosted at
`github.githubassets.com`. This tool reads that page, downloads the PNGs into
`assets/badges/`, and writes a README section linking each badge back to its
achievement page.

## Usage

From the profile repository root:

```bash
python3 github-achievements/github_achievements.py --update-readme
```

Options:

- `--username NAME` — profile to read (default: `Lamar-Glass`).
- `--output-dir PATH` — where badge PNGs and metadata are written.
- `--readme PATH` — README to update.
- `--update-readme` — refresh the section between the achievement markers.
- `--no-download` — keep remote GitHub image URLs instead of saving PNGs.
- `--config PATH` — display options (`badge_width`, `show_names`).

The tool writes `assets/achievements.json` with each badge's name, slug, source
URL, and profile link.

## Automation

`.github/workflows/achievements.yml` runs weekly and on demand, committing any
new or changed badges so the profile stays current.

## Tests

```bash
python3 -m unittest discover -s github-achievements
```

## Notes

- Only achievements GitHub has actually awarded appear on the page; the tool
  cannot invent or unlock badges for you.
- If GitHub changes its HTML, adjust `CARD_PATTERN` in the script.
- Badge images remain the property of GitHub and are used as public profile
  assets.
