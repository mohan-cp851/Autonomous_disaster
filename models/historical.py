from utils.database import db

class HistoricalDisaster(db.Model):
    __tablename__ = 'historical_disasters'

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    disaster_type = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    fatalities = db.Column(db.Integer, default=0)
    estimated_loss_usd_m = db.Column(db.Float, default=0.0) # Loss in Millions USD
    severity_rating = db.Column(db.String(20), nullable=False) # Low, Moderate, Severe

    def to_dict(self):
        return {
            'id': self.id,
            'year': self.year,
            'disaster_type': self.disaster_type,
            'location': self.location,
            'fatalities': self.fatalities,
            'estimated_loss_usd_m': self.estimated_loss_usd_m,
            'severity_rating': self.severity_rating
        }
