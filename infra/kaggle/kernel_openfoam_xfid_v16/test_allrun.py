import subprocess
import tempfile
from pathlib import Path


ALLRUN = Path(__file__).with_name("case_template") / "Allrun"


def _mock_case(tmp_path: Path, checkmesh_output: str, *, checkmesh_exit: int = 1, surface_exit: int = 0):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "calls"
    for command in ("blockMesh", "snappyHexMesh", "simpleFoam"):
        marker = "echo simpleFoam >> \"$CALL_LOG\"" if command == "simpleFoam" else f"echo {command} >> \"$CALL_LOG\""
        (bin_dir / command).write_text(f"#!/bin/bash\n{marker}\nexit 0\n")
    (bin_dir / "surfaceFeatureExtract").write_text(f"#!/bin/bash\necho surfaceFeatureExtract >> \"$CALL_LOG\"\nexit {surface_exit}\n")
    (bin_dir / "checkMesh").write_text(
        "#!/bin/bash\ncat <<'EOF'\n" + checkmesh_output + "\nEOF\nexit " + str(checkmesh_exit) + "\n"
    )
    for path in bin_dir.iterdir():
        path.chmod(0o755)
    return bin_dir, call_log


def test_allrun_allows_only_registered_concave_exit_and_runs_solver():
    valid = "cells: 100\n***Concave cells (using face planes) found, number of cells: 7\nFailed 1 mesh checks."
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bin_dir, call_log = _mock_case(root, valid)
        result = subprocess.run(["bash", str(ALLRUN)], cwd=root, env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CALL_LOG": str(call_log)}, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert "simpleFoam" in call_log.read_text()


def test_allrun_rejects_nonconcave_mesh_failure_before_solver():
    invalid = "cells: 100\n***Face area check failed\nFailed 1 mesh checks."
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bin_dir, call_log = _mock_case(root, invalid)
        result = subprocess.run(["bash", str(ALLRUN)], cwd=root, env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CALL_LOG": str(call_log)}, capture_output=True, text=True)
        assert result.returncode != 0
        assert "simpleFoam" not in call_log.read_text()


def test_allrun_rejects_multiple_failed_check_markers_before_solver():
    invalid = "cells: 100\n***Concave cells (using face planes) found, number of cells: 7\nFailed 1 mesh checks.\nFailed 2 mesh checks."
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bin_dir, call_log = _mock_case(root, invalid)
        result = subprocess.run(["bash", str(ALLRUN)], cwd=root, env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CALL_LOG": str(call_log)}, capture_output=True, text=True)
        assert result.returncode != 0
        assert "simpleFoam" not in call_log.read_text()


def test_allrun_propagates_surface_feature_extract_failure():
    valid = "cells: 100\n***Concave cells (using face planes) found, number of cells: 7\nFailed 1 mesh checks."
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bin_dir, call_log = _mock_case(root, valid, surface_exit=2)
        result = subprocess.run(["bash", str(ALLRUN)], cwd=root, env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CALL_LOG": str(call_log)}, capture_output=True, text=True)
        assert result.returncode == 2
        assert "simpleFoam" not in call_log.read_text()
