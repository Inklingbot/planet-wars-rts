package games.planetwars.agents

import games.planetwars.core.GameParams
import games.planetwars.core.GameState
import games.planetwars.core.Player

/** Non-blocking agent: the GUI supplies one order before requesting a game tick. */
class HumanAgent : PlanetWarsPlayer() {
    private var pending: Action? = null

    override fun prepareToPlayAs(player: Player, params: GameParams, opponent: String?): String {
        require(player != Player.Neutral)
        pending = null
        return super.prepareToPlayAs(player, params, opponent)
    }

    fun submit(action: Action) {
        check(pending == null) { "A human order is already pending" }
        require(action.playerId == player)
        pending = action
    }

    fun clearPending() {
        pending = null
    }

    override fun getAction(gameState: GameState): Action {
        val action = pending ?: return Action.DO_NOTHING
        pending = null
        require(validateLaunch(gameState, player, action) == null) { "Human order is no longer valid" }
        return action
    }

    override fun getAgentType() = "Human"

    companion object {
        fun validateLaunch(state: GameState, player: Player, action: Action): String? {
            if (action.playerId != player) return "This order belongs to another player."
            val source = state.planets.getOrNull(action.sourcePlanetId)
                ?: return "Select a source planet."
            if (action.destinationPlanetId !in state.planets.indices) return "Select a destination planet."
            if (action.sourcePlanetId == action.destinationPlanetId) return "Choose a different destination planet."
            if (source.owner != player) return "You no longer own the source planet."
            if (source.transporter != null) return "This source already has a fleet in flight."
            if (!action.numShips.isFinite() || action.numShips <= 0) return "Enter a positive, finite ship count."
            if (action.numShips > source.nShips) return "The source does not have that many ships."
            return null
        }
    }
}
