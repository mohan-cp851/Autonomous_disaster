from utils.database import db

class Resource(db.Model):
    __tablename__ = 'resources'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # Medical Kit, Food Package, Inflatable Boat, Fire Truck
    resource_type = db.Column(db.String(50), nullable=False) # Medical, Food, Water, Vehicle, Shelter Tent
    total_qty = db.Column(db.Integer, default=0)
    allocated_qty = db.Column(db.Integer, default=0)
    location_name = db.Column(db.String(100), nullable=False)

    @property
    def available_qty(self):
        return self.total_qty - self.allocated_qty

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'resource_type': self.resource_type,
            'total_qty': self.total_qty,
            'allocated_qty': self.allocated_qty,
            'available_qty': self.available_qty,
            'location_name': self.location_name
        }
