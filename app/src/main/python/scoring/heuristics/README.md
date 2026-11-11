# Shared board heuristics

Import evaluators from `scoring.heuristics` for agents, MCTS, or standalone scoring:

```python
from scoring.heuristics import (
    BoardStrengthEvaluator, BoardWeights,
    ShipAdvantageEvaluator,
    ThreeFactorAdvantageEvaluator, ThreeFactorWeights,
)

evaluator = ThreeFactorAdvantageEvaluator(
    ThreeFactorWeights(ships=0.3, planets=0.4, growth=0.3)
)
value = evaluator.evaluate(state, player, params)
```

- `board_strength.py`: original five-term MCTS heuristic, `BoardWeights`, and the
  `default_mcts_evaluator()` factory used by both MCTS and its display profile.
- `ship_advantage.py`: stationed and in-flight ship share.
- `three_factor.py`: weighted ship share, owned planets / all planets, and growth
  share. Direct construction defaults to equal weights; configured profiles supply
  the selected weights.
- `stats.py`: full-precision per-team ship and planet totals.

These implementations depend on game-domain code in `core`, including
`core/fleet_projection.py` and `core/terminal.py`. They do not import the search
engine or scoring service. Current evaluators independently score terminal
win/draw/loss as 1/0.5/0; MCTS also enforces these outcomes before backpropagation.

Profile registration, YAML loading, metadata, and historical implementation-version
handling remain in `scoring/evaluators.py`. See [scoring configuration](../README.md).
Algorithms, weights, profile versions, and configuration hashes are unchanged by
this move. Old imports from `search.mcts.evaluation`, `search.mcts.projection`,
and evaluator names in `scoring.evaluators` continue to work.
