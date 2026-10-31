"""用途：本地生成可复现的家居纹理，并为 Gazebo 家具设置 PBR 材质。"""

from pathlib import Path
import math
import random
import struct
import zlib
import xml.etree.ElementTree as ET


def _png(path, base, pattern):
    """Write a small RGB texture with standard library only."""
    rng = random.Random(31)
    rows = bytearray()
    size = 512 if pattern == 'floor' else 256
    for y in range(size):
        rows.append(0)
        for x in range(size):
            noise = rng.uniform(-2, 2)
            if pattern == 'floor':
                row = y // 26
                shifted = (x + (51 if row % 2 else 0)) % 102
                bend = 2 * math.sin(x*.045)
                detail = 3*math.sin((y+bend)*1.1) + ((row*7 + (x//102)*3)%9)-4
                if y % 26 == 0 or shifted == 0:
                    detail = -17  # Fine brown joints; no white gaps or geometry holes.
            elif pattern == 'wood':
                bend = 5 * math.sin(y*.035) + 2*math.sin(y*.11)
                detail = 5*math.sin((x+bend)*.40) + 2*math.sin((x+bend)*1.3)
            elif pattern == 'fabric':
                detail = (3 if x % 3 == 0 else -1) + (3 if y % 3 == 0 else -1)
            elif pattern == 'stone':
                detail = 2*math.sin(x*.09+y*.07) + 2*math.sin(x*.3-y*.11)
            else:
                detail = 0
            rows.extend(max(0, min(255, round(c+noise+detail))) for c in base)
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', size,size,8,2,0,0,0))
                     + chunk(b'IDAT', zlib.compress(bytes(rows))) + chunk(b'IEND', b''))


def apply_materials(world, directory):
    """Apply portable absolute texture paths; files live as long as the world."""
    directory = Path(directory) / 'materials'
    directory.mkdir(parents=True, exist_ok=True)
    specs = {'floor': ((163,132,94), 'floor'), 'walnut': ((113,82,56), 'wood'),
             'linen': ((109,139,143), 'fabric'), 'rug': ((133,143,119), 'fabric'),
             'plaster': ((222,215,201), 'plaster'), 'stone': ((170,178,174), 'stone')}
    for key, (color, pattern) in specs.items():
        _png(directory/f'{key}.png', color, pattern)
    walls = {'north','south','west','east','room_divider','entry_divider'}
    for model in world.findall('model'):
        name = model.get('name', '')
        key = None
        if name == 'floor':
            key = 'floor'
        elif name.startswith(('sofa_', 'duvet', 'bed_throw', 'lamp_shade')):
            key = 'linen'
        elif name in ('living_rug', 'welcome_mat'):
            key = 'rug'
        elif name in walls or '_hall_' in name:
            key = 'plaster'
        elif name in ('worktop', 'kitchen_tiles'):
            key = 'stone'
        elif name.startswith(('table_leg', 'wardrobe', 'bed_base', 'headboard', 'bedside', 'tv_cabinet', 'shoe_cabinet')) or name == 'coffee_table':
            if 'handle' not in name:
                key = 'walnut'
        for visual in model.findall('link/visual'):
            material = visual.find('material')
            if material is None:
                continue
            metal = any(part in name for part in ('tap_', 'handle', 'latch', 'sink', 'burner'))
            workflow = ET.SubElement(ET.SubElement(material, 'pbr'), 'metal')
            ET.SubElement(workflow, 'metalness').text = '.65' if metal else '0'
            ET.SubElement(workflow, 'roughness').text = '.32' if metal else '.85'
            if key:
                material.find('ambient').text = '1 1 1 1'
                material.find('diffuse').text = '1 1 1 1'
                ET.SubElement(workflow, 'albedo_map').text = str((directory/f'{key}.png').resolve())
