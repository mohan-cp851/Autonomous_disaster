import pytest
from app import create_app
from utils.database import db
from models.user import User

@pytest.fixture
def app():
    app = create_app('test')
    
    with app.app_context():
        db.create_all()
        # Seed test user
        from flask_bcrypt import Bcrypt
        bcrypt = Bcrypt(app)
        pw_hash = bcrypt.generate_password_hash("test1234").decode('utf-8')
        u = User(username="test_officer", email="test@disaster.gov.in", password_hash=pw_hash, role="responder")
        db.session.add(u)
        db.session.commit()
        
    yield app
    
    with app.app_context():
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_login_success(client):
    response = client.post('/login', data={
        'account_type': 'volunteer',
        'email': 'test@disaster.gov.in',
        'password': 'test1234'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Logged in successfully!" in response.data

def test_login_failure(client):
    response = client.post('/login', data={
        'account_type': 'volunteer',
        'email': 'test@disaster.gov.in',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Invalid email, password, or account type" in response.data


def test_login_rejects_mismatched_account_type(client):
    response = client.post('/login', data={
        'account_type': 'ndma',
        'email': 'test@disaster.gov.in',
        'password': 'test1234'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Invalid email, password, or account type" in response.data


def test_login_page_offers_public_volunteer_and_ndma(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'value="public" selected>Public' in response.data
    assert b'value="volunteer">Volunteer' in response.data
    assert b'value="ndma">NDMA Officer' in response.data

def test_registration(client, app):
    response = client.post('/register', data={
        'username': 'new_officer',
        'email': 'new@disaster.gov.in',
        'password': 'newpassword123',
        'role': 'responder'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Registration successful" in response.data
    
    with app.app_context():
        registered = User.query.filter_by(username="new_officer").first()
        assert registered is not None
        assert registered.role == "public"
