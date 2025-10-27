# Task Scheduling API

This API allows you to manage task schedules for clients. You can create, update, and delete schedules.
Base URL
`http://127.0.0.1:5000`

Endpoints

## 1. Create a Schedule (POST)

URL: /schedule
Method: POST
Request Body:

`
{
  "client_id": 1,
  "team": "Development",
  "cron_expr": "0 3 * * 1",
  "active_days": "Monday, Friday",
  "time_window": "08:00-17:00"
}
`

Response:
{"message": "Schedule added successfully",
  "schedule_id": 5}

## 2. Update a Schedule (PUT)

URL: /schedule/<schedule_id>
Method: PUT
Request Body:

`
{
  "client_id": 1,
  "team": "Development",
  "cron_expr": "0 3 * * 1",
  "active_days": "Sunday, Friday",
  "time_window": "08:00-18:00"
}
`

Response:
{"message": "Schedule updated successfully"}

## 3. Delete a Schedule (DELETE)

URL: /schedule/<schedule_id>

Method: DELETE

Response:
{"message": "Schedule deleted successfully"}

Example Usage with curl

Create a Schedule:

```powershell
curl -Uri http://127.0.0.1:5000/schedule -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"client_id": 1, "team": "Development", "cron_expr": "0 3 * * 1", "active_days": "Monday, Friday", "time_window": "08:00-17:00"}'
```

Update a Schedule:

```powershell
curl -Uri http://127.0.0.1:5000/schedule/5 -Method PUT -Headers @{"Content-Type"="application/json"} -Body '{"client_id": 1, "team": "Development", "cron_expr": "0 3 * * 1", "active_days": "Sunday, Friday", "time_window": "08:00-18:00"}'
```

Delete a Schedule:

```powershell
curl -Uri http://127.0.0.1:5000/schedule/5 -Method DELETE -Headers @{"Content-Type"="application/json"}
```

Errors

If an error occurs, the response will contain an "error" field with a description. Example:
{"error": "Failed to add schedule"}

Notes

- Ensure the server is running (python app.py).
- The API is available at `http://127.0.0.1:5000`.
- You can use any HTTP client (curl, Postman, etc.) to interact with the API.
