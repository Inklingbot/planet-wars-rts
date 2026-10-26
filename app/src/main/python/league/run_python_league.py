"""Run a local league using the built-in Python agents."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from league.init_db import get_default_db_path, init_db
from league.launch_python_agents import LOCAL_AGENTS, LOCAL_INSTANCE_PREFIX
from league.league_schema import AgentInstance
from league.run_agents_trueskill import main as run_agents_trueskill


def port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_agents(
    process: subprocess.Popen,
    run_id: str,
    timeout: float = 15.0,
) -> None:
    deadline = time.monotonic() + timeout
    instance_prefix = f"{LOCAL_INSTANCE_PREFIX}:{run_id}:%"
    engine = create_engine(get_default_db_path())

    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"Python agent launcher exited before becoming ready (exit code {exit_code})"
            )

        with Session(engine) as session:
            instances = (
                session.query(AgentInstance)
                .filter(AgentInstance.container_id.like(instance_prefix))
                .all()
            )
        if len(instances) == len(LOCAL_AGENTS) and all(
            port_is_listening(instance.port) for instance in instances
        ):
            print(f"Python agent launcher is ready ({len(instances)} agents).")
            return
        time.sleep(0.2)

    raise TimeoutError(f"Python agents did not become ready within {timeout:g} seconds")


def remove_local_instances(run_id: str) -> None:
    engine = create_engine(get_default_db_path())
    instance_prefix = f"{LOCAL_INSTANCE_PREFIX}:{run_id}:%"
    with Session(engine) as session:
        session.query(AgentInstance).filter(
            AgentInstance.container_id.like(instance_prefix)
        ).delete(synchronize_session=False)
        session.commit()


def main(n_pairs: int = 4) -> None:
    init_db()

    env = os.environ.copy()
    env.update(
        {
            "OMP_NUM_THREADS": "4",
            "OPENBLAS_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4",
            "NUMEXPR_NUM_THREADS": "4",
            "VECLIB_MAXIMUM_THREADS": "4",
        }
    )
    run_id = uuid.uuid4().hex
    env["PLANET_WARS_LOCAL_RUN_ID"] = run_id
    print("Launching Python agent servers...")
    python_root = Path(__file__).resolve().parents[1]
    agents_process = subprocess.Popen(
        [sys.executable, "-m", "league.launch_python_agents"],
        cwd=python_root,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env,
    )

    try:
        wait_for_agents(agents_process, run_id)
        print("Starting league run...")
        run_agents_trueskill(n_pairs)
        print("League run finished.")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        print("Stopping Python agent servers...")
        if agents_process.poll() is None:
            agents_process.terminate()
            try:
                agents_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                agents_process.kill()
                agents_process.wait(timeout=5)
        remove_local_instances(run_id)
        print("Done.")


if __name__ == "__main__":
    main()
