import re
import numpy as np
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

COLOR_PALETTE = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (220, 38, 38),
    "blue": (37, 99, 235),
    "green": (22, 163, 74),
    "yellow": (234, 179, 8),
    "silver": (156, 163, 175),
    "gray": (107, 114, 128),
    "brown": (120, 53, 15)
}

def extract_dominant_color_name(image_path: str) -> str:
    """Extracts dominant color name using Euclidean distance on average pixel values."""
    try:
        with Image.open(image_path) as img:
            img = img.convert('RGB').resize((50, 50))
            pixels = np.array(img).reshape(-1, 3)
            avg_color = np.mean(pixels, axis=0)

            best_color = "unknown"
            min_dist = float('inf')
            for name, rgb in COLOR_PALETTE.items():
                dist = np.linalg.norm(avg_color - np.array(rgb))
                if dist < min_dist:
                    min_dist = dist
                    best_color = name
            return best_color
    except Exception:
        return ""

def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return ' '.join(text.split())

def match_items(new_item_text: str, candidate_items: list, threshold: float = 0.35):
    """
    Compares new item text against candidate items using TF-IDF and Cosine Similarity.
    """
    if not candidate_items:
        return []

    corpus = [clean_text(new_item_text)] + [
        clean_text(f"{item.title} {item.description} {item.location}") 
        for item in candidate_items
    ]

    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(corpus)

    similarity_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

    matches = []
    for idx, score in enumerate(similarity_scores):
        if score >= threshold:
            matches.append({
                'item': candidate_items[idx],
                'score': round(float(score) * 100, 1)
            })

    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches