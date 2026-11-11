"""Named evaluator registry shared by the service and offline history tools."""

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import subprocess

import yaml

from core.game_state import GameParams, GameState, Player
from .heuristics import (BoardStrengthEvaluator, BoardWeights, default_mcts_evaluator,
                        ShipAdvantageEvaluator, ThreeFactorAdvantageEvaluator, ThreeFactorWeights,
                        team_stats)

ROOT = Path(__file__).resolve().parents[5]
DEFAULT_CONFIG = ROOT / "heuristic_comparison.yaml"
IMPLEMENTATION_VERSIONS = {"ship_advantage": 2, "three_factor_advantage": 2,
                           "board_strength": 1, "mcts_board_strength": 1}


def _ship_advantage(spec, restore):
    if spec.get("weights"):
        raise ValueError("ship_advantage has no weights")
    return ShipAdvantageEvaluator(terminal_outcomes=spec["version"] >= 2), {}


def _three_factor_advantage(spec, restore):
    evaluator = ThreeFactorAdvantageEvaluator(ThreeFactorWeights(**spec.get("weights", {})),
                                             terminal_outcomes=spec["version"] >= 2)
    # Keep old profiles' metadata/hash stable for historical score recovery.
    options = {"weights": asdict(evaluator.weights)} if "weights" in spec else {}
    return evaluator, options


def _board_strength(spec, restore):
    evaluator = BoardStrengthEvaluator(BoardWeights(**spec.get("weights", {})))
    return evaluator, {"weights": asdict(evaluator.weights)}


def _mcts_strength(spec, restore):
    if restore:
        return _board_strength(spec, restore)
    if "weights" in spec:
        raise ValueError("mcts_board_strength uses MCTS defaults; use board_strength for custom weights")
    evaluator = default_mcts_evaluator()
    return evaluator, {"weights": asdict(evaluator.weights)}


# Add a factory here and its current version above to expose another evaluator.
EVALUATOR_FACTORIES = {"ship_advantage": _ship_advantage,
                       "three_factor_advantage": _three_factor_advantage,
                       "board_strength": _board_strength,
                       "mcts_board_strength": _mcts_strength}


def code_revision() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=2, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


class Comparison:
    def __init__(self, config: dict, *, restore: bool = False):
        if not isinstance(config, dict) or set(config) != {"comparison", "evaluators"}:
            raise ValueError("Config must contain comparison and evaluators mappings")
        slots = config["comparison"]
        profiles = config["evaluators"]
        if not isinstance(slots, dict) or set(slots) != {"A", "B"} or not isinstance(profiles, dict):
            raise ValueError("comparison must select exactly A and B")
        self.evaluators = {}
        resolved = {}
        for name, spec in profiles.items():
            if not isinstance(name, str) or not isinstance(spec, dict):
                raise ValueError("Evaluator profiles must be named mappings")
            if set(spec) - {"type", "label", "weights", "version"}:
                raise ValueError(f"Unknown options in evaluator {name}")
            kind = spec.get("type")
            if kind not in EVALUATOR_FACTORIES:
                raise ValueError(f"Unknown evaluator type: {kind}")
            current_version = IMPLEMENTATION_VERSIONS[kind]
            version = spec.get("version", current_version)
            if type(version) is not int or version not in range(1, current_version + 1):
                raise ValueError(f"Unsupported evaluator version for {name}")
            label = spec.get("label", name)
            if not isinstance(label, str) or not label:
                raise ValueError("Evaluator labels must be nonempty strings")
            evaluator, options = EVALUATOR_FACTORIES[kind]({**spec, "version": version}, restore)
            self.evaluators[name] = evaluator
            resolved[name] = {"type": kind, "label": label, "version": version, **options}
        if any(not isinstance(name, str) or name not in resolved for name in slots.values()):
            raise ValueError("A and B must select known evaluator profiles")
        self.slots = dict(slots)
        self.config = {"comparison": self.slots, "evaluators": resolved}
        digest = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()
        self.metadata = {"schemaVersion": 1, "configHash": digest, "config": self.config,
                         "evaluators": {slot: {"id": name, **resolved[name]} for slot, name in slots.items()},
                         "codeRevision": code_revision()}

    @classmethod
    def load(cls, path: Path | str = DEFAULT_CONFIG):
        with Path(path).open(encoding="utf-8") as source:
            return cls(yaml.safe_load(source))

    def score(self, state: GameState, params: GameParams) -> dict:
        scores = {}
        for player in (Player.Player1, Player.Player2):
            scores[player.value] = {}
            for slot, name in self.slots.items():
                value = self.evaluators[name].evaluate(state, player, params)
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(f"Evaluator {name} returned an invalid score")
                scores[player.value][slot] = value
        return {"scores": scores, "stats": team_stats(state)}
