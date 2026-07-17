from pathlib import Path


def test_only_cli_owns_process_boundary():
    package = Path(__file__).parents[1] / "src" / "crypto_analyser"
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if path.name == "cli.py":
            assert source.count("def main(") == 1
            continue
        assert "def main(" not in source, path
        assert "import argparse" not in source, path
        assert "import subprocess" not in source, path
        assert "if __name__" not in source, path
