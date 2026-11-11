package games.planetwars.runners

import games.planetwars.agents.RemoteAgent
import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.agents.random.BetterRandomAgent
import games.planetwars.core.*
import kotlinx.serialization.json.*
import java.io.File
import java.time.Instant
import java.util.Locale

/** Paired-map evaluation against Better Random, or a second remote MCTS variant. */
fun main(args: Array<String>) {
    val games = args.getOrNull(0)?.toInt() ?: 100
    val port = args.getOrNull(1)?.toInt() ?: 18765
    val seed = args.getOrNull(2)?.toLong() ?: 42L
    val opponentPort = args.getOrNull(4)?.toInt()
    require(opponentPort != port) { "The two variants require separate servers" }
    require(games > 0 && games % 2 == 0) { "Use a positive, even number of games" }
    val output = File(args.getOrNull(3) ?: "log_data/mcts-evaluations/${Instant.now().toString().replace(':', '-')}")
    require(!output.exists()) { "Output directory already exists: $output" }
    check(output.mkdirs()) { "Cannot create $output" }
    val json = Json { encodeDefaults = true; prettyPrint = true }
    val params = GameParams(numPlanets = 10, maxTicks = 2000)
    val revision = runCatching {
        ProcessBuilder("git", "rev-parse", "HEAD").start().inputStream.bufferedReader().readText().trim()
    }.getOrNull()
    File(output, "metadata.json").writeText(buildJsonObject {
        put("startedAt", Instant.now().toString()); put("gamesRequested", games)
        put("agent", "Reference MCTS")
        put("opponent", if (opponentPort == null) "Kotlin BetterRandomAgent" else "Remote variant on port $opponentPort")
        put("opponentPort", opponentPort?.let(::JsonPrimitive) ?: JsonNull)
        put("port", port); put("mapSeedStart", seed)
        put("pairedMaps", true)
        put("opponentRandomness", if (opponentPort == null) "Unseeded Kotlin Random.Default" else "See opponent server search configuration")
        put("params", json.encodeToJsonElement(GameParams.serializer(), params))
        put("codeRevision", revision?.let(::JsonPrimitive) ?: JsonNull)
        put("searchConfigNote", "See the dedicated MCTS server startup log for its search budget and heuristic weights")
        put("winnerRule", "ForwardModel.getLeader(): stationed ships at termination")
    }.toString())
    var wins = 0
    var losses = 0
    var draws = 0
    val started = System.nanoTime()
    val records = File(output, "games.jsonl")
    println("Headless reference MCTS vs ${opponentPort?.let { "remote port $it" } ?: "Better Random"}: $games games, ${games / 2} paired maps; output=${output.absolutePath}")
    try {
        for (index in 0 until games) {
            val mapSeed = seed + index / 2
            val mctsPlayer = if (index % 2 == 0) Player.Player1 else Player.Player2
            val opponentPlayer = mctsPlayer.opponent()
            val initial = GameStateFactory(params, mapSeed).createGame()
            var failedMcts = 0
            var failedOpponent = 0
            val model = ForwardModel(initial, params) { event ->
                if (event.player == mctsPlayer) failedMcts++ else failedOpponent++
            }
            val gameStarted = System.nanoTime()
            var actionNanos = 0L
            var decisions = 0
            RemoteAgent("MCTSAgent", port, requestTimeoutMillis = 30_000, strictResponses = true).use { mcts ->
                val opponent: PlanetWarsAgent = opponentPort?.let {
                    RemoteAgent("MCTSAgent", it, requestTimeoutMillis = 30_000, strictResponses = true)
                } ?: BetterRandomAgent()
                try {
                    val opponentName = opponent.prepareToPlayAs(opponentPlayer, params)
                    val mctsName = mcts.prepareToPlayAs(mctsPlayer, params, opponentName)
                    while (!model.isTerminal()) {
                        val beforeAction = System.nanoTime()
                        val mctsAction = mcts.getAction(model.state.deepCopy())
                        actionNanos += System.nanoTime() - beforeAction
                        decisions++
                        val opponentAction = opponent.getAction(model.state.deepCopy())
                        model.step(mapOf(mctsPlayer to mctsAction, opponentPlayer to opponentAction))
                    }
                    val winner = model.getLeader()
                    val result = when (winner) {
                        mctsPlayer -> { wins++; "win" }
                        Player.Neutral -> { draws++; "draw" }
                        else -> { losses++; "loss" }
                    }
                    records.appendText(buildJsonObject {
                        put("game", index + 1); put("mapSeed", mapSeed); put("mctsPlayer", mctsPlayer.name)
                        put("agentName", mctsName); put("opponentName", opponentName)
                        put("result", result); put("winner", winner.name)
                        put("ticks", model.state.gameTick)
                        put("elapsedSeconds", (System.nanoTime() - gameStarted) / 1e9)
                        put("mctsDecisions", decisions)
                        put("mctsMeanDecisionMs", if (decisions > 0) actionNanos / 1e6 / decisions else 0.0)
                        put("mctsFailedActions", failedMcts); put("opponentFailedActions", failedOpponent)
                        put("mctsStationedShips", model.getShips(mctsPlayer))
                        put("opponentStationedShips", model.getShips(opponentPlayer))
                    }.toString() + "\n")
                    mcts.processGameOver(model.state.deepCopy())
                    opponent.processGameOver(model.state.deepCopy())
                    println("Game ${index + 1}/$games: MCTS=$result as ${mctsPlayer.name}, seed=$mapSeed, ticks=${model.state.gameTick}; W/L/D=$wins/$losses/$draws")
                } finally {
                    (opponent as? AutoCloseable)?.close()
                }
            }
        }
        val summary = buildJsonObject {
            put("games", games); put("wins", wins); put("losses", losses); put("draws", draws)
            put("winRate", wins.toDouble() / games)
            put("elapsedSeconds", (System.nanoTime() - started) / 1e9)
        }
        File(output, "summary.json").writeText(json.encodeToString(JsonObject.serializer(), summary))
        println("Completed: $wins wins, $losses losses, $draws draws; win rate=${String.format(Locale.ROOT, "%.1f", 100.0 * wins / games)}%")
    } catch (error: Exception) {
        File(output, "error.txt").writeText(error.stackTraceToString())
        throw error
    }
}
