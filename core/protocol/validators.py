from typing import Any, Dict, Union
from pydantic import ValidationError

from core.protocol.schema import WorkProtocolEvent, TaskDispatchPackage, CURRENT_SCHEMA_VERSION
from core.protocol.events import ProtocolEventType


class ProtocolValidationError(Exception):
    """Raised when an event or task dispatch violates Work Protocol v1 rules."""
    def __init__(self, message: str, errors: Any = None):
        super().__init__(message)
        self.message = message
        self.errors = errors


def validate_schema_version(version: str, expected_major: str = "1") -> bool:
    """Verifies that the schema version matches the expected major release."""
    if not version or not isinstance(version, str):
        return False
    parts = version.strip().split(".")
    return len(parts) >= 1 and parts[0] == expected_major


def validate_protocol_event(data: Union[Dict[str, Any], WorkProtocolEvent]) -> WorkProtocolEvent:
    """
    Validates that an incoming dictionary or object adheres to Work Protocol v1.
    Ensures required identity fields, timestamp, schema version, and event type.
    """
    if isinstance(data, WorkProtocolEvent):
        event = data
    elif isinstance(data, dict):
        try:
            event = WorkProtocolEvent.model_validate(data)
        except ValidationError as e:
            raise ProtocolValidationError(f"Invalid Work Protocol event format: {e}", errors=e.errors())
        except Exception as e:
            raise ProtocolValidationError(f"Failed to parse Work Protocol event: {e}")
    else:
        raise ProtocolValidationError(f"Unsupported event data type: {type(data).__name__}")

    # Core identity checks
    if not event.mission_id or not event.mission_id.strip():
        raise ProtocolValidationError("Work Protocol event must include a non-empty 'mission_id'.")

    if not event.event_type or not event.event_type.strip():
        raise ProtocolValidationError("Work Protocol event must include a non-empty 'event_type'.")

    if not validate_schema_version(event.schema_version):
        raise ProtocolValidationError(
            f"Unsupported schema_version '{event.schema_version}'. Expected major version 1 (e.g. {CURRENT_SCHEMA_VERSION})."
        )

    return event


def validate_dispatch_package(data: Union[Dict[str, Any], TaskDispatchPackage]) -> TaskDispatchPackage:
    """
    Validates that a task dispatch package adheres to Work Protocol v1.
    Ensures isolation boundaries (workspace, objective, task_id, mission_id).
    """
    if isinstance(data, TaskDispatchPackage):
        pkg = data
    elif isinstance(data, dict):
        try:
            pkg = TaskDispatchPackage.model_validate(data)
        except ValidationError as e:
            raise ProtocolValidationError(f"Invalid TaskDispatchPackage format: {e}", errors=e.errors())
        except Exception as e:
            raise ProtocolValidationError(f"Failed to parse TaskDispatchPackage: {e}")
    else:
        raise ProtocolValidationError(f"Unsupported dispatch package type: {type(data).__name__}")

    if not pkg.task_id or not pkg.task_id.strip():
        raise ProtocolValidationError("TaskDispatchPackage must include a non-empty 'task_id'.")

    if not pkg.mission_id or not pkg.mission_id.strip():
        raise ProtocolValidationError("TaskDispatchPackage must include a non-empty 'mission_id'.")

    if not pkg.objective or not pkg.objective.strip():
        raise ProtocolValidationError("TaskDispatchPackage must include a non-empty 'objective'.")

    if not pkg.workspace or not pkg.workspace.strip():
        raise ProtocolValidationError("TaskDispatchPackage must include a non-empty 'workspace'.")

    if not validate_schema_version(pkg.schema_version):
        raise ProtocolValidationError(
            f"Unsupported schema_version '{pkg.schema_version}'. Expected major version 1."
        )

    return pkg
