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
    PriorityAssessmentRecord,
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
    record_priority_assessment,
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
DEMO_SCENARIOS = {
    'pune': {
        'name': 'Pune',
        'scenario_key': 'pune-disruption-v1',
        'area': 'Pune demonstration area',
        'depot': 'Pune demonstration depot',
        'incidents': [
            ('[SIM] Riverside flooding', 'flood', 'Critical', (18.5214, 73.8567), 80,
             'Floodwater is approaching homes beside the river road.'),
            ('[SIM] Neighborhood structural damage', 'earthquake', 'High', (18.5190, 73.8510), 35,
             'Several buildings are damaged and residents report trapped occupants.'),
            ('[SIM] Market building fire', 'fire', 'High', (18.5240, 73.8610), 24,
             'A commercial building fire is producing heavy smoke.'),
            ('[SIM] Hillside slope movement', 'landslide', 'Medium', (18.5160, 73.8590), 18,
             'Residents report fresh slope movement near a hillside settlement.'),
        ],
        'evidence': [
            (0, 'Citizen', 'INC-1-REPORT-A', 'Residents see water covering the river approach.', 'road_access', 'Open'),
            (0, 'Sensor', 'INC-1-SENSOR', 'Water-level sensor records a rapid rise near the river road.', 'road_access', 'Closed'),
            (0, 'Citizen', 'INC-1-REPORT-A', 'Residents see water covering the river approach.', 'road_access', 'Open'),
            (1, 'Field Team', 'INC-2-FIELD', 'Field officer confirms visible structural damage.', 'severity', 'High'),
        ],
        'teams': [
            ('Boat flood team', 'Flood Rescue', 20, (18.5204, 73.8567)),
            ('Urban search team', 'Search & Rescue', 16, (18.5214, 73.8760)),
            ('Medical response team', 'Medical Assistance', 12, (18.5190, 73.8505)),
            ('Fire response team', 'Fire / Hazmat', 14, (18.5240, 73.8605)),
        ],
        'resources': [('Medical kits', 'Medical', 20), ('Food packages', 'Food', 30), ('Drinking water', 'Water', 30)],
        'shelters': [
            ('Riverside community shelter', 18.5260, 73.8640, 120, 25, 'Accessible'),
            ('Hillside relief center', 18.5140, 73.8550, 60, 58, 'Unknown'),
        ],
        'roads': [
            ('Riverside bridge', (18.5204, 73.8567), (18.5214, 73.8567)),
            ('Boat depot connector', (18.5204, 73.8567), (18.5214, 73.8767)),
            ('Riverside alternate approach', (18.5214, 73.8767), (18.5214, 73.8567)),
            ('Search team corridor', (18.5214, 73.8760), (18.5214, 73.8767)),
            ('Structural response corridor', (18.5190, 73.8510), (18.5190, 73.8505)),
            ('Market response corridor', (18.5240, 73.8610), (18.5240, 73.8605)),
            ('Hillside response corridor', (18.5160, 73.8590), (18.5160, 73.8595)),
            ('Shelter access corridor', (18.5214, 73.8767), (18.5260, 73.8640)),
        ],
    },
    'chennai': {
        'name': 'Chennai',
        'scenario_key': 'chennai-flood-v1',
        'area': 'Chennai synthetic demonstration area',
        'depot': 'Chennai synthetic demonstration depot',
        'incidents': [
            ('[SIM-CHENNAI] Adyar river flooding', 'flood', 'Critical', (13.0067, 80.2572), 120,
             'Synthetic report of rising water affecting low-lying homes near the Adyar river.'),
            ('[SIM-CHENNAI] Velachery street inundation', 'flood', 'High', (12.9750, 80.2210), 75,
             'Synthetic report of waterlogging affecting residents and access roads in Velachery.'),
            ('[SIM-CHENNAI] Ennore cyclone shelter request', 'cyclone', 'High', (13.2150, 80.3210), 90,
             'Synthetic high-wind alert with residents requesting transport to a designated demonstration shelter.'),
            ('[SIM-CHENNAI] Perungudi market fire', 'fire', 'Medium', (12.9611, 80.2430), 30,
             'Synthetic report of a market-area fire with smoke affecting nearby streets.'),
        ],
        'evidence': [
            (0, 'Citizen', 'ADYAR-REPORT-A', 'Synthetic resident report: water is covering the approach road.', 'road_access', 'Open'),
            (0, 'Sensor', 'ADYAR-GAUGE-1', 'Synthetic water-level observation indicates the approach is inundated.', 'road_access', 'Closed'),
            (0, 'Citizen', 'ADYAR-REPORT-A', 'Synthetic resident report: water is covering the approach road.', 'road_access', 'Open'),
            (0, 'Field Team', 'ADYAR-FIELD-1', 'Synthetic field-team corroboration: water is rising near the homes.', 'water_trend', 'Rising'),
            (1, 'Citizen', 'VELACHERY-REPORT-A', 'Synthetic report of waterlogged streets and slow vehicle access.', 'road_access', 'Restricted'),
            (2, 'Government', 'ENNORE-ALERT-SIM', 'Synthetic demonstration alert; not an official weather warning.', 'source_status', 'Simulated'),
            (3, 'Field Team', 'PERUNGUDI-FIELD-SIM', 'Synthetic field observer reports smoke near the market.', 'fire_status', 'Active'),
        ],
        'teams': [
            ('Adyar boat rescue team', 'Flood Rescue', 24, (13.0073, 80.2568)),
            ('Velachery urban response team', 'Search & Rescue', 18, (12.9740, 80.2195)),
            ('North Chennai cyclone response team', 'Cyclone Rescue', 20, (13.2140, 80.3195)),
            ('Perungudi fire and medical team', 'Fire / Hazmat', 16, (12.9605, 80.2420)),
        ],
        'resources': [
            ('Medical kits', 'Medical', 45),
            ('Family food packs', 'Food', 60),
            ('Drinking water packs', 'Water', 60),
            ('Rescue boat kits', 'Vehicle', 4),
        ],
        'shelters': [
            ('Adyar synthetic relief center', 13.0120, 80.2620, 180, 55, 'Accessible'),
            ('Velachery synthetic community shelter', 12.9810, 80.2260, 140, 132, 'Unknown'),
            ('North Chennai synthetic cyclone shelter', 13.2200, 80.3260, 260, 100, 'Accessible'),
        ],
        'roads': [
            ('Adyar bridge approach', (13.0073, 80.2568), (13.0067, 80.2572)),
            ('Adyar northern detour connector', (13.0073, 80.2568), (13.0120, 80.2600)),
            ('Adyar alternate river approach', (13.0120, 80.2600), (13.0067, 80.2572)),
            ('Velachery response corridor', (12.9740, 80.2195), (12.9750, 80.2210)),
            ('Velachery alternate access', (12.9740, 80.2195), (12.9800, 80.2240)),
            ('Velachery shelter connector', (12.9800, 80.2240), (12.9750, 80.2210)),
            ('Ennore cyclone response corridor', (13.2140, 80.3195), (13.2150, 80.3210)),
            ('Perungudi fire response corridor', (12.9605, 80.2420), (12.9611, 80.2430)),
            ('Adyar shelter access', (13.0120, 80.2600), (13.0120, 80.2620)),
            ('North Chennai shelter access', (13.2150, 80.3210), (13.2200, 80.3260)),
        ],
    },
}


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
            'priority_history': [{
                'priority': record.priority,
                'score': record.score,
                'trigger': record.trigger,
                'created_at': _timestamp(record.created_at),
            } for record in PriorityAssessmentRecord.query.filter_by(
                incident_id=incident.id
            ).order_by(PriorityAssessmentRecord.created_at.desc()).limit(5).all()],
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
    record_priority_assessment(incident, 'Incident report created', current_user.id)
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
    history = PriorityAssessmentRecord.query.filter_by(incident_id=incident.id).order_by(
        PriorityAssessmentRecord.created_at.desc()
    ).limit(20).all()
    return jsonify({
        'success': True,
        'incident': incident.to_dict(),
        'priority': priority_assessment(incident),
        'potential_duplicates': incident_duplicates(incident),
        'priority_history': [{
            'priority': item.priority,
            'score': item.score,
            'factors': json.loads(item.factors),
            'rationale': item.rationale,
            'trigger': item.trigger,
            'created_at': _timestamp(item.created_at),
        } for item in history],
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
    record_priority_assessment(incident, 'Evidence submitted', current_user.id)
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
    record_priority_assessment(report.incident, f'Evidence {state.lower()}', current_user.id)
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

    data = request.get_json(silent=True) or {}
    scenario_name = str(data.get('scenario', 'pune')).strip().lower()
    scenario = DEMO_SCENARIOS.get(scenario_name)
    if scenario is None:
        return jsonify({
            'success': False,
            'error': 'Unknown scenario. Choose "pune" or "chennai".',
        }), 400

    demo_incidents = scenario['incidents']
    existing = {
        incident.title: incident
        for incident in Incident.query.filter(
            Incident.title.in_([item[0] for item in demo_incidents])
        ).all()
    }
    if existing:
        if len(existing) != len(demo_incidents):
            return jsonify({
                'success': False,
                'error': f'A partial {scenario["name"]} simulation scenario already exists; no records were changed.',
            }), 409
        return jsonify({
            'success': True,
            'already_initialized': True,
            'scenario': scenario_name,
            'incident_ids': [existing[item[0]].id for item in demo_incidents],
            'message': f'The deterministic simulated {scenario["name"]} scenario is already initialized.',
        })

    incidents = []
    now = datetime.utcnow()
    for title, disaster_type, severity, coordinates, affected, description in demo_incidents:
        incident = Incident(
            title=title,
            disaster_type=disaster_type,
            severity=severity,
            location_name=scenario['area'],
            latitude=coordinates[0],
            longitude=coordinates[1],
            description=description,
            reported_by='Simulation scenario',
            created_at=now,
            affected_count=affected,
            verification_status='Pending Review',
        )
        db.session.add(incident)
        incidents.append(incident)
    db.session.flush()

    for incident_index, source, reference, description, claim_type, claim_value in scenario['evidence']:
        incident = incidents[incident_index]
        db.session.add(EvidenceReport(
            incident=incident,
            source_type=source,
            source_reference=f'{scenario_name.upper()}-{reference}',
            description=description,
            claim_type=claim_type,
            claim_value=claim_value,
            observed_at=now,
            submitted_by_id=current_user.id,
        ))
        update_incident_verification(incident)
    for incident in incidents:
        record_priority_assessment(
            incident,
            f'{scenario["name"]} simulation initialized',
            current_user.id,
        )

    prefix = f'[SIM-{scenario_name.upper()}]'
    for name, specialization, members, coordinates in scenario['teams']:
        db.session.add(RescueTeam(
            name=f'{prefix} {name}',
            specialization=specialization,
            members_count=members,
            status='Available',
            latitude=coordinates[0],
            longitude=coordinates[1],
            contact_number='SIM',
        ))

    for name, category, quantity in scenario['resources']:
        db.session.add(Resource(
            name=f'{prefix} {name}',
            resource_type=category,
            total_qty=quantity,
            allocated_qty=0,
            location_name=scenario['depot'],
        ))

    shelters = []
    for name, latitude, longitude, capacity, occupancy, accessibility in scenario['shelters']:
        shelter = Shelter(
            name=f'{prefix} {name}',
            location_name=scenario['area'],
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
            information_source=f'Simulated {scenario["name"]} demonstration data',
        ))

    for name, start, end in scenario['roads']:
        db.session.add(RoadSegment(
            name=f'{prefix} {name}',
            start_lat=start[0],
            start_lng=start[1],
            end_lat=end[0],
            end_lng=end[1],
            status='Open',
            source_type='Simulated',
            source_reference='SIM-ROAD-NETWORK',
            updated_by_id=current_user.id,
            updated_at=now,
            scenario_key=scenario['scenario_key'],
        ))
    audit('demo.initialized', 'scenario', None, current_user.id, {
        'scenario_key': scenario['scenario_key'],
        'city': scenario['name'],
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
        'scenario': scenario_name,
        'incident_ids': [incident.id for incident in incidents],
        'road_segments': [
            _road_payload(segment)
            for segment in RoadSegment.query.filter_by(scenario_key=scenario['scenario_key']).all()
        ],
        'message': f'Deterministic simulated {scenario["name"]} scenario initialized. It does not represent live conditions.',
    }), 201
