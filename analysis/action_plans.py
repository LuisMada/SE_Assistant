"""
Dynamic theme clustering and action plan generation for high-priority issues
"""
import logging
import os
import json
from typing import List, Dict, Any, Tuple
import sqlite3
import openai

logger = logging.getLogger(__name__)

# Directory to store workflow reference files
WORKFLOWS_DIR = "workflows"

def get_high_priority_reviews(db_conn) -> List[Dict[str, Any]]:
    """
    Get high priority reviews (priority 1-2, Negative or Neutral sentiment)
    
    Args:
        db_conn: Database connection
        
    Returns:
        List of high priority review dictionaries
    """
    try:
        cursor = db_conn.cursor()
        
        # Get reviews with priority 1-2 and negative/neutral sentiment
        cursor.execute('''
        SELECT r.*, s.sentiment, p.priority_level
        FROM reviews r
        JOIN priorities p ON r.review_id = p.review_id
        JOIN sentiment s ON r.review_id = s.review_id
        WHERE p.priority_level <= 2 
        AND (s.sentiment = 'Negative' OR s.sentiment = 'Neutral')
        ORDER BY p.priority_level, r.date_added DESC
        LIMIT 50
        ''')
        
        reviews = [dict(zip([column[0] for column in cursor.description], row)) 
                  for row in cursor.fetchall()]
        
        # Get categories for each review
        for review in reviews:
            cursor.execute('''
            SELECT category FROM categories
            WHERE review_id = ?
            ''', (review['review_id'],))
            
            categories = [row[0] for row in cursor.fetchall()]
            review['categories'] = categories
        
        return reviews
    
    except Exception as e:
        logger.error(f"Error retrieving high priority reviews: {e}")
        return []

def cluster_reviews_into_themes(reviews: List[Dict[str, Any]], api_key: str) -> List[Dict[str, Any]]:
    """
    Use OpenAI to cluster reviews into common themes
    
    Args:
        reviews: List of review dictionaries
        api_key: OpenAI API key
        
    Returns:
        List of theme dictionaries, each containing title, summary, and related reviews
    """
    if not reviews:
        return []
    
    try:
        # Configure OpenAI client
        client = openai.OpenAI(api_key=api_key)
        
        # Prepare the review data for clustering
        review_texts = []
        for review in reviews:
            review_info = {
                "id": review['review_id'],
                "text": review['review_text'],
                "rating": review['rating'],
                "sentiment": review.get('sentiment', 'Unknown'),
                "priority": review.get('priority_level', 5),
                "categories": review.get('categories', [])
            }
            review_texts.append(json.dumps(review_info))
        
        # Create prompt for OpenAI
        prompt = f"""
You are analyzing app reviews to identify common themes and issues.
Below are high-priority app reviews in JSON format that need to be clustered into themes.

Each JSON includes:
- id: unique identifier for the review
- text: the review content
- rating: star rating (1-5)
- sentiment: sentiment analysis (Positive, Neutral, Negative)
- priority: priority level (1-5, with 1 being highest priority)
- categories: list of categories assigned to the review

Reviews:
{review_texts}

Analyze these reviews and cluster them into 2-5 common themes or issues.
For each theme, provide:
1. A short, descriptive title (max 5 words)
2. A brief summary of the issue (1-2 sentences)
3. The IDs of reviews that belong to this theme

Return the results as a JSON array with this format:
[
  {{
    "title": "Theme Title",
    "summary": "Brief description of the issue",
    "review_ids": ["id1", "id2", ...]
  }},
  ...
]

Be specific and practical in your themes. Focus on actionable issues.
"""
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-16k",
            messages=[
                {"role": "system", "content": "You are an expert at analyzing app user feedback and clustering related issues."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=2000
        )
        
        # Parse the themes from the response
        themes_json = response.choices[0].message.content.strip()
        
        # Handle different formats that might be returned
        # Sometimes the API returns the JSON with code block formatting
        if themes_json.startswith("```json"):
            themes_json = themes_json[7:-3].strip()
        elif themes_json.startswith("```"):
            themes_json = themes_json[3:-3].strip()
            
        themes = json.loads(themes_json)
        
        # Enrich the themes with the actual review objects
        for theme in themes:
            theme_reviews = []
            for review_id in theme['review_ids']:
                for review in reviews:
                    if review['review_id'] == review_id:
                        theme_reviews.append(review)
                        break
            theme['reviews'] = theme_reviews
            theme['count'] = len(theme_reviews)
            
        return themes
        
    except Exception as e:
        logger.error(f"Error clustering reviews into themes: {e}")
        return []

def get_workflow_content(theme_title: str) -> str:
    """
    Get the content of a workflow file that matches the theme title
    
    Args:
        theme_title: Title of the theme
        
    Returns:
        Content of the workflow file, or empty string if not found
    """
    # Create workflows directory if it doesn't exist
    if not os.path.exists(WORKFLOWS_DIR):
        os.makedirs(WORKFLOWS_DIR)
        
    # Generate a filename from the theme title
    filename = theme_title.lower().replace(" ", "_") + ".txt"
    filepath = os.path.join(WORKFLOWS_DIR, filename)
    
    # Check if the file exists
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading workflow file {filepath}: {e}")
            
    return ""

def generate_action_plan(theme: Dict[str, Any], workflow_content: str, api_key: str) -> Dict[str, Any]:
    """
    Generate an action plan for a theme using OpenAI
    
    Args:
        theme: Theme dictionary
        workflow_content: Content of the workflow file (if found)
        api_key: OpenAI API key
        
    Returns:
        Dictionary with action plan and suggested user response
    """
    try:
        # Configure OpenAI client
        client = openai.OpenAI(api_key=api_key)
        
        # Prepare review information
        review_info = []
        for review in theme['reviews']:
            review_info.append(f"- \"{review['review_text']}\" (Rating: {review['rating']}, Sentiment: {review.get('sentiment', 'Unknown')})")
        
        reviews_text = "\n".join(review_info)
        
        # Create prompt for OpenAI
        if workflow_content:
            workflow_reference = f"Here is an existing workflow for this type of issue:\n\n{workflow_content}\n\n"
            instruction = "Update or adapt the action plan based on the current reviews and the existing workflow. Add any missing steps."
        else:
            workflow_reference = ""
            instruction = "Create a comprehensive action plan for this issue."
            
        prompt = f"""
You are creating an action plan for a theme of high-priority app reviews.

Theme: {theme['title']}
Summary: {theme['summary']}

Reviews in this theme:
{reviews_text}

{workflow_reference}
{instruction}

Provide:
1. An internal action plan (4-6 bullet points) with concrete technical steps the development team should take
2. A suggested user response (2-3 sentences) that customer support can send to these users

Format your response as a JSON object with these keys:
- action_steps: Array of strings, each string is a bullet point for internal action
- user_response: String with the suggested response to users
"""
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert product manager who creates actionable plans for app issues."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1000
        )
        
        # Parse the action plan from the response
        plan_json = response.choices[0].message.content.strip()
        
        # Handle different formats that might be returned
        if plan_json.startswith("```json"):
            plan_json = plan_json[7:-3].strip()
        elif plan_json.startswith("```"):
            plan_json = plan_json[3:-3].strip()
            
        plan = json.loads(plan_json)
        
        # Return the action plan
        result = {
            "title": theme['title'],
            "summary": theme['summary'],
            "action_steps": plan['action_steps'],
            "user_response": plan['user_response'],
            "review_count": theme['count'],
            "review_samples": [r['review_text'] for r in theme['reviews'][:3]]  # Include up to 3 sample reviews
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating action plan for theme {theme['title']}: {e}")
        
        # Return a basic structure even if there was an error
        return {
            "title": theme.get('title', 'Unknown Theme'),
            "summary": theme.get('summary', 'Could not generate summary'),
            "action_steps": ["Error generating action steps"],
            "user_response": "We're looking into this issue and will get back to you soon.",
            "review_count": theme.get('count', 0),
            "review_samples": []
        }

def generate_action_plans(db_conn, api_key: str) -> List[Dict[str, Any]]:
    """
    Generate action plans for high-priority issues
    
    Args:
        db_conn: Database connection
        api_key: OpenAI API key
        
    Returns:
        List of action plan dictionaries
    """
    if not api_key:
        logger.error("OpenAI API key not provided for action plan generation")
        return []
        
    try:
        # Get high priority reviews
        high_priority_reviews = get_high_priority_reviews(db_conn)
        
        if not high_priority_reviews:
            logger.info("No high priority reviews found for action planning")
            return []
            
        logger.info(f"Found {len(high_priority_reviews)} high priority reviews for action planning")
        
        # Cluster reviews into themes
        themes = cluster_reviews_into_themes(high_priority_reviews, api_key)
        
        if not themes:
            logger.warning("No themes identified from reviews")
            return []
            
        logger.info(f"Clustered reviews into {len(themes)} themes")
        
        # Generate action plans for each theme
        action_plans = []
        for theme in themes:
            # Get the matching workflow if available
            workflow_content = get_workflow_content(theme['title'])
            
            # Generate the action plan
            logger.info(f"Generating action plan for theme: {theme['title']}")
            action_plan = generate_action_plan(theme, workflow_content, api_key)
            action_plans.append(action_plan)
            
        return action_plans
        
    except Exception as e:
        logger.error(f"Error in action plan generation: {e}")
        return []

def get_action_plans(db_conn) -> List[Dict[str, Any]]:
    """
    Get action plans for high-priority issues (dynamic clustering version)
    
    Args:
        db_conn: Database connection
        
    Returns:
        List of action plan dictionaries
    """
    try:
        # Check if we have stored action plans
        cursor = db_conn.cursor()
        cursor.execute('''
        SELECT * FROM action_plans
        ORDER BY id DESC
        LIMIT 20
        ''')
        
        action_plans = [dict(zip([column[0] for column in cursor.description], row)) 
                       for row in cursor.fetchall()]
                       
        return action_plans
        
    except Exception as e:
        logger.error(f"Error retrieving action plans: {e}")
        return []

def save_action_plans(db_conn, action_plans: List[Dict[str, Any]]) -> bool:
    """
    Save generated action plans to the database
    
    Args:
        db_conn: Database connection
        action_plans: List of action plan dictionaries
        
    Returns:
        Boolean indicating success
    """
    if not action_plans:
        return False
        
    try:
        cursor = db_conn.cursor()
        
        # Clear existing action plans
        cursor.execute('DELETE FROM action_plans')
        
        # Insert new action plans
        for plan in action_plans:
            cursor.execute('''
            INSERT INTO action_plans (
                title, summary, action_steps, user_response, review_count
            ) VALUES (?, ?, ?, ?, ?)
            ''', (
                plan['title'],
                plan['summary'],
                json.dumps(plan['action_steps']),
                plan['user_response'],
                plan['review_count']
            ))
        
        db_conn.commit()
        logger.info(f"Saved {len(action_plans)} action plans to database")
        return True
        
    except Exception as e:
        logger.error(f"Error saving action plans: {e}")
        db_conn.rollback()
        return False