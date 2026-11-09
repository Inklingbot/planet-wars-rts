# Live heuristic comparison

The human and MCTS spectator GUIs show two scores per team using a separate Python
service. They score real board states, not search rollouts. Comparison never selects
agent moves. Scores are in [0, 1], higher is stronger, and are not win probabilities.

## Start the service and viewers

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'app/src/main/python'
python -m scoring.server --config heuristic_comparison.yaml --port 8766
```

In another terminal:

```powershell
.\gradlew.bat :app:runHumanGame
```

For human-versus-MCTS or the MCTS spectator, also start the existing agent server:

```powershell
$env:PYTHONPATH = 'app/src/main/python'
python -m examples.mcts_server --port 8765
```

```powershell
.\gradlew.bat :app:runVisualMCTS
# Or:
.\gradlew.bat :app:runHumanGame --args="--opponent mcts --port 8765"
```

Close viewers and use Ctrl+C in each Python terminal to stop services. Agent RPC
uses port 8765; scoring has its own client and service on 8766.

## Select heuristics

Edit `heuristic_comparison.yaml`: `comparison.A` and `comparison.B` select profile
IDs under `evaluators`. Both slots may select the same profile. Restart the service
and start New Game after changing profiles.

- `ship_advantage`: own stationed + in-flight ships divided by both players' total;
  returns 0.5 when both totals are zero. It remains a material score at game end.
- `mcts_board_strength`: the same factory/default weights used by MCTS, including
  its existing terminal win/draw/loss scoring. This profile does not accept weights.
- `board_strength`: the same formula with optional custom weights, for example:

```yaml
  captures_first:
    type: board_strength
    label: Captures First
    weights:
      planets: 1
      growth: 1
      ships: 1
      expected_captures: 3
      planets_over_10: 1
```

Add that mapping under `evaluators`, then select `captures_first` in A or B.
Unknown IDs/types and invalid weights fail at startup. Comparison selection does
not alter the MCTS configuration. If you explicitly inject a custom evaluator into
an agent, configure a matching display profile too. Red and blue are evaluated
independently; board-strength scores need not sum to one.

The footer identifies the scoring tick and board tick, so delayed scores cannot
masquerade as current scores. Scoring continues catching up while gameplay is paused.

## Histories

Both visual tasks run from the repository root and write one unique JSONL file per
game under `log_data/heuristics/`. Hover over the panel footer for the path.
Tournament runners do not install this observer. Optional GUI environment settings:

```powershell
$env:HEURISTIC_SCORER_URL = 'ws://127.0.0.1:8766'
$env:HEURISTIC_LOG_DIR = 'C:\path\to\histories'
$env:HEURISTIC_LOGGING = 'false'  # Default: true; display still works.
```

Events are joined by `gameId` and `tick`:

- `game_start`: schema, players/sides, actual parameters, code revision.
- `tick`: initial board and every committed tick; full state and each team's
  `planetCount`, `stationedShips`, `shipsInFlight`, and `totalShips`.
- `metadata`: evaluator IDs, resolved weights, implementation versions, config
  hash, and scoring code revision.
- `scores`: A/B values for both players and their configuration hash.
- `game_end`: final tick, winner, and whether restart/closure aborted the game.

Stats retain fractional precision; fleets belong to their owner even after their
source changes hands. Repaints, invalid orders, and MCTS simulations are not ticks.
Snapshots are persisted before scoring, and pending requests refer to file offsets
instead of keeping all old boards in memory. Reconnection backfills them in order.
Old-game responses are logged but cannot overwrite the new game's panel. Changing
service configuration cannot mix heuristic settings within one game.

Score records may follow `game_end`, because scoring is asynchronous. Closing a
viewer flushes queued history writes; unscored boards remain recoverable offline.
Logging/service errors are visible in the panel without stopping gameplay.

## Export and plot

```powershell
$env:PYTHONPATH = 'app/src/main/python'
python -m scoring.export log_data/heuristics/GAME.jsonl --csv results/history.csv --plot results/history.png
```

Missing scores stay blank in CSV and form gaps in plots. To explicitly recover
missing scores from saved boards and the recorded evaluator configuration:

```powershell
python -m scoring.export log_data/heuristics/GAME.jsonl --rescore-missing --plot results/history.png
```

If the service never connected, supply `--config heuristic_comparison.yaml` with
`--rescore-missing`. Rescoring uses recorded weights when available, rejects
unsupported implementation versions, and never changes the original history file.
Preserve the recorded code revision when studying older evaluator implementations.
Matplotlib is optional for the service/game and needed only for plotting:

```powershell
python -m pip install -r app/src/main/python/scoring/requirements-plot.txt
```
