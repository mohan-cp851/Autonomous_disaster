from flask import Blueprint, render_template
from flask_login import login_required
from models.incident import Incident
from models.sensor import Sensor
from models.resource import Resource
from models.alert import Alert
from models.team import RescueTeam
from models.shelter import Shelter

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    # Fetch overview stats
    active_incidents_count = Incident.query.filter_by(status='Active').count()
    under_control_count = Incident.query.filter_by(status='Under Control').count()
    resolved_count = Incident.query.filter_by(status='Resolved').count()
    
    total_sensors = Sensor.query.count()
    critical_sensors = Sensor.query.filter_by(status='Critical').count()
    warning_sensors = Sensor.query.filter_by(status='Warning').count()
    
    active_alerts = Alert.query.filter_by(is_active=True).order_by(Alert.timestamp.desc()).limit(8).all()
    
    # Resource metrics
    resources = Resource.query.all()
    medical_avail = sum(r.available_qty for r in resources if r.resource_type == 'Medical')
    food_avail = sum(r.available_qty for r in resources if r.resource_type == 'Food')
    water_avail = sum(r.available_qty for r in resources if r.resource_type == 'Water')
    vehicle_avail = sum(r.available_qty for r in resources if r.resource_type == 'Vehicle')
    
    # Active teams
    dispatched_teams_count = RescueTeam.query.filter_by(status='Dispatched').count()
    available_teams_count = RescueTeam.query.filter_by(status='Available').count()
    
    # Shelter stats
    shelters = Shelter.query.all()
    total_capacity = sum(s.capacity for s in shelters)
    total_occupancy = sum(s.occupancy for s in shelters)
    
    return render_template(
        'dashboard.html',
        active_incidents=active_incidents_count,
        under_control_incidents=under_control_count,
        resolved_incidents=resolved_count,
        total_sensors=total_sensors,
        critical_sensors=critical_sensors,
        warning_sensors=warning_sensors,
        active_alerts=active_alerts,
        medical_avail=medical_avail,
        food_avail=food_avail,
        water_avail=water_avail,
        vehicle_avail=vehicle_avail,
        dispatched_teams=dispatched_teams_count,
        available_teams=available_teams_count,
        total_capacity=total_capacity,
        total_occupancy=total_occupancy
    )
