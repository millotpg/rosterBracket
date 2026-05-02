import urllib.request
import urllib.parse
import http.cookiejar
import json
import random

BASE = "http://localhost:8005"

TEAMS = [
    ("Mario",    "Luigi"),
    ("Peach",    "Daisy"),
    ("Yoshi",    "Birdo"),
    ("Bowser",   "Bowser Jr."),
    ("Toad",     "Toadette"),
    ("Wario",    "Waluigi"),
    ("DK",       "Diddy"),
    ("Rosalina", "Luma"),
    ("Koopa",    "Lakitu"),
    ("Shy Guy",  "Boo"),
    ("Link",     "Isabelle"),
    ("Inkling",  "Villager"),
]

def populate_users():
    for p1, p2 in TEAMS:
        payload = json.dumps({"player1_name": p1, "player2_name": p2}).encode()
        req = urllib.request.Request(
            f"{BASE}/teams",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        print(f"  #{data['team_id']:>2}  {data['player1']} & {data['player2']}")

    print(f"\nDone — {len(TEAMS)} teams registered.")


def start_tournament():
    # Authenticate
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login_data = urllib.parse.urlencode({"username": "admin", "password": "password"}).encode()
    opener.open(f"{BASE}/auth/login", login_data)

    # Fetch registered teams
    with opener.open(f"{BASE}/teams") as resp:
        teams = json.loads(resp.read())["teams"]

    ids = [t["team_id"] for t in teams]
    random.shuffle(ids)
    half = len(ids) // 2
    group_a, group_b = ids[:half], ids[half:]

    print("Group A:", [t["player1"] + " & " + t["player2"]
                       for t in teams if t["team_id"] in group_a])
    print("Group B:", [t["player1"] + " & " + t["player2"]
                       for t in teams if t["team_id"] in group_b])

    payload = json.dumps({"group_a": group_a, "group_b": group_b}).encode()
    req = urllib.request.Request(
        f"{BASE}/tournament/start",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(req) as resp:
        data = json.loads(resp.read())

    print(f"\nTournament started — Round {data['round_number']}")
    for cup in data["cups"]:
        print(f"  Cup {cup['cup_number']}: {', '.join(cup['teams'])}")


def populate_cup(round_num, cup):
    """Submit random cumulative scores for all players in a cup."""
    with urllib.request.urlopen(f"{BASE}/tournament/status") as resp:
        active_cups = json.loads(resp.read())["active_cups"]

    cup_data = next((c for c in active_cups if c["cup_number"] == cup), None)
    if cup_data is None:
        print(f"Cup {cup} not found in active cups")
        return

    players = [p for team in cup_data["teams"] for p in team.split(" & ")]
    placements = [{"player_name": p, "score": random.randint(4, 60)} for p in players]

    payload = json.dumps({"placements": placements}).encode()
    req = urllib.request.Request(
        f"{BASE}/rounds/{round_num}/cups/{cup}/results",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    top3 = sorted(data["placements"], key=lambda r: r["score"], reverse=True)[:3]
    print(f"R{round_num} Cup{cup} — "
          + ", ".join(f"{r['player_name']}:{r['score']}" for r in top3)
          + " …")


if __name__ == "__main__":
    # populate_users()
    # breakpoint()
    # start_tournament()
    for round_num in range(1, 7):
        for cup in range(1, 3):
            breakpoint()
            populate_cup(round_num, cup)


