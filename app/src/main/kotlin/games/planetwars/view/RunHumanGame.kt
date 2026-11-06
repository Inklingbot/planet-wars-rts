package games.planetwars.view

import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.core.GameParams
import javax.swing.SwingUtilities
import javax.swing.UIManager

fun main(args: Array<String>) {
    var opponent = "better-random"
    var port = 8765
    var index = 0
    while (index < args.size) {
        when (val option = args[index++]) {
            "--opponent" -> opponent = args.getOrNull(index++) ?: error("Missing opponent")
            "--port" -> port = args.getOrNull(index++)?.toIntOrNull() ?: error("Missing/invalid port")
            "--help" -> {
                println("runHumanGame --args=\"--opponent better-random|mcts --port 8765\"")
                return
            }
            else -> error("Unknown option: $option")
        }
    }
    require(opponent in setOf("better-random", "mcts")) { "Opponent must be better-random or mcts" }
    require(port in 1..65535) { "Port must be between 1 and 65535" }
    val name = if (opponent == "mcts") "MCTS" else "Better Random"
    val opponentFactory: () -> PlanetWarsAgent = if (opponent == "mcts") {
        { RemoteAgent("MCTSAgent", port, requestTimeoutMillis = 30_000, strictResponses = true) }
    } else {
        { BetterRandomAgent() }
    }
    SwingUtilities.invokeLater {
        runCatching { UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName()) }
        HumanMatchWindow(GameParams(numPlanets = 10, maxTicks = 2000), name, opponentFactory).show()
    }
}
