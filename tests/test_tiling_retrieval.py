"""224 px windows at native GSD, instead of squashing a 10 km scene to 224 px."""
from PIL import Image

from app.semantic_clusters import TILE_PX, tile_images


def test_a_1024_scene_becomes_sixteen_windows():
    assert len(tile_images(Image.new("RGB", (1024, 1024)))) == 16


def test_windows_are_exactly_the_model_input_size():
    for crop in tile_images(Image.new("RGB", (1024, 1024))):
        assert crop.size == (TILE_PX, TILE_PX)


def test_a_small_image_falls_back_to_itself():
    tiny = Image.new("RGB", (200, 150))
    assert tile_images(tiny) == [tiny]


def test_partial_edge_windows_are_dropped_not_padded():
    # 500 px holds two whole 224 windows per axis; the 52 px remainder is not
    # padded, because padding would feed the model invented pixels.
    assert len(tile_images(Image.new("RGB", (500, 500)))) == 4


def test_windows_cover_distinct_ground():
    image = Image.new("RGB", (448, 448))
    image.paste(Image.new("RGB", (224, 224), (255, 0, 0)), (0, 0))
    colours = {crop.getpixel((0, 0)) for crop in tile_images(image)}
    assert (255, 0, 0) in colours and (0, 0, 0) in colours


def test_window_positions_are_row_major():
    from app.semantic_clusters import tile_windows

    positions = [(r, c) for _, r, c in tile_windows(Image.new("RGB", (1024, 1024)))]
    assert positions[0] == (0, 0)
    assert positions[1] == (0, 1)
    assert positions[-1] == (3, 3)


def test_near_water_includes_touching_windows_only():
    from app.semantic_clusters import near_water_mask

    # Water sits at (0,0). (0,1) and (1,1) touch it; (0,3) is two windows away.
    cells = [(1, 0, 0, 0.9), (1, 0, 1, 0.0), (1, 1, 1, 0.0), (1, 0, 3, 0.0)]
    assert near_water_mask(cells) == [True, True, True, False]


def test_near_water_does_not_leak_across_scenes():
    from app.semantic_clusters import near_water_mask

    # Same grid position, different scene: proximity must not cross scenes.
    cells = [(1, 0, 0, 0.9), (2, 0, 1, 0.0)]
    assert near_water_mask(cells) == [True, False]


def test_a_trace_of_water_is_not_enough():
    from app.semantic_clusters import near_water_mask

    # Wet field edges show a few SCL water pixels; that is not a water body.
    assert near_water_mask([(1, 0, 0, 0.01), (1, 0, 1, 0.0)]) == [False, False]
