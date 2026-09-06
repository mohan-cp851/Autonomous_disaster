from utils.database import db

class Shelter(db.Model):
    __tablename__ = 'shelters'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location_name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    occupancy = db.Column(db.Integer, default=0)
    food_stock_days = db.Column(db.Integer, default=5)
    water_stock_days = db.Column(db.Integer, default=5)
    medical_stock_level = db.Column(db.String(20), default='Good') # Good, Low, Critical

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'location_name': self.location_name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'capacity': self.capacity,
            'occupancy': self.occupancy,
            'food_stock_days': self.food_stock_days,
            'water_stock_days': self.water_stock_days,
            'medical_stock_level': self.medical_stock_level,
            'vacancy': self.capacity - self.occupancy
        }
