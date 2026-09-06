from utils.database import db

class EvacuationRoute(db.Model):
    __tablename__ = 'evacuation_routes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    source_lat = db.Column(db.Float, nullable=False)
    source_lng = db.Column(db.Float, nullable=False)
    dest_lat = db.Column(db.Float, nullable=False)
    dest_lng = db.Column(db.Float, nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default='Safe') # Safe, Congested, Blocked
    hazard_info = db.Column(db.String(200), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'source_lat': self.source_lat,
            'source_lng': self.source_lng,
            'dest_lat': self.dest_lat,
            'dest_lng': self.dest_lng,
            'distance_km': self.distance_km,
            'status': self.status,
            'hazard_info': self.hazard_info
        }
