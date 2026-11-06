package games.planetwars.agents

import games.planetwars.core.*
import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.plugins.websocket.*
import io.ktor.websocket.*
import json_rmi.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class RemoteAgent(
    private val className: String,
    private val port: Int = 8080,
    private val logger: JsonLogger = JsonLogger(),
    private val requestTimeoutMillis: Long? = null,
    private val strictResponses: Boolean = false,
) : PlanetWarsPlayer(), AutoCloseable {

    private val serverUrl = "ws://localhost:$port/ws"
    private val client = HttpClient(CIO) {
        install(WebSockets)
    }

    private lateinit var session: DefaultClientWebSocketSession
    private lateinit var objectId: String
    private var connected = false
    private var closed = false

    private fun <T> request(block: suspend () -> T): T = runBlocking {
        check(!closed) { "Remote agent is closed" }
        if (requestTimeoutMillis == null) block() else withTimeout(requestTimeoutMillis) { block() }
    }

    private fun responseObject(response: String): JsonObject {
        val parsed = json.parseToJsonElement(response).jsonObject
        if (strictResponses && parsed["status"]?.jsonPrimitive?.content != "ok") {
            error(parsed["error"]?.jsonPrimitive?.content ?: "Invalid remote response")
        }
        return parsed
    }

    private suspend fun connectOnceIfNeeded() {
        if (!connected) {
            session = client.webSocketSession(serverUrl)
            objectId = initAgent(session, className, logger)  // ✅ fixed argument order
            connected = true
        }
    }

    override fun prepareToPlayAs(player: Player, params: GameParams, opponent: String?): String = request {
        connectOnceIfNeeded()
        val response = invokeRemoteMethod(
            session = session,
            objectId = objectId,
            method = "prepareToPlayAs",
            args = listOf(player, params, opponent ?: "Anonymous"),
            logger = logger
        )
        responseObject(response)
        readAgentType()
    }

    override fun getAction(gameState: GameState): Action = request {
        connectOnceIfNeeded()
        val response = invokeRemoteMethod(
            session = session,
            objectId = objectId,
            method = "getAction",
            args = listOf(gameState),
            logger = logger
        )
        val jsonResp = responseObject(response)
        val result = jsonResp["result"]
        if (result != null && result is JsonObject) {
            json.decodeFromJsonElement(Action.serializer(), result)
        } else {
            check(!strictResponses) { "Remote agent returned no action" }
            Action.doNothing()
        }
    }

    override fun getAgentType(): String = request { readAgentType() }

    private suspend fun readAgentType(): String {
        connectOnceIfNeeded()
        val response = invokeRemoteMethod(
            session = session,
            objectId = objectId,
            method = "getAgentType",
            args = emptyList(),
            logger = logger
        )
        val jsonResp = responseObject(response)
        val result = jsonResp["result"]
        val type = result?.toString()?.trim('"') ?: "Remote[$className]"
        return "$type (Remote)"
    }

    override fun processGameOver(finalState: GameState) {
        if (closed) return
        try {
            request {
                if (connected) {
                    responseObject(invokeRemoteMethod(
                        session = session,
                        objectId = objectId,
                        method = "processGameOver",
                        args = listOf(finalState),
                        logger = logger,
                    ))
                }
            }
        } finally {
            close()
        }
    }

    /** Bounded, idempotent cleanup, also safe after a connection/init failure. */
    override fun close() {
        if (closed) return
        closed = true
        try {
            runBlocking {
                withTimeoutOrNull(1_000) {
                    if (connected) runCatching { endAgent(session, objectId, logger) }
                    if (::session.isInitialized) session.close()
                }
            }
        } finally {
            if (::session.isInitialized) session.cancel()
            connected = false
            client.close()
        }
    }
}
