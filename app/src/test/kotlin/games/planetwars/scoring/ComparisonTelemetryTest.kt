package games.planetwars.scoring

import games.planetwars.core.*
import games.planetwars.view.HeuristicScorePanel
import kotlinx.serialization.json.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import util.Vec2d
import java.io.File
import java.util.Collections
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import javax.swing.SwingUtilities
import kotlin.test.*

class ComparisonTelemetryTest {
    @TempDir lateinit var directory: File
    private fun board(tick: Int = 0) = GameState(listOf(
        Planet(Player.Player1, 20.25, Vec2d(100.0, 100.0), .1, 10.0, id = 0),
        Planet(Player.Player2, 10.0, Vec2d(300.0, 100.0), .1, 10.0,
            Transporter(Vec2d(200.0, 100.0), Vec2d(3.0, 0.0), Player.Player1, 1, 0, 5.5), 1),
    ), tick)

    private fun await(condition: () -> Boolean) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(8)
        while (!condition() && System.nanoTime() < deadline) Thread.sleep(10)
        assertTrue(condition(), "Timed out waiting for scoring/history")
    }

    private class FakeConnection(
        private val hash: AtomicReference<String> = AtomicReference("config-1"),
        private val beforeScore: () -> Unit = {},
    ) : ScoreConnection {
        override fun exchange(request: JsonObject): JsonObject {
            if (request["type"]!!.jsonPrimitive.content == "describe") return buildJsonObject {
                put("status", "ok")
                put("metadata", buildJsonObject {
                    put("configHash", hash.get())
                    put("evaluators", buildJsonObject {
                        for (slot in listOf("A", "B")) put(slot, buildJsonObject { put("label", "Heuristic $slot") })
                    })
                })
            }
            beforeScore()
            check(request["configHash"]!!.jsonPrimitive.content == hash.get()) { "Config changed" }
            return buildJsonObject {
                put("status", "ok")
                for (key in listOf("requestId", "gameId", "tick", "configHash")) put(key, request[key]!!)
                put("scores", buildJsonObject {
                    put("Player1", buildJsonObject { put("A", .6); put("B", .7) })
                    put("Player2", buildJsonObject { put("A", .4); put("B", .4) })
                })
            }
        }
        override fun close() {}
    }

    private fun records(file: File) = file.readLines().filter { it.isNotBlank() }
        .map { Json.parseToJsonElement(it).jsonObject }

    @Test
    fun `full precision stats use fleet owner rather than source owner`() {
        val stats = matchStats(board())
        assertEquals(1, stats["Player1"]!!.jsonObject["planetCount"]!!.jsonPrimitive.int)
        assertEquals(20.25, stats["Player1"]!!.jsonObject["stationedShips"]!!.jsonPrimitive.double)
        assertEquals(5.5, stats["Player1"]!!.jsonObject["shipsInFlight"]!!.jsonPrimitive.double)
        assertEquals(25.75, stats["Player1"]!!.jsonObject["totalShips"]!!.jsonPrimitive.double)
    }

    @Test
    fun `disconnected service retains each tick and reconnect backfills in order`() {
        val online = AtomicBoolean(false)
        val telemetry = ComparisonTelemetry(connectionFactory = {
            check(online.get()) { "offline" }; FakeConnection()
        }, logDirectory = directory, retryMillis = 20, dispatch = { it() })
        telemetry.started(GameParams(maxTicks = 1), "Human", "Random", board())
        telemetry.advanced(board(1))
        telemetry.advanced(board(2))
        telemetry.ended(board(2), aborted = false)
        await { directory.listFiles()?.firstOrNull()?.let { f ->
            runCatching { records(f).count { it["event"]!!.jsonPrimitive.content == "tick" } == 3 }.getOrDefault(false)
        } ?: false }
        assertNull(telemetry.display.scoredTick)
        online.set(true)
        await { telemetry.display.scoredTick == 2 }
        telemetry.close()
        val events = records(directory.listFiles()!!.single())
        assertEquals(listOf(0, 1, 2), events.filter { it["event"]!!.jsonPrimitive.content == "scores" }
            .map { it["tick"]!!.jsonPrimitive.int })
        assertEquals(1, events.count { it["event"]!!.jsonPrimitive.content == "metadata" })
        assertEquals(3, events.count { it["event"]!!.jsonPrimitive.content == "tick" })
        assertFalse(events.first { it["event"]!!.jsonPrimitive.content == "game_end" }["aborted"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun `delayed previous game responses never overwrite the new game display`() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val updates = Collections.synchronizedList(mutableListOf<ScoreDisplay>())
        val telemetry = ComparisonTelemetry(connectionFactory = { FakeConnection(beforeScore = {
            entered.countDown(); check(release.await(5, TimeUnit.SECONDS))
        }) }, logDirectory = directory, dispatch = { it() }, onUpdate = { updates.add(it) })
        try {
            telemetry.started(GameParams(), "first red", "first blue", board())
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            telemetry.ended(board(), aborted = true)
            telemetry.started(GameParams(), "second red", "second blue", board())
            val newId = telemetry.display.gameId
            val startIndex = updates.size
            release.countDown()
            await { telemetry.display.scoredTick == 0 }
            assertEquals(newId, telemetry.display.gameId)
            assertTrue(updates.drop(startIndex).all { it.gameId == newId })
        } finally { release.countDown(); telemetry.close() }
        assertEquals(2, directory.listFiles()!!.size)
        directory.listFiles()!!.forEach { file ->
            assertEquals(1, records(file).map { it["gameId"]!!.jsonPrimitive.content }.toSet().size)
        }
    }

    @Test
    fun `changed configuration cannot mix scores within a game`() {
        val hash = AtomicReference("config-1")
        val telemetry = ComparisonTelemetry(connectionFactory = { FakeConnection(hash) },
            logDirectory = directory, retryMillis = 10, dispatch = { it() })
        try {
            telemetry.started(GameParams(), "red", "blue", board())
            await { telemetry.display.scoredTick == 0 }
            hash.set("config-2")
            telemetry.advanced(board(1))
            await { telemetry.display.status.contains("config changed") }
            assertEquals(0, telemetry.display.scoredTick)
            telemetry.ended(board(1), aborted = true)
            telemetry.started(GameParams(), "red", "blue", board())
            await { telemetry.display.scoredTick == 0 }
            assertEquals("config-2", telemetry.display.metadata!!["configHash"]!!.jsonPrimitive.content)
        } finally { telemetry.close() }
    }

    @Test
    fun `disabled logging still supports display without creating files`() {
        val telemetry = ComparisonTelemetry(connectionFactory = { FakeConnection() }, logDirectory = directory,
            loggingEnabled = false, dispatch = { it() })
        try {
            telemetry.started(GameParams(), "red", "blue", board())
            await { telemetry.display.scoredTick == 0 }
            assertNull(telemetry.display.logPath)
            assertEquals(0, directory.listFiles()!!.size)
        } finally { telemetry.close() }
    }

    @Test
    fun `score panel displays both independent scores and labels stale ticks`() {
        SwingUtilities.invokeAndWait {
            val panel = HeuristicScorePanel()
            val scores = buildJsonObject {
                put("Player1", buildJsonObject { put("A", .6); put("B", .7) })
                put("Player2", buildJsonObject { put("A", .4); put("B", .4) })
            }
            panel.refresh(ScoreDisplay("one", 5, 3, scores = scores, status = "Scores ready"))
            assertEquals("0.700", panel.values["Player1"]!!["B"]!!.text)
            assertEquals("0.400", panel.values["Player2"]!!["B"]!!.text)
            assertTrue(panel.footer.text.contains("tick 3 / board: 5"))
            panel.refresh(ScoreDisplay("two"))
            assertEquals("—", panel.values["Player1"]!!["A"]!!.text)
        }
    }
}
