"""
Setup environment variables handling
"""

import logging

from environs import Env

logger = logging.getLogger(__name__)


def create_env():
    """
    Initialise the environment

    Loads a .env file according to the current value of TARGET
    """
    env = Env(
        expand_vars=True,
    )

    # Load environment variables from a file
    target_env = env.str("TARGET", "nci")

    logger.info("Loading environment variables from .env.%s", target_env)
    env.read_env(f".env.{target_env}", verbose=True, override=True)
    return env


env = create_env()
