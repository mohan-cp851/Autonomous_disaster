from datetime import datetime
from utils.database import db

class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(250), nullable=False)
    severity = db.Column(db.String(20), nullable=False) # Warning, Critical, Info
    alert_type = db.Column(db.String(30), default='System') # IoT Threshold, Manual, Prediction
    location_name = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'message': self.message,
            'severity': self.severity,
            'alert_type': self.alert_type,
            'location_name': self.location_name,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'is_active': self.is_active
        }
