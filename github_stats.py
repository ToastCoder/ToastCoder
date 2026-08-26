"""Fetch GitHub profile statistics and update the profile SVG themes."""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
API_URL = "https://api.github.com/graphql"
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
USERNAME = os.environ.get("USER_NAME", "ToastCoder")

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!, $cursor: String) {
  user(login: $login) {
    followers { totalCount }
    createdAt
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
      totalCount
      nodes { nameWithOwner stargazerCount }
      pageInfo { endCursor hasNextPage }
    }
  }
}
"""


def fetch_stats() -> dict[str, int]:
    if not TOKEN:
        raise RuntimeError("ACCESS_TOKEN or GITHUB_TOKEN is required")

    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=365)
    cursor = None
    stars = 0
    repositories: list[str] = []

    while True:
        response = requests.post(
            API_URL,
            json={"query": QUERY, "variables": {
                "login": USERNAME, "from": start.isoformat(),
                "to": end.isoformat(), "cursor": cursor,
            }},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        user = payload["data"]["user"]
        if user is None:
            raise RuntimeError(f"GitHub user not found: {USERNAME}")

        page = user["repositories"]
        stars += sum(repo["stargazerCount"] for repo in page["nodes"])
        repositories.extend(repo["nameWithOwner"] for repo in page["nodes"])
        stats = {
            "repositories": page["totalCount"],
            "stars": stars,
            "followers": user["followers"]["totalCount"],
            "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
            "created_at": user["createdAt"],
            "repositories_list": repositories,
        }
        if not page["pageInfo"]["hasNextPage"]:
            return stats
        cursor = page["pageInfo"]["endCursor"]


def fetch_loc(repositories: list[str]) -> tuple[int, int]:
    """Count additions and deletions in commits authored by the profile owner."""
    query = """
    query($owner: String!, $name: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef { target { ... on Commit {
          history(first: 100, after: $cursor) {
            nodes { additions deletions author { user { login } } }
            pageInfo { endCursor hasNextPage }
          }
        } } }
      }
    }
    """
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    additions = deletions = 0
    for full_name in repositories:
        owner, name = full_name.split("/", 1)
        cursor = None
        while True:
            response = requests.post(API_URL, json={"query": query, "variables": {
                "owner": owner, "name": name, "cursor": cursor,
            }}, headers=headers, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(payload["errors"])
            branch = payload["data"]["repository"]["defaultBranchRef"]
            if not branch:
                break
            history = branch["target"]["history"]
            for commit in history["nodes"]:
                author = commit.get("author") or {}
                user = author.get("user") or {}
                if user.get("login", "").lower() == USERNAME.lower():
                    additions += commit["additions"]
                    deletions += commit["deletions"]
            if not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]
    return additions, deletions


def uptime(created_at: str) -> str:
    created = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    days = (dt.datetime.now(dt.timezone.utc) - created).days
    years, remainder = divmod(days, 365)
    months = remainder // 30
    return f"{years}y {months}m"


def update_svg(path: Path, stats: dict[str, int]) -> None:
    source = path.read_text(encoding="utf-8")
    light = path.name == "light_mode.svg"
    colors = ("#d0d7de", "#0969da", "#953800", "#24292f") if light else ("#3d444d", "#58a6ff", "#ffa657", "#c9d1d9")
    rule, accent, label, text = colors
    x, ys = (("732", (593, 615, 637, 659, 681, 703, 725, 747)) if light else ("674.4", (446.6, 468.6, 490.6, 512.6, 534.6, 556.6, 578.6, 600.6)))
    header_y, github_y, loc_y, uptime_y, contact_y, email_y, linkedin_y, github_contact_y = ys
    additions = stats["additions"]
    deletions = stats["deletions"]
    block = (
        f'  <text x="{x}" y="{header_y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="12">'
        f'<tspan fill="{rule}">─</tspan><tspan fill="{accent}"> Stats </tspan><tspan fill="{rule}">────────────────────────────────────────────────</tspan></text>\n'
        f'  <text x="{x}" y="{github_y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="12"><tspan fill="{label}">. GitHub: </tspan><tspan fill="{text}">Repositories: {stats["repositories"]:,} | Stars: {stats["stars"]:,} | Followers: {stats["followers"]:,}</tspan></text>\n'
        f'  <text x="{x}" y="{loc_y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="12"><tspan fill="{label}">. Code: </tspan><tspan fill="{text}">+{additions:,} / -{deletions:,} lines | Net: {additions - deletions:+,}</tspan></text>\n'
        f'  <text x="{x}" y="{uptime_y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="12"><tspan fill="{label}">. Activity: </tspan><tspan fill="{text}">{stats["contributions"]:,} contributions | Uptime: {stats["uptime"]}</tspan></text>\n'
        f'  <text x="{x}" y="{contact_y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="12"><tspan fill="{rule}">─</tspan><tspan fill="{accent}"> Contact </tspan><tspan fill="{rule}">────────────────────────────────────────────────</tspan></text>\n'
        f'  <text x="{x}" y="{email_y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="12"><tspan fill="{label}">. Email: </tspan><tspan fill="{text}">hellovigkr@gmail.com</tspan></text>\n'
        f'  <text x="{x}" y="{linkedin_y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="12"><tspan fill="{label}">. LinkedIn: </tspan><tspan fill="{text}">linkedin.com/in/toastcoder</tspan></text>\n'
        f'  <text x="{x}" y="{github_contact_y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="12"><tspan fill="{label}">. GitHub: </tspan><tspan fill="{text}">github.com/ToastCoder</tspan></text>'
    )
    pattern = r"  <!-- GITHUB_STATS_START -->.*?  <!-- GITHUB_STATS_END -->"
    replacement = f"  <!-- GITHUB_STATS_START -->\n{block}\n  <!-- GITHUB_STATS_END -->"
    updated, count = re.subn(pattern, replacement, source, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Stats markers not found in {path.name}")
    path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    stats = fetch_stats()
    stats["additions"], stats["deletions"] = fetch_loc(stats.pop("repositories_list"))
    stats["uptime"] = uptime(stats.pop("created_at"))
    for filename in ("dark_mode.svg", "light_mode.svg"):
        update_svg(ROOT / filename, stats)
    print("Updated GitHub stats:", stats)
