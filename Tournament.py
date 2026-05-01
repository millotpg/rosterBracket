from __future__ import annotations

from typing import TYPE_CHECKING

from RosterEntry import Player, Team
from Round import Round, Cup

if TYPE_CHECKING:
    from db import TournamentDB

TOTAL_ROUNDS = 6
TOTAL_TEAMS = 12  # change here if team count changes last minute


class Tournament:
    def __init__(self, teams: list[Team], db: TournamentDB | None = None):
        if len(teams) != TOTAL_TEAMS:
            raise ValueError(f"Expected {TOTAL_TEAMS} teams, got {len(teams)}.")
        self.teams = teams
        self.rounds: list[Round] = []
        self.current_round: int = 0  # 0 = not started
        self.db = db
        if db:
            db.init_tournament(teams, TOTAL_ROUNDS)

    # ------------------------------------------------------------------
    # Round management
    # ------------------------------------------------------------------

    def start_first_round(self, cup_1_teams: list[Team], cup_2_teams: list[Team]) -> Round:
        """Begin round 1 with admin-specified cup groups."""
        if self.current_round != 0:
            raise RuntimeError("Tournament has already started.")
        round_ = Round(round_number=1, all_teams=self.teams)
        round_.assign_custom_cups(cup_1_teams, cup_2_teams)
        self.rounds.append(round_)
        self.current_round = 1
        if self.db:
            self.db.save_round(round_)
        return round_

    def advance_round(self) -> Round:
        if self.current_round == 0:
            raise RuntimeError("Call start_first_round() to begin the tournament.")
        if self.current_round >= TOTAL_ROUNDS:
            raise RuntimeError("All rounds have been completed.")
        if not self._active_round().completed:
            raise RuntimeError(f"Round {self.current_round} still has incomplete cups.")

        next_num = self.current_round + 1
        round_ = Round(round_number=next_num, all_teams=self.teams)
        round_.assign_cups_by_score(next_num)
        self.rounds.append(round_)
        self.current_round = next_num
        if self.db:
            self.db.save_round(round_)
        return round_

    def record_cup_results(
        self, cup_idx: int, placements: list[tuple[Player, int]]
    ):
        """Record cup-level scores. cup_idx is 0-based."""
        self._active_round().record_cup_results(cup_idx, placements)
        if self.db:
            self.db.save_cup_results(self.current_round, cup_idx, placements)

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------

    @property
    def leaderboard(self) -> list[Team]:
        return sorted(self.teams, key=lambda t: t.total_score, reverse=True)

    @property
    def podium(self) -> list[Team]:
        return self.leaderboard[:3]

    def print_leaderboard(self):
        board = self.leaderboard
        width = max(len(t.name) for t in board)
        print(f"\n{'Rank':<6} {'Team':<{width}} {'Score':>6}")
        print("-" * (width + 14))
        for rank, team in enumerate(board, start=1):
            marker = " <--" if rank <= 3 else ""
            print(f"{rank:<6} {team.name:<{width}} {team.total_score:>6}{marker}")
        print()

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        return self.current_round == TOTAL_ROUNDS and self._active_round().completed

    @property
    def rounds_remaining(self) -> int:
        return TOTAL_ROUNDS - self.current_round

    def _active_round(self) -> Round:
        if not self.rounds:
            raise RuntimeError("No rounds have started yet.")
        return self.rounds[-1]

    def __repr__(self):
        return (
            f"Tournament(round={self.current_round}/{TOTAL_ROUNDS}, "
            f"teams={len(self.teams)}, complete={self.is_complete})"
        )
