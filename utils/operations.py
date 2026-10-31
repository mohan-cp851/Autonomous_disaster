import heapq
import json
import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from scipy.optimize import linear_sum_assignment

from models.incident import Incident
from models.operations import (
    AllocationAssignment,
    AllocationNeed,
    AllocationPlan,
    AllocationSupply,
    AuditRecord,
    EvidenceReport,
    PriorityAssessmentRecord,
    RoadSegment,
    ShelterCondition,
)
from models.resource import Resource
from models.shelter import Shelter
from models.team import RescueTeam
from utils.database import db


SOURCE_RELIABILITY = {
    'Government': 0.75,
    'Field Team': 0.80,
    'Sensor': 0.70,
    'Citizen': 0.45,
    'Simulated': 0.50,
    'Unknown': 0.35,
}
SEVERITY_SCORE = {'Critical': 100, 'High': 75, 'Medium': 50, 'Low': 25}
STALE_AFTER_HOURS = 24
EARTH_RADIUS_KM = 6371.0
MAXIMUM_SNAP_DISTANCE_KM = 3.0


def parse_datetime(value, field_name='timestamp'):
    if not value:
        return datetime.utcnow()
    if not isinstance(value, str):
        raise ValueError(f'{field_name} must be an ISO-8601 string.')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'{field_name} must be an ISO-8601 timestamp.') from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    delta_lat = lat2 - lat1
    delta_lng = lng2 - lng1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _normalized(value):
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


def _source_key(report):
    if report.source_reference:
        return f'ref:{_normalized(report.source_reference)}'
    return f'type:{report.source_type}'


def _evidence_conflicts(reports):
    usable = sorted([
        report for report in reports
        if report.claim_type and report.claim_value
        and report.verification_status not in ('Rejected', 'Inconclusive', 'Superseded')
    ], key=lambda report: report.observed_at, reverse=True)
    unique_reports = []
    seen_references = set()
    for report in usable:
        if report.source_reference:
            source_key = _source_key(report)
            if source_key in seen_references:
                continue
            seen_references.add(source_key)
        unique_reports.append(report)

    conflicts = []
    for index, first in enumerate(unique_reports):
        for second in unique_reports[index + 1:]:
            if (
                first.claim_type == second.claim_type
                and _normalized(first.claim_value) != _normalized(second.claim_value)
            ):
                conflicts.append({
                    'claim_type': first.claim_type,
                    'reports': [
                        {'id': first.id, 'value': first.claim_value, 'source': first.source_type},
                        {'id': second.id, 'value': second.claim_value, 'source': second.source_type},
                    ],
                    'status': 'Unresolved',
                })
    return conflicts


def evidence_assessment(incident, now=None):
    now = now or datetime.utcnow()
    reports = sorted(incident.evidence_reports, key=lambda report: report.observed_at, reverse=True)
    included = [
        report for report in reports
        if report.verification_status not in ('Rejected', 'Inconclusive', 'Superseded')
    ]
    conflicts = _evidence_conflicts(reports)

    independent_sources = {}
    stale_ids = []
    for report in included:
        age_hours = max(0.0, (now - report.observed_at).total_seconds() / 3600)
        freshness = max(0.25, 1 - age_hours / 168)
        if age_hours > STALE_AFTER_HOURS:
            stale_ids.append(report.id)
        source_key = _source_key(report)
        quality = SOURCE_RELIABILITY.get(report.source_type, SOURCE_RELIABILITY['Unknown']) * freshness
        independent_sources[source_key] = max(independent_sources.get(source_key, 0), quality)

    if independent_sources:
        base_quality = max(independent_sources.values())
        corroboration = min(0.20, max(0, len(independent_sources) - 1) * 0.10)
        verified_bonus = 0.10 if any(
            report.verification_status == 'Verified' for report in included
        ) else 0
        conflict_penalty = 0.20 if conflicts else 0
        confidence = round(max(0, min(100, 100 * (
            base_quality + corroboration + verified_bonus - conflict_penalty
        ))))
    else:
        corroboration = 0
        verified_bonus = 0
        conflict_penalty = 0
        confidence = 0

    duplicate_groups = []
    for index, first in enumerate(reports):
        for second in reports[index + 1:]:
            same_reference = bool(
                first.source_reference
                and _normalized(first.source_reference) == _normalized(second.source_reference)
            )
            close_in_time = abs((first.observed_at - second.observed_at).total_seconds()) <= 3600
            similar_text = SequenceMatcher(
                None, _normalized(first.description), _normalized(second.description)
            ).ratio() >= 0.88
            if same_reference or (close_in_time and similar_text):
                duplicate_groups.append({'report_ids': [first.id, second.id]})

    if not included:
        reason = 'No active evidence has been submitted.'
    else:
        reason = (
            f'Highest source/freshness contribution {max(independent_sources.values()) * 100:.0f}; '
            f'{len(independent_sources)} independent source group(s), '
            f'{len(conflicts)} unresolved conflict(s).'
        )
    if stale_ids:
        reason += f' Evidence reports {", ".join(map(str, stale_ids))} are older than 24 hours.'

    return {
        'confidence_score': confidence,
        'label': 'Evidence-confidence score; not a calibrated probability.',
        'source_breakdown': _source_breakdown(reports),
        'evidence': [_evidence_payload(report, now) for report in reports],
        'conflicts': conflicts,
        'potential_duplicate_reports': duplicate_groups,
        'stale_report_ids': stale_ids,
        'independent_source_groups': len(independent_sources),
        'reason': reason,
        'updated_at': now.isoformat(timespec='seconds') + 'Z',
        'calculation': {
            'maximum_source_quality': round(max(independent_sources.values(), default=0), 3),
            'corroboration_bonus': round(corroboration, 3),
            'verified_evidence_bonus': round(verified_bonus, 3),
            'conflict_penalty': round(conflict_penalty, 3),
        },
    }


def _source_breakdown(reports):
    counts = {}
    for report in reports:
        counts[report.source_type] = counts.get(report.source_type, 0) + 1
    return counts


def _evidence_payload(report, now=None):
    now = now or datetime.utcnow()
    age_hours = max(0.0, (now - report.observed_at).total_seconds() / 3600)
    return {
        'id': report.id,
        'source_type': report.source_type,
        'source_reference': report.source_reference,
        'description': report.description,
        'claim_type': report.claim_type,
        'claim_value': report.claim_value,
        'observed_at': report.observed_at.isoformat(timespec='seconds') + 'Z',
        'age_hours': round(age_hours, 1),
        'is_stale': age_hours > STALE_AFTER_HOURS,
        'verification_status': report.verification_status,
        'review_note': report.review_note,
    }


def update_incident_verification(incident):
    reports = [
        report for report in incident.evidence_reports
        if report.verification_status not in ('Rejected', 'Inconclusive', 'Superseded')
    ]
    conflicts = _evidence_conflicts(reports)
    if conflicts:
        incident.verification_status = 'Conflicting'
    elif any(report.verification_status == 'Verified' for report in reports):
        incident.verification_status = 'Verified'
    elif reports:
        incident.verification_status = 'Pending Review'
    else:
        incident.verification_status = 'Unverified'


def priority_assessment(incident):
    evidence = evidence_assessment(incident)
    confidence = evidence['confidence_score']
    severity_points = SEVERITY_SCORE.get(incident.severity, 25)
    affected_points = min(25, max(0, incident.affected_count) * 0.25)
    evidence_points = confidence * 0.30
    score = round(min(100, severity_points * 0.70 + affected_points + evidence_points))
    if (
        incident.verification_status != 'Verified'
        and (not evidence['evidence'] or confidence < 30)
    ):
        category = 'Needs Verification'
    elif score >= 85:
        category = 'Critical'
    elif score >= 65:
        category = 'High'
    elif score >= 40:
        category = 'Moderate'
    else:
        category = 'Low'

    factors = [
        {'name': 'Reported severity', 'value': incident.severity, 'points': round(severity_points * 0.70)},
        {'name': 'People potentially affected', 'value': incident.affected_count, 'points': round(affected_points)},
        {'name': 'Evidence confidence', 'value': confidence, 'points': round(evidence_points)},
    ]
    rationale = (
        f'{category}: severity contributes {round(severity_points * 0.70)} points, '
        f'known impact contributes {round(affected_points)}, and evidence contributes '
        f'{round(evidence_points)}. {evidence["reason"]}'
    )
    return {
        'incident_id': incident.id,
        'priority': category,
        'score': score,
        'factors': factors,
        'rationale': rationale,
        'verification_status': incident.verification_status,
        'evidence': evidence,
    }


def incident_duplicates(incident, incidents=None):
    possible_matches = (
        Incident.query.filter(Incident.id != incident.id).all()
        if incidents is None else incidents
    )
    suggestions = []

    incident_text = _normalized(f'{incident.title} {incident.description}')
    for candidate in possible_matches:
        if candidate.id == incident.id:
            continue
        if _normalized(candidate.disaster_type) != _normalized(incident.disaster_type):
            continue
        distance = haversine_km(
            incident.latitude, incident.longitude, candidate.latitude, candidate.longitude
        )
        hours = abs((incident.created_at - candidate.created_at).total_seconds()) / 3600
        similarity = SequenceMatcher(
            None, incident_text, _normalized(f'{candidate.title} {candidate.description}')
        ).ratio()
        if distance <= 2 and hours <= 48 and similarity >= 0.35:
            suggestions.append({
                'incident_id': candidate.id,
                'title': candidate.title,
                'distance_km': round(distance, 2),
                'time_difference_hours': round(hours, 1),
                'description_similarity': round(similarity, 2),
                'review_required': True,
            })
    return suggestions


def _network_route(source, destination):
    segments = RoadSegment.query.all()
    straight_distance = haversine_km(*source, *destination)
    if not segments:
        return {
            'distance_km': round(straight_distance, 2),
            'duration_min': round(straight_distance / 25 * 60, 1),
            'geometry': [],
            'status': 'Unknown: no road network',
            'note': 'Straight-line distance estimate only; no route or safety claim is available.',
        }

    graph = {}
    for segment in segments:
        start = (segment.start_lat, segment.start_lng)
        end = (segment.end_lat, segment.end_lng)
        graph.setdefault(start, [])
        graph.setdefault(end, [])
        if segment.status not in ('Closed', 'Blocked'):
            length = haversine_km(*start, *end)
            graph[start].append((end, length))
            graph[end].append((start, length))

    def nearest_node(point):
        if not graph:
            return None, None
        node = min(graph, key=lambda item: haversine_km(*point, *item))
        distance = haversine_km(*point, *node)
        if distance > MAXIMUM_SNAP_DISTANCE_KM:
            return None, distance
        return node, distance

    start_node, start_connector = nearest_node(source)
    end_node, end_connector = nearest_node(destination)
    if start_node is None or end_node is None:
        return {
            'distance_km': round(straight_distance, 2),
            'duration_min': round(straight_distance / 25 * 60, 1),
            'geometry': [],
            'status': 'Unknown: locations outside road network',
            'note': 'Straight-line estimate only; locations are not connected to the stored road graph.',
        }

    distances = {start_node: start_connector}
    previous = {}
    queue = [(start_connector, start_node)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        if node == end_node:
            break
        for neighbor, edge_distance in graph[node]:
            candidate_distance = distance + edge_distance
            if candidate_distance < distances.get(neighbor, float('inf')):
                distances[neighbor] = candidate_distance
                previous[neighbor] = node
                heapq.heappush(queue, (candidate_distance, neighbor))

    if end_node not in distances:
        return {
            'distance_km': None,
            'duration_min': None,
            'geometry': [],
            'status': 'Unavailable: no open path',
            'note': 'No path exists through currently open stored road segments.',
        }

    path = [end_node]
    while path[-1] != start_node:
        path.append(previous[path[-1]])
    path.reverse()
    geometry = [[source[0], source[1]]]
    geometry.extend([[node[0], node[1]] for node in path])
    geometry.append([destination[0], destination[1]])
    distance_km = distances[end_node] + end_connector
    return {
        'distance_km': round(distance_km, 2),
        'duration_min': round(distance_km / 30 * 60, 1),
        'geometry': geometry,
        'status': 'Calculated from stored road graph',
        'note': 'Graph distance estimate; road safety has not been independently verified.',
    }


def _team_capability(team, disaster_type):
    capabilities = {
        'flood': {'flood', 'boat', 'water', 'rescue', 'search'},
        'tsunami': {'flood', 'boat', 'water', 'rescue', 'search'},
        'fire': {'fire', 'hazmat', 'rescue', 'search'},
        'earthquake': {'earthquake', 'search', 'rescue', 'medical'},
        'landslide': {'landslide', 'search', 'rescue', 'medical'},
        'cyclone': {'cyclone', 'search', 'rescue', 'medical'},
    }
    spec = _normalized(team.specialization)
    matching = capabilities.get(_normalized(disaster_type), {'search', 'rescue', 'medical'})
    matched = {term for term in matching if term in spec}
    if not matched:
        return 0
    return 2 if _normalized(disaster_type) in spec else 1


def active_incidents():
    return Incident.query.filter(Incident.status != 'Resolved').all()


def _inventory_needs(plan, incidents):
    type_needs = {
        'flood': ('Medical', 'Food', 'Water'),
        'tsunami': ('Medical', 'Food', 'Water'),
        'earthquake': ('Medical', 'Food', 'Water'),
        'cyclone': ('Medical', 'Food', 'Water'),
        'landslide': ('Medical', 'Food', 'Water'),
        'fire': ('Medical',),
    }
    remaining = {
        item.id: max(0, item.available_qty)
        for item in Resource.query.order_by(Resource.id).all()
    }
    resources = {item.id: item for item in Resource.query.order_by(Resource.id).all()}
    for incident in incidents:
        planning_population = incident.affected_count or 10
        demand = max(1, math.ceil(planning_population / 20))
        for resource_type in type_needs.get(_normalized(incident.disaster_type), ('Medical',)):
            requested = demand
            allocated = 0
            matching_resources = [
                item for item in resources.values()
                if _normalized(item.resource_type) == _normalized(resource_type)
            ]
            for item in matching_resources:
                quantity = min(requested - allocated, remaining[item.id])
                if quantity > 0:
                    db.session.add(AllocationSupply(
                        plan_id=plan.id,
                        incident_id=incident.id,
                        resource_id=item.id,
                        quantity=quantity,
                        shortage=0,
                    ))
                    remaining[item.id] -= quantity
                    allocated += quantity
                if allocated == requested:
                    break
            db.session.add(AllocationNeed(
                plan_id=plan.id,
                incident_id=incident.id,
                resource_type=resource_type,
                requested_qty=requested,
                allocated_qty=allocated,
                shortage_qty=max(0, requested - allocated),
            ))


def create_allocation_plan(user_id, trigger='Manual optimization', previous_plan=None):
    incidents = sorted(
        active_incidents(),
        key=lambda incident: (
            -priority_assessment(incident)['score'],
            incident.created_at,
            incident.id,
        ),
    )
    eligible_teams = RescueTeam.query.filter_by(status='Available').order_by(RescueTeam.id).all()
    version = (db.session.query(db.func.max(AllocationPlan.version)).scalar() or 0) + 1
    plan = AllocationPlan(
        version=version,
        status='Proposed',
        trigger=trigger[:200],
        previous_plan_id=previous_plan.id if previous_plan else None,
        created_by_id=user_id,
    )
    db.session.add(plan)
    db.session.flush()

    previous_proposals = AllocationPlan.query.filter_by(status='Proposed').filter(
        AllocationPlan.id != plan.id
    ).all()
    for old_plan in previous_proposals:
        old_plan.status = 'Superseded'

    if incidents and eligible_teams:
        dummy_count = len(incidents)
        scores = []
        routes = {}
        priorities = {}
        for incident in incidents:
            priorities[incident.id] = priority_assessment(incident)
            row = []
            for team in eligible_teams:
                capability = _team_capability(team, incident.disaster_type)
                required_capacity = max(1, incident.affected_count)
                if capability == 0 or team.members_count * 10 < required_capacity:
                    row.append(-1_000_000)
                    continue
                route = _network_route(
                    (team.latitude, team.longitude),
                    (incident.latitude, incident.longitude),
                )
                routes[(incident.id, team.id)] = route
                if route['status'] == 'Unavailable: no open path':
                    row.append(-1_000_000)
                    continue
                travel = route['duration_min'] or 0
                row.append(
                    priorities[incident.id]['score'] * 100
                    + capability * 25
                    - travel * 3
                )
            row.extend([0] * dummy_count)
            scores.append(row)

        row_indexes, column_indexes = linear_sum_assignment(scores, maximize=True)
        for row_index, column_index in zip(row_indexes, column_indexes):
            incident = incidents[row_index]
            if column_index >= len(eligible_teams) or scores[row_index][column_index] <= 0:
                continue
            team = eligible_teams[column_index]
            route = routes[(incident.id, team.id)]
            priority = priorities[incident.id]
            capacity = team.members_count * 10
            rationale = (
                f'{team.specialization} matches {incident.disaster_type}; '
                f'priority score {priority["score"]}/100. '
                f'{route["note"]} Team planning capacity: {capacity} people.'
            )
            db.session.add(AllocationAssignment(
                plan_id=plan.id,
                incident_id=incident.id,
                team_id=team.id,
                travel_distance_km=route['distance_km'],
                travel_time_min=route['duration_min'],
                route_status=route['status'],
                route_geometry=json.dumps(route['geometry']),
                rationale=rationale,
            ))
    _inventory_needs(plan, incidents)
    db.session.flush()
    return plan


def plan_payload(plan):
    assignments = []
    assigned_ids = set()
    for assignment in sorted(plan.assignments, key=lambda item: item.incident_id):
        priority = priority_assessment(assignment.incident)
        assignments.append({
            'incident_id': assignment.incident_id,
            'incident_title': assignment.incident.title,
            'priority': priority['priority'],
            'priority_score': priority['score'],
            'team_id': assignment.team_id,
            'team_name': assignment.team.name,
            'travel_distance_km': assignment.travel_distance_km,
            'travel_time_min': assignment.travel_time_min,
            'route_status': assignment.route_status,
            'route_geometry': json.loads(assignment.route_geometry or '[]'),
            'rationale': assignment.rationale,
        })
        assigned_ids.add(assignment.incident_id)
    unserved = [
        {
            'incident_id': incident.id,
            'title': incident.title,
            'priority': priority_assessment(incident)['priority'],
            'reason': 'No available team satisfies capability, capacity, and current route constraints.',
        }
        for incident in active_incidents()
        if incident.id not in assigned_ids
    ]
    needs = [{
        'incident_id': need.incident_id,
        'incident_title': db.session.get(Incident, need.incident_id).title,
        'resource_type': need.resource_type,
        'requested_qty': need.requested_qty,
        'allocated_qty': need.allocated_qty,
        'shortage_qty': need.shortage_qty,
    } for need in AllocationNeed.query.filter_by(plan_id=plan.id).all()]
    supplies = [{
        'incident_id': item.incident_id,
        'incident_title': db.session.get(Incident, item.incident_id).title,
        'resource_id': item.resource_id,
        'resource_name': item.resource.name,
        'quantity': item.quantity,
    } for item in AllocationSupply.query.filter_by(plan_id=plan.id).all()]
    return {
        'id': plan.id,
        'version': plan.version,
        'status': plan.status,
        'trigger': plan.trigger,
        'previous_plan_id': plan.previous_plan_id,
        'created_at': plan.created_at.isoformat(timespec='seconds') + 'Z',
        'assignments': assignments,
        'unserved_incidents': unserved,
        'resource_needs': needs,
        'resource_allocations': supplies,
        'constraints': [
            'Teams can appear at most once in a plan.',
            'Only teams marked Available are considered.',
            'Capability, team planning capacity, and open-road-path constraints are enforced.',
            'Proposals do not dispatch teams or reserve physical inventory.',
        ],
    }


def compare_plans(previous, proposed):
    old_assignments = {
        item.incident_id: item for item in (previous.assignments if previous else [])
    }
    new_assignments = {item.incident_id: item for item in proposed.assignments}
    retained = []
    changed = []
    added = []
    removed = []

    for incident_id, new_item in new_assignments.items():
        old_item = old_assignments.get(incident_id)
        new_data = {
            'incident_id': incident_id,
            'incident_title': new_item.incident.title,
            'team_id': new_item.team_id,
            'team_name': new_item.team.name,
            'travel_distance_km': new_item.travel_distance_km,
            'travel_time_min': new_item.travel_time_min,
            'route_status': new_item.route_status,
        }
        if not old_item:
            added.append(new_data)
        elif old_item.team_id == new_item.team_id:
            retained.append({
                **new_data,
                'previous_travel_time_min': old_item.travel_time_min,
                'travel_time_change_min': round(
                    (new_item.travel_time_min or 0) - (old_item.travel_time_min or 0), 1
                ),
                'route_changed': old_item.route_status != new_item.route_status
                    or old_item.route_geometry != new_item.route_geometry,
            })
        else:
            changed.append({
                **new_data,
                'previous_team_id': old_item.team_id,
                'previous_team_name': old_item.team.name,
                'reason': new_item.rationale,
            })

    for incident_id, old_item in old_assignments.items():
        if incident_id not in new_assignments:
            removed.append({
                'incident_id': incident_id,
                'incident_title': old_item.incident.title,
                'previous_team_id': old_item.team_id,
                'previous_team_name': old_item.team.name,
                'reason': 'No feasible team remains under the updated constraints.',
            })

    new_plan_payload = plan_payload(proposed)
    previous_unserved = (
        plan_payload(previous)['unserved_incidents'] if previous else [
            {'incident_id': incident.id, 'title': incident.title}
            for incident in active_incidents()
        ]
    )
    return {
        'previous_plan_id': previous.id if previous else None,
        'new_plan_id': proposed.id,
        'new_assignments': added,
        'changed_assignments': changed,
        'retained_assignments': retained,
        'removed_assignments': removed,
        'unserved_before': previous_unserved,
        'unserved_after': new_plan_payload['unserved_incidents'],
    }


def audit(action, object_type, object_id, user_id, details):
    db.session.add(AuditRecord(
        action=action,
        object_type=object_type,
        object_id=object_id,
        user_id=user_id,
        details=json.dumps(details, sort_keys=True),
    ))


def shelter_payload(shelter):
    condition = ShelterCondition.query.filter_by(shelter_id=shelter.id).first()
    vacancy = max(0, shelter.capacity - shelter.occupancy)
    return {
        **shelter.to_dict(),
        'vacancy': vacancy,
        'accessibility_status': condition.accessibility_status if condition else 'Unknown',
        'facilities': condition.facilities if condition else None,
        'information_source': condition.information_source if condition else None,
        'information_updated_at': (
            condition.updated_at.isoformat(timespec='seconds') + 'Z' if condition else None
        ),
        'information_freshness': 'Unknown' if condition is None else 'Recorded',
    }


def recommend_shelters(latitude, longitude, people=1):
    shelters = []
    for shelter in Shelter.query.all():
        item = shelter_payload(shelter)
        distance = haversine_km(latitude, longitude, shelter.latitude, shelter.longitude)
        item['distance_km'] = round(distance, 2)
        item['feasible_for_requested_capacity'] = (
            item['vacancy'] >= people
            and item['accessibility_status'] != 'Inaccessible'
        )
        shelters.append(item)
    return sorted(
        shelters,
        key=lambda item: (
            not item['feasible_for_requested_capacity'],
            item['distance_km'],
            item['id'],
        ),
    )
