"""Draws assets/contributions.svg: where the contribution count comes from.

GitHub's contribution total mixes public commits, pull requests, issues,
new repositories and private work. Private work comes back as one number
with no type, so the usual stats cards leave it out. This card shows the
parts for the last year and for all time, plus how many repositories the
account owns.

Usage:
  GITHUB_TOKEN=... [CARD_TOKEN=...] python3 scripts/contributions_card.py <login> <out.svg>

GITHUB_TOKEN reads the public contribution numbers. CARD_TOKEN is optional:
a read-only token of the account itself, used only to count private
repositories, which GitHub shows to no one else. Without it the card shows
the public repository count only.

Standard library only, so the workflow needs no install step.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

TYPED = (
    "totalCommitContributions",
    "restrictedContributionsCount",
    "totalPullRequestContributions",
    "totalIssueContributions",
    "totalRepositoryContributions",
    "totalPullRequestReviewContributions",
)
FIELDS = " ".join(TYPED) + " contributionCalendar { totalContributions }"

# Tokyo Night, matching the stats and streak cards in the README.
BG = "#1a1b27"
TITLE = "#70a5fd"
TEXT = "#38bdae"
MUTED = "#a9b1d6"
LINE = "#2f3449"

# (key, label, colour). "other" gathers everything small: pull requests,
# new repositories, issues and reviews. Rows that are zero in both columns
# are left out.
ROWS_WITH_PRIVATE_COMMITS = [
    ("private_commits", "Commits to private repos", "#bf91f3"),
    ("public_commits", "Commits to public repos", "#38bdae"),
    ("other", "Other (pull requests, new repos)", "#e0af68"),
    ("unknown", "Private, type not shared", "#565f89"),
]
# Used when no token of the account is available, so GitHub reports all
# private work as one untyped number.
ROWS_PUBLIC_VIEW = [
    ("unknown", "Private contributions", "#bf91f3"),
    ("public_commits", "Commits to public repos", "#38bdae"),
    ("other", "Other (pull requests, new repos)", "#e0af68"),
]


def graphql(query, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "contributions-card"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(f"GitHub API error: {body['errors']}")
    return body["data"]


def flatten(c):
    out = {k: c[k] for k in TYPED}
    out["calendar"] = c["contributionCalendar"]["totalContributions"]
    return out


def combine(public, owner):
    """Splits one period's total into the card's rows.

    public: numbers as anyone sees them. owner: the same numbers read with
    the account's own token, where GitHub types private work too (or None).
    """
    calendar = public["calendar"]
    public_commits = public["totalCommitContributions"]
    if owner is None:
        unknown = public["restrictedContributionsCount"]
        return {
            "calendar": calendar,
            "unknown": unknown,
            "public_commits": public_commits,
            "private_commits": 0,
            "all_commits": None,
            "other": max(0, calendar - unknown - public_commits),
        }
    all_commits = owner["totalCommitContributions"]
    unknown = owner["restrictedContributionsCount"]
    private_commits = max(0, all_commits - public_commits)
    return {
        "calendar": calendar,
        "unknown": unknown,
        "public_commits": public_commits,
        "private_commits": private_commits,
        "all_commits": all_commits,
        "other": max(0, calendar - unknown - public_commits - private_commits),
    }


def fetch_contributions(login, token):
    user = graphql(
        f'query {{ user(login: "{login}") {{ createdAt '
        f"contributionsCollection {{ contributionYears {FIELDS} }} }} }}",
        token,
    )["user"]
    last_year = flatten(user["contributionsCollection"])
    years = user["contributionsCollection"]["contributionYears"]
    aliases = " ".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", '
        f'to: "{y}-12-31T23:59:59Z") {{ {FIELDS} }}'
        for y in years
    )
    per_year = graphql(f'query {{ user(login: "{login}") {{ {aliases} }} }}', token)["user"]
    all_time = {}
    for c in per_year.values():
        for k, v in flatten(c).items():
            all_time[k] = all_time.get(k, 0) + v
    since = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    return last_year, all_time, since


def owner_login(owner_token):
    """The login a token belongs to, or None if it can't be read."""
    try:
        return graphql("query { viewer { login } }", owner_token)["viewer"]["login"]
    except (RuntimeError, urllib.error.HTTPError) as e:
        print(f"CARD_TOKEN could not be used ({e}).")
        return None


def fetch_repos(login, public_token, owner_token):
    """Returns (public, private). private is None when it can't be known."""
    q = (
        f'query {{ user(login: "{login}") {{ '
        "repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount } } }"
    )
    public = graphql(q, public_token)["user"]["repositories"]["totalCount"]
    if not owner_token:
        return public, None
    try:
        data = graphql(
            "query { viewer { "
            "repositories(ownerAffiliations: OWNER, privacy: PRIVATE) { totalCount } } }",
            owner_token,
        )["viewer"]
    except (RuntimeError, urllib.error.HTTPError) as e:
        print(f"CARD_TOKEN could not read private repositories ({e}); showing public only.")
        return public, None
    return public, data["repositories"]["totalCount"]


def n(v):
    return f"{v:,}"


def render(rows, last_year, all_time, since, repos):
    rows = [r for r in rows if last_year[r[0]] or all_time[r[0]]]
    show_all_commits = last_year["all_commits"] is not None
    width, pad = 495, 25
    bar_y = 70
    table_y = 112
    row_h = 24
    height = table_y + row_h * (len(rows) + 1) + 92 + (row_h if show_all_commits else 0)
    col_a, col_b = width - pad - 110, width - pad

    def row_values(y, label, key, bold=False, colour=TEXT, indent=18):
        weight = ' font-weight="700"' if bold else ""
        return [
            f'<text x="{pad + indent}" y="{y}" font-size="14"{weight} fill="{colour}">{label}</text>',
            f'<text x="{col_a}" y="{y}" font-size="14"{weight} fill="{colour}" text-anchor="end">{n(last_year[key])}</text>',
            f'<text x="{col_b}" y="{y}" font-size="14"{weight} fill="{colour}" text-anchor="end">{n(all_time[key])}</text>',
        ]

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Contribution breakdown">',
        "<style>text{font-family:'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif}</style>",
        f'<rect width="{width}" height="{height}" rx="4.5" fill="{BG}"/>',
        f'<text x="{pad}" y="38" font-size="18" fill="{TITLE}">Contributions in the last year</text>',
        f'<text x="{width - pad}" y="40" font-size="22" font-weight="700" fill="{TITLE}" '
        f'text-anchor="end">{n(last_year["calendar"])}</text>',
    ]

    # Stacked bar of the last year.
    bar_w = width - 2 * pad
    out.append(f'<rect x="{pad}" y="{bar_y}" width="{bar_w}" height="10" rx="5" fill="{LINE}"/>')
    out.append(f'<clipPath id="bar"><rect x="{pad}" y="{bar_y}" width="{bar_w}" height="10" rx="5"/></clipPath>')
    out.append('<g clip-path="url(#bar)">')
    x, total = pad, max(last_year["calendar"], 1)
    for key, _, colour in rows:
        w = bar_w * last_year[key] / total
        if w > 0:
            out.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{max(w, 2):.2f}" height="10" fill="{colour}"/>')
            x += w
    out.append("</g>")

    # Contributions table.
    out.append(f'<text x="{col_a}" y="{table_y - 8}" font-size="11" fill="{MUTED}" text-anchor="end">Last year</text>')
    out.append(
        f'<text x="{col_b}" y="{table_y - 8}" font-size="11" fill="{MUTED}" text-anchor="end">'
        f"Since {since:%b %Y}</text>"
    )
    y = table_y
    for key, label, colour in rows:
        y += row_h
        out.append(f'<rect x="{pad}" y="{y - 10}" width="10" height="10" rx="2" fill="{colour}"/>')
        out.extend(row_values(y, label, key))

    y += 10
    out.append(f'<line x1="{pad}" y1="{y}" x2="{width - pad}" y2="{y}" stroke="{LINE}"/>')
    y += row_h - 4
    out.extend(row_values(y, "Total", "calendar", bold=True, colour=TITLE))
    if show_all_commits:
        y += row_h
        out.extend(row_values(y, "All commits (private + public)", "all_commits", bold=True, colour=TITLE))

    # Repositories owned right now.
    public, private = repos
    y += 18
    out.append(f'<line x1="{pad}" y1="{y}" x2="{width - pad}" y2="{y}" stroke="{LINE}"/>')
    y += 26
    owned = public if private is None else public + private
    split = f"{n(public)} public" if private is None else f"{n(public)} public · {n(private)} private"
    out.append(f'<text x="{pad}" y="{y}" font-size="14" font-weight="700" fill="{TITLE}">Repositories I own</text>')
    out.append(f'<text x="{col_a}" y="{y}" font-size="14" fill="{TEXT}" text-anchor="end">{split}</text>')
    out.append(f'<text x="{col_b}" y="{y}" font-size="14" font-weight="700" fill="{TITLE}" text-anchor="end">{n(owned)}</text>')

    updated = datetime.now(timezone.utc)
    note = (
        "Private commits are read with my own read-only token."
        if show_all_commits
        else "GitHub counts private work as one number, without its type."
    )
    out.append(
        f'<text x="{pad}" y="{height - 14}" font-size="10" fill="{MUTED}">'
        f"{note} Updated {updated:%d %b %Y}.</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    login, path = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN or GH_TOKEN.")
    owner_token = os.environ.get("CARD_TOKEN") or None
    if owner_token:
        who = owner_login(owner_token)
        if who is None or who.lower() != login.lower():
            if who is not None:
                print(f"CARD_TOKEN belongs to {who}, not {login}; ignoring it.")
            owner_token = None

    public_ly, public_at, since = fetch_contributions(login, token)
    owner_ly = owner_at = None
    if owner_token:
        owner_ly, owner_at, _ = fetch_contributions(login, owner_token)
        # Only use the owner view if it reveals private commits. A token with
        # Metadata access alone sees private repos but not their commits,
        # and an "all commits" total would then be only the public ones.
        if owner_at["totalCommitContributions"] <= public_at["totalCommitContributions"]:
            print(
                "CARD_TOKEN can't see private commits (it needs Contents: read-only); "
                "showing private work as one number."
            )
            owner_ly = owner_at = None

    last_year = combine(public_ly, owner_ly)
    all_time = combine(public_at, owner_at)
    rows = ROWS_PUBLIC_VIEW if owner_ly is None else ROWS_WITH_PRIVATE_COMMITS
    repos = fetch_repos(login, token, owner_token)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(render(rows, last_year, all_time, since, repos))
    print(
        f"last year {last_year['calendar']:,} (all commits {last_year['all_commits']}), "
        f"all time {all_time['calendar']:,} (all commits {all_time['all_commits']}), "
        f"untyped private {last_year['unknown']:,}/{all_time['unknown']:,}, "
        f"repos {repos[0]} public / {repos[1] if repos[1] is not None else '?'} private -> {path}"
    )


if __name__ == "__main__":
    main()
