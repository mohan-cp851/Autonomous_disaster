from datetime import datetime
from utils.database import db

class Incident(db.Model):
    __tablename__ = 'incidents'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    disaster_type = db.Column(db.String(50), nullable=False)  # flood, earthquake, fire, cyclone, landslide, tsunami
    severity = db.Column(db.String(20), nullable=False)      # Low, Medium, High, Critical
    location_name = db.Column(db.String(150), nullable=False) # Pune, Mumbai, etc.
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='Active', nullable=False) # Active, Under Control, Resolved
    reported_by = db.Column(db.String(100), default='System', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    affected_count = db.Column(db.Integer, nullable=False, default=0)
    verification_status = db.Column(db.String(20), nullable=False, default='Unverified')

    # Dispatched rescue team relation
    dispatched_team_id = db.Column(db.Integer, db.ForeignKey('rescue_teams.id'), nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'disaster_type': self.disaster_type,
            'severity': self.severity,
            'location_name': self.location_name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'description': self.description,
            'status': self.status,
            'reported_by': self.reported_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'dispatched_team_id': self.dispatched_team_id,
            'affected_count': self.affected_count,
            'verification_status': self.verification_status
        }
