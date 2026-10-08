# AI Work Supervisor — Phase 6: Jenkins CI/CD Verification Layer

## 1. Architectural Philosophy

> **Worker completion is not verification.**

Autonomous agents may prematurely declare tasks complete, omit edge cases, or hallucinate passing test outputs. The **AI Work Supervisor** enforces that worker completion is treated solely as an unverified claim.

Independent verification evaluates test assertions, file scope boundaries, git worktree diffs, completion criteria, and regressions. When connected, an external continuous integration system—**Jenkins CI**—acts as an authoritative CI evidence source. Jenkins executes against the resulting workspace code, runs the test suite, generates structured test reports (e.g., JUnit XML via pytest), and emits structured telemetry to the central `EventBus`.

```text
                    HUMAN
                      |
                      v
                   MISSION
                      |
                      v
                    WORKER
                      |
                      v
            DOCKER / LOCAL SANDBOX
                      |
                      v
                WORKSPACE CODE
                      |
                      v
                   JENKINS
                      |
          +-----------+-----------+
          |           |           |
        BUILD       TEST        LINT
          |           |           |
          +-----------+-----------+
                      |
                      v
                  CI RESULT
                      |
                      v
                  EVENT BUS
                      |
                      v
                 SUPERVISOR
                      |
          +-----------+-----------+
          |           |           |
       ACCEPT      RECOVER      ESCALATE
    (-> Verifier) (-> Reviewer) (-> Operator)
```

---

## 2. Decoupled Provider Abstraction

The Jenkins integration layer (`integrations/jenkins/`) is cleanly decoupled from HTTP implementation details:

- **`JenkinsProvider` (ABC)**:
  - `trigger_build(job_name, parameters) -> JenkinsTriggerResult`
  - `get_build_status(build_id, job_name) -> JenkinsBuildStatus`
  - `get_build_result(build_id, job_name) -> JenkinsBuildResult`
  - `stop_build(build_id, job_name) -> bool`
  - `poll_build_completion(build_id, job_name, timeout, interval) -> JenkinsBuildResult`

- **`JenkinsHttpClient`**:
  - Interacts with standard Jenkins REST API (`/job/{job_name}/build`, `/queue/item/{id}/api/json`, `/job/{job_name}/{id}/api/json`, `/job/{job_name}/{id}/testReport/api/json`).
  - Supports CSRF crumb issuance (`/crumbIssuer/api/json`).
  - Implements Basic Auth with API tokens.
  - Sanitizes credentials; never logs tokens.
  - Resolves queued items into build numbers.
  - Parses JUnit test reports into structured pass/fail/skip counts and failure signatures.

- **`MockJenkinsProvider`**:
  - Deterministic simulation for tests and offline development without needing a live Jenkins server.
  - Simulates `SUCCESS`, `FAILURE`, `ABORTED`, `TIMEOUT`, and `UNAVAILABLE`.
  - Supports `DYNAMIC_WORKSPACE` mode, which inspects the actual workspace files (`src/parser.py`) to confirm whether genuine fixes (such as UTF-8 BOM stripping) have been applied.

- **`JenkinsVerificationAdapter`**:
  - Bridges the provider to `EventBus` and `SupervisorEngine`.
  - Emits normalized CI lifecycle events: `CI_BUILD_TRIGGERED`, `CI_BUILD_STARTED`, `CI_BUILD_COMPLETED`, `CI_BUILD_FAILED`, `CI_TEST_RESULTS_AVAILABLE`, `CI_UNAVAILABLE`, `CI_TIMEOUT`.

---

## 3. Configuration & Environment Variables

Configure Jenkins integration via `.env`:

```env
# Phase 6: Jenkins CI Integration
JENKINS_ENABLED=false
JENKINS_URL=http://localhost:8080
JENKINS_JOB_NAME=ai-work-supervisor
JENKINS_USERNAME=
JENKINS_API_TOKEN=
JENKINS_TIMEOUT_SECONDS=30
JENKINS_POLL_INTERVAL_SECONDS=2
```

### Security & Secret Protection
- `JENKINS_API_TOKEN` is loaded strictly from environment configuration.
- Tokens are never logged, committed to git, emitted in `Event` payloads, or sent to LLMs (Nemotron).
- If `JENKINS_ENABLED=false` (the default), `MockJenkinsProvider` is automatically used for deterministic offline execution.

---

## 4. Pipeline & Structured Test Reports

The repository root includes an independent `Jenkinsfile`:

```groovy
pipeline {
    agent any
    stages {
        stage('Environment Validation') { ... }
        stage('Install Dependencies') { ... }
        stage('Static Checks') { ... }
        stage('Independent Verification Tests') {
            steps {
                sh 'python -m pytest tests/ --junitxml=test-results.xml -v'
            }
        }
    }
    post {
        always {
            junit testResults: 'test-results.xml', allowEmptyResults: true
        }
    }
}
```

Jenkins extracts structured JUnit test reports (`testReport/api/json`):
- `tests_passed`, `tests_failed`, `tests_skipped`
- `error_signature` (e.g. `CSV_HEADER_MISMATCH_BOM`)
- Test case breakdown without arbitrary unstructured console scraping.

---

## 5. Supervisor CI Flow & Failure Modes

When an agent claims task completion:

```text
Worker COMPLETE (Claim)
        |
        v
Jenkins CI Pipeline
        |
        +---- PASS ----> VerifierAgent (Empirical confirmation)
        |                      |
        |                      v
        |                Supervisor (Mark VERIFIED)
        |
        +---- FAIL ----> SupervisorEngine (CI_FAILURE Anomaly)
                               |
                               +--> Reopen Task in TaskManager
                               +--> Actively Pause Worker
                               +--> Nemotron Structured Decision
                               +--> DELEGATE -> ReviewerAgent
                               +--> Project Memory Update
                               +--> Worker Resumes with Context
```

### Failure Modes & Safe State Handling:
1. **Jenkins Unavailable (`CI_UNAVAILABLE`)**:
   - Emitted when Jenkins server is unreachable or offline.
   - Supervisor enters `INVESTIGATING` / `PAUSED`. Worker is paused. Task remains unverified.
2. **Jenkins Timeout (`CI_TIMEOUT`)**:
   - Emitted when build polling exceeds `JENKINS_TIMEOUT_SECONDS`.
   - Task remains unverified.
3. **CI Build Failure (`CI_BUILD_FAILED`)**:
   - Compilation error, script failure, or static check failure.
   - Task reopened; supervisor triggers anomaly pipeline.
4. **CI Test Failure (`tests_failed > 0`)**:
   - Contradicts worker claim. Task reopened; worker paused; Nemotron invoked for targeted delegation.
5. **CI Success (`CI_BUILD_COMPLETED`)**:
   - Pipeline passed. Supervisor hands off to `VerifierAgent` for final empirical confirmation before task is marked completed.

---

## 6. Docker & Container Isolation Relationship

In Phase 5, agents execute in ephemeral Docker containers (`DockerExecutionProvider`) or local subprocess jail (`LocalExecutionProvider`).

### Interaction Boundary:
- **Worker in Docker**: The worker executes tools (edits files, runs local scratch checks) inside the isolated container mounting `/workspace`.
- **Jenkins CI Boundary**: Jenkins operates as an external, independent execution environment. It clones or accesses the verified workspace code without requiring access to the host Docker daemon socket (`/var/run/docker.sock`), strictly avoiding container escape vulnerabilities.
- **Independence Principle**: Jenkins has its own runner, dependencies, and environment, preventing agents from tampering with test runners or falsifying exit codes.

---

## 7. Running the CI Failure Scenario

The dedicated killer scenario (`demo/scenarios/scenario_02_ci_failure.py`) demonstrates the complete false-completion recovery loop:

### Local / Mock Mode (Default):
```bash
python demo/scenarios/scenario_02_ci_failure.py
```

### Real Jenkins Mode (Requires running Jenkins server):
```bash
JENKINS_ENABLED=true python demo/scenarios/scenario_02_ci_failure.py
```

---

## 8. Real Jenkins Setup Instructions

To connect AI Work Supervisor to a live Jenkins instance:

1. **Install Jenkins**:
   ```bash
   docker run -p 8080:8080 -p 50000:50000 -v jenkins_home:/var/jenkins_home jenkins/jenkins:lts
   ```
2. **Create API Token**:
   - Go to Jenkins > **Manage Jenkins** > **Users** > Select User > **Configure**.
   - Under **API Token**, generate a new token and copy it.
3. **Create Pipeline Job**:
   - Create a new Pipeline job named `ai-work-supervisor`.
   - Point the pipeline definition to Pipeline script from SCM (or paste `Jenkinsfile`).
4. **Configure `.env`**:
   ```env
   JENKINS_ENABLED=true
   JENKINS_URL=http://localhost:8080
   JENKINS_JOB_NAME=ai-work-supervisor
   JENKINS_USERNAME=admin
   JENKINS_API_TOKEN=<your_token>
   ```
5. **Run Verification**:
   ```bash
   python demo/scenarios/scenario_02_ci_failure.py
   ```

---

## 9. Limitations & Scope

- **Job Parameterization**: Current implementation supports standard Git/workspace checkouts and parameter dictionaries. Multi-branch matrix setups can be added in future extensions.
- **Artifact Archival**: Retains test result XML and structured metrics; full console logs are queried on demand but not dumped into EventStore to avoid bloat.
