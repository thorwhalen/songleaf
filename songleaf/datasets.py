"""Where the ``datasets`` data kind lives: local files by default, S3 by configuration.

The corpus files (``chords-and-lyrics/...``) are addressed by their path relative
to the ``datasets`` kind. ADR-0024 makes the S3 key mirror the local layout, so a
store over disk (``dol.Files``) and a store over S3 (``s3dol``) hold the same
relative keys, and :func:`dataset_path` is the one place that turns a key into a
real file (SQLite and zip readers need one).

Configuration (environment; ``SONGLEAF_DATA_DIR`` always wins, so a pinned local
root is never overridden by S3):

- ``SONGLEAF_DATASETS_URI``: ``s3://bucket/prefix`` of the ``datasets`` kind
  (for example ``s3://tw-apps/thorwhalen/songleaf/datasets``). Unset means local.
- ``SONGLEAF_S3_PROFILE``: the AWS profile to read with (optional).
- ``SONGLEAF_CACHE_DIR``: where S3 objects are cached (default
  ``~/.cache/songleaf/datasets``).
"""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from songleaf.store import DATA_DIR_ENVVAR, data_dir

DATASETS_URI_ENVVAR = "SONGLEAF_DATASETS_URI"
S3_PROFILE_ENVVAR = "SONGLEAF_S3_PROFILE"
CACHE_DIR_ENVVAR = "SONGLEAF_CACHE_DIR"
_S3 = "s3"


@dataclass(frozen=True)
class S3Location:
    bucket: str
    prefix: str  # ends with "/" (or is empty)
    profile: str | None = None


def s3_location(environ=None) -> S3Location | None:
    """The configured S3 home of the datasets, or ``None`` when they are local.

    >>> s3_location({"SONGLEAF_DATASETS_URI": "s3://b/x/datasets"})
    S3Location(bucket='b', prefix='x/datasets/', profile=None)
    >>> s3_location({"SONGLEAF_DATASETS_URI": "s3://b/x", "SONGLEAF_DATA_DIR": "/d"})
    >>> s3_location({})
    """
    env = os.environ if environ is None else environ
    uri = env.get(DATASETS_URI_ENVVAR)
    if not uri or env.get(DATA_DIR_ENVVAR):
        return None
    parsed = urlparse(uri)
    if parsed.scheme != _S3 or not parsed.netloc:
        raise ValueError(f"{DATASETS_URI_ENVVAR} must look like s3://bucket/prefix, not {uri!r}")
    prefix = parsed.path.strip("/")
    return S3Location(
        parsed.netloc, prefix + "/" if prefix else "", env.get(S3_PROFILE_ENVVAR) or None
    )


def datasets_store(*, location: S3Location | None = None, readonly: bool = True):
    """The ``datasets`` kind as a ``MutableMapping[str, bytes]`` keyed by relative path.

    ``dol.Files`` over the local folder unless S3 is configured (or ``location``
    is given), then ``s3dol`` (the ``s3`` extra).
    """
    location = location or s3_location()
    if location is None:
        from dol import Files

        return Files(data_dir("datasets"))
    from s3dol import s3_store

    return s3_store(
        location.bucket, prefix=location.prefix, profile=location.profile, readonly=readonly
    )


def _cache_dir() -> str:
    return os.environ.get(CACHE_DIR_ENVVAR) or os.path.join(
        os.path.expanduser("~"), ".cache", "songleaf", "datasets"
    )


def dataset_path(key: str, *, location: S3Location | None = None) -> str:
    """The path of a real file for the dataset ``key`` (relative path), cached if remote.

    Local: ``<data root>/datasets/<key>`` (it may not exist). On S3: the object is
    downloaded once to the cache (a missing object leaves no file, so the path
    does not exist) and the cached path is returned; an object whose size changed
    on S3 is fetched again.
    """
    location = location or s3_location()
    if location is None:
        return os.path.join(data_dir("datasets"), *key.split("/"))
    path = os.path.join(_cache_dir(), *key.split("/"))
    store = datasets_store(location=location)
    client, s3_key = store.client, location.prefix + key
    try:
        remote_size = client.head_object(Bucket=location.bucket, Key=s3_key)["ContentLength"]
    except client.exceptions.ClientError:
        return path  # absent on S3: callers test os.path.isfile, as for a local path
    if not (os.path.isfile(path) and os.path.getsize(path) == remote_size):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        part = f"{path}.{os.getpid()}.part"  # moved into place when whole
        try:
            client.download_file(location.bucket, s3_key, part)
            os.replace(part, path)
        finally:
            if os.path.exists(part):
                os.remove(part)
    return path
