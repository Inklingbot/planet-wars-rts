package games.planetwars.view

import games.planetwars.agents.PlanetWarsAgent
import games.planetwars.core.GameParams
import games.planetwars.core.GameState
import games.planetwars.core.Player
import util.Vec2d
import xkg.gui.*
import xkg.jvm.EasyComponent
import xkg.jvm.XGraphicsJVM
import java.awt.BorderLayout
import java.awt.Color
import java.awt.Dimension
import java.awt.Font
import java.awt.event.*
import javax.swing.*
import javax.swing.border.EmptyBorder

/** Decisions and adjustable playback drive ticks; repainting never does. */
class HumanMatchWindow(
    private val params: GameParams,
    opponentName: String,
    opponentFactory: () -> PlanetWarsAgent,
) {
    private val frame = JFrame("Human (red) vs $opponentName (blue) — Tick by tick")
    private val board = EasyComponent(960, 640)
    private val renderer = GameView(GameState(emptyList()), params, paused = true)
    private val selection = HumanPlanetSelection()
    private val fleetSelection = HumanFleetSelection()
    private val orderPanel = HumanOrderPanel()
    private val playbackBar = HumanPlaybackBar()
    private val amount = orderPanel.amount
    private val pass = playbackBar.pass
    private val playPause = playbackBar.playPause
    private val cancel = orderPanel.clearSelection
    private val newGame = playbackBar.newGame
    private val status = JLabel("Starting game…")
    private val message = JTextArea(2, 50)
    private val session = HumanMatchSession(params, opponentFactory, onUpdate = ::acceptSnapshot)
    private val playback = HumanMatchPlayback(session)
    private val repaintTimer = Timer(1000 / 30) { board.repaint() }
    private val playbackTimer = Timer(playback.delayMillis) {
        playback.tick()
        refreshPlaybackControls()
    }.apply { isCoalesce = true }

    init {
        frame.defaultCloseOperation = WindowConstants.DISPOSE_ON_CLOSE
        frame.layout = BorderLayout(0, 0)
        val heading = JPanel(BorderLayout(12, 6)).apply {
            border = EmptyBorder(12, 16, 10, 16)
            add(JLabel("YOU · RED     /     $opponentName · BLUE").apply {
                font = font.deriveFont(Font.BOLD, 16f)
            }, BorderLayout.NORTH)
            add(status, BorderLayout.SOUTH)
        }
        frame.add(heading, BorderLayout.NORTH)
        board.background = Color.BLACK
        board.isFocusable = true
        board.xg = XGraphicsJVM(board)
        board.xApp = object : XApp {
            override fun paint(xg: XGraphics) {
                val snapshot = session.snapshot
                val state = snapshot.state ?: GameState(emptyList())
                renderer.gameState = state
                renderer.paint(xg)
                val viewport = viewport() ?: return
                xg.saveTransform()
                viewport.apply(xg)
                for (planet in state.planets) {
                    val displayRadius = renderer.displayRadius(planet)
                    if (planet.id == selection.sourceId) {
                        val diameter = 2 * (displayRadius + 4)
                        xg.draw(XEllipse(planet.position, diameter, diameter,
                            XStyle(fg = XColor.yellow, fill = false, stroke = true, lineWidth = 2.0)))
                    }
                }
                fleetSelection.current(state)?.let { fleet ->
                    val target = state.planets[fleet.destinationIndex]
                    val targetRadius = renderer.displayRadius(target) + 6
                    val diameter = 2 * targetRadius
                    val style = XStyle(fg = XColor.cyan, fill = false, stroke = true, lineWidth = 2.0)
                    val distance = fleet.s.distance(target.position)
                    if (distance > targetRadius + 24) {
                        val direction = (target.position - fleet.s).normalize()
                        xg.draw(XLine(fleet.s + direction * 24.0, target.position - direction * targetRadius, style))
                    }
                    xg.draw(XEllipse(target.position, diameter, diameter, style))
                    xg.draw(XEllipse(fleet.s, 48.0, 48.0, style))
                }
                xg.restoreTransform()
            }
        }
        board.addMouseListener(object : MouseAdapter() {
            override fun mousePressed(event: MouseEvent) {
                if (event.button != MouseEvent.BUTTON1) return
                val state = session.snapshot.state ?: return
                val viewport = viewport() ?: return
                val point = Vec2d(event.x.toDouble(), event.y.toDouble())
                if (viewport.fleetAt(state, point) == null &&
                    viewport.planetAt(state, point, renderer.planetRadiusScale) == null) {
                    // Deselect immediately, even if a rapid/repeated click will
                    // be ignored by the launch handler's single-click filter.
                    clearSelection()
                    board.requestFocusInWindow()
                }
            }

            override fun mouseClicked(event: MouseEvent) {
                if (event.button == MouseEvent.BUTTON1 && event.clickCount == 1) {
                    onBoardClick(Vec2d(event.x.toDouble(), event.y.toDouble()))
                }
            }
        })
        bindBoardKey("SPACE", "pass") { if (pass.isEnabled) manualPass() }
        bindBoardKey("ESCAPE", "cancel") { clearSelection() }
        frame.add(board, BorderLayout.CENTER)

        val controls = JPanel(BorderLayout(0, 8)).apply { border = EmptyBorder(10, 16, 14, 16) }
        controls.add(orderPanel, BorderLayout.NORTH)
        message.apply {
            isEditable = false
            isFocusable = false
            lineWrap = true
            wrapStyleWord = true
            isOpaque = false
            font = amount.font
        }
        controls.add(message, BorderLayout.CENTER)
        controls.add(playbackBar, BorderLayout.SOUTH)
        frame.add(controls, BorderLayout.SOUTH)
        playbackBar.speed.addChangeListener {
            playback.setSpeed(playbackBar.speed.value)
            playbackTimer.delay = playback.delayMillis
            playbackTimer.initialDelay = playback.delayMillis
            if (playback.playing) playbackTimer.restart()
            refreshStatus(session.snapshot)
        }
        playPause.addActionListener {
            if (playback.playing) playback.pause() else playback.play()
            refreshPlaybackControls()
            refreshStatus(session.snapshot)
            board.requestFocusInWindow()
        }
        pass.addActionListener { manualPass(); board.requestFocusInWindow() }
        cancel.addActionListener { clearSelection(); board.requestFocusInWindow() }
        amount.addActionListener { board.requestFocusInWindow() }
        amount.getInputMap(JComponent.WHEN_FOCUSED).put(KeyStroke.getKeyStroke("ESCAPE"), "cancel-selection")
        amount.actionMap.put("cancel-selection", object : AbstractAction() {
            override fun actionPerformed(event: ActionEvent) {
                clearSelection()
                board.requestFocusInWindow()
            }
        })
        newGame.addActionListener {
            playback.pause()
            refreshPlaybackControls()
            clearSelection()
            amount.text = ""
            session.newGame()
        }
        frame.addWindowListener(object : WindowAdapter() {
            override fun windowClosed(event: WindowEvent) {
                repaintTimer.stop()
                playbackTimer.stop()
                playback.pause()
                session.close()
            }
        })
        acceptSnapshot(session.snapshot.copy(busy = true))
        frame.minimumSize = Dimension(720, 680)
        frame.pack()
        frame.setLocationRelativeTo(null)
    }

    fun show() {
        frame.isVisible = true
        repaintTimer.start()
        session.newGame()
        board.requestFocusInWindow()
    }

    private fun viewport() = BoardViewport.fit(params.width.toDouble(), params.height.toDouble(),
        board.width.toDouble(), board.height.toDouble())

    private fun bindBoardKey(key: String, name: String, action: () -> Unit) {
        board.getInputMap(JComponent.WHEN_FOCUSED).put(KeyStroke.getKeyStroke(key), name)
        board.actionMap.put(name, object : AbstractAction() {
            override fun actionPerformed(event: ActionEvent) { action() }
        })
    }

    private fun clearSelection() {
        selection.clear()
        fleetSelection.clear()
        refreshSelection(session.snapshot)
        message.text = "Selection cleared. Select a red planet, inspect a fleet, or Pass."
        message.foreground = Color(55, 55, 55)
        board.repaint()
    }

    private fun refreshSelection(snapshot: HumanMatchSnapshot) {
        val state = snapshot.state
        if (state != null) selection.reconcile(state)
        val inspected = state?.let { fleetSelection.current(it) }
        orderPanel.refresh(snapshot, selection.sourceId, inspected)
    }

    private fun acceptSnapshot(snapshot: HumanMatchSnapshot) {
        playback.observe(snapshot)
        refreshPlaybackControls()
        refreshStatus(snapshot)
        message.text = snapshot.message
        message.foreground = if (snapshot.error) Color(170, 35, 35) else Color(55, 55, 55)
        refreshSelection(snapshot)
        board.repaint()
    }

    private fun refreshPlaybackControls() {
        playbackBar.refresh(session.snapshot, playback.playing)
        if (playback.playing) {
            if (!playbackTimer.isRunning) playbackTimer.start()
        } else playbackTimer.stop()
    }

    private fun manualPass() {
        session.pass()
        if (playback.playing) playbackTimer.restart()
    }

    private fun refreshStatus(snapshot: HumanMatchSnapshot) {
        val state = snapshot.state
        status.text = if (state == null) "Waiting for game initialization" else {
            val own = state.planets.count { it.owner == Player.Player1 }
            val enemy = state.planets.count { it.owner == Player.Player2 }
            "Tick ${state.gameTick} · Your planets: $own · Opponent planets: $enemy · " +
                (snapshot.result ?: if (snapshot.busy) "Opponent thinking…" else
                    if (playback.playing) "Playing · ${playback.ticksPerSecond} ticks/second" else
                        "Paused · Launch or Pass to advance")
        }
    }

    private fun onBoardClick(point: Vec2d) {
        val snapshot = session.snapshot
        val state = snapshot.state ?: return
        val viewport = viewport() ?: return
        // Fleets are painted over planets, so pick them first. Inspection is safe
        // even while the opponent is thinking or when the final board is frozen.
        val fleet = viewport.fleetAt(state, point)
        if (fleet != null) {
            selection.clear()
            fleetSelection.select(fleet)
            refreshSelection(snapshot)
            message.text = "Fleet destination highlighted in cyan. Inspection does not advance time."
            message.foreground = Color(55, 55, 55)
            board.requestFocusInWindow()
            board.repaint()
            return
        }
        val planet = viewport.planetAt(state, point, renderer.planetRadiusScale)
        if (planet == null) {
            clearSelection()
            return
        }
        if (snapshot.busy || snapshot.gameOver) return
        fleetSelection.clear()
        refreshSelection(snapshot)
        val source = selection.sourceId
        if (source == null) {
            val error = selection.select(state, planet.id)
            if (error != null) {
                message.text = error
                message.foreground = Color(170, 35, 35)
            } else {
                refreshSelection(snapshot)
                message.text = "Enter the ship count, then click a different planet to launch. Escape cancels selection."
                message.foreground = Color(55, 55, 55)
                amount.requestFocusInWindow()
                amount.selectAll()
            }
        } else {
            val ships = amount.text.trim().toDoubleOrNull()
            if (ships == null) {
                message.text = "Enter a numeric ship count before choosing a destination."
                message.foreground = Color(170, 35, 35)
                amount.requestFocusInWindow()
                amount.selectAll()
            } else {
                session.launch(source, planet.id, ships)
                if (playback.playing) playbackTimer.restart()
                board.requestFocusInWindow()
            }
        }
        board.repaint()
    }
}
