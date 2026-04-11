"""Tests for workers/state_backend.py — Gate 2 state migration layer.

LocalFileBackend uses real temp files. AzureTableBackend and
AzureBlobBackend tests stub the azure SDK at import time so the tests
run with no Azure deps installed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.state_backend import (  # noqa: E402
    AzureBlobBackend,
    AzureTableBackend,
    LocalFileBackend,
    get_backfill_backend,
    get_dispatcher_backend,
    get_pick_board_backend,
)


# ─── LocalFileBackend ───


def test_local_file_backend_returns_none_when_missing(tmp_path):
    backend = LocalFileBackend(tmp_path / "missing.json")
    assert backend.read() is None


def test_local_file_backend_round_trip(tmp_path):
    backend = LocalFileBackend(tmp_path / "state.json")
    backend.write({"hello": "world", "n": 42})
    assert backend.read() == {"hello": "world", "n": 42}


def test_local_file_backend_creates_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "state.json"
    backend = LocalFileBackend(target)
    backend.write({"a": 1})
    assert target.exists()
    assert json.loads(target.read_text()) == {"a": 1}


def test_local_file_backend_sorts_keys_for_diff_stability(tmp_path):
    backend = LocalFileBackend(tmp_path / "state.json")
    backend.write({"z": 1, "a": 2, "m": 3})
    raw = (tmp_path / "state.json").read_text()
    # Sorted keys should yield "a" before "m" before "z"
    assert raw.index('"a"') < raw.index('"m"') < raw.index('"z"')


def test_local_file_backend_returns_none_on_corrupt_json(tmp_path):
    target = tmp_path / "state.json"
    target.write_text("{not valid json")
    assert LocalFileBackend(target).read() is None


def test_local_file_backend_overwrites_existing_payload(tmp_path):
    backend = LocalFileBackend(tmp_path / "state.json")
    backend.write({"v": 1})
    backend.write({"v": 2})
    assert backend.read() == {"v": 2}


def test_local_file_backend_name():
    assert LocalFileBackend(Path("/tmp/x")).name == "local"


# ─── AzureTableBackend (stubbed SDK) ───


class _FakeTableClient:
    """In-memory stand-in for azure.data.tables.TableClient."""

    def __init__(self):
        self._rows: dict[tuple[str, str], dict] = {}

    def get_entity(self, partition_key: str, row_key: str):
        from azure.core.exceptions import ResourceNotFoundError  # type: ignore

        key = (partition_key, row_key)
        if key not in self._rows:
            raise ResourceNotFoundError(f"missing {key}")
        return dict(self._rows[key])

    def upsert_entity(self, entity: dict):
        key = (entity["PartitionKey"], entity["RowKey"])
        self._rows[key] = dict(entity)


class _FakeTableServiceClient:
    """In-memory TableServiceClient."""

    last_conn: str = ""

    def __init__(self):
        self._tables: dict[str, _FakeTableClient] = {}

    @classmethod
    def from_connection_string(cls, conn: str):
        instance = cls()
        cls.last_conn = conn
        return instance

    def create_table_if_not_exists(self, name: str):
        self._tables.setdefault(name, _FakeTableClient())

    def get_table_client(self, name: str):
        return self._tables.setdefault(name, _FakeTableClient())


@pytest.fixture
def stub_azure_tables(monkeypatch):
    """Install fake azure.data.tables + azure.core.exceptions modules in sys.modules
    so AzureTableBackend's lazy imports get the stubs instead of the real SDK."""
    fake_tables = SimpleNamespace(TableServiceClient=_FakeTableServiceClient)

    class _ResourceNotFoundError(Exception):
        pass

    fake_exceptions = SimpleNamespace(ResourceNotFoundError=_ResourceNotFoundError)
    fake_core = SimpleNamespace(exceptions=fake_exceptions)
    fake_data = SimpleNamespace(tables=fake_tables)
    fake_azure = SimpleNamespace(data=fake_data, core=fake_core, storage=None)

    monkeypatch.setitem(sys.modules, "azure", fake_azure)
    monkeypatch.setitem(sys.modules, "azure.data", fake_data)
    monkeypatch.setitem(sys.modules, "azure.data.tables", fake_tables)
    monkeypatch.setitem(sys.modules, "azure.core", fake_core)
    monkeypatch.setitem(sys.modules, "azure.core.exceptions", fake_exceptions)
    yield


def test_azure_table_backend_requires_connection_string():
    with pytest.raises(ValueError, match="connection_string"):
        AzureTableBackend(
            connection_string="",
            table_name="t",
            partition_key="p",
            row_key="r",
        )


def test_azure_table_backend_read_returns_none_when_row_missing(stub_azure_tables):
    backend = AzureTableBackend(
        connection_string="UseDevelopmentStorage=true",
        table_name="livescoutstate",
        partition_key="dispatcher",
        row_key="current",
    )
    assert backend.read() is None


def test_azure_table_backend_round_trip(stub_azure_tables):
    backend = AzureTableBackend(
        connection_string="UseDevelopmentStorage=true",
        table_name="livescoutstate",
        partition_key="dispatcher",
        row_key="current",
    )
    backend.write({"our_event": "2026txbel", "n_streams": 3})
    assert backend.read() == {"our_event": "2026txbel", "n_streams": 3}


def test_azure_table_backend_upsert_overwrites(stub_azure_tables):
    backend = AzureTableBackend(
        connection_string="UseDevelopmentStorage=true",
        table_name="livescoutstate",
        partition_key="dispatcher",
        row_key="current",
    )
    backend.write({"v": 1})
    backend.write({"v": 2, "extra": "ok"})
    assert backend.read() == {"v": 2, "extra": "ok"}


def test_azure_table_backend_isolates_partition_and_row(stub_azure_tables):
    """Two backends pointing at different (partition, row) keys should not see
    each other's writes, even when they share a table."""
    a = AzureTableBackend(
        connection_string="UseDevelopmentStorage=true",
        table_name="livescoutstate",
        partition_key="dispatcher",
        row_key="current",
    )
    b = AzureTableBackend(
        connection_string="UseDevelopmentStorage=true",
        table_name="livescoutstate",
        partition_key="dispatcher",
        row_key="other",
    )
    a.write({"id": "a"})
    b.write({"id": "b"})
    assert a.read() == {"id": "a"}
    assert b.read() == {"id": "b"}


def test_azure_table_backend_name():
    assert AzureTableBackend.name == "azure-table"


# ─── AzureBlobBackend (stubbed SDK) ───


class _FakeBlobDownload:
    def __init__(self, payload: bytes):
        self._payload = payload

    def readall(self) -> bytes:
        return self._payload


class _FakeBlobClient:
    def __init__(self, store: dict, name: str):
        self._store = store
        self._name = name

    def download_blob(self):
        from azure.core.exceptions import ResourceNotFoundError  # type: ignore

        if self._name not in self._store:
            raise ResourceNotFoundError(f"no blob {self._name}")
        return _FakeBlobDownload(self._store[self._name])

    def upload_blob(self, data, overwrite: bool = False):
        if self._name in self._store and not overwrite:
            raise RuntimeError("blob exists and overwrite=False")
        self._store[self._name] = bytes(data)


class _FakeContainerClient:
    def __init__(self):
        self._blobs: dict[str, bytes] = {}

    def create_container(self):
        # idempotent in the fake
        pass

    def get_blob_client(self, name: str):
        return _FakeBlobClient(self._blobs, name)


class _FakeBlobServiceClient:
    last_conn: str = ""
    _containers: dict[str, _FakeContainerClient] = {}

    @classmethod
    def from_connection_string(cls, conn: str):
        cls.last_conn = conn
        return cls()

    def get_container_client(self, name: str):
        return self._containers.setdefault(name, _FakeContainerClient())


@pytest.fixture
def stub_azure_blobs(monkeypatch):
    """Install fake azure.storage.blob in sys.modules."""
    # Reset the class-level container store between tests
    _FakeBlobServiceClient._containers = {}

    fake_blob = SimpleNamespace(BlobServiceClient=_FakeBlobServiceClient)

    class _ResourceNotFoundError(Exception):
        pass

    fake_exceptions = SimpleNamespace(ResourceNotFoundError=_ResourceNotFoundError)
    fake_core = SimpleNamespace(exceptions=fake_exceptions)
    fake_storage = SimpleNamespace(blob=fake_blob)
    fake_azure = SimpleNamespace(storage=fake_storage, core=fake_core)

    monkeypatch.setitem(sys.modules, "azure", fake_azure)
    monkeypatch.setitem(sys.modules, "azure.storage", fake_storage)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", fake_blob)
    monkeypatch.setitem(sys.modules, "azure.core", fake_core)
    monkeypatch.setitem(sys.modules, "azure.core.exceptions", fake_exceptions)
    yield


def test_azure_blob_backend_requires_connection_string():
    with pytest.raises(ValueError, match="connection_string"):
        AzureBlobBackend(connection_string="", container_name="c", blob_name="b")


def test_azure_blob_backend_read_returns_none_when_missing(stub_azure_blobs):
    backend = AzureBlobBackend(
        connection_string="UseDevelopmentStorage=true",
        container_name="livescoutstate",
        blob_name="pick_board.json",
    )
    assert backend.read() is None


def test_azure_blob_backend_round_trip(stub_azure_blobs):
    backend = AzureBlobBackend(
        connection_string="UseDevelopmentStorage=true",
        container_name="livescoutstate",
        blob_name="pick_board.json",
    )
    payload = {"event_key": "2026txbel", "live_matches": {"qm32": {"red_score": 42}}}
    backend.write(payload)
    assert backend.read() == payload


def test_azure_blob_backend_overwrites(stub_azure_blobs):
    backend = AzureBlobBackend(
        connection_string="UseDevelopmentStorage=true",
        container_name="livescoutstate",
        blob_name="pick_board.json",
    )
    backend.write({"v": 1})
    backend.write({"v": 2})
    assert backend.read() == {"v": 2}


def test_azure_blob_backend_isolates_blobs(stub_azure_blobs):
    a = AzureBlobBackend(
        connection_string="UseDevelopmentStorage=true",
        container_name="livescoutstate",
        blob_name="alpha.json",
    )
    b = AzureBlobBackend(
        connection_string="UseDevelopmentStorage=true",
        container_name="livescoutstate",
        blob_name="beta.json",
    )
    a.write({"who": "alpha"})
    b.write({"who": "beta"})
    assert a.read() == {"who": "alpha"}
    assert b.read() == {"who": "beta"}


def test_azure_blob_backend_name():
    assert AzureBlobBackend.name == "azure-blob"


# ─── Factories ───


def test_get_dispatcher_backend_defaults_to_local(monkeypatch, tmp_path):
    monkeypatch.delenv("STATE_BACKEND", raising=False)
    backend = get_dispatcher_backend(local_path=tmp_path / "dispatcher.json")
    assert isinstance(backend, LocalFileBackend)
    assert backend.path == tmp_path / "dispatcher.json"


def test_get_dispatcher_backend_local_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_BACKEND", "local")
    backend = get_dispatcher_backend(local_path=tmp_path / "x.json")
    assert isinstance(backend, LocalFileBackend)


def test_get_dispatcher_backend_azure_picks_table(monkeypatch):
    monkeypatch.setenv("STATE_BACKEND", "azure")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.setenv("AZURE_STATE_TABLE", "myteststate")
    backend = get_dispatcher_backend()
    assert isinstance(backend, AzureTableBackend)
    assert backend._table == "myteststate"
    assert backend._partition == "dispatcher"
    assert backend._row == "current"


def test_get_dispatcher_backend_azure_uses_default_table(monkeypatch):
    monkeypatch.setenv("STATE_BACKEND", "azure")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.delenv("AZURE_STATE_TABLE", raising=False)
    backend = get_dispatcher_backend()
    assert backend._table == "livescoutstate"


def test_get_dispatcher_backend_azure_requires_connection_string(monkeypatch):
    monkeypatch.setenv("STATE_BACKEND", "azure")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    with pytest.raises(ValueError, match="connection_string"):
        get_dispatcher_backend()


def test_get_pick_board_backend_defaults_to_local(monkeypatch, tmp_path):
    monkeypatch.delenv("STATE_BACKEND", raising=False)
    backend = get_pick_board_backend(local_path=tmp_path / "pb.json")
    assert isinstance(backend, LocalFileBackend)


def test_get_pick_board_backend_azure_picks_blob(monkeypatch):
    monkeypatch.setenv("STATE_BACKEND", "azure")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.setenv("AZURE_STATE_BLOB_CONTAINER", "myboard")
    monkeypatch.setenv("AZURE_PICK_BOARD_BLOB", "draft.json")
    backend = get_pick_board_backend()
    assert isinstance(backend, AzureBlobBackend)
    assert backend._container == "myboard"
    assert backend._blob == "draft.json"


def test_get_pick_board_backend_azure_uses_defaults(monkeypatch):
    monkeypatch.setenv("STATE_BACKEND", "azure")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.delenv("AZURE_STATE_BLOB_CONTAINER", raising=False)
    monkeypatch.delenv("AZURE_PICK_BOARD_BLOB", raising=False)
    backend = get_pick_board_backend()
    assert backend._container == "livescoutstate"
    assert backend._blob == "pick_board.json"


# ─── Backfill factory (Gate 5 / W6) ───


def test_get_backfill_backend_local_default_path(monkeypatch, tmp_path):
    """Default local backend lands under workers/.state/backfill/{season}/{event}.json."""
    monkeypatch.delenv("STATE_BACKEND", raising=False)
    backend = get_backfill_backend(event_key="2025txbel", season=2025)
    assert isinstance(backend, LocalFileBackend)
    p = str(backend.path)
    assert p.endswith("/backfill/2025/2025txbel.json")


def test_get_backfill_backend_requires_event_key():
    with pytest.raises(ValueError, match="event_key"):
        get_backfill_backend(event_key="", season=2025)


def test_get_backfill_backend_azure_uses_backfill_container(monkeypatch, stub_azure_blobs):
    monkeypatch.setenv("STATE_BACKEND", "azure")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.delenv("AZURE_BACKFILL_BLOB_CONTAINER", raising=False)
    backend = get_backfill_backend(event_key="2025txbel", season=2025)
    assert isinstance(backend, AzureBlobBackend)
    # New dedicated container by default — NOT the live state container
    assert backend._container == "livescoutbackfill"
    assert backend._blob == "backfill/2025/2025txbel.json"


def test_get_backfill_backend_azure_respects_container_override(monkeypatch, stub_azure_blobs):
    monkeypatch.setenv("STATE_BACKEND", "azure")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.setenv("AZURE_BACKFILL_BLOB_CONTAINER", "customcorpus")
    backend = get_backfill_backend(event_key="2024txhou", season=2024)
    assert backend._container == "customcorpus"
    assert backend._blob == "backfill/2024/2024txhou.json"


# ─── Discovery integration: prove the W1 worker can talk to the backend ───


def test_discovery_save_load_round_trip_through_default_backend(monkeypatch, tmp_path):
    """save_dispatcher_state + load_dispatcher_state should agree on the
    same record when both go through the same explicit local file path."""
    from workers.discovery import (
        DispatcherState,
        load_dispatcher_state,
        save_dispatcher_state,
    )

    state = DispatcherState(
        generated_at=1700000000,
        today="2026-04-11",
        our_event="2026txbel",
        our_event_name="Belton",
        active_events=["2026txbel"],
        active_streams=[],
        stream_to_event={},
    )
    target = tmp_path / "dispatcher.json"
    save_dispatcher_state(state, target)
    restored = load_dispatcher_state(target)
    assert restored is not None
    assert restored.our_event == "2026txbel"
    assert restored.generated_at == 1700000000


def test_discovery_round_trip_through_explicit_backend(tmp_path):
    """When a backend is passed explicitly, discovery should use it
    instead of the env-driven default."""
    from workers.discovery import (
        DispatcherState,
        load_dispatcher_state,
        save_dispatcher_state,
    )

    backend = LocalFileBackend(tmp_path / "explicit.json")
    state = DispatcherState(
        generated_at=42,
        today="2026-04-11",
        our_event="2026txbel",
    )
    save_dispatcher_state(state, backend=backend)
    assert (tmp_path / "explicit.json").exists()

    restored = load_dispatcher_state(backend=backend)
    assert restored is not None
    assert restored.our_event == "2026txbel"


def test_discovery_load_returns_none_when_backend_empty(tmp_path):
    from workers.discovery import load_dispatcher_state

    backend = LocalFileBackend(tmp_path / "nope.json")
    assert load_dispatcher_state(backend=backend) is None
