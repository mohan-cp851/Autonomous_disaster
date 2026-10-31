from datetime import datetime

from utils.database import db


class EvidenceReport(db.Model):
    __tablename__ = 'evidence_reports'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), nullable=False, index=True)
    source_type = db.Column(db.String(30), nullable=False)
    source_reference = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text, nullable=False)
    claim_type = db.Column(db.String(40), nullable=True)
    claim_value = db.Column(db.String(120), nullable=True)
    observed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    verification_status = db.Column(db.String(20), nullable=False, default='Pending')
    review_note = db.Column(db.String(500), nullable=True)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    incident = db.relationship('Incident', backref=db.backref('evidence_reports', lazy=True))


class RoadSegment(db.Model):
    __tablename__ = 'road_segments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    start_lat = db.Column(db.Float, nullable=False)
    start_lng = db.Column(db.Float, nullable=False)
    end_lat = db.Column(db.Float, nullable=False)
    end_lng = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Open')
    source_type = db.Column(db.String(30), nullable=False, default='Unknown')
    source_reference = db.Column(db.String(120), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    scenario_key = db.Column(db.String(60), nullable=True, index=True)


class ShelterCondition(db.Model):
    __tablename__ = 'shelter_conditions'

    id = db.Column(db.Integer, primary_key=True)
    shelter_id = db.Column(db.Integer, db.ForeignKey('shelters.id'), nullable=False, unique=True)
    accessibility_status = db.Column(db.String(20), nullable=False, default='Unknown')
    facilities = db.Column(db.Text, nullable=True)
    information_source = db.Column(db.String(120), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    shelter = db.relationship('Shelter', backref=db.backref('operational_condition', uselist=False))


class AllocationPlan(db.Model):
    __tablename__ = 'allocation_plans'

    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Proposed', index=True)
    trigger = db.Column(db.String(200), nullable=False, default='Manual optimization')
    previous_plan_id = db.Column(db.Integer, db.ForeignKey('allocation_plans.id'), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    previous_plan = db.relationship('AllocationPlan', remote_side=[id], uselist=False)
    assignments = db.relationship('AllocationAssignment', backref='plan', cascade='all, delete-orphan', lazy=True)
    supplies = db.relationship('AllocationSupply', backref='plan', cascade='all, delete-orphan', lazy=True)


class AllocationAssignment(db.Model):
    __tablename__ = 'allocation_assignments'
    __table_args__ = (
        db.UniqueConstraint('plan_id', 'incident_id', name='uq_plan_incident'),
        db.UniqueConstraint('plan_id', 'team_id', name='uq_plan_team'),
    )

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('allocation_plans.id'), nullable=False, index=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('rescue_teams.id'), nullable=False)
    travel_distance_km = db.Column(db.Float, nullable=True)
    travel_time_min = db.Column(db.Float, nullable=True)
    route_status = db.Column(db.String(40), nullable=False)
    route_geometry = db.Column(db.Text, nullable=False, default='[]')
    rationale = db.Column(db.Text, nullable=False)
    incident = db.relationship('Incident')
    team = db.relationship('RescueTeam')


class AllocationSupply(db.Model):
    __tablename__ = 'allocation_supplies'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('allocation_plans.id'), nullable=False, index=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    shortage = db.Column(db.Integer, nullable=False, default=0)
    resource = db.relationship('Resource')


class AllocationNeed(db.Model):
    __tablename__ = 'allocation_needs'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('allocation_plans.id'), nullable=False, index=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)
    requested_qty = db.Column(db.Integer, nullable=False)
    allocated_qty = db.Column(db.Integer, nullable=False)
    shortage_qty = db.Column(db.Integer, nullable=False)


class PlanApproval(db.Model):
    __tablename__ = 'plan_approvals'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('allocation_plans.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    decision = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class ReplanEvent(db.Model):
    __tablename__ = 'replan_events'

    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(120), nullable=False, unique=True)
    event_type = db.Column(db.String(40), nullable=False)
    source_type = db.Column(db.String(30), nullable=False)
    segment_id = db.Column(db.Integer, db.ForeignKey('road_segments.id'), nullable=True)
    previous_plan_id = db.Column(db.Integer, db.ForeignKey('allocation_plans.id'), nullable=True)
    new_plan_id = db.Column(db.Integer, db.ForeignKey('allocation_plans.id'), nullable=True)
    details = db.Column(db.Text, nullable=False, default='{}')
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class AuditRecord(db.Model):
    __tablename__ = 'audit_records'

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    object_type = db.Column(db.String(40), nullable=False)
    object_id = db.Column(db.Integer, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    details = db.Column(db.Text, nullable=False, default='{}')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class PriorityAssessmentRecord(db.Model):
    __tablename__ = 'priority_assessments'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id'), nullable=False, index=True)
    priority = db.Column(db.String(30), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    factors = db.Column(db.Text, nullable=False)
    rationale = db.Column(db.Text, nullable=False)
    trigger = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
