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
    cup_number INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cup_teams (
    cup_id  INTEGER NOT NULL REFERENCES cups(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    PRIMARY KEY (cup_id, team_id)
);
CREATE TABLE IF NOT EXISTS races (
    id          INTEGER PRIMARY KEY,
    cup_id      INTEGER NOT NULL REFERENCES cups(id),
    race_number INTEGER NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS race_results (
    id        INTEGER PRIMARY KEY,
    race_id   INTEGER NOT NULL REFERENCES races(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    place     INTEGER NOT NULL,
    score     INTEGER NOT NULL
);
"""


class TournamentDB:
    def __init__(self, path: str = "tournament.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_DDL)

        self.tournament_id: int | None = None
        # Python object id → DB row id mappings
        self._player_ids: dict[int, int] = {}
        self._team_ids: dict[int, int] = {}
        # (round_number, cup_idx, race_idx) → DB race row id
        self._race_ids: dict[tuple[int, int, int], int] = {}

    # ------------------------------------------------------------------
    # Write path — called by Tournament as state is produced
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
            for team in cup.teams:
                cur.execute(
                    "INSERT INTO cup_teams (cup_id, team_id) VALUES (?, ?)",
                    (cup_db_id, self._team_ids[id(team)]),
                )
            for race_idx in range(len(cup.races)):
                cur.execute(
                    "INSERT INTO races (cup_id, race_number) VALUES (?, ?)",
                    (cup_db_id, race_idx),
                )
                self._race_ids[(round_.round_number, cup.cup_number - 1, race_idx)] = cur.lastrowid

        cur.execute(
            "UPDATE tournaments SET current_round=? WHERE id=?",
            (round_.round_number, self.tournament_id),
        )
        self.conn.commit()

    def save_race_result(
        self,
        round_number: int,
        cup_idx: int,
        race_idx: int,
        placements: list[tuple["Player", int]],
    ):
        from RosterEntry import PLACEMENT_SCORES

        race_id = self._race_ids[(round_number, cup_idx, race_idx)]
        cur = self.conn.cursor()
        for player, place in placements:
            cur.execute(
                "INSERT INTO race_results (race_id, player_id, place, score) VALUES (?, ?, ?, ?)",
                (race_id, self._player_ids[id(player)], place, PLACEMENT_SCORES.get(place, 0)),
            )
        cur.execute("UPDATE races SET completed=1 WHERE id=?", (race_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Read path — reconstruct a Tournament from a saved DB
    # ------------------------------------------------------------------

    @classmethod
    def load_tournament(cls, path: str, tournament_id: int = 1):
        """
        Reconstruct a Tournament from a saved DB file so a crashed or
        interrupted tournament can be resumed.  Returns (tournament, db).
        """
        from RosterEntry import Player, Team
        from Round import Round, Cup, Race
        from Tournament import Tournament, TOTAL_ROUNDS

        db = cls(path)
        conn = db.conn
        db.tournament_id = tournament_id

        # Rebuild players
        players_by_id = {
            row["id"]: Player(row["name"])
            for row in conn.execute("SELECT id, name FROM players").fetchall()
        }
        for db_id, player in players_by_id.items():
            db._player_ids[id(player)] = db_id

        # Rebuild teams
        teams_by_id: dict[int, Team] = {}
        for row in conn.execute("SELECT id, player1_id, player2_id FROM teams").fetchall():
            team = Team(players_by_id[row["player1_id"]], players_by_id[row["player2_id"]])
            teams_by_id[row["id"]] = team
            db._team_ids[id(team)] = row["id"]
        teams = list(teams_by_id.values())

        # Build Tournament shell — bypass __init__ so team-count validation
        # doesn't reject a DB that used a different TOTAL_TEAMS at creation time
        tourney: Tournament = object.__new__(Tournament)
        tourney.teams = teams
        tourney.rounds = []
        tourney.current_round = 0
        tourney.db = db

        # Replay rounds in order, restoring all scores and match history
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
                cup.races = []

                cup_idx = c_row["cup_number"] - 1

                for race_row in conn.execute(
                    "SELECT * FROM races WHERE cup_id=? ORDER BY race_number",
                    (c_row["id"],),
                ).fetchall():
                    race_idx = race_row["race_number"]
                    race: Race = object.__new__(Race)
                    race.teams = cup_teams
                    race.completed = bool(race_row["completed"])
                    cup.races.append(race)

                    db._race_ids[(round_number, cup_idx, race_idx)] = race_row["id"]

                    if race.completed:
                        # Restore player scores
                        for res in conn.execute(
                            "SELECT player_id, score FROM race_results WHERE race_id=?",
                            (race_row["id"],),
                        ).fetchall():
                            players_by_id[res["player_id"]].scores.append(res["score"])
                        # Restore team match history
                        for team in cup_teams:
                            for opp in cup_teams:
                                if opp is not team:
                                    team.opponents_faced.append(opp)

                round_.cups.append(cup)

            tourney.rounds.append(round_)
            tourney.current_round = round_number

        return tourney, db

    # ------------------------------------------------------------------
    # Query path — read historical data without restoring in-memory state
    # ------------------------------------------------------------------

    def delete_cup_results(self, tournament_id: int, round_number: int, cup_number: int):
        """Remove race_results rows and reset completed flags for one cup. Used by PATCH correction."""
        cur = self.conn.cursor()
        race_rows = cur.execute("""
            SELECT r.id FROM races r
            JOIN cups   c  ON r.cup_id   = c.id
            JOIN rounds rd ON c.round_id = rd.id
            WHERE rd.tournament_id = ? AND rd.round_number = ? AND c.cup_number = ?
            ORDER BY r.race_number
        """, (tournament_id, round_number, cup_number)).fetchall()
        race_ids = [row["id"] for row in race_rows]
        if race_ids:
            ph = ",".join("?" * len(race_ids))
            cur.execute(f"DELETE FROM race_results WHERE race_id IN ({ph})", race_ids)
            cur.execute(f"UPDATE races SET completed=0 WHERE id IN ({ph})", race_ids)
        self.conn.commit()

    def get_cup_results(self, tournament_id: int, round_number: int, cup_number: int) -> list[dict]:
        """Return all race_results for one cup, annotated with player/team names."""
        rows = self.conn.execute("""
            SELECT r.race_number,
                   pl.name  AS player_name,
                   p1.name  AS player1,
                   p2.name  AS player2,
                   rr.place,
                   rr.score
            FROM race_results rr
            JOIN races   r  ON rr.race_id   = r.id
            JOIN cups    c  ON r.cup_id     = c.id
            JOIN rounds  rd ON c.round_id   = rd.id
            JOIN players pl ON rr.player_id = pl.id
            JOIN teams   tm ON (pl.id = tm.player1_id OR pl.id = tm.player2_id)
            JOIN players p1 ON tm.player1_id = p1.id
            JOIN players p2 ON tm.player2_id = p2.id
            WHERE rd.tournament_id = ? AND rd.round_number = ? AND c.cup_number = ?
            ORDER BY r.race_number, rr.place
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
                     SELECT 1 FROM races r
                     JOIN cups c  ON r.cup_id   = c.id
                     JOIN rounds rd ON c.round_id = rd.id
                     WHERE rd.tournament_id = t.id AND r.completed = 0
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
                     SELECT 1 FROM races r
                     JOIN cups c  ON r.cup_id   = c.id
                     JOIN rounds rd ON c.round_id = rd.id
                     WHERE rd.tournament_id = t.id AND r.completed = 0
                 ))                                               AS is_complete
            FROM tournaments t
            WHERE t.id = ?
        """, (tournament_id,)).fetchone()
        return dict(row) if row else None

    def get_leaderboard(self, tournament_id: int) -> list[dict]:
        """
        Sum every race-result score for each team's two players across all
        races in the tournament.  Teams are discovered via the cup_teams
        participation chain (rounds → cups → cup_teams → teams).
        """
        rows = self.conn.execute("""
            SELECT
                p1.name                AS player1,
                p2.name                AS player2,
                COALESCE(SUM(rr.score), 0) AS total_score
            FROM race_results rr
            JOIN races   r  ON rr.race_id  = r.id
            JOIN cups    c  ON r.cup_id    = c.id
            JOIN rounds  rd ON c.round_id  = rd.id
            JOIN players pl ON rr.player_id = pl.id
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
