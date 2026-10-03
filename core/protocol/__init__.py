"""
Work Protocol v1 Package.
Provides typed event structures, action specifications, telemetry models,
and task dispatch packages for multi-agent interoperability.
"""

from core.protocol.events import ProtocolEventType
from core.protocol.actions import ActionType, ActionInfo, TelemetryInfo
from core.protocol.schema import (
    CURRENT_SCHEMA_VERSION,
    WorkProtocolEvent,
    TaskDispatchPackage,
    default_event_id,
    default_dispatch_id,
)
from core.protocol.validators import (
    ProtocolValidationError,
    validate_protocol_event,
    validate_dispatch_package,
    validate_schema_version,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "ProtocolEventType",
    "ActionType",
    "ActionInfo",
    "TelemetryInfo",
    "WorkProtocolEvent",
    "TaskDispatchPackage",
    "default_event_id",
    "default_dispatch_id",
    "ProtocolValidationError",
    "validate_protocol_event",
    "validate_dispatch_package",
    "validate_schema_version",
]
