import asyncio
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from gps_tracker.api import health


def test_health_endpoint():
    response = asyncio.run(health())
    assert response == {"status": "ok"}
