"""Fetch original Garmin activity FIT files via the Personal API.

The API key is exchanged for a 24 h bearer token. Tokens are cached in the
same file as Garmin's own Python client so both tools share one credential.
Downloaded FITs go into the configured FIT archive; the existing FIT importer
does the canonical write, so this module only fetches and keeps a manifest.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

import requests

from hobbyjogging_core import TrainingWriter

from .config import (
    default_garmin_dir,
    garmin_api_key,
    garmin_base_url,
    garmin_token_cache_path,
)

SOURCE = "garmin"
RECORD_TYPE = "activity-file"

_TOKEN_PATH = (
    "/personalapitoken-service/personal-api/"
    "personal-api-key/token"
)
_ACTIVITY_LIST_PATH = "/activitylist-service/activities/search/activities"
_DOWNLOAD_PATH = "/download-service/files/activity/{activity_id}"
_ZIP_ACCEPT = (
    "application/zip, application/x-zip-compressed, "
    "application/octet-stream"
)
_TOKEN_REFRESH_WINDOW_S = 60 * 60
_PAGE_SIZE = 100


class GarminApi(Protocol):

    def list_activities(self, start: date, end: date) -> list[dict]:
        ...

    def download_activity(self, activity_id: str) -> bytes:
        ...


class GarminClient:
    """Minimal Garmin Connect Personal API client."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 30,
        session=None,
        token_cache_path: str | Path | None = None,
        clock=time.time,
    ):
        key = (api_key or garmin_api_key() or "").strip()
        if not key:
            raise RuntimeError(
                "GARMIN_PERSONAL_API_KEY or GARMIN_API_KEY must be set"
            )

        self.api_key = key
        self.base_url = (base_url or garmin_base_url()).rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.token_cache_path = Path(
            token_cache_path or garmin_token_cache_path()
        ).expanduser()
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0

    def list_activities(self, start: date, end: date) -> list[dict]:
        """Return every activity summary in the inclusive date range."""
        if start > end:
            raise ValueError("start must not be after end")

        activities: list[dict] = []
        seen: set[str] = set()
        offset = 0

        while True:
            response = self._get(
                _ACTIVITY_LIST_PATH,
                params={
                    "start": offset,
                    "limit": _PAGE_SIZE,
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                },
            )
            page = response.json() if response.content else []
            if not isinstance(page, list):
                raise RuntimeError("Garmin activity list was not a JSON array")
            if not page:
                break

            added = 0
            for item in page:
                activity_id = _activity_id(item)
                if activity_id is None or activity_id in seen:
                    continue
                seen.add(activity_id)
                activities.append(item)
                added += 1

            if added == 0 or len(page) < _PAGE_SIZE:
                break
            offset += len(page)

        return activities

    def download_activity(self, activity_id: str) -> bytes:
        """Return the original activity ZIP bytes."""
        response = self._get(
            _DOWNLOAD_PATH.format(activity_id=activity_id),
            accept=_ZIP_ACCEPT,
        )
        if not response.content:
            raise RuntimeError(f"empty download for activity {activity_id}")
        return response.content

    def _get(
        self,
        path: str,
        *,
        params: dict | None = None,
        accept: str = "application/json",
        retry: bool = True,
        force_refresh: bool = False,
    ) -> requests.Response:
        token = self._bearer_token(force_refresh=force_refresh)
        response = self.session.get(
            f"{self.base_url}{path}",
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {token}",
            },
            params=params,
            timeout=self.timeout,
        )

        if response.status_code == 401 and retry:
            return self._get(
                path,
                params=params,
                accept=accept,
                retry=False,
                force_refresh=True,
            )

        if not response.ok:
            detail = str(response.text or "")[:200]
            raise RuntimeError(
                f"Garmin request {path} failed "
                f"(HTTP {response.status_code}): {detail}"
            )

        return response

    def _bearer_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh:
            if (
                self._token
                and self._token_expires_at - self._clock()
                > _TOKEN_REFRESH_WINDOW_S
            ):
                return self._token

            cached = self._read_cached_token()
            if (
                cached is not None
                and cached[1] - self._clock()
                > _TOKEN_REFRESH_WINDOW_S
            ):
                self._token, self._token_expires_at = cached
                return self._token

        return self._request_token()

    def _request_token(self) -> str:
        response = self.session.post(
            f"{self.base_url}{_TOKEN_PATH}",
            headers={
                "Accept": "*/*",
                "Authorization": f"ApiKey {self.api_key}",
            },
            timeout=self.timeout,
        )
        if not response.ok:
            detail = str(response.text or "")[:200]
            raise RuntimeError(
                "Garmin token request failed "
                f"(HTTP {response.status_code}): {detail}"
            )

        token = str(response.text or "").strip()
        if not token:
            raise RuntimeError("Garmin token response was empty")

        expires_at = _jwt_expiration(token)
        self._token = token
        self._token_expires_at = expires_at
        self._write_cached_token(token, expires_at)
        return token

    def _fingerprint(self) -> str:
        return hashlib.sha256(
            f"{self.base_url}\0{self.api_key}".encode()
        ).hexdigest()

    def _read_cached_token(self) -> tuple[str, float] | None:
        try:
            data = json.loads(self.token_cache_path.read_text("utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return None

        if not isinstance(data, dict):
            return None
        if data.get("fingerprint") != self._fingerprint():
            return None

        try:
            return str(data["access_token"]), float(data["expires_at"])
        except (KeyError, TypeError, ValueError):
            return None

    def _write_cached_token(self, token: str, expires_at: float) -> None:
        path = self.token_cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as cache_file:
            json.dump(
                {
                    "fingerprint": self._fingerprint(),
                    "access_token": token,
                    "expires_at": expires_at,
                },
                cache_file,
            )
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


@dataclass
class GarminFetchSummary:
    """Results of one Garmin fetch run."""

    run_id: int | None = None
    dry_run: bool = False
    listed: int = 0
    new: int = 0
    downloaded: int = 0
    skipped_known: int = 0
    skipped_limit: int = 0
    failed: int = 0
    fit_dir: Path | None = None
    new_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class GarminFetcher:
    """Download missing activity FITs into the archive."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        client: GarminApi | None = None,
        fit_dir: str | Path | None = None,
    ):
        self.connection = connection
        self.client = client or GarminClient()
        self.writer = TrainingWriter(connection)
        self.fit_dir = (
            Path(fit_dir).expanduser()
            if fit_dir is not None
            else default_garmin_dir()
        )

    def fetch(
        self,
        start: date,
        end: date,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        force: bool = False,
    ) -> GarminFetchSummary:
        if start > end:
            raise ValueError("start must not be after end")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than zero")

        summary = GarminFetchSummary(
            dry_run=dry_run,
            fit_dir=self.fit_dir,
        )

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "fit_dir": str(self.fit_dir) if self.fit_dir else None,
                    "limit": limit,
                    "force": force,
                },
            )

        try:
            activities = list(self.client.list_activities(start, end) or [])
            summary.listed = len(activities)

            for item in activities:
                activity_id = _activity_id(item)
                if activity_id is None:
                    summary.failed += 1
                    summary.errors.append("activity without a numeric id")
                    continue

                if not force and self._known(activity_id):
                    summary.skipped_known += 1
                    continue

                if limit is not None and summary.new >= limit:
                    summary.skipped_limit += 1
                    continue

                summary.new += 1
                summary.new_ids.append(activity_id)

                if dry_run:
                    continue

                try:
                    zip_bytes = self.client.download_activity(activity_id)
                    fit_name, fit_bytes = extract_fit(zip_bytes)
                    destination = self._destination(activity_id, fit_name)
                    _write_atomic(destination, fit_bytes)
                    self._record_manifest(
                        item,
                        activity_id,
                        destination,
                        summary.run_id,
                    )
                    summary.downloaded += 1
                except Exception as exc:
                    summary.failed += 1
                    summary.errors.append(
                        f"{activity_id}: {exc}"
                    )

            if not dry_run:
                self.writer.finish_import_run(
                    summary.run_id,
                    "partial" if summary.failed else "success",
                    records_seen=summary.listed,
                    records_imported=summary.downloaded,
                    records_skipped=(
                        summary.skipped_known + summary.skipped_limit
                    ),
                    error=(
                        "; ".join(summary.errors[:5])
                        if summary.errors
                        else None
                    ),
                )

            return summary

        except Exception as exc:
            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "failed",
                    records_seen=summary.listed,
                    records_imported=summary.downloaded,
                    records_skipped=(
                        summary.skipped_known + summary.skipped_limit
                    ),
                    error=str(exc),
                )
            raise

    def _known(self, activity_id: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1 FROM source_records
            WHERE source = ? AND record_type = ? AND external_id = ?
            """,
            (SOURCE, RECORD_TYPE, activity_id),
        ).fetchone()
        return row is not None

    def _destination(self, activity_id: str, fit_name: str) -> Path:
        suffix = Path(fit_name).suffix.lower() or ".fit"
        return self.fit_dir / f"{activity_id}{suffix}"

    def _record_manifest(
        self,
        item: dict,
        activity_id: str,
        destination: Path,
        run_id: int | None,
    ) -> None:
        payload = json.dumps(
            item,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.writer.upsert_source_record(
            source=SOURCE,
            record_type=RECORD_TYPE,
            external_id=activity_id,
            checksum=checksum,
            payload_json=payload,
            raw_path=str(destination),
            import_run_id=run_id,
        )
        self.connection.commit()


def extract_fit(zip_bytes: bytes) -> tuple[str, bytes]:
    """Return the FIT member name and bytes from a Garmin download ZIP."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("download was not a ZIP file") from exc

    with archive:
        names = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".fit")
            and not name.startswith("__MACOSX/")
        ]
        if not names:
            raise ValueError("ZIP contains no FIT file")

        preferred = [
            name
            for name in names
            if Path(name).name.endswith("_ACTIVITY.fit")
        ]
        name = (preferred or names)[0]
        data = archive.read(name)

    if not data:
        raise ValueError(f"FIT member {name} is empty")
    return name, data


def _activity_id(item: dict) -> str | None:
    value = item.get("activityId")
    if value is None:
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    return text


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _jwt_expiration(token: str) -> float:
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
        return float(claims["exp"])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "Garmin token response was not a JWT with an exp claim"
        ) from exc
