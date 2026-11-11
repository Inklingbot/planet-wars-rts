"""Compatibility imports; implementations live in ``scoring.heuristics``."""

from scoring.heuristics import BoardStrengthEvaluator, BoardWeights, default_mcts_evaluator

__all__ = ["BoardStrengthEvaluator", "BoardWeights", "default_mcts_evaluator"]
