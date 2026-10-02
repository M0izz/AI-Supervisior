import logging
import os
from typing import Any, Dict, Optional

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from integrations.jenkins.client import JenkinsProvider, JenkinsHttpClient
from integrations.jenkins.mock import MockJenkinsProvider
from integrations.jenkins.models import (
    JenkinsBuildStatus,
    JenkinsBuildOutcome,
    JenkinsBuildResult,
    JenkinsTriggerResult,
    JenkinsError,
    JenkinsConnectionError,
    JenkinsAuthError,
    JenkinsJobNotFoundError,
    JenkinsTimeoutError
)

logger = logging.getLogger("supervisor.jenkins.adapter")


class JenkinsVerificationAdapter:
    """
    Orchestrates the independent verification cycle between Jenkins CI and the Supervisor EventBus.
    Publishes CI lifecycle events, sanitizes outputs, and converts raw results to structured evidence.
    """

    def __init__(
        self,
        provider: Optional[JenkinsProvider] = None,
        event_bus: Optional[EventBus] = None,
        default_job_name: Optional[str] = None
    ):
        self.event_bus = event_bus or EventBus()
        self.default_job_name = default_job_name or os.getenv("JENKINS_JOB_NAME", "ai-work-supervisor")

        if provider:
            self.provider = provider
        else:
            jenkins_enabled = os.getenv("JENKINS_ENABLED", "false").lower() in ("true", "1", "yes")
            if jenkins_enabled:
                self.provider = JenkinsHttpClient(job_name=self.default_job_name)
            else:
                self.provider = MockJenkinsProvider()

    async def trigger_and_verify(
        self,
        mission_id: str,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        job_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[float] = None
    ) -> JenkinsBuildResult:
        """
        Trigger independent CI build, poll for completion, and emit structured events to EventBus.
        Handles connection errors, timeouts, and build failures gracefully without crashing.
        """
        target_job = job_name or self.default_job_name

        # 1. Trigger Build
        try:
            trigger_res: JenkinsTriggerResult = await self.provider.trigger_build(
                job_name=target_job,
                parameters=parameters
            )
        except JenkinsConnectionError as e:
            logger.warning(f"Jenkins connection failed: {e}")
            await self._emit_ci_event(
                event_type=EventType.CI_UNAVAILABLE,
                severity=EventSeverity.CRITICAL,
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                job_name=target_job,
                status="UNAVAILABLE",
                error=f"Jenkins server unreachable: {e}"
            )
            return JenkinsBuildResult(
                build_id="none",
                job_name=target_job,
                status=JenkinsBuildStatus.UNAVAILABLE,
                result=JenkinsBuildOutcome.UNKNOWN,
                error_signature="JENKINS_CONNECTION_ERROR",
                details=str(e)
            )
        except JenkinsAuthError as e:
            logger.error(f"Jenkins auth failure: {e}")
            await self._emit_ci_event(
                event_type=EventType.CI_UNAVAILABLE,
                severity=EventSeverity.CRITICAL,
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                job_name=target_job,
                status="UNAVAILABLE",
                error="Jenkins authentication failed"
            )
            return JenkinsBuildResult(
                build_id="none",
                job_name=target_job,
                status=JenkinsBuildStatus.UNAVAILABLE,
                result=JenkinsBuildOutcome.UNKNOWN,
                error_signature="JENKINS_AUTH_ERROR",
                details="Authentication failed"
            )
        except JenkinsTimeoutError as e:
            await self._emit_ci_event(
                event_type=EventType.CI_TIMEOUT,
                severity=EventSeverity.CRITICAL,
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                job_name=target_job,
                status="TIMEOUT",
                error="Timed out triggering Jenkins build"
            )
            return JenkinsBuildResult(
                build_id="none",
                job_name=target_job,
                status=JenkinsBuildStatus.TIMEOUT,
                result=JenkinsBuildOutcome.UNKNOWN,
                error_signature="JENKINS_TRIGGER_TIMEOUT"
            )
        except Exception as e:
            logger.error(f"Unexpected error triggering Jenkins: {e}")
            await self._emit_ci_event(
                event_type=EventType.CI_UNAVAILABLE,
                severity=EventSeverity.ERROR,
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                job_name=target_job,
                status="UNAVAILABLE",
                error=str(e)
            )
            return JenkinsBuildResult(
                build_id="none",
                job_name=target_job,
                status=JenkinsBuildStatus.UNAVAILABLE,
                result=JenkinsBuildOutcome.UNKNOWN,
                error_signature="JENKINS_UNEXPECTED_ERROR",
                details=str(e)
            )

        build_id = trigger_res.build_id or "pending"

        # Emit CI_BUILD_TRIGGERED
        await self._emit_ci_event(
            event_type=EventType.CI_BUILD_TRIGGERED,
            severity=EventSeverity.INFO,
            mission_id=mission_id,
            task_id=task_id,
            agent_id=agent_id,
            job_name=target_job,
            build_id=build_id,
            status="QUEUED"
        )

        # 2. Resolve queue item if build_id was pending
        if build_id == "pending" and trigger_res.queue_item_url and isinstance(self.provider, JenkinsHttpClient):
            try:
                build_id = await self.provider.resolve_queue_item(trigger_res.queue_item_url)
            except Exception as e:
                logger.error(f"Failed to resolve queue item to build number: {e}")
                build_id = "unknown"

        # Emit CI_BUILD_STARTED
        await self._emit_ci_event(
            event_type=EventType.CI_BUILD_STARTED,
            severity=EventSeverity.INFO,
            mission_id=mission_id,
            task_id=task_id,
            agent_id=agent_id,
            job_name=target_job,
            build_id=build_id,
            status="RUNNING"
        )

        # 3. Poll for build completion
        try:
            build_result: JenkinsBuildResult = await self.provider.poll_build_completion(
                build_id=build_id,
                job_name=target_job,
                timeout_seconds=timeout_seconds
            )
        except JenkinsTimeoutError as e:
            logger.warning(f"Jenkins build {build_id} timed out: {e}")
            await self._emit_ci_event(
                event_type=EventType.CI_TIMEOUT,
                severity=EventSeverity.CRITICAL,
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                job_name=target_job,
                build_id=build_id,
                status="TIMEOUT",
                error=str(e)
            )
            return JenkinsBuildResult(
                build_id=build_id,
                job_name=target_job,
                status=JenkinsBuildStatus.TIMEOUT,
                result=JenkinsBuildOutcome.UNKNOWN,
                error_signature="JENKINS_BUILD_TIMEOUT"
            )
        except JenkinsConnectionError as e:
            logger.warning(f"Jenkins disconnected during build polling: {e}")
            await self._emit_ci_event(
                event_type=EventType.CI_UNAVAILABLE,
                severity=EventSeverity.CRITICAL,
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                job_name=target_job,
                build_id=build_id,
                status="UNAVAILABLE",
                error=str(e)
            )
            return JenkinsBuildResult(
                build_id=build_id,
                job_name=target_job,
                status=JenkinsBuildStatus.UNAVAILABLE,
                result=JenkinsBuildOutcome.UNKNOWN,
                error_signature="JENKINS_CONNECTION_LOST"
            )

        # 4. Emit Completion and Results Available
        summary = build_result.to_concise_summary()
        summary["mission_id"] = mission_id
        summary["task_id"] = task_id
        summary["agent_id"] = agent_id

        if build_result.is_success:
            await self._emit_ci_event(
                event_type=EventType.CI_BUILD_COMPLETED,
                severity=EventSeverity.INFO,
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                job_name=target_job,
                build_id=build_id,
                status="COMPLETED",
                result="SUCCESS",
                duration_ms=build_result.duration_ms,
                tests_passed=build_result.tests_passed,
                tests_failed=build_result.tests_failed,
                tests_skipped=build_result.tests_skipped,
                details=build_result.details
            )
        else:
            await self._emit_ci_event(
                event_type=EventType.CI_BUILD_FAILED,
                severity=EventSeverity.ERROR,
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                job_name=target_job,
                build_id=build_id,
                status="COMPLETED" if build_result.status == JenkinsBuildStatus.COMPLETED else build_result.status.value,
                result=build_result.result.value,
                duration_ms=build_result.duration_ms,
                tests_passed=build_result.tests_passed,
                tests_failed=build_result.tests_failed,
                tests_skipped=build_result.tests_skipped,
                error_signature=build_result.error_signature,
                details=build_result.details
            )

        # Emit CI_TEST_RESULTS_AVAILABLE with structured test evidence
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                type=EventType.CI_TEST_RESULTS_AVAILABLE,
                severity=EventSeverity.INFO if build_result.is_success else EventSeverity.WARNING,
                payload=summary
            )
        )

        return build_result

    async def _emit_ci_event(
        self,
        event_type: EventType,
        severity: EventSeverity,
        mission_id: str,
        task_id: Optional[str],
        agent_id: Optional[str],
        job_name: str,
        status: str,
        build_id: Optional[str] = None,
        result: Optional[str] = None,
        duration_ms: Optional[float] = None,
        tests_passed: Optional[int] = None,
        tests_failed: Optional[int] = None,
        tests_skipped: Optional[int] = None,
        error_signature: Optional[str] = None,
        details: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        payload = {
            "mission_id": mission_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "job_name": job_name,
            "status": status,
        }
        if build_id:
            payload["build_id"] = build_id
        if result:
            payload["result"] = result
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if tests_passed is not None:
            payload["tests_passed"] = tests_passed
        if tests_failed is not None:
            payload["tests_failed"] = tests_failed
        if tests_skipped is not None:
            payload["tests_skipped"] = tests_skipped
        if error_signature:
            payload["error_signature"] = error_signature
        if details:
            payload["details"] = details
        if error:
            payload["error"] = error

        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                type=event_type,
                severity=severity,
                payload=payload
            )
        )
