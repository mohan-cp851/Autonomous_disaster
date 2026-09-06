import os
import pickle
import numpy as np
import cv2
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_DIR = os.path.join(BASE_DIR, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "disaster_risk_model.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "disaster_risk_scaler.pkl")

# Target disasters: 0: Normal, 1: Flood, 2: Earthquake, 3: Fire, 4: Cyclone, 5: Landslide, 6: Tsunami
DISASTER_MAP = {
    0: "No Risk (Normal)",
    1: "Flood",
    2: "Earthquake",
    3: "Wildfire",
    4: "Cyclone",
    5: "Landslide",
    6: "Tsunami"
}

def train_risk_model():
    """
    Generates a synthetic training dataset based on realistic ranges and trains a RandomForestClassifier.
    """
    os.makedirs(MODEL_DIR, exist_ok=True)
    np.random.seed(42)
    n_samples = 1500
    
    # Features: Rainfall (mm), Temperature (C), Water Level (m), Seismic Activity (Richter), Wind Speed (km/h), Humidity (%)
    # Normal state
    X_normal = np.random.uniform(low=[0, 15, 0.5, 0.5, 5, 40], high=[50, 32, 2.0, 2.5, 25, 75], size=(600, 6))
    y_normal = np.zeros(600)
    
    # Flood state: high rainfall, high water level
    X_flood = np.random.uniform(low=[150, 20, 4.0, 0.5, 10, 80], high=[400, 35, 9.0, 2.0, 40, 100], size=(150, 6))
    y_flood = np.ones(150)
    
    # Earthquake state: high seismic activity
    X_earthquake = np.random.uniform(low=[0, 10, 0.5, 4.5, 5, 20], high=[50, 40, 2.5, 8.5, 30, 80], size=(150, 6))
    y_earthquake = np.ones(150) * 2
    
    # Fire state: high temp, low humidity, low rainfall
    X_fire = np.random.uniform(low=[0, 38, 0.1, 0.2, 10, 5], high=[5, 50, 1.2, 1.5, 45, 25], size=(150, 6))
    y_fire = np.ones(150) * 3
    
    # Cyclone state: high wind speed, high rainfall, low temp
    X_cyclone = np.random.uniform(low=[80, 15, 1.0, 0.5, 80, 70], high=[300, 28, 4.0, 1.5, 220, 95], size=(150, 6))
    y_cyclone = np.ones(150) * 4
    
    # Landslide state: high rainfall on hilly terrains + mild tremors
    X_landslide = np.random.uniform(low=[120, 15, 0.5, 2.0, 10, 75], high=[350, 28, 3.0, 4.2, 35, 95], size=(150, 6))
    y_landslide = np.ones(150) * 5
    
    # Tsunami state: high seismic activity near coast (seismic > 6.0)
    X_tsunami = np.random.uniform(low=[10, 18, 1.0, 6.0, 20, 70], high=[150, 30, 8.0, 9.0, 80, 95], size=(100, 6))
    y_tsunami = np.ones(100) * 6
    
    X = np.vstack([X_normal, X_flood, X_earthquake, X_fire, X_cyclone, X_landslide, X_tsunami])
    y = np.concatenate([y_normal, y_flood, y_earthquake, y_fire, y_cyclone, y_landslide, y_tsunami])
    
    # Shuffle
    indices = np.arange(X.shape[0])
    np.random.shuffle(indices)
    X = X[indices]
    y = y[indices]
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_scaled, y)
    
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(model, f)
        
    with open(SCALER_PATH, 'wb') as f:
        pickle.dump(scaler, f)
        
    print("AI Risk Prediction Model trained and saved successfully.")

def predict_risk(rainfall, temp, water_level, seismic, wind_speed, humidity):
    """
    Predicts the risk probability of each disaster type.
    """
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
        train_risk_model()
        
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    with open(SCALER_PATH, 'rb') as f:
        scaler = pickle.load(f)
        
    features = np.array([[rainfall, temp, water_level, seismic, wind_speed, humidity]])
    features_scaled = scaler.transform(features)
    
    probs = model.predict_proba(features_scaled)[0]
    preds = {DISASTER_MAP[i]: float(probs[i]) * 100 for i in range(len(probs))}
    
    # Get highest risk
    max_idx = np.argmax(probs)
    risk_type = DISASTER_MAP[max_idx]
    risk_prob = probs[max_idx] * 100
    
    if max_idx == 0:
        # If normal is highest, get the second highest risk
        other_probs = probs.copy()
        other_probs[0] = -1
        second_max_idx = np.argmax(other_probs)
        risk_type = DISASTER_MAP[second_max_idx]
        risk_prob = probs[second_max_idx] * 100
        
    if risk_prob < 15.0:
        level = "Low"
    elif risk_prob < 40.0:
        level = "Medium"
    elif risk_prob < 75.0:
        level = "High"
    else:
        level = "Critical"
        
    return {
        'predictions': preds,
        'highest_risk_type': risk_type,
        'highest_risk_probability': round(risk_prob, 2),
        'risk_level': level
    }

def analyze_satellite_image(filepath):
    """
    Uses OpenCV to analyze satellite/drone images for fire, flood, or damage.
    Generates a highlighted output file and returns severity metrics.
    """
    img = cv2.imread(filepath)
    if img is None:
        return {'disaster_type': 'Unknown', 'severity_score': 0.0, 'annotated_filename': None}
        
    h, w, _ = img.shape
    total_pixels = h * w
    
    # Convert to HSV for robust color segmentation
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 1. Fire detection (Red/Orange/Yellow in HSV)
    # Red has two ranges in HSV
    lower_red1 = np.array([0, 120, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 120, 100])
    upper_red2 = np.array([180, 255, 255])
    lower_orange = np.array([11, 120, 100])
    upper_orange = np.array([25, 255, 255])
    
    mask_r1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_r2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_o = cv2.inRange(hsv, lower_orange, upper_orange)
    
    fire_mask = mask_r1 | mask_r2 | mask_o
    fire_pixels = cv2.countNonZero(fire_mask)
    fire_pct = (fire_pixels / total_pixels) * 100
    
    # 2. Flood detection
    # Detect both blue/gray water and muddy brown floodwater.

    # Blue / blue-gray water
    lower_blue_water = np.array([80, 20, 30])
    upper_blue_water = np.array([135, 255, 210])
    blue_water_mask = cv2.inRange(
        hsv,
        lower_blue_water,
        upper_blue_water
    )

    # Muddy brown floodwater
    lower_muddy_water = np.array([5, 25, 35])
    upper_muddy_water = np.array([35, 200, 220])
    muddy_water_mask = cv2.inRange(
        hsv,
        lower_muddy_water,
        upper_muddy_water
    )

    # Combine both water masks
    water_mask = cv2.bitwise_or(
        blue_water_mask,
        muddy_water_mask
    )

    # Clean small isolated regions
    kernel = np.ones((5, 5), np.uint8)
    water_mask = cv2.morphologyEx(
        water_mask,
        cv2.MORPH_OPEN,
        kernel
    )
    water_mask = cv2.morphologyEx(
        water_mask,
        cv2.MORPH_CLOSE,
        kernel
    )

    water_pixels = cv2.countNonZero(water_mask)
    water_pct = (water_pixels / total_pixels) * 100
    
    # 3. Earthquake/Landslide damage (High edge density indicating debris/cracks)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edge_pixels = cv2.countNonZero(edges)
    edge_pct = (edge_pixels / total_pixels) * 100

    print("=" * 60)
    print(f"FIRE PERCENTAGE  : {fire_pct:.2f}%")
    print(f"WATER PERCENTAGE : {water_pct:.2f}%")
    print(f"EDGE PERCENTAGE  : {edge_pct:.2f}%")
    print("=" * 60)
    
    # Determine the classification and draw highlight contours
    disaster_type = "Normal"
    severity_score = 0.0
    annotated_img = img.copy()
    
    if water_pct > 8.0 and water_pct > fire_pct * 1.5:
        # Flood has stronger evidence than fire
        disaster_type = "Flood"
        severity_score = min(water_pct * 1.2, 100.0)

        # Highlight detected flood-water regions in green
        contours, _ = cv2.findContours(
            water_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        cv2.drawContours(
            annotated_img,
            contours,
            -1,
            (0, 255, 0),
            2
        )

        cv2.putText(
            annotated_img,
            f"DETECTED: Flood (Severity: {round(severity_score, 1)}%)",
            (15, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 0, 0),
            2
        )
    elif fire_pct > 2.5:
        # Fire evidence is stronger
        disaster_type = "Wildfire"
        severity_score = min(fire_pct * 8, 100.0)

        # Highlight fire regions in green
        contours, _ = cv2.findContours(
            fire_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        cv2.drawContours(
            annotated_img,
            contours,
            -1,
            (0, 255, 0),
            2
        )

        cv2.putText(
            annotated_img,
            f"DETECTED: Wildfire (Severity: {round(severity_score, 1)}%)",
            (15, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )
    elif edge_pct > 8.0:
        disaster_type = "Structural Damage / Landslide"
        # Debris edge density mapping
        severity_score = min((edge_pct - 5.0) * 10, 100.0)
        severity_score = max(severity_score, 15.0)
        # Highlight edges by overlaying the Canny output in red
        annotated_img[edges > 0] = [0, 0, 255]
        cv2.putText(annotated_img, f"DETECTED: Debris & Structural Damage ({round(severity_score, 1)}%)", (15, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    else:
        cv2.putText(annotated_img, "STATUS: Normal terrain", (15, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
    # Save output annotated image
    filename = os.path.basename(filepath)
    annotated_filename = "annotated_" + filename
    annotated_path = os.path.join(os.path.dirname(filepath), annotated_filename)
    cv2.imwrite(annotated_path, annotated_img)

    # Convert severity score into a human-readable severity level
    if severity_score >= 75:
        severity_level = "Critical"
    elif severity_score >= 50:
           severity_level = "High"
    elif severity_score >= 25:
           severity_level = "Moderate"
    else:
        severity_level = "Low"

    # Disaster-specific safety precautions
    precautions = {
        "Flood": [
            "Move to higher ground immediately if water levels are rising.",
            "Avoid walking or driving through flood water.",
            "Stay away from electric poles, wires, and submerged electrical equipment.",
            "Keep drinking water and essential medicines ready."
        ],

        "Wildfire": [
            "Move away from the fire and follow official evacuation instructions.",
            "Avoid smoke and use a protective mask if available.",
            "Keep doors and windows closed when smoke is heavy.",
            "Do not attempt to cross active fire zones."
        ],

        "Structural Damage / Landslide": [
            "Stay away from damaged buildings, slopes, and unstable structures.",
            "Move to a safe open area if there is a risk of collapse.",
            "Avoid areas with visible cracks or falling debris.",
            "Follow instructions from rescue and emergency teams."
        ],

        "Normal": [
            "No immediate disaster indicators detected.",
            "Continue monitoring local alerts and environmental conditions."
        ],

        "Unknown": [
            "Image could not be analyzed.",
            "Use local emergency information and verify the situation manually."
        ]
    }

    return {
        'disaster_type': disaster_type,
        'severity_score': round(severity_score, 2),
        'severity_level': severity_level,
        'precautions': precautions.get(
            disaster_type,
            precautions["Unknown"]
        ),
        'annotated_filename': annotated_filename
    }
