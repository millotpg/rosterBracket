import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from RosterEntry import Player, Team
    from Round import Round

_DDL = """
CREATE TABLE IF NOT EXISTS players (
    id   INTEGER PRIMARY KEY,
    name TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS teams (
    id         INTEGER PRIMARY KEY,
    player1_id INTEGER NOT NULL REFERENCES players(id),
    player2_id INTEGER NOT NULL REFERENCES players(id)
);
CREATE TABLE IF NOT EXISTS tournaments (
    id            INTEGER PRIMARY KEY,
    total_rounds  INTEGER NOT NULL,
    current_round INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS rounds (
    id            INTEGER PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id),
    round_number  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cups (
    id         INTEGER PRIMARY KEY,
    round_id   INTEGER NOT NULL REFERENCES rounds(id),
    cup_number INTEGER NOT NULL,
    completed  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cup_teams (
    cup_id  INTEGER NOT NULL REFERENCES cups(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    PRIMARY KEY (cup_id, team_id)
);
CREATE TABLE IF NOT EXISTS cup_results (
    id        INTEGER PRIMARY KEY,
    cup_id    INTEGER NOT NULL REFERENCES cups(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    score     INTEGER NOT NULL
);
"""


class TournamentDB:
    def __init__(self, path: str = "tournament.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_DDL)

        self.tournament_id: int | None = None
        self._player_ids: dict[int, int] = {}
        self._team_ids: dict[int, int] = {}
        # (round_number, cup_idx) → DB cup row id
        self._cup_ids: dict[tuple[int, int], int] = {}

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def init_tournament(self, teams: list["Team"], total_rounds: int) -> int:
        cur = self.conn.cursor()
        for team in teams:
            for player in team.players:
                cur.execute("INSERT INTO players (name) VALUES (?)", (player.name,))
                self._player_ids[id(player)] = cur.lastrowid
        for team in teams:
            cur.execute(
                "INSERT INTO teams (player1_id, player2_id) VALUES (?, ?)",
                (self._player_ids[id(team.players[0])], self._player_ids[id(team.players[1])]),
            )
            self._team_ids[id(team)] = cur.lastrowid
        cur.execute("INSERT INTO tournaments (total_rounds) VALUES (?)", (total_rounds,))
        self.tournament_id = cur.lastrowid
        self.conn.commit()
        return self.tournament_id

    def save_round(self, round_: "Round"):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO rounds (tournament_id, round_number) VALUES (?, ?)",
            (self.tournament_id, round_.round_number),
        )
        round_db_id = cur.lastrowid

        for cup in round_.cups:
            cur.execute(
                "INSERT INTO cups (round_id, cup_number) VALUES (?, ?)",
                (round_db_id, cup.cup_number),
            )
            cup_db_id = cur.lastrowid
            self._cup_ids[(round_.round_number, cup.cup_number - 1)] = cup_db_id
            for team in cup.teams:
                cur.execute(
                    "INSERT INTO cup_teams (cup_id, team_id) VALUES (?, ?)",
                    (cup_db_id, self._team_ids[id(team)]),
                )

        cur.execute(
            "UPDATE tournaments SET current_round=? WHERE id=?",
            (round_.round_number, self.tournament_id),
        )
        self.conn.commit()

    def save_cup_results(
        self,
        round_number: int,
        cup_idx: int,
        placements: list[tuple["Player", int]],
    ):
        cup_id = self._cup_ids[(round_number, cup_idx)]
        cur = self.conn.cursor()
        for player, score in placements:
            cur.execute(
                "INSERT INTO cup_results (cup_id, player_id, score) VALUES (?, ?, ?)",
                (cup_id, self._player_ids[id(player)], score),
            )
        cur.execute("UPDATE cups SET completed=1 WHERE id=?", (cup_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Read path — reconstruct a Tournament from a saved DB
    # ------------------------------------------------------------------

    @classmethod
    def load_tournament(cls, path: str, tournament_id: int = 1):
        from RosterEntry import Player, Team
        from Round import Round, Cup
        from Tournament import Tournament, TOTAL_ROUNDS

        db = cls(path)
        conn = db.conn
        db.tournament_id = tournament_id

        players_by_id = {
            row["id"]: Player(row["name"])
            for row in conn.execute("SELECT id, name FROM players").fetchall()
        }
        for db_id, player in players_by_id.items():
            db._player_ids[id(player)] = db_id

        teams_by_id: dict[int, Team] = {}
        for row in conn.execute("SELECT id, player1_id, player2_id FROM teams").fetchall():
            team = Team(players_by_id[row["player1_id"]], players_by_id[row["player2_id"]])
            teams_by_id[row["id"]] = team
            db._team_ids[id(team)] = row["id"]
        teams = list(teams_by_id.values())

        tourney: Tournament = object.__new__(Tournament)
        tourney.teams = teams
        tourney.rounds = []
        tourney.current_round = 0
        tourney.db = db

        for r_row in conn.execute(
            "SELECT * FROM rounds WHERE tournament_id=? ORDER BY round_number",
            (tournament_id,),
        ).fetchall():
            round_number = r_row["round_number"]
            round_: Round = object.__new__(Round)
            round_.round_number = round_number
            round_.all_teams = teams
            round_.cups = []

            for c_row in conn.execute(
                "SELECT * FROM cups WHERE round_id=? ORDER BY cup_number",
                (r_row["id"],),
            ).fetchall():
                cup_team_ids = [
                    ct["team_id"]
                    for ct in conn.execute(
                        "SELECT team_id FROM cup_teams WHERE cup_id=?", (c_row["id"],)
                    ).fetchall()
                ]
                cup_teams = [teams_by_id[tid] for tid in cup_team_ids]

                cup: Cup = object.__new__(Cup)
                cup.cup_number = c_row["cup_number"]
                cup.teams = cup_teams
                cup.completed = bool(c_row["completed"])

                cup_idx = c_row["cup_number"] - 1
                db._cup_ids[(round_number, cup_idx)] = c_row["id"]

                if cup.completed:
                    for res in conn.execute(
                        "SELECT player_id, score FROM cup_results WHERE cup_id=?",
                        (c_row["id"],),
                    ).fetchall():
                        players_by_id[res["player_id"]].record_score(res["score"])
                    for team in cup_teams:
                        for opp in cup_teams:
                            if opp is not team:
                                team.opponents_faced.append(opp)

                round_.cups.append(cup)

            tourney.rounds.append(round_)
            tourney.current_round = round_number

        return tourney, db

    # ------------------------------------------------------------------
    # Query path
    # ------------------------------------------------------------------

    def delete_cup_results(self, tournament_id: int, round_number: int, cup_number: int):
        cur = self.conn.cursor()
        cup_row = cur.execute("""
            SELECT c.id FROM cups c
            JOIN rounds rd ON c.round_id = rd.id
            WHERE rd.tournament_id = ? AND rd.round_number = ? AND c.cup_number = ?
        """, (tournament_id, round_number, cup_number)).fetchone()
        if cup_row:
            cur.execute("DELETE FROM cup_results WHERE cup_id = ?", (cup_row["id"],))
            cur.execute("UPDATE cups SET completed=0 WHERE id = ?", (cup_row["id"],))
        self.conn.commit()

    def get_cup_results(self, tournament_id: int, round_number: int, cup_number: int) -> list[dict]:
        rows = self.conn.execute("""
            SELECT pl.name  AS player_name,
                   p1.name  AS player1,
                   p2.name  AS player2,
                   cr.score
            FROM cup_results cr
            JOIN cups    c  ON cr.cup_id    = c.id
            JOIN rounds  rd ON c.round_id   = rd.id
            JOIN players pl ON cr.player_id = pl.id
            JOIN teams   tm ON (pl.id = tm.player1_id OR pl.id = tm.player2_id)
            JOIN players p1 ON tm.player1_id = p1.id
            JOIN players p2 ON tm.player2_id = p2.id
            WHERE rd.tournament_id = ? AND rd.round_number = ? AND c.cup_number = ?
            ORDER BY cr.score DESC
        """, (tournament_id, round_number, cup_number)).fetchall()
        return [dict(r) for r in rows]

    def list_tournaments(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT
                t.id,
                t.created_at,
                t.total_rounds,
                t.current_round                                   AS rounds_completed,
                (t.current_round = t.total_rounds
                 AND NOT EXISTS (
                     SELECT 1 FROM cups c
                     JOIN rounds rd ON c.round_id = rd.id
                     WHERE rd.tournament_id = t.id AND c.completed = 0
                 ))                                               AS is_complete
            FROM tournaments t
            ORDER BY t.id DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_tournament_meta(self, tournament_id: int):
        row = self.conn.execute("""
            SELECT
                t.id,
                t.created_at,
                t.total_rounds,
                t.current_round                                   AS rounds_completed,
                (t.current_round = t.total_rounds
                 AND NOT EXISTS (
                     SELECT 1 FROM cups c
                     JOIN rounds rd ON c.round_id = rd.id
                     WHERE rd.tournament_id = t.id AND c.completed = 0
                 ))                                               AS is_complete
            FROM tournaments t
            WHERE t.id = ?
        """, (tournament_id,)).fetchone()
        return dict(row) if row else None

    def get_leaderboard(self, tournament_id: int) -> list[dict]:
        rows = self.conn.execute("""
            SELECT
                p1.name                        AS player1,
                p2.name                        AS player2,
                COALESCE(SUM(cr.score), 0)     AS total_score
            FROM cup_results cr
            JOIN cups    c  ON cr.cup_id    = c.id
            JOIN rounds  rd ON c.round_id   = rd.id
            JOIN players pl ON cr.player_id = pl.id
            JOIN teams   tm ON (pl.id = tm.player1_id OR pl.id = tm.player2_id)
            JOIN players p1 ON tm.player1_id = p1.id
            JOIN players p2 ON tm.player2_id = p2.id
            WHERE rd.tournament_id = ?
            GROUP BY tm.id
            ORDER BY total_score DESC
        """, (tournament_id,)).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
