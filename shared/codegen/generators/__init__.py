"""Code generators for shared enum definitions.

This package contains one module per target language. Each module must expose
a single ``generate(definition: dict[str, Any]) -> str`` function that accepts
a parsed shared/enums/*.json definition and returns fully-formed source code.

Supported generators:
    python_gen: Produces a Python StrEnum / IntEnum file.
    java_gen: Produces a Java public enum class file.
"""
