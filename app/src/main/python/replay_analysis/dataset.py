"""Sample replay states for a small, game-linked analysis dataset."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Iterable

from core.game_replay import load_replay, replay_game
from core.game_state import Action, GameParams, GameState, Player


@dataclass
class Position:
    game_id: str
    replay_path: str
    tick: int
    player: Player
    bot: str
    outcome: float
    state: GameState
    params: GameParams
    played_action: Action
    static_value: float
    features: dict[str, float] = field(default_factory=dict)

    @property
    def position_id(self) -> str:
        return f"{self.game_id}:{self.tick}:{self.player.value}"

    def row(self) -> dict:
        return {
            "position_id": self.position_id,
            "game_id": self.game_id,
            "tick": self.tick,
            "player": self.player.value,
            "bot": self.bot,
            "outcome": self.outcome,
            "static_value": self.static_value,
            "features": json.dumps(self.features, sort_keys=True),
            "played_action": json.dumps(
                self.played_action.model_dump(mode="json", by_alias=True), sort_keys=True),
        }


def _features(evaluator, state: GameState, player: Player,
              params: GameParams) -> dict[str, float]:
    feature_fn = getattr(evaluator, "features", None)
    if not callable(feature_fn):
        return {}
    return {str(key): float(value)
            for key, value in feature_fn(state, player, params).items()}


def collect_positions(paths: Iterable[str | Path], evaluator, *, stride: int = 20,
                      verify_replays: bool = True,
                      max_positions_per_game: int | None = None) -> list[Position]:
    """Take both player perspectives before each selected replay tick.

    The cap counts selected ticks, so each tick yields two position rows.
    Terminal states are omitted because they have no move to analyze.
    """
    if stride < 1:
        raise ValueError("stride must be positive")
    if max_positions_per_game is not None and max_positions_per_game < 1:
        raise ValueError("max_positions_per_game must be positive")

    positions: list[Position] = []
    seen_games: set[str] = set()
    for path_value in paths:
        path = Path(path_value).resolve()
        replay = load_replay(path)
        game_id = hashlib.sha256(path.read_bytes()).hexdigest()[:20]
        if game_id in seen_games:
            continue
        seen_games.add(game_id)
        if verify_replays:
            for _ in replay_game(replay, verify=True):
                pass
        params = GameParams.model_validate(replay["params"])
        winner = Player(replay["winner"])
        initial = GameState.model_validate(replay["initialState"])
        bots = replay.get("agents", {})
        selected = 0
        for entry_index, entry in enumerate(replay["ticks"]):
            tick = int(entry["tick"])
            if tick % stride:
                continue
            state = (initial if entry_index == 0 else
                     GameState.model_validate(replay["ticks"][entry_index - 1]["state"]))
            if state.game_tick != tick:
                raise ValueError(f"Replay tick mismatch in {path}: {tick} != {state.game_tick}")
            actions = entry.get("actions", {})
            for player in (Player.Player1, Player.Player2):
                action_data = actions.get(player.value)
                action = Action.model_validate(action_data) if action_data else Action.do_nothing()
                value = float(evaluator.evaluate(state, player, params))
                if not 0 <= value <= 1:
                    raise ValueError(f"Evaluator returned a value outside [0, 1] at {path}:{tick}")
                positions.append(Position(
                    game_id=game_id, replay_path=str(path), tick=tick, player=player,
                    bot=str(bots.get(player.value, player.value)),
                    outcome=(0.5 if winner == Player.Neutral else float(winner == player)),
                    state=state, params=params, played_action=action,
                    static_value=value, features=_features(evaluator, state, player, params)))
            selected += 1
            if max_positions_per_game is not None and selected >= max_positions_per_game:
                break
    return positions
