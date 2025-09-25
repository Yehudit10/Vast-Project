from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import datetime
from psycopg2 import sql

app = Flask(__name__)
CORS(app)

# define the connect to the DB
def get_db_connection():
    conn = psycopg2.connect(
        dbname="missions_db", 
        user="missions_user", 
        password="pg123", 
        host="localhost", 
        port="5432"
    )
    return conn

@app.route('/schedules', methods=['GET'])
def get_schedules():
    client_id = request.args.get('client_id')
    
    # connect to the database
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if client_id:
            # Get schedules for specific client
            cur.execute("""
                SELECT schedule_id, client_id, team, cron_expr, active_days, time_window, last_updated
                FROM clients 
                WHERE client_id = %s
                ORDER BY last_updated DESC
            """, (client_id,))
        else:
            # Get all schedules
            cur.execute("""
                SELECT schedule_id, client_id, team, cron_expr, active_days, time_window, last_updated
                FROM clients 
                ORDER BY last_updated DESC
            """)
        
        schedules = cur.fetchall()
        
        # Convert to list of dictionaries
        schedule_list = []
        for schedule in schedules:
            schedule_list.append({
                'schedule_id': schedule[0],
                'client_id': schedule[1],
                'team': schedule[2],
                'cron_expr': schedule[3],
                'active_days': schedule[4],
                'time_window': schedule[5],
                'last_updated': schedule[6].isoformat() if schedule[6] else None
            })
        
        return jsonify(schedule_list), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

@app.route('/schedule/<int:schedule_id>', methods=['GET'])
def get_schedule(schedule_id):
    # connect to the database
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT schedule_id, client_id, team, cron_expr, active_days, time_window, last_updated
            FROM clients 
            WHERE schedule_id = %s
        """, (schedule_id,))
        
        schedule = cur.fetchone()
        
        if not schedule:
            return jsonify({"error": "Schedule not found"}), 404
        
        # Convert to dictionary
        schedule_data = {
            'schedule_id': schedule[0],
            'client_id': schedule[1],
            'team': schedule[2],
            'cron_expr': schedule[3],
            'active_days': schedule[4],
            'time_window': schedule[5],
            'last_updated': schedule[6].isoformat() if schedule[6] else None
        }
        
        return jsonify(schedule_data), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

@app.route('/schedule', methods=['POST'])
def add_schedule():
    
    data = request.json
    client_id = data.get('client_id')
    team = data.get('team')
    cron_expr = data.get('cron_expr')
    active_days = data.get('active_days')
    time_window = data.get('time_window')

    # connect to the database
    conn = get_db_connection()
    cur = conn.cursor()

    # insert the new schedule into the database
    query = sql.SQL("""
        INSERT INTO clients (client_id, team, cron_expr, active_days, time_window, last_updated)
        VALUES (%s, %s, %s, %s, %s, now())
        RETURNING schedule_id;
    """)

    try:
        cur.execute(query, (client_id, team, cron_expr, active_days, time_window))
        result = cur.fetchone()

        if not result:
            return jsonify({"error": "Failed to add schedule"}), 400
        
        schedule_id = result[0]
        conn.commit()

        return jsonify({"message": "Schedule added successfully", "schedule_id": schedule_id}), 201
    
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

@app.route('/schedule/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    data = request.get_json()
    
    # connect to the database
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE clients
            SET client_id = %s, team = %s, cron_expr = %s, active_days = %s, time_window = %s, last_updated = %s
            WHERE schedule_id = %s
        """, (
            data['client_id'], 
            data['team'], 
            data['cron_expr'], 
            data['active_days'], 
            data['time_window'], 
            datetime.datetime.now(),
            schedule_id
        ))
        conn.commit()
        
        return jsonify({"message": "Schedule updated successfully"}), 200
    
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

@app.route('/schedule/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    # connect to the database
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM clients WHERE schedule_id = %s", (schedule_id,))
        conn.commit()
        
        return jsonify({"message": "Schedule deleted successfully"}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    app.run(debug=True)
