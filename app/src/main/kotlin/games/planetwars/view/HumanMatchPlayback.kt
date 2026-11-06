package games.planetwars.view

import java.util.concurrent.CompletableFuture

/** The GUI schedules ticks at the selected speed; missed ticks are never queued. */
class HumanMatchPlayback(private val session: HumanMatchSession) {
    var playing: Boolean = false
        private set

    var ticksPerSecond: Int = DEFAULT_TICKS_PER_SECOND
        private set

    val delayMillis: Int
        get() = kotlin.math.ceil(1000.0 / ticksPerSecond).toInt()

    fun setSpeed(ticksPerSecond: Int) {
        require(ticksPerSecond in MIN_TICKS_PER_SECOND..MAX_TICKS_PER_SECOND)
        this.ticksPerSecond = ticksPerSecond
    }

    fun play() {
        val snapshot = session.snapshot
        if (snapshot.state != null && !snapshot.busy && !snapshot.gameOver) playing = true
    }

    fun pause() {
        playing = false
    }

    fun observe(snapshot: HumanMatchSnapshot) {
        if (snapshot.state == null || snapshot.gameOver || snapshot.error) pause()
    }

    fun tick(): CompletableFuture<HumanMatchSnapshot> {
        val snapshot = session.snapshot
        if (snapshot.state == null || snapshot.gameOver) pause()
        return if (playing && !snapshot.busy) session.pass()
            else CompletableFuture.completedFuture(snapshot)
    }

    companion object {
        const val DEFAULT_TICKS_PER_SECOND = 10
        const val MIN_TICKS_PER_SECOND = 1
        const val MAX_TICKS_PER_SECOND = 30
    }
}
