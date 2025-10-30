"""
ArtLens - Interactive AI Art Education Web App
Congressional App Challenge Submission
"""

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_caching import Cache
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
import json
import hashlib
from PIL import Image

# Import custom modules
from models import db, User, Artwork, UserProgress, Gallery, QuizAttempt
from ai_services import recognize_artwork, generate_description, chat_with_artwork, generate_quiz, get_related_artworks_and_context, generate_artist_info
from config import Config

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize caching
cache = Cache(app, config={
    'CACHE_TYPE': 'SimpleCache',  # In-memory cache
    'CACHE_DEFAULT_TIMEOUT': 3600  # 1 hour default
})

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== HELPER FUNCTIONS ====================

def generate_image_hash(filepath):
    """Generate SHA256 hash of image file for duplicate detection"""
    try:
        with open(filepath, 'rb') as f:
            file_hash = hashlib.sha256()
            # Read file in chunks to handle large files
            while chunk := f.read(8192):
                file_hash.update(chunk)
            return file_hash.hexdigest()
    except Exception as e:
        print(f"Error generating hash: {e}")
        return None

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Home page with app introduction"""
    return render_template('index.html')

@app.route('/scan')
@login_required
def scan():
    """Artwork scanning page"""
    return render_template('scan.html')

@app.route('/api/recognize', methods=['POST'])
@login_required
def recognize():
    """Handle artwork image upload and recognition"""
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        # Generate unique filename with UUID (flat structure)
        # Get file extension
        original_filename = secure_filename(file.filename)
        file_ext = os.path.splitext(original_filename)[1] or '.jpg'
        
        # Generate UUID filename
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save uploaded file
        file.save(filepath)
        
        # Generate hash for duplicate detection
        image_hash = generate_image_hash(filepath)
        
        # Check if artwork already exists by hash (instant cache hit)
        if image_hash:
            cached_artwork = Artwork.query.filter_by(image_hash=image_hash).first()
            if cached_artwork:
                # Return cached result without AI call
                return jsonify({
                    'success': True,
                    'artwork_id': cached_artwork.id,
                    'title': cached_artwork.title,
                    'artist': cached_artwork.artist,
                    'year': cached_artwork.year,
                    'movement': cached_artwork.movement,
                    'image_url': cached_artwork.image_url,
                    'confidence': cached_artwork.confidence,
                    'cached': True  # Indicate this was a cache hit
                })
        
        # Recognize artwork using AI (only if not cached)
        result = recognize_artwork(filepath)
        
        if result['success']:
            # Check if artwork exists in database by title
            artwork = Artwork.query.filter_by(title=result['title']).first()
            
            if not artwork:
                # Create new artwork entry with hash
                artwork = Artwork(
                    title=result['title'],
                    artist=result['artist'],
                    year=result.get('year'),
                    movement=result.get('movement'),
                    description=result.get('description'),
                    image_url=f'/static/uploads/{unique_filename}',
                    confidence=result.get('confidence', 0.0),
                    image_hash=image_hash
                )
                db.session.add(artwork)
                db.session.commit()
            else:
                # Update existing artwork with hash and higher confidence
                new_confidence = result.get('confidence', 0.0)
                if new_confidence > (artwork.confidence or 0.0):
                    artwork.confidence = new_confidence
                # Update hash if missing
                if not artwork.image_hash and image_hash:
                    artwork.image_hash = image_hash
                db.session.commit()
            
            # Award XP for discovery
            current_user.add_xp(10)
            current_user.increment_artworks_discovered()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'artwork_id': artwork.id,
                'title': artwork.title,
                'artist': artwork.artist,
                'year': artwork.year,
                'movement': artwork.movement,
                'image_url': artwork.image_url,
                'confidence': artwork.confidence
            })
        else:
            # Recognition failed - pass through AI response with suggestions
            return jsonify({
                'success': False,
                'message': result.get('message', 'Could not recognize this artwork'),
                'suggestions': result.get('suggestions', []),
                'is_artwork': result.get('is_artwork', False)
            }), 404

@app.route('/artwork/<int:artwork_id>')
@login_required
def artwork_detail(artwork_id):
    """Artwork detail page with Learn, Chat, Quiz modes"""
    artwork = Artwork.query.get_or_404(artwork_id)
    user_progress = UserProgress.query.filter_by(
        user_id=current_user.id,
        artwork_id=artwork_id
    ).first()
    
    # Check if artwork is already in user's gallery
    in_gallery = Gallery.query.filter_by(
        user_id=current_user.id,
        artwork_id=artwork_id
    ).first() is not None
    
    return render_template('artwork.html', artwork=artwork, progress=user_progress, in_gallery=in_gallery)

@app.route('/api/learn/<int:artwork_id>')
@login_required
def learn_mode(artwork_id):
    """Generate educational description for artwork"""
    artwork = Artwork.query.get_or_404(artwork_id)
    
    if not artwork.detailed_description:
        # Generate description using AI
        description = generate_description(artwork)
        artwork.detailed_description = description
        db.session.commit()
    
    return jsonify({
        'description': artwork.detailed_description,
        'details': artwork.detail_regions or []
    })

@app.route('/api/artist/<int:artwork_id>')
@login_required
def artist_mode(artwork_id):
    """Generate comprehensive artist biography and information"""
    artwork = Artwork.query.get_or_404(artwork_id)
    
    # Generate artist information using AI
    artist_info = generate_artist_info(artwork)
    
    return jsonify({
        'success': True,
        'artist': artist_info
    })

@app.route('/api/chat/<int:artwork_id>', methods=['POST'])
@login_required
def chat_mode(artwork_id):
    """Chat with artwork or artist"""
    artwork = Artwork.query.get_or_404(artwork_id)
    data = request.get_json()
    user_message = data.get('message', '')
    
    # Get chat history from session (user-specific)
    chat_key = f'chat_{current_user.id}_{artwork_id}'
    chat_history = session.get(chat_key, [])
    
    # Generate AI response
    response = chat_with_artwork(artwork, user_message, chat_history)
    
    # Update chat history (user-specific)
    chat_history.append({'role': 'user', 'content': user_message})
    chat_history.append({'role': 'assistant', 'content': response})
    session[chat_key] = chat_history[-10:]  # Keep last 10 messages per user
    
    return jsonify({'response': response})

@app.route('/api/related/<int:artwork_id>')
@login_required
def get_related_content(artwork_id):
    """Get related artworks with guaranteed images from museum APIs"""
    # Use user-specific cache key to avoid cross-user contamination
    cache_key = f"related_{artwork_id}_{current_user.id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return jsonify(cached_result)
    
    artwork = Artwork.query.get_or_404(artwork_id)
    
    # Import Museum API search helpers
    from museum_api_search import find_related_artworks_by_artist, find_related_artworks_by_style
    
    # Strategy: Find real artworks with images first, then let AI explain similarities
    related_artworks = []
    
    # 1. Try to find artworks by the same artist (most relevant)
    if artwork.artist:
        artworks_by_artist = find_related_artworks_by_artist(
            artwork.artist, 
            exclude_title=artwork.title,
            limit=3
        )
        related_artworks.extend(artworks_by_artist)
    
    # 2. If we need more, try to find artworks from the same movement/style
    if len(related_artworks) < 3 and artwork.movement and artwork.movement != 'Unknown':
        artworks_by_style = find_related_artworks_by_style(
            artwork.movement,
            limit=3 - len(related_artworks)
        )
        related_artworks.extend(artworks_by_style)
    
    # 3. If still not enough, get AI suggestions (but these might not have images)
    if len(related_artworks) < 3:
        ai_content = get_related_artworks_and_context(artwork)
        ai_suggestions = ai_content.get('similar_artworks', [])[:3]
        
        # Try to enrich AI suggestions with images
        from museum_api_search import get_artwork_image_url
        for suggestion in ai_suggestions:
            title = suggestion.get('title')
            artist = suggestion.get('artist')
            db_artwork = Artwork.query.filter_by(title=title).first()
            
            image_url = get_artwork_image_url(title, artist, db_artwork)
            
            # Only add if we found a real image (not placeholder)
            if image_url and 'placeholder' not in image_url:
                suggestion['image_url'] = image_url
                related_artworks.append(suggestion)
                if len(related_artworks) >= 3:
                    break
    
    # Now have AI generate similarity explanations for our found artworks
    if related_artworks:
        try:
            from ai_services import generate_similarity_explanations
            related_artworks = generate_similarity_explanations(artwork, related_artworks)
        except Exception as e:
            print(f"⚠️  Could not generate AI explanations: {e}")
            # Use default explanations
            for art in related_artworks:
                if 'similarity' not in art:
                    art['similarity'] = f"Related artwork by {art.get('artist', 'the same artist')}"
    
    # Also generate historical context and contemporary artists
    historical_context = {}
    contemporary_artists = []
    
    try:
        ai_content = get_related_artworks_and_context(artwork)
        historical_context = ai_content.get('historical_context', {})
        contemporary_artists = ai_content.get('contemporary_artists', [])
    except Exception as e:
        print(f"⚠️  Could not generate historical context: {e}")
    
    result = {
        'similar_artworks': related_artworks,
        'historical_context': historical_context,
        'contemporary_artists': contemporary_artists
    }
    
    # Cache the result for 30 minutes per user
    cache.set(cache_key, result, timeout=1800)
    
    return jsonify(result)


@app.route('/api/artwork/search')
@login_required
def search_artwork():
    """Search for artwork by title and artist"""
    title = request.args.get('title', '')
    artist = request.args.get('artist', '')
    
    if not title or not artist:
        return jsonify({'exists': False})
    
    # Search for artwork in database
    artwork = Artwork.query.filter_by(title=title, artist=artist).first()
    
    if artwork:
        return jsonify({
            'exists': True,
            'artwork_id': artwork.id
        })
    else:
        return jsonify({'exists': False})

@app.route('/api/artwork/create', methods=['POST'])
@login_required
def create_artwork():
    """Create a new artwork from related artwork suggestion"""
    try:
        data = request.get_json()
        title = data.get('title')
        artist = data.get('artist')
        year = data.get('year')
        image_url = data.get('image_url')
        description = data.get('description', '')
        movement = data.get('movement', 'Unknown')
        
        # Check if artwork already exists (artworks are shared across all users)
        existing = Artwork.query.filter_by(
            title=title,
            artist=artist
        ).first()
        
        if existing:
            # Award XP for discovering existing artwork
            current_user.add_xp(10)
            current_user.increment_artworks_discovered()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'artwork_id': existing.id,
                'already_exists': True
            })
        
        # Create new artwork (shared across all users)
        artwork = Artwork(
            title=title,
            artist=artist,
            year=year,
            image_url=image_url,
            description=description,
            movement=movement,
            confidence=0.9  # High confidence for museum API results
        )
        
        db.session.add(artwork)
        db.session.flush()  # Get the artwork ID
        
        # Award XP for discovering new artwork
        current_user.add_xp(10)
        current_user.increment_artworks_discovered()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'artwork_id': artwork.id,
            'already_exists': False
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating artwork: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/quiz/<int:artwork_id>')
@login_required
def quiz_mode(artwork_id):
    """Generate quiz for artwork"""
    artwork = Artwork.query.get_or_404(artwork_id)
    
    # Check if user already has a quiz for this artwork (completed or not)
    # We want to reuse the same questions every time
    quiz_attempt = QuizAttempt.query.filter_by(
        user_id=current_user.id,
        artwork_id=artwork_id
    ).order_by(QuizAttempt.started_at.desc()).first()
    
    if not quiz_attempt:
        # Generate new quiz only if user has never taken one for this artwork
        questions = generate_quiz(artwork)
        quiz_attempt = QuizAttempt(
            user_id=current_user.id,
            artwork_id=artwork_id,
            questions=json.dumps(questions)
        )
        db.session.add(quiz_attempt)
        db.session.commit()
    elif quiz_attempt.completed:
        # If previous quiz was completed, create a new attempt with SAME questions
        # This allows retaking while maintaining consistency
        new_attempt = QuizAttempt(
            user_id=current_user.id,
            artwork_id=artwork_id,
            questions=quiz_attempt.questions  # Reuse the same questions!
        )
        db.session.add(new_attempt)
        db.session.commit()
        quiz_attempt = new_attempt
    
    return jsonify({
        'quiz_id': quiz_attempt.id,
        'questions': json.loads(quiz_attempt.questions)
    })

@app.route('/api/quiz/<int:quiz_id>/submit', methods=['POST'])
@login_required
def submit_quiz(quiz_id):
    """Submit quiz answers and calculate score"""
    quiz_attempt = QuizAttempt.query.get_or_404(quiz_id)
    
    if quiz_attempt.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    answers = data.get('answers', [])
    
    questions = json.loads(quiz_attempt.questions)
    correct = 0
    
    for i, answer in enumerate(answers):
        if i < len(questions) and answer == questions[i]['correct_answer']:
            correct += 1
    
    score = int((correct / len(questions)) * 100)
    xp_earned = correct * 10
    
    # Update quiz attempt
    quiz_attempt.score = score
    quiz_attempt.completed = True
    quiz_attempt.completed_at = datetime.utcnow()
    
    # Find best score for this artwork
    all_attempts = QuizAttempt.query.filter_by(
        user_id=current_user.id,
        artwork_id=quiz_attempt.artwork_id,
        completed=True
    ).all()
    
    best_score = max([attempt.score for attempt in all_attempts] + [score])
    is_best_score = score == best_score
    previous_best = max([attempt.score for attempt in all_attempts if attempt.id != quiz_attempt.id], default=0)
    
    # Award XP
    current_user.add_xp(xp_earned)
    current_user.increment_quizzes_completed()
    
    # Check for badges
    new_badges = current_user.check_and_award_badges()
    
    db.session.commit()
    
    return jsonify({
        'score': score,
        'correct': correct,
        'total': len(questions),
        'xp_earned': xp_earned,
        'new_badges': new_badges,
        'best_score': best_score,
        'is_best_score': is_best_score,
        'previous_best': previous_best
    })

@app.route('/gallery')
@login_required
def my_gallery():
    """User's curated gallery page"""
    galleries = Gallery.query.filter_by(user_id=current_user.id).all()
    return render_template('gallery.html', galleries=galleries)

@app.route('/api/gallery/add', methods=['POST'])
@login_required
def add_to_gallery():
    """Add artwork to user's gallery"""
    data = request.get_json()
    artwork_id = data.get('artwork_id')
    reflection = data.get('reflection', '')
    
    # Check if artwork is already in user's gallery
    existing_item = Gallery.query.filter_by(
        user_id=current_user.id,
        artwork_id=artwork_id
    ).first()
    
    if existing_item:
        return jsonify({
            'success': False, 
            'message': 'This artwork is already in your gallery!'
        }), 409  # 409 Conflict
    
    gallery_item = Gallery(
        user_id=current_user.id,
        artwork_id=artwork_id,
        reflection=reflection
    )
    db.session.add(gallery_item)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Added to gallery!'})

@app.route('/api/gallery/remove/<int:gallery_id>', methods=['DELETE'])
@login_required
def remove_from_gallery(gallery_id):
    """Remove artwork from user's gallery"""
    gallery_item = Gallery.query.get_or_404(gallery_id)
    
    # Ensure the gallery item belongs to the current user
    if gallery_item.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    db.session.delete(gallery_item)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Removed from gallery!'})

@app.route('/profile')
@login_required
def profile():
    """User profile with XP, badges, and stats"""
    return render_template('profile.html', user=current_user)

@app.route('/leaderboard')
def leaderboard():
    """Global leaderboard (optional)"""
    top_users = User.query.order_by(User.xp.desc()).limit(20).all()
    return render_template('leaderboard.html', users=top_users)

# ==================== AUTH ROUTES ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Validate input
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))
        
        # Create new user
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('index'))

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# ==================== CLI COMMANDS ====================

@app.cli.command()
def init_db():
    """Initialize database"""
    db.create_all()
    print('Database initialized!')

# Removed seed_db command - This is a real product, users discover artworks themselves!

if __name__ == '__main__':
    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=80)
