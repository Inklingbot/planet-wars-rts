import asyncio

from client_server.game_agent_server import GameServerAgent
from agents.one_trick_agent import OneTrickAgent 

asyncio.run(
    GameServerAgent(
        port=8765,
        agent=OneTrickAgent(),
    ).start()
)
