"""Two suites, deliberately separate.

The tests beside this file are the rules: they import the pure modules
directly and need nothing but pytest, so they run anywhere in under a
second. The ones in ``integration`` run against a real Home Assistant and
need ``requirements_test.txt`` installed. Where that is missing, they are
skipped rather than failing the suite, so the fast path keeps working on
a machine with nothing set up.
"""

import sys
from importlib.util import find_spec
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# The pure modules import nothing from the package, so they can be
# imported by name once their directory is on the path.
sys.path.insert(0, str(_ROOT / "custom_components" / "ma_curated_radio"))
# The repository root, so the integration tests can import the component
# as custom_components.ma_curated_radio, the way Home Assistant does.
sys.path.insert(0, str(_ROOT))

collect_ignore_glob = []
if find_spec("pytest_homeassistant_custom_component") is None:
    collect_ignore_glob.append("integration/*")
