# Replay analysis

This tool samples saved games, runs one MCTS search at a chosen tree-depth cap
for each player position, and writes five files. The replay JSON files remain
the source of truth for full game reconstruction.

## Run from Windows Command Prompt

```cmd
set PYTHONPATH=app\src\main\python
python -m replay_analysis --replays "replays\mcts-vs-careful-random\*.json" --output "results\replay-analysis\mcts-vs-careful-random" --heuristic mcts_board_strength --stride 1 --depth 8 --iterations 32 --calibration-bot "Heuristic UCT MCTS in Python"
```

`--output` is a base name. Each run creates a new sibling folder such as
`results\replay-analysis\mcts-vs-careful-random-2026-11-23_19-42-08Z`.
The timestamp is UTC. If two runs start in the same second, a numeric suffix
keeps their folders distinct. Existing tournament folders are never overwritten.

`--replays` accepts files, directories, or glob patterns. `--heuristic` accepts
a built-in evaluator type or a profile ID from `--heuristic-config file.yaml`.
`--stride 1` samples every replay tick; the default is 20. Use
`--max-positions-per-game N` to cap sampled ticks in each game. Each sampled
tick produces two rows, one per player. Final states are excluded because they
have no move to search.

## Files

| File | One row or record | Contents |
|---|---|---|
| `positions.csv` | Sampled tick and player | Game/position ID, bot, outcome, static score and features, highest root search value, played move and value, best move and value, and estimated regret. |
| `root_actions.csv` | Expanded root action for a position | Action, visit count, mean search value, immediate heuristic value and weighted heuristic terms, and best/played flags. |
| `reliability.csv` | Probability bin for static or search score | Held-out mean logistic prediction and observed result, bin count, and game-balanced weight. |
| `reliability.png` | Graph for the two logistic series | Static and search reliability compared with the perfect-calibration diagonal. |
| `tournament.json` | Whole analysis run | Search and sampling settings, heuristic identity, game parameters, replay paths, bot names and results, and calibration coefficients and metrics. |

Join the two CSVs on `position_id`. The `features` and `heuristic_terms`
columns contain JSON objects. `features` describes the current board;
`heuristic_terms` describes the immediate board after a candidate root action
and the search's modeled opponent response. The `best_action` is the expanded
root action with the highest mean search value. Regret is
`max(0, best_action_value - played_action_value)`; the played action is always
included among root candidates.
In `positions.csv`, `played_action` and `played_action_value` appear before
`best_action` and `best_action_value`. `best_action` reads `unchanged` when it
is the same move as `played_action`; its numeric value remains in
`best_action_value`.

Reliability fits `sigmoid(intercept + slope * (2 * score - 1))` separately for
static and search scores. It splits by whole game, gives each game equal total
weight, and reports predictions on held-out games. With multiple bots, specify
`--calibration-bot` so the labels reflect one policy's continuation. Use
`--calibration-bot all` only when intentionally pooling policies. All sampled
positions still appear in `positions.csv` and `root_actions.csv`; the filter
affects reliability only. With only one game, the
result is marked `in_sample` in `tournament.json`. The file contains logistic
calibration only. A tree-depth cap is measured in game ticks; MCTS can stop a
path before reaching it. Search values and regret are estimates under the
chosen evaluator and modeled opponent, not solved-game values.

The graph needs Matplotlib (`pip install -r app/src/main/python/scoring/requirements-plot.txt`).
To redraw it from an existing `reliability.csv` without rerunning MCTS:

```cmd
python -m replay_analysis.plot --reliability "results\replay-analysis\mcts-vs-careful-random\reliability.csv" --output "results\replay-analysis\mcts-vs-careful-random\reliability.png" --depth 8 --bot "Heuristic UCT MCTS in Python"
```

The CLI prints the exact folder it created when the run finishes. The original
base folder, if present, remains available for earlier results.
