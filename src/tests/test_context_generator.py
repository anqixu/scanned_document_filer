"""Unit tests for the context generator."""

from unittest.mock import patch

import pytest

from docfiler import config as cfg
from docfiler.cli.context_generator import (
    enumerate_folder_structure,
    format_folder_info,
    generate_context,
)

from .conftest import make_config


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "docs"
    for rel in [
        "top.pdf",
        "Personal/Medical/CVS Pharmacy/rx.pdf",
        "Personal/CV/resume.pdf",
        "Work/a/b/c/deep.pdf",
        ".git/objects/x",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    return root


def test_enumerate_ignores_by_folder_name_and_depth(tree):
    structure = enumerate_folder_structure(tree, max_depth=3, ignore_patterns=[r"\.git", "CV"])
    assert structure == {
        "root": ["top.pdf"],
        "Personal/Medical/CVS Pharmacy": ["rx.pdf"],  # "CV" must not match "CVS Pharmacy"
    }
    raw = (cfg.DATA_DIR / "source_scanned_results.txt").read_text()
    assert "FILE: top.pdf" in raw and ".git" not in raw


def test_format_folder_info_respects_budget():
    structure = {f"folder{i}": [f"file{j}.pdf" for j in range(100)] for i in range(50)}
    full = format_folder_info(structure, max_files_per_dir=100, max_chars=10**9)
    assert "file99.pdf" in full

    small = format_folder_info(structure, max_files_per_dir=100, max_chars=5_000)
    assert len(small) <= 5_000
    assert "folder49/" in small  # every folder is still listed
    assert "(100 files)" in small


def test_format_folder_info_max_folders():
    structure = {f"f{i:02}": ["a"] for i in range(10)}
    text = format_folder_info(structure, max_folders=3)
    assert "f02/" in text and "f03/" not in text and "out of 10" in text


def test_generate_context_writes_output(tree, tmp_path):
    with patch("docfiler.cli.context_generator.create_client_from_config") as create:
        create.return_value.generate.return_value = "  Conventions  "
        out = tmp_path / "ctx.md"
        result = generate_context(tree, make_config(), output_path=out)
    assert result == "Conventions" and out.read_text() == "Conventions"
    prompt = create.return_value.generate.call_args.args[0]
    assert "top.pdf" in prompt


def test_generate_context_empty_dir_raises(tmp_path):
    empty = tmp_path / "empty"
    (empty / "sub").mkdir(parents=True)
    with patch("docfiler.cli.context_generator.create_client_from_config"):
        with pytest.raises(ValueError, match="No files found"):
            generate_context(empty, make_config())
