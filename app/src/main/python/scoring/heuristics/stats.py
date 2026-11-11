"""Full-precision team totals shared by heuristics and scoring reports."""

from core.game_state import GameState, Player


def team_stats(state: GameState) -> dict:
    result = {}
    for player in (Player.Player1, Player.Player2):
        planets = [p for p in state.planets if p.owner == player]
        stationed = sum(p.n_ships for p in planets)
        flying = sum(p.transporter.n_ships for p in state.planets
                     if p.transporter is not None and p.transporter.owner == player)
        result[player.value] = {"planetCount": len(planets), "stationedShips": stationed,
                                "shipsInFlight": flying, "totalShips": stationed + flying}
    return result
