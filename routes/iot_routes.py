from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models.sensor import Sensor
from models.alert import Alert
from models.incident import Incident
from utils.database import db
import random

iot_bp = Blueprint('iot', __name__)

@iot_bp.route('/sensors')
@login_required
def index():
    sensors = Sensor.query.all()
    alerts = Alert.query.order_by(Alert.timestamp.desc()).limit(15).all()
    return render_template('sensors.html', sensors=sensors, alerts=alerts)

@iot_bp.route('/api/sensors/data')
@login_required
def get_sensor_data():
    sensors = Sensor.query.all()
    return jsonify([s.to_dict() for s in sensors])

@iot_bp.route('/api/sensors/trigger-event', methods=['POST'])
@login_required
def trigger_sensor_event():
    if current_user.role not in ['admin', 'responder']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.get_json() or {}
    sensor_id = data.get('sensor_id')
    event_type = data.get('event_type') # e.g. "flood_spike", "seismic_shock", "wind_gust", "heat_wave", "reset"
    
    sensor = Sensor.query.get(sensor_id)
    if not sensor:
        return jsonify({'error': 'Sensor not found'}), 404
        
    if event_type == "flood_spike":
        sensor.current_value = float(sensor.critical_threshold + random.uniform(1.0, 3.0))
    elif event_type == "seismic_shock":
        sensor.current_value = float(sensor.critical_threshold + random.uniform(0.5, 2.5))
    elif event_type == "wind_gust":
        sensor.current_value = float(sensor.critical_threshold + random.uniform(10.0, 50.0))
    elif event_type == "heat_wave":
        sensor.current_value = float(sensor.critical_threshold + random.uniform(2.0, 6.0))
    elif event_type == "reset":
        sensor.current_value = float(sensor.warning_threshold - random.uniform(0.5, 1.5))
        sensor.status = 'Normal'
        db.session.commit()
        return jsonify({'message': f'Sensor {sensor.name} reset to normal', 'value': sensor.current_value})
        
    # Check status and trigger DB update
    if sensor.current_value >= sensor.critical_threshold:
        sensor.status = 'Critical'
    elif sensor.current_value >= sensor.warning_threshold:
        sensor.status = 'Warning'
    else:
        sensor.status = 'Normal'
        
    msg = f"Simulated Event: Sensor {sensor.name} in {sensor.location_name} spiked to {round(sensor.current_value, 2)} {sensor.unit} ({sensor.status})"
    alert = Alert(
        message=msg,
        severity=sensor.status,
        alert_type='Manual Sim Spike',
        location_name=sensor.location_name
    )
    db.session.add(alert)
    
    # Auto-add Incident
    if sensor.status == 'Critical':
        dtype = "flood" if sensor.sensor_type == "Water Level" else                 "earthquake" if sensor.sensor_type == "Seismic" else                 "fire" if sensor.sensor_type == "Temperature" else                 "cyclone" if sensor.sensor_type == "Wind Speed" else "general"
                
        inc = Incident(
            title=f"Manual Simulation Alarm: {sensor.sensor_type} Spike",
            disaster_type=dtype,
            severity='Critical',
            location_name=sensor.location_name,
            latitude=sensor.latitude,
            longitude=sensor.longitude,
            description=f"Simulated alert: Sensor {sensor.name} reached critical reading of {round(sensor.current_value, 2)} {sensor.unit}.",
            reported_by='Simulation Control'
        )
        db.session.add(inc)
        
    db.session.commit()
    
    return jsonify({
        'message': f'Sensor {sensor.name} event triggered successfully',
        'value': round(sensor.current_value, 2),
        'status': sensor.status
    })
