"""Score weighted ship, planet ownership, and growth shares."""

from dataclasses import asdict, dataclass
import math

from core.game_state import GameParams, GameState, Player
from core.terminal import terminal_value
from .stats import team_stats


@dataclass(frozen=True)
class ThreeFactorWeights:
    ships: float = 1.0
    planets: float = 1.0
    growth: float = 1.0

    def __post_init__(self):
        values = tuple(asdict(self).values())
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Three-factor weights must be finite and nonnegative")
        if not math.isfinite(sum(values)) or sum(values) <= 0:
            raise ValueError("Three-factor weights must have a positive, finite total")


class ThreeFactorAdvantageEvaluator:
    """Weighted average of ship share, all-planet ownership, and team growth share."""

    def __init__(self, weights: ThreeFactorWeights | None = None, *, terminal_outcomes: bool = True):
        # Preserve equal weighting for older saved profiles without weight options.
        self.weights = weights or ThreeFactorWeights()
        self.terminal_outcomes = terminal_outcomes

    def evaluate(self, state: GameState, player: Player, params: GameParams) -> float:
        if self.terminal_outcomes:
            outcome = terminal_value(state, player, params)
            if outcome is not None:
                return outcome
        stats = team_stats(state)
        own = stats[player.value]
        enemy = stats[player.opponent().value]
        ships = own["totalShips"] + enemy["totalShips"]
        ship_share = own["totalShips"] / ships if ships else 0.5
        planet_share = own["planetCount"] / len(state.planets) if state.planets else 0.5
        own_growth = sum(p.growth_rate for p in state.planets if p.owner == player)
        enemy_growth = sum(p.growth_rate for p in state.planets if p.owner == player.opponent())
        growth = own_growth + enemy_growth
        growth_share = own_growth / growth if growth else 0.5
        weights = self.weights
        return (weights.ships * ship_share + weights.planets * planet_share +
                weights.growth * growth_share) / (weights.ships + weights.planets + weights.growth)
