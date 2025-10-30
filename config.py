"""
Configuration settings for ArtLens
"""
import os
from datetime import timedelta

class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///artlens.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # AI API Keys (set these as environment variables)
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    AZURE_VISION_KEY = os.environ.get('AZURE_VISION_KEY', '')
    AZURE_VISION_ENDPOINT = os.environ.get('AZURE_VISION_ENDPOINT', '')
    
    # Google Custom Search API (for finding artwork images)
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
    GOOGLE_CSE_ID = os.environ.get('GOOGLE_CSE_ID', '')  # Custom Search Engine ID
    
    # Badge thresholds
    BADGES = {
        'first_discovery': {
            'name': 'First Discovery',
            'description': 'Discovered your first artwork',
            'icon': 'logo',
            'requirement': 'artworks_discovered >= 1'
        },
        'art_explorer': {
            'name': 'Art Explorer',
            'description': 'Discovered 10 artworks',
            'icon': 'fas fa-search',
            'requirement': 'artworks_discovered >= 10'
        },
        'museum_master': {
            'name': 'Museum Master',
            'description': 'Discovered 50 artworks',
            'icon': 'fas fa-university',
            'requirement': 'artworks_discovered >= 50'
        },
        'quiz_novice': {
            'name': 'Quiz Novice',
            'description': 'Completed 5 quizzes',
            'icon': 'fas fa-edit',
            'requirement': 'quizzes_completed >= 5'
        },
        'art_historian': {
            'name': 'Art Historian',
            'description': 'Completed 20 quizzes',
            'icon': 'fas fa-book',
            'requirement': 'quizzes_completed >= 20'
        },
        'impressionist_expert': {
            'name': 'Impressionist Expert',
            'description': 'Discovered 5 Impressionist paintings',
            'icon': 'fas fa-water',
            'requirement': 'movement_count.Impressionism >= 5'
        },
        'curator': {
            'name': 'Curator',
            'description': 'Created your first gallery',
            'icon': 'fas fa-images',
            'requirement': 'galleries_created >= 1'
        },
        'xp_hundred': {
            'name': 'Century Club',
            'description': 'Earned 100 XP',
            'icon': 'fas fa-medal',
            'requirement': 'xp >= 100'
        },
        'xp_thousand': {
            'name': 'XP Master',
            'description': 'Earned 1000 XP',
            'icon': 'fas fa-crown',
            'requirement': 'xp >= 1000'
        }
    }
