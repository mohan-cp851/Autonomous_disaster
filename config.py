import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'disaster-response-secret-key-99999')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "database.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload Directories
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    SATELLITE_FOLDER = os.path.join(UPLOAD_FOLDER, 'satellite')
    RESOURCES_FOLDER = os.path.join(UPLOAD_FOLDER, 'resources')
    
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    ALLOWED_DOC_EXTENSIONS = {'pdf', 'docx', 'csv', 'xlsx'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Ollama AI Configurations
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'qwen2.5-coder:7b')

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

config_by_name = {
    'dev': DevelopmentConfig,
    'prod': ProductionConfig,
    'test': TestingConfig
}
