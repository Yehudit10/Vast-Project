import sys
import types
from pathlib import Path

from core import model_io


def test_load_labels_from_csv_with_index_and_display_name(tmp_path: Path):
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text(
        "index,name,display_name\n"
        "1,dog,Dog\n"
        "0,engine,Engine\n", encoding="utf-8"
    )
    labels = model_io.load_labels_from_csv(str(csv_path))
    # Sorted by 'index' -> [Engine, Dog] -> display_name preferred
    assert labels == ["Engine", "Dog"]


def test_load_audioset_labels_from_pkg_via_fake_pkg(tmp_path: Path, monkeypatch):
    # Create fake package with resources/class_labels_indices.csv
    pkg_dir = tmp_path / "fake_pkg"
    res_dir = pkg_dir / "resources"
    res_dir.mkdir(parents=True)

    csv_path = res_dir / "class_labels_indices.csv"
    csv_path.write_text(
        "index,name,display_name\n"
        "0,animal,Animal\n"
        "1,vehicle,Vehicle\n", encoding="utf-8"
    )

    # Fake module panns_inference with a file path inside pkg_dir
    fake_mod = types.ModuleType("panns_inference")
    # `inspect.getfile(panns_inference)` will use module.__file__
    fake_mod.__file__ = str(pkg_dir / "__init__.py")
    sys.modules["panns_inference"] = fake_mod

    labels = model_io.load_audioset_labels_from_pkg()
    assert labels == ["Animal", "Vehicle"]
