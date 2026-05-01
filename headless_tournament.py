import os
import random
from RosterEntry import Player, Team
from Tournament import Tournament
from db import TournamentDB

random.seed(42)

DB_PATH = "tournament.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

# ---------------------------------------------------------------------------
# Setup: 24 players -> 12 teams
# ---------------------------------------------------------------------------
player_names = [
    "Mario",   "Luigi",
    "Peach",   "Daisy",
    "Yoshi",   "Birdo",
    "Bowser",  "Bowser Jr.",
    "Toad",    "Toadette",
    "Wario",   "Waluigi",
    "DK",      "Diddy",
    "Rosalina","Luma",
    "Koopa",   "Lakitu",
    "Shy Guy", "Boo",
    "Link",    "Isabelle",
    "Inkling", "Villager",
]

players = [Player(name) for name in player_names]
teams = [Team(players[i * 2], players[i * 2 + 1]) for i in range(12)]

db = TournamentDB(DB_PATH)
tourney = Tournament(teams, db=db)

# ---------------------------------------------------------------------------
# Helper: generate random cumulative cup scores for all players
# ---------------------------------------------------------------------------
def simulate_cup_scores(cup) -> list[tuple[Player, int]]:
    all_players = [p for team in cup.teams for p in team.players]
    return [(player, random.randint(4, 60)) for player in all_players]

def print_cup(cup_idx: int, cup, label: str):
    team_names = ", ".join(t.name for t in cup.teams)
    print(f"\n  Cup {cup.cup_number} [{label}]: {team_names}")
    scores = simulate_cup_scores(cup)
    tourney.record_cup_results(cup_idx, scores)
    top3 = sorted(scores, key=lambda x: x[1], reverse=True)[:3]
    print(f"    Top 3: " + ", ".join(f"{p.name}({s})" for p, s in top3))

# ---------------------------------------------------------------------------
# Round 1: admin-specified cup groups
# ---------------------------------------------------------------------------
print("=" * 60)
print("ROUND 1  —  admin-specified cup groups")
print("=" * 60)

r1 = tourney.start_first_round(cup_1_teams=teams[:6], cup_2_teams=teams[6:])
print_cup(0, r1.cups[0], "Cup A")
print_cup(1, r1.cups[1], "Cup B")
tourney.print_leaderboard()

# ---------------------------------------------------------------------------
# Rounds 2-6: score-seeded cups
# ---------------------------------------------------------------------------
CUP_LABELS = {0: "Elite Cup", 1: "Standard Cup"}

for round_num in range(2, 7):
    print("=" * 60)
    print(f"ROUND {round_num}  —  score-seeded cups")
    print("=" * 60)

    rnd = tourney.advance_round()
    for c_idx, cup in enumerate(rnd.cups):
        print_cup(c_idx, cup, CUP_LABELS[c_idx])

    tourney.print_leaderboard()

# ---------------------------------------------------------------------------
# Final results
# ---------------------------------------------------------------------------
print("=" * 60)
print("FINAL STANDINGS")
print("=" * 60)
tourney.print_leaderboard()

print("PODIUM:")
for rank, team in enumerate(tourney.podium, start=1):
    print(f"  {rank}. {team.name}  —  {team.total_score} pts")

print(f"\nTournament complete: {tourney.is_complete}")
db.close()

# ---------------------------------------------------------------------------
# Round-trip verification
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("LOADING FROM DB  —  round-trip verification")
print("=" * 60)

restored, _ = TournamentDB.load_tournament(DB_PATH)
print(f"Restored tournament: round {restored.current_round}/6, "
      f"complete={restored.is_complete}")
restored.print_leaderboard()
