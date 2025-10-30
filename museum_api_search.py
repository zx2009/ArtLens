"""
The Metropolitan Museum of Art (The Met) Collection API
Free, unlimited, no API key required!
"""
import requests
import urllib.parse
from functools import lru_cache
import re

def infer_art_movement(artwork_data, artist_name, year_str):
    """
    Infer art movement from Met API data or artist/year information
    Returns a proper art movement name (e.g., "Impressionism", "Renaissance")
    """
    # Check if there's a culture field (good for non-Western art)
    culture = artwork_data.get('culture', '')
    if culture and culture not in ['American', 'European', 'French', 'Italian']:
        return culture
    
    # Try to extract from tags or title
    tags = artwork_data.get('tags', [])
    for tag in tags:
        tag_name = tag.get('term', '').lower() if isinstance(tag, dict) else str(tag).lower()
        # Look for movement keywords
        movements = [
            'renaissance', 'baroque', 'rococo', 'neoclassicism', 'romanticism',
            'realism', 'impressionism', 'post-impressionism', 'expressionism',
            'cubism', 'surrealism', 'abstract', 'modernism', 'contemporary'
        ]
        for movement in movements:
            if movement in tag_name:
                return movement.title()
    
    # Infer from time period and artist
    year = None
    try:
        # Extract year from string like "1872" or "ca. 1870-1880"
        year_match = re.search(r'\b(1[4-9]\d{2}|20\d{2})\b', str(year_str))
        if year_match:
            year = int(year_match.group(1))
    except:
        pass
    
    # Time-based movement inference
    if year:
        if year < 1400:
            return "Medieval"
        elif year < 1600:
            return "Renaissance"
        elif year < 1750:
            return "Baroque"
        elif year < 1800:
            return "Neoclassicism"
        elif year < 1850:
            return "Romanticism"
        elif year < 1880:
            return "Realism"
        elif year < 1905:
            # Check artist for Impressionism
            impressionists = ['monet', 'renoir', 'degas', 'pissarro', 'sisley', 'morisot', 'cassatt']
            if any(name in artist_name.lower() for name in impressionists):
                return "Impressionism"
            post_impressionists = ['van gogh', 'cézanne', 'gauguin', 'seurat', 'toulouse-lautrec']
            if any(name in artist_name.lower() for name in post_impressionists):
                return "Post-Impressionism"
            return "Late 19th Century"
        elif year < 1920:
            return "Early Modernism"
        elif year < 1945:
            return "Modernism"
        elif year < 1970:
            return "Post-War Art"
        elif year < 2000:
            return "Contemporary"
        else:
            return "21st Century"
    
    # Default
    return artwork_data.get('classification') or 'Unknown'

# Add LRU cache to cache Met API searches
@lru_cache(maxsize=100)
def search_met_artwork(artwork_title, artist_name):
    """
    Search The Met Collection API for artwork images
    Returns image URL and additional artwork info, or None if not found
    """
    
    try:
        # Build search query - prioritize title
        query = f"{artwork_title} {artist_name}"
        encoded_query = urllib.parse.quote(query)
        
        # Step 1: Search for artwork
        search_url = f"https://collectionapi.metmuseum.org/public/collection/v1/search?q={encoded_query}"
        
        print(f"🔍 Searching Met API for: {query}")
        response = requests.get(search_url, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        if not data.get('objectIDs') or len(data['objectIDs']) == 0:
            print(f"⚠️  No results found in Met collection for '{artwork_title}'")
            return None
        
        # Step 2: Get details of multiple results and find best match
        object_ids = data['objectIDs'][:10]  # Check up to 10 results
        best_match = None
        best_score = 0
        
        for object_id in object_ids:
            try:
                object_url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
                
                response = requests.get(object_url, timeout=5)
                response.raise_for_status()
                
                artwork_data = response.json()
                
                # Get object data
                obj_title = (artwork_data.get('title') or '').lower().strip()
                obj_artist = (artwork_data.get('artistDisplayName') or '').lower().strip()
                search_title = artwork_title.lower().strip()
                search_artist = artist_name.lower().strip()
                
                # Must have an image
                if not artwork_data.get('primaryImage'):
                    continue
                
                # Calculate match score (more strict)
                score = 0
                
                # Title matching (strict)
                if obj_title == search_title:
                    score += 10  # Exact match
                elif search_title in obj_title:
                    # Check it's not a substring of a much longer title
                    title_ratio = len(search_title) / max(len(obj_title), 1)
                    if title_ratio > 0.5:  # Search title is at least 50% of object title
                        score += 5
                    else:
                        score += 1  # Weak match
                elif obj_title in search_title:
                    score += 3
                
                # Artist matching (strict)
                if obj_artist and search_artist:
                    # Split names to check last names
                    obj_last_name = obj_artist.split()[-1] if obj_artist else ''
                    search_last_name = search_artist.split()[-1] if search_artist else ''
                    
                    if obj_artist == search_artist:
                        score += 10  # Exact match
                    elif search_artist in obj_artist or obj_artist in search_artist:
                        score += 5
                    elif obj_last_name and search_last_name and obj_last_name == search_last_name:
                        score += 3  # Last name match
                
                print(f"  📊 Score {score}: '{obj_title}' by '{obj_artist}'")
                
                # Only consider high-confidence matches (score >= 8)
                if score >= 8 and score > best_score:
                    best_score = score
                    best_match = artwork_data
                    
            except Exception as e:
                print(f"  ⚠️  Error checking object {object_id}: {e}")
                continue
        
        if not best_match:
            print(f"⚠️  No high-confidence matches found for '{artwork_title}' by {artist_name}")
            return None
        
        artwork_data = best_match
        print(f"✅ Best match (score {best_score}): '{artwork_data.get('title')}' by '{artwork_data.get('artistDisplayName')}'")
        
        
        # Get primary image
        image_url = artwork_data.get('primaryImage')
        
        if image_url:
            print(f"✅ Found Met image for '{artwork_title}': {image_url}")
            return {
                'image_url': image_url,
                'met_url': artwork_data.get('objectURL'),
                'department': artwork_data.get('department'),
                'medium': artwork_data.get('medium'),
                'dimensions': artwork_data.get('dimensions')
            }
        else:
            print(f"⚠️  Met object found but no image available for '{artwork_title}'")
            return None
            
    except requests.RequestException as e:
        print(f"❌ Error searching Met API: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None


def search_multiple_sources(artwork_title, artist_name):
    """
    Search multiple museum APIs for artwork images
    Currently: The Met Museum
    Can be expanded to include: Rijksmuseum, Art Institute of Chicago, etc.
    """
    
    # Try The Met first
    met_result = search_met_artwork(artwork_title, artist_name)
    if met_result:
        return met_result['image_url']
    
    # Future: Add more museum APIs here
    # - Rijksmuseum API
    # - Art Institute of Chicago API
    # - Cleveland Museum of Art API
    
    return None


def get_artwork_image_url(artwork_title, artist_name, db_artwork=None):
    """
    Get artwork image URL with fallback logic:
    1. Try to use image from database if artwork exists
    2. Search The Met API for image
    3. Fallback to placeholder
    """
    
    # First priority: Use database image if available
    if db_artwork and db_artwork.image_url:
        return db_artwork.image_url
    
    # Second priority: Search The Met Museum API
    met_image = search_multiple_sources(artwork_title, artist_name)
    if met_image:
        return met_image
    
    # Third priority: Placeholder
    encoded_title = urllib.parse.quote_plus(artwork_title)
    return f'https://via.placeholder.com/400x300/7c3aed/ffffff?text={encoded_title}'


@lru_cache(maxsize=50)
def find_related_artworks_by_artist(artist_name, exclude_title=None, limit=4):
    """
    Find related artworks by the same artist or similar artists from The Met
    Returns list of artworks with guaranteed images
    """
    try:
        # Search for artworks by this artist
        encoded_query = urllib.parse.quote(artist_name)
        search_url = f"https://collectionapi.metmuseum.org/public/collection/v1/search?artistOrCulture=true&q={encoded_query}"
        
        print(f"🔍 Finding related artworks by artist: {artist_name}")
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if not data.get('objectIDs') or len(data['objectIDs']) == 0:
            print(f"⚠️  No artworks found by {artist_name}")
            return []
        
        # Get details for multiple artworks
        object_ids = data['objectIDs'][:20]  # Check up to 20
        related_artworks = []
        
        for object_id in object_ids:
            if len(related_artworks) >= limit:
                break
                
            try:
                object_url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
                response = requests.get(object_url, timeout=5)
                response.raise_for_status()
                
                artwork_data = response.json()
                
                # Must have image
                if not artwork_data.get('primaryImage'):
                    continue
                
                # Get data
                title = artwork_data.get('title', 'Untitled')
                artist = artwork_data.get('artistDisplayName', artist_name)
                year = artwork_data.get('objectDate', 'Unknown')
                image_url = artwork_data.get('primaryImage')
                
                # Infer proper art movement
                movement = infer_art_movement(artwork_data, artist, year)
                
                # Skip if this is the same artwork we're viewing
                if exclude_title and title.lower() == exclude_title.lower():
                    continue
                
                related_artworks.append({
                    'title': title,
                    'artist': artist,
                    'year': year,
                    'image_url': image_url,
                    'met_url': artwork_data.get('objectURL'),
                    'department': artwork_data.get('department'),
                    'medium': artwork_data.get('medium'),
                    'movement': movement
                })
                
                print(f"  ✅ Found: '{title}' by {artist} ({year})")
                
            except Exception as e:
                print(f"  ⚠️  Error fetching object {object_id}: {e}")
                continue
        
        print(f"✅ Found {len(related_artworks)} related artworks with images")
        return related_artworks
        
    except Exception as e:
        print(f"❌ Error finding related artworks: {e}")
        return []


@lru_cache(maxsize=50)
def find_related_artworks_by_style(style_or_movement, limit=4):
    """
    Find artworks by style/movement from The Met
    Returns list of artworks with guaranteed images
    """
    try:
        # Search for artworks by style/movement
        encoded_query = urllib.parse.quote(style_or_movement)
        search_url = f"https://collectionapi.metmuseum.org/public/collection/v1/search?q={encoded_query}"
        
        print(f"🔍 Finding artworks in style: {style_or_movement}")
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if not data.get('objectIDs') or len(data['objectIDs']) == 0:
            print(f"⚠️  No artworks found for style {style_or_movement}")
            return []
        
        # Get details for multiple artworks
        object_ids = data['objectIDs'][:20]
        related_artworks = []
        
        for object_id in object_ids:
            if len(related_artworks) >= limit:
                break
                
            try:
                object_url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
                response = requests.get(object_url, timeout=5)
                response.raise_for_status()
                
                artwork_data = response.json()
                
                # Must have image
                if not artwork_data.get('primaryImage'):
                    continue
                
                title = artwork_data.get('title', 'Untitled')
                artist = artwork_data.get('artistDisplayName', 'Unknown Artist')
                year = artwork_data.get('objectDate', 'Unknown')
                image_url = artwork_data.get('primaryImage')
                
                # Infer proper art movement
                movement = infer_art_movement(artwork_data, artist, year)
                
                related_artworks.append({
                    'title': title,
                    'artist': artist,
                    'year': year,
                    'image_url': image_url,
                    'movement': movement
                })
                
                print(f"  ✅ Found: '{title}' by {artist}")
                
            except Exception as e:
                continue
        
        print(f"✅ Found {len(related_artworks)} artworks in style with images")
        return related_artworks
        
    except Exception as e:
        print(f"❌ Error finding artworks by style: {e}")
        return []
