# Planet Wars heuristic MCTS

This package implements UCT with standard expansion (one untried action per
iteration), random tactical rollouts for the searching player, and a deterministic
tactical opponent. Both actions are chosen from the same pre-update state and
applied together. Each search starts a new tree. No neural dependency is required.

Heuristic implementations live in [scoring/heuristics](../../scoring/heuristics/README.md).
Fleet projections are shared game-domain code in `core/fleet_projection.py`.

```python
from agents.mcts_agent import MCTSAgent
from search.mcts import MCTSConfig, TacticalActionGenerator
from scoring.heuristics import BoardStrengthEvaluator, BoardWeights

agent = MCTSAgent(
    config=MCTSConfig(
        iterations=128,
        tree_depth=20,
        rollout_depth=80,
        exploration_constant=1.414,
        seed=42,
        # time_limit_seconds=0.1,  # Optional soft deadline per decision.
    ),
    action_generator=TacticalActionGenerator(safety_margin=1.0),
    evaluator=BoardStrengthEvaluator(BoardWeights(
        planets=1.0, growth=1.0, ships=1.0, expected_captures=1.0,
        planets_over_10=1.0,
    )),
)
```

Use `prepare_to_play_as(player, params)` followed by `get_action(state)`, as with
other fully observable agents. `as_unified(agent)` supplies the existing
observation adapter; hidden-information reconstruction is not information-set MCTS.
The engine can also be called directly via `MCTS.search(state, player, params)`.
Custom action generators, evaluators, and **deterministic** opponent policies can
implement the interfaces in `policies.py`. Empty candidate sets fall back to wait.

## Search budgets and diagnostics

`tree_depth` is the maximum ticks from the root through tree edges.
`rollout_depth` is the additional ticks after a selected leaf. A simulation advances
at most their sum and stops early at a terminal state. Zero rollout depth evaluates
tree leaves directly. Iterations must be positive, tree depth at least one, and the
exploration constant finite and nonnegative. Zero exploration uses mean value
after initial expansion. The root action with most visits wins, with mean value
breaking visit ties.

An optional time limit is checked between iterations: it is a soft deadline and
one iteration can exceed it. If no iteration completes, return do nothing.
`agent.last_result` exposes per-action visits/mean values, completed iterations,
elapsed time, deepest tree tick, and deepest total simulated tick. Seeds reproduce
iteration-limited searches; wall-clock limits can change completed iteration counts.
Search randomness resets at `prepare_to_play_as`. Simulation does not mutate input
states or add to the forward model's live-game statistics.

Before backpropagation, the engine assigns terminal wins/draws/losses values of
1/0.5/0 from the searching player's perspective. Terminal states bypass the
configured heuristic, including custom evaluators. The tactical opponent applies
the same rule to its one-step candidates. Built-in heuristics independently guard
terminal states when used outside search; their fallback does not replace the
engine's check. These outcomes follow the existing forward model's termination
and stationed-ship winner rules.

## Fleet projection and tactical actions

Project every reachable fleet already in flight, up to the game tick limit.
Use its current position and velocity to find the first discrete arrival check
inside the destination radius. Fleets that overshoot or never arrive are excluded.
Group all arrivals on the same tick, credit owned-planet growth before combat,
and apply the forward model's neutral/owned combat rules. After a capture, later
growth accrues to the new defender. Exactly zero defenders retains the owner.

Final projected ownership is measured after the last incoming arrival; a temporary
capture followed by a recapture is not a final loss. No future launches are assumed.

The tactical generator includes wait, captures of enemy/neutral planets, and
reinforcement of friendly planets projected to be lost. It estimates the smallest
launch that leaves the target friendly after **all** known arrivals, then adds a
configurable ship margin (capped by available ships). It skips already-secured
targets, busy sources, unreachable targets, and attacks a source cannot afford.
There is no general redistribution. Reinforcement arriving after a loss can act
as a recapture. The heuristic opponent scores these candidates by one-tick board
strength, with stable candidate ordering breaking ties.

## Board strength

All values use the searching player's perspective; there is no alternating sign.
Five features are in [-1, 1], with equal configurable weights by default:

| Feature | Normalization |
|---|---|
| Planets | (own count - enemy count) / all planet count |
| Growth | (own total growth - enemy total growth) / their sum |
| Ships | (own ships - enemy ships) / their sum; includes fleets by fleet owner |
| Expected captures | (own expected gains - own expected losses) / all planet count |
| Planets over 10 ships | Own planets with strictly more than 10 stationed ships / all planet count |

Zero denominators yield zero. Gains include neutral planets. The weighted average
is mapped to [0, 1]. There is no separate weakness feature. Terminal states instead
use 1/0.5/0 for win/draw/loss under the existing runner's `get_leader()` rule, which
compares stationed ships and excludes fleets. Feature weights must be nonnegative
and at least one must be positive.

`planets_over_10` rewards each qualifying owned planet equally; exactly 10 ships
does not qualify, and ships in flight do not count toward that planet's garrison.
Its feature lies in [0, 1]. Set its weight to 0 to disable this reward.

## Modern options reserved for later

These configurations raise `NotImplementedError` immediately:

- `selection="puct"` (`c_puct` is reserved independently of the UCT constant).
- `expansion="progressive_widening"`.
- `evaluation="network"` or `"hybrid"`.
- `priors="heuristic"` or `"network"`.
- `inference_batch_size > 1`, `reuse_tree=True`, `root_noise=True`.
- `temperature > 0`, `inference_cache=True`.

`modern.py` also contains explicit PUCT, progressive widening, PyTorch policy/value,
and batched inference placeholders. `PolicyValueModel` specifies candidate priors
and a value prediction. Future neural implementations will use PyTorch; no model,
training, GPU batching, or self-play training pipeline is implemented yet. The
current tree is deterministic; stochastic opponent policies need separate outcome
branches before they can be supported correctly.

## Run

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'app/src/main/python'
python -m unittest discover -s app/src/test/python -p test_mcts.py -v
python -m examples.mcts_battle --benchmark-only
python -m examples.mcts_battle --games 2 --max-ticks 200 --opponent greedy
```

The example uses a smaller search budget than the engine defaults for quicker
experimentation. Pure Python simulation and tactical sizing can dominate runtime;
benchmark the intended map size and budget before using a strict decision deadline.

## Headed match against Better Random

Start the Python server in one terminal, then the existing Kotlin viewer in another:

```powershell
$env:PYTHONPATH = 'app/src/main/python'
python -u -m examples.mcts_server --time-limit 0.05
```

```powershell
.\gradlew.bat :app:runVisualMCTS
```

MCTS is red (Player1); Kotlin's `BetterRandomAgent` is blue (Player2). The viewer
uses 10 planets and a 2,000-tick limit and automatically starts a new game after
each result. Space pauses/resumes; S slows playback; F speeds it up. The server
prints search timing, completed iterations, and selected actions every 25 ticks.
Its defaults use 20 rollout ticks and a 50 ms soft deadline for interactive viewing;
change `--iterations`, `--tree-depth`, `--rollout-depth`, or `--time-limit` on the
server command to adjust the search budget. A single iteration may exceed the
deadline. The opponent modeled inside search remains the deterministic tactical
policy; the actual match opponent is Better Random.

## Play against the agent yourself

See [Human play](../../../kotlin/games/planetwars/view/HUMAN_PLAY.md) for the
tick-by-tick human GUI. Launch it against MCTS with
`.\gradlew.bat :app:runHumanGame --args="--opponent mcts --port 8765"` after
starting the Python server. Every human launch or Pass advances exactly one tick.

Both this spectator and the human GUI support a separate display-only scoring
service. See [Heuristic comparison](../../scoring/README.md) for the two-evaluator
configuration, per-game JSONL histories, and CSV/plot export.

## Headless evaluation against Better Random

Start a dedicated server with the viewer's current search budget:

```powershell
$env:PYTHONPATH = 'app/src/main/python'
python -m examples.mcts_server --port 18765 --iterations 128 --tree-depth 20 --rollout-depth 20 --time-limit 0.05 --seed 42
```

In another terminal, run 100 games (50 maps, each played on both sides):

```powershell
.\gradlew.bat :app:runMctsEvaluation --args="100 18765 42"
```

Arguments are game count (positive and even), server port, first map seed, and an
optional new output directory. Uses 10 planets and the viewer's 2,000-tick limit.
`games.jsonl`, `metadata.json`, and `summary.json` are saved under
`log_data/mcts-evaluations/`. RPC failures stop the run and produce `error.txt`;
they are not silently counted as losses. The 30-second RPC timeout allows a full
search iteration to overrun the soft deadline. Better Random uses its existing
unseeded Kotlin random generator, so map seeds alone do not reproduce the games.
The winner follows the existing forward model's stationed-ship rule. Display-only
heuristic comparison settings do not affect this agent's evaluation.

To compare search heuristics directly, start a second server with the three-factor
profile injected into both its leaf evaluation and tactical opponent policy:

```powershell
python -m examples.mcts_server --port 18766 --evaluator three_factor_advantage
```

Keep the reference/default server on 18765 and run a 10-game paired pilot. The
fifth argument is the opponent server port; results are from the first port's view:

```powershell
.\gradlew.bat :app:runMctsEvaluation --args="10 18765 42 log_data/mcts-evaluations/heuristic-pilot 18766"
```

Both servers default to the same 128-iteration cap, 20 tree ticks, 20 rollout ticks,
50 ms soft deadline, and seed 42. `--evaluator` selects a profile from the root
`heuristic_comparison.yaml`; `--evaluator-config` can select another profile file.
Each server prints its resolved weights at startup. Without `--evaluator`, the
server continues to use the original MCTS heuristic regardless of display config.
