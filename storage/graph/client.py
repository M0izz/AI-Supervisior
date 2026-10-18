"""
FalkorDB Client & Connection Management.
Provides resilient, authenticated connection handling and health diagnostics.
"""

from dataclasses import dataclass
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("supervisor.storage.graph.client")


class FalkorDBUnavailableError(RuntimeError):
    """Raised when FalkorDB graph store is disconnected, unreachable, or inoperable."""
    pass


@dataclass
class FalkorDBConfig:
    host: str = "localhost"
    port: int = 6379
    username: Optional[str] = None
    password: Optional[str] = None
    graph_name: str = "ai_supervisor_memory"
    timeout: float = 10.0
    ssl: bool = False
    url: Optional[str] = None

    @classmethod
    def from_env(cls) -> "FalkorDBConfig":
        from urllib.parse import urlparse

        url_env = os.getenv("FALKORDB_URL") or None
        url_user = None
        url_pass = None
        url_host = None
        url_port = None
        url_ssl = False

        if url_env:
            try:
                parsed = urlparse(url_env)
                url_user = parsed.username
                url_pass = parsed.password
                url_host = parsed.hostname
                url_port = parsed.port
                url_ssl = parsed.scheme in ("falkors", "rediss")
            except Exception:
                pass

        # Discrete environment variables take precedence if explicitly set,
        # but URL provides values for anything omitted.
        host = os.getenv("FALKORDB_HOST") or url_host or "localhost"
        port_env = os.getenv("FALKORDB_PORT")
        port = int(port_env) if port_env else (url_port or 6379)
        username = os.getenv("FALKORDB_USERNAME") or url_user or ("falkordb" if (host and ("cloud" in host or "falkordb" in host)) else None)
        password = os.getenv("FALKORDB_PASSWORD") or url_pass or None

        ssl_env = os.getenv("FALKORDB_SSL")
        if ssl_env is not None:
            ssl_enabled = ssl_env.lower() in ("true", "1", "yes")
        else:
            ssl_enabled = url_ssl

        return cls(
            host=host,
            port=port,
            username=username,
            password=password,
            graph_name=os.getenv("FALKORDB_GRAPH", "ai_supervisor_memory"),
            timeout=float(os.getenv("FALKORDB_TIMEOUT", "10.0")),
            ssl=ssl_enabled,
            url=url_env,
        )


class FalkorDBClient:
    """
    Manages connections and direct Cypher query executions against FalkorDB.
    Supports local Docker containers and hosted FalkorDB Cloud instances with TLS and authentication.
    Guarantees no silent fallbacks when graph operations are required.
    """

    def __init__(self, config: Optional[FalkorDBConfig] = None):
        self.config = config or FalkorDBConfig.from_env()
        self._db: Optional[Any] = None
        self._graph: Optional[Any] = None
        self._connected: bool = False
        self._last_error: Optional[str] = None

    def _get_target_repr(self) -> str:
        """Returns safe connection target representation for logging without credentials."""
        if self.config.url:
            raw = self.config.url
            if "@" in raw:
                prefix, hostpart = raw.split("@", 1)
                scheme = prefix.split("://")[0] if "://" in prefix else ""
                return f"{scheme}://***@{hostpart}" if scheme else f"***@{hostpart}"
            return raw
        return f"{self.config.host}:{self.config.port}"

    def connect(self) -> bool:
        """
        Attempts to connect to FalkorDB and select the designated graph.
        Supports both local Docker (no auth/no TLS) and hosted FalkorDB Cloud
        (custom host, port, username, password, TLS/SSL, or connection URL).
        Returns True on success, or sets error and returns False.
        """
        try:
            from falkordb import FalkorDB

            if self.config.url:
                url_kwargs: Dict[str, Any] = {
                    "socket_timeout": self.config.timeout,
                    "socket_connect_timeout": self.config.timeout,
                }
                if self.config.username:
                    url_kwargs["username"] = self.config.username
                if self.config.password:
                    url_kwargs["password"] = self.config.password
                if self.config.ssl:
                    url_kwargs["ssl"] = self.config.ssl
                self._db = FalkorDB.from_url(self.config.url, **url_kwargs)
            else:
                kwargs: Dict[str, Any] = {
                    "host": self.config.host,
                    "port": self.config.port,
                    "username": self.config.username,
                    "password": self.config.password,
                    "socket_timeout": self.config.timeout,
                    "socket_connect_timeout": self.config.timeout,
                    "ssl": self.config.ssl,
                }
                # Clean None values
                kwargs = {k: v for k, v in kwargs.items() if v is not None}
                self._db = FalkorDB(**kwargs)

            self._graph = self._db.select_graph(self.config.graph_name)

            # Test connection with a lightweight Cypher query
            start_t = time.perf_counter()
            self._graph.query("RETURN 1 AS ping")
            _ = (time.perf_counter() - start_t) * 1000

            self._connected = True
            self._last_error = None
            target = self._get_target_repr()
            logger.info(
                f"[FalkorDB] Successfully connected to {target} "
                f"(graph: '{self.config.graph_name}', ssl={self.config.ssl})"
            )
            return True
        except Exception as e:
            self._connected = False
            self._last_error = str(e)
            target = self._get_target_repr()
            logger.warning(
                f"[FalkorDB] Connection to {target} failed: {e}"
            )
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_graph(self) -> Any:
        """
        Returns the active FalkorDB Graph handle.
        Raises FalkorDBUnavailableError if not connected.
        """
        if not self._connected or self._graph is None:
            # Attempt reconnect once
            if not self.connect():
                raise FalkorDBUnavailableError(
                    f"FalkorDB is unavailable ({self.config.host}:{self.config.port}). "
                    f"Last error: {self._last_error}. Graph operations cannot proceed."
                )
        return self._graph

    def query(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
        read_only: bool = False,
    ) -> Any:
        """
        Executes a parameterized Cypher query with timeout and error tracking.
        """
        graph = self.get_graph()
        try:
            clean_params = params or {}
            if read_only and hasattr(graph, "ro_query"):
                return graph.ro_query(cypher, clean_params)
            return graph.query(cypher, clean_params)
        except Exception as e:
            self._connected = False
            self._last_error = str(e)
            logger.error(f"[FalkorDB] Query failed: {cypher} | Error: {e}")
            raise FalkorDBUnavailableError(f"FalkorDB query execution failed: {e}") from e

    def is_available(self) -> bool:
        """
        Returns True if FalkorDB is reachable and responsive, False otherwise.
        """
        try:
            return self.connect()
        except Exception:
            return False

    def check_health(self) -> Dict[str, Any]:
        """
        Returns structured health diagnostic report for FalkorDB.
        """
        t0 = time.perf_counter()
        connected = self.connect()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        base_report = {
            "host": self.config.host,
            "port": self.config.port,
            "ssl": self.config.ssl,
            "graph_name": self.config.graph_name,
        }
        if self.config.username:
            base_report["username"] = self.config.username

        if not connected:
            return {
                **base_report,
                "status": "UNHEALTHY",
                "connected": False,
                "error": self._last_error,
                "latency_ms": latency_ms,
                "nodes_count": 0,
                "relationships_count": 0,
            }

        try:
            # Query node and edge counts
            node_res = self._graph.query("MATCH (n) RETURN count(n) AS cnt")
            node_cnt = node_res.result_set[0][0] if node_res.result_set else 0

            edge_res = self._graph.query("MATCH ()-[r]->() RETURN count(r) AS cnt")
            edge_cnt = edge_res.result_set[0][0] if edge_res.result_set else 0

            return {
                **base_report,
                "status": "HEALTHY",
                "connected": True,
                "latency_ms": latency_ms,
                "nodes_count": int(node_cnt),
                "relationships_count": int(edge_cnt),
                "error": None,
            }
        except Exception as e:
            return {
                **base_report,
                "status": "DEGRADED",
                "connected": True,
                "latency_ms": latency_ms,
                "nodes_count": 0,
                "relationships_count": 0,
                "error": str(e),
            }
