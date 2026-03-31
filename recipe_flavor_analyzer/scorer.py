from .models import Ingredient, FlavorProfile
from .parser import match_ingredient_to_flavor

# Max expected raw score per category before capping at 10.
# A typical heavily-loaded category (e.g., 3 fat sources) yields raw ~7-9.
# We map raw scores to 0-10 by: score = raw / MAX_RAW * 10, capped at 10.
_MAX_RAW = 7.0


def compute_scores(ingredients: list[Ingredient]) -> FlavorProfile:
    """Aggregate flavor contributions from all ingredients into a profile."""
    profile = FlavorProfile()

    for ingredient in ingredients:
        flavors = match_ingredient_to_flavor(ingredient)
        if flavors is None:
            continue

        profile.salt += flavors.get("salt", 0)
        profile.fat += flavors.get("fat", 0)
        profile.acid += flavors.get("acid", 0)
        profile.sweet += flavors.get("sweet", 0)
        profile.umami += flavors.get("umami", 0)
        profile.heat += flavors.get("heat", 0)

    # Normalize to 0-10 scale
    profile.salt = min(10, profile.salt / _MAX_RAW * 10)
    profile.fat = min(10, profile.fat / _MAX_RAW * 10)
    profile.acid = min(10, profile.acid / _MAX_RAW * 10)
    profile.sweet = min(10, profile.sweet / _MAX_RAW * 10)
    profile.umami = min(10, profile.umami / _MAX_RAW * 10)
    profile.heat = min(10, profile.heat / _MAX_RAW * 10)

    return profile


def detect_imbalances(scores: dict[str, int]) -> list[tuple[str, str]]:
    """Detect flavor imbalances and return (issue_key, description) pairs."""
    # If all scores are 0, no ingredients were recognized — nothing to analyze
    if all(v == 0 for v in scores.values()):
        return []

    imbalances: list[tuple[str, str]] = []

    fat = scores["fat"]
    acid = scores["acid"]
    salt = scores["salt"]
    sweet = scores["sweet"]
    umami = scores["umami"]
    heat = scores["heat"]

    # High fat, low acid → heavy/flat
    if fat > 7 and acid < 3:
        imbalances.append(("needs_acid", "High fat, low acid \u2192 will taste heavy and flat"))

    # Low salt → under-seasoned (only flag if other flavors are present)
    if salt < 3 and max(fat, acid, sweet, umami, heat) > 3:
        imbalances.append(("needs_salt", "Low salt \u2192 under-seasoned"))

    # High sweet, low acid → cloying
    if sweet > 7 and acid < 3:
        imbalances.append(("needs_acid_for_sweet", "High sweet, low acid \u2192 will taste cloying"))

    # High heat, low fat → harsh
    if heat > 7 and fat < 3:
        imbalances.append(("needs_fat", "High heat, low fat \u2192 heat will feel harsh"))

    # Low umami and low salt → lacks depth (only if recipe has substance)
    if umami < 2 and salt < 3 and max(fat, acid, sweet, heat) > 3:
        imbalances.append(("needs_depth", "Low umami and salt \u2192 lacks depth"))

    # High acid, low fat → too sharp
    if acid > 7 and fat < 3:
        imbalances.append(("needs_fat_for_acid", "High acid, low fat \u2192 will taste too sharp"))

    # All mid-range, no contrast → flat
    all_values = [fat, acid, salt, sweet, umami, heat]
    if all(3 <= v <= 6 for v in all_values) and max(all_values) - min(all_values) < 2:
        imbalances.append(("flat", "All flavors are mid-range with no contrast \u2192 flat"))

    return imbalances


def determine_decision(scores: dict[str, int], imbalances: list[tuple[str, str]]) -> str:
    """Return KEEP, TWEAK, or RESCUE based on scores and imbalances."""
    all_values = list(scores.values())

    # RESCUE: any extreme score
    if any(v > 8 for v in all_values) or any(v < 2 for v in all_values if scores.get("heat", 0) != v):
        # Don't penalize low heat — many recipes have no heat intentionally
        non_heat = {k: v for k, v in scores.items() if k != "heat"}
        if any(v > 8 for v in non_heat.values()) or any(v < 2 for v in non_heat.values()):
            if len(imbalances) >= 2:
                return "RESCUE"

    if imbalances:
        return "TWEAK"

    return "KEEP"
