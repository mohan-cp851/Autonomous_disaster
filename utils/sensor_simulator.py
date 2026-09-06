import time
import random
import threading
from datetime import datetime
from utils.database import db

# Thread control variable
_simulator_thread = None
_stop_event = threading.Event()

def simulate_sensors_task(app):
    """
    Background loop that runs inside Flask app context.
    Periodically updates sensor values in SQLite and creates alerts if thresholds are exceeded.
    """
    from models.sensor import Sensor
    from models.alert import Alert
    from models.incident import Incident
    
    print("Background Sensor Simulator Thread Started.")
    with app.app_context():
        while not _stop_event.is_set():
            try:
                sensors = Sensor.query.all()
                for sensor in sensors:
                    # Random walk noise
                    delta = random.uniform(-0.15, 0.15)
                    
                    # Custom simulation for sensor types
                    if sensor.sensor_type == 'Seismic':
                        # Seismic values usually stay low (0.5 - 2.0), but can spike
                        sensor.current_value += delta * 0.5
                        sensor.current_value = max(0.1, min(sensor.current_value, 9.0))
                    elif sensor.sensor_type == 'Water Level':
                        # Water level stays normal unless heavy rain simulation is triggered
                        sensor.current_value += delta * 0.3
                        sensor.current_value = max(0.0, min(sensor.current_value, 15.0))
                    elif sensor.sensor_type == 'Temperature':
                        # Temperature fluctuates around 30C
                        sensor.current_value += delta * 1.5
                        sensor.current_value = max(10.0, min(sensor.current_value, 55.0))
                    elif sensor.sensor_type == 'Wind Speed':
                        # Wind speed fluctuates (10 - 45 km/h)
                        sensor.current_value += delta * 5.0
                        sensor.current_value = max(0.0, min(sensor.current_value, 250.0))
                    
                    # Check thresholds
                    old_status = sensor.status
                    if sensor.current_value >= sensor.critical_threshold:
                        sensor.status = 'Critical'
                    elif sensor.current_value >= sensor.warning_threshold:
                        sensor.status = 'Warning'
                    else:
                        sensor.status = 'Normal'
                        
                    # If status degraded, create an alert and incident
                    if sensor.status != old_status and sensor.status in ['Warning', 'Critical']:
                        msg = f"IoT {sensor.sensor_type} Alert: {sensor.name} in {sensor.location_name} reached {round(sensor.current_value, 2)} {sensor.unit} (Threshold: {sensor.critical_threshold if sensor.status == 'Critical' else sensor.warning_threshold})"
                        
                        alert = Alert(
                            message=msg,
                            severity=sensor.status,
                            alert_type='IoT Sensor Alert',
                            location_name=sensor.location_name
                        )
                        db.session.add(alert)
                        
                        # Auto-trigger an Incident for Critical states
                        if sensor.status == 'Critical':
                            dtype = "flood" if sensor.sensor_type == "Water Level" else                                     "earthquake" if sensor.sensor_type == "Seismic" else                                     "fire" if sensor.sensor_type == "Temperature" and sensor.current_value > 48 else                                     "cyclone" if sensor.sensor_type == "Wind Speed" else "general"
                                    
                            # Check if similar incident already active to avoid duplicates
                            dup = Incident.query.filter_by(
                                location_name=sensor.location_name,
                                disaster_type=dtype,
                                status='Active'
                            ).first()
                            
                            if not dup:
                                inc = Incident(
                                    title=f"Automatic IoT Trigger: {sensor.sensor_type} Hazard",
                                    disaster_type=dtype,
                                    severity='Critical',
                                    location_name=sensor.location_name,
                                    latitude=sensor.latitude,
                                    longitude=sensor.longitude,
                                    description=f"Auto-generated incident: Sensor {sensor.name} registered critical reading of {round(sensor.current_value, 2)} {sensor.unit}.",
                                    reported_by='IoT Simulator'
                                )
                                db.session.add(inc)
                                
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Simulator Thread Error: {e}")
                
            # Sleep 8 seconds
            _stop_event.wait(8.0)

def start_simulator(app):
    global _simulator_thread
    if _simulator_thread is None or not _simulator_thread.is_alive():
        _stop_event.clear()
        _simulator_thread = threading.Thread(target=simulate_sensors_task, args=(app,), daemon=True)
        _simulator_thread.start()

def stop_simulator():
    _stop_event.set()
