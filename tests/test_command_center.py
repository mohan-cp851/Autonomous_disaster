import pytest
from flask_bcrypt import Bcrypt

from app import create_app
from models.incident import Incident
from models.operations import (
    AllocationAssignment,
    AllocationPlan,
    EvidenceReport,
    PlanApproval,
    RoadSegment,
    ShelterCondition,
)
from models.resource import Resource
from models.shelter import Shelter
from models.team import RescueTeam
from models.user import User
from utils.database import db


@pytest.fixture
def command_app():
    app = create_app('test')
    with app.app_context():
        db.create_all()
        bcrypt = Bcrypt(app)
        for username, role in (('admin', 'admin'), ('responder', 'responder'), ('citizen', 'public')):
            db.session.add(User(
                username=username,
                email=f'{username}@disaster.gov.in',
                password_hash=bcrypt.generate_password_hash('testpass123').decode('utf-8'),
                role=role,
            ))
        db.session.commit()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def admin_client(command_app):
    client = command_app.test_client()
    client.post('/login', data={
        'account_type': 'ndma',
        'email': 'admin@disaster.gov.in',
        'password': 'testpass123',
    })
    return client


def _create_incident(client, **overrides):
    payload = {
        'title': 'Riverbank flooding',
        'description': 'Flood water is rising near houses.',
        'disaster_type': 'flood',
        'severity': 'High',
        'source_type': 'Citizen',
        'location_name': 'Pune',
        'latitude': 18.52,
        'longitude': 73.85,
        'affected_count': 12,
    }
    payload.update(overrides)
    return client.post('/api/command/incidents', json=payload)


def test_evidence_conflicts_duplicates_and_review_recalculate_priority(admin_client):
    created = _create_incident(admin_client)
    assert created.status_code == 201
    incident_id = created.get_json()['incident']['id']

    first = admin_client.post(
        f'/api/command/incidents/{incident_id}/evidence',
        json={
            'source_type': 'Field Team',
            'source_reference': 'FIELD-21',
            'description': 'Field team reports the river access road is open.',
            'claim_type': 'road_access',
            'claim_value': 'Open',
        },
    )
    second = admin_client.post(
        f'/api/command/incidents/{incident_id}/evidence',
        json={
            'source_type': 'Sensor',
            'source_reference': 'SENSOR-9',
            'description': 'Water sensor indicates the river access road is closed.',
            'claim_type': 'road_access',
            'claim_value': 'Closed',
        },
    )
    duplicate = admin_client.post(
        f'/api/command/incidents/{incident_id}/evidence',
        json={
            'source_type': 'Field Team',
            'source_reference': 'FIELD-21',
            'description': 'Field team reports the river access road is open.',
            'claim_type': 'road_access',
            'claim_value': 'Open',
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert duplicate.status_code == 201
    result = admin_client.get(f'/api/command/incidents/{incident_id}/assessment').get_json()
    evidence = result['priority']['evidence']
    assert evidence['confidence_score'] > 0
    assert len(evidence['conflicts']) == 1
    assert evidence['potential_duplicate_reports']
    assert result['priority']['factors'][0]['name'] == 'Reported severity'

    report_id = next(item['id'] for item in evidence['evidence'] if item['source_type'] == 'Field Team')
    reviewed = admin_client.post(
        f'/api/command/evidence/{report_id}/review',
        json={'status': 'Verified', 'reason': 'Confirmed at the location.'},
    )
    assert reviewed.status_code == 200
    assert reviewed.get_json()['incident_verification_status'] == 'Conflicting'


def test_optimizer_enforces_capabilities_availability_and_unique_teams(command_app, admin_client):
    with command_app.app_context():
        db.session.add_all([
            Incident(
                title='Flood A', description='Flood report', disaster_type='flood',
                severity='Critical', location_name='Pune', latitude=18.52, longitude=73.85,
                affected_count=10,
            ),
            Incident(
                title='Flood B', description='Another flood report', disaster_type='flood',
                severity='High', location_name='Pune', latitude=18.53, longitude=73.86,
                affected_count=10,
            ),
        ])
        db.session.add_all([
            RescueTeam(
                name='Available flood crew', specialization='Flood Rescue', members_count=10,
                status='Available', latitude=18.52, longitude=73.85, contact_number='1',
            ),
            RescueTeam(
                name='Unavailable flood crew', specialization='Flood Rescue', members_count=10,
                status='Dispatched', latitude=18.52, longitude=73.85, contact_number='2',
            ),
            RescueTeam(
                name='Medical-only crew', specialization='Medical Assistance', members_count=10,
                status='Available', latitude=18.52, longitude=73.85, contact_number='3',
            ),
            Resource(
                name='One medical kit', resource_type='Medical', total_qty=1,
                allocated_qty=0, location_name='Pune',
            ),
        ])
        db.session.commit()

    response = admin_client.post('/api/command/plans/optimize', json={})
    assert response.status_code == 201
    plan = response.get_json()['plan']
    assert len(plan['assignments']) == 1
    assert plan['assignments'][0]['team_name'] == 'Available flood crew'
    assert len(plan['unserved_incidents']) == 1
    assert all(
        item['team_name'] != 'Medical-only crew'
        and item['team_name'] != 'Unavailable flood crew'
        for item in plan['assignments']
    )
    assert all(need['shortage_qty'] >= 0 for need in plan['resource_needs'])


def test_road_disruption_replans_and_retries_are_idempotent(command_app, admin_client):
    with command_app.app_context():
        incident = Incident(
            title='Road-graph flood', description='Flood in a settlement',
            disaster_type='flood', severity='Critical', location_name='Pune',
            latitude=0, longitude=0.01, affected_count=10,
        )
        team = RescueTeam(
            name='Road-graph boat team', specialization='Flood Rescue',
            members_count=10, status='Available', latitude=0, longitude=0,
            contact_number='1',
        )
        db.session.add_all([incident, team])
        db.session.flush()
        db.session.add_all([
            RoadSegment(
                name='Direct bridge', start_lat=0, start_lng=0, end_lat=0, end_lng=0.01,
                status='Open', source_type='Simulated',
            ),
            RoadSegment(
                name='Alternate north road', start_lat=0, start_lng=0, end_lat=0.01, end_lng=0,
                status='Open', source_type='Simulated',
            ),
            RoadSegment(
                name='Alternate east road', start_lat=0.01, start_lng=0, end_lat=0, end_lng=0.01,
                status='Open', source_type='Simulated',
            ),
        ])
        db.session.commit()

    initial = admin_client.post('/api/command/plans/optimize', json={}).get_json()['plan']
    direct_distance = initial['assignments'][0]['travel_distance_km']
    with command_app.app_context():
        bridge_id = RoadSegment.query.filter_by(name='Direct bridge').first().id
    disrupted = admin_client.post(
        f'/api/command/roads/{bridge_id}/status',
        json={
            'event_id': 'bridge-closure-1',
            'status': 'Closed',
            'source_type': 'Field Team',
        },
    )
    assert disrupted.status_code == 201
    payload = disrupted.get_json()
    assert payload['plan']['previous_plan_id'] == initial['id']
    assert payload['plan']['status'] == 'Proposed'
    assert payload['comparison']['retained_assignments'][0]['route_changed']
    assert payload['plan']['assignments'][0]['travel_distance_km'] > direct_distance

    retry = admin_client.post(
        f'/api/command/roads/{bridge_id}/status',
        json={
            'event_id': 'bridge-closure-1',
            'status': 'Closed',
            'source_type': 'Field Team',
        },
    )
    assert retry.status_code == 200
    assert retry.get_json()['duplicate_event'] is True
    with command_app.app_context():
        assert AllocationPlan.query.count() == 2


def test_plan_approval_is_admin_only_and_does_not_dispatch(command_app, admin_client):
    with command_app.app_context():
        db.session.add(Incident(
            title='Approval flood', description='Flood alert',
            disaster_type='flood', severity='High', location_name='Pune',
            latitude=18.52, longitude=73.85, affected_count=5,
        ))
        db.session.add(RescueTeam(
            name='Approval team', specialization='Flood Rescue', members_count=5,
            status='Available', latitude=18.52, longitude=73.85, contact_number='1',
        ))
        db.session.commit()
    plan = admin_client.post('/api/command/plans/optimize', json={}).get_json()['plan']
    responder = command_app.test_client()
    responder.post('/login', data={
        'account_type': 'volunteer',
        'email': 'responder@disaster.gov.in',
        'password': 'testpass123',
    })
    denied = responder.post(
        f"/api/command/plans/{plan['id']}/decision",
        json={'decision': 'Approved'},
    )
    assert denied.status_code == 403
    approved = admin_client.post(
        f"/api/command/plans/{plan['id']}/decision",
        json={'decision': 'Approved', 'reason': 'Reviewed by command.'},
    )
    assert approved.status_code == 200
    with command_app.app_context():
        assert RescueTeam.query.filter_by(name='Approval team').first().status == 'Available'
        assert PlanApproval.query.filter_by(plan_id=plan['id'], decision='Approved').count() == 1


def test_shelter_capacity_and_accessibility_are_enforced(command_app, admin_client):
    with command_app.app_context():
        shelter = Shelter(
            name='Full shelter', location_name='Pune', latitude=18.52, longitude=73.85,
            capacity=10, occupancy=10,
        )
        db.session.add(shelter)
        db.session.flush()
        db.session.add(ShelterCondition(
            shelter_id=shelter.id,
            accessibility_status='Inaccessible',
            information_source='Field report',
        ))
        db.session.commit()
    response = admin_client.get(
        '/api/command/shelters/recommendations?latitude=18.52&longitude=73.85&people=1'
    )
    assert response.status_code == 200
    shelter_data = response.get_json()['shelters'][0]
    assert shelter_data['vacancy'] == 0
    assert shelter_data['feasible_for_requested_capacity'] is False


def test_public_user_cannot_modify_operational_records(command_app):
    public = command_app.test_client()
    public.post('/login', data={
        'account_type': 'public',
        'email': 'citizen@disaster.gov.in',
        'password': 'testpass123',
    })
    assert _create_incident(public).status_code == 403
    assert public.post('/api/command/plans/optimize', json={}).status_code == 403
    page = public.get('/command-center')
    assert page.status_code == 200
    assert b'Load simulated scenario' not in page.data


def test_simulated_scenario_initializes_repeatably(admin_client):
    first = admin_client.post('/api/command/demo', json={})
    assert first.status_code == 201
    assert first.get_json()['simulated'] is True
    overview = admin_client.get('/api/command/overview').get_json()
    assert len(overview['incidents']) == 4
    assert len(overview['roads']) >= 6
    assert any(item['evidence']['conflicts'] for item in (
        incident['priority_assessment'] for incident in overview['incidents']
    ))

    second = admin_client.post('/api/command/demo', json={})
    assert second.status_code == 200
    assert second.get_json()['already_initialized'] is True
