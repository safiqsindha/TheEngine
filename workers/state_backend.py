#!/usr/bin/env python3
"""
The Engine — Live Scout State Backend
Team 2950 — The Devastators

Single abstraction over the two pieces of mutable state Live Scout
needs to persist between cron ticks:

  1. Dispatcher state — small JSON record produced by W1 (workers/discovery.py)
     and consumed by every other worker on each tick. Lives in
     `workers/.state/dispatcher.json` locally; in Azure it lives as a
     single row in an Azure Storage Table (cheap, transactional, fast
     small-record reads).

  2. Pick board state — the larger JSON the alliance-draft tool reads/writes
     and that Live Scout workers append `live_matches` into. Lives in
     `~/.scout/state.json` locally; in Azure it lives as one Blob in
     Azure Storage Blob (no row-size limits, JSON-friendly).

The backend selection is driven entirely by environment variables so
the same `python -m workers.mode_a` invocation works locally on a laptop
and inside an Azure Container Apps Job with zero code changes:

  STATE_BACKEND=local             → LocalFileBackend (default)
  STATE_BACKEND=azure             → Azure Table + Blob
  AZURE_STORAGE_CONNECTION_STRING → required when STATE_BACKEND=azure
  AZURE_STATE_TABLE               → table name (default: livescoutstate)
  AZURE_STATE_BLOB_CONTAINER      → blob container (default: livescoutstate)
  AZURE_PICK_BOARD_BLOB           → blob name (default: pick_board.json)
  AZURE_BACKFILL_BLOB_CONTAINER   → backfill blob container (default: livescoutbackfill)
  AZURE_BRIEF_BLOB                → synthesis brief blob name
                                    (default: brief_<event_key>.json)

Backfill namespace isolation (Gate 5 / W6):
  The backfill worker writes one state document per (season, event_key)
  tuple, strictly segregated from live dispatcher / pick_board state.
  Locally this lives under `workers/.state/backfill/{season}/{event_key}.json`;
  in Azure it lives in a dedicated container `livescoutbackfill` at
  `backfill/{season}/{event_key}.json`. The factory is
  `get_backfill_backend(event_key=..., season=...)`.

Lazy SDK imports: `azure-data-tables` and `azure-storage-blob` are only
imported on first use so this module is import-safe in dev environments
that haven't installed the Azure SDK yet (e.g. local laptops, CI, or
the existing pytest suite).

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §Gate 2 migration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Protocol

# ─── Protocol ───


class JsonStateBackend(Protocol):
    """A read/write store for one JSON document."""

    name: str

    def read(self) -> Optional[dict[str, Any]]:
        """Return the stored document, or None if nothing has been written yet."""
        ...

    def write(self, state: dict[str, Any]) -> None:
        """Persist the document. Overwrites any prior contents."""
        ...


# ─── Local file backend ───


class LocalFileBackend:
    """Reads/writes a single JSON document to a local file path.

    Used by default in development, in tests, and as the fallback when
    `STATE_BACKEND` is unset. Mirrors the pre-Gate-2 disk shape exactly
    so swapping a workflow between local and azure is just an env flip.
    """

    name = "local"

    def __init__(self, path: Path):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> Optional[dict[str, Any]]:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text())
        except json.JSONDecodeError:
            return None

    def write(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state, indent=2, sort_keys=True))


# ─── Azure Storage Table backend ───


class AzureTableBackend:
    """Stores one JSON document as a single row in an Azure Storage Table.

    Storage Tables are cheap (~$0.045/GB/month), have ~5ms read latency
    for single-row lookups, and let us read/write the dispatcher state
    transactionally without managing a database. The row stores the
    serialized JSON in a single string property.

    Lazy SDK import: `azure-data-tables` is imported on first read/write
    so this class is safe to construct in environments that don't have
    the Azure SDK installed yet.
    """

    name = "azure-table"
    JSON_PROPERTY = "json_payload"

    def __init__(
        self,
        connection_string: str,
        table_name: str,
        partition_key: str,
        row_key: str,
    ):
        if not connection_string:
            raise ValueError("AzureTableBackend requires a connection_string")
        self._conn = connection_string
        self._table = table_name
        self._partition = partition_key
        self._row = row_key
        self._client: Any = None  # lazy

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        # Lazy import — only fails if Azure backend is actually used
        from azure.data.tables import TableServiceClient

        service = TableServiceClient.from_connection_string(self._conn)
        # create_table_if_not_exists is idempotent and cheap
        try:
            service.create_table_if_not_exists(self._table)
        except Exception:
            # Race conditions on first deploy are fine — table exists.
            pass
        self._client = service.get_table_client(self._table)
        return self._client

    def read(self) -> Optional[dict[str, Any]]:
        from azure.core.exceptions import ResourceNotFoundError

        client = self._get_client()
        try:
            entity = client.get_entity(
                partition_key=self._partition,
                row_key=self._row,
            )
        except ResourceNotFoundError:
            return None

        payload = entity.get(self.JSON_PROPERTY)
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def write(self, state: dict[str, Any]) -> None:
        client = self._get_client()
        entity = {
            "PartitionKey": self._partition,
            "RowKey": self._row,
            self.JSON_PROPERTY: json.dumps(state, sort_keys=True),
        }
        # upsert_entity is idempotent — overwrite-or-insert in one call
        client.upsert_entity(entity=entity)


# ─── Azure Storage Blob backend ───


class AzureBlobBackend:
    """Stores one JSON document as a Blob in an Azure Storage container.

    Used for the larger pick_board state document (no row-size cap, easy
    to download for offline debugging). Lazy SDK import: `azure-storage-blob`
    is only imported on first read/write.
    """

    name = "azure-blob"

    def __init__(
        self,
        connection_string: str,
        container_name: str,
        blob_name: str,
    ):
        if not connection_string:
            raise ValueError("AzureBlobBackend requires a connection_string")
        self._conn = connection_string
        self._container = container_name
        self._blob = blob_name
        self._client: Any = None  # lazy

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient.from_connection_string(self._conn)
        container = service.get_container_client(self._container)
        try:
            container.create_container()
        except Exception:
            # Already exists or race — fine.
            pass
        self._client = container.get_blob_client(self._blob)
        return self._client

    def read(self) -> Optional[dict[str, Any]]:
        from azure.core.exceptions import ResourceNotFoundError

        client = self._get_client()
        try:
            data = client.download_blob().readall()
        except ResourceNotFoundError:
            return None
        if not data:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    def write(self, state: dict[str, Any]) -> None:
        client = self._get_client()
        payload = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
        client.upload_blob(payload, overwrite=True)


# ─── Factories ───


_DEFAULT_DISPATCHER_LOCAL_PATH = Path(__file__).parent / ".state" / "dispatcher.json"
_DEFAULT_PICK_BOARD_LOCAL_PATH = Path.home() / ".scout" / "state.json"
_DEFAULT_BACKFILL_LOCAL_ROOT = Path(__file__).parent / ".state" / "backfill"
_DEFAULT_ANOMALY_LOCAL_PATH = Path(__file__).parent / ".state" / "mode_c_anomaly.json"
_DEFAULT_DIGEST_LOCAL_DIR = Path(__file__).parent / ".state" / "digests"
_DEFAULT_BRIEF_LOCAL_DIR = Path(__file__).parent / ".state" / "briefs"
_DEFAULT_DISCORD_DEDUPE_LOCAL_PATH = Path(__file__).parent / ".state" / "discord_dedupe.json"


def _selected_backend() -> str:
    """Return the active backend identifier ('local' or 'azure')."""
    return os.environ.get("STATE_BACKEND", "local").lower()


def get_dispatcher_backend(
    *,
    local_path: Optional[Path] = None,
) -> JsonStateBackend:
    """Return the configured dispatcher state backend.

    Defaults to LocalFileBackend at workers/.state/dispatcher.json. If
    `STATE_BACKEND=azure`, returns an AzureTableBackend keyed at
    (PartitionKey='dispatcher', RowKey='current') in
    AZURE_STATE_TABLE (default 'livescoutstate').
    """
    if _selected_backend() == "azure":
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        table = os.environ.get("AZURE_STATE_TABLE", "livescoutstate")
        return AzureTableBackend(
            connection_string=conn,
            table_name=table,
            partition_key="dispatcher",
            row_key="current",
        )
    return LocalFileBackend(local_path or _DEFAULT_DISPATCHER_LOCAL_PATH)


def get_pick_board_backend(
    *,
    local_path: Optional[Path] = None,
) -> JsonStateBackend:
    """Return the configured pick board state backend.

    Defaults to LocalFileBackend at ~/.scout/state.json. If
    `STATE_BACKEND=azure`, returns an AzureBlobBackend at
    AZURE_STATE_BLOB_CONTAINER/AZURE_PICK_BOARD_BLOB
    (defaults: container 'livescoutstate', blob 'pick_board.json').
    """
    if _selected_backend() == "azure":
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        container = os.environ.get("AZURE_STATE_BLOB_CONTAINER", "livescoutstate")
        blob_name = os.environ.get("AZURE_PICK_BOARD_BLOB", "pick_board.json")
        return AzureBlobBackend(
            connection_string=conn,
            container_name=container,
            blob_name=blob_name,
        )
    return LocalFileBackend(local_path or _DEFAULT_PICK_BOARD_LOCAL_PATH)


def get_backfill_backend(
    *,
    event_key: str,
    season: int,
    local_path: Optional[Path] = None,
) -> JsonStateBackend:
    """Return a backfill-namespaced state backend for one (season, event_key).

    Gate 5 / W6 writes one document per historical event. The namespace
    is kept completely separate from live dispatcher and pick_board state
    so a long-running backfill job cannot pollute the live draft tool.

    Local layout:
        workers/.state/backfill/{season}/{event_key}.json

    Azure layout:
        container = AZURE_BACKFILL_BLOB_CONTAINER (default "livescoutbackfill")
        blob name = backfill/{season}/{event_key}.json

    The container defaults to a NEW container ("livescoutbackfill"), not
    the live state container, so backfill data can be managed (lifecycle
    policies, deletion, cold storage) independently of live state.
    """
    if not event_key:
        raise ValueError("get_backfill_backend requires an event_key")
    if not isinstance(season, int):
        raise ValueError("get_backfill_backend requires an integer season")

    if _selected_backend() == "azure":
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        container = os.environ.get(
            "AZURE_BACKFILL_BLOB_CONTAINER", "livescoutbackfill",
        )
        blob_name = f"backfill/{season}/{event_key}.json"
        return AzureBlobBackend(
            connection_string=conn,
            container_name=container,
            blob_name=blob_name,
        )

    if local_path is None:
        local_path = _DEFAULT_BACKFILL_LOCAL_ROOT / str(season) / f"{event_key}.json"
    return LocalFileBackend(local_path)


def get_anomaly_backend(
    *,
    local_path: Optional[Path] = None,
) -> JsonStateBackend:
    """Return the configured Mode C anomaly state backend.

    Stores per-event score stats + cursors used by W4 (mode_c_anomaly).
    Defaults to LocalFileBackend at workers/.state/mode_c_anomaly.json.
    If `STATE_BACKEND=azure`, returns an AzureBlobBackend at
    AZURE_STATE_BLOB_CONTAINER/AZURE_ANOMALY_BLOB
    (defaults: container 'livescoutstate', blob 'mode_c_anomaly.json').
    """
    if _selected_backend() == "azure":
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        container = os.environ.get("AZURE_STATE_BLOB_CONTAINER", "livescoutstate")
        blob_name = os.environ.get("AZURE_ANOMALY_BLOB", "mode_c_anomaly.json")
        return AzureBlobBackend(
            connection_string=conn,
            container_name=container,
            blob_name=blob_name,
        )
    return LocalFileBackend(local_path or _DEFAULT_ANOMALY_LOCAL_PATH)


def get_digest_backend(
    event_key: str,
    *,
    local_path: Optional[Path] = None,
) -> JsonStateBackend:
    """Return the configured digest blob backend for a specific event.

    Written by W5 (mode_c_event_end). One blob per event so digests from
    different events don't clobber each other. Local default is
    workers/.state/digests/digest_<event_key>.json. In Azure,
    AZURE_DIGEST_BLOB (default: `digest_<event_key>.json`) lives in
    AZURE_STATE_BLOB_CONTAINER (default: 'livescoutstate').
    """
    if _selected_backend() == "azure":
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        container = os.environ.get("AZURE_STATE_BLOB_CONTAINER", "livescoutstate")
        blob_name = os.environ.get(
            "AZURE_DIGEST_BLOB", f"digest_{event_key}.json"
        )
        return AzureBlobBackend(
            connection_string=conn,
            container_name=container,
            blob_name=blob_name,
        )
    if local_path is None:
        local_path = _DEFAULT_DIGEST_LOCAL_DIR / f"digest_{event_key}.json"
    return LocalFileBackend(local_path)


def get_brief_backend(
    event_key: str,
    *,
    local_path: Optional[Path] = None,
) -> JsonStateBackend:
    """Return the configured synthesis-brief backend for a specific event.

    Written by T3 (workers/synthesis_worker.py). One blob per event so
    briefs from different events don't clobber each other. Local default
    is workers/.state/briefs/brief_<event_key>.json. In Azure,
    AZURE_BRIEF_BLOB (default: `brief_<event_key>.json`) lives in
    AZURE_STATE_BLOB_CONTAINER (default: 'livescoutstate').
    """
    if not event_key:
        raise ValueError("get_brief_backend requires an event_key")
    if _selected_backend() == "azure":
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        container = os.environ.get("AZURE_STATE_BLOB_CONTAINER", "livescoutstate")
        blob_name = os.environ.get(
            "AZURE_BRIEF_BLOB", f"brief_{event_key}.json"
        )
        return AzureBlobBackend(
            connection_string=conn,
            container_name=container,
            blob_name=blob_name,
        )
    if local_path is None:
        local_path = _DEFAULT_BRIEF_LOCAL_DIR / f"brief_{event_key}.json"
    return LocalFileBackend(local_path)


def get_discord_dedupe_backend(
    *,
    local_path: Optional[Path] = None,
) -> JsonStateBackend:
    """Return the configured Discord dedupe state backend.

    Stores a `{"seen": [dedupe_key, ...]}` document so cron retries of
    mode_a / mode_c workers don't double-post the same alert. Local
    default is workers/.state/discord_dedupe.json. In Azure, lives in
    AZURE_STATE_BLOB_CONTAINER/AZURE_DISCORD_DEDUPE_BLOB
    (defaults: container 'livescoutstate', blob 'discord_dedupe.json').
    """
    if _selected_backend() == "azure":
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        container = os.environ.get("AZURE_STATE_BLOB_CONTAINER", "livescoutstate")
        blob_name = os.environ.get("AZURE_DISCORD_DEDUPE_BLOB", "discord_dedupe.json")
        return AzureBlobBackend(
            connection_string=conn,
            container_name=container,
            blob_name=blob_name,
        )
    return LocalFileBackend(local_path or _DEFAULT_DISCORD_DEDUPE_LOCAL_PATH)
