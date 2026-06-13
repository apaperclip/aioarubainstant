from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from aioarubainstant import (
    ArubaAccessPoint,
    ArubaClient,
    ArubaCluster,
    ArubaInstantSnapshot,
)


def test_models_are_immutable_and_preserve_absent_fields() -> None:
    cluster = ArubaCluster(name="office")
    access_point = ArubaAccessPoint(name="lobby")
    client = ArubaClient(mac="aa:bb:cc:dd:ee:ff")
    snapshot = ArubaInstantSnapshot(
        cluster=cluster,
        access_points=(access_point,),
        clients=(client,),
        _raw_output={"show summary": "sanitized"},
    )

    assert cluster.management_address is None
    assert access_point.serial is None
    assert client.hostname is None
    raw_output = object.__getattribute__(snapshot, "_raw_output")
    assert raw_output["show summary"] == "sanitized"

    with pytest.raises(FrozenInstanceError):
        cluster.name = "changed"  # type: ignore[misc]

    with pytest.raises(TypeError):
        raw_output["show summary"] = "changed"
