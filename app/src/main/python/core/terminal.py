"""Terminal outcome values, independent of search and heuristic implementations."""

from core.forward_model import ForwardModel
from core.game_state import GameParams, GameState, Player


def terminal_value(state: GameState, player: Player, params: GameParams) -> float | None:
    """Return win=1, draw=0.5, loss=0, or None for an unfinished position.

    Follow the live forward model's termination and stationed-ship winner rules.
    This function only reads the board; it never advances the game.
    """
    model = ForwardModel(state, params, record_statistics=False)
    if not model.is_terminal():
        return None
    winner = model.get_leader()
    return 0.5 if winner == Player.Neutral else float(winner == player)
