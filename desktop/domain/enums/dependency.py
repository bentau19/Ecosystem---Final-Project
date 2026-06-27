from enum import StrEnum


class Dependency(StrEnum):
    """Required Windows components SyncDose verifies at startup.

    ``DOTNET8`` is required by the TauSync C# library (loaded via pythonnet);
    ``WINFSP`` and ``OBS`` back optional features (virtual drive, camera
    streaming). Used as the typed identifier throughout dependency detection,
    install routing, and the missing-dependencies dialog instead of raw string
    literals.
    """
    DOTNET8 = "dotnet8"
    WINFSP = "winfsp"
    OBS = "obs"
