package games.planetwars.runners

import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.agents.random.PureRandomAgent
import games.planetwars.core.*
import games.planetwars.scoring.MatchObserver

data class GameRunner(
    val agent1: PlanetWarsAgent,
    val agent2: PlanetWarsAgent,
    val gameParams: GameParams,
    val failedActionHandler: ((FailedActionEvent) -> Unit)? = null,
    val matchObserver: MatchObserver? = null,
) {
    var gameState: GameState = GameStateFactory(gameParams).createGame()
    var forwardModel: ForwardModel = ForwardModel(gameState.deepCopy(), gameParams, failedActionHandler)
    private var observationActive = false

    private fun observe(action: MatchObserver.() -> Unit) {
        matchObserver?.let { runCatching { it.action() }.onFailure { error ->
            System.err.println("Match observation failed: ${error.message}")
        } }
    }

    fun finishObservation(aborted: Boolean = !forwardModel.isTerminal()) {
        if (observationActive) {
            observationActive = false
            observe { ended(forwardModel.state.deepCopy(), aborted) }
        }
    }
    // call newGame() to reset the game state and agents in the constructor
    init {
        newGame()
    }

    fun runGame() : ForwardModel {
        // runs with a fresh copy of the game state each time
//        val forwardModel = ForwardModel(gameState.deepCopy(), gameParams)

        newGame()
        while (!forwardModel.isTerminal()) {
            val actions = mapOf(
                Player.Player1 to agent1.getAction(forwardModel.state.deepCopy()),
                Player.Player2 to agent2.getAction(forwardModel.state.deepCopy()),
            )
            forwardModel.step(actions)
            observe { advanced(forwardModel.state.deepCopy()) }
        }
        finishObservation(aborted = false)
        return forwardModel
    }

    fun newGame() {
        finishObservation(aborted = true)
        if (gameParams.newMapEachRun) {
            gameState = GameStateFactory(gameParams).createGame()
        }
        forwardModel = ForwardModel(gameState.deepCopy(), gameParams, failedActionHandler)
        val name1 = agent1.prepareToPlayAs(Player.Player1, gameParams)
        val name2 = agent2.prepareToPlayAs(Player.Player2, gameParams)
        observationActive = matchObserver != null
        observe { started(gameParams, name1, name2, forwardModel.state.deepCopy()) }
    }

    fun stepGame() : ForwardModel {
        if (forwardModel.isTerminal()) {
            finishObservation(aborted = false)
            return forwardModel
        }
        val actions = mapOf(
            Player.Player1 to agent1.getAction(forwardModel.state),
            Player.Player2 to agent2.getAction(forwardModel.state),
        )
        forwardModel.step(actions)
        observe { advanced(forwardModel.state.deepCopy()) }
        if (forwardModel.isTerminal()) finishObservation(aborted = false)
        return forwardModel
    }

    fun runGames(nGames: Int) : Map<Player, Int> {
        val scores = mutableMapOf(Player.Player1 to 0, Player.Player2 to 0, Player.Neutral to 0)
        for (i in 0 until nGames) {
            val finalModel = runGame()
            val winner = finalModel.getLeader()
            scores[winner] = scores[winner]!! + 1
        }
//        println(forwardModel.statusString())

        return scores
    }
}

fun main() {
    val gameParams = GameParams(numPlanets = 20)
//    val gameState = GameStateFactory(gameParams).createGame()
    val agent1 = PureRandomAgent()
    val agent2 = BetterRandomAgent()
    val gameRunner = GameRunner(agent1, agent2, gameParams)
    val finalModel = gameRunner.runGame()
    println("Game over!")
    println(finalModel.statusString())
    // time to run a bunch of games
    val nGames = 1000
    val t = System.currentTimeMillis()
    val results = gameRunner.runGames(nGames)
    val dt = System.currentTimeMillis() - t
    println(results)
    println("Time per game: ${dt.toDouble() / nGames} ms")
    // also print time per step
    val nSteps = ForwardModel.nUpdates
    println("Time per step: ${dt.toDouble() / nSteps} ms")

    println("Successful actions: ${ForwardModel.nActions}")
    println("Failed actions: ${ForwardModel.nFailedActions}")

}
