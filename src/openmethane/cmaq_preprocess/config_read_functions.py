import json


def load_json(filepath: str) -> dict[str, str | int | float]:
    """
    Loads and parses JSON data from a file.

    Parameters
    ----------
    filepath
        The path to the JSON file to load.

    Returns
    -------
        The parsed JSON data.
    """

    with open(filepath) as f:
        config = json.load(f)

    return config
