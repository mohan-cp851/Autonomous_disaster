from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from utils.chatbot import ask_copilot

copilot_bp = Blueprint('copilot', __name__)

@copilot_bp.route('/copilot')
@login_required
def index():
    return render_template('copilot.html')

@copilot_bp.route('/api/copilot/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'Query cannot be empty'}), 400
        
    response_text = ask_copilot(query)
    return jsonify({'response': response_text})
