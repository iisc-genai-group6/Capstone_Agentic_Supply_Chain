from __future__ import annotations

import warnings


_GRADIO_STARLETTE_MESSAGES = (
    r".*HTTP_422_UNPROCESSABLE_ENTITY.*deprecated.*",
    r".*HTTP_413_REQUEST_ENTITY_TOO_LARGE.*deprecated.*",
    r".*HTTP_414_REQUEST_URI_TOO_LONG.*deprecated.*",
    r".*HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE.*deprecated.*",
)


def suppress_known_dependency_warnings() -> None:
    for message in _GRADIO_STARLETTE_MESSAGES:
        warnings.filterwarnings("ignore", message=message, category=Warning)
