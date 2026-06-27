import dataclasses

from domain.enums.dependency import Dependency


@dataclasses.dataclass(frozen=True)
class DependencyInfoDTO:
    """View-facing description of a single required Windows component.

    Built by :class:`~services.dependency.DependencyService` for each
    component it detects as missing and rendered by
    :class:`~views.widgets.dialogs.missing_dependencies_dialog.MissingDependenciesDialog`.
    Carries everything the dialog needs so the view never branches on raw
    dependency identifiers.

    Attributes:
        dependency:   Typed identifier of the component.
        display_name: Human-readable label, e.g. ".NET 8 Runtime".
        description:  One-line explanation of why the component is needed.
        required:     When ``True`` the app cannot run without it (.NET 8). The
                      dialog withholds the "continue without installing" option
                      while any required component is missing.
    """

    dependency: Dependency
    display_name: str
    description: str
    required: bool
