"""The input catalogue and the check before a log is read."""

import hashlib

import pytest

from wise.evaluation import data


def test_catalogue_names_the_three_logs_with_identity_and_hash():
    catalogue = data.catalogue()
    assert [d["id"] for d in catalogue["datasets"]] == ["bpic2019", "bpic2013_incidents", "bpic2017"]
    for entry in catalogue["datasets"]:
        assert entry["identifier"].startswith("https://doi.org/10.4121/")
        assert len(entry["file"]["sha256"]) == 64 and int(entry["file"]["sha256"], 16) >= 0
        assert entry["file"]["bytes"] > 0
        assert "redistribut" in entry["redistribution"]
    assert data.entry("bpic2019")["file"] == {
        "name": "BPI_Challenge_2019.csv",
        "bytes": 527457189,
        "sha256": "7d592fb425690d13011d1b874fe2af63f61a66acfc368ecf87b4ed266e6cdb00",
        "rows": 1595923,
        "encoding": "cp1252",
        "timestamp_format": "%d-%m-%Y %H:%M:%S.%f",
    }
    with pytest.raises(KeyError):
        data.entry("bpic2099")


def test_a_log_is_found_by_name_and_read_only_with_the_recorded_checksum(tmp_path, monkeypatch):
    content = b"case,activity\n1,a\n"
    fake = {
        "id": "tiny",
        "file": {"name": "Tiny_Log.csv", "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()},
    }
    monkeypatch.setattr(data, "catalogue", lambda: {"datasets": [fake]})
    with pytest.raises(data.DataNotAvailable, match="not in the data folder"):
        data.locate("tiny", tmp_path)
    assert data.available("tiny", tmp_path) is False
    nested = tmp_path / "some" / "sub folder"
    nested.mkdir(parents=True)
    (nested / "tiny_log.CSV").write_bytes(content)  # found by name, whatever its case and depth
    assert data.locate("tiny", tmp_path).name == "tiny_log.CSV"
    assert data.available("tiny", tmp_path) is True
    assert data.verify(tmp_path)[0]["status"] == "verified"
    other = tmp_path / "other"
    other.mkdir()
    (other / "Tiny_Log.csv").write_bytes(content + b"2,b\n")
    with pytest.raises(data.DataMismatch, match="SHA-256"):
        data.locate("tiny", other)
    assert data.verify(other)[0]["status"] == "found with another size or checksum"


def test_the_data_folder_comes_from_the_argument_or_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv(data.DATA_ENVIRONMENT, raising=False)
    with pytest.raises(data.DataNotAvailable, match=data.DATA_ENVIRONMENT):
        data.data_folder()
    monkeypatch.setenv(data.DATA_ENVIRONMENT, str(tmp_path))
    assert data.data_folder() == tmp_path
    assert data.data_folder(tmp_path / ".") == tmp_path / "."
    with pytest.raises(data.DataNotAvailable, match="does not exist") as caught:
        data.data_folder(tmp_path / "missing")
    assert str(tmp_path) not in str(caught.value)  # a message never shows a path of the machine
    assert data.main(["--data", str(tmp_path)]) == 1
