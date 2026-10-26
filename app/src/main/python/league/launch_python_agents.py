"""Launch and register the built-in Python agents for local league play."""

from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass
from datetime import datetime
from typing import Type

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from agents.one_trick_agent import OneTrickAgent
from agents.planet_wars_agent import PlanetWarsPlayer
from agents.random_agents import CarefulRandomAgent, PureRandomAgent
from client_server.game_agent_server import GameServerAgent
from league.init_db import get_default_db_path
from league.league_schema import Agent, AgentInstance, Base


LOCAL_INSTANCE_PREFIX = "local-python"
LOCAL_REPO_URL = "local://built-in-python-agents"


@dataclass(frozen=True)
class LocalAgentSpec:
    name: str
    agent_type: Type[PlanetWarsPlayer]


LOCAL_AGENTS = (
    LocalAgentSpec("Python Pure Random", PureRandomAgent),
    LocalAgentSpec("Python Careful Random", CarefulRandomAgent),
    LocalAgentSpec("Python Greedy Heuristic", GreedyHeuristicAgent),
    LocalAgentSpec("Python One Trick", OneTrickAgent),
)


def find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def register_agents(
    specs_and_ports: list[tuple[LocalAgentSpec, int]],
    db_url: str | None = None,
    run_id: str | None = None,
) -> None:
    engine = create_engine(db_url or get_default_db_path())
    Base.metadata.create_all(engine)
    run_id = run_id or str(os.getpid())

    with Session(engine) as session:
        for spec, port in specs_and_ports:
            agent = (
                session.query(Agent)
                .filter_by(name=spec.name, commit="working-tree")
                .first()
            )
            if agent is None:
                agent = Agent(
                    name=spec.name,
                    owner="local",
                    repo_url=LOCAL_REPO_URL,
                    commit="working-tree",
                    created_at=datetime.now(),
                )
                session.add(agent)
                session.flush()
            else:
                agent.owner = "local"
                agent.repo_url = LOCAL_REPO_URL

            instance = session.get(AgentInstance, agent.agent_id)
            container_id = f"{LOCAL_INSTANCE_PREFIX}:{run_id}:{spec.name}"
            if instance is None:
                session.add(
                    AgentInstance(
                        agent_id=agent.agent_id,
                        port=port,
                        container_id=container_id,
                        last_seen=datetime.now(),
                    )
                )
            else:
                instance.port = port
                instance.container_id = container_id
                instance.last_seen = datetime.now()

        session.commit()


async def wait_until_listening(
    port: int,
    server_task: asyncio.Task,
    timeout: float = 10.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if server_task.done():
            server_task.result()
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError(f"Python agent server on port {port} did not start")


async def main() -> None:
    ports: list[int] = []
    while len(ports) < len(LOCAL_AGENTS):
        port = find_free_port()
        if port not in ports:
            ports.append(port)
    specs_and_ports = list(zip(LOCAL_AGENTS, ports))
    tasks = [
        asyncio.create_task(
            GameServerAgent(
                host="127.0.0.1",
                port=port,
                agent=spec.agent_type(),
            ).start(),
            name=spec.name,
        )
        for spec, port in specs_and_ports
    ]

    try:
        await asyncio.gather(
            *(
                wait_until_listening(port, task)
                for (_spec, port), task in zip(specs_and_ports, tasks)
            )
        )
        register_agents(
            specs_and_ports,
            run_id=os.environ.get("PLANET_WARS_LOCAL_RUN_ID"),
        )
        print(f"LOCAL_PYTHON_AGENTS_READY={len(specs_and_ports)}", flush=True)
        for spec, port in specs_and_ports:
            print(f"  {spec.name}: ws://127.0.0.1:{port}", flush=True)
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
