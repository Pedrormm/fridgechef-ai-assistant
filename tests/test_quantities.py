from src.fridgechef.quantities import display_quantity_label, merge_quantity_parts, parse_quantity_label


def test_missing_quantity_defaults_to_one_unit():
    assert parse_quantity_label("Cantidad no indicada") == {"unit": 1.0}
    assert display_quantity_label({}, "Cantidad no indicada", "es") == "1 unidad"


def test_common_count_quantities_are_parsed():
    assert parse_quantity_label("2 patatas") == {"unit": 2.0}
    assert parse_quantity_label("3 unidades") == {"unit": 3.0}
    assert parse_quantity_label("un par") == {"unit": 2.0}


def test_mass_and_volume_units_share_canonical_families():
    assert parse_quantity_label("1 kg") == {"g": 1000.0}
    assert parse_quantity_label("500 gramos") == {"g": 500.0}
    assert merge_quantity_parts({"g": 1000}, {"g": 500}, mode="sum") == {"g": 1500.0}
    assert display_quantity_label({"g": 1500}, "", "es") == "1,5 kg"


def test_english_quantity_display_is_deterministic():
    assert display_quantity_label({"unit": 3}, "", "en") == "3 units"
