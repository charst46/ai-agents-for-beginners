import re

from .models import Ingredient
from .flavor_map import FLAVOR_MAP

# Common units to strip from ingredient text
_UNITS = (
    r"cups?|tbsps?|tablespoons?|tsps?|teaspoons?|oz|ounces?|lbs?|pounds?|"
    r"grams?|g|kg|ml|liters?|l|quarts?|pints?|gallons?|"
    r"cloves?|slices?|pieces?|pinch(?:es)?|dash(?:es)?|bunche?s?|"
    r"cans?|sticks?|heads?|stalks?|sprigs?|handfuls?"
)

# Pattern: optional quantity (number/fraction), optional unit, then ingredient name
_INGREDIENT_PATTERN = re.compile(
    rf"^\s*(?P<qty>[\d½¼¾⅓⅔⅛/.\s-]+)?\s*(?:(?:{_UNITS})\s+(?:of\s+)?)?(?P<name>.+)$",
    re.IGNORECASE,
)

# Lines that are likely not ingredients
_SKIP_PATTERNS = re.compile(
    r"^\s*(?:instructions?|directions?|steps?|method|notes?|serves?|prep|cook|"
    r"preheat|bake|mix|stir|combine|set aside|let|place|heat|bring|"
    r"total time|yield|servings?|calories)\b",
    re.IGNORECASE,
)


def parse_recipe(recipe_text: str) -> list[Ingredient]:
    """Extract ingredients from recipe text.

    Handles common formats:
    - Bullet/numbered lists: "- 2 cups butter", "1. 1 tsp salt"
    - Plain lines: "2 cups flour"
    - Comma-separated in a line: "butter, salt, lemon"
    """
    ingredients: list[Ingredient] = []
    seen_names: set[str] = set()

    for line in recipe_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Strip bullet points, numbering, asterisks
        line = re.sub(r"^[\-\*•]\s*", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        line = line.strip()

        if not line:
            continue

        # Skip instruction-like lines
        if _SKIP_PATTERNS.match(line):
            continue

        # Handle comma-separated ingredients in a single line
        if "," in line and not any(c.isdigit() for c in line[:3]):
            parts = [p.strip() for p in line.split(",")]
            if all(len(p.split()) <= 4 for p in parts):
                for part in parts:
                    if part:
                        _add_ingredient(part, ingredients, seen_names)
                continue

        _add_ingredient(line, ingredients, seen_names)

    return ingredients


def _add_ingredient(text: str, ingredients: list[Ingredient], seen: set[str]) -> None:
    """Parse a single ingredient string and add it to the list."""
    text = text.strip().rstrip(".")

    match = _INGREDIENT_PATTERN.match(text)
    if not match:
        return

    qty = match.group("qty")
    name = match.group("name")

    if not name:
        return

    # Clean up the name
    name = _normalize_name(name)

    if not name or name in seen:
        return

    seen.add(name)
    ingredients.append(Ingredient(
        name=name,
        quantity=qty.strip() if qty and qty.strip() else None,
    ))


def _normalize_name(name: str) -> str:
    """Normalize ingredient name for lookup."""
    # Remove parenthetical notes like "(optional)", "(to taste)"
    name = re.sub(r"\(.*?\)", "", name)
    # Remove trailing descriptors like "freshly squeezed", "finely chopped"
    name = re.sub(
        r",?\s*(?:freshly |finely |roughly |coarsely )?(?:squeezed|chopped|diced|"
        r"minced|sliced|grated|shredded|crushed|ground|melted|softened|"
        r"room temperature|to taste|as needed|for garnish|divided|"
        r"peeled|deseeded|trimmed|washed|dried|fresh|large|medium|small|"
        r"extra.virgin)\s*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = name.strip().lower()
    # Remove leading "of "
    name = re.sub(r"^of\s+", "", name)
    return name


def match_ingredient_to_flavor(ingredient: Ingredient) -> dict[str, float] | None:
    """Look up an ingredient in the flavor map.

    Tries exact match first, then partial matching.
    """
    name = ingredient.name

    # Exact match
    if name in FLAVOR_MAP:
        return FLAVOR_MAP[name]

    # Try without trailing 's' (simple depluralize)
    if name.endswith("s") and name[:-1] in FLAVOR_MAP:
        return FLAVOR_MAP[name[:-1]]

    # Try partial match: check if any key is contained in the name or vice versa
    for key in FLAVOR_MAP:
        if key in name or name in key:
            return FLAVOR_MAP[key]

    return None
