"""The datasets kind resolves through a store: local by default, S3 by configuration."""

import os

import pytest

from songleaf import datasets
from songleaf.datasets import S3Location, dataset_path, datasets_store, s3_location


def test_local_is_the_default(tmp_path, monkeypatch):
    monkeypatch.delenv(datasets.DATASETS_URI_ENVVAR, raising=False)
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))
    (tmp_path / "datasets" / "c").mkdir(parents=True)
    (tmp_path / "datasets" / "c" / "f.txt").write_bytes(b"hi")
    assert datasets_store()["c/f.txt"] == b"hi"
    assert dataset_path("c/f.txt") == str(tmp_path / "datasets" / "c" / "f.txt")


def test_data_dir_wins_over_s3(tmp_path, monkeypatch):
    monkeypatch.setenv(datasets.DATASETS_URI_ENVVAR, "s3://b/p")
    monkeypatch.setenv("SONGLEAF_DATA_DIR", str(tmp_path))
    assert s3_location() is None


def test_bad_uri():
    with pytest.raises(ValueError):
        s3_location({datasets.DATASETS_URI_ENVVAR: "http://b/p"})


class _Client:
    """A boto3 client stand-in holding one object."""

    class exceptions:
        ClientError = KeyError

    def __init__(self, objects):
        self.objects, self.downloads = objects, 0

    def head_object(self, *, Bucket, Key):
        return {"ContentLength": len(self.objects[Key])}

    def download_file(self, bucket, key, dest):
        self.downloads += 1
        with open(dest, "wb") as f:
            f.write(self.objects[key])


def test_s3_path_is_cached_and_refetched_on_size_change(tmp_path, monkeypatch):
    client = _Client({"pre/c/f.bin": b"abc"})

    class _Store:
        pass

    _Store.client = client
    monkeypatch.setattr(datasets, "datasets_store", lambda **kw: _Store)
    monkeypatch.setenv(datasets.CACHE_DIR_ENVVAR, str(tmp_path))
    loc = S3Location("b", "pre/")
    path = dataset_path("c/f.bin", location=loc)
    assert open(path, "rb").read() == b"abc"
    dataset_path("c/f.bin", location=loc)
    assert client.downloads == 1
    client.objects["pre/c/f.bin"] = b"abcdef"
    dataset_path("c/f.bin", location=loc)
    assert open(path, "rb").read() == b"abcdef"
    assert not os.path.exists(dataset_path("c/missing", location=loc))
