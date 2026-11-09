package games.planetwars.scoring

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.websocket.*
import io.ktor.websocket.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*

interface ScoreConnection : AutoCloseable {
    fun exchange(request: JsonObject): JsonObject
}

/** A separate connection/client from agent RPC; never used on the Swing thread. */
class WebSocketScoreConnection(private val url: String) : ScoreConnection {
    private val client = HttpClient(CIO) { install(WebSockets) }
    private var session: DefaultClientWebSocketSession? = null

    override fun exchange(request: JsonObject): JsonObject = runBlocking {
        withTimeout(2_000) {
            val socket = session ?: client.webSocketSession(url).also { session = it }
            socket.send(request.toString())
            val response = (socket.incoming.receive() as Frame.Text).readText()
            Json.parseToJsonElement(response).jsonObject.also {
                check(it["status"]?.jsonPrimitive?.content == "ok") {
                    it["error"]?.jsonPrimitive?.content ?: "Invalid scoring response"
                }
            }
        }
    }

    override fun close() {
        session?.cancel()
        session = null
        client.close()
    }
}
