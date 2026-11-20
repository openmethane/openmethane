import json
import subprocess
import sys

import pytest

# Modules that read no configuration on import, so any part of the project can
# import them. A module listed here stays importable without setting up the
# environment that the older fourdvar modules need.
MODULES = (
    "openmethane.util.process",
    "openmethane.util.download",
    "openmethane.util.logging",
    "openmethane.util.decomposition",
    "openmethane.wrf.config",
    "openmethane.wrf.geometry",
    "openmethane.wrf.install",
    "openmethane.wrf.mpi",
    "openmethane.wrf.namelists",
    "openmethane.wrf.outputs",
    "openmethane.wrf.windows",
)

# Imports the module with os.environ replaced by a mapping that records every
# read, and an audit hook recording every file opened that isn't Python code.
# Third-party packages are imported first, since what they read on import
# (urllib3 reads SSLKEYLOGFILE, and importlib.resources seeds `random` from
# /dev/urandom) is outside openmethane's control. Run it with
# -B, or a checkout with no bytecode cache records the .pyc files it writes.
CHECK_IMPORT = """
import importlib, importlib.resources, json, os, sys
import attrs, f90nml, requests, urllib3, yaml

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


@pytest.mark.parametrize("module", MODULES)
def test_importing_the_module_reads_no_environment_or_files(module):
    result = subprocess.run(
        [sys.executable, "-B", "-c", CHECK_IMPORT, module],  # noqa: S603
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == '{"env": [], "files": []}', result.stderr


def test_the_check_reports_a_module_that_reads_environment_and_files(tmp_path):
    # A module that does on import what the listed modules must not, so a
    # check that has stopped recording anything can't pass the test above.
    (tmp_path / "settings.txt").write_text("")
    (tmp_path / "reads_on_import.py").write_text(
        "import os, pathlib\n"
        "os.getenv('PROBE_VARIABLE')\n"
        "pathlib.Path(__file__).with_name('settings.txt').read_text()\n"
    )

    result = subprocess.run(
        [sys.executable, "-B", "-c", CHECK_IMPORT, "reads_on_import"],  # noqa: S603
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    assert json.loads(result.stdout) == {
        "env": ["PROBE_VARIABLE"],
        "files": [str(tmp_path / "settings.txt")],
    }, result.stderr
