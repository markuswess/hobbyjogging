"""Minimal Intervals.icu API client used by the importer."""

import os
from datetime import date
from typing import Protocol

import requests


class IntervalsApi(Protocol):

    def activities(self, start: date, end: date) -> list[dict]:
        ...

    def wellness(self, start: date, end: date) -> list[dict]:
        ...

    def events(self, start: date, end: date) -> list[dict]:
        ...

    def activity(self, activity_id: str) -> dict:
        ...

    def activity_intervals(self, activity_id: str) -> list[dict]:
        ...


class IntervalsClient:
    """Read raw Intervals.icu payloads."""

    def __init__(
        self,
        athlete_id: str | None = None,
        api_key: str | None = None,
        timeout: int = 20,
    ):
        self.athlete_id = athlete_id or os.environ.get("INTERVALS_ATHLETE_ID")
        self.api_key = api_key or os.environ.get("INTERVALS_API_KEY")
        if not self.athlete_id or not self.api_key:
            raise RuntimeError(
                "INTERVALS_ATHLETE_ID and INTERVALS_API_KEY must be set"
            )

        self.timeout = timeout
        self.auth = ("API_KEY", self.api_key)
        self.base = (
            "https://intervals.icu/api/v1/athlete/"
            f"{self.athlete_id}"
        )

    def _get(self, endpoint: str, params: dict | None = None) -> object:
        response = requests.get(
            f"{self.base}/{endpoint}",
            auth=self.auth,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def activities(self, start: date, end: date) -> list[dict]:
        return self._get(
            "activities",
            {"oldest": start.isoformat(), "newest": end.isoformat()},
        )

    def wellness(self, start: date, end: date) -> list[dict]:
        return self._get(
            "wellness",
            {"oldest": start.isoformat(), "newest": end.isoformat()},
        )

    def events(self, start: date, end: date) -> list[dict]:
        return self._get(
            "events",
            {"oldest": start.isoformat(), "newest": end.isoformat()},
        )

    def activity(self, activity_id: str) -> dict:
        response = requests.get(
            f"https://intervals.icu/api/v1/activity/{activity_id}",
            auth=self.auth,
            params={"intervals": "true"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def activity_intervals(self, activity_id: str) -> list[dict]:
        return self.activity(activity_id).get("icu_intervals") or []
