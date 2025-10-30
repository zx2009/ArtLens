"""
Database models for ArtLens
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    # Gamification
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    badges = db.Column(db.Text, default='[]')  # JSON array of badge IDs
    
    # Stats
    artworks_discovered = db.Column(db.Integer, default=0)
    quizzes_completed = db.Column(db.Integer, default=0)
    total_quiz_score = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    progress = db.relationship('UserProgress', backref='user', lazy='dynamic')
    galleries = db.relationship('Gallery', backref='user', lazy='dynamic')
    quiz_attempts = db.relationship('QuizAttempt', backref='user', lazy='dynamic')
    
    def add_xp(self, amount):
        """Add XP and check for level up"""
        self.xp += amount
        new_level = self.xp // 100 + 1
        if new_level > self.level:
            self.level = new_level
            return True  # Leveled up!
        return False
    
    def increment_artworks_discovered(self):
        """Increment artwork discovery count"""
        self.artworks_discovered += 1
    
    def increment_quizzes_completed(self):
        """Increment quiz completion count"""
        self.quizzes_completed += 1
    
    def get_badges(self):
        """Get list of earned badges"""
        return json.loads(self.badges)
    
    def add_badge(self, badge_id):
        """Add a badge if not already earned"""
        badges = self.get_badges()
        if badge_id not in badges:
            badges.append(badge_id)
            self.badges = json.dumps(badges)
            return True
        return False
    
    def check_and_award_badges(self):
        """Check if user qualifies for new badges and award them"""
        from config import Config
        new_badges = []
        
        for badge_id, badge_info in Config.BADGES.items():
            if badge_id not in self.get_badges():
                # Simple evaluation of requirements
                requirement = badge_info['requirement']
                
                # Parse requirement (simple format: "field >= value")
                if 'artworks_discovered' in requirement:
                    threshold = int(requirement.split('>=')[1].strip())
                    if self.artworks_discovered >= threshold:
                        self.add_badge(badge_id)
                        new_badges.append(badge_info)
                
                elif 'quizzes_completed' in requirement:
                    threshold = int(requirement.split('>=')[1].strip())
                    if self.quizzes_completed >= threshold:
                        self.add_badge(badge_id)
                        new_badges.append(badge_info)
                
                elif 'xp >=' in requirement:
                    threshold = int(requirement.split('>=')[1].strip())
                    if self.xp >= threshold:
                        self.add_badge(badge_id)
                        new_badges.append(badge_info)
        
        return new_badges

class Artwork(db.Model):
    """Artwork model"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=False)
    year = db.Column(db.Integer)
    movement = db.Column(db.String(100))  # Impressionism, Post-Impressionism, etc.
    museum = db.Column(db.String(200))
    
    # Descriptions
    description = db.Column(db.Text)  # Short description
    detailed_description = db.Column(db.Text)  # AI-generated educational description
    
    # Visual details
    image_url = db.Column(db.String(500))
    detail_regions = db.Column(db.Text)  # JSON array of highlighted regions
    image_hash = db.Column(db.String(64), index=True)  # SHA256 hash for duplicate detection
    
    # AI Recognition
    confidence = db.Column(db.Float)  # AI confidence score (0.0 to 1.0)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    progress = db.relationship('UserProgress', backref='artwork', lazy='dynamic')
    galleries = db.relationship('Gallery', backref='artwork', lazy='dynamic')
    quiz_attempts = db.relationship('QuizAttempt', backref='artwork', lazy='dynamic')

class UserProgress(db.Model):
    """Track user's progress with specific artworks"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artwork.id'), nullable=False)
    
    # Learning modes completed
    learned = db.Column(db.Boolean, default=False)
    chatted = db.Column(db.Boolean, default=False)
    quiz_completed = db.Column(db.Boolean, default=False)
    quiz_score = db.Column(db.Integer)
    
    # Emotional reaction
    emotion = db.Column(db.String(50))  # Calm, Joy, Wonder, Mystery
    
    # Timestamps
    first_viewed = db.Column(db.DateTime, default=datetime.utcnow)
    last_viewed = db.Column(db.DateTime, default=datetime.utcnow)

class Gallery(db.Model):
    """User's curated gallery items"""
    __table_args__ = (
        db.UniqueConstraint('user_id', 'artwork_id', name='unique_user_artwork'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artwork.id'), nullable=False)
    
    # User's personal reflection
    reflection = db.Column(db.Text)
    
    # Order in gallery
    position = db.Column(db.Integer, default=0)
    
    # Timestamps
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class QuizAttempt(db.Model):
    """Track quiz attempts"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artwork.id'), nullable=False)
    
    # Quiz data
    questions = db.Column(db.Text, nullable=False)  # JSON array of questions
    score = db.Column(db.Integer)
    
    # Status
    completed = db.Column(db.Boolean, default=False)
    
    # Timestamps
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
