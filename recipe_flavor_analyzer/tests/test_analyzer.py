import sys
import os

# Allow running tests from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from recipe_flavor_analyzer.parser import parse_recipe, match_ingredient_to_flavor
from recipe_flavor_analyzer.models import Ingredient, FlavorProfile
from recipe_flavor_analyzer.scorer import compute_scores, detect_imbalances, determine_decision
from recipe_flavor_analyzer.suggestions import (
    generate_fixes,
    generate_substitutions,
    generate_pantry_suggestions,
    _filter_constraints,
)
from recipe_flavor_analyzer.analyzer import analyze_recipe


# ---- Parser Tests ----

class TestParser:
    def test_simple_list(self):
        text = """
        - 2 cups butter
        - 1 tsp salt
        - 3 tbsp lemon juice
        """
        ingredients = parse_recipe(text)
        names = [i.name for i in ingredients]
        assert "butter" in names
        assert "salt" in names
        assert "lemon juice" in names

    def test_numbered_list(self):
        text = """
        1. butter
        2. garlic
        3. soy sauce
        """
        ingredients = parse_recipe(text)
        names = [i.name for i in ingredients]
        assert "butter" in names
        assert "garlic" in names
        assert "soy sauce" in names

    def test_comma_separated(self):
        text = "butter, salt, lemon, garlic"
        ingredients = parse_recipe(text)
        names = [i.name for i in ingredients]
        assert len(names) == 4
        assert "butter" in names

    def test_skips_instructions(self):
        text = """
        - 2 cups butter
        - 1 tsp salt
        Preheat oven to 350F
        Mix ingredients together
        Bake for 30 minutes
        """
        ingredients = parse_recipe(text)
        names = [i.name for i in ingredients]
        assert "butter" in names
        assert "salt" in names
        assert len(ingredients) == 2

    def test_quantity_extraction(self):
        text = "2 cups butter"
        ingredients = parse_recipe(text)
        assert len(ingredients) == 1
        assert ingredients[0].name == "butter"
        assert ingredients[0].quantity is not None

    def test_empty_input(self):
        assert parse_recipe("") == []
        assert parse_recipe("   ") == []

    def test_deduplication(self):
        text = """
        - butter
        - butter
        """
        ingredients = parse_recipe(text)
        assert len(ingredients) == 1


class TestFlavorMapping:
    def test_exact_match(self):
        ing = Ingredient(name="butter")
        result = match_ingredient_to_flavor(ing)
        assert result is not None
        assert result["fat"] == 3

    def test_pluralized(self):
        ing = Ingredient(name="tomatoes")
        result = match_ingredient_to_flavor(ing)
        assert result is not None
        assert "acid" in result

    def test_unknown_ingredient(self):
        ing = Ingredient(name="xyznoexist")
        result = match_ingredient_to_flavor(ing)
        assert result is None

    def test_multi_flavor(self):
        ing = Ingredient(name="soy sauce")
        result = match_ingredient_to_flavor(ing)
        assert result is not None
        assert "salt" in result
        assert "umami" in result


# ---- Scorer Tests ----

class TestScorer:
    def test_basic_scoring(self):
        ingredients = [Ingredient(name="butter"), Ingredient(name="butter")]
        # Only one gets added due to dedup in parser, but we test scorer directly
        profile = compute_scores(ingredients)
        assert profile.fat > 0

    def test_normalization(self):
        ingredients = [Ingredient(name="butter")]
        profile = compute_scores(ingredients)
        scores = profile.to_scores()
        for v in scores.values():
            assert 0 <= v <= 10


class TestImbalanceDetection:
    def test_high_fat_low_acid(self):
        scores = {"salt": 5, "fat": 8, "acid": 2, "sweet": 3, "umami": 5, "heat": 1}
        imbalances = detect_imbalances(scores)
        keys = [k for k, _ in imbalances]
        assert "needs_acid" in keys

    def test_low_salt(self):
        scores = {"salt": 2, "fat": 5, "acid": 5, "sweet": 5, "umami": 5, "heat": 3}
        imbalances = detect_imbalances(scores)
        keys = [k for k, _ in imbalances]
        assert "needs_salt" in keys

    def test_balanced(self):
        scores = {"salt": 5, "fat": 5, "acid": 5, "sweet": 3, "umami": 5, "heat": 3}
        imbalances = detect_imbalances(scores)
        # Should not trigger flat because range > 2
        assert len(imbalances) == 0

    def test_flat_detection(self):
        scores = {"salt": 5, "fat": 5, "acid": 5, "sweet": 5, "umami": 5, "heat": 5}
        imbalances = detect_imbalances(scores)
        keys = [k for k, _ in imbalances]
        assert "flat" in keys


class TestDecision:
    def test_keep(self):
        scores = {"salt": 5, "fat": 5, "acid": 5, "sweet": 3, "umami": 5, "heat": 3}
        assert determine_decision(scores, []) == "KEEP"

    def test_tweak(self):
        scores = {"salt": 5, "fat": 8, "acid": 2, "sweet": 3, "umami": 5, "heat": 1}
        imbalances = [("needs_acid", "test")]
        assert determine_decision(scores, imbalances) == "TWEAK"

    def test_rescue(self):
        scores = {"salt": 1, "fat": 9, "acid": 1, "sweet": 3, "umami": 5, "heat": 1}
        imbalances = [("needs_acid", "test"), ("needs_salt", "test")]
        assert determine_decision(scores, imbalances) == "RESCUE"


# ---- Suggestions Tests ----

class TestSuggestions:
    def test_generate_fixes(self):
        imbalances = [("needs_acid", "test")]
        fixes = generate_fixes(imbalances)
        assert len(fixes) > 0
        assert any("lemon" in f.lower() for f in fixes)

    def test_generate_substitutions(self):
        imbalances = [("needs_acid", "test")]
        subs = generate_substitutions(imbalances)
        assert len(subs) > 0
        assert subs[0].need == "acid"
        assert len(subs[0].options) > 0

    def test_pantry_matching(self):
        imbalances = [("needs_acid", "test")]
        suggestions = generate_pantry_suggestions(
            imbalances, pantry_items=["lemon", "olive oil"]
        )
        assert len(suggestions) > 0
        assert any("lemon" in s.lower() for s in suggestions)

    def test_no_pantry(self):
        imbalances = [("needs_acid", "test")]
        suggestions = generate_pantry_suggestions(imbalances, pantry_items=None)
        assert suggestions == []

    def test_constraint_filtering(self):
        options = ["butter", "olive oil", "cream"]
        filtered = _filter_constraints(options, ["no_dairy"])
        assert "butter" not in filtered
        assert "cream" not in filtered
        assert "olive oil" in filtered

    def test_vegan_constraint(self):
        options = ["butter", "olive oil", "honey"]
        filtered = _filter_constraints(options, ["vegan"])
        assert "butter" not in filtered
        assert "honey" not in filtered
        assert "olive oil" in filtered


# ---- End-to-End Tests ----

class TestAnalyzeRecipe:
    def test_full_pipeline(self):
        recipe = """
        - 3 tbsp butter
        - 2 cups heavy cream
        - 1 lb pasta
        - 1 cup parmesan cheese
        - salt
        - black pepper
        """
        result = analyze_recipe(recipe)

        assert "flavor_scores" in result
        assert "diagnosis" in result
        assert "decision" in result
        assert "fixes" in result
        assert "pantry_suggestions" in result
        assert "substitutions" in result

        # This recipe is fat-heavy
        assert result["flavor_scores"]["fat"] > 5
        assert result["decision"] in ("TWEAK", "RESCUE")

    def test_with_pantry(self):
        recipe = """
        - 3 tbsp butter
        - 2 cups heavy cream
        - 1 lb pasta
        """
        result = analyze_recipe(recipe, pantry_items=["lemon", "vinegar"])

        if result["pantry_suggestions"]:
            assert any("lemon" in s.lower() or "vinegar" in s.lower()
                       for s in result["pantry_suggestions"])

    def test_with_constraints(self):
        recipe = """
        - 3 tbsp butter
        - 2 cups heavy cream
        - pasta
        """
        result = analyze_recipe(recipe, constraints=["no_dairy"])

        # Substitutions should not include dairy
        for sub in result["substitutions"]:
            assert "butter" not in sub["options"]
            assert "cream" not in sub["options"]

    def test_balanced_recipe(self):
        recipe = """
        - chicken
        - soy sauce
        - lemon juice
        - olive oil
        - honey
        - garlic
        - ginger
        - salt
        """
        result = analyze_recipe(recipe)
        # Well-balanced recipe should be KEEP or TWEAK
        assert result["decision"] in ("KEEP", "TWEAK")

    def test_output_format(self):
        recipe = "butter, cream, pasta"
        result = analyze_recipe(recipe)

        # Verify all expected keys
        assert set(result.keys()) == {
            "flavor_scores", "diagnosis", "decision",
            "fixes", "pantry_suggestions", "substitutions",
        }

        # Verify flavor_scores structure
        assert set(result["flavor_scores"].keys()) == {
            "salt", "fat", "acid", "sweet", "umami", "heat",
        }

        # Verify types
        assert isinstance(result["diagnosis"], str)
        assert result["decision"] in ("KEEP", "TWEAK", "RESCUE")
        assert isinstance(result["fixes"], list)
        assert isinstance(result["pantry_suggestions"], list)
        assert isinstance(result["substitutions"], list)

        for sub in result["substitutions"]:
            assert "need" in sub
            assert "options" in sub

    def test_empty_recipe(self):
        result = analyze_recipe("")
        assert result["decision"] == "KEEP"
        assert result["diagnosis"] == "Recipe is well-balanced"
