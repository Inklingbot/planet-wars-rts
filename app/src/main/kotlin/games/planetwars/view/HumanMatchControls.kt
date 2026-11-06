package games.planetwars.view

import games.planetwars.core.Transporter
import java.awt.*
import javax.swing.*
import javax.swing.border.EmptyBorder

enum class PlaybackGlyph { PLAY, PAUSE, SKIP }

/** Draw icons directly to avoid platform-dependent Unicode glyphs. */
class PlaybackIcon(private val glyph: PlaybackGlyph) : Icon {
    override fun getIconWidth() = 28
    override fun getIconHeight() = 28

    override fun paintIcon(component: Component?, graphics: Graphics, x: Int, y: Int) {
        val g = graphics.create() as Graphics2D
        try {
            g.translate(x, y)
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON)
            g.color = if (component?.isEnabled != false) component?.foreground ?: Color.DARK_GRAY else Color.GRAY
            when (glyph) {
                PlaybackGlyph.PLAY -> g.fillPolygon(intArrayOf(6, 6, 24), intArrayOf(3, 25, 14), 3)
                PlaybackGlyph.PAUSE -> {
                    g.fillRoundRect(5, 3, 6, 22, 2, 2)
                    g.fillRoundRect(17, 3, 6, 22, 2, 2)
                }
                PlaybackGlyph.SKIP -> {
                    g.fillPolygon(intArrayOf(4, 4, 19), intArrayOf(3, 25, 14), 3)
                    g.fillRect(22, 3, 3, 22)
                }
            }
        } finally { g.dispose() }
    }
}

class HumanPlaybackBar : JPanel(BorderLayout(16, 0)) {
    val playPause = JButton(PlaybackIcon(PlaybackGlyph.PLAY))
    val pass = JButton(PlaybackIcon(PlaybackGlyph.SKIP))
    val newGame = JButton("New Game")
    val speed = JSlider(HumanMatchPlayback.MIN_TICKS_PER_SECOND,
        HumanMatchPlayback.MAX_TICKS_PER_SECOND, HumanMatchPlayback.DEFAULT_TICKS_PER_SECOND)
    val speedReadout = JLabel()

    init {
        border = BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(Color(205, 210, 218)), EmptyBorder(8, 10, 8, 10))
        add(JPanel(FlowLayout(FlowLayout.LEFT, 8, 0)).apply {
            for (button in listOf(playPause, pass)) {
                button.preferredSize = Dimension(56, 48)
                add(button)
            }
        }, BorderLayout.WEST)
        pass.toolTipText = "Pass: advance one tick without launching ships (Space)"
        pass.accessibleContext.accessibleName = "Pass one tick"
        add(JPanel(BorderLayout(10, 0)).apply {
            add(JLabel("Tick speed"), BorderLayout.WEST)
            add(speed, BorderLayout.CENTER)
            speedReadout.preferredSize = Dimension(85, 24)
            add(speedReadout, BorderLayout.EAST)
        }, BorderLayout.CENTER)
        speed.apply {
            majorTickSpacing = 5
            minorTickSpacing = 1
            paintTicks = true
            toolTipText = "Target simulation ticks per second"
            accessibleContext.accessibleName = "Tick speed"
            addChangeListener { speedReadout.text = "$value ticks/s" }
        }
        speedReadout.text = "${speed.value} ticks/s"
        add(newGame, BorderLayout.EAST)
    }

    fun refresh(snapshot: HumanMatchSnapshot, playing: Boolean) {
        val action = if (playing) "Pause" else "Play"
        playPause.icon = PlaybackIcon(if (playing) PlaybackGlyph.PAUSE else PlaybackGlyph.PLAY)
        playPause.toolTipText = action
        playPause.accessibleContext.accessibleName = action
        // Pause remains usable while an opponent request is in progress.
        playPause.isEnabled = playing ||
            (snapshot.state != null && !snapshot.busy && !snapshot.gameOver)
        pass.isEnabled = snapshot.state != null && !snapshot.busy && !snapshot.gameOver
        newGame.isEnabled = !snapshot.busy
    }
}

/** Refreshes labels and availability without ever overwriting user-entered text. */
class HumanOrderPanel : JPanel(BorderLayout(0, 6)) {
    val amount = JTextField(12)
    val clearSelection = JButton("Clear Selection")
    val sourceLabel = JLabel("No source selected")

    init {
        add(sourceLabel, BorderLayout.NORTH)
        add(JPanel(FlowLayout(FlowLayout.LEFT, 8, 0)).apply {
            add(JLabel("Ships:"))
            add(amount)
            add(clearSelection)
        }, BorderLayout.SOUTH)
    }

    fun refresh(snapshot: HumanMatchSnapshot, sourceId: Int?, inspected: Transporter?) {
        val selected = sourceId?.let { snapshot.state?.planets?.getOrNull(it) }
        sourceLabel.text = when {
            inspected != null -> "Fleet #${inspected.sourceIndex} → planet #${inspected.destinationIndex} · " +
                "${formatShipCount(inspected.nShips, 4)} ships"
            selected != null -> "Source #${selected.id} · ${formatShipCount(selected.nShips, 4)} available"
            else -> "No source selected"
        }
        amount.isEnabled = selected != null && !snapshot.busy && !snapshot.gameOver
        clearSelection.isEnabled = inspected != null || (selected != null && !snapshot.busy)
    }
}
