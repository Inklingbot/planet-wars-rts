"""Ship share scoring, including fleets by their current owner."""

from core.game_state import GameParams, GameState, Player
from core.terminal import terminal_value
from .stats import team_stats


class ShipAdvantageEvaluator:
    def __init__(self, *, terminal_outcomes: bool = True):
        self.terminal_outcomes = terminal_outcomes

    def evaluate(self, state: GameState, player: Player, params: GameParams) -> float:
        if self.terminal_outcomes:
            outcome = terminal_value(state, player, params)
            if outcome is not None:
                return outcome
        stats = team_stats(state)
        own = stats[player.value]["totalShips"]
        enemy = stats[player.opponent().value]["totalShips"]
        return own / (own + enemy) if own + enemy else 0.5
