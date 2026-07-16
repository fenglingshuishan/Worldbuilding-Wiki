class WorldbuildingWikiError(Exception):
    """Base class for expected application errors."""


class VaultError(WorldbuildingWikiError):
    """The requested vault operation is invalid."""


class ValidationError(WorldbuildingWikiError):
    """Content failed domain validation."""


class ConflictError(WorldbuildingWikiError):
    """Content changed since the caller last read it."""


class TransferError(WorldbuildingWikiError):
    """An import or export could not be safely completed."""
