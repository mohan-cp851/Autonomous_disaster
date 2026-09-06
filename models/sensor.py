from datetime import datetime
from utils.database import db

class Sensor(db.Model):
    __tablename__ = 'sensors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    sensor_type = db.Column(db.String(50), nullable=False) # Seismic, Water Level, Temperature, Wind Speed
    location_name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    current_value = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(20), nullable=False)
    warning_threshold = db.Column(db.Float, nullable=False)
    critical_threshold = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Normal') # Normal, Warning, Critical
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'sensor_type': self.sensor_type,
            'location_name': self.location_name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'current_value': round(self.current_value, 2),
            'unit': self.unit,
            'warning_threshold': self.warning_threshold,
            'critical_threshold': self.critical_threshold,
            'status': self.status,
            'last_updated': self.last_updated.strftime('%Y-%m-%d %H:%M:%S')
        }
