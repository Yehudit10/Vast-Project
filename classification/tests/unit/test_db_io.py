import pytest
import uuid
from unittest.mock import MagicMock, Mock, patch

from classification.core.db_io_pg import (
    open_db,
    finish_run,
)

# ------------------- Fixtures -------------------

@pytest.fixture
def mock_db_connection():
    """Create a mock database connection that supports context manager"""
    conn = MagicMock()
    # cursor() used in 'with conn.cursor() as cur:'
    cursor_mock = MagicMock()
    cursor_mock.__enter__.return_value = cursor_mock
    cursor_mock.__exit__.return_value = False
    conn.cursor.return_value = cursor_mock
    return conn

# ------------------- Tests -------------------

@pytest.mark.db
def test_open_db():
    """Test database connection opening"""
    with patch('psycopg2.connect') as mock_connect:
        conn = open_db('postgresql://user:pass@localhost/db', schema='audio_cls')
        mock_connect.assert_called_once()

        # Test connection with default schema
        conn = open_db('postgresql://user:pass@localhost/db')
        assert conn is not None

@pytest.mark.db
def test_finish_run(mock_db_connection):
    """Test run finalization"""
    cursor = mock_db_connection.cursor().__enter__()
    run_id = str(uuid.uuid4())

    finish_run(mock_db_connection, run_id)
    cursor.execute.assert_called_once()

    sql = cursor.execute.call_args[0][0]
    assert 'finished_at' in sql
    assert 'run_id' in sql

@pytest.mark.db
def test_error_handling(mock_db_connection):
    """Test exception handling in DB functions"""
    cursor = mock_db_connection.cursor().__enter__()
    cursor.execute.side_effect = Exception("Database error")

    # Only finish_run is left here since others are fully covered with fakes
    with pytest.raises(Exception):
        finish_run(mock_db_connection, str(uuid.uuid4()))
