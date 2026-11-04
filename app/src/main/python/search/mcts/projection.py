"""Project existing fleets without assuming any future launches.

Arrival times and combat match ForwardModel: arrival is checked before movement,
owned planets grow before combat, same-tick fleets resolve together, and ties do
not change ownership. Growth follows the current owner after every capture.
"""

from dataclasses import dataclass
import math

from core.game_state import GameParams, GameState, Planet, Player, Transporter


@dataclass(frozen=True)
class Arrival:
    tick: int  # Relative to the supplied state; the next update is tick 1.
    owner: Player
    ships: float


@dataclass(frozen=True)
class PlanetProjection:
    owner: Player
    ships: float
    tick: int


def remaining_ticks(state: GameState, params: GameParams) -> int:
    # ForwardModel stops only once game_tick > max_ticks.
    return max(0, params.max_ticks - state.game_tick + 1)


def arrival_tick(fleet: Transporter, target: Planet, horizon: int) -> int | None:
    """First discrete arrival within horizon, including overshooting/stalled fleets."""
    if horizon < 1 or target.radius <= 0:
        return None
    dx = fleet.s.x - target.position.x
    dy = fleet.s.y - target.position.y
    a = fleet.v.x ** 2 + fleet.v.y ** 2
    c = dx * dx + dy * dy - target.radius ** 2
    if c < 0:
        return 1
    if a == 0:
        return None
    b = 2 * (dx * fleet.v.x + dy * fleet.v.y)
    discriminant = b * b - 4 * a * c
    if discriminant <= 0:
        return None
    enter = (-b - math.sqrt(discriminant)) / (2 * a)
    # k movements have occurred when update k+1 checks arrival.
    k = max(0, math.floor(enter) + 1)
    # Verify near the boundary to avoid floating-point root rounding errors.
    for movements in range(max(0, k - 1), min(horizon - 1, k + 1) + 1):
        if ((dx + movements * fleet.v.x) ** 2 +
                (dy + movements * fleet.v.y) ** 2 < target.radius ** 2):
            return movements + 1
    return None


def incoming_fleets(state: GameState, params: GameParams) -> dict[int, list[Arrival]]:
    incoming: dict[int, list[Arrival]] = {p.id: [] for p in state.planets}
    for source in state.planets:
        fleet = source.transporter
        if fleet is None:
            continue
        target = state.planets[fleet.destination_index]
        tick = arrival_tick(fleet, target, remaining_ticks(state, params))
        if tick is not None:
            incoming[target.id].append(Arrival(tick, fleet.owner, fleet.n_ships))
    return incoming


def project_planet(planet: Planet, arrivals: list[Arrival],
                   until_tick: int | None = None) -> PlanetProjection:
    owner, ships, previous = planet.owner, planet.n_ships, 0
    groups: dict[int, dict[Player, float]] = {}
    for arrival in arrivals:
        if until_tick is not None and arrival.tick > until_tick:
            continue
        forces = groups.setdefault(arrival.tick, {})
        forces[arrival.owner] = forces.get(arrival.owner, 0.0) + arrival.ships
    for tick, forces in sorted(groups.items()):
        if owner != Player.Neutral:
            ships += planet.growth_rate * (tick - previous)
            ships += forces.get(owner, 0.0) - forces.get(owner.opponent(), 0.0)
            if ships < 0:
                owner, ships = owner.opponent(), -ships
        else:
            net = forces.get(Player.Player1, 0.0) - forces.get(Player.Player2, 0.0)
            ships -= abs(net)
            if ships < 0:
                owner = Player.Player1 if net > 0 else Player.Player2
                ships = -ships
        previous = tick
    if until_tick is not None and until_tick > previous:
        if owner != Player.Neutral:
            ships += planet.growth_rate * (until_tick - previous)
        previous = until_tick
    return PlanetProjection(owner, ships, previous)


def project_board(state: GameState, params: GameParams) -> dict[int, PlanetProjection]:
    incoming = incoming_fleets(state, params)
    return {p.id: project_planet(p, incoming[p.id]) for p in state.planets}
