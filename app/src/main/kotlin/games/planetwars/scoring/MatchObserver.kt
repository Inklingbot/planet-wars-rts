package games.planetwars.scoring

import games.planetwars.core.GameParams
import games.planetwars.core.GameState

/** Optional observation hooks. Only the two comparison-enabled visual launchers install one. */
interface MatchObserver : AutoCloseable {
    fun started(params: GameParams, player1: String, player2: String, state: GameState)
    fun advanced(state: GameState)
    fun ended(state: GameState, aborted: Boolean)
    override fun close() {}
}
