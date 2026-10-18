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
    password: Optional[str] = None
    graph_name: str = "ai_supervisor_memory"
    timeout: float = 10.0
    ssl: bool = False

    @classmethod
    def from_env(cls) -> "FalkorDBConfig":
        return cls(
            host=os.getenv("FALKORDB_HOST", "localhost"),
            port=int(os.getenv("FALKORDB_PORT", "6379")),
            password=os.getenv("FALKORDB_PASSWORD") or None,
            graph_name=os.getenv("FALKORDB_GRAPH", "ai_supervisor_memory"),
            timeout=float(os.getenv("FALKORDB_TIMEOUT", "10.0")),
            ssl=os.getenv("FALKORDB_SSL", "false").lower() in ("true", "1", "yes"),
        )


class FalkorDBClient:
    """
    Manages connections and direct Cypher query executions against FalkorDB.
    Guarantees no silent fallbacks when graph operations are required.
    """

    def __init__(self, config: Optional[FalkorDBConfig] = None):
        self.config = config or FalkorDBConfig.from_env()
        self._db: Optional[Any] = None
        self._graph: Optional[Any] = None
        self._connected: bool = False
        self._last_error: Optional[str] = None

    def connect(self) -> bool:
        """
        Attempts to connect to FalkorDB and select the designated graph.
        Returns True on success, or sets error and returns False.
        """
        try:
            from falkordb import FalkorDB

            kwargs: Dict[str, Any] = {
                "host": self.config.host,
                "port": self.config.port,
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
            logger.info(
                f"[FalkorDB] Successfully connected to {self.config.host}:{self.config.port} "
                f"(graph: '{self.config.graph_name}')"
            )
            return True
        except Exception as e:
            self._connected = False
            self._last_error = str(e)
            logger.warning(
                f"[FalkorDB] Connection to {self.config.host}:{self.config.port} failed: {e}"
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

        if not connected:
            return {
                "status": "UNHEALTHY",
                "connected": False,
                "host": self.config.host,
                "port": self.config.port,
                "graph_name": self.config.graph_name,
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
                "status": "HEALTHY",
                "connected": True,
                "host": self.config.host,
                "port": self.config.port,
                "graph_name": self.config.graph_name,
                "latency_ms": latency_ms,
                "nodes_count": int(node_cnt),
                "relationships_count": int(edge_cnt),
                "error": None,
            }
        except Exception as e:
            return {
                "status": "DEGRADED",
                "connected": True,
                "host": self.config.host,
                "port": self.config.port,
                "graph_name": self.config.graph_name,
                "latency_ms": latency_ms,
                "nodes_count": 0,
                "relationships_count": 0,
                "error": str(e),
            }
