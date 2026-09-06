from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required

from models.incident import Incident
from models.sensor import Sensor
from models.team import RescueTeam
from models.shelter import Shelter
from models.route import EvacuationRoute
from utils.routing import get_driving_route
from utils.database import db

map_bp = Blueprint('map', __name__)


@map_bp.route('/map')
@login_required
def index():
    return render_template('map.html')


@map_bp.route('/api/map/layers')
@login_required
def map_layers():
    incidents = [i.to_dict() for i in Incident.query.all()]
    sensors = [s.to_dict() for s in Sensor.query.all()]
    teams = [t.to_dict() for t in RescueTeam.query.all()]
    shelters = [sh.to_dict() for sh in Shelter.query.all()]
    routes = [r.to_dict() for r in EvacuationRoute.query.all()]

    return jsonify({
        'incidents': incidents,
        'sensors': sensors,
        'teams': teams,
        'shelters': shelters,
        'routes': routes
    })


@map_bp.route('/api/map/route', methods=['POST'])
@login_required
def calculate_map_route():
    data = request.get_json(silent=True) or {}

    try:
        source_lat = float(data['source_lat'])
        source_lng = float(data['source_lng'])
        dest_lat = float(data['dest_lat'])
        dest_lng = float(data['dest_lng'])
    except (KeyError, TypeError, ValueError):
        return jsonify({
            'success': False,
            'error': 'Invalid source or destination coordinates.'
        }), 400

    # Validate coordinates
    if not (-90 <= source_lat <= 90 and -180 <= source_lng <= 180):
        return jsonify({
            'success': False,
            'error': 'Invalid source coordinates.'
        }), 400

    if not (-90 <= dest_lat <= 90 and -180 <= dest_lng <= 180):
        return jsonify({
            'success': False,
            'error': 'Invalid destination coordinates.'
        }), 400

    # Find matching evacuation route from database
    evacuation_route = EvacuationRoute.query.filter_by(
        source_lat=source_lat,
        source_lng=source_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng
    ).first()

    hazard_status = 'Safe'
    hazard_info = 'No hazard information available.'

    if evacuation_route:
        hazard_status = evacuation_route.status or 'Safe'
        hazard_info = evacuation_route.hazard_info or 'No hazard information available.'

    # Calculate actual driving route using OSRM
    route = get_driving_route(
        source_lat,
        source_lng,
        dest_lat,
        dest_lng
    )

    if route is None:
        return jsonify({
            'success': False,
            'error': 'Unable to calculate a driving route right now.'
        }), 502

    # Find matching evacuation route in database
    hazard_route = EvacuationRoute.query.filter(
        db.func.abs(EvacuationRoute.source_lat - source_lat) < 0.001,
        db.func.abs(EvacuationRoute.source_lng - source_lng) < 0.001,
        db.func.abs(EvacuationRoute.dest_lat - dest_lat) < 0.001,
        db.func.abs(EvacuationRoute.dest_lng - dest_lng) < 0.001
    ).first()

    # Default route status
    status = 'Safe'
    hazard_info = 'No known hazards on this corridor.'

    # Use database hazard information if route exists
    if hazard_route:
        status = hazard_route.status
        hazard_info = hazard_route.hazard_info or 'No hazard information available.'

    return jsonify({
        'success': True,
        'distance_km': route['distance_km'],
        'duration_min': route['duration_min'],
        'geometry': route['geometry'],
        'status': status,
        'hazard_info': hazard_info
    })