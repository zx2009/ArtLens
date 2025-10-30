"""
AI service integrations for artwork recognition, chat, and quiz generation
Supports both OpenAI and Azure OpenAI
"""
import os
import json
import random
from typing import Dict, List, Any
from PIL import Image
import base64
from io import BytesIO
from functools import lru_cache

# Try to import OpenAI - will use mock if not available
try:
    from openai import OpenAI, AzureOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Configuration - Check for Azure OpenAI first, then regular OpenAI
USE_AZURE = os.environ.get('AZURE_OPENAI_KEY') and os.environ.get('AZURE_OPENAI_ENDPOINT')
USE_OPENAI = os.environ.get('OPENAI_API_KEY')
USE_REAL_AI = (USE_AZURE or USE_OPENAI) and OPENAI_AVAILABLE

def get_ai_client():
    """
    Get the appropriate AI client (Azure OpenAI or OpenAI)
    """
    if USE_AZURE:
        print("🔷 Using Azure OpenAI")
        return AzureOpenAI(
            api_key=os.environ.get('AZURE_OPENAI_KEY'),
            api_version=os.environ.get('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),
            azure_endpoint=os.environ.get('AZURE_OPENAI_ENDPOINT')
        )
    elif USE_OPENAI:
        print("🟢 Using OpenAI")
        return OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
    else:
        return None

def get_model_name(task='vision'):
    """
    Get the appropriate model name for Azure or OpenAI
    """
    if USE_AZURE:
        # Azure uses deployment names
        if task == 'vision':
            return os.environ.get('AZURE_OPENAI_VISION_DEPLOYMENT', 'gpt-4o')
        else:
            return os.environ.get('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')
    else:
        # Regular OpenAI uses model names
        return 'gpt-4o'

def encode_image_to_base64(image_path: str) -> str:
    """Convert image to base64 for API calls"""
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def recognize_artwork_with_gpt4_vision(image_path: str) -> Dict[str, Any]:
    """
    Use GPT-4 Vision to recognize artwork
    Supports both OpenAI and Azure OpenAI
    """
    try:
        client = get_ai_client()
        if not client:
            raise Exception("No AI client available")
        
        # Encode image
        base64_image = encode_image_to_base64(image_path)
        
        # Call GPT-4 Vision API
        response = client.chat.completions.create(
            model=get_model_name('vision'),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """You are an expert art historian. Analyze this image VERY CAREFULLY.

CRITICAL RULES:
1. If this is a PHOTOGRAPH of a person (selfie, portrait, etc.) → Return success: false
2. If this is NOT a painting/sculpture/famous artwork → Return success: false  
3. If this is a digital image/screenshot/random photo → Return success: false
4. ONLY return success: true if you are 100% certain this is a FAMOUS artwork in a museum

First, determine: Is this an actual painting, sculpture, or famous artwork photograph?
- If NO (it's a selfie, person photo, random image, digital art, etc.) → Return the "not a famous artwork" response
- If YES, and you can identify it with certainty → Return the success response

SUCCESS RESPONSE (only for famous museum artworks you can identify):
{
    "success": true,
    "title": "The Starry Night",
    "artist": "Vincent van Gogh",
    "year": 1889,
    "movement": "Post-Impressionism",
    "description": "A swirling night sky over a French village",
    "museum": "Museum of Modern Art, New York",
    "confidence": 0.95
}

FAILURE RESPONSE (for selfies, photos of people, random images, non-artwork):
{
    "success": false,
    "message": "This appears to be a photograph or image, not a famous artwork. ArtLens is designed to recognize famous paintings and sculptures from museums.",
    "is_artwork": false,
    "suggestions": [
        "Try uploading a photo of a famous painting (Mona Lisa, Starry Night, etc.)",
        "Visit an art museum and photograph famous artworks",
        "Search online for famous paintings by Van Gogh, Monet, Picasso, or Da Vinci"
    ]
}

FAILURE RESPONSE (for unclear artwork or artwork you cannot identify):
{
    "success": false,
    "message": "This may be artwork, but I cannot identify it as a famous piece with confidence.",
    "is_artwork": true,
    "suggestions": [
        "Try a clearer photo with better lighting",
        "Ensure the entire artwork is visible",
        "Make sure it's a famous artwork from a major museum"
    ]
}

BE EXTREMELY STRICT. If there is ANY doubt, return success: false. Do not try to match patterns - only identify actual famous artworks you are certain about.

IMPORTANT: Respond with ONLY the JSON object. Do not include any explanatory text before or after the JSON. Start your response with { and end with }."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.1
        )
        
        # Parse response
        result_text = response.choices[0].message.content.strip()
        
        # Extract JSON from response - try multiple methods
        import re
        
        # Method 1: Try parsing the entire response
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            # Method 2: Extract JSON between first { and last }
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                try:
                    json_str = json_match.group()
                    # Clean up common JSON issues
                    json_str = json_str.replace('\n', ' ')
                    json_str = re.sub(r'\s+', ' ', json_str)  # Normalize whitespace
                    
                    # Fix common AI mistakes
                    # Fix unquoted year ranges like: "year": 1908-1912 → "year": "1908-1912"
                    json_str = re.sub(r'"year":\s*(\d{4})-(\d{4})', r'"year": "\1-\2"', json_str)
                    # Fix unquoted single years to make consistent
                    json_str = re.sub(r'"year":\s*(\d{4})([,}])', r'"year": \1\2', json_str)
                    
                    result = json.loads(json_str)
                except json.JSONDecodeError as e:
                    print(f"❌ JSON parse error: {e}")
                    print(f"📄 AI Response (first 300 chars):")
                    print(result_text[:300])
                    print("...")
                    
                    # Return a generic failure response if JSON is malformed
                    return {
                        'success': False,
                        'message': 'Could not parse the AI recognition result. Please try again with a clearer image.',
                        'is_artwork': False,
                        'suggestions': [
                            'Try uploading the image again',
                            'Make sure the image is clear and well-lit',
                            'Try a different famous artwork'
                        ]
                    }
            else:
                print(f"❌ No JSON found in AI response")
                print(f"📄 AI Response: {result_text[:200]}...")
                return {
                    'success': False,
                    'message': 'AI did not return a valid response. Please try again.',
                    'is_artwork': False,
                    'suggestions': [
                        'Try uploading the image again',
                        'Try a different famous artwork'
                    ]
                }
        
        # If we got here, JSON parsing succeeded
        # Additional validation for success cases
        if result.get('success'):
            # Ensure we have required fields for a valid artwork
            required_fields = ['title', 'artist']
            if not all(field in result for field in required_fields):
                return {
                    'success': False,
                    'message': 'Could not identify this as a famous artwork.',
                    'is_artwork': False,
                    'suggestions': [
                        'Try uploading a photo of a famous painting',
                        'Make sure the image shows a clear view of museum artwork'
                    ]
                }
            
            # Check confidence - only accept high confidence
            confidence = result.get('confidence', 0)
            if confidence < 0.7:
                return {
                    'success': False,
                    'message': 'Low confidence in recognition. This may not be a famous artwork.',
                    'is_artwork': result.get('is_artwork', True),
                    'suggestions': [
                        'Try a clearer photo',
                        'Make sure it\'s a famous artwork from a major museum',
                        'Ensure good lighting without glare'
                    ]
                }
        
        return result
            
    except Exception as e:
        print(f"Error in GPT-4 Vision recognition: {e}")
        return {
            'success': False,
            'message': f'Recognition error: {str(e)}'
        }

def recognize_artwork(image_path: str) -> Dict[str, Any]:
    """
    Recognize artwork from image using AI
    
    Uses GPT-4 Vision if API key is available, otherwise falls back to mock data
    """
    
    # Try real AI first if available
    if USE_REAL_AI:
        print("🔍 Using GPT-4 Vision for real artwork recognition...")
        result = recognize_artwork_with_gpt4_vision(image_path)
        
        # If recognition was successful, return it
        if result.get('success'):
            print(f"✅ Recognized: {result.get('title')} by {result.get('artist')}")
            return result
        else:
            # Recognition failed - return the error with suggestions
            print(f"⚠️  Recognition failed: {result.get('message')}")
            print(f"💡 Returning error to user with suggestions")
            return result
    
    # Mock data for demo (only when no API key is configured)
    print("📝 Using mock data for demo purposes (no API key configured)...")
    mock_artworks = [
        {
            'title': 'The Starry Night',
            'artist': 'Vincent van Gogh',
            'year': 1889,
            'movement': 'Post-Impressionism',
            'description': 'A swirling night sky over a French village',
            'museum': 'Museum of Modern Art, New York'
        },
        {
            'title': 'Mona Lisa',
            'artist': 'Leonardo da Vinci',
            'year': 1503,
            'movement': 'Renaissance',
            'description': 'Portrait of Lisa Gherardini with an enigmatic smile',
            'museum': 'Louvre Museum, Paris'
        },
        {
            'title': 'The Persistence of Memory',
            'artist': 'Salvador Dalí',
            'year': 1931,
            'movement': 'Surrealism',
            'description': 'Melting clocks in a dreamlike landscape',
            'museum': 'Museum of Modern Art, New York'
        },
        {
            'title': 'Girl with a Pearl Earring',
            'artist': 'Johannes Vermeer',
            'year': 1665,
            'movement': 'Dutch Golden Age',
            'description': 'Portrait of a girl wearing an exotic dress and a pearl earring',
            'museum': 'Mauritshuis, The Hague'
        },
        {
            'title': 'The Scream',
            'artist': 'Edvard Munch',
            'year': 1893,
            'movement': 'Expressionism',
            'description': 'An agonized figure against a tumultuous orange sky',
            'museum': 'National Museum of Norway'
        }
    ]
    
    # Randomly select artwork for demo
    artwork = random.choice(mock_artworks)
    artwork['success'] = True
    
    return artwork

def generate_description(artwork) -> str:
    """
    Generate educational description using GPT-4
    """
    
    # Try real AI if available
    if USE_REAL_AI:
        try:
            client = get_ai_client()
            if not client:
                raise Exception("No AI client available")
            
            prompt = f'''Generate a 200-300 word educational description for the following artwork:

Title: {artwork.title}
Artist: {artwork.artist}
Year: {artwork.year}
Movement: {artwork.movement}

The description should:
- Explain the artwork's historical and cultural context
- Describe color symbolism and artistic techniques
- Discuss the artist's emotional intent
- Use friendly, inspiring language suitable for high school students
- Include fascinating details that make the artwork memorable
- Be engaging and encourage deeper appreciation of art'''
            
            response = client.chat.completions.create(
                model=get_model_name('text'),
                messages=[
                    {"role": "system", "content": "You are an engaging art history teacher who makes art accessible and exciting for students."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            description = response.choices[0].message.content
            print(f"✅ Generated description for {artwork.title}")
            return description
            
        except Exception as e:
            print(f"⚠️  Error generating description: {e}")
            # Fall back to mock
    
    # Mock descriptions for demo
    descriptions = {
        'The Starry Night': '''
        Vincent van Gogh painted "The Starry Night" in 1889 while staying at an asylum in Saint-Rémy-de-Provence, France. This iconic masterpiece captures a swirling night sky ablaze with movement and emotion, reflecting van Gogh's turbulent inner world.

        The painting features bold, expressive brushstrokes that create a sense of motion and energy. The cypress tree in the foreground reaches toward the sky like a dark flame, symbolizing the connection between earth and heaven. The village below remains peaceful and still, contrasting with the dynamic cosmos above.

        Van Gogh used vivid blues and yellows to create dramatic contrast and emotional intensity. The swirling patterns in the sky suggest both beauty and chaos, reflecting the artist's struggle with mental illness while celebrating the wonder of nature.

        This Post-Impressionist work broke traditional rules of perspective and color, paving the way for modern art. Van Gogh painted from memory and imagination rather than direct observation, infusing the scene with his unique vision and passion. Today, it remains one of the most recognized and beloved paintings in the world.
        ''',
        'Mona Lisa': '''
        Leonardo da Vinci's "Mona Lisa," painted between 1503-1519, is arguably the world's most famous painting. This Renaissance masterpiece portrays Lisa Gherardini, a Florentine merchant's wife, with an enigmatic expression that has captivated viewers for centuries.

        Da Vinci employed sfumato, a technique of subtle gradations between colors without harsh outlines, creating an almost ethereal quality. The painting's mysterious smile seems to change depending on where you look – a result of Leonardo's understanding of optics and human perception.

        The background landscape features winding paths and distant mountains, painted in atmospheric perspective that adds depth and mystery. Leonardo worked on this portrait for years, continuously refining it and considering it his favorite work.

        The Mona Lisa revolutionized portraiture by depicting the subject in a three-quarter view with hands visible, creating a more intimate and lifelike representation. Her direct gaze engages viewers, making them feel personally connected to the painting across five centuries.
        ''',
        'default': f'''
        "{artwork.title}" by {artwork.artist} is a remarkable example of {artwork.movement} art created in {artwork.year}. This masterpiece showcases the artist's unique vision and technical mastery.

        The composition demonstrates careful attention to form, color, and meaning. The artist employed techniques characteristic of the {artwork.movement} movement, which emphasized innovation and emotional expression in visual art.

        This work invites viewers to contemplate its deeper meanings and appreciate the artistic decisions that make it memorable. The painting's cultural impact extends beyond its era, continuing to inspire and engage audiences today.

        Understanding this artwork helps us appreciate how art reflects and shapes human experience across time and cultures.
        '''
    }
    
    return descriptions.get(artwork.title, descriptions['default'])

def chat_with_artwork(artwork, user_message: str, chat_history: List[Dict]) -> str:
    """
    Generate conversational response as if the artwork/artist is speaking
    """
    
    # Try real AI if available
    if USE_REAL_AI:
        try:
            client = get_ai_client()
            if not client:
                raise Exception("No AI client available")
            
            system_prompt = f'''You are {artwork.artist}, the creator of "{artwork.title}".
You speak with passion, emotion, and curiosity about your work.
Respond to students in short, vivid language (60-100 words).
Share insights about your artistic process, inspiration, and the meaning behind your work.
Be engaging, educational, and stay in character.
Encourage students to think deeply about art.'''
            
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(chat_history[-6:])  # Keep last 6 messages for context
            messages.append({"role": "user", "content": user_message})
            
            response = client.chat.completions.create(
                model=get_model_name('text'),
                messages=messages,
                max_tokens=150,
                temperature=0.8
            )
            
            reply = response.choices[0].message.content
            print(f"💬 Generated chat response for {artwork.title}")
            return reply
            
        except Exception as e:
            print(f"⚠️  Error in chat: {e}")
            # Fall back to mock
    
    # Mock responses for demo
    responses = [
        f"Ah, you want to know about {artwork.title}! I created this piece during a time of great emotion and discovery. Every brushstroke carries my passion and vision.",
        f"When I painted this, I was exploring the depths of {artwork.movement}. The colors and forms you see represent my inner world and observations of life.",
        "What a wonderful question! Let me share with you the story behind this work...",
        f"As {artwork.artist}, I poured my soul into every detail. What you're seeing isn't just paint on canvas – it's a window into my experience and perspective.",
        "The techniques I used here were revolutionary for {artwork.year}. I wanted to capture something that went beyond mere representation."
    ]
    
    return random.choice(responses)

def generate_quiz(artwork) -> List[Dict]:
    """
    Generate quiz questions about the artwork using AI
    """
    
    # Try real AI if available
    if USE_REAL_AI:
        try:
            client = get_ai_client()
            if not client:
                raise Exception("No AI client available")
            
            prompt = f'''Generate 5 multiple-choice quiz questions about this artwork:

Title: {artwork.title}
Artist: {artwork.artist}
Year: {artwork.year}
Movement: {artwork.movement}

Include varied question types:
1. Factual (artist, year, movement)
2. Visual details and composition
3. Artistic techniques and style
4. Interpretation and meaning
5. Historical context

Return ONLY a valid JSON array (no markdown, no code blocks) with this exact format:
[
  {{
    "question": "question text",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": 0,
    "explanation": "brief explanation of correct answer"
  }}
]

Make questions engaging and educational for high school students.'''
            
            response = client.chat.completions.create(
                model=get_model_name('text'),
                messages=[
                    {"role": "system", "content": "You are an art education expert. Return only valid JSON arrays."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            questions = json.loads(result_text)
            
            # Ensure we have a list
            if isinstance(questions, dict) and 'questions' in questions:
                questions = questions['questions']
            
            print(f"✅ Generated {len(questions)} quiz questions for {artwork.title}")
            return questions
            
        except Exception as e:
            print(f"⚠️  Error generating quiz: {e}")
            # Fall back to mock
    
    # Mock quiz questions for demo
    base_questions = [
        {
            'question': f'Who painted "{artwork.title}"?',
            'options': [artwork.artist, 'Pablo Picasso', 'Claude Monet', 'Rembrandt'],
            'correct_answer': 0,
            'explanation': f'{artwork.artist} created this masterpiece in {artwork.year}.'
        },
        {
            'question': f'What art movement does "{artwork.title}" belong to?',
            'options': [artwork.movement or 'Renaissance', 'Cubism', 'Abstract Expressionism', 'Baroque'],
            'correct_answer': 0,
            'explanation': f'This work is a prime example of {artwork.movement} art.'
        },
        {
            'question': f'When was "{artwork.title}" created?',
            'options': [str(artwork.year) if artwork.year else '1800s', '1920s', '1650s', '2000s'],
            'correct_answer': 0,
            'explanation': f'The artwork was painted in {artwork.year}.'
        },
        {
            'question': 'What emotion does this artwork primarily convey?',
            'options': ['A sense of wonder and movement', 'Anger and frustration', 'Boredom', 'Confusion'],
            'correct_answer': 0,
            'explanation': 'The composition and colors work together to create an emotional impact.'
        },
        {
            'question': 'Which technique is most prominent in this painting?',
            'options': ['Expressive brushwork', 'Photorealism', 'Digital manipulation', 'Collage'],
            'correct_answer': 0,
            'explanation': 'The artist used distinctive brushwork techniques characteristic of their style.'
        }
    ]
    
    # Shuffle options for some randomization
    random.shuffle(base_questions)
    return base_questions[:5]

# Cache for AI-generated content (avoid regenerating same content)
_ai_content_cache = {}

def get_related_artworks_and_context(artwork) -> Dict[str, Any]:
    """
    Get related artworks, contemporary artists, and historical context using AI
    Cached to avoid regenerating same content
    """
    
    # Check cache first
    cache_key = f"{artwork.id}_{artwork.title}_{artwork.artist}"
    if cache_key in _ai_content_cache:
        print(f"✅ Using cached AI content for {artwork.title}")
        return _ai_content_cache[cache_key]
    
    # Try real AI if available
    if USE_REAL_AI:
        try:
            client = get_ai_client()
            if not client:
                raise Exception("No AI client available")
            
            prompt = f'''You are an art historian. Provide context about "{artwork.title}" by {artwork.artist} ({artwork.year}).

Return a JSON object with this EXACT structure:
{{
    "similar_artworks": [
        {{
            "title": "Artwork name",
            "artist": "Artist name",
            "year": "Year or range",
            "similarity": "Why it's similar (one sentence)"
        }}
    ],
    "contemporary_artists": [
        {{
            "name": "Artist name",
            "years": "Birth-death years",
            "movement": "Art movement",
            "notable_work": "Famous artwork",
            "connection": "How they relate to {artwork.artist} (one sentence)"
        }}
    ],
    "historical_context": {{
        "time_period": "Brief description of the era (40-60 words)",
        "art_movement": "Description of {artwork.movement} (40-60 words)",
        "artist_story": "Brief story about {artwork.artist}'s life and influence (60-80 words)"
    }}
}}

Provide 3-4 similar artworks and 3-4 contemporary artists.
Return ONLY valid JSON, no extra text.'''
            
            response = client.chat.completions.create(
                model=get_model_name('text'),
                messages=[
                    {"role": "system", "content": "You are an expert art historian. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.7
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    print(f"✅ Generated related content for {artwork.title}")
                    # Cache the result
                    _ai_content_cache[cache_key] = result
                    return result
                except json.JSONDecodeError as e:
                    print(f"⚠️  JSON parse error in related content: {e}")
                    # Fall through to mock data
            
        except Exception as e:
            print(f"⚠️  Error generating related content: {e}")
            # Fall through to mock data
    
    # Mock data for demo
    mock_data = {
        "similar_artworks": [
            {
                "title": "Water Lilies",
                "artist": "Claude Monet",
                "year": "1916",
                "similarity": "Both use impressionistic techniques to capture light and atmosphere"
            },
            {
                "title": "Impression, Sunrise",
                "artist": "Claude Monet",
                "year": "1872",
                "similarity": "Pioneering impressionist work that revolutionized painting techniques"
            },
            {
                "title": "The Scream",
                "artist": "Edvard Munch",
                "year": "1893",
                "similarity": "Shares the expressive use of swirling patterns and emotional intensity"
            }
        ],
        "contemporary_artists": [
            {
                "name": "Paul Cézanne",
                "years": "1839-1906",
                "movement": "Post-Impressionism",
                "notable_work": "Mont Sainte-Victoire",
                "connection": "Fellow post-impressionist who also broke from traditional techniques"
            }
        ],
        "historical_context": {
            "time_period": "Late 19th century art period",
            "art_movement": "Impressionism and Post-Impressionism",
            "artist_story": "Artist biography and influence"
        }
    }
    
    # Cache mock data too
    _ai_content_cache[cache_key] = mock_data
    return mock_data


def generate_similarity_explanations(current_artwork, related_artworks):
    """
    Generate AI explanations for why related artworks are similar to the current artwork
    Takes a list of artworks with images and adds 'similarity' explanations
    """
    
    if not USE_REAL_AI or not related_artworks:
        # Add default explanations
        for art in related_artworks:
            if 'similarity' not in art:
                art['similarity'] = f"Created by {art.get('artist', 'a related artist')} in a similar style"
        return related_artworks
    
    try:
        client = get_ai_client()
        if not client:
            raise Exception("No AI client available")
        
        # Build list of artworks to explain
        artworks_list = "\n".join([
            f"- '{art.get('title')}' by {art.get('artist')} ({art.get('year')})"
            for art in related_artworks
        ])
        
        prompt = f'''You are an art historian. Explain why these artworks are similar to "{current_artwork.title}" by {current_artwork.artist}.

Current artwork: "{current_artwork.title}" by {current_artwork.artist} ({current_artwork.year})
Movement: {current_artwork.movement or 'Unknown'}

Related artworks to explain:
{artworks_list}

For each artwork, write ONE sentence (15-25 words) explaining its similarity or connection.
Return a JSON array with this structure:
[
    {{"title": "Artwork 1", "similarity": "One sentence explanation"}},
    {{"title": "Artwork 2", "similarity": "One sentence explanation"}},
    ...
]

Return ONLY valid JSON, no extra text.'''
        
        response = client.chat.completions.create(
            model=get_model_name('text'),
            messages=[
                {"role": "system", "content": "You are an expert art historian. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        import re
        json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
        if json_match:
            try:
                explanations = json.loads(json_match.group())
                
                # Match explanations to artworks
                for art in related_artworks:
                    for exp in explanations:
                        if exp.get('title', '').lower() in art.get('title', '').lower():
                            art['similarity'] = exp.get('similarity', '')
                            break
                    
                    # Default if no match found
                    if 'similarity' not in art or not art['similarity']:
                        art['similarity'] = f"Related artwork by {art.get('artist', 'a similar artist')}"
                
                print(f"✅ Generated similarity explanations")
                return related_artworks
                
            except json.JSONDecodeError as e:
                print(f"⚠️  JSON parse error: {e}")
        
    except Exception as e:
        print(f"⚠️  Error generating explanations: {e}")
    
    # Fallback: add default explanations
    for art in related_artworks:
        if 'similarity' not in art:
            art['similarity'] = f"Created by {art.get('artist', 'a related artist')} in a similar style"
    
    return related_artworks


def generate_artist_info(artwork) -> dict:
    """
    Generate comprehensive artist biography and information using GPT-4
    """
    
    # Try real AI if available
    if USE_REAL_AI:
        try:
            client = get_ai_client()
            if not client:
                raise Exception("No AI client available")
            
            prompt = f'''Generate comprehensive information about the artist who created this artwork:

Title: {artwork.title}
Artist: {artwork.artist}
Year: {artwork.year}
Movement: {artwork.movement}

Please provide a detailed JSON response with the following structure:
{{
    "name": "Full artist name",
    "birth_year": "Birth year or null",
    "death_year": "Death year or null if still alive",
    "nationality": "Nationality",
    "biography": "Comprehensive 300-400 word biography covering their life, artistic journey, challenges, and impact on art history",
    "style": "Detailed description of their artistic style, techniques, and unique characteristics (150-200 words)",
    "notable_works": ["List of 4-6 most famous artworks"],
    "influences": "Description of what influenced the artist and their legacy (100-150 words)"
}}

Make the content engaging, educational, and suitable for high school students. Focus on making the artist relatable and their achievements inspiring.'''
            
            response = client.chat.completions.create(
                model=get_model_name('text'),
                messages=[
                    {"role": "system", "content": "You are a knowledgeable art historian who creates engaging, accurate artist biographies. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            import json
            artist_info = json.loads(response.choices[0].message.content)
            print(f"✅ Generated artist info for {artwork.artist}")
            return artist_info
            
        except Exception as e:
            print(f"⚠️  Error generating artist info: {e}")
            # Fall back to mock
    
    # Mock artist information for demo
    mock_artists = {
        'Vincent van Gogh': {
            'name': 'Vincent van Gogh',
            'birth_year': '1853',
            'death_year': '1890',
            'nationality': 'Dutch',
            'biography': '''Vincent Willem van Gogh was born in 1853 in the Netherlands and became one of the most influential figures in Western art history, despite selling only one painting during his lifetime. His journey into art began relatively late at age 27, after unsuccessful careers as an art dealer and missionary.

Van Gogh struggled with mental illness throughout his adult life, experiencing severe depression and psychotic episodes. These challenges deeply influenced his work, infusing his paintings with raw emotion and intensity. He spent time in psychiatric hospitals, including the asylum in Saint-Rémy where he created many masterpieces.

His artistic career lasted only a decade (1880-1890), but during this time he produced over 2,100 artworks, including around 860 oil paintings. Van Gogh developed a unique style characterized by bold colors, emotional honesty, and dramatic brushwork that laid the groundwork for Expressionism.

Tragically, Van Gogh died at 37 from a gunshot wound, likely self-inflicted. His brother Theo was his greatest supporter, both emotionally and financially. Today, Van Gogh's work sells for millions and his story of perseverance through adversity inspires artists worldwide.''',
            'style': '''Van Gogh's style evolved from dark, earthy tones to the vibrant, expressive palette he's famous for today. He employed thick, visible brushstrokes (impasto technique) that created texture and movement, making his paintings come alive with energy.

His use of color was revolutionary - he used complementary colors (like blue and orange) to create vibrancy and emotional intensity. Swirling, dynamic compositions characterized his later work, expressing psychological turbulence and spiritual transcendence.

Van Gogh was influenced by Japanese woodblock prints, which inspired his bold outlines and flat color areas. He often painted outdoors (en plein air) to capture the changing light and atmosphere, working quickly to preserve spontaneity and emotion.''',
            'notable_works': [
                'The Starry Night (1889)',
                'Sunflowers (1888)',
                'Café Terrace at Night (1888)',
                'The Bedroom (1888)',
                'Irises (1889)',
                'Wheatfield with Crows (1890)'
            ],
            'influences': '''Van Gogh was profoundly influenced by French Impressionists like Claude Monet, Japanese ukiyo-e prints, and the peasant paintings of Jean-François Millet. His emotional intensity and expressive use of color directly inspired the Fauvists and German Expressionists.

His legacy extends beyond painting - his letters to his brother Theo provide invaluable insights into the creative process. Van Gogh proved that art could express the deepest human emotions, making him a symbol of the tortured genius and the transformative power of perseverance. His impact on modern art cannot be overstated.'''
        },
        'Leonardo da Vinci': {
            'name': 'Leonardo da Vinci',
            'birth_year': '1452',
            'death_year': '1519',
            'nationality': 'Italian',
            'biography': '''Leonardo da Vinci, born in 1452 in Vinci, Italy, epitomizes the Renaissance ideal of the "universal man" - excelling as a painter, scientist, engineer, and inventor. Apprenticed to the artist Verrocchio in Florence, Leonardo's talent quickly surpassed his master's.

Throughout his life, Leonardo served various patrons including the Medici family, Ludovico Sforza of Milan, and King Francis I of France. His insatiable curiosity led him to study anatomy, engineering, geology, and botany, filling thousands of notebook pages with observations and inventions centuries ahead of their time.

Despite his genius, Leonardo was notoriously slow to complete paintings, often leaving works unfinished as new ideas captured his attention. He spent his final years in France as a guest of King Francis I, continuing his scientific studies until his death in 1519.

His influence on art and science remains unparalleled. Leonardo's systematic approach to studying nature and his integration of art and science established new standards that still inspire today.''',
            'style': '''Leonardo pioneered sfumato, a technique of subtle, almost imperceptible transitions between colors and tones, creating soft, atmospheric effects. This gave his portraits an unprecedented lifelike quality and psychological depth.

His mastery of perspective, anatomy, and light was unmatched. Leonardo studied human corpses to understand muscle structure, bone placement, and movement, enabling him to depict the human form with scientific accuracy infused with grace and beauty.

He emphasized the importance of observing nature directly, sketching from life to capture authentic detail. His paintings demonstrate perfect balance between realism and idealization, technical precision and emotional expression, making them eternally captivating.''',
            'notable_works': [
                'Mona Lisa (1503-1519)',
                'The Last Supper (1495-1498)',
                'Vitruvian Man (1490)',
                'Lady with an Ermine (1489-1491)',
                'The Virgin of the Rocks (1483-1486)',
                'Salvator Mundi (c. 1500)'
            ],
            'influences': '''Leonardo was influenced by his teacher Verrocchio, ancient Roman art, and the mathematical principles of perspective developed by Brunelleschi. His scientific method and artistic innovations profoundly influenced High Renaissance masters like Raphael and Michelangelo.

His notebooks, containing revolutionary concepts for flying machines, hydraulics, and anatomy, demonstrated the power of observational science. Leonardo showed that art and science are inseparable, establishing a legacy that continues to inspire interdisciplinary thinking and innovation across all fields of human endeavor.'''
        }
    }
    
    # Return mock data if available
    if artwork.artist in mock_artists:
        return mock_artists[artwork.artist]
    
    # Generic fallback
    return {
        'name': artwork.artist or 'Unknown Artist',
        'birth_year': None,
        'death_year': None,
        'nationality': None,
        'biography': f'''Information about {artwork.artist or "this artist"} is currently being compiled. {artwork.artist or "This artist"} created "{artwork.title}" {f"in {artwork.year}" if artwork.year else ""}, demonstrating mastery of {artwork.movement or "their artistic style"}.

The artist's work represents a significant contribution to art history, showcasing technical skill and creative vision that continues to inspire viewers today.

This artwork exemplifies the artistic principles and cultural context of its time, making it an important piece for study and appreciation.''',
        'style': f'''The artistic style of {artwork.artist or "this artist"} is characterized by techniques typical of {artwork.movement or "their period"}, demonstrating skillful use of composition, color, and form.''',
        'notable_works': [artwork.title],
        'influences': f'''The work of {artwork.artist or "this artist"} reflects the artistic movements and cultural influences of their time, contributing to the evolution of {artwork.movement or "art history"}.'''
    }
