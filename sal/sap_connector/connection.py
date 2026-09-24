"""Thin wrapper around pyrfc.Connection for a single named SAP system profile.

Kept deliberately small: this module is the only place in SAL that talks to
pyrfc directly, so later collectors (SM20, SM19, ...) depend on this
abstraction rather than on pyrfc itself.
"""
from __future__ import annotations

from .. import config  # noqa: F401  (import side effect: sets PATH/SAPNWRFC_HOME)

import pyrfc


class SapConnectionError(RuntimeError):
    pass


class SapConnection:
    def __init__(self, system_id: str):
        self.system_id = system_id
        self._params = config.sap_system_config(system_id)
        self._conn: pyrfc.Connection | None = None

    def __enter__(self) -> "SapConnection":
        try:
            self._conn = pyrfc.Connection(
                ashost=self._params["ashost"],
                sysnr=self._params["sysnr"],
                client=self._params["client"],
                user=self._params["user"],
                passwd=self._params["passwd"],
            )
        except pyrfc.RFCError as exc:
            raise SapConnectionError(
                f"Failed to connect to SAP system '{self.system_id}': {exc}"
            ) from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def ping(self) -> bool:
        if self._conn is None:
            raise SapConnectionError("Not connected")
        self._conn.ping()
        return True

    def call(self, function_name: str, **kwargs):
        if self._conn is None:
            raise SapConnectionError("Not connected")
        try:
            return self._conn.call(function_name, **kwargs)
        except pyrfc.RFCError as exc:
            raise SapConnectionError(
                f"RFC call '{function_name}' failed on system '{self.system_id}': {exc}"
            ) from exc
