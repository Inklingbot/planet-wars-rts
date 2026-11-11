"""Heuristic Planet Wars MCTS with explicit modern-feature extension points."""

from .config import MCTSConfig
from .engine import ActionStatistics, MCTS, SearchResult
from scoring.heuristics import BoardStrengthEvaluator, BoardWeights
from .tactical import DeterministicTacticalPolicy, TacticalActionGenerator

__all__ = ["MCTS", "MCTSConfig", "SearchResult", "ActionStatistics",
           "BoardStrengthEvaluator", "BoardWeights", "TacticalActionGenerator",
           "DeterministicTacticalPolicy"]
