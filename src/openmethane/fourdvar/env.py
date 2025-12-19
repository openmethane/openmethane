"""
Setup environment variables handling
"""

import logging

from environs import Env

# TODO: replace this with util.logger once circular dependency has been resolved
logger = logging.getLogger(__name__)


def create_env():
    """
    Initialise the environment

    Loads a `.env.${TARGET}` file according to the current value of the
    TARGET environment variable.

    Any existing environment variables will take precedence over the `.env.{target}` file.
    This allows overriding of environment variables for testing purposes or to set
    different start dates.
    """
    env = Env(
        expand_vars=True,
    )

    # Load environment variables from a file
    target_env = env.str("TARGET", "nci")

    logger.info("Loading environment variables from .env.%s", target_env)
    env.read_env(f".env.{target_env}", verbose=True, override=False)
    return env


env = create_env()
