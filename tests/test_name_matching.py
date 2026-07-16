from src.fridgechef.name_matching import inventory_name_key


def test_spanish_vowel_plural_matches_singular():
    assert inventory_name_key("patatas") == inventory_name_key("patata")
    assert inventory_name_key("naranjas") == inventory_name_key("naranja")
    assert inventory_name_key("tomates") == inventory_name_key("tomate")


def test_spanish_consonant_plural_matches_singular():
    assert inventory_name_key("limones") == inventory_name_key("limón")
    assert inventory_name_key("nueces") == inventory_name_key("nuez")
    assert inventory_name_key("pasteles") == inventory_name_key("pastel")


def test_common_english_plural_matches_singular():
    assert inventory_name_key("potatoes") == inventory_name_key("potato")
    assert inventory_name_key("oranges") == inventory_name_key("orange")
    assert inventory_name_key("berries") == inventory_name_key("berry")
