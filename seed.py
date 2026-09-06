import os
from flask import Flask
from config import config_by_name
from utils.database import db
from flask_bcrypt import Bcrypt
from models.user import User
from models.sensor import Sensor
from models.incident import Incident
from models.resource import Resource
from models.team import RescueTeam
from models.shelter import Shelter
from models.route import EvacuationRoute
from models.historical import HistoricalDisaster
from models.alert import Alert
from utils.ai_engine import train_risk_model

def seed_database():
    app = Flask(__name__)
    app.config.from_object(config_by_name['dev'])
    db.init_app(app)
    bcrypt = Bcrypt(app)
    
    with app.app_context():
        db.drop_all()
        db.create_all()
        
        print("Database structure recreated.")
        
        # 1. Seed Users
        users_data = [
            ("admin", "admin@disaster.gov.in", "admin123", "admin"),
            ("responder", "responder@disaster.gov.in", "responder123", "responder"),
            ("citizen", "citizen@disaster.gov.in", "citizen123", "public")
        ]
        
        for username, email, password, role in users_data:
            pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            u = User(username=username, email=email, password_hash=pw_hash, role=role)
            db.session.add(u)
            
        print("Users seeded.")
        
        # 2. Seed IoT Sensors (Pune, Mumbai, Nashik, Kolhapur, Nagpur)
        sensors_data = [
            ("Mula Mutha Level-1", "Water Level", "Pune", 18.5204, 73.8567, 1.8, "meters", 3.5, 5.0),
            ("Mumbai Coast Tidal", "Water Level", "Mumbai", 18.9500, 72.8200, 2.5, "meters", 4.0, 6.0),
            ("Nashik Godavari Level-2", "Water Level", "Nashik", 20.0100, 73.7900, 1.2, "meters", 3.0, 4.5),
            ("Panchganga Kolhapur", "Water Level", "Kolhapur", 16.7100, 74.2500, 6.2, "meters", 5.0, 8.0), # Spiked slightly for seed state
            ("Katraj Hills Seismic", "Seismic", "Pune", 18.4500, 73.8500, 0.4, "Richter", 3.5, 5.0),
            ("Koyna Dam Seismic Monitor", "Seismic", "Kolhapur", 17.3980, 73.7538, 1.2, "Richter", 4.0, 6.0),
            ("Thermal Sensor Forest-1", "Temperature", "Nashik", 19.9500, 73.6500, 31.5, "Celsius", 42.0, 48.0),
            ("Wind Station East Coast", "Wind Speed", "Mumbai", 18.9000, 72.8000, 22.4, "km/h", 60.0, 90.0)
        ]
        
        for name, stype, loc, lat, lng, val, unit, warn, crit in sensors_data:
            # Set initial status based on threshold
            status = 'Normal'
            if val >= crit:
                status = 'Critical'
            elif val >= warn:
                status = 'Warning'
                
            s = Sensor(
                name=name, sensor_type=stype, location_name=loc,
                latitude=lat, longitude=lng, current_value=val,
                unit=unit, warning_threshold=warn, critical_threshold=crit,
                status=status
            )
            db.session.add(s)
            
        print("IoT Sensors seeded.")
        
        # 3. Seed Rescue Teams
        teams_data = [
            ("NDRF Team Alpha", "Flood Rescue", 25, 18.5204, 73.8567, "9876543210"),
            ("SDRF Team Maharashtra-1", "Search & Rescue", 20, 19.0760, 72.8777, "9876543211"),
            ("Nashik Fire Rescue Unit", "Hazmat / Fire Control", 15, 19.9975, 73.7898, "9876543212"),
            ("Kolhapur Quick Response Force", "Flood Rescue", 30, 16.7050, 74.2433, "9876543213"),
            ("Nagpur Emergency Medics", "Medical Assistance", 12, 21.1458, 79.0882, "9876543214")
        ]
        
        for name, spec, size, lat, lng, phone in teams_data:
            t = RescueTeam(
                name=name, specialization=spec, members_count=size,
                status='Available', latitude=lat, longitude=lng,
                contact_number=phone
            )
            db.session.add(t)
            
        print("Rescue Teams seeded.")
        
        # 4. Seed Shelters
        shelters_data = [
            ("Pune Municipal Community Hall", "Pune", 18.5300, 73.8600, 500, 45, 8, 7, "Good"),
            ("Mumbai Stadium Relief Center", "Mumbai", 19.0000, 72.8300, 1200, 210, 6, 5, "Good"),
            ("Nashik District School Shelter", "Nashik", 20.0200, 73.8000, 300, 0, 10, 10, "Good"),
            ("Kolhapur Temple Relief Camp", "Kolhapur", 16.7200, 74.2600, 600, 480, 2, 2, "Low"), # Low stock due to high occupancy
            ("Nagpur Sports Complex", "Nagpur", 21.1500, 79.1000, 800, 0, 12, 12, "Good")
        ]
        
        for name, loc, lat, lng, cap, occ, food, water, med in shelters_data:
            sh = Shelter(
                name=name, location_name=loc, latitude=lat, longitude=lng,
                capacity=cap, occupancy=occ, food_stock_days=food,
                water_stock_days=water, medical_stock_level=med
            )
            db.session.add(sh)
            
        print("Shelters seeded.")
        
        # 5. Seed Resources
        resources_data = [
            ("Basic Medical Kits", "Medical", 1500, 250, "Pune HQ"),
            ("Dry Food Packages", "Food", 5000, 1200, "Mumbai Depot"),
            ("Bottled Water (20L)", "Water", 3000, 1000, "Kolhapur Depot"),
            ("Inflatable Rescue Boats", "Vehicle", 50, 15, "Kolhapur Depot"),
            ("Mobile Emergency Tents", "Shelter Tent", 200, 50, "Nashik Hub"),
            ("Fire Fighting Extinguishers", "Vehicle", 100, 30, "Nashik Hub")
        ]
        
        for name, rtype, total, alloc, loc in resources_data:
            r = Resource(name=name, resource_type=rtype, total_qty=total, allocated_qty=alloc, location_name=loc)
            db.session.add(r)
            
        print("Resources seeded.")
        
        # 6. Seed Evacuation Routes
        routes_data = [
            ("Kolhapur Riverside to Temple Camp", 16.7050, 74.2433, 16.7200, 74.2600, 2.5, "Congested", "High water on approach roads"),
            ("Pune Low-lying area to Community Hall", 18.5204, 73.8567, 18.5300, 73.8600, 1.2, "Safe", None),
            ("Mumbai Coastal to Stadium Camp", 18.9500, 72.8200, 19.0000, 72.8300, 5.8, "Blocked", "Severe flooding at Worli highway")
        ]
        
        for name, slat, slng, dlat, dlng, dist, status, haz in routes_data:
            rt = EvacuationRoute(
                name=name, source_lat=slat, source_lng=slng,
                dest_lat=dlat, dest_lng=dlng, distance_km=dist,
                status=status, hazard_info=haz
            )
            db.session.add(rt)
            
        print("Evacuation Routes seeded.")
        
        # 7. Seed Incidents (Pune water level warnings & Kolhapur flood alerts)
        incidents_data = [
            ("Mula River Rising Level Alert", "flood", "High", "Pune", 18.5204, 73.8567, 
             "Mula-Mutha river bank water rising due to dam discharge. Citizen advisory issued.", "System Trigger", "Active"),
            ("Panchganga Flood Evacuation Required", "flood", "Critical", "Kolhapur", 16.7050, 74.2433,
             "River has crossed critical warning level. Immediate evacuation of low lying sectors ongoing.", "System Trigger", "Active")
        ]
        
        for title, dtype, sev, loc, lat, lng, desc, rep, status in incidents_data:
            inc = Incident(
                title=title, disaster_type=dtype, severity=sev,
                location_name=loc, latitude=lat, longitude=lng,
                description=desc, reported_by=rep, status=status
            )
            db.session.add(inc)
            
        print("Incidents seeded.")
        
        # 8. Seed Historical Disaster Data
        historical_data = [
            (2005, "Flood", "Mumbai", 1094, 250.0, "Severe"),
            (2015, "Flood", "Chennai", 500, 180.0, "Severe"),
            (2018, "Flood", "Kerala", 483, 3000.0, "Severe"),
            (2019, "Flood", "Kolhapur & Pune", 105, 50.0, "Moderate"),
            (1993, "Earthquake", "Latur", 9748, 12.0, "Severe"),
            (2001, "Earthquake", "Bhuj", 20084, 2100.0, "Severe"),
            (2020, "Cyclone", "Cyclone Nisarga (Alibaug)", 6, 80.0, "Moderate"),
            (2021, "Cyclone", "Cyclone Tauktae (West Coast)", 169, 210.0, "Severe"),
            (2014, "Landslide", "Malin (Pune District)", 151, 2.0, "Severe")
        ]
        
        for year, dtype, loc, fatal, loss, sev in historical_data:
            hd = HistoricalDisaster(
                year=year, disaster_type=dtype, location=loc,
                fatalities=fatal, estimated_loss_usd_m=loss, severity_rating=sev
            )
            db.session.add(hd)
            
        print("Historical Disasters seeded.")
        
        # 9. Seed Alerts
        a1 = Alert(
            message="Emergency: Heavy Rainfall Warning issued for Pune and Kolhapur districts for next 24 Hours.",
            severity="Critical", alert_type="Meteorological", location_name="Pune", is_active=True
        )
        a2 = Alert(
            message="Road Closure: Evacuation route from Worli Coastal to Stadium is currently BLOCKED.",
            severity="Warning", alert_type="Evacuation Command", location_name="Mumbai", is_active=True
        )
        db.session.add(a1)
        db.session.add(a2)
        
        db.session.commit()
        print("Database Seeded Successfully!")
        
    print("Training ML risk classifier model on start...")
    train_risk_model()

if __name__ == '__main__':
    seed_database()
