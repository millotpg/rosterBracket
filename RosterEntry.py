PLACEMENT_SCORES = {1: 15, 2: 12, 3: 10, 4: 9, 5: 8, 6: 7, 7: 6, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}


class Player:
    def __init__(self, name: str):
        self.name = name
        self.scores: list[int] = []

    @property
    def total_score(self) -> int:
        return sum(self.scores)

    def record_placement(self, place: int):
        self.scores.append(PLACEMENT_SCORES.get(place, 0))

    def __repr__(self):
        return f"Player({self.name}, score={self.total_score})"


class Team:
    def __init__(self, player1: Player, player2: Player):
        self.players: tuple[Player, Player] = (player1, player2)
        self.opponents_faced: list["Team"] = []

    @property
    def total_score(self) -> int:
        return sum(p.total_score for p in self.players)

    def record_match(self, opponent: "Team"):
        self.opponents_faced.append(opponent)

    def times_faced(self, opponent: "Team") -> int:
        return self.opponents_faced.count(opponent)

    @property
    def name(self) -> str:
        return f"{self.players[0].name} & {self.players[1].name}"

    def __repr__(self):
        return f"Team({self.name}, score={self.total_score})"
