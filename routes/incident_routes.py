from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models.incident import Incident
from models.operations import EvidenceReport
from models.team import RescueTeam
from utils.database import db
from utils.operations import audit

incident_bp = Blueprint('incident', __name__)

@incident_bp.route('/incidents', methods=['GET', 'POST'])
@login_required
def list_incidents():
    if request.method == 'POST':
        title = request.form.get('title')
        disaster_type = request.form.get('disaster_type')
        severity = request.form.get('severity')
        location_name = request.form.get('location_name')
        source_type = request.form.get('source_type', 'Citizen')
        try:
            affected_count = int(request.form.get('affected_count', '0'))
        except ValueError:
            flash('Potentially affected people must be a whole number.', 'danger')
            return redirect(url_for('incident.list_incidents'))

        if affected_count < 0 or affected_count > 1_000_000:
            flash('Potentially affected people must be between 0 and 1,000,000.', 'danger')
            return redirect(url_for('incident.list_incidents'))
        if source_type not in {'Government', 'Field Team', 'Sensor', 'Citizen', 'Simulated', 'Unknown'}:
            flash('Select a valid report source.', 'danger')
            return redirect(url_for('incident.list_incidents'))
        
        # Geocode fallbacks for Pune, Mumbai, etc.
        coords = {
            'Pune': (18.5204, 73.8567),
            'Mumbai': (19.0760, 72.8777),
            'Nashik': (19.9975, 73.7898),
            'Kolhapur': (16.7050, 74.2433),
            'Nagpur': (21.1458, 79.0882)
        }
        lat, lng = coords.get(location_name, (18.5204, 73.8567))
        
        description = request.form.get('description')
        
        new_inc = Incident(
            title=title,
            disaster_type=disaster_type,
            severity=severity,
            location_name=location_name,
            latitude=lat,
            longitude=lng,
            description=description,
            reported_by=current_user.username,
            affected_count=affected_count,
            verification_status='Pending Review'
        )
        db.session.add(new_inc)
        db.session.flush()
        db.session.add(EvidenceReport(
            incident=new_inc,
            source_type=source_type,
            description=description or title,
            submitted_by_id=current_user.id,
        ))
        audit('incident.created', 'incident', new_inc.id, current_user.id, {
            'source_type': source_type,
        })
        db.session.commit()
        flash('Incident reported successfully!', 'success')
        return redirect(url_for('incident.list_incidents'))
        
    incidents = Incident.query.order_by(Incident.created_at.desc()).all()
    available_teams = RescueTeam.query.filter_by(status='Available').all()
    return render_template('incidents.html', incidents=incidents, available_teams=available_teams)

@incident_bp.route('/api/incidents/<int:id>/status', methods=['POST'])
@login_required
def update_status(id):
    if current_user.role not in ['admin', 'responder']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    incident = Incident.query.get_or_404(id)
    data = request.get_json()
    status = data.get('status')
    
    if status in ['Active', 'Under Control', 'Resolved']:
        incident.status = status
        # If resolved, free up dispatched team
        if status == 'Resolved' and incident.dispatched_team:
            incident.dispatched_team.status = 'Available'
            incident.dispatched_team_id = None
        db.session.commit()
        return jsonify({'message': 'Status updated successfully'})
    return jsonify({'error': 'Invalid status'}), 400

@incident_bp.route('/api/incidents/<int:id>/dispatch', methods=['POST'])
@login_required
def dispatch_team(id):
    if current_user.role not in ['admin', 'responder']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    incident = Incident.query.get_or_404(id)
    data = request.get_json()
    team_id = data.get('team_id')
    
    team = RescueTeam.query.get(team_id)
    if team and team.status == 'Available':
        # Free old team if exists
        if incident.dispatched_team:
            incident.dispatched_team.status = 'Available'
            
        incident.dispatched_team_id = team.id
        team.status = 'Dispatched'
        
        # Update incident status to Active or Under Control
        if incident.status == 'Active':
            incident.status = 'Under Control'
            
        db.session.commit()
        return jsonify({'message': f'Rescue Team {team.name} dispatched successfully'})
        
    return jsonify({'error': 'Team unavailable or invalid'}), 400
