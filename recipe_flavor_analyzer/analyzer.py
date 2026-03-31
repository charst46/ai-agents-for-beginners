from .models import AnalysisResult
from .parser import parse_recipe
from .scorer import compute_scores, detect_imbalances, determine_decision
from .suggestions import generate_fixes, generate_substitutions, generate_pantry_suggestions


def analyze_recipe(
    recipe_text: str,
    pantry_items: list[str] | None = None,
    constraints: list[str] | None = None,
) -> dict:
    """Analyze a recipe for flavor balance and return suggestions.

    Args:
        recipe_text: Raw recipe text containing ingredients.
        pantry_items: Optional list of ingredients available in the pantry.
        constraints: Optional dietary constraints (e.g., "no_dairy", "vegan").

    Returns:
        Dictionary with flavor_scores, diagnosis, decision, fixes,
        pantry_suggestions, and substitutions.
    """
    # 1. Parse ingredients
    ingredients = parse_recipe(recipe_text)

    # 2-3. Map to flavors and score
    profile = compute_scores(ingredients)
    scores = profile.to_scores()

    # 4. Detect imbalances
    imbalances = detect_imbalances(scores)

    # 5. Generate fixes
    fixes = generate_fixes(imbalances)

    # 6. Pantry matching
    pantry_suggestions = generate_pantry_suggestions(imbalances, pantry_items, constraints)

    # 7. Substitutions
    substitutions = generate_substitutions(imbalances, pantry_items, constraints)

    # 8. Decision
    decision = determine_decision(scores, imbalances)

    # Build diagnosis string
    if imbalances:
        diagnosis = "; ".join(desc for _key, desc in imbalances)
    else:
        diagnosis = "Recipe is well-balanced"

    result = AnalysisResult(
        flavor_scores=scores,
        diagnosis=diagnosis,
        decision=decision,
        fixes=fixes,
        pantry_suggestions=pantry_suggestions,
        substitutions=substitutions,
    )

    return result.to_dict()
