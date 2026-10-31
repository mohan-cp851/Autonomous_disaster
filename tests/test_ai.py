import pytest
from app import create_app
from utils.database import db
from models.user import User

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
        db.session.commit()
        
    yield app
    
    with app.app_context():
        db.drop_all()

@pytest.fixture
def authenticated_client(app):
    client = app.test_client()
    client.post('/login', data={
        'account_type': 'ndma',
        'email': 'admin@disaster.gov.in',
        'password': 'admin123'
    })
    return client

def test_risk_predictor_low(authenticated_client):
    # Low values should predict Low risk
    response = authenticated_client.post('/api/ai/predict', json={
        'rainfall': 10.0,
        'temperature': 25.0,
        'water_level': 1.0,
        'seismic': 0.1,
        'wind_speed': 10.0,
        'humidity': 50.0
    })
    assert response.status_code == 200
    res_json = response.get_json()
    assert 'highest_risk_type' in res_json
    assert res_json['risk_level'] in ['Low', 'Medium']

def test_risk_predictor_critical(authenticated_client):
    # Spiking rainfall and water level should trigger Flood
    response = authenticated_client.post('/api/ai/predict', json={
        'rainfall': 350.0,
        'temperature': 25.0,
        'water_level': 8.5,
        'seismic': 0.1,
        'wind_speed': 15.0,
        'humidity': 90.0
    })
    assert response.status_code == 200
    res_json = response.get_json()
    assert res_json['highest_risk_type'] == 'Flood'
    assert res_json['risk_level'] in ['High', 'Critical']
