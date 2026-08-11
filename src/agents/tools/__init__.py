from importlib import import_module
from typing import Any

from .BaseTool import BaseTool
from .OpenMeteoClient import (
    LocationNotFoundError,
    OpenMeteoClient,
    describe_wmo_weather_code,
)
from .SendEmailTool import EmailDeliveryGateway, SendEmailTool
from .ToolRegistry import ToolRegistry


_LAZY_IMPORTS = {
    "SearchProjectChunksTool": (
        ".SearchProjectChunksTool",
        "SearchProjectChunksTool",
    ),
    "ListProjectAssetsTool": (
        ".ListProjectAssetsTool",
        "ListProjectAssetsTool",
    ),
    "SearchAssetsByNameTool": (
        ".SearchAssetsByNameTool",
        "SearchAssetsByNameTool",
    ),
    "GetAssetDetailsTool": (
        ".GetAssetDetailsTool",
        "GetAssetDetailsTool",
    ),
    "ReadAssetTool": (
        ".ReadAssetTool",
        "ReadAssetTool",
    ),
    "RequestClarificationTool": (
        ".RequestClarificationTool",
        "RequestClarificationTool",
    ),
    "GetCurrentTimeTool": (
        ".GetCurrentTimeTool",
        "GetCurrentTimeTool",
    ),
    "GetCurrentWeatherTool": (
        ".GetCurrentWeatherTool",
        "GetCurrentWeatherTool",
    ),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_IMPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = target
    value = getattr(
        import_module(module_name, __name__),
        attribute_name,
    )
    globals()[name] = value
    return value


__all__ = [
    "BaseTool",
    "ToolRegistry",
    "SearchProjectChunksTool",
    "ListProjectAssetsTool",
    "SearchAssetsByNameTool",
    "GetAssetDetailsTool",
    "ReadAssetTool",
    "RequestClarificationTool",
    "GetCurrentTimeTool",
    "GetCurrentWeatherTool",
    "LocationNotFoundError",
    "OpenMeteoClient",
    "describe_wmo_weather_code",
    "EmailDeliveryGateway",
    "SendEmailTool",
]
