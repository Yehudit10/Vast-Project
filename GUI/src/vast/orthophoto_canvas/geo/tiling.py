from typing import Tuple

TILE_SIZE = 512  # pixels

def eff_tile_scene(z: int, z_base: int) -> float:
    """
    Size (in scene units) of a single tile at zoom z, when scene is anchored to z_base.
    """
    return TILE_SIZE / float(1 << (z - z_base))

def anchor_indices_to_scene(z: int, z_base: int, x_min_base: int, y_min_base: int,
                            x_idx: int, y_idx: int) -> Tuple[int, int]:
    """
    Convert (z/x/y) indices to scene grid indices (tx, ty), anchored to z_base.
    """
    scale = 1 << (z - z_base)
    x0 = x_min_base * scale
    y0 = y_min_base * scale
    tx = x_idx - x0
    ty = y_idx - y0
    return tx, ty

def scene_pos_from_indices(tx: int, ty: int, eff_tile: float) -> Tuple[int, int]:
    """
    Convert tile grid indices (tx, ty) to scene pixel coordinates (sx, sy).
    """
    sx = int(tx * eff_tile)
    sy = int(ty * eff_tile)
    return sx, sy
