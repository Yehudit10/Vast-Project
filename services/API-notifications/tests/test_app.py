import pytest
from src.backend.app import app
from unittest.mock import patch, MagicMock
from datetime import datetime

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

# Test: GET /schedules (Fetch all schedules)
@patch('src.backend.app.get_db_connection')
def test_get_schedules(mock_get_db_connection, client):
    # Mocking the database connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        (1, 'client1', 'team1', 'cron1', 'Mon,Tue', '09:00-12:00', datetime(2025, 10, 20, 10, 0, 0)),
        (2, 'client2', 'team2', 'cron2', 'Wed,Thu', '14:00-16:00', datetime(2025, 10, 19, 9, 0, 0))
    ]
    
    response = client.get('/schedules')

    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    assert data[0]['client_id'] == 'client1'
    assert data[1]['team'] == 'team2'

# Test: GET /schedule/{schedule_id} (Fetch a single schedule)
@patch('src.backend.app.get_db_connection')
def test_get_schedule(mock_get_db_connection, client):
    # Mocking the database connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (
        1, 'client1', 'team1', 'cron1', 'Mon,Tue', '09:00-12:00', datetime(2025, 10, 20, 10, 0, 0)
    )

    response = client.get('/schedule/1')

    assert response.status_code == 200
    data = response.get_json()
    assert data['client_id'] == 'client1'
    assert data['schedule_id'] == 1

# Test: POST /schedule (Add a new schedule)
@patch('src.backend.app.get_db_connection')
def test_add_schedule(mock_get_db_connection, client):
    # Mocking the database connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (1,)
    
    schedule_data = {
        'client_id': 'client3',
        'team': 'team3',
        'cron_expr': 'cron3',
        'active_days': 'Mon,Wed,Fri',
        'time_window': '08:00-10:00'
    }

    response = client.post('/schedule', json=schedule_data)

    assert response.status_code == 201
    data = response.get_json()
    assert data['message'] == "Schedule added successfully"
    assert data['schedule_id'] == 1

# Test: PUT /schedule/{schedule_id} (Update a schedule)
@patch('src.backend.app.get_db_connection')
def test_update_schedule(mock_get_db_connection, client):
    # Mocking the database connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    update_data = {
        'client_id': 'client1',
        'team': 'team1_updated',
        'cron_expr': 'cron1_updated',
        'active_days': 'Mon,Wed',
        'time_window': '10:00-12:00'
    }

    response = client.put('/schedule/1', json=update_data)

    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == "Schedule updated successfully"

# Test: DELETE /schedule/{schedule_id} (Delete a schedule)
@patch('src.backend.app.get_db_connection')
def test_delete_schedule(mock_get_db_connection, client):
    # Mocking the database connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    response = client.delete('/schedule/1')

    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == "Schedule deleted successfully"