# Human play: manual ticks or adjustable playback

From the repository root in PowerShell, run:

```powershell
.\gradlew.bat :app:runHumanGame
```

This opens a local match against **Better Random**. You are red (Player1), the
opponent is blue, and neutral planets are gray. No Python server is required.
Use a Java version compatible with Gradle 8.12 (the project compiles with Java 21).
On the development machine, the launcher can use:

```powershell
$env:JAVA_HOME = 'C:\Users\davec\.jdks\openjdk-23.0.2'
```

## Controls

1. Click one of your available red planets. It gains a yellow selection ring.
2. Enter the exact number of ships in the **Ships** field below the board.
   The field starts empty; positive decimal counts work. Only your typing changes
   the amount. Source changes, growth, passing, and fleet inspection preserve it;
   New Game clears it.
3. Click a different planet to launch. Friendly destinations are allowed.

Your launch and the opponent's action execute **together in exactly one tick**.
When paused, the board then waits for your next decision. A source with a fleet already in
flight cannot launch another fleet until that transporter becomes available.

The **Skip / Pass** icon in the playback bar advances one tick without a human
launch. It lets fleets travel and planets grow. Space also passes when the board
has keyboard focus; typing in the ship-count field does not activate shortcuts.
Press Enter in that field to return focus to the board. Escape (from the board or
ship-count field) or **Clear Selection** clears a source without advancing time.
Clicking the background also immediately deselects the planet, including on rapid
clicks or in the margins around a resized board. Your typed ship count is preserved.

Click any fleet, including an opponent's, to inspect its destination. The selected
fleet and destination planet gain cyan rings, with a line connecting them. Its
source, destination, and ship count appear below the board. Inspection clears
any pending source selection, never launches ships, and does not advance a tick.
The highlight follows the fleet during playback and clears when it arrives.
Click empty space, press Escape, or use **Clear Selection** to dismiss it; clicking
a planet returns to the normal launch controls. Fleets take click priority where
their visible arrows overlap a planet.

The match starts **paused**. Click the **Play** triangle in the playback bar to
advance automatically without a human launch; it becomes a **Pause** icon while
running. The **Tick speed** slider and readout set the target speed from 1 to 30
ticks per second, defaulting to **10 ticks/s**. Changing speed takes effect during
playback and does not start a paused game. Hover over an icon to see its action.
You can still submit launches or click Pass during playback; each executes one tick
immediately and resets the automatic timer so another tick is not due immediately.
Playback remains active after a launch or Pass until you pause it.

While paused, idle time, repainting, resizing, invalid input, and cancellation
advance **zero** ticks. Launch and Pass are disabled while the opponent is thinking,
but Pause stays available. An already-running tick finishes after you pause; no new
automatic tick starts. If the opponent takes longer than the selected interval, timer events
are skipped rather than queued or caught up. The GUI stays responsive.

Errors, game completion, and New Game stop playback. The final board freezes at
game end; **New Game** starts a fresh, paused match.

## Play against MCTS

Start the Python server in a separate terminal:

```powershell
$env:PYTHONPATH = 'app/src/main/python'
python -u -m examples.mcts_server --time-limit 0.2
```

Then launch the human window:

```powershell
.\gradlew.bat :app:runHumanGame --args="--opponent mcts --port 8765"
```

The viewer and server must use the same port (server option: `--port 8765`).
Connection or opponent errors leave the board unchanged; check the server and retry
the decision, or choose New Game. Human-mode remote operations time out after 30
seconds. New Game and closing the window release the old remote agent; the Python
server itself remains running until you press Ctrl+C in its terminal.

Human matches are fully observable, use 10 planets, and have a 2,000-tick limit.
Existing spectator runners keep their original automatic playback behavior.

Planet markers are drawn at 1.5 times their gameplay radius for easier viewing and
clicking. Selection rings and click targets use the same visual size; the game rules
and fleet arrival radii are unchanged. The shared default is
`DEFAULT_PLANET_RADIUS_SCALE` in `BoardViewport.kt`.
The board shows ship counts without planet ID (`#`) labels; selected source and
fleet details remain available in the panel below it.

Fleets must contain a positive, finite ship count; zero and negative fleets are
rejected by both forward models and fleet data validation. Positive fractional
fleets remain legal. Planet and fleet labels on the board show the floor of the
actual count, so a fleet containing `0.5` ships displays as `0`. The details panel
retains fractional counts, with amounts below its precision shown as `<0.0001`.
