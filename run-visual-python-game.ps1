param(
    [ValidateSet("PureRandomAgent", "CarefulRandomAgent", "GreedyHeuristicAgent", "OneTrickAgent", "DefensiveCircleAgent", "HyperAggressiveAgent")]
    [string]$Agent1 = "PureRandomAgent",

    [ValidateSet("PureRandomAgent", "CarefulRandomAgent", "GreedyHeuristicAgent", "OneTrickAgent", "HyperAggressiveAgent", "DefensiveCircleAgent")]
    [string]$Agent2 = "CarefulRandomAgent"
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$pythonRoot = Join-Path $repoRoot "app\src\main\python"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$gradleWrapper = Join-Path $repoRoot "gradlew.bat"
$agentProcesses = @()

function Get-AgentDefinition {
    param([string]$AgentName)

    switch ($AgentName) {
        "PureRandomAgent" {
            return @{ Module = "agents.random_agents"; Class = "PureRandomAgent" }
        }
        "CarefulRandomAgent" {
            return @{ Module = "agents.random_agents"; Class = "CarefulRandomAgent" }
        }
        "GreedyHeuristicAgent" {
            return @{ Module = "agents.greedy_heuristic_agent"; Class = "GreedyHeuristicAgent" }
        }
        "OneTrickAgent" {
            return @{ Module = "agents.one_trick_agent"; Class = "OneTrickAgent" }
        }
        "DefensiveCircleAgent" {
            return @{ Module = "agents.defensive_circle_agent"; Class = "DefensiveCircleAgent" }
        }
    }
}

function Start-AgentServer {
    param(
        [string]$AgentName,
        [int]$Port
    )

    $definition = Get-AgentDefinition $AgentName
    $pythonCode = "import asyncio; from client_server.game_agent_server import GameServerAgent; from $($definition.Module) import $($definition.Class); asyncio.run(GameServerAgent(port=$Port, agent=$($definition.Class)()).start())"

    Write-Host "Starting $AgentName on port $Port..."
    return Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @("-c", "`"$pythonCode`"") `
        -WorkingDirectory $pythonRoot `
        -NoNewWindow `
        -PassThru
}

function Wait-AgentServer {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$AgentName,
        [int]$Port,
        [int]$TimeoutSeconds = 15
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "$AgentName exited before it was ready (exit code $($Process.ExitCode))."
        }

        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $connect = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            if ($connect.AsyncWaitHandle.WaitOne(250) -and $client.Connected) {
                $client.EndConnect($connect)
                Write-Host "$AgentName is ready."
                return
            }
        }
        catch {
            # The server may still be starting.
        }
        finally {
            $client.Dispose()
        }

        Start-Sleep -Milliseconds 200
    }

    throw "Timed out waiting for $AgentName on port $Port."
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python virtual environment not found at $pythonExe"
}

if (-not (Test-Path -LiteralPath $gradleWrapper)) {
    throw "Gradle wrapper not found at $gradleWrapper"
}

try {
    $agent1Process = Start-AgentServer -AgentName $Agent1 -Port 5001
    $agentProcesses += $agent1Process

    $agent2Process = Start-AgentServer -AgentName $Agent2 -Port 5002
    $agentProcesses += $agent2Process

    Wait-AgentServer -Process $agent1Process -AgentName $Agent1 -Port 5001
    Wait-AgentServer -Process $agent2Process -AgentName $Agent2 -Port 5002

    Write-Host "Launching visual game: $Agent1 vs $Agent2"
    Push-Location $repoRoot
    try {
        & $gradleWrapper :app:runVisualRemote --console=plain
        if ($LASTEXITCODE -ne 0) {
            throw "The visual game exited with code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    foreach ($process in $agentProcesses) {
        if ($null -ne $process -and -not $process.HasExited) {
            Write-Host "Stopping Python agent process $($process.Id)..."
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
        }
    }
}
