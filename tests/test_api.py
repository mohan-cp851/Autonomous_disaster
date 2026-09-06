import pytest
from app import create_app
from utils.database import db
from models.user import User
from models.sensor import Sensor
from models.incident import Incident

@pytest.fixture
def app():
    app = create_app('test')
    
    with app.app_context():
        db.create_all()
        # Seed user
        from flask_bcrypt import Bcrypt
        bcrypt = Bcrypt(app)
        pw_hash = bcrypt.generate_password_hash("admin123").decode('utf-8')
        u = User(username="admin", email="admin@disaster.gov.in", password_hash=pw_hash, role="admin")
        db.session.add(u)
        
        # Seed sensor
        s = Sensor(
            name="Pune Mula River Level", sensor_type="Water Level", location_name="Pune",
            latitude=18.52, longitude=73.85, current_value=1.5, unit="meters",
            warning_threshold=3.0, critical_threshold=5.0, status="Normal"
        )
        db.session.add(s)
        
        # Seed Incident
        inc = Incident(
            title="Pune Water Logging", disaster_type="flood", severity="Medium",
            location_name="Pune", latitude=18.52, longitude=73.85, description="Pune logging",
            status="Active", reported_by="System"
        )
        db.session.add(inc)
        db.session.commit()
        
    yield app
    
    with app.app_context():
        db.drop_all()

@pytest.fixture
def authenticated_client(app):
    client = app.test_client()
    client.post('/login', data={
        'email': 'admin@disaster.gov.in',
        'password': 'admin123'
    })
    return client

def test_get_sensor_data(authenticated_client):
    response = authenticated_client.get('/api/sensors/data')
    assert response.status_code == 200
    json_data = response.get_json()
    assert len(json_data) == 1
    assert json_data[0]['name'] == "Pune Mula River Level"

def test_trigger_sensor_spike(authenticated_client, app):
    response = authenticated_client.post('/api/sensors/trigger-event', json={
        'sensor_id': 1,
        'event_type': 'flood_spike'
    })
    assert response.status_code == 200
    res_json = response.get_json()
    assert res_json['status'] == 'Critical'
    assert res_json['value'] >= 5.0

def test_update_incident_status(authenticated_client, app):
    response = authenticated_client.post('/api/incidents/1/status', json={
        'status': 'Under Control'
    })
    assert response.status_code == 200
    with app.app_context():
        inc = Incident.query.get(1)
        assert inc.status == 'Under Control'
