"""Versioned JSON replay logs for complete, inspectable Planet Wars games."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from core.game_state import Action, GameParams, GameState, Player
from core.forward_model import ForwardModel


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(k.value if isinstance(k, Player) else k): _json_value(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Player):
        return value.value
    return value


def agent_analysis(agent) -> dict | None:
    """Return serializable diagnostics exposed by an agent, when available."""
    analysis = getattr(agent, "last_analysis", None)
    if analysis is not None:
        return _json_value(analysis)
    result = getattr(agent, "last_result", None)
    if result is None:
        return None
    to_log = getattr(result, "to_log_dict", None)
    if callable(to_log):
        return _json_value(to_log())
    if is_dataclass(result):
        return _json_value(asdict(result))
    return None


class GameReplayLogger:
    """Collect one game and persist it as a self-contained JSON document."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.game: dict | None = None
        self.games_written = 0
        self.active_path: Path | None = None

    def start(self, state: GameState, params: GameParams,
              agent_names: Mapping[Player, str] | None = None) -> None:
        sequence = self.games_written + 1
        self.active_path = (self.path if sequence == 1 else
                            self.path.with_name(f"{self.path.stem}-{sequence:04d}{self.path.suffix}"))
        self.game = {
            "schemaVersion": self.SCHEMA_VERSION,
            "params": _json_value(params),
            "agents": _json_value(agent_names or {}),
            "initialState": _json_value(state),
            "ticks": [],
        }

    def record_tick(self, state_before: GameState, actions: Mapping[Player, Action],
                    state_after: GameState, analyses: Mapping[Player, Any] | None = None) -> None:
        if self.game is None:
            raise RuntimeError("start() must be called before recording ticks")
        self.game["ticks"].append({
            "tick": state_before.game_tick,
            "actions": _json_value(actions),
            "analysis": _json_value(analyses or {}),
            # Snapshots make replays seekable and auditable without depending on
            # future changes to the simulation implementation.
            "state": _json_value(state_after),
        })

    def finish(self, final_state: GameState, winner: Player) -> None:
        if self.game is None:
            raise RuntimeError("start() must be called before finishing")
        self.game["finalState"] = _json_value(final_state)
        self.game["winner"] = winner.value
        assert self.active_path is not None
        self.active_path.parent.mkdir(parents=True, exist_ok=True)
        self.active_path.write_text(json.dumps(self.game, indent=2, allow_nan=False) + "\n",
                                    encoding="utf-8")
        self.games_written += 1


def load_replay(path: str | Path) -> dict:
    """Load and minimally validate a replay file."""
    with Path(path).open(encoding="utf-8") as source:
        replay = json.load(source)
    if replay.get("schemaVersion") != GameReplayLogger.SCHEMA_VERSION:
        raise ValueError("Unsupported replay schema version")
    if not isinstance(replay.get("initialState"), dict) or not isinstance(replay.get("ticks"), list):
        raise ValueError("Malformed replay: initialState and ticks are required")
    return replay


def replay_states(replay: dict):
    """Yield the initial state followed by each stored post-tick state."""
    yield GameState.model_validate(replay["initialState"])
    for tick in replay["ticks"]:
        yield GameState.model_validate(tick["state"])


def replay_game(replay: dict, *, verify: bool = True):
    """Re-simulate recorded actions and yield each resulting state.

    With verification enabled, fail at the first tick whose stored snapshot
    differs from the current forward model's result.
    """
    params = GameParams.model_validate(replay["params"])
    initial = GameState.model_validate(replay["initialState"])
    model = ForwardModel(initial, params, record_statistics=False)
    yield model.state.model_copy(deep=True)
    for entry in replay["ticks"]:
        actions = {Player(player): Action.model_validate(action)
                   for player, action in entry["actions"].items()}
        model.step(actions)
        if verify:
            expected = GameState.model_validate(entry["state"])
            if model.state.model_dump(mode="json") != expected.model_dump(mode="json"):
                raise ValueError(f"Replay diverged at tick {entry['tick']}")
        yield model.state.model_copy(deep=True)
    if verify and "finalState" in replay:
        expected_final = GameState.model_validate(replay["finalState"])
        if model.state.model_dump(mode="json") != expected_final.model_dump(mode="json"):
            raise ValueError("Replay final state does not match the last recorded tick")
        if "winner" in replay and model.get_leader().value != replay["winner"]:
            raise ValueError("Replay winner does not match its final state")
