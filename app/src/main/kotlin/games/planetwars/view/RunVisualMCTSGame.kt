package games.planetwars.view

import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.core.GameParams
import games.planetwars.runners.GameRunner
import games.planetwars.scoring.ComparisonTelemetry
import xkg.jvm.AppLauncher
import java.awt.BorderLayout
import javax.swing.SwingUtilities
import javax.swing.WindowConstants

/** Run the Python MCTS server first: python -m examples.mcts_server */
fun main() {
    val params = GameParams(numPlanets = 10, maxTicks = 2000)
    val mcts = RemoteAgent("MCTSAgent", port = 8765)
    val random = BetterRandomAgent()
    val scorePanel = HeuristicScorePanel()
    val comparison = ComparisonTelemetry(onUpdate = scorePanel::refresh)
    val runner = GameRunner(mcts, random, params, matchObserver = comparison)
    val launcher = AppLauncher(
        preferredWidth = params.width,
        preferredHeight = params.height,
        app = GameView(params = params, gameState = runner.forwardModel.state, gameRunner = runner),
        title = "MCTS (red) vs Better Random (blue) | Space: pause | S/F: speed",
        frameRate = 30.0,
    )
    SwingUtilities.invokeAndWait {
        launcher.frame.defaultCloseOperation = WindowConstants.DISPOSE_ON_CLOSE
        launcher.frame.contentPane.add(scorePanel, BorderLayout.SOUTH)
        launcher.frame.pack()
    }
    try {
        launcher.launch()
    } finally {
        runner.finishObservation()
        comparison.close()
        mcts.close()
    }
}
