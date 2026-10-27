"""Dramatiq broker bootstrap.

Imported at the bottom of ``config.settings`` so every process (web,
``dramatiq`` worker, ``manage.py crontab`` scheduler) shares one broker
before any actor module loads. Reads env vars directly — no settings
import — to stay circular-import free.

DRAMATIQ_BROKER selects the broker: "redis" (default) or "stub" (tests).
"""

import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker


def setup_broker():
    name = os.getenv("DRAMATIQ_BROKER", "redis")
    if name == "stub":
        from dramatiq.brokers.stub import StubBroker

        dramatiq.set_broker(StubBroker())
        return
    dramatiq.set_broker(
        RedisBroker(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
        )
    )


setup_broker()
