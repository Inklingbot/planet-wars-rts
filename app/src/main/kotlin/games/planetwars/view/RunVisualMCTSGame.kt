package games.planetwars.view

import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.core.GameParams
import games.planetwars.runners.GameRunner
import xkg.jvm.AppLauncher

/** Run the Python MCTS server first: python -m examples.mcts_server */
fun main() {
    val params = GameParams(numPlanets = 10, maxTicks = 2000)
    val mcts = RemoteAgent("MCTSAgent", port = 8765)
    val random = BetterRandomAgent()
    val runner = GameRunner(mcts, random, params)
    AppLauncher(
        preferredWidth = params.width,
        preferredHeight = params.height,
        app = GameView(params = params, gameState = runner.forwardModel.state, gameRunner = runner),
        title = "MCTS (red) vs Better Random (blue) | Space: pause | S/F: speed",
        frameRate = 30.0,
    ).launch()
}
