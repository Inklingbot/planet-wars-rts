"""Configurable board strength, scored from the supplied player's view."""

from dataclasses import dataclass, asdict
import math

from core.game_state import GameParams, GameState, Player
from core.terminal import terminal_value
from core.fleet_projection import project_board


@dataclass(frozen=True)
class BoardWeights:
    planets: float = 1.0
    growth: float = 1.0
    ships: float = 1.0
    expected_captures: float = 1.0
    planets_over_10: float = 1.0

    def __post_init__(self):
        values = asdict(self).values()
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Board weights must be finite and nonnegative")
        if sum(asdict(self).values()) == 0:
            raise ValueError("At least one board weight must be positive")


class BoardStrengthEvaluator:
    def __init__(self, weights: BoardWeights | None = None):
        self.weights = weights or BoardWeights()

    def features(self, state: GameState, player: Player, params: GameParams) -> dict[str, float]:
        opponent = player.opponent()
        def total(owner, attribute):
            return sum(getattr(p, attribute) for p in state.planets if p.owner == owner)
        def difference(own, enemy):
            return (own - enemy) / (own + enemy) if own + enemy else 0.0
        n = max(1, len(state.planets))
        own_count = sum(p.owner == player for p in state.planets)
        enemy_count = sum(p.owner == opponent for p in state.planets)
        ships = {owner: total(owner, "n_ships") for owner in (player, opponent)}
        for planet in state.planets:
            fleet = planet.transporter
            if fleet is not None and fleet.owner in ships:
                ships[fleet.owner] += fleet.n_ships
        projected = project_board(state, params)
        gains = sum(p.owner != player and projected[p.id].owner == player for p in state.planets)
        losses = sum(p.owner == player and projected[p.id].owner != player for p in state.planets)
        return {
            "planets": (own_count - enemy_count) / n,
            "growth": difference(total(player, "growth_rate"), total(opponent, "growth_rate")),
            "ships": difference(ships[player], ships[opponent]),
            "expected_captures": (gains - losses) / n,
            "planets_over_10": sum(p.owner == player and p.n_ships > 10
                                   for p in state.planets) / n,
        }

    def evaluate(self, state: GameState, player: Player, params: GameParams) -> float:
        # Keep standalone evaluation consistent even outside the MCTS engine.
        outcome = terminal_value(state, player, params)
        if outcome is not None:
            return outcome
        features = self.features(state, player, params)
        weights = asdict(self.weights)
        score = sum(weights[k] * features[k] for k in weights) / sum(weights.values())
        return min(1.0, max(0.0, (score + 1) / 2))


def default_mcts_evaluator() -> BoardStrengthEvaluator:
    """One construction path for MCTS defaults and its display-only comparison."""
    return BoardStrengthEvaluator()
