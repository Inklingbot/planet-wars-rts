# Game replay logging

Both Python runners can write a complete JSON replay by passing a path as
`replay_log_path`. Logging is opt-in.

```python
from core.game_replay import load_replay, replay_game
from core.game_runner import GameRunner

runner = GameRunner(agent1, agent2, params, replay_log_path="replays/game-001.json")
runner.run_game()

replay = load_replay("replays/game-001.json")
states = list(replay_game(replay))  # Re-simulates actions and checks each snapshot.
```

`UnifiedGameRunner` accepts the same `replay_log_path` argument. With either
runner, the file contains the parameters, agent names, initial state, and one
entry per game tick. Each tick includes the actions, agent diagnostics, and
resulting full state. Stored snapshots support direct seeking with
`replay_states`; `replay_game` reconstructs the game by applying the recorded
actions and reports the first tick that diverges from its snapshot. If the same
runner writes more than one game, later files receive `-0002`, `-0003`, and so
on before the extension.

The greedy heuristic agent records its scoring terms, candidate moves, and
heuristic-selected move. MCTS records its chosen move, root action statistics,
mean search values by tree depth, and each root move's immediate heuristic
value. Agents that do not expose analysis still have their actions and game
states recorded.
