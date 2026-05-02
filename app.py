import os
import secrets
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator, model_validator

from RosterEntry import Player, Team
from Round import CUPS_PER_ROUND, get_cup_label
from Tournament import Tournament, TOTAL_TEAMS, TOTAL_ROUNDS
from db import TournamentDB

app = FastAPI(title="Mario Kart Tournament")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DB_PATH = "db/mariokart.db"

# ---------------------------------------------------------------------------
# Auth — simple signed-cookie session, credentials hardcoded as defaults
# ---------------------------------------------------------------------------

ADMIN_SESSION_TOKEN = secrets.token_hex(32)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password"


def _is_admin(request: Request) -> bool:
    return request.cookies.get("mk_admin") == ADMIN_SESSION_TOKEN


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

_roster: list[Team] = []
_tournament: Optional[Tournament] = None
_db: Optional[TournamentDB] = None


@app.on_event("startup")
def _restore_state():
    """If mariokart.db contains an incomplete tournament, rebuild in-memory state from it."""
    global _roster, _tournament, _db
    if not os.path.exists(DB_PATH):
        return

    tmp = TournamentDB(DB_PATH)
    rows = tmp.list_tournaments()
    tmp.close()

    incomplete = [r for r in rows if not bool(r["is_complete"])]
    if not incomplete:
        return

    tournament_id = incomplete[0]["id"]
    restored, restored_db = TournamentDB.load_tournament(DB_PATH, tournament_id)
    _tournament = restored
    _db = restored_db
    _roster = list(restored.teams)
    print(f"[startup] Restored tournament #{tournament_id} "
          f"(round {restored.current_round}/{TOTAL_ROUNDS})")


# ---------------------------------------------------------------------------
# Schemas — roster
# ---------------------------------------------------------------------------

class AddTeamRequest(BaseModel):
    player1_name: str
    player2_name: str

    @field_validator("player1_name", "player2_name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("player2_name")
    @classmethod
    def names_must_differ(cls, v: str, info) -> str:
        if v.lower() == (info.data.get("player1_name") or "").lower():
            raise ValueError("Both players on a team must have different names.")
        return v


class EditTeamRequest(BaseModel):
    player1_name: Optional[str] = None
    player2_name: Optional[str] = None

    @field_validator("player1_name", "player2_name", mode="before")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v is not None else v

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.player1_name is None and self.player2_name is None:
            raise ValueError("Provide at least one of player1_name or player2_name.")
        return self


class TeamResponse(BaseModel):
    team_id: int
    player1: str
    player2: str


class RosterResponse(BaseModel):
    teams: list[TeamResponse]
    count: int


# ---------------------------------------------------------------------------
# Schemas — tournament lifecycle
# ---------------------------------------------------------------------------

class CupAssignment(BaseModel):
    cup_number: int
    teams: list[str]


class TournamentStartRequest(BaseModel):
    group_a: list[int]  # team_ids (1-indexed, as returned by GET /teams)
    group_b: list[int]

    @model_validator(mode="after")
    def validate_groups(self):
        teams_per_cup = TOTAL_TEAMS // CUPS_PER_ROUND
        if len(self.group_a) != teams_per_cup:
            raise ValueError(f"Group A must have {teams_per_cup} teams, got {len(self.group_a)}.")
        if len(self.group_b) != teams_per_cup:
            raise ValueError(f"Group B must have {teams_per_cup} teams, got {len(self.group_b)}.")
        overlap = set(self.group_a) & set(self.group_b)
        if overlap:
            raise ValueError(f"Teams appear in both groups: {sorted(overlap)}.")
        return self


class TournamentStartResponse(BaseModel):
    round_number: int
    cups: list[CupAssignment]


# ---------------------------------------------------------------------------
# Schemas — past tournaments
# ---------------------------------------------------------------------------

class TournamentSummary(BaseModel):
    id: int
    created_at: str
    total_rounds: int
    rounds_completed: int
    is_complete: bool


class TournamentsListResponse(BaseModel):
    tournaments: list[TournamentSummary]


class LeaderboardEntry(BaseModel):
    rank: int
    team: str
    player1: str
    player2: str
    total_score: int


class TournamentDetailResponse(BaseModel):
    id: int
    created_at: str
    total_rounds: int
    rounds_completed: int
    is_complete: bool
    leaderboard: list[LeaderboardEntry]


# ---------------------------------------------------------------------------
# Schemas — cup results
# ---------------------------------------------------------------------------

class PlayerScore(BaseModel):
    player_name: str
    score: int

    @field_validator("player_name", mode="before")
    @classmethod
    def strip_player_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("score")
    @classmethod
    def positive_score(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Score must be at least 1.")
        return v


class CupResultsRequest(BaseModel):
    placements: list[PlayerScore]


class PlayerCupResult(BaseModel):
    player_name: str
    team_name: str
    score: int


class TeamCupStanding(BaseModel):
    rank: int
    team_name: str
    cup_points: int
    total_points: int


class CupResultsResponse(BaseModel):
    round_number: int
    cup_number: int
    placements: list[PlayerCupResult]
    cup_standings: list[TeamCupStanding]
    round_complete: bool


# ---------------------------------------------------------------------------
# UI routes — public
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def public_view(request: Request):
    return templates.TemplateResponse("public.html", {"request": request})


# ---------------------------------------------------------------------------
# UI routes — admin auth
# ---------------------------------------------------------------------------

@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/auth/login")
async def do_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie("mk_admin", ADMIN_SESSION_TOKEN, httponly=True, samesite="lax")
        return resp
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid username or password."},
        status_code=401,
    )


@app.post("/auth/logout")
def do_logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie("mk_admin")
    return resp


@app.get("/admin", response_class=HTMLResponse)
def admin_view(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse("admin.html", {"request": request})


# ---------------------------------------------------------------------------
# API — tournament status (used by both public and admin JS)
# ---------------------------------------------------------------------------

@app.get("/tournament/status")
def tournament_status():
    if _tournament is None:
        return {
            "state": "not_started",
            "current_round": 0,
            "total_rounds": TOTAL_ROUNDS,
            "leaderboard": [],
            "active_cups": [],
        }

    state = "complete" if _tournament.is_complete else "in_progress"
    leaderboard = [
        {
            "rank": i + 1,
            "team": t.name,
            "player1": t.players[0].name,
            "player2": t.players[1].name,
            "score": t.total_score,
        }
        for i, t in enumerate(_tournament.leaderboard)
    ]

    active_round = _tournament._active_round()
    active_cups = [
        {
            "cup_number": cup.cup_number,
            "label": get_cup_label(active_round.round_number, cup.cup_number),
            "teams": [t.name for t in cup.teams],
            "completed": cup.completed,
        }
        for cup in active_round.cups
    ]

    return {
        "state": state,
        "current_round": _tournament.current_round,
        "total_rounds": TOTAL_ROUNDS,
        "leaderboard": leaderboard,
        "active_cups": active_cups,
    }


# ---------------------------------------------------------------------------
# API routes — roster
# ---------------------------------------------------------------------------

@app.post("/teams", status_code=status.HTTP_201_CREATED, response_model=TeamResponse)
def add_team(body: AddTeamRequest):
    """Register a new team. Both player names must be unique across the entire roster."""
    if _tournament is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Tournament has already started; the roster is locked.")

    registered_names = {p.name.lower() for team in _roster for p in team.players}
    for name in (body.player1_name, body.player2_name):
        if name.lower() in registered_names:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"'{name}' is already registered in the roster.")

    team = Team(Player(body.player1_name), Player(body.player2_name))
    _roster.append(team)
    return TeamResponse(team_id=len(_roster), player1=team.players[0].name, player2=team.players[1].name)


@app.patch("/teams/{team_id}", response_model=TeamResponse)
def edit_team(team_id: int, body: EditTeamRequest):
    """Update one or both player names on a team. Omit a field to leave that player unchanged."""
    if _tournament is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Tournament has already started; the roster is locked.")

    if team_id < 1 or team_id > len(_roster):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Team {team_id} not found.")

    team = _roster[team_id - 1]
    new_p1 = body.player1_name if body.player1_name is not None else team.players[0].name
    new_p2 = body.player2_name if body.player2_name is not None else team.players[1].name

    if new_p1.lower() == new_p2.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Both players on a team must have different names.")

    other_names = {
        p.name.lower()
        for i, t in enumerate(_roster)
        if i != team_id - 1
        for p in t.players
    }
    for name in (new_p1, new_p2):
        if name.lower() in other_names:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"'{name}' is already registered on another team.")

    team.players[0].name = new_p1
    team.players[1].name = new_p2
    return TeamResponse(team_id=team_id, player1=new_p1, player2=new_p2)


@app.get("/teams", response_model=RosterResponse)
def list_teams():
    """Return all currently registered teams."""
    return RosterResponse(
        teams=[
            TeamResponse(team_id=i + 1, player1=t.players[0].name, player2=t.players[1].name)
            for i, t in enumerate(_roster)
        ],
        count=len(_roster),
    )


# ---------------------------------------------------------------------------
# API routes — tournament lifecycle
# ---------------------------------------------------------------------------

@app.post("/tournament/start", status_code=status.HTTP_201_CREATED,
          response_model=TournamentStartResponse)
def start_tournament(body: TournamentStartRequest):
    """Lock the roster and start the tournament with admin-specified round-1 cup groups."""
    global _tournament, _db
    if _tournament is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Tournament has already started.")
    if len(_roster) != TOTAL_TEAMS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Need exactly {TOTAL_TEAMS} teams to start "
                                   f"(currently have {len(_roster)}).")

    all_ids = set(range(1, len(_roster) + 1))
    submitted_ids = set(body.group_a + body.group_b)
    if submitted_ids != all_ids:
        missing = sorted(all_ids - submitted_ids)
        extra = sorted(submitted_ids - all_ids)
        parts = []
        if missing: parts.append(f"missing team IDs: {missing}")
        if extra:   parts.append(f"invalid team IDs: {extra}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Groups must contain all registered teams. {'; '.join(parts)}")

    cup_1_teams = [_roster[i - 1] for i in body.group_a]
    cup_2_teams = [_roster[i - 1] for i in body.group_b]

    _db = TournamentDB(DB_PATH)
    _tournament = Tournament(_roster, db=_db)
    rnd = _tournament.start_first_round(cup_1_teams, cup_2_teams)

    return TournamentStartResponse(
        round_number=rnd.round_number,
        cups=[
            CupAssignment(cup_number=cup.cup_number, teams=[t.name for t in cup.teams])
            for cup in rnd.cups
        ],
    )


@app.post("/tournament/new", status_code=status.HTTP_200_OK)
def new_tournament():
    """Reset state for a fresh tournament. Blocked while a tournament is in progress."""
    global _roster, _tournament, _db
    if _tournament is not None and not _tournament.is_complete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Current tournament is still in progress. "
                   "Complete all rounds before starting a new one.",
        )
    if _db is not None:
        _db.close()
    _roster = []
    _tournament = None
    _db = None
    return {"message": "Ready for new tournament. Register your teams and POST /tournament/start."}


# ---------------------------------------------------------------------------
# API routes — cup results (submit, view, correct)
# ---------------------------------------------------------------------------

def _validate_cup_scores(cup, placements: list[PlayerScore]) -> dict[str, Player]:
    """Validate that all cup players are present with no extras. Returns player_by_name."""
    player_by_name: dict[str, Player] = {}
    team_by_player: dict[str, Team] = {}
    for team in cup.teams:
        for player in team.players:
            player_by_name[player.name.lower()] = player
            team_by_player[player.name.lower()] = team

    expected = set(player_by_name.keys())
    submitted = {p.player_name.lower() for p in placements}
    if submitted != expected:
        missing = sorted(expected - submitted)
        extra = sorted(submitted - expected)
        parts = []
        if missing: parts.append(f"missing: {missing}")
        if extra:   parts.append(f"unknown players: {extra}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Player mismatch — {'; '.join(parts)}")
    return player_by_name


def _build_cup_response(round_number, cup_number, cup, placements, player_by_name,
                         scores_before, round_complete) -> CupResultsResponse:
    placement_list = [
        PlayerCupResult(
            player_name=player_by_name[p.player_name.lower()].name,
            team_name=next(
                t for t in cup.teams
                if any(pl.name.lower() == p.player_name.lower() for pl in t.players)
            ).name,
            score=p.score,
        )
        for p in sorted(placements, key=lambda p: p.score, reverse=True)
    ]

    cup_standings = sorted(cup.teams, key=lambda t: t.total_score - scores_before[t], reverse=True)
    standings = [
        TeamCupStanding(
            rank=i + 1,
            team_name=team.name,
            cup_points=team.total_score - scores_before[team],
            total_points=team.total_score,
        )
        for i, team in enumerate(cup_standings)
    ]
    return CupResultsResponse(
        round_number=round_number,
        cup_number=cup_number,
        placements=placement_list,
        cup_standings=standings,
        round_complete=round_complete,
    )


@app.post("/rounds/{round_number}/cups/{cup_number}/results",
          response_model=CupResultsResponse)
def submit_cup_results(round_number: int, cup_number: int, body: CupResultsRequest):
    """Submit cumulative scores for all players in a cup."""
    if _tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Tournament has not started. POST /tournament/start first.")
    if _tournament.is_complete:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Tournament is complete; no more results can be submitted.")
    if round_number != _tournament.current_round:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Active round is {_tournament.current_round}, not {round_number}.")

    active_round = _tournament._active_round()
    if cup_number < 1 or cup_number > len(active_round.cups):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Cup {cup_number} not found in round {round_number}.")

    cup = active_round.cups[cup_number - 1]
    if cup.completed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Results for round {round_number}, cup {cup_number} "
                                   f"have already been submitted.")

    player_by_name = _validate_cup_scores(cup, body.placements)
    scores_before = {team: team.total_score for team in cup.teams}

    placements = [(player_by_name[p.player_name.lower()], p.score) for p in body.placements]
    _tournament.record_cup_results(cup_number - 1, placements)

    round_complete = active_round.completed
    if round_complete and not _tournament.is_complete:
        _tournament.advance_round()

    return _build_cup_response(round_number, cup_number, cup, body.placements,
                                player_by_name, scores_before, round_complete)


@app.get("/rounds/{round_number}/cups/{cup_number}/results")
def get_cup_results(round_number: int, cup_number: int, request: Request):
    """Return submitted scores for one cup (admin only). Empty list if not yet submitted."""
    if not _is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    if _tournament is None or _db is None:
        return {"round_number": round_number, "cup_number": cup_number, "placements": []}

    rows = _db.get_cup_results(_db.tournament_id, round_number, cup_number)
    return {
        "round_number": round_number,
        "cup_number": cup_number,
        "placements": [dict(r) for r in rows],
    }


@app.patch("/rounds/{round_number}/cups/{cup_number}/results",
           response_model=CupResultsResponse)
def correct_cup_results(round_number: int, cup_number: int,
                         body: CupResultsRequest, request: Request):
    """Correct already-submitted cup scores. Rebuilds in-memory state from DB after correction."""
    global _roster, _tournament, _db

    if not _is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    if _tournament is None or _db is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active tournament.")

    target_round = next((r for r in _tournament.rounds if r.round_number == round_number), None)
    if target_round is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Round {round_number} not found.")
    if cup_number < 1 or cup_number > len(target_round.cups):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Cup {cup_number} not found in round {round_number}.")

    cup = target_round.cups[cup_number - 1]
    player_by_name = _validate_cup_scores(cup, body.placements)

    old_tournament_id = _db.tournament_id
    _db.delete_cup_results(old_tournament_id, round_number, cup_number)
    placements = [(player_by_name[p.player_name.lower()], p.score) for p in body.placements]
    _db.save_cup_results(round_number, cup_number - 1, placements)

    new_tourney, new_db = TournamentDB.load_tournament(DB_PATH, old_tournament_id)
    _db.close()
    _tournament = new_tourney
    _db = new_db
    _roster = list(new_tourney.teams)

    new_round = next(r for r in _tournament.rounds if r.round_number == round_number)
    new_cup = new_round.cups[cup_number - 1]
    scores_before = {t: 0 for t in new_cup.teams}

    return _build_cup_response(round_number, cup_number, new_cup, body.placements,
                                player_by_name, scores_before, new_round.completed)


# ---------------------------------------------------------------------------
# API routes — statistics
# ---------------------------------------------------------------------------

@app.get("/admin/statistics")
def get_statistics(request: Request):
    """Per-round scores for all teams and players in the active tournament (admin only)."""
    if not _is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    if _tournament is None or _db is None:
        return {"rounds_played": 0, "round_numbers": [], "teams": [], "players": []}

    rows = _db.get_round_scores(_db.tournament_id)
    round_numbers = sorted({r["round_number"] for r in rows})

    # Aggregate team scores per round (sum of both players)
    team_scores: dict[str, dict[int, int]] = {}
    player_scores: dict[str, dict] = {}

    for row in rows:
        team_name = f"{row['player1']} & {row['player2']}"
        rn = row["round_number"]

        if team_name not in team_scores:
            team_scores[team_name] = {}
        team_scores[team_name][rn] = team_scores[team_name].get(rn, 0) + row["score"]

        pname = row["player_name"]
        if pname not in player_scores:
            player_scores[pname] = {"name": pname, "team": team_name, "by_round": {}}
        player_scores[pname]["by_round"][rn] = row["score"]

    def scores_list(by_round):
        return [by_round.get(rn, 0) for rn in round_numbers]

    # Sort teams by total score descending for stable color assignment
    sorted_teams = sorted(
        team_scores.items(),
        key=lambda kv: sum(kv[1].values()),
        reverse=True,
    )

    # Sort players by total score descending for the table
    sorted_players = sorted(
        player_scores.values(),
        key=lambda p: sum(p["by_round"].values()),
        reverse=True,
    )

    return {
        "rounds_played": len(round_numbers),
        "round_numbers": round_numbers,
        "teams": [
            {"name": name, "round_scores": scores_list(by_round)}
            for name, by_round in sorted_teams
        ],
        "players": [
            {"name": p["name"], "team": p["team"], "round_scores": scores_list(p["by_round"])}
            for p in sorted_players
        ],
    }


# ---------------------------------------------------------------------------
# API routes — past tournament history
# ---------------------------------------------------------------------------

def _open_db_readonly():
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No tournament history found.")
    return TournamentDB(DB_PATH)


@app.get("/tournaments", response_model=TournamentsListResponse)
def list_tournaments():
    """List every tournament stored in the database, newest first."""
    db = _open_db_readonly()
    try:
        rows = db.list_tournaments()
    finally:
        db.close()
    return TournamentsListResponse(
        tournaments=[
            TournamentSummary(
                id=r["id"],
                created_at=r["created_at"],
                total_rounds=r["total_rounds"],
                rounds_completed=r["rounds_completed"],
                is_complete=bool(r["is_complete"]),
            )
            for r in rows
        ]
    )


@app.get("/tournaments/{tournament_id}", response_model=TournamentDetailResponse)
def get_tournament(tournament_id: int):
    """Return metadata and final leaderboard for one past tournament."""
    db = _open_db_readonly()
    try:
        meta = db.get_tournament_meta(tournament_id)
        if meta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Tournament {tournament_id} not found.")
        board = db.get_leaderboard(tournament_id)
    finally:
        db.close()

    return TournamentDetailResponse(
        id=meta["id"],
        created_at=meta["created_at"],
        total_rounds=meta["total_rounds"],
        rounds_completed=meta["rounds_completed"],
        is_complete=bool(meta["is_complete"]),
        leaderboard=[
            LeaderboardEntry(
                rank=i + 1,
                team=f"{r['player1']} & {r['player2']}",
                player1=r["player1"],
                player2=r["player2"],
                total_score=r["total_score"],
            )
            for i, r in enumerate(board)
        ],
    )
