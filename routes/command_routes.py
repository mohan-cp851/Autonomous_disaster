import json
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from models.incident import Incident
from models.operations import (
    AllocationPlan,
    AuditRecord,
    EvidenceReport,
    PlanApproval,
    ReplanEvent,
    RoadSegment,
    ShelterCondition,
)
from models.resource import Resource
from models.shelter import Shelter
from models.team import RescueTeam
from utils.database import db
from utils.operations import (
    SOURCE_RELIABILITY,
    active_incidents,
    audit,
    compare_plans,
    create_allocation_plan,
    evidence_assessment,
    incident_duplicates,
    parse_datetime,
    plan_payload,
    priority_assessment,
    recommend_shelters,
    shelter_payload,
    update_incident_verification,
    _network_route,
)


command_bp = Blueprint('command', __name__)
SOURCE_TYPES = set(SOURCE_RELIABILITY)
SEVERITIES = {'Low', 'Medium', 'High', 'Critical'}
DISASTER_TYPES = {'flood', 'earthquake', 'fire', 'cyclone', 'landslide', 'tsunami'}
EVIDENCE_STATES = {'Verified', 'Rejected', 'Inconclusive', 'Superseded'}


def _operator():
    return current_user.role in ('admin', 'responder')


def _forbidden():
    return jsonify({'success': False, 'error': 'This operation is not permitted for your role.'}), 403


def _commit_or_error():
    try:
        db.session.commit()
        return None
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Command-center database operation failed')
        return jsonify({'success': False, 'error': 'The operation could not be saved.'}), 500


def _latest_plan():
    return AllocationPlan.query.filter(
        AllocationPlan.status.in_(('Proposed', 'Approved'))
    ).order_by(AllocationPlan.created_at.desc(), AllocationPlan.id.desc()).first()


def _timestamp(value):
    return value.isoformat(timespec='seconds') + 'Z' if value else None


def _road_payload(segment):
    return {
        'id': segment.id,
        'name': segment.name,
        'start': [segment.start_lat, segment.start_lng],
        'end': [segment.end_lat, segment.end_lng],
        'status': segment.status,
        'source_type': segment.source_type,
        'source_reference': segment.source_reference,
        'updated_at': _timestamp(segment.updated_at),
    }


@command_bp.route('/command-center')
@login_required
def index():
    return render_template('command_center.html', can_operate=_operator())


@command_bp.route('/api/command/overview')
@login_required
def overview():
    incidents = sorted(
        active_incidents(),
        key=lambda incident: (
            -priority_assessment(incident)['score'],
            incident.created_at,
        ),
    )
    latest = _latest_plan()
    proposed = AllocationPlan.query.filter_by(status='Proposed').order_by(
        AllocationPlan.created_at.desc()
    ).first()
    return jsonify({
        'success': True,
        'generated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'summary': {
            'active_incidents': len(incidents),
            'needs_verification': sum(
                priority_assessment(incident)['priority'] == 'Needs Verification'
                for incident in incidents
            ),
            'available_teams': RescueTeam.query.filter_by(status='Available').count(),
            'available_supply_units': sum(
                max(0, item.available_qty) for item in Resource.query.all()
            ),
            'pending_approvals': AllocationPlan.query.filter_by(status='Proposed').count(),
        },
        'incidents': [{
            **incident.to_dict(),
            'priority_assessment': priority_assessment(incident),
        } for incident in incidents],
        'teams': [team.to_dict() for team in RescueTeam.query.order_by(RescueTeam.id).all()],
        'resources': [item.to_dict() for item in Resource.query.order_by(Resource.id).all()],
        'shelters': [
            shelter_payload(shelter)
            for shelter in Shelter.query.order_by(Shelter.id).all()
        ],
        'roads': [_road_payload(segment) for segment in RoadSegment.query.order_by(RoadSegment.id).all()],
        'latest_plan': plan_payload(latest) if latest else None,
        'pending_plan': plan_payload(proposed) if proposed else None,
        'recent_events': [{
            'id': event.id,
            'event_type': event.event_type,
            'source_type': event.source_type,
            'details': json.loads(event.details or '{}'),
            'created_at': _timestamp(event.created_at),
        } for event in ReplanEvent.query.order_by(ReplanEvent.created_at.desc()).limit(10).all()],
        'recent_audit': [{
            'action': record.action,
            'object_type': record.object_type,
            'object_id': record.object_id,
            'details': json.loads(record.details or '{}'),
            'created_at': _timestamp(record.created_at),
        } for record in AuditRecord.query.order_by(AuditRecord.created_at.desc()).limit(10).all()],
    })


@command_bp.route('/api/command/incidents', methods=['POST'])
@login_required
def create_incident():
    if not _operator():
        return _forbidden()
    data = request.get_json(silent=True) or {}
    title = data.get('title', '').strip() if isinstance(data.get('title'), str) else ''
    description = data.get('description', '').strip() if isinstance(data.get('description'), str) else ''
    disaster_type = str(data.get('disaster_type', '')).strip().lower()
    severity = str(data.get('severity', '')).strip().title()
    source_type = str(data.get('source_type', 'Citizen')).strip()
    location_name = str(data.get('location_name', 'Unspecified')).strip()[:150]

    try:
        latitude = float(data['latitude'])
        longitude = float(data['longitude'])
        affected_count = int(data.get('affected_count', 0))
        reported_at = parse_datetime(data.get('reported_at'), 'reported_at')
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({'success': False, 'error': str(exc) or 'Coordinates are required.'}), 400

    if not title or len(title) > 150 or not description or len(description) > 5000:
        return jsonify({'success': False, 'error': 'Title and description are required and must be within length limits.'}), 400
    if disaster_type not in DISASTER_TYPES or severity not in SEVERITIES or source_type not in SOURCE_TYPES:
        return jsonify({'success': False, 'error': 'Disaster type, severity, or source category is invalid.'}), 400
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({'success': False, 'error': 'Coordinates are outside valid latitude/longitude ranges.'}), 400
    if affected_count < 0 or affected_count > 1_000_000:
        return jsonify({'success': False, 'error': 'affected_count must be between 0 and 1,000,000.'}), 400

    incident = Incident(
        title=title,
        description=description,
        disaster_type=disaster_type,
        severity=severity,
        location_name=location_name or 'Unspecified',
        latitude=latitude,
        longitude=longitude,
        reported_by=current_user.username,
        created_at=reported_at,
        affected_count=affected_count,
        verification_status='Pending Review',
    )
    db.session.add(incident)
    db.session.flush()
    evidence = EvidenceReport(
        incident=incident,
        source_type=source_type,
        source_reference=(str(data.get('source_reference', '')).strip()[:120] or None),
        description=description,
        observed_at=reported_at,
        submitted_by_id=current_user.id,
    )
    db.session.add(evidence)
    audit('incident.created', 'incident', incident.id, current_user.id, {'source_type': source_type})
    error = _commit_or_error()
    if error:
        return error
    return jsonify({
        'success': True,
        'incident': incident.to_dict(),
        'potential_duplicates': incident_duplicates(incident),
    }), 201


@command_bp.route('/api/command/incidents/<int:incident_id>/assessment')
@login_required
def incident_assessment(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    return jsonify({
        'success': True,
        'incident': incident.to_dict(),
        'priority': priority_assessment(incident),
        'potential_duplicates': incident_duplicates(incident),
    })


@command_bp.route('/api/command/incidents/<int:incident_id>/evidence', methods=['POST'])
@login_required
def submit_evidence(incident_id):
    if not _operator():
        return _forbidden()
    incident = Incident.query.get_or_404(incident_id)
    data = request.get_json(silent=True) or {}
    description = data.get('description', '').strip() if isinstance(data.get('description'), str) else ''
    source_type = str(data.get('source_type', '')).strip()
    claim_type = str(data.get('claim_type', '')).strip() or None
    claim_value = str(data.get('claim_value', '')).strip() or None
    if not description or len(description) > 5000:
        return jsonify({'success': False, 'error': 'Evidence description is required and must be at most 5,000 characters.'}), 400
    if source_type not in SOURCE_TYPES:
        return jsonify({'success': False, 'error': 'Unknown evidence source category.'}), 400
    if (claim_type is None) != (claim_value is None) or (
        claim_type and (len(claim_type) > 40 or len(claim_value) > 120)
    ):
        return jsonify({'success': False, 'error': 'Claim type and value must both be provided within their limits.'}), 400
    try:
        observed_at = parse_datetime(data.get('observed_at'), 'observed_at')
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    report = EvidenceReport(
        incident=incident,
        source_type=source_type,
        source_reference=(str(data.get('source_reference', '')).strip()[:120] or None),
        description=description,
        claim_type=claim_type,
        claim_value=claim_value,
        observed_at=observed_at,
        submitted_by_id=current_user.id,
    )
    db.session.add(report)
    db.session.flush()
    update_incident_verification(incident)
    audit('evidence.submitted', 'evidence', report.id, current_user.id, {'incident_id': incident.id})
    error = _commit_or_error()
    if error:
        return error
    return jsonify({
        'success': True,
        'evidence': evidence_assessment(incident),
        'priority': priority_assessment(incident),
    }), 201


@command_bp.route('/api/command/evidence/<int:evidence_id>/review', methods=['POST'])
@login_required
def review_evidence(evidence_id):
    if not _operator():
        return _forbidden()
    report = EvidenceReport.query.get_or_404(evidence_id)
    data = request.get_json(silent=True) or {}
    state = str(data.get('status', '')).strip().title()
    note = str(data.get('reason', '')).strip()
    if state not in EVIDENCE_STATES or len(note) > 500:
        return jsonify({'success': False, 'error': 'Review status or reason is invalid.'}), 400
    report.verification_status = state
    report.review_note = note or None
    report.reviewed_by_id = current_user.id
    report.reviewed_at = datetime.utcnow()
    update_incident_verification(report.incident)
    audit('evidence.reviewed', 'evidence', report.id, current_user.id, {
        'status': state,
        'reason': note,
    })
    error = _commit_or_error()
    if error:
        return error
    return jsonify({
        'success': True,
        'incident_verification_status': report.incident.verification_status,
        'priority': priority_assessment(report.incident),
    })


@command_bp.route('/api/command/plans/optimize', methods=['POST'])
@login_required
def optimize_plan():
    if not _operator():
        return _forbidden()
    previous = _latest_plan()
    try:
        plan = create_allocation_plan(
            current_user.id,
            trigger='Manual optimization',
            previous_plan=previous,
        )
        audit('plan.proposed', 'allocation_plan', plan.id, current_user.id, {
            'previous_plan_id': previous.id if previous else None,
        })
        error = _commit_or_error()
        if error:
            return error
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Allocation optimization failed')
        return jsonify({'success': False, 'error': 'Could not calculate or save an allocation plan.'}), 500
    return jsonify({
        'success': True,
        'plan': plan_payload(plan),
        'comparison': compare_plans(previous, plan),
    }), 201


@command_bp.route('/api/command/plans/<int:plan_id>/decision', methods=['POST'])
@login_required
def decide_plan(plan_id):
    if current_user.role != 'admin':
        return _forbidden()
    plan = AllocationPlan.query.get_or_404(plan_id)
    data = request.get_json(silent=True) or {}
    decision = str(data.get('decision', '')).strip().title()
    reason = str(data.get('reason', '')).strip()
    if decision not in ('Approved', 'Rejected') or len(reason) > 500:
        return jsonify({'success': False, 'error': 'Decision or reason is invalid.'}), 400
    if plan.status != 'Proposed':
        return jsonify({'success': False, 'error': 'Only a pending proposed plan can be reviewed.'}), 409
    plan.status = decision
    approval = PlanApproval(
        plan_id=plan.id,
        user_id=current_user.id,
        decision=decision,
        reason=reason or None,
    )
    db.session.add(approval)
    audit(f'plan.{decision.lower()}', 'allocation_plan', plan.id, current_user.id, {
        'reason': reason,
        'version': plan.version,
    })
    error = _commit_or_error()
    if error:
        return error
    return jsonify({'success': True, 'plan': plan_payload(plan)})


@command_bp.route('/api/command/plans/<int:plan_id>/comparison')
@login_required
def plan_comparison(plan_id):
    plan = AllocationPlan.query.get_or_404(plan_id)
    return jsonify({
        'success': True,
        'comparison': compare_plans(plan.previous_plan, plan),
        'plan': plan_payload(plan),
    })


@command_bp.route('/api/command/roads/<int:segment_id>/status', methods=['POST'])
@login_required
def update_road_status(segment_id):
    if not _operator():
        return _forbidden()
    segment = RoadSegment.query.get_or_404(segment_id)
    data = request.get_json(silent=True) or {}
    event_key = str(data.get('event_id', '')).strip()
    new_status = str(data.get('status', '')).strip().title()
    source_type = str(data.get('source_type', 'Field Team')).strip()
    if not event_key or len(event_key) > 120:
        return jsonify({'success': False, 'error': 'A unique event_id of at most 120 characters is required.'}), 400
    if new_status not in ('Open', 'Closed') or source_type not in SOURCE_TYPES:
        return jsonify({'success': False, 'error': 'Road status or source category is invalid.'}), 400

    prior_event = ReplanEvent.query.filter_by(event_key=event_key).first()
    if prior_event:
        prior_details = json.loads(prior_event.details or '{}')
        if prior_details.get('segment_id') != segment.id or prior_details.get('requested_status') != new_status:
            return jsonify({'success': False, 'error': 'event_id was already used for a different road update.'}), 409
        return jsonify({
            'success': True,
            'duplicate_event': True,
            'event_id': prior_event.id,
            'details': prior_details,
        })

    previous = _latest_plan()
    old_status = segment.status
    segment.status = new_status
    segment.source_type = source_type
    segment.source_reference = str(data.get('source_reference', '')).strip()[:120] or None
    segment.updated_by_id = current_user.id
    segment.updated_at = datetime.utcnow()
    event = ReplanEvent(
        event_key=event_key,
        event_type='road_status_changed',
        source_type=source_type,
        segment_id=segment.id,
        previous_plan_id=previous.id if previous else None,
        created_by_id=current_user.id,
        details=json.dumps({
            'segment_id': segment.id,
            'segment_name': segment.name,
            'previous_status': old_status,
            'requested_status': new_status,
        }, sort_keys=True),
    )
    db.session.add(event)
    db.session.flush()

    plan = None
    comparison = None
    if previous:
        plan = create_allocation_plan(
            current_user.id,
            trigger=f'Road update: {segment.name} is {new_status}',
            previous_plan=previous,
        )
        comparison = compare_plans(previous, plan)
        event.new_plan_id = plan.id
        details = {
            'segment_id': segment.id,
            'segment_name': segment.name,
            'previous_status': old_status,
            'requested_status': new_status,
            'affected_assignments': [
                item['incident_id'] for item in (
                    comparison['changed_assignments'] + comparison['removed_assignments']
                )
            ],
            'comparison': comparison,
        }
        event.details = json.dumps(details, sort_keys=True)
    audit('road.status_changed', 'road_segment', segment.id, current_user.id, {
        'from': old_status,
        'to': new_status,
        'event_id': event_key,
    })
    if plan:
        audit('plan.reproposed', 'allocation_plan', plan.id, current_user.id, {
            'event_id': event.id,
            'previous_plan_id': previous.id,
        })
    error = _commit_or_error()
    if error:
        return error
    return jsonify({
        'success': True,
        'duplicate_event': False,
        'event_id': event.id,
        'road': _road_payload(segment),
        'plan': plan_payload(plan) if plan else None,
        'comparison': comparison,
        'message': (
            'The road update was recorded and a new proposed allocation plan was calculated.'
            if plan else 'The road update was recorded; generate a plan to assess assignments.'
        ),
    }), 201


@command_bp.route('/api/command/routes')
@login_required
def route_recommendation():
    try:
        source = (float(request.args['source_lat']), float(request.args['source_lng']))
        destination = (float(request.args['dest_lat']), float(request.args['dest_lng']))
    except (KeyError, TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Valid source and destination coordinates are required.'}), 400
    if (
        not -90 <= source[0] <= 90 or not -180 <= source[1] <= 180
        or not -90 <= destination[0] <= 90 or not -180 <= destination[1] <= 180
    ):
        return jsonify({'success': False, 'error': 'Coordinates are outside valid latitude/longitude ranges.'}), 400
    return jsonify({'success': True, 'route': _network_route(source, destination)})


@command_bp.route('/api/command/shelters/recommendations')
@login_required
def shelter_recommendations():
    try:
        latitude = float(request.args['latitude'])
        longitude = float(request.args['longitude'])
        people = int(request.args.get('people', '1'))
    except (KeyError, TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Valid coordinates and a people count are required.'}), 400
    if (
        not -90 <= latitude <= 90 or not -180 <= longitude <= 180
        or people < 1 or people > 1_000_000
    ):
        return jsonify({'success': False, 'error': 'Coordinates or people count are outside allowed ranges.'}), 400
    return jsonify({
        'success': True,
        'shelters': recommend_shelters(latitude, longitude, people),
        'routing_note': 'Shelters are sorted by straight-line distance; this is not a driving route.',
    })


@command_bp.route('/api/command/shelters/<int:shelter_id>/condition', methods=['POST'])
@login_required
def update_shelter_condition(shelter_id):
    if not _operator():
        return _forbidden()
    shelter = Shelter.query.get_or_404(shelter_id)
    data = request.get_json(silent=True) or {}
    state = str(data.get('accessibility_status', '')).strip().title()
    facilities = str(data.get('facilities', '')).strip()
    source = str(data.get('information_source', '')).strip()
    if state not in ('Accessible', 'Inaccessible', 'Unknown'):
        return jsonify({'success': False, 'error': 'Accessibility status is invalid.'}), 400
    if len(facilities) > 1000 or len(source) > 120:
        return jsonify({'success': False, 'error': 'Shelter information exceeds the allowed length.'}), 400
    condition = ShelterCondition.query.filter_by(shelter_id=shelter.id).first()
    if condition is None:
        condition = ShelterCondition(shelter_id=shelter.id)
        db.session.add(condition)
    condition.accessibility_status = state
    condition.facilities = facilities or None
    condition.information_source = source or None
    condition.updated_at = datetime.utcnow()
    audit('shelter.condition_updated', 'shelter', shelter.id, current_user.id, {
        'accessibility_status': state,
        'source': source,
    })
    error = _commit_or_error()
    if error:
        return error
    return jsonify({'success': True, 'shelter': shelter_payload(shelter)})


@command_bp.route('/api/command/audit')
@login_required
def audit_history():
    try:
        limit = min(100, max(1, int(request.args.get('limit', '50'))))
    except ValueError:
        return jsonify({'success': False, 'error': 'limit must be an integer.'}), 400
    records = AuditRecord.query.order_by(AuditRecord.created_at.desc()).limit(limit).all()
    return jsonify({
        'success': True,
        'records': [{
            'id': record.id,
            'action': record.action,
            'object_type': record.object_type,
            'object_id': record.object_id,
            'details': json.loads(record.details or '{}'),
            'created_at': _timestamp(record.created_at),
        } for record in records],
    })


@command_bp.route('/api/command/demo', methods=['POST'])
@login_required
def initialize_demo():
    if current_user.role != 'admin':
        return _forbidden()

    demo_incidents = [
        {
            'title': '[SIM] Riverside flooding',
            'type': 'flood',
            'severity': 'Critical',
            'location': 'Pune demonstration area',
            'coordinates': (18.5214, 73.8567),
            'affected': 80,
            'description': 'Floodwater is approaching homes beside the river road.',
        },
        {
            'title': '[SIM] Neighborhood structural damage',
            'type': 'earthquake',
            'severity': 'High',
            'location': 'Pune demonstration area',
            'coordinates': (18.5190, 73.8510),
            'affected': 35,
            'description': 'Several buildings are damaged and residents report trapped occupants.',
        },
        {
            'title': '[SIM] Market building fire',
            'type': 'fire',
            'severity': 'High',
            'location': 'Pune demonstration area',
            'coordinates': (18.5240, 73.8610),
            'affected': 24,
            'description': 'A commercial building fire is producing heavy smoke.',
        },
        {
            'title': '[SIM] Hillside slope movement',
            'type': 'landslide',
            'severity': 'Medium',
            'location': 'Pune demonstration area',
            'coordinates': (18.5160, 73.8590),
            'affected': 18,
            'description': 'Residents report fresh slope movement near a hillside settlement.',
        },
    ]
    existing = {
        incident.title: incident
        for incident in Incident.query.filter(
            Incident.title.in_([item['title'] for item in demo_incidents])
        ).all()
    }
    if existing:
        if len(existing) != len(demo_incidents):
            return jsonify({
                'success': False,
                'error': 'A partial simulation scenario already exists; no records were changed.',
            }), 409
        return jsonify({
            'success': True,
            'already_initialized': True,
            'incident_ids': [existing[item['title']].id for item in demo_incidents],
            'message': 'The deterministic simulation scenario is already initialized.',
        })

    incidents = []
    now = datetime.utcnow()
    for item in demo_incidents:
        incident = Incident(
            title=item['title'],
            disaster_type=item['type'],
            severity=item['severity'],
            location_name=item['location'],
            latitude=item['coordinates'][0],
            longitude=item['coordinates'][1],
            description=item['description'],
            reported_by='Simulation scenario',
            created_at=now,
            affected_count=item['affected'],
            verification_status='Pending Review',
        )
        db.session.add(incident)
        incidents.append(incident)
    db.session.flush()

    reports = [
        (incidents[0], 'Citizen', 'SIM-INC-1-REPORT-A', 'Residents see water covering the river approach.', 'road_access', 'Open'),
        (incidents[0], 'Sensor', 'SIM-INC-1-SENSOR', 'Water-level sensor records a rapid rise near the river road.', 'road_access', 'Closed'),
        (incidents[0], 'Citizen', 'SIM-INC-1-REPORT-A', 'Residents see water covering the river approach.', 'road_access', 'Open'),
        (incidents[1], 'Field Team', 'SIM-INC-2-FIELD', 'Field officer confirms visible structural damage.', 'severity', 'High'),
    ]
    for incident, source, reference, description, claim_type, claim_value in reports:
        db.session.add(EvidenceReport(
            incident=incident,
            source_type=source,
            source_reference=reference,
            description=description,
            claim_type=claim_type,
            claim_value=claim_value,
            observed_at=now,
            submitted_by_id=current_user.id,
        ))
        update_incident_verification(incident)

    teams_data = [
        ('[SIM] Boat flood team', 'Flood Rescue', 20, (18.5204, 73.8567)),
        ('[SIM] Urban search team', 'Search & Rescue', 16, (18.5214, 73.8760)),
        ('[SIM] Medical response team', 'Medical Assistance', 12, (18.5190, 73.8505)),
        ('[SIM] Fire response team', 'Fire / Hazmat', 14, (18.5240, 73.8605)),
    ]
    for name, specialization, members, coordinates in teams_data:
        db.session.add(RescueTeam(
            name=name,
            specialization=specialization,
            members_count=members,
            status='Available',
            latitude=coordinates[0],
            longitude=coordinates[1],
            contact_number='SIM',
        ))

    for name, category, quantity in (
        ('[SIM] Medical kits', 'Medical', 20),
        ('[SIM] Food packages', 'Food', 30),
        ('[SIM] Drinking water', 'Water', 30),
    ):
        db.session.add(Resource(
            name=name,
            resource_type=category,
            total_qty=quantity,
            allocated_qty=0,
            location_name='Pune demonstration depot',
        ))

    shelters_data = [
        ('[SIM] Riverside community shelter', 18.5260, 73.8640, 120, 25, 'Accessible'),
        ('[SIM] Hillside relief center', 18.5140, 73.8550, 60, 58, 'Unknown'),
    ]
    shelters = []
    for name, latitude, longitude, capacity, occupancy, accessibility in shelters_data:
        shelter = Shelter(
            name=name,
            location_name='Pune demonstration area',
            latitude=latitude,
            longitude=longitude,
            capacity=capacity,
            occupancy=occupancy,
            food_stock_days=3,
            water_stock_days=3,
            medical_stock_level='Good',
        )
        db.session.add(shelter)
        shelters.append((shelter, accessibility))
    db.session.flush()
    for shelter, accessibility in shelters:
        db.session.add(ShelterCondition(
            shelter_id=shelter.id,
            accessibility_status=accessibility,
            facilities='First aid, accessible water point' if accessibility == 'Accessible' else None,
            information_source='Simulated demonstration data',
        ))

    junction = (18.5214, 73.8767)
    road_specs = [
        ('[SIM] Riverside bridge', (18.5204, 73.8567), (18.5214, 73.8567)),
        ('[SIM] Boat depot connector', (18.5204, 73.8567), junction),
        ('[SIM] Riverside alternate approach', junction, (18.5214, 73.8567)),
        ('[SIM] Search team corridor', (18.5214, 73.8760), junction),
        ('[SIM] Structural response corridor', (18.5190, 73.8505), junction),
        ('[SIM] Market response corridor', (18.5240, 73.8605), junction),
        ('[SIM] Hillside response corridor', (18.5160, 73.8590), junction),
        ('[SIM] Shelter access corridor', junction, (18.5260, 73.8640)),
    ]
    for name, start, end in road_specs:
        db.session.add(RoadSegment(
            name=name,
            start_lat=start[0],
            start_lng=start[1],
            end_lat=end[0],
            end_lng=end[1],
            status='Open',
            source_type='Simulated',
            source_reference='SIM-ROAD-NETWORK',
            updated_by_id=current_user.id,
            updated_at=now,
            scenario_key='pune-disruption-v1',
        ))
    audit('demo.initialized', 'scenario', None, current_user.id, {
        'scenario_key': 'pune-disruption-v1',
        'simulated': True,
        'incident_ids': [incident.id for incident in incidents],
    })
    error = _commit_or_error()
    if error:
        return error
    return jsonify({
        'success': True,
        'already_initialized': False,
        'simulated': True,
        'incident_ids': [incident.id for incident in incidents],
        'road_segments': [
            _road_payload(segment)
            for segment in RoadSegment.query.filter_by(scenario_key='pune-disruption-v1').all()
        ],
        'message': 'Deterministic simulated scenario initialized. It does not represent live conditions.',
    }), 201
