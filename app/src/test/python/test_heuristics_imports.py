"""Guard shared-package independence and compatibility in fresh interpreters."""

from pathlib import Path
import subprocess
import sys
import unittest


PYTHON_ROOT = Path(__file__).resolve().parents[2] / "main" / "python"


class TestHeuristicImports(unittest.TestCase):
    def run_fresh(self, code):
        result = subprocess.run([sys.executable, "-c", code], cwd=PYTHON_ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_heuristics_do_not_load_search_or_scoring_service(self):
        self.run_fresh("""
import sys
from scoring.heuristics import (BoardStrengthEvaluator, BoardWeights, ShipAdvantageEvaluator,
                        ThreeFactorAdvantageEvaluator, ThreeFactorWeights, team_stats)
assert not any(name.split('.')[0] == 'search' for name in sys.modules)
assert not any(name in sys.modules for name in ('scoring.evaluators', 'scoring.server', 'scoring.export'))
""")

    def test_old_and_new_imports_remain_compatible_in_either_order(self):
        for first in ("scoring.heuristics", "search.mcts.evaluation", "scoring.evaluators"):
            with self.subTest(first=first):
                self.run_fresh(f"""
import importlib
importlib.import_module({first!r})
import scoring.heuristics as heuristics
import scoring.evaluators as scoring
import search.mcts as mcts
import search.mcts.evaluation as old_evaluation
import search.mcts.projection as old_projection
import core.fleet_projection as projection
assert old_evaluation.BoardStrengthEvaluator is heuristics.BoardStrengthEvaluator
assert old_evaluation.BoardWeights is heuristics.BoardWeights
assert old_evaluation.default_mcts_evaluator is heuristics.default_mcts_evaluator
assert mcts.BoardStrengthEvaluator is heuristics.BoardStrengthEvaluator
assert scoring.ShipAdvantageEvaluator is heuristics.ShipAdvantageEvaluator
assert scoring.ThreeFactorAdvantageEvaluator is heuristics.ThreeFactorAdvantageEvaluator
assert scoring.ThreeFactorWeights is heuristics.ThreeFactorWeights
assert scoring.team_stats is heuristics.team_stats
assert old_projection.project_board is projection.project_board
assert old_projection.Arrival is projection.Arrival
""")
