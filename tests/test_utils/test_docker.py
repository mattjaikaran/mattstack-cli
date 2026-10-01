"""Tests for Docker utility functions."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from mattstack.utils.docker import (
    docker_available,
    docker_compose_available,
    docker_running,
    parse_compose_ps,
)

# --- docker_available ---


@patch("mattstack.utils.docker.shutil.which", return_value="/usr/local/bin/docker")
def test_docker_available_found(mock_which) -> None:
    assert docker_available() is True
    mock_which.assert_called_once_with("docker")


@patch("mattstack.utils.docker.shutil.which", return_value=None)
def test_docker_available_not_found(mock_which) -> None:
    assert docker_available() is False
    mock_which.assert_called_once_with("docker")


# --- docker_compose_available ---


@patch("mattstack.utils.docker.subprocess.run")
def test_docker_compose_available_success(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
    assert docker_compose_available() is True


@patch("mattstack.utils.docker.subprocess.run", side_effect=subprocess.CalledProcessError(1, ""))
def test_docker_compose_available_called_process_error(mock_run) -> None:
    assert docker_compose_available() is False


@patch("mattstack.utils.docker.subprocess.run", side_effect=FileNotFoundError)
def test_docker_compose_available_file_not_found(mock_run) -> None:
    assert docker_compose_available() is False


# --- docker_running ---


@patch("mattstack.utils.docker.subprocess.run")
def test_docker_running_success(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
    assert docker_running() is True


@patch("mattstack.utils.docker.subprocess.run", side_effect=subprocess.CalledProcessError(1, ""))
def test_docker_running_called_process_error(mock_run) -> None:
    assert docker_running() is False


@patch("mattstack.utils.docker.subprocess.run", side_effect=FileNotFoundError)
def test_docker_running_file_not_found(mock_run) -> None:
    assert docker_running() is False


@patch("mattstack.utils.docker.subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 20))
def test_docker_running_hung_daemon_is_not_running(mock_run) -> None:
    assert docker_running() is False


# --- parse_compose_ps ---


def test_parse_compose_ps_accepts_legacy_json_array() -> None:
    output = (
        '[{"Service": "db", "Name": "x-db-1", "State": "running", "Health": "healthy"},'
        ' {"Service": "redis", "Name": "x-redis-1", "State": "restarting", "Health": ""}]'
    )
    containers = {c.service: c for c in parse_compose_ps(output)}
    assert containers["db"].healthy is True
    assert containers["redis"].healthy is False
    assert containers["redis"].summary == "restarting"


def test_parse_compose_ps_accepts_ndjson_and_flags_unhealthy() -> None:
    output = (
        '{"Service": "db", "Name": "x-db-1", "State": "running", "Health": "unhealthy"}\n'
        '{"Service": "api-dev", "Name": "x-api-1", "State": "running", "Health": ""}\n'
    )
    containers = {c.service: c for c in parse_compose_ps(output)}
    assert containers["db"].healthy is False
    assert containers["db"].summary == "running (unhealthy)"
    assert containers["api-dev"].healthy is True


def test_parse_compose_ps_empty_output_has_no_containers() -> None:
    assert parse_compose_ps("") == []
    assert parse_compose_ps("[]") == []
