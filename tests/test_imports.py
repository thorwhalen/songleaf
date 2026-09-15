import subprocess
import sys

HEAVY = ("sung", "pandas", "reportlab", "cw", "rapidfuzz", "dol")


def test_importing_songleaf_loads_no_heavy_dependency():
    code = (
        "import sys, songleaf, songleaf.tools, songleaf.render, songleaf.sources, "
        "songleaf.store, songleaf.parse, songleaf.model; "
        f"print(sorted(set({HEAVY!r}) & set(sys.modules)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
