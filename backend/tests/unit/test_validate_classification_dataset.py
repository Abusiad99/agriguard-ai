"""`python -m ai.data.validate_dataset` - the read-only check of the classification dataset.

Every image here is SYNTHETIC (random noise written to pytest's temporary folder); the
repository's real dataset is never read or changed by these tests."""
from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from app.infrastructure.external import ai_pipeline_client  # noqa: F401  (puts the repo-root `ai` package on sys.path)

from ai.data import validate_dataset as vd

LFS_POINTER = (b"version https://git-lfs.github.com/spec/v1\n"
               b"oid sha256:4d7a214614ab2935c943f9e0ff69d22eadbb8f32b1258daaa5e2ca24d17e2393\nsize 12345\n")


def _image(path, seed):
    """A distinct synthetic noise image (distinct so the duplicate check keeps them apart)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = np.random.default_rng(seed).integers(0, 256, size=(48, 48, 3), dtype=np.uint8)
    Image.fromarray(pixels, "RGB").save(path, format="JPEG", quality=95)


def _dataset(root, classes, family="mycrops"):
    seed = 0
    for name, count in classes.items():
        for i in range(count):
            seed += 1
            _image(root / family / name / f"img{i}.jpg", seed)
    return root


def test_a_clean_dataset_is_usable_and_counted_per_class(tmp_path):
    root = _dataset(tmp_path, {"tomato late blight": 6, "tomato healthy": 6, "apple scab": 7})
    report = vd.check_dataset(root, full=True)
    assert report["errors"] == []
    assert report["images"] == 19 and report["images_decoded"] == 19 and report["unreadable_images"] == 0
    assert report["lfs_pointer_files"] == 0 and report["duplicate_images"] == 0
    assert report["classes"]["tomato___late_blight"]["images"] == 6
    assert report["classes"]["apple___scab"]["images"] == 7
    assert report["class_count"] == 3 and report["classes_used"] == 3 and report["plants"] == ["apple", "tomato"]
    assert not any("no 'healthy' class" in w for w in report["warnings"])   # it has a healthy class
    assert "RESULT: usable" in vd.format_report(report)


def test_git_lfs_pointers_are_an_error_with_the_fix(tmp_path):
    root = _dataset(tmp_path, {"tomato late blight": 5})
    for i in range(5):
        path = root / "mycrops" / "apple scab" / f"img{i}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(LFS_POINTER)
    report = vd.check_dataset(root)
    assert report["lfs_pointer_files"] == 5
    assert len(report["errors"]) == 1 and "git lfs pull" in report["errors"][0]
    assert report["unreadable_images"] == 0                             # pointers are reported once, as pointers
    assert "NOT USABLE" in vd.format_report(report)


def test_small_classes_missing_healthy_and_unknown_plants_are_warnings(tmp_path):
    root = _dataset(tmp_path, {"tomato late blight": 60, "apple scab": 5, "tomato leaf mold": 3,
                               "zzzfruit strange spots": 6})
    report = vd.check_dataset(root)
    assert report["errors"] == []
    assert report["classes_dropped"] == ["tomato___leaf_mold"] and report["classes_used"] == 3
    text = " | ".join(report["warnings"])
    assert "will be dropped" in text and "tomato___leaf_mold" in text
    assert "no 'healthy' class" in text
    assert "fewer than 20 images" in text and "apple___scab" in text
    assert "very unbalanced (5 to 60" in text
    assert report["unrecognised_plant_labels"] == ["zzzfruit strange spots"] and "no recognised plant" in text


def test_a_corrupted_image_is_reported_not_fatal(tmp_path):
    root = _dataset(tmp_path, {"tomato late blight": 5, "tomato healthy": 5})
    (root / "mycrops" / "tomato healthy" / "img0.jpg").write_bytes(b"this is not a jpeg")
    report = vd.check_dataset(root, full=True)
    assert report["errors"] == [] and report["unreadable_images"] == 1
    assert any("cannot be decoded" in w for w in report["warnings"])


def test_exact_duplicates_are_counted_in_full_mode_only(tmp_path):
    root = _dataset(tmp_path, {"tomato late blight": 5, "tomato healthy": 5})
    source = root / "mycrops" / "tomato healthy" / "img0.jpg"
    (root / "mycrops" / "tomato late blight" / "copy.jpg").write_bytes(source.read_bytes())
    assert vd.check_dataset(root, full=True)["duplicate_images"] == 1
    assert "duplicate_images" not in vd.check_dataset(root)             # quick mode does not read every file


@pytest.mark.parametrize("classes", [{}, {"tomato late blight": 6}])
def test_nothing_to_train_on_is_an_error(tmp_path, classes):
    root = _dataset(tmp_path, classes)
    (root / "segmentation" / "raw" / "images").mkdir(parents=True)      # other pipelines' folders are not classes
    report = vd.check_dataset(root)
    assert report["errors"], report
    assert "NOT USABLE" in vd.format_report(report)


def test_command_line_exit_code_and_json_report(tmp_path, capsys):
    good = _dataset(tmp_path / "good", {"tomato late blight": 5, "tomato healthy": 5})
    out = tmp_path / "out" / "report.json"
    assert vd.main(["--datasets-dir", str(good), "--json-out", str(out)]) == 0
    assert "RESULT: usable" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["classes"]["tomato___healthy"]["images"] == 5
    assert vd.main(["--datasets-dir", str(tmp_path / "missing")]) == 1
    assert "NOT USABLE" in capsys.readouterr().out


def test_the_check_never_writes_into_the_dataset(tmp_path):
    root = _dataset(tmp_path, {"tomato late blight": 5, "tomato healthy": 5})
    before = sorted((p.relative_to(root).as_posix(), p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*"))
    vd.check_dataset(root, full=True)
    assert sorted((p.relative_to(root).as_posix(), p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*")) == before
