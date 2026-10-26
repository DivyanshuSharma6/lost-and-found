import re
import numpy as np
from PIL import Image, UnidentifiedImageError
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
    "brown": (120, 53, 15),
}

def extract_dominant_color_name(image_path: str) -> str:
    """Extract dominant palette color from image."""
    try:
        with Image.open(image_path) as image:
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            thumb = image.convert("RGB").resize((50, 50), resample_filter)
            pixels = np.asarray(thumb, dtype=np.float32).reshape(-1, 3)
            average = pixels.mean(axis=0)

        return min(
            COLOR_PALETTE,
            key=lambda name: np.linalg.norm(
                average - np.asarray(COLOR_PALETTE[name], dtype=np.float32)
            ),
        )
    except (OSError, ValueError, UnidentifiedImageError):
        return ""

def clean_text(text: str) -> str:
    """Normalize text while retaining letters, digits, and spaces."""
    text = (text or "").casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())

def match_items(new_item_text: str, candidate_items: list, threshold: float = 0.15):
    """
    Hybrid matching engine combining:
    1. TF-IDF Cosine Similarity (semantic/term weights)
    2. Token Overlap Jaccard Index (exact keyword hits)
    3. Category match boost
    Returns candidates sorted descending by percentage score.
    """
    if not candidate_items:
        return []

    new_text = clean_text(new_item_text)
    if not new_text:
        return []

    new_tokens = set(new_text.split())
    candidates = []

    for item in candidate_items:
        cand_text = clean_text(
            f"{getattr(item, 'title', '') or ''} "
            f"{getattr(item, 'category', '') or ''} "
            f"{getattr(item, 'description', '') or ''} "
            f"{getattr(item, 'location', '') or ''}"
        )
        candidates.append((item, cand_text))

    items, candidate_texts = zip(*candidates)

    # 1. TF-IDF Cosine Similarity
    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            token_pattern=r"(?u)\b\w+\b"
        )
        matrix = vectorizer.fit_transform([new_text, *candidate_texts])
        tfidf_scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    except ValueError:
        tfidf_scores = np.zeros(len(candidate_texts))

    matches = []
    for idx, (item, c_text) in enumerate(zip(items, candidate_texts)):
        cand_tokens = set(c_text.split())

        # 2. Token overlap ratio
        overlap = len(new_tokens.intersection(cand_tokens))
        union = len(new_tokens.union(cand_tokens))
        jaccard = (overlap / union) if union > 0 else 0.0

        # 3. Category match bonus
        cat = getattr(item, 'category', '').lower()
        cat_boost = 0.15 if cat and cat in new_text else 0.0

        # Weighted composite score: 60% TF-IDF + 25% Jaccard Overlap + 15% Category Boost
        hybrid_score = (0.60 * tfidf_scores[idx]) + (0.25 * jaccard) + cat_boost
        hybrid_score = min(hybrid_score, 1.0)
        pct_score = round(float(hybrid_score) * 100, 1)

        if hybrid_score >= threshold:
            matches.append({
                "item": item,
                "score": pct_score
            })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches