import random
from RosterEntry import Player, Team

RACES_PER_CUP = 4
CUPS_PER_ROUND = 2


class Race:
    def __init__(self, teams: list[Team]):
        self.teams = teams
        self.completed = False

    def record_results(self, placements: list[tuple[Player, int]]):
        for player, place in placements:
            player.record_placement(place)
        for team in self.teams:
            for opponent in self.teams:
                if opponent is not team:
                    team.record_match(opponent)
        self.completed = True

    def __repr__(self):
        return f"Race({[t.name for t in self.teams]}, completed={self.completed})"


class Cup:
    def __init__(self, cup_number: int, teams: list[Team]):
        self.cup_number = cup_number
        self.teams = teams
        # All races within a cup use the same set of teams
        self.races: list[Race] = [Race(list(teams)) for _ in range(RACES_PER_CUP)]

    def record_race_results(self, race_idx: int, placements: list[tuple[Player, int]]):
        self.races[race_idx].record_results(placements)

    @property
    def completed(self) -> bool:
        return all(r.completed for r in self.races)

    def __repr__(self):
        return f"Cup({self.cup_number}, teams={[t.name for t in self.teams]}, completed={self.completed})"


class Round:
    def __init__(self, round_number: int, all_teams: list[Team]):
        self.round_number = round_number
        self.all_teams = all_teams
        self.cups: list[Cup] = []

    def assign_custom_cups(self, cup_1_teams: list[Team], cup_2_teams: list[Team]):
        """Round 1: use admin-specified groups."""
        self.cups = [Cup(1, list(cup_1_teams)), Cup(2, list(cup_2_teams))]

    def assign_cups_by_score(self, round_number: int):
        """
        Rounds 2+: sort by score then split into cups.
        Even rounds (2,4,6): top scorers → Cup 1 (Elite).
        Odd rounds (3,5): top scorers → Cup 2 (Elite), low scorers → Cup 1 (Standard).
        """
        ranked = sorted(self.all_teams, key=lambda t: t.total_score, reverse=True)
        if round_number % 2 != 0:
            ranked = list(reversed(ranked))
        self._split_into_cups(ranked)

    def _split_into_cups(self, ordered_teams: list[Team]):
        size = len(ordered_teams) // CUPS_PER_ROUND
        self.cups = [
            Cup(i + 1, ordered_teams[i * size : (i + 1) * size])
            for i in range(CUPS_PER_ROUND)
        ]

    def record_race_results(
        self, cup_idx: int, race_idx: int, placements: list[tuple[Player, int]]
    ):
        self.cups[cup_idx].record_race_results(race_idx, placements)

    @property
    def completed(self) -> bool:
        return all(c.completed for c in self.cups)

    def __repr__(self):
        return f"Round({self.round_number}, cups={self.cups})"


def get_cup_label(round_number: int, cup_number: int) -> str:
    """Return the display label for a cup based on round parity and cup number."""
    if round_number == 1:
        return "Cup A" if cup_number == 1 else "Cup B"
    if round_number % 2 == 0:
        return "Elite Cup" if cup_number == 1 else "Standard Cup"
    return "Standard Cup" if cup_number == 1 else "Elite Cup"
