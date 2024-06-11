"""
Setup environment variables handling
"""

from environs import Env


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

    env.read_env(f".env.{target_env}", verbose=True, override=True)
    return env


env = create_env()
