"""Standalone scoring service: python -m scoring.server --port 8766."""

import argparse
import asyncio
import json

from websockets import serve
from client_server.util import strip_type_field
from core.game_state import GameParams, GameState
from .evaluators import Comparison, DEFAULT_CONFIG


class ScoringService:
    def __init__(self, comparison: Comparison):
        self.comparison = comparison

    def respond(self, request: dict) -> dict:
        if request.get("type") == "describe":
            return {"status": "ok", "metadata": self.comparison.metadata}
        if request.get("type") != "score":
            raise ValueError("Unknown request type")
        if request.get("configHash") != self.comparison.metadata["configHash"]:
            raise ValueError("Scoring configuration changed; start a new game or restore the original config")
        state = GameState.model_validate(strip_type_field(request["state"]))
        params = GameParams.model_validate(strip_type_field(request["params"]))
        if state.game_tick != request["tick"]:
            raise ValueError("Request tick does not match the board state")
        if not request.get("gameId") or not request.get("requestId"):
            raise ValueError("gameId and requestId are required")
        return {"status": "ok", "gameId": request["gameId"], "tick": state.game_tick,
                "requestId": request["requestId"], "configHash": self.comparison.metadata["configHash"],
                **self.comparison.score(state, params)}

    async def handler(self, websocket, path=None):
        async for message in websocket:
            try:
                request = json.loads(message)
                response = await asyncio.to_thread(self.respond, request)
            except Exception as error:
                response = {"status": "error", "error": str(error)}
            await websocket.send(json.dumps(response, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    comparison = Comparison.load(args.config)  # Validate before accepting connections.
    service = ScoringService(comparison)

    async def run():
        async with serve(service.handler, "127.0.0.1", args.port, max_size=8 * 1024 * 1024):
            print(f"Scoring service running on ws://127.0.0.1:{args.port}", flush=True)
            print(json.dumps(comparison.metadata), flush=True)
            await asyncio.Future()
    asyncio.run(run())


if __name__ == "__main__":
    main()
