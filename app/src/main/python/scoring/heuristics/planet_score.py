"""Per-planet strategic scores and their component features."""

from dataclasses import asdict, dataclass
import math

from core.game_state import GameState, Player


@dataclass(frozen=True)
class PlanetScoreWeights:
    troops: float = 1.0
    growth: float = 1.0
    centrality: float = 1.0
    vulnerability: float = 1.0

    def __post_init__(self):
        values = tuple(asdict(self).values())
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Planet score weights must be finite and nonnegative")
        if not math.isfinite(sum(values)) or sum(values) <= 0:
            raise ValueError("Planet score weights must have a positive, finite total")


@dataclass(frozen=True)
class PlanetScore:
    planet_id: int
    owner: Player
    score: float
    troops: float
    growth: float
    centrality: float
    vulnerability: float


def score_planets(state: GameState, *, top_k: int = 3,
                  weights: PlanetScoreWeights | None = None) -> list[PlanetScore]:
    """Return risk-adjusted planet scores and their normalized components.

    Troops and growth are normalized against the largest value on this board.
    Centrality is the inverse mean distance to every other planet, normalized so
    the most central planet scores 1. Vulnerability is the fraction of the
    ``top_k`` nearest planets that are enemy-owned and have a larger garrison.
    Vulnerability is subtracted from the positive asset components in the total.
    """
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise ValueError("top_k must be a nonnegative integer")
    weights = weights or PlanetScoreWeights()
    planets = state.planets
    if not planets:
        return []

    max_troops = max((max(0.0, p.n_ships) for p in planets), default=0.0)
    max_growth = max((max(0.0, p.growth_rate) for p in planets), default=0.0)
    mean_distances = []
    for planet in planets:
        distances = [planet.position.distance(other.position)
                     for other in planets if other is not planet]
        mean_distances.append(sum(distances) / len(distances) if distances else 0.0)
    inverse_distances = [1.0 / (1.0 + distance) for distance in mean_distances]
    max_centrality = max(inverse_distances, default=0.0)
    weight_sum = sum(asdict(weights).values())

    result = []
    for index, planet in enumerate(planets):
        troop_score = max(0.0, planet.n_ships) / max_troops if max_troops else 0.0
        growth_score = max(0.0, planet.growth_rate) / max_growth if max_growth else 0.0
        centrality = inverse_distances[index] / max_centrality if max_centrality else 0.0

        if top_k and planet.owner in (Player.Player1, Player.Player2):
            opponent = planet.owner.opponent()
            neighbors = sorted(
                ((planet.position.distance(other.position), other)
                 for other in planets if other is not planet),
                key=lambda item: item[0],
            )[:top_k]
            vulnerable_neighbors = sum(
                other.owner == opponent and other.n_ships > planet.n_ships
                for _, other in neighbors
            )
            vulnerability = vulnerable_neighbors / len(neighbors) if neighbors else 0.0
        else:
            vulnerability = 0.0

        components = {
            "troops": troop_score,
            "growth": growth_score,
            "centrality": centrality,
            "vulnerability": vulnerability,
        }
        score = (weights.troops * troop_score + weights.growth * growth_score +
                 weights.centrality * centrality - weights.vulnerability * vulnerability) / weight_sum
        result.append(PlanetScore(
            planet_id=planet.id,
            owner=planet.owner,
            score=score,
            troops=troop_score,
            growth=growth_score,
            centrality=centrality,
            vulnerability=vulnerability,
        ))
    return result
