import subprocess
import sys

import pytest

# Imports the module with os.environ replaced by a mapping that records every
# read, and an audit hook recording every file opened that isn't Python code.
# Third-party packages are imported first, since what they read on import
# (urllib3 reads SSLKEYLOGFILE) is outside openmethane's control.
CHECK_IMPORT = """
import importlib, json, os, sys
import attrs, requests, urllib3

class RecordingEnviron(dict):
    reads = []
    def __getitem__(self, key):
        self.reads.append(key)
        return super().__getitem__(key)
    def get(self, key, default=None):
        self.reads.append(key)
        return super().get(key, default)
    def __contains__(self, key):
        self.reads.append(key)
        return super().__contains__(key)

opened = []
def audit(event, args):
    if event == "open" and isinstance(args[0], str):
        if not args[0].endswith((".py", ".pyc", ".so", ".pth")) and not os.path.isdir(args[0]):
            opened.append(args[0])

os.environ = RecordingEnviron(os.environ)
sys.addaudithook(audit)
importlib.import_module(sys.argv[1])
print(json.dumps({"env": RecordingEnviron.reads, "files": opened}))
"""


@pytest.mark.parametrize(
    "module",
    (
        "openmethane.util.process",
        "openmethane.util.download",
        "openmethane.util.logging",
        "openmethane.util.decomposition",
    ),
)
def test_importing_a_shared_utility_reads_no_environment_or_files(module):
    result = subprocess.run(
        [sys.executable, "-c", CHECK_IMPORT, module],  # noqa: S603
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == '{"env": [], "files": []}', result.stderr
