package games.planetwars.view

import games.planetwars.agents.Action
import games.planetwars.agents.HumanAgent
import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.core.*
import games.planetwars.scoring.MatchObserver
import java.util.concurrent.CompletableFuture
import java.util.concurrent.Executors
import java.util.concurrent.Future
import javax.swing.SwingUtilities

data class HumanMatchSnapshot(
    val state: GameState? = null,
    val busy: Boolean = false,
    val gameOver: Boolean = false,
    val message: String = "Start a new game.",
    val error: Boolean = false,
    val result: String? = null,
)

/** All mutable simulation/agent state belongs to one worker, never the Swing EDT. */
class HumanMatchSession(
    val params: GameParams,
    private val opponentFactory: () -> PlanetWarsAgent,
    private val stateFactory: () -> GameState = { GameStateFactory(params).createGame() },
    private val dispatch: (() -> Unit) -> Unit = { SwingUtilities.invokeLater(it) },
    private val onUpdate: (HumanMatchSnapshot) -> Unit = {},
    private val observer: MatchObserver? = null,
) : AutoCloseable {
    private val lock = Any()
    private val worker = Executors.newSingleThreadExecutor { runnable ->
        // Keep the process alive until window-close cleanup flushes its observer.
        Thread(runnable, "human-match")
    }
    private var closed = false
    private var activeTask: Future<*>? = null
    private var activeResult: CompletableFuture<HumanMatchSnapshot>? = null
    private var model: ForwardModel? = null
    private var human = HumanAgent()
    private var opponent: PlanetWarsAgent? = null
    private var opponentName = "Opponent"
    private var observationActive = false

    private fun observe(action: MatchObserver.() -> Unit) {
        observer?.let { runCatching { it.action() }.onFailure { error ->
            System.err.println("Match observation failed: ${error.message}")
        } }
    }

    private fun endObservation(aborted: Boolean) {
        val state = model?.state ?: return
        if (observationActive) {
            observationActive = false
            observe { ended(state.deepCopy(), aborted) }
        }
    }

    @Volatile
    var snapshot = HumanMatchSnapshot()
        private set

    private fun publish(next: HumanMatchSnapshot) {
        snapshot = next
        dispatch {
            synchronized(lock) {
                if (!closed && snapshot === next) onUpdate(next)
            }
        }
    }

    private fun disposeOpponent() {
        val previous = opponent
        opponent = null
        if (previous is AutoCloseable) runCatching { previous.close() }
    }

    private fun readyOpponent(): PlanetWarsAgent {
        opponent?.let { return it }
        val fresh = opponentFactory()
        opponent = fresh // Also close clients whose initialization fails.
        opponentName = fresh.prepareToPlayAs(Player.Player2, params, human.getAgentType())
        return fresh
    }

    private fun current(message: String, error: Boolean = false): HumanMatchSnapshot {
        val currentModel = model
        val terminal = currentModel?.isTerminal() ?: false
        val result = if (terminal) when (currentModel!!.getLeader()) {
            Player.Player1 -> "You win!"
            Player.Player2 -> "Opponent wins."
            Player.Neutral -> "Draw."
        } else null
        return HumanMatchSnapshot(currentModel?.state?.deepCopy(), gameOver = terminal,
            message = message, error = error, result = result)
    }

    private fun submitTask(message: String, operation: () -> String): CompletableFuture<HumanMatchSnapshot> =
        synchronized(lock) {
            if (closed || snapshot.busy) return@synchronized CompletableFuture.completedFuture(snapshot)
            val result = CompletableFuture<HumanMatchSnapshot>()
            activeResult = result
            publish(snapshot.copy(busy = true, message = message, error = false))
            activeTask = worker.submit {
                val next = try {
                    current(operation())
                } catch (error: Exception) {
                    human.clearPending()
                    disposeOpponent()
                    current("Opponent unavailable: ${error.message ?: error.javaClass.simpleName}. " +
                        "No tick advanced. Retry, or choose New Game. For MCTS, check the Python server.", true)
                }
                synchronized(lock) {
                    if (!closed) {
                        publish(next)
                        result.complete(next)
                    }
                }
            }
            result
        }

    fun newGame(): CompletableFuture<HumanMatchSnapshot> = submitTask("Starting game…") {
        endObservation(aborted = true)
        disposeOpponent()
        model = null
        human = HumanAgent()
        human.prepareToPlayAs(Player.Player1, params, "Opponent")
        val fresh = ForwardModel(stateFactory().deepCopy(), params)
        readyOpponent()
        model = fresh
        observationActive = observer != null
        observe { started(params, human.getAgentType(), opponentName, fresh.state.deepCopy()) }
        "Choose a source and ship count, then a destination. Or Pass to advance one tick."
    }

    fun launch(source: Int, destination: Int, ships: Double): CompletableFuture<HumanMatchSnapshot> =
        decide(Action(Player.Player1, source, destination, ships))

    fun pass(): CompletableFuture<HumanMatchSnapshot> = decide(Action.DO_NOTHING)

    private fun decide(action: Action): CompletableFuture<HumanMatchSnapshot> = synchronized(lock) {
        val state = snapshot.state
        if (closed || snapshot.busy || state == null || snapshot.gameOver) {
            return@synchronized CompletableFuture.completedFuture(snapshot)
        }
        if (action != Action.DO_NOTHING) {
            val error = HumanAgent.validateLaunch(state, Player.Player1, action)
            if (error != null) {
                publish(snapshot.copy(message = error, error = true))
                return@synchronized CompletableFuture.completedFuture(snapshot)
            }
        }
        submitTask("Opponent is choosing… No more input until this tick finishes.") {
            val previous = checkNotNull(model)
            if (action != Action.DO_NOTHING) {
                require(HumanAgent.validateLaunch(previous.state, Player.Player1, action) == null)
                human.submit(action)
            }
            val ai = readyOpponent()
            val other = ai.getAction(previous.state.deepCopy())
            val own = human.getAction(previous.state.deepCopy())
            // Commit only after both actions are available. AI errors leave the board untouched.
            val next = ForwardModel(previous.state.deepCopy(), params)
            next.step(mapOf(Player.Player1 to own, Player.Player2 to other))
            model = next
            observe { advanced(next.state.deepCopy()) }
            if (next.isTerminal()) {
                endObservation(aborted = false)
                val cleanup = runCatching { ai.processGameOver(next.state.deepCopy()) }
                disposeOpponent()
                "Game over. Choose New Game to play again." +
                    if (cleanup.isFailure) " Opponent cleanup failed; the final board is preserved." else ""
            } else if (own == Action.DO_NOTHING) {
                "Passed one tick."
            } else {
                "Launched ${own.numShips} ships from #${own.sourcePlanetId} to #${own.destinationPlanetId}."
            }
        }
    }

    override fun close() {
        synchronized(lock) {
            if (closed) return
            closed = true
            activeResult?.cancel(false)
            activeTask?.cancel(true)
            worker.submit {
                endObservation(aborted = !(model?.isTerminal() ?: false))
                disposeOpponent()
                observe { close() }
            }
            worker.shutdown()
        }
    }
}

/** Selection survives passes only while the source remains owned and available. */
class HumanPlanetSelection {
    var sourceId: Int? = null
        private set

    fun select(state: GameState, id: Int): String? {
        val source = state.planets.getOrNull(id) ?: return "Click an owned planet to select a source."
        if (source.owner != Player.Player1) return "Select one of your red planets first."
        if (source.transporter != null) return "This planet already has a fleet in flight."
        sourceId = id
        return null
    }

    fun clear() { sourceId = null }

    fun reconcile(state: GameState) {
        val id = sourceId ?: return
        val source = state.planets.getOrNull(id)
        if (source == null || source.owner != Player.Player1 || source.transporter != null) clear()
    }
}
