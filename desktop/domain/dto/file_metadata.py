import dataclasses


@dataclasses.dataclass()
class FileMetadataDTO:
    name: str
    size: int
