import os
from flask import Flask, send_from_directory
from config import config_by_name
from utils.database import db
from flask_login import LoginManager
from utils.sensor_simulator import start_simulator, stop_simulator

def create_app(config_name='dev'):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Initialize extensions
    db.init_app(app)
    
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'

    # Ensure required folders exist
    os.makedirs(app.config['SATELLITE_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RESOURCES_FOLDER'], exist_ok=True)

    # User loader
    from models.user import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register Blueprints
    from routes.auth_routes import auth_bp
    from routes.dashboard_routes import dashboard_bp
    from routes.map_routes import map_bp
    from routes.incident_routes import incident_bp
    from routes.ai_routes import ai_bp
    from routes.iot_routes import iot_bp
    from routes.resource_routes import resource_bp
    from routes.command_routes import command_bp
    from routes.resources_links import resources_links_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(incident_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(iot_bp)
    app.register_blueprint(resource_bp)
    app.register_blueprint(command_bp)
    app.register_blueprint(resources_links_bp)

    # Serving satellite files
    @app.route('/uploads/satellite/<filename>')
    def serve_satellite_image(filename):
        return send_from_directory(app.config['SATELLITE_FOLDER'], filename)

    with app.app_context():
        # Make sure DB schema is created if not exists
        db.create_all()
        from utils.schema import upgrade_existing_schema
        upgrade_existing_schema()

    # Start the IoT Sensor simulator background task
    start_simulator(app)

    return app

if __name__ == '__main__':
    app = create_app('dev')
    try:
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    finally:
        stop_simulator()
