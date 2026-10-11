import difflib
import re

CATEGORY_KEYWORDS = {
    "Grains & Cereals": [
        "rice", "basmati", "sona masoori", "poha", "atta", "wheat", "wheat flour",
        "maida", "suji", "sooji", "rava", "semolina", "ragi", "jowar", "bajra",
        "millet", "barley", "oats", "daliya", "dalia", "vermicelli", "semiya",
    ],
    "Lentils & Pulses": [
        "dal", "daal", "lentil", "toor", "tuvar", "arhar", "moong", "mung",
        "masoor", "chana", "chickpea", "urad", "rajma", "lobia", "chole", "kulthi",
    ],
    "Spices & Masalas": [
        "cumin", "jeera", "mustard", "rai", "cardamom", "elaichi", "turmeric",
        "haldi", "coriander", "dhania", "chilli", "chili", "mirch", "masala",
        "garam masala", "chaat masala", "pepper", "black pepper", "clove", "laung",
        "cinnamon", "dalchini", "bay leaf", "tej patta", "fennel", "saunf",
        "fenugreek", "methi", "ajwain", "hing", "asafoetida", "saffron", "kesar",
        "nutmeg", "jaiphal", "star anise", "paprika", "amchur", "kasuri methi",
    ],
    "Oils & Fats": [
        "oil", "mustard oil", "ghee", "vanaspati", "dalda",
    ],
    "Dairy Products": [
        "milk", "curd", "dahi", "yogurt", "yoghurt", "paneer", "butter",
        "cheese", "cream", "buttermilk", "chaas", "khoya", "mawa", "milk powder",
    ],
    "Vegetables": [
        "onion", "potato", "tomato", "garlic", "ginger", "green chilli", "capsicum",
        "bell pepper", "carrot", "cabbage", "cauliflower", "brinjal", "eggplant",
        "baingan", "okra", "bhindi", "spinach", "palak", "lauki", "bottle gourd",
        "ridge gourd", "tori", "karela", "bitter gourd", "pumpkin", "cucumber",
        "radish", "beetroot", "beans", "peas", "green peas", "coriander leaves",
        "curry leaves", "mint", "pudina", "methi leaves", "lemon", "drumstick",
        "sweet potato", "corn",
    ],
    "Beverages": [
        "tea", "chai", "green tea", "coffee", "horlicks", "bournvita", "juice",
    ],
    "Taste Essentials": [
        "salt", "namak", "rock salt", "black salt", "sendha namak", "sugar",
        "brown sugar", "cheeni", "jaggery", "gur", "honey", "sweetener",
        "stevia", "mishri",
    ],
    "Other Grains & Alternatives": [
        "quinoa", "couscous", "besan", "gram flour", "millet flour", "ragi flour",
        "jowar flour", "bajra flour", "rice flour", "corn flour", "cornflour",
        "oat flour", "almond flour", "amaranth", "rajgira", "buckwheat", "kuttu",
        "sabudana", "tapioca", "sattu",
    ],
}

CATEGORIES = list(CATEGORY_KEYWORDS) + ["Other"]

CATEGORY_EMOJI = {
    "Grains & Cereals": "🌾",
    "Lentils & Pulses": "🫘",
    "Spices & Masalas": "🌶️",
    "Oils & Fats": "🫒",
    "Dairy Products": "🥛",
    "Vegetables": "🥦",
    "Beverages": "☕",
    "Taste Essentials": "🧂",
    "Other Grains & Alternatives": "🥣",
    "Other": "📦",
}


def _normalize_word(word):
    """Turn simple plurals into singular: onions -> onion, oats -> oat."""
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def normalize(text):
    """Lowercase, keep letters only, singularise each word."""
    words = re.findall(r"[a-z]+", text.lower())
    return " ".join(_normalize_word(word) for word in words)


# One flat lookup: normalised keyword -> category
KEYWORD_TO_CATEGORY = {}
for _category, _words in CATEGORY_KEYWORDS.items():
    for _word in _words:
        KEYWORD_TO_CATEGORY[normalize(_word)] = _category

SINGLE_WORDS = [kw for kw in KEYWORD_TO_CATEGORY if " " not in kw]


def guess_category(name):
    """Return a category name, or None if we can't tell."""
    text = normalize(name)
    if not text:
        return None

    # 1) Exact whole-word / phrase match. The longest keyword wins,
    #    so "mustard oil" beats "mustard".
    padded = f" {text} "
    matches = [kw for kw in KEYWORD_TO_CATEGORY if f" {kw} " in padded]
    if matches:
        return KEYWORD_TO_CATEGORY[max(matches, key=len)]

    # 2) Fuzzy match for spelling variations ("tuvar daal", "jira").
    for word in text.split():
        close = difflib.get_close_matches(word, SINGLE_WORDS, n=1, cutoff=0.8)
        if close:
            return KEYWORD_TO_CATEGORY[close[0]]

    return None