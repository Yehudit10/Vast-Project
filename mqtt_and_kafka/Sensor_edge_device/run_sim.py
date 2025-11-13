# run_sim.py
import time
import json
import paho.mqtt.client as mqtt
from fill_system_with_fake_data import generate_sensor_data

BROKER = "mosquitto" 
PORT = 1883
TOPIC = "sensors"

def main():
    print("🚀 Simulation started... publishing sensor data to MQTT")
    client = mqtt.Client()
    client.connect(BROKER, PORT, 60)
    
    print("🚀 Simulation started... publishing sensor data to MQTT")

    while True:
        data = generate_sensor_data()
        payload = json.dumps(data)
        client.publish(TOPIC, payload)
        print(f"📤 Published to {TOPIC}: {payload}")
        time.sleep(20) 
if __name__ == "__main__":
    main()
