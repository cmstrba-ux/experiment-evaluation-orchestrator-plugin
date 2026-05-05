import hashlib
import subprocess
from pathlib import Path

def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def test_rerender_is_byte_identical(tmp_path):
    # Run render.py twice on the same sample fixture, hash output, compare.
    out1 = tmp_path / "report1.html"
    out2 = tmp_path / "report2.html"
    cmd = ["python", "-m", "scripts.lib.render", "--run-dir", "fixtures/sample_run", "--out"]
    subprocess.run(cmd + [str(out1)], check=True)
    subprocess.run(cmd + [str(out2)], check=True)
    assert _hash(out1) == _hash(out2), "Re-render not idempotent"
