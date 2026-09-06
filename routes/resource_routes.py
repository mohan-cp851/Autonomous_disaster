from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models.resource import Resource
from models.team import RescueTeam
from models.shelter import Shelter
from models.route import EvacuationRoute
from utils.database import db

resource_bp = Blueprint('resources', __name__)

@resource_bp.route('/resources')
@login_required
def index():
    resources = Resource.query.all()
    teams = RescueTeam.query.all()
    shelters = Shelter.query.all()
    routes = EvacuationRoute.query.all()
    return render_template(
        'resources.html',
        resources=resources,
        teams=teams,
        shelters=shelters,
        routes=routes
    )

@resource_bp.route('/api/resources/allocate', methods=['POST'])
@login_required
def allocate_resource():
    if current_user.role != 'admin':
        return jsonify({'error': 'Only Admins can allocate physical resources'}), 403
        
    data = request.get_json() or {}
    res_id = data.get('resource_id')
    qty = int(data.get('qty', 0))
    
    resource = Resource.query.get(res_id)
    if not resource:
        return jsonify({'error': 'Resource not found'}), 404
        
    if qty <= resource.available_qty:
        resource.allocated_qty += qty
        db.session.commit()
        return jsonify({'message': f'Allocated {qty} units of {resource.name}'})
        
    return jsonify({'error': 'Insufficient inventory available'}), 400

@resource_bp.route('/api/shelters/<int:id>/update', methods=['POST'])
@login_required
def update_shelter(id):
    if current_user.role not in ['admin', 'responder']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    shelter = Shelter.query.get_or_404(id)
    data = request.get_json() or {}
    
    if 'occupancy' in data:
        new_occupancy = int(data['occupancy'])
        if new_occupancy <= shelter.capacity:
            shelter.occupancy = new_occupancy
        else:
            return jsonify({'error': 'Occupancy cannot exceed total capacity'}), 400
            
    if 'food_stock_days' in data:
        shelter.food_stock_days = int(data['food_stock_days'])
        
    if 'water_stock_days' in data:
        shelter.water_stock_days = int(data['water_stock_days'])
        
    db.session.commit()
    return jsonify({'message': 'Shelter status updated successfully'})

@resource_bp.route('/api/routes/create', methods=['POST'])
@login_required
def create_route():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.get_json() or {}
    try:
        new_route = EvacuationRoute(
            name=data['name'],
            source_lat=float(data['source_lat']),
            source_lng=float(data['source_lng']),
            dest_lat=float(data['dest_lat']),
            dest_lng=float(data['dest_lng']),
            distance_km=float(data['distance_km']),
            status=data.get('status', 'Safe'),
            hazard_info=data.get('hazard_info', '')
        )
        db.session.add(new_route)
        db.session.commit()
        return jsonify({'message': 'Evacuation route created successfully'})
    except (KeyError, ValueError) as e:
        return jsonify({'error': f'Invalid arguments: {e}'}), 400
