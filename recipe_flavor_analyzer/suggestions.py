from .models import Substitution
from .flavor_map import CONSTRAINT_TAGS

# Map flavor need → possible ingredient additions
SUBSTITUTION_TABLE: dict[str, list[str]] = {
    "acid": ["lemon juice", "vinegar", "lime juice", "yogurt", "white wine"],
    "fat": ["butter", "olive oil", "cream", "coconut oil", "avocado"],
    "salt": ["salt", "soy sauce", "fish sauce", "miso", "parmesan"],
    "sweet": ["sugar", "honey", "maple syrup", "mirin", "brown sugar"],
    "umami": ["soy sauce", "mushrooms", "parmesan", "miso", "tomato paste"],
    "heat": ["chili flakes", "black pepper", "cayenne", "hot sauce", "ginger"],
}

# Map imbalance key → fix suggestions
FIX_TABLE: dict[str, list[str]] = {
    "needs_acid": [
        "Add 1-2 tsp lemon juice",
        "Add a splash of vinegar",
        "Reduce butter or oil slightly",
    ],
    "needs_salt": [
        "Season with salt to taste",
        "Add a small splash of soy sauce",
        "Add a pinch of flaky finishing salt",
    ],
    "needs_acid_for_sweet": [
        "Add 1-2 tsp lemon or lime juice",
        "Add a splash of vinegar to cut sweetness",
        "Reduce sugar slightly",
    ],
    "needs_fat": [
        "Add a knob of butter",
        "Drizzle with olive oil",
        "Add a dollop of cream or yogurt",
    ],
    "needs_depth": [
        "Add a splash of soy sauce or fish sauce",
        "Add mushrooms or tomato paste for umami",
        "Season more aggressively with salt",
    ],
    "needs_fat_for_acid": [
        "Add butter or olive oil to round out acidity",
        "Add cream or coconut milk",
        "Reduce acidic ingredients slightly",
    ],
    "flat": [
        "Add a squeeze of lemon for brightness",
        "Add a pinch of chili flakes for contrast",
        "Boost umami with a splash of soy sauce or parmesan",
    ],
}


def generate_fixes(imbalances: list[tuple[str, str]]) -> list[str]:
    """Generate fix suggestions for detected imbalances."""
    fixes: list[str] = []
    for key, _desc in imbalances:
        if key in FIX_TABLE:
            fixes.extend(FIX_TABLE[key])
    return fixes


def generate_substitutions(
    imbalances: list[tuple[str, str]],
    pantry_items: list[str] | None = None,
    constraints: list[str] | None = None,
) -> list[Substitution]:
    """Generate substitution options for each flavor need."""
    needs: set[str] = set()
    for key, _desc in imbalances:
        if "acid" in key:
            needs.add("acid")
        if "salt" in key or "depth" in key:
            needs.add("salt")
            needs.add("umami")
        if "fat" in key:
            needs.add("fat")
        if "flat" in key:
            needs.add("acid")
            needs.add("heat")
            needs.add("umami")

    substitutions: list[Substitution] = []
    for need in sorted(needs):
        options = SUBSTITUTION_TABLE.get(need, [])
        options = _filter_constraints(options, constraints)
        substitutions.append(Substitution(need=need, options=options))

    return substitutions


def generate_pantry_suggestions(
    imbalances: list[tuple[str, str]],
    pantry_items: list[str] | None = None,
    constraints: list[str] | None = None,
) -> list[str]:
    """Match fixes against pantry items."""
    if not pantry_items:
        return []

    pantry_lower = [item.lower() for item in pantry_items]
    suggestions: list[str] = []

    needs: set[str] = set()
    for key, _desc in imbalances:
        if "acid" in key:
            needs.add("acid")
        if "salt" in key or "depth" in key:
            needs.add("salt")
            needs.add("umami")
        if "fat" in key:
            needs.add("fat")
        if "flat" in key:
            needs.add("acid")
            needs.add("heat")
            needs.add("umami")

    for need in sorted(needs):
        options = SUBSTITUTION_TABLE.get(need, [])
        options = _filter_constraints(options, constraints)
        matched = [opt for opt in options if _in_pantry(opt, pantry_lower)]
        if matched:
            suggestions.append(f"Use {matched[0]} (from pantry) for {need}")
        elif options:
            suggestions.append(f"Consider getting {options[0]} for {need}")

    return suggestions


def _in_pantry(option: str, pantry_lower: list[str]) -> bool:
    """Check if an option matches any pantry item (partial match)."""
    option_lower = option.lower()
    for item in pantry_lower:
        if option_lower in item or item in option_lower:
            return True
    return False


def _filter_constraints(options: list[str], constraints: list[str] | None) -> list[str]:
    """Remove options that violate constraints."""
    if not constraints:
        return options

    constraint_set = set(c.lower().replace(" ", "_") for c in constraints)
    filtered: list[str] = []
    for opt in options:
        tags = CONSTRAINT_TAGS.get(opt, [])
        blocked = False
        for tag in tags:
            # Map constraint names to tags
            if "no_dairy" in constraint_set and tag == "dairy":
                blocked = True
            if "no_meat" in constraint_set and tag == "meat":
                blocked = True
            if "vegan" in constraint_set and tag in ("dairy", "meat", "fish", "not_vegan"):
                blocked = True
            if "vegetarian" in constraint_set and tag in ("meat", "fish"):
                blocked = True
        if not blocked:
            filtered.append(opt)

    return filtered
