"""Run one fixed-depth MCTS search for each sampled position."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Iterable

from replay_analysis.dataset import Position
from search.mcts import MCTS, MCTSConfig
from search.mcts.policies import ActionGenerator


def _action_key(action) -> str:
    return json.dumps(action.model_dump(mode="json", by_alias=True), sort_keys=True)


def _position_seed(position: Position, base_seed: int) -> int:
    digest = hashlib.sha256(position.position_id.encode()).digest()
    return (int.from_bytes(digest[:4], "big") + base_seed) % (2 ** 31)


def search_positions(positions: Iterable[Position], evaluator, *, depth: int = 8,
                     iterations: int = 32, rollout_depth: int = 0,
                     exploration_constant: float = math.sqrt(2), seed: int = 42,
                     action_generator: ActionGenerator | None = None,
                     progress=None) -> list[dict]:
    """Return the best estimated root move, played-move regret, and root actions.

    Depth is an MCTS tree-depth cap in game ticks, not uniform minimax ply.
    The played action is inserted as a root candidate for the regret estimate.
    """
    if depth < 1 or iterations < 1 or rollout_depth < 0:
        raise ValueError("depth and iterations must be positive; rollout_depth must be nonnegative")
    if exploration_constant < 0 or not math.isfinite(exploration_constant):
        raise ValueError("exploration_constant must be finite and nonnegative")

    positions = list(positions)
    rows = []
    for index, position in enumerate(positions, 1):
        engine = MCTS(MCTSConfig(
            iterations=iterations, tree_depth=depth, rollout_depth=rollout_depth,
            exploration_constant=exploration_constant,
            seed=_position_seed(position, seed)),
            action_generator=action_generator, evaluator=evaluator)
        result = engine.search(position.state, position.player, position.params,
                               forced_root_actions=(position.played_action,))
        best = max(result.root_actions,
                   key=lambda action: (action.mean_value, action.visits), default=None)
        best_key = _action_key(best.action) if best else None
        played_key = _action_key(position.played_action)
        stats_by_action = {_action_key(action.action): action for action in result.root_actions}
        heuristic_by_action = {_action_key(action.action): action
                               for action in result.heuristic_action_values}
        played = stats_by_action.get(played_key)
        root_actions = []
        for key, action in stats_by_action.items():
            heuristic = heuristic_by_action.get(key)
            root_actions.append({
                "action": action.action.model_dump(mode="json", by_alias=True),
                "visits": action.visits,
                "search_value": action.mean_value,
                "heuristic_value": heuristic.value if heuristic else None,
                "heuristic_terms": heuristic.terms if heuristic else {},
                "is_best": key == best_key,
                "is_played": key == played_key,
            })
        best_value = best.mean_value if best else None
        played_value = played.mean_value if played else None
        rows.append({
            "position_id": position.position_id,
            "search_value": best_value,
            "best_action": best.action.model_dump(mode="json", by_alias=True) if best else None,
            "best_action_value": best_value,
            "played_action_value": played_value,
            "regret": (max(0.0, best_value - played_value)
                       if best_value is not None and played_value is not None else None),
            "root_actions": root_actions,
        })
        if progress:
            progress(index, len(positions))
    return rows
