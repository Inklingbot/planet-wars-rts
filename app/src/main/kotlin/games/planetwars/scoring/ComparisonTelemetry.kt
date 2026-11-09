package games.planetwars.scoring

import games.planetwars.core.*
import kotlinx.serialization.json.*
import java.io.File
import java.io.RandomAccessFile
import java.nio.charset.StandardCharsets
import java.time.Instant
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import javax.swing.SwingUtilities

data class ScoreDisplay(
    val gameId: String = "",
    val boardTick: Int = 0,
    val scoredTick: Int? = null,
    val metadata: JsonObject? = null,
    val scores: JsonObject? = null,
    val status: String = "Waiting for a game",
    val logPath: String? = null,
)

fun matchStats(state: GameState): JsonObject = buildJsonObject {
    for (player in listOf(Player.Player1, Player.Player2)) {
        val planets = state.planets.filter { it.owner == player }
        val stationed = planets.sumOf { it.nShips }
        val flying = state.planets.mapNotNull { it.transporter }.filter { it.owner == player }.sumOf { it.nShips }
        put(player.name, buildJsonObject {
            put("planetCount", planets.size)
            put("stationedShips", stationed)
            put("shipsInFlight", flying)
            put("totalShips", stationed + flying)
        })
    }
}

/** Durable tick snapshots and independent background scoring. No agent calls. */
class ComparisonTelemetry(
    private val connectionFactory: () -> ScoreConnection = {
        WebSocketScoreConnection(System.getenv("HEURISTIC_SCORER_URL") ?: "ws://127.0.0.1:8766")
    },
    private val logDirectory: File = File(System.getenv("HEURISTIC_LOG_DIR") ?: "log_data/heuristics"),
    private val loggingEnabled: Boolean = System.getenv("HEURISTIC_LOGGING")?.toBooleanStrictOrNull() ?: true,
    private val retryMillis: Long = 1_000,
    private val dispatch: (() -> Unit) -> Unit = { SwingUtilities.invokeLater(it) },
    private val onUpdate: (ScoreDisplay) -> Unit = {},
) : MatchObserver {
    private val json = Json { encodeDefaults = true }
    private val lifecycle = Any()
    private val writer = Executors.newSingleThreadExecutor { Thread(it, "heuristic-history").apply { isDaemon = true } }
    private val scorer = Executors.newSingleThreadExecutor { Thread(it, "heuristic-scoring").apply { isDaemon = true } }
    private class Trace(val id: String, val params: JsonObject, val file: File?) {
        var boardTick = -1
        var scoredTick: Int? = null
        var metadata: JsonObject? = null
        var scores: JsonObject? = null
        var status = "Waiting for scoring service"
        var logError: String? = null
        var ended = false
        var incompatible = false
    }
    private data class Pending(val trace: Trace, val offset: Long?, val memory: JsonObject?)
    private val pending = LinkedBlockingQueue<Pending>()
    @Volatile private var closed = false
    @Volatile private var current: Trace? = null

    val display: ScoreDisplay
        get() = current?.let(::view) ?: ScoreDisplay()

    init { scorer.submit { scoreLoop() } }

    private fun view(trace: Trace): ScoreDisplay = synchronized(trace) {
        ScoreDisplay(trace.id, trace.boardTick, trace.scoredTick, trace.metadata, trace.scores,
            trace.logError ?: trace.status, trace.file?.absolutePath)
    }

    private fun notify(trace: Trace, status: String? = null) {
        if (status != null) synchronized(trace) { trace.status = status }
        dispatch { if (!closed && current === trace) onUpdate(view(trace)) }
    }

    private fun writeTask(task: () -> Unit) = synchronized(lifecycle) {
        if (!closed) writer.submit(task)
    }

    private fun append(trace: Trace, event: JsonObject): Long? {
        val file = trace.file ?: return null
        return try {
            file.parentFile.mkdirs()
            val offset = file.length()
            file.appendText(event.toString() + "\n", Charsets.UTF_8)
            offset
        } catch (error: Exception) {
            synchronized(trace) { trace.logError = "History write failed: ${error.message}" }
            notify(trace)
            null
        }
    }

    private fun event(trace: Trace, name: String, fields: JsonObject = buildJsonObject {}): JsonObject =
        buildJsonObject {
            put("event", name)
            put("gameId", trace.id)
            put("timestampMillis", System.currentTimeMillis())
            fields.forEach { (key, value) -> put(key, value) }
        }

    override fun started(params: GameParams, player1: String, player2: String, state: GameState) {
        if (closed) return
        val id = UUID.randomUUID().toString()
        val filename = Instant.now().toString().replace(':', '-') + "_$id.jsonl"
        val trace = Trace(id, json.encodeToJsonElement(GameParams.serializer(), params).jsonObject,
            if (loggingEnabled) File(logDirectory, filename) else null)
        current = trace
        writeTask {
            val revision = runCatching {
                val process = ProcessBuilder("git", "rev-parse", "HEAD").redirectErrorStream(true).start()
                if (process.waitFor(1, TimeUnit.SECONDS) && process.exitValue() == 0)
                    process.inputStream.bufferedReader().readText().trim()
                else { process.destroyForcibly(); null }
            }.getOrNull()
            append(trace, event(trace, "game_start", buildJsonObject {
                put("schemaVersion", 1)
                put("params", trace.params)
                put("players", buildJsonObject { put("Player1", player1); put("Player2", player2) })
                put("codeRevision", revision?.let(::JsonPrimitive) ?: JsonNull)
            }))
        }
        record(trace, state)
    }

    override fun advanced(state: GameState) { current?.let { record(it, state) } }

    private fun record(trace: Trace, state: GameState) {
        val copy: GameState
        synchronized(trace) {
            if (closed || trace.ended || state.gameTick <= trace.boardTick) return
            trace.boardTick = state.gameTick
            copy = state.deepCopy()
        }
        notify(trace)
        writeTask {
            val record = event(trace, "tick", buildJsonObject {
                put("tick", copy.gameTick)
                put("state", json.encodeToJsonElement(GameState.serializer(), copy))
                put("stats", matchStats(copy))
            })
            val offset = append(trace, record)
            // Keep just an offset when durable storage works, not whole old boards in RAM.
            pending.put(Pending(trace, offset, if (offset == null) record else null))
        }
    }

    override fun ended(state: GameState, aborted: Boolean) {
        val trace = current ?: return
        synchronized(trace) {
            if (trace.ended) return
            trace.ended = true
        }
        val tick = state.gameTick
        val winner = if (aborted) null else ForwardModel(state, GameParams()).getLeader().name
        writeTask { append(trace, event(trace, "game_end", buildJsonObject {
            put("tick", tick)
            put("aborted", aborted)
            put("winner", winner?.let(::JsonPrimitive) ?: JsonNull)
        })) }
    }

    private fun load(job: Pending): JsonObject {
        job.memory?.let { return it }
        val line = RandomAccessFile(checkNotNull(job.trace.file), "r").use {
            it.seek(checkNotNull(job.offset))
            it.readLine()
        }
        val utf8 = line.toByteArray(StandardCharsets.ISO_8859_1).toString(StandardCharsets.UTF_8)
        return json.parseToJsonElement(utf8).jsonObject
    }

    private fun scoreLoop() {
        var connection: ScoreConnection? = null
        var job: Pending? = null
        try {
            while (!closed) {
                try {
                    val item = job ?: pending.poll(100, TimeUnit.MILLISECONDS)?.also { job = it } ?: continue
                    val trace = item.trace
                    if (trace.incompatible) { job = null; continue }
                    if (connection == null) {
                        connection = connectionFactory()
                        val metadata = connection.exchange(buildJsonObject { put("type", "describe") })["metadata"]!!.jsonObject
                        val pinned = trace.metadata
                        if (pinned != null && pinned["configHash"] != metadata["configHash"]) {
                            trace.incompatible = true
                            notify(trace, "Scoring config changed. Start New Game; old history can be rescored offline.")
                            job = null
                            continue
                        }
                    }
                    if (trace.metadata == null) {
                        val metadata = connection.exchange(buildJsonObject { put("type", "describe") })["metadata"]!!.jsonObject
                        synchronized(trace) { trace.metadata = metadata }
                        writeTask { append(trace, event(trace, "metadata", buildJsonObject { put("metadata", metadata) })) }
                    }
                    val record = load(item)
                    val tick = record["tick"]!!.jsonPrimitive.int
                    val requestId = UUID.randomUUID().toString()
                    val hash = checkNotNull(trace.metadata)["configHash"]!!
                    val response = connection.exchange(buildJsonObject {
                        put("type", "score"); put("requestId", requestId)
                        put("gameId", trace.id); put("tick", tick); put("configHash", hash)
                        put("params", trace.params); put("state", record["state"]!!)
                    })
                    check(response["gameId"]?.jsonPrimitive?.content == trace.id &&
                        response["tick"]?.jsonPrimitive?.int == tick &&
                        response["requestId"]?.jsonPrimitive?.content == requestId && response["configHash"] == hash) {
                        "Scorer returned a mismatched game, tick, or configuration"
                    }
                    val scores = response["scores"]!!.jsonObject
                    for (player in listOf("Player1", "Player2")) for (slot in listOf("A", "B")) {
                        val value = scores[player]!!.jsonObject[slot]!!.jsonPrimitive.double
                        check(value.isFinite() && value in 0.0..1.0) { "Invalid heuristic score" }
                    }
                    writeTask { append(trace, event(trace, "scores", buildJsonObject {
                        put("tick", tick); put("configHash", hash); put("scores", scores)
                    })) }
                    synchronized(trace) { trace.scoredTick = tick; trace.scores = scores }
                    notify(trace, "Scores ready")
                    job = null
                } catch (error: Exception) {
                    runCatching { connection?.close() }
                    connection = null
                    if (closed) break
                    current?.let { notify(it, "Scoring unavailable; snapshots retained. Retrying… ${error.message ?: ""}") }
                    try { Thread.sleep(retryMillis) } catch (_: InterruptedException) { break }
                }
            }
        } finally { runCatching { connection?.close() } }
    }

    override fun close() {
        synchronized(lifecycle) {
            if (closed) return
            closed = true
            scorer.shutdownNow()
            writer.shutdown()
        }
        // Called by the match worker / spectator main thread, not Swing.
        writer.awaitTermination(3, TimeUnit.SECONDS)
    }
}
