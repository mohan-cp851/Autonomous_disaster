import os
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Local Guidelines Database based on Indian NDMA guidelines
NDMA_GUIDELINES = {
    "flood": """
[NDMA FLOOD EMERGENCY PROTOCOLS]
1. BEFORE FLOODING:
   - Identify evacuation routes and high grounds in your area (Pune, Mumbai, Kolhapur have mapping layers ready).
   - Keep emergency kit ready: dry foods, clean water, first-aid, flashlights, batteries.
   - Keep sandbags or barriers ready to block water entry.
2. DURING FLOODING:
   - Turn off main electrical switches and gas valves to avoid accidents.
   - Do not walk or drive through moving water. Even 6 inches of water can sweep you away.
   - Drink only boiled/chlorinated water. Avoid contact with flood waters (hazard of sewage, chemicals, electric cables).
   - Head to designated relief shelters (e.g. Pune Municipal Shelter, Mumbai Central Relief Camp).
3. AFTER FLOODING:
   - Stay tuned to radio/alerts. Watch out for snakes/scorpions carried by water.
   - Get medical help for minor wounds immediately to prevent infection.
   - Do not enter damaged buildings until inspected.
    """,
    "earthquake": """
[NDMA EARTHQUAKE EMERGENCY PROTOCOLS]
1. DURING TREMORS (DROP, COVER, HOLD ON):
   - DROP to your hands and knees.
   - COVER your head and neck under a sturdy table or desk.
   - HOLD ON until the shaking stops.
   - If outdoors, move to an open area clear of buildings, trees, electric wires, and overpasses.
   - If driving, pull over to a safe open space, keep seatbelt on.
2. AFTER TREMORS:
   - Expect aftershocks. Inspect gas, water, and power lines. Turn off mains if leaks/damage are found.
   - Do not use elevators.
   - Report trapped victims to the Rescue Team Dispatch portal immediately.
   - Check local advisories via SMS Alerts panel.
    """,
    "fire": """
[NDMA WILDFIRE & BUILDING FIRE EMERGENCY PROTOCOLS]
1. IMMEDIATE ACTION:
   - Raise fire alarm. Sound warning.
   - Crawl low under smoke. Cleaner air is near the floor.
   - Before opening doors, check with the back of your hand. If hot, DO NOT open. Find alternate route.
   - Do not use elevators. Use fire escape stairs.
2. IF TRAPPED:
   - Close all doors. Seal cracks with wet clothes/towels to block smoke.
   - Signal from windows using a bright cloth or flashlight.
3. EXTINGUISHING:
   - Only attempt to fight small fires with proper extinguishers (PASS: Pull, Aim, Squeeze, Sweep).
   - For chemical/electrical fires, do not throw water. Use CO2 or dry powder.
    """,
    "cyclone": """
[NDMA CYCLONE & HIGH WINDS PROTOCOLS]
1. BEFORE LANDFALL:
   - Secure loose outdoor objects (roof tiles, sheets, pots).
   - Board up glass windows or tape them in a cross shape.
   - Keep mobile phones, power banks, and torches fully charged.
   - Keep livestock in safe, high shelters.
2. DURING CYCLONE:
   - Remain indoors. Close all doors and windows.
   - Do not go outside even if winds calm down (it might be the eye of the storm, winds will resume rapidly).
   - Disconnect heavy appliances to prevent surge damage.
3. AFTER LANDFALL:
   - Watch out for fallen trees, live electrical wires, and damaged poles.
   - Do not visit the coast or sightseeing. Boil water before drinking.
    """,
    "landslide": """
[NDMA LANDSLIDE EMERGENCY PROTOCOLS]
1. WARNING SIGNS:
   - Sudden cracking in pavements, driveways, or building walls.
   - Tilted trees, poles, or fences.
   - Muddy water flow in rocky slopes or unusual mud discharge.
2. DURING LANDSLIDE:
   - Evacuate immediately if advised. Head to designated high grounds or shelters.
   - If trapped, curl into a tight ball, cover your head to protect yourself from rocks/debris.
   - Avoid river valleys and low areas as landslides often block streams and cause flash floods.
3. AFTER LANDSLIDE:
   - Avoid slide areas. Debris may slide further.
   - Watch out for broken gas/water lines and report immediately.
    """,
    "tsunami": """
[NDMA TSUNAMI COASTAL EMERGENCY PROTOCOLS]
1. IMMEDIATE ACTION:
   - If you feel an earthquake, notice a sudden sea level drop/rebound, or hear a loud ocean roar: move inland to high ground immediately.
   - Head to a height of at least 100 feet (30 meters) above sea level or 2 miles inland.
   - Do not go to the beach to watch the tsunami.
   - Keep away from river channels leading to the ocean.
2. ONCE SAFE:
   - Stay on high ground. Tsunami waves can arrive in clusters over several hours.
   - Do not enter damaged structures. Wait for official clearance from rescue commands.
    """,
    "general": """
[NDMA GENERAL EMERGENCY ASSISTANCE]
- Standard Emergency Hotline: 112 (All-in-one disaster relief)
- National Disaster Response Force (ND NDRF): 011-23438091
- State Disaster Management Authority (SDMA Maharashtra): 022-22027990
- District Command Centers:
  - Pune: 020-2561234
  - Mumbai: 022-22620232
  - Nashik: 0253-223412
  - Nagpur: 0712-256266
- Always verify SMS alerts. Follow instructions from rescue personnel and shelter staff.
    """
}

def get_fallback_response(query):
    """
    Simple TF-IDF classification to fetch the most relevant NDMA guideline section.
    """
    keys = list(NDMA_GUIDELINES.keys())
    docs = list(NDMA_GUIDELINES.values())
    
    # Setup Vectorizer
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(docs)
    query_vec = vectorizer.transform([query])
    
    # Calculate similarities
    similarities = cosine_similarity(query_vec, tfidf_matrix)[0]
    max_idx = similarities.argmax()
    
    # If similarity score is very low, return general info
    if similarities[max_idx] < 0.1:
        return NDMA_GUIDELINES["general"]
        
    return docs[max_idx]

def ask_copilot(query, ollama_url="http://localhost:11434", model="qwen2.5-coder:7b"):
    """
    Queries Ollama if available, otherwise falls back to NDMA TF-IDF guidelines.
    """
    try:
        # Check if Ollama is running and has the model
        resp = requests.get(f"{ollama_url}/api/tags", timeout=1.5)
        if resp.status_code == 200:
            # Prepare payload for Ollama
            prompt = f"""
You are the AI Emergency Response Copilot for the Disaster Response Command System.
Use standard NDMA disaster guidelines. Keep answers short, actionable, and formatted in markdown.

User Question: {query}
"""
            response = requests.post(f"{ollama_url}/api/generate", json={
                "model": model,
                "prompt": prompt,
                "stream": False
            }, timeout=8.0)
            
            if response.status_code == 200:
                return response.json().get('response', '')
    except Exception:
        pass
        
    # Offline Fallback
    return get_fallback_response(query)
