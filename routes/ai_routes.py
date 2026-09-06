import os
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required
from utils.ai_engine import predict_risk, analyze_satellite_image
from werkzeug.utils import secure_filename

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/ai/dashboard')
@login_required
def index():
    return render_template('ai_dashboard.html')

@ai_bp.route('/api/ai/predict', methods=['POST'])
@login_required
def risk_predict():
    data = request.get_json() or {}
    try:
        rainfall = float(data.get('rainfall', 0))
        temp = float(data.get('temperature', 25))
        water = float(data.get('water_level', 1.0))
        seismic = float(data.get('seismic', 0.5))
        wind = float(data.get('wind_speed', 15))
        humidity = float(data.get('humidity', 60))
        
        result = predict_risk(rainfall, temp, water, seismic, wind, humidity)
        return jsonify(result)
    except ValueError:
        return jsonify({'error': 'Invalid numeric parameters'}), 400

@ai_bp.route('/api/ai/analyze-image', methods=['POST'])
@login_required
def image_analyze():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file uploaded'}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    if file:
        filename = secure_filename(file.filename)
        save_path = os.path.join(current_app.config['SATELLITE_FOLDER'], filename)
        file.save(save_path)
        
        # Analyze using OpenCV engine
        result = analyze_satellite_image(save_path)
        
        # Generate URLs for original and annotated files
        result['original_url'] = f"/uploads/satellite/{filename}"
        result['annotated_url'] = f"/uploads/satellite/{result['annotated_filename']}"
        
        return jsonify(result)
        
    return jsonify({'error': 'Failed to process file'}), 500
