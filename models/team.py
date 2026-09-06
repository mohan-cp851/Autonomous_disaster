from utils.database import db

class RescueTeam(db.Model):
    __tablename__ = 'rescue_teams'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    specialization = db.Column(db.String(100), nullable=False) # Flood Rescue, Hazmat, Medical, Search & Rescue
    members_count = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), default='Available') # Available, Dispatched, Off-Duty
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)

    # Dispatched relation
    incidents = db.relationship('Incident', backref='dispatched_team', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'specialization': self.specialization,
            'members_count': self.members_count,
            'status': self.status,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'contact_number': self.contact_number
        }
