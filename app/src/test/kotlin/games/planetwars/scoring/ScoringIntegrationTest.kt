package games.planetwars.scoring

import games.planetwars.agents.Action
import games.planetwars.agents.PlanetWarsPlayer
import games.planetwars.agents.RemoteAgent
import games.planetwars.core.*
import games.planetwars.runners.GameRunner
import games.planetwars.view.HumanMatchSession
import kotlinx.serialization.json.*
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.util.concurrent.TimeUnit
import kotlin.test.*

class ScoringIntegrationTest {
    @TempDir lateinit var directory: File
    private class Waiting : PlanetWarsPlayer() {
        override fun getAgentType() = "Waiting"
        override fun getAction(gameState: GameState) = Action.DO_NOTHING
    }
    private fun awaitScore(telemetry: ComparisonTelemetry, tick: Int) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15)
        while (telemetry.display.scoredTick != tick && System.nanoTime() < deadline) Thread.sleep(20)
        assertEquals(tick, telemetry.display.scoredTick, telemetry.display.status)
    }
    private fun telemetry(): ComparisonTelemetry {
        val url = System.getenv("HEURISTIC_SCORER_TEST_URL")
        assumeTrue(url != null, "Set HEURISTIC_SCORER_TEST_URL for live Python scoring tests")
        return ComparisonTelemetry(connectionFactory = { WebSocketScoreConnection(url!!) },
            logDirectory = directory, dispatch = { it() })
    }

    @Test
    fun `human match receives real Python scores and leaves a complete history`() {
        val telemetry = telemetry()
        val params = GameParams(numPlanets = 2, initialNeutralRatio = 0.0, maxTicks = 1)
        val session = HumanMatchSession(params, { Waiting() }, dispatch = { it() }, observer = telemetry)
        try {
            val initial = session.newGame().get(5, TimeUnit.SECONDS)
            awaitScore(telemetry, 0)
            val totals = matchStats(initial.state!!)
            val own = totals["Player1"]!!.jsonObject["totalShips"]!!.jsonPrimitive.double
            val enemy = totals["Player2"]!!.jsonObject["totalShips"]!!.jsonPrimitive.double
            assertEquals(own / (own + enemy), telemetry.display.scores!!["Player1"]!!.jsonObject["A"]!!.jsonPrimitive.double)
            session.pass().get(5, TimeUnit.SECONDS)
            session.pass().get(5, TimeUnit.SECONDS)
            awaitScore(telemetry, 2)
            telemetry.close() // Flushes scores; terminal event was already queued.
            val records = directory.listFiles()!!.single().readLines().map { Json.parseToJsonElement(it).jsonObject }
            assertEquals(3, records.count { it["event"]!!.jsonPrimitive.content == "tick" })
            assertEquals(3, records.count { it["event"]!!.jsonPrimitive.content == "scores" })
            assertTrue(records.any { it["event"]!!.jsonPrimitive.content == "game_end" && !it["aborted"]!!.jsonPrimitive.boolean })
        } finally { session.close(); telemetry.close() }
    }

    @Test
    fun `MCTS spectator runner uses independent real agent and scoring connections`() {
        val port = System.getenv("HUMAN_MCTS_TEST_PORT")?.toIntOrNull()
        assumeTrue(port != null, "Set HUMAN_MCTS_TEST_PORT for the MCTS spectator smoke test")
        val telemetry = telemetry()
        val agent = RemoteAgent("MCTSAgent", port!!, requestTimeoutMillis = 30_000, strictResponses = true)
        try {
            val runner = GameRunner(agent, Waiting(),
                GameParams(numPlanets = 2, initialNeutralRatio = 0.0, maxTicks = 1), matchObserver = telemetry)
            runner.stepGame()
            runner.stepGame()
            awaitScore(telemetry, 2)
            assertEquals(2, telemetry.display.boardTick)
            assertEquals("three_factor_advantage", telemetry.display.metadata!!["evaluators"]!!.jsonObject["B"]!!.jsonObject["id"]!!.jsonPrimitive.content)
        } finally { telemetry.close(); agent.close() }
    }
}
