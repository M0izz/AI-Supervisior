import asyncio
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import httpx

from integrations.jenkins.models import (
    JenkinsBuildStatus,
    JenkinsBuildOutcome,
    JenkinsBuildResult,
    JenkinsTriggerResult,
    JenkinsTestCase,
    JenkinsError,
    JenkinsConnectionError,
    JenkinsAuthError,
    JenkinsJobNotFoundError,
    JenkinsTimeoutError
)

logger = logging.getLogger("supervisor.jenkins")


class JenkinsProvider(ABC):
    """
    Abstract interface for Jenkins CI verification provider.
    Enforces independent CI execution and structured test reporting.
    """

    @abstractmethod
    async def trigger_build(
        self,
        job_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> JenkinsTriggerResult:
        """Trigger a CI build for the specified job."""
        pass

    @abstractmethod
    async def get_build_status(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> JenkinsBuildStatus:
        """Query the execution status of a build."""
        pass

    @abstractmethod
    async def get_build_result(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> JenkinsBuildResult:
        """Retrieve structured build and test verification results."""
        pass

    @abstractmethod
    async def stop_build(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> bool:
        """Stop/abort a running build."""
        pass

    @abstractmethod
    async def poll_build_completion(
        self,
        build_id: str,
        job_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        poll_interval: Optional[float] = None
    ) -> JenkinsBuildResult:
        """Poll until build finishes or timeout expires."""
        pass


class JenkinsHttpClient(JenkinsProvider):
    """
    Production Jenkins HTTP Client communicating with standard Jenkins REST API.
    Handles CSRF crumbs, queue polling, and structured JUnit test report extraction.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        job_name: Optional[str] = None,
        username: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: Optional[float] = None
    ):
        self.base_url = (url or os.getenv("JENKINS_URL", "http://localhost:8080")).rstrip("/")
        self.default_job = job_name or os.getenv("JENKINS_JOB_NAME", "ai-work-supervisor")
        self.username = username or os.getenv("JENKINS_USERNAME", "")
        self.api_token = api_token or os.getenv("JENKINS_API_TOKEN", "")
        self.timeout_seconds = float(timeout_seconds or os.getenv("JENKINS_TIMEOUT_SECONDS", "30.0"))
        self.poll_interval_seconds = float(poll_interval_seconds or os.getenv("JENKINS_POLL_INTERVAL_SECONDS", "2.0"))

    def _get_auth(self) -> Optional[httpx.BasicAuth]:
        if self.username and self.api_token:
            return httpx.BasicAuth(self.username, self.api_token)
        return None

    async def _get_crumb(self, client: httpx.AsyncClient) -> Dict[str, str]:
        """Fetch CSRF protection crumb if enabled on Jenkins."""
        try:
            crumb_url = f"{self.base_url}/crumbIssuer/api/json"
            res = await client.get(crumb_url, auth=self._get_auth())
            if res.status_code == 200:
                data = res.json()
                field = data.get("crumbRequestField")
                crumb = data.get("crumb")
                if field and crumb:
                    return {field: crumb}
        except Exception as e:
            logger.debug(f"Crumb issuer check failed or not enabled: {e}")
        return {}

    async def trigger_build(
        self,
        job_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> JenkinsTriggerResult:
        target_job = job_name or self.default_job
        auth = self._get_auth()

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            headers = await self._get_crumb(client)

            if parameters:
                endpoint = f"{self.base_url}/job/{target_job}/buildWithParameters"
                data = parameters
            else:
                endpoint = f"{self.base_url}/job/{target_job}/build"
                data = None

            try:
                res = await client.post(endpoint, auth=auth, headers=headers, data=data)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                raise JenkinsConnectionError(f"Cannot connect to Jenkins at {self.base_url}: {e}") from e
            except httpx.TimeoutException as e:
                raise JenkinsTimeoutError(f"Timeout triggering build on Jenkins: {e}") from e
            except Exception as e:
                raise JenkinsConnectionError(f"Failed to communicate with Jenkins: {e}") from e

            if res.status_code in (401, 403):
                raise JenkinsAuthError("Jenkins authentication failed. Check credentials.")
            elif res.status_code == 404:
                raise JenkinsJobNotFoundError(f"Jenkins job '{target_job}' does not exist.")
            elif res.status_code not in (200, 201):
                raise JenkinsError(f"Unexpected status triggering Jenkins build: {res.status_code}")

            location = res.headers.get("Location")
            return JenkinsTriggerResult(
                queued=True,
                job_name=target_job,
                queue_item_url=location,
                message=f"Build queued for {target_job}"
            )

    async def resolve_queue_item(self, queue_item_url: str, timeout: Optional[float] = None) -> str:
        """Resolve a queued item URL to its assigned build_id/build number."""
        cutoff = time.monotonic() + (timeout or self.timeout_seconds)
        auth = self._get_auth()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            while time.monotonic() < cutoff:
                try:
                    res = await client.get(f"{queue_item_url.rstrip('/')}/api/json", auth=auth)
                    if res.status_code == 200:
                        data = res.json()
                        executable = data.get("executable")
                        if executable and "number" in executable:
                            return str(executable["number"])
                        if data.get("cancelled"):
                            raise JenkinsError("Jenkins queue item was cancelled before build started.")
                except (JenkinsError, JenkinsAuthError):
                    raise
                except Exception as e:
                    logger.debug(f"Queue poll error: {e}")
                await asyncio.sleep(self.poll_interval_seconds)

        raise JenkinsTimeoutError("Timed out waiting for Jenkins queue item to start execution.")

    async def get_build_status(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> JenkinsBuildStatus:
        target_job = job_name or self.default_job
        auth = self._get_auth()
        url = f"{self.base_url}/job/{target_job}/{build_id}/api/json"

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                res = await client.get(url, auth=auth)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                raise JenkinsConnectionError(f"Cannot connect to Jenkins: {e}") from e
            except httpx.TimeoutException as e:
                raise JenkinsTimeoutError(f"Timeout querying Jenkins build {build_id}: {e}") from e

            if res.status_code in (401, 403):
                raise JenkinsAuthError("Authentication failure querying Jenkins build status.")
            elif res.status_code == 404:
                raise JenkinsJobNotFoundError(f"Build {build_id} not found on job {target_job}.")

            data = res.json()
            if data.get("building"):
                return JenkinsBuildStatus.RUNNING

            raw_result = data.get("result")
            if raw_result == "SUCCESS":
                return JenkinsBuildStatus.COMPLETED
            elif raw_result in ("FAILURE", "UNSTABLE"):
                return JenkinsBuildStatus.COMPLETED
            elif raw_result == "ABORTED":
                return JenkinsBuildStatus.ABORTED

            return JenkinsBuildStatus.RUNNING

    async def get_build_result(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> JenkinsBuildResult:
        target_job = job_name or self.default_job
        auth = self._get_auth()
        build_url = f"{self.base_url}/job/{target_job}/{build_id}/api/json"

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                res = await client.get(build_url, auth=auth)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                raise JenkinsConnectionError(f"Cannot connect to Jenkins: {e}") from e
            except httpx.TimeoutException as e:
                raise JenkinsTimeoutError(f"Timeout querying Jenkins build {build_id}: {e}") from e

            if res.status_code in (401, 403):
                raise JenkinsAuthError("Authentication failure querying Jenkins build result.")
            elif res.status_code == 404:
                raise JenkinsJobNotFoundError(f"Build {build_id} not found for job {target_job}.")

            build_data = res.json()
            is_building = build_data.get("building", False)
            raw_result = build_data.get("result") or ("RUNNING" if is_building else "UNKNOWN")
            duration_ms = float(build_data.get("duration", 0))

            status = JenkinsBuildStatus.RUNNING if is_building else JenkinsBuildStatus.COMPLETED
            if raw_result == "ABORTED":
                status = JenkinsBuildStatus.ABORTED

            # Map raw result to JenkinsBuildOutcome
            outcome_map = {
                "SUCCESS": JenkinsBuildOutcome.SUCCESS,
                "FAILURE": JenkinsBuildOutcome.FAILURE,
                "UNSTABLE": JenkinsBuildOutcome.UNSTABLE,
                "ABORTED": JenkinsBuildOutcome.ABORTED,
            }
            outcome = outcome_map.get(raw_result, JenkinsBuildOutcome.UNKNOWN)

            # Query structured JUnit test report
            test_report_url = f"{self.base_url}/job/{target_job}/{build_id}/testReport/api/json"
            passed = 0
            failed = 0
            skipped = 0
            test_cases: List[JenkinsTestCase] = []
            error_signature = None
            details = None

            try:
                test_res = await client.get(test_report_url, auth=auth)
                if test_res.status_code == 200:
                    tdata = test_res.json()
                    failed = tdata.get("failCount", 0)
                    passed = tdata.get("passCount", 0)
                    skipped = tdata.get("skipCount", 0)

                    # Extract failed cases for error signature
                    suites = tdata.get("suites", [])
                    for suite in suites:
                        for case in suite.get("cases", []):
                            c_status = case.get("status", "PASSED")
                            c_name = case.get("name", "test")
                            c_err = case.get("errorDetails")
                            c_trace = case.get("errorStackTrace")
                            tc = JenkinsTestCase(
                                name=c_name,
                                status=c_status,
                                duration_s=case.get("duration", 0.0),
                                error_details=c_err,
                                error_stack_trace=c_trace
                            )
                            test_cases.append(tc)
                            if c_status in ("FAILED", "REGRESSION") and not error_signature:
                                error_signature = self._extract_error_signature(c_err or c_name)
                                details = (c_err or c_name)[:200]
                else:
                    if outcome == JenkinsBuildOutcome.FAILURE:
                        failed = 1
                        error_signature = "BUILD_FAILURE"
                        details = "Pipeline failed prior to publishing test results"
                    elif outcome == JenkinsBuildOutcome.SUCCESS:
                        passed = 1
            except Exception as e:
                logger.debug(f"Failed to query test report: {e}")
                if outcome == JenkinsBuildOutcome.FAILURE:
                    failed = 1
                    error_signature = "CI_EXECUTION_FAILURE"

            return JenkinsBuildResult(
                build_id=str(build_id),
                job_name=target_job,
                status=status,
                result=outcome,
                duration_ms=duration_ms,
                tests_passed=passed,
                tests_failed=failed,
                tests_skipped=skipped,
                error_signature=error_signature,
                details=details,
                test_cases=test_cases,
                url=build_data.get("url")
            )

    async def stop_build(
        self,
        build_id: str,
        job_name: Optional[str] = None
    ) -> bool:
        target_job = job_name or self.default_job
        auth = self._get_auth()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            headers = await self._get_crumb(client)
            url = f"{self.base_url}/job/{target_job}/{build_id}/stop"
            try:
                res = await client.post(url, auth=auth, headers=headers)
                return res.status_code in (200, 302)
            except Exception as e:
                logger.error(f"Failed to stop Jenkins build {build_id}: {e}")
                return False

    async def poll_build_completion(
        self,
        build_id: str,
        job_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        poll_interval: Optional[float] = None
    ) -> JenkinsBuildResult:
        cutoff = time.monotonic() + (timeout_seconds or self.timeout_seconds)
        interval = poll_interval or self.poll_interval_seconds

        while time.monotonic() < cutoff:
            result = await self.get_build_result(build_id, job_name=job_name)
            if result.status in (JenkinsBuildStatus.COMPLETED, JenkinsBuildStatus.ABORTED):
                return result
            await asyncio.sleep(interval)

        raise JenkinsTimeoutError(f"Build {build_id} timed out after {timeout_seconds or self.timeout_seconds}s.")

    def _extract_error_signature(self, text: str) -> str:
        """Derive normalized concise error signature from error details."""
        if not text:
            return "UNKNOWN_CI_FAILURE"
        # Match typical assertion or exception names
        match = re.search(r"([A-Za-z0-9_]+Error|AssertionError|Exception):?\s*([^\n\r]+)", text)
        if match:
            sig = f"{match.group(1)}: {match.group(2).strip()[:60]}"
            return sig.replace(" ", "_").upper()
        # Clean special chars
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", text[:50]).strip("_").upper()
        return cleaned or "CI_TEST_FAILURE"
