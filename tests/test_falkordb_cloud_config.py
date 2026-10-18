"""
Unit and integration tests for FalkorDB configuration parsing,
cloud connection setup, TLS/SSL configuration, and credential security.
"""

import os
from unittest.mock import patch, MagicMock
import pytest

from storage.graph.client import FalkorDBConfig, FalkorDBClient


def test_falkordb_config_defaults():
    """Verify local Docker defaults are preserved when no env vars are set."""
    with patch.dict(os.environ, {}, clear=True):
        cfg = FalkorDBConfig.from_env()
        assert cfg.host == "localhost"
        assert cfg.port == 6379
        assert cfg.username is None
        assert cfg.password is None
        assert cfg.graph_name == "ai_supervisor_memory"
        assert cfg.timeout == 10.0
        assert cfg.ssl is False
        assert cfg.url is None


def test_falkordb_config_cloud_env_parsing():
    """Verify FalkorDB Cloud environment variables are correctly parsed."""
    env = {
        "FALKORDB_HOST": "my-cluster.falkordb.cloud",
        "FALKORDB_PORT": "14920",
        "FALKORDB_USERNAME": "cloud_operator",
        "FALKORDB_PASSWORD": "super-secret-password-123",
        "FALKORDB_GRAPH": "production_memory",
        "FALKORDB_TIMEOUT": "25.5",
        "FALKORDB_SSL": "true",
    }
    with patch.dict(os.environ, env, clear=True):
        cfg = FalkorDBConfig.from_env()
        assert cfg.host == "my-cluster.falkordb.cloud"
        assert cfg.port == 14920
        assert cfg.username == "cloud_operator"
        assert cfg.password == "super-secret-password-123"
        assert cfg.graph_name == "production_memory"
        assert cfg.timeout == 25.5
        assert cfg.ssl is True
        assert cfg.url is None


def test_falkordb_config_cloud_host_defaults_to_falkordb_user_when_omitted():
    """Verify cloud endpoint automatically defaults username to 'falkordb' when omitted in env."""
    env = {
        "FALKORDB_HOST": "r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud",
        "FALKORDB_PORT": "56915",
        "FALKORDB_PASSWORD": "secret_password",
    }
    with patch.dict(os.environ, env, clear=True):
        cfg = FalkorDBConfig.from_env()
        assert cfg.host == "r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud"
        assert cfg.port == 56915
        assert cfg.username == "falkordb"
        assert cfg.password == "secret_password"


def test_falkordb_config_url_env_parsing():
    """Verify connection URL extracts username, password, host, port, and ssl."""
    env = {
        "FALKORDB_URL": "falkor://falkordb@r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud:56915",
        "FALKORDB_PASSWORD": "secret_cloud_password",
        "FALKORDB_GRAPH": "url_memory",
    }
    with patch.dict(os.environ, env, clear=True):
        cfg = FalkorDBConfig.from_env()
        assert cfg.url == "falkor://falkordb@r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud:56915"
        assert cfg.host == "r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud"
        assert cfg.port == 56915
        assert cfg.username == "falkordb"
        assert cfg.password == "secret_cloud_password"
        assert cfg.ssl is False
        assert cfg.graph_name == "url_memory"


def test_falkordb_config_incomplete_url_fallback():
    """Verify that an incomplete URL without username/password does NOT drop discrete credentials."""
    env = {
        "FALKORDB_URL": "falkor://r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud:56915",
        "FALKORDB_USERNAME": "falkordb",
        "FALKORDB_PASSWORD": "secret_cloud_password",
    }
    with patch.dict(os.environ, env, clear=True):
        cfg = FalkorDBConfig.from_env()
        # Incomplete URL host/port are parsed, while discrete username and password fill the missing auth
        assert cfg.host == "r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud"
        assert cfg.port == 56915
        assert cfg.username == "falkordb"
        assert cfg.password == "secret_cloud_password"


def test_falkordb_client_discrete_kwargs_setup():
    """Verify FalkorDBClient passes username, password, ssl, and timeouts correctly in discrete-configuration mode."""
    cfg = FalkorDBConfig(
        host="r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud",
        port=56915,
        username="falkordb",
        password="secret_password",
        graph_name="test_graph",
        timeout=15.0,
        ssl=False,
    )
    client = FalkorDBClient(config=cfg)

    with patch("falkordb.FalkorDB") as mock_falkordb_cls:
        mock_instance = MagicMock()
        mock_graph = MagicMock()
        mock_instance.select_graph.return_value = mock_graph
        mock_falkordb_cls.return_value = mock_instance

        success = client.connect()
        assert success is True
        assert client.is_connected is True

        # Verify SDK was called with discrete username and password
        mock_falkordb_cls.assert_called_once_with(
            host="r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud",
            port=56915,
            username="falkordb",
            password="secret_password",
            socket_timeout=15.0,
            socket_connect_timeout=15.0,
            ssl=False,
        )
        mock_instance.select_graph.assert_called_once_with("test_graph")


def test_falkordb_client_url_mode_passes_username_and_password():
    """Verify FalkorDBClient in URL mode passes both username and password to FalkorDB.from_url."""
    cfg = FalkorDBConfig(
        url="falkor://falkordb@r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud:56915",
        username="falkordb",
        password="secret_password",
        graph_name="cloud_graph",
        timeout=20.0,
        ssl=False,
    )
    client = FalkorDBClient(config=cfg)

    with patch("falkordb.FalkorDB.from_url") as mock_from_url:
        mock_instance = MagicMock()
        mock_graph = MagicMock()
        mock_instance.select_graph.return_value = mock_graph
        mock_from_url.return_value = mock_instance

        success = client.connect()
        assert success is True
        mock_from_url.assert_called_once_with(
            "falkor://falkordb@r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud:56915",
            username="falkordb",
            password="secret_password",
            socket_timeout=20.0,
            socket_connect_timeout=20.0,
        )


def test_falkordb_client_url_mode_incomplete_url_auth_preservation():
    """Verify that an incomplete URL without embedded credentials still receives discrete username and password in from_url."""
    cfg = FalkorDBConfig(
        url="falkor://r-6jissuruar.instance-k4ikf9kv0.hc-7up0crkyn.ap-south-1.aws.f2e0a955bb84.cloud:56915",
        username="falkordb",
        password="secret_password",
        graph_name="cloud_graph",
        timeout=10.0,
    )
    client = FalkorDBClient(config=cfg)

    with patch("falkordb.FalkorDB.from_url") as mock_from_url:
        mock_instance = MagicMock()
        mock_graph = MagicMock()
        mock_instance.select_graph.return_value = mock_graph
        mock_from_url.return_value = mock_instance

        success = client.connect()
        assert success is True
        # Explicit username and password must NOT be omitted
        assert mock_from_url.call_args.kwargs.get("username") == "falkordb"
        assert mock_from_url.call_args.kwargs.get("password") == "secret_password"


def test_falkordb_credential_security_no_secret_leaks():
    """Verify that credentials and passwords are never exposed in logs or health reports."""
    cfg = FalkorDBConfig(
        host="cloud.falkordb.cloud",
        port=15000,
        username="db_user",
        password="CLASSIFIED_SECRET_PASSWORD_XYZ",
        graph_name="secure_graph",
        ssl=True,
    )
    client = FalkorDBClient(config=cfg)

    # 1. Target representation masking
    target_repr = client._get_target_repr()
    assert "CLASSIFIED_SECRET" not in target_repr
    assert target_repr == "cloud.falkordb.cloud:15000"

    url_cfg = FalkorDBConfig(
        url="falkors://user:SECRET_PASS_999@db.falkordb.cloud:15000",
    )
    client_url = FalkorDBClient(config=url_cfg)
    url_repr = client_url._get_target_repr()
    assert "SECRET_PASS_999" not in url_repr
    assert "***" in url_repr

    # 2. check_health() report does NOT leak password
    health = client.check_health()
    assert "password" not in health
    assert "CLASSIFIED_SECRET_PASSWORD_XYZ" not in str(health)
    assert health["ssl"] is True
    assert health["username"] == "db_user"


def test_falkordb_local_docker_live_query():
    """Verify local Docker instance connectivity still succeeds with default configuration."""
    local_cfg = FalkorDBConfig(host="localhost", port=6379, ssl=False)
    client = FalkorDBClient(config=local_cfg)
    health = client.check_health()

    if health["connected"]:
        # If local docker is up, verify ping query works
        res = client.query("RETURN 100 AS num")
        assert res.result_set[0][0] == 100
    else:
        # If docker isn't running in test env, verify it cleanly reports disconnected without crash
        assert health["status"] == "UNHEALTHY"
        assert health["connected"] is False
