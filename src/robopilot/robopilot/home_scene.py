"""用途：生成无外部模型依赖的家居世界及同源几何导航地图；包含家具细节与低开销材质层次。"""

from pathlib import Path
import xml.etree.ElementTree as ET

from robopilot.home_materials import apply_materials


def build_home(world, directory, toolbox_state='present', backpack_state='hanging',
               door_state='closed', fruit_state='present'):
    """Replace sandbox models with a furnished apartment; return matching map YAML."""
    if toolbox_state not in ('present','absent','distractor','occluded'):
        raise ValueError('Invalid toolbox state')
    if backpack_state not in ('hanging','floor','absent','occluded') or door_state not in ('closed','open','ajar') or fruit_state not in ('present','empty','absent'):
        raise ValueError('Invalid household inspection state')
    for model in list(world.findall('model')):
        world.remove(model)
    obstacles = []

    def box(name, x, y, z, sx, sy, sz, color, solid=True):
        model = ET.SubElement(world, 'model', name=name)
        ET.SubElement(model, 'static').text = 'true'
        ET.SubElement(model, 'pose').text = f'{x} {y} {z} 0 0 0'
        link = ET.SubElement(model, 'link', name='body')
        for kind in (('collision', 'visual') if solid else ('visual',)):
            element = ET.SubElement(link, kind, name=kind)
            geometry = ET.SubElement(element, 'geometry')
            ET.SubElement(ET.SubElement(geometry, 'box'), 'size').text = f'{sx} {sy} {sz}'
            if kind == 'visual':
                material = ET.SubElement(element, 'material')
                ET.SubElement(material, 'ambient').text = color
                ET.SubElement(material, 'diffuse').text = color
        if solid and z + sz / 2 > 0.08:
            obstacles.append((x, y, sx, sy))

    def round_detail(name, x, y, z, radius, length, color, sphere=False):
        # Small decorative parts have no collision; furniture retains its coarse collider.
        box(name, x, y, z, radius*2, radius*2, length, color, False)
        geometry = world.findall('model')[-1].find('link/visual/geometry')
        geometry.clear()
        shape = ET.SubElement(geometry, 'sphere' if sphere else 'cylinder')
        ET.SubElement(shape, 'radius').text = str(radius)
        if not sphere:
            ET.SubElement(shape, 'length').text = str(length)

    scene = world.find('scene')
    if scene is None:
        scene = ET.SubElement(world, 'scene')
    for tag, value in [('ambient', '0.65 0.65 0.65 1'),
                       ('background', '0.76 0.81 0.85 1')]:
        node = scene.find(tag)
        if node is None:
            node = ET.SubElement(scene, tag)
        node.text = value

    cream = '0.88 0.85 0.77 1'
    wood = '0.52 0.32 0.18 1'
    blue = '0.20 0.37 0.48 1'
    white = '0.88 0.90 0.90 1'
    box('floor', 0, 0, -0.06, 10.4, 8.4, 0.12, '0.65 0.53 0.39 1')
    box('kitchen_tiles', -2.5, -2.7, 0.005, 4.8, 2.4, 0.01, '0.68 0.73 0.73 1', False)
    box('living_rug', -2.6, 2, 0.012, 3.4, 2.2, 0.015, '0.38 0.48 0.45 1', False)
    # Open roof; 1.5 m walls keep room structure visible in the overview.
    for name, x, y, sx, sy in [
        ('north', 0, 4, 10.2, .16), ('south', -2.225, -4, 5.55, .16),
        ('south_right', 3.325, -4, 3.35, .16),
        ('west', -5, 0, .16, 8), ('east', 5, 0, .16, 8),
        ('room_divider', 0, 2.75, .16, 2.5),
        ('living_hall_left', -4.1, .5, 1.8, .16),
        ('living_hall_right', -1.1, .5, 2.2, .16),
        ('bedroom_hall_left', .8, .5, 1.6, .16),
        ('bedroom_hall_right', 4, .5, 2, .16),
        ('kitchen_hall_left', -4.1, -1.5, 1.8, .16),
        ('kitchen_hall_right', -.91, -1.5, 2.58, .16),
        ('entry_divider', .3, -2.75, .16, 2.5),
    ]:
        box(name, x, y, .75, sx, sy, 1.5, cream)
    # Living room: upholstered sofa, low table, television and plant.
    box('sofa_seat', -3.7, 2.9, .32, 2.2, .85, .48, blue)
    box('sofa_back', -3.7, 3.3, .65, 2.2, .18, .65, blue)
    for x in [-4.75, -2.65]:
        box('sofa_arm_' + str(x), x, 2.9, .5, .16, .85, .6, blue)
    box('coffee_table', -3.6, 1.65, .23, 1.35, .6, .46, wood)
    box('tv_cabinet', -1, 3.55, .3, 1.4, .5, .6, wood)
    box('television', -1, 3.6, 1, 1.25, .09, .7, '0.06 0.08 0.10 1')
    box('plant_collision', -4.5, .95, .16, .28, .28, .32, wood)
    round_detail('plant_pot_round', -4.5, .95, .19, .19, .38, wood)
    for i, (dx, dy, dz) in enumerate([(-.13, 0, .53), (.13, .05, .60), (0, -.10, .72)]):
        round_detail(f'plant_leaves_{i}', -4.5+dx, .95+dy, dz, .18, .3, '0.19 0.36 0.16 1', True)
    # Bedroom: bed, pillow, wardrobe, bedside cabinet.
    box('bed_base', 3.65, 2.65, .22, 1.8, 2.3, .44, wood)
    box('mattress', 3.65, 2.65, .5, 1.8, 2.3, .18, white)
    box('duvet', 3.65, 2.2, .61, 1.75, 1.35, .08, '0.35 0.50 0.65 1')
    box('pillow', 3.65, 3.4, .64, 1.15, .45, .14, white)
    box('bedside', 2.2, 3.5, .3, .55, .65, .6, wood)
    box('wardrobe', .65, 3, .85, .8, 1.6, 1.7, wood)
    # Kitchen: counters with doors, stove and refrigerator.
    box('kitchen_counter', -3, -3.5, .45, 3.5, .65, .9, white)
    box('worktop', -3, -3.5, .93, 3.6, .7, .06, '0.22 0.25 0.26 1')
    for x in [-4.2, -3.4, -2.6, -1.8]:
        box('cabinet_handle_' + str(x), x, -3.16, .65, .28, .025, .035, wood, False)
    box('stove', -3.8, -3.5, .97, .65, .5, .025, '0.08 0.09 0.10 1', False)
    box('sink', -2.4, -3.5, .97, .6, .45, .025, '0.48 0.57 0.60 1', False)
    box('refrigerator', -4.45, -2.3, .85, .75, .8, 1.7, white)
    # Entry: shoe cabinet, low charging dock and decorative welcome mat.
    box('shoe_cabinet', 4.5, -2.7, .4, .6, 1.5, .8, wood)
    box('charging_dock', 2.7, -3.65, .12, .65, .3, .24, '0.12 0.15 0.18 1')
    box('welcome_mat', 2.6, -2.8, .012, 1.2, .7, .015, blue, False)
    # Recognisable prop only; no semantic detector is enabled by this scene.
    red = '0.72 0.06 0.04 1'
    box('toolbox_body', -1.2, 1.6, .16, .5, .3, .32, red)
    box('toolbox_lid', -1.2, 1.6, .34, .52, .32, .06, '0.20 0.22 0.24 1')
    for x in [-1.34, -1.06]:
        box('handle_post_' + str(x), x, 1.6, .41, .035, .06, .1, '0.12 0.13 0.14 1')
    box('toolbox_handle', -1.2, 1.6, .47, .31, .06, .035, '0.12 0.13 0.14 1')
    # Continuous finish above Gazebo's z=0 grid: joints belong in the texture,
    # not in physical gaps between many coplanar board meshes.
    floor_visual = world.find("model[@name='floor']/link/visual")
    ET.SubElement(floor_visual, 'pose').text = '0 0 0.004 0 0 0'
    # Restore overlays above the boards; decorations do not modify occupancy.
    for i in range(9):
        x = -4.9+i*.6
        if x <= -.1:
            box(f'tile_grout_x_{i}', x, -2.7, .012, .008, 2.4, .002, white, False)
    for i in range(5):
        box(f'tile_grout_y_{i}', -2.5, -3.9+i*.6, .012, 4.8, .008, .002, white, False)
    for x in [-4.22, -.98]:
        box(f'rug_border_{x}', x, 2, .022, .035, 2.1, .003, '0.76 0.72 0.57 1', False)
    # Split upholstery and add piping/pillows over the collision body.
    for i, x in enumerate([-4.35, -3.7, -3.05]):
        box(f'sofa_cushion_{i}', x, 2.84, .58, .62, .68, .10, '0.32 0.48 0.54 1', False)
        box(f'sofa_back_cushion_{i}', x, 3.16, .76, .62, .12, .42, '0.29 0.43 0.49 1', False)
    box('throw_pillow_cream', -4.4, 2.98, .78, .36, .20, .34, '0.83 0.73 0.54 1', False)
    box('throw_pillow_sage', -3, 2.98, .78, .35, .20, .34, '0.49 0.58 0.42 1', False)
    # Coffee table reads as a tabletop with legs rather than a solid block.
    table = world.find("model[@name='coffee_table']/link/visual/geometry/box/size")
    table.text = '1.35 0.6 0.07'
    world.find("model[@name='coffee_table']/link/visual").append(ET.fromstring('<pose>0 0 0.195 0 0 0</pose>'))
    for x in [-4.14, -3.06]:
        for y in [1.43, 1.87]:
            box(f'table_leg_{x}_{y}', x, y, .21, .055, .055, .42, wood, False)
    box('book_cover', -3.85, 1.65, .49, .28, .21, .025, '0.29 0.41 0.35 1', False)
    box('book_pages', -3.85, 1.65, .507, .26, .195, .015, white, False)
    round_detail('mug', -3.3, 1.65, .525, .055, .12, white)
    round_detail('mug_coffee', -3.3, 1.65, .587, .043, .002, '0.13 0.08 0.04 1')
    box('tv_screen', -1, 3.547, 1.02, 1.12, .008, .57, '0.15 0.23 0.29 1', False)
    # Wall-mounted window panels; no changes to wall collision geometry.
    for room, x in [('living', -3.1), ('bedroom', 3.3)]:
        box(f'{room}_window_frame', x, 3.90, 1.02, 1.5, .035, .78, white, False)
        box(f'{room}_window_glass', x, 3.875, 1.02, 1.34, .018, .63, '0.51 0.68 0.76 1', False)
        box(f'{room}_window_mullion', x, 3.855, 1.02, .045, .02, .68, white, False)
        box(f'{room}_window_sill', x, 3.80, .61, 1.6, .18, .045, white, False)
    # Doors/drawers, bed headboard, folded throw, bedside lamp.
    box('headboard', 3.65, 3.84, .76, 1.85, .08, .85, wood, False)
    box('bed_throw', 3.65, 1.82, .66, 1.74, .4, .035, '0.73 0.66 0.52 1', False)
    for i in range(2):
        box(f'wardrobe_door_{i}', 1.06, 2.61+i*.78, .87, .025, .75, 1.6, '0.63 0.46 0.29 1', False)
        box(f'wardrobe_handle_{i}', 1.09, 2.9+i*.18, .85, .025, .025, .23, white, False)
    round_detail('lamp_base', 2.2, 3.5, .63, .13, .04, '0.3 0.28 0.24 1')
    round_detail('lamp_stem', 2.2, 3.5, .79, .02, .29, wood)
    round_detail('lamp_shade', 2.2, 3.5, 1, .18, .23, '0.88 0.79 0.60 1')
    for i, x in enumerate([-4.2, -3.4, -2.6, -1.8]):
        box(f'kitchen_door_{i}', x, -3.166, .43, .76, .018, .77, '0.79 0.81 0.78 1', False)
    for i, (x, y) in enumerate([(-4, -3.65), (-3.65, -3.65), (-4, -3.35), (-3.65, -3.35)]):
        round_detail(f'burner_{i}', x, y, .99, .095, .015, '0.26 0.28 0.29 1')
    box('sink_basin', -2.4, -3.5, .986, .46, .31, .008, '0.20 0.28 0.30 1', False)
    round_detail('tap_stem', -2.4, -3.72, 1.08, .025, .23, white)
    box('tap_spout', -2.4, -3.63, 1.19, .045, .2, .035, white, False)
    box('fridge_door_seam', -4.45, -1.894, 1.2, .69, .012, .015, '0.4 0.43 0.45 1', False)
    box('fridge_handle', -4.19, -1.86, .88, .035, .05, .42, '0.4 0.43 0.45 1', False)
    for x in [-1.36, -1.04]:
        box(f'toolbox_latch_{x}', x, 1.438, .29, .045, .02, .09, white, False)
    # Skirting visually grounds walls; these remain within existing wall envelopes.
    for name in ['north', 'south', 'west', 'east']:
        model = world.find(f"model[@name='{name}']")
        x, y = map(float, model.findtext('pose').split()[:2])
        sx, sy, _ = map(float, model.findtext('link/visual/geometry/box/size').split())
        box(f'skirting_{name}', x, y, .055, sx+.015, sy+.015, .11, white, False)
    # Home accents stay within furniture/wall envelopes, leaving routes clear.
    for i in range(3):
        box(f'tv_drawer_{i}', -1.46+i*.46, 3.292, .33, .43, .018, .39,
            '0.46 0.33 0.22 1', False)
        box(f'tv_drawer_pull_{i}', -1.46+i*.46, 3.274, .37, .15, .025, .025,
            '0.65 0.61 0.48 1', False)
    # Framed artwork on corridor-facing wall.
    box('art_frame', -.8, .397, .99, .68, .035, .62, wood, False)
    box('art_canvas', -.8, .374, .99, .59, .008, .53, '0.85 0.80 0.68 1', False)
    box('art_landscape', -.8, .368, .87, .57, .004, .20, '0.37 0.48 0.41 1', False)
    round_detail('fruit_bowl', -1.0, -2.8, .57, .12, .06, '0.72 0.61 0.44 1')
    for i, (dx, dy) in enumerate([(-.045, 0), (.045, 0), (0, .065)]):
        round_detail(f'fruit_{i}', -1.0+dx, -2.8+dy, .64, .055, .1,
                     '0.85 0.52 0.13 1', True)
    # Use a separate linen colour for pillows to retain the coordinated accents.
    for name in ('throw_pillow_cream', 'throw_pillow_sage'):
        visual = world.find(f"model[@name='{name}']/link/visual")
        shape = visual.find('geometry')
        shape.clear()
        ellipsoid = ET.SubElement(shape, 'ellipsoid')
        ET.SubElement(ellipsoid, 'radii').text = '.20 .12 .19'
    if toolbox_state in ('absent','distractor'):
        for model in list(world.findall('model')):
            name=model.get('name','')
            if name.startswith(('toolbox_', 'handle_post_')):
                world.remove(model)
        # Removed target footprints must also disappear from the generated map.
        obstacles[:] = [o for o in obstacles if not (abs(o[0]+1.2)<.2 and abs(o[1]-1.6)<.2)]
        if toolbox_state=='distractor':
            box('plain_red_box', -1.2,1.6,.16,.5,.3,.32,red)
    elif toolbox_state=='occluded':
        box('inspection_occluder', -1.42,1.52,.39,.12,.6,.78,'0.50 0.52 0.53 1')
    # Low household hook and inspection trolley are visible from the fixed downward camera.
    bag_color = '0.19 0.32 0.48 1'
    box('backpack_hook_mount', 1.65, 3.88, .87, .16, .05, .12, wood, False)
    box('backpack_hook_tip', 1.65, 3.78, .85, .035, .18, .045, white, False)
    if backpack_state != 'absent':
        z = .59 if backpack_state in ('hanging','occluded') else .23
        y = 3.74 if backpack_state in ('hanging','occluded') else 3.35
        box('backpack_body', 1.65,y,z,.30,.19,.38,bag_color,False)
        box('backpack_pocket', 1.65,y-.11,z-.06,.23,.06,.17,'0.27 0.42 0.56 1',False)
        for dx in [-.095,.095]:
            box(f'backpack_strap_{dx}',1.65+dx,y-.125,z+.05,.032,.025,.25,'0.08 0.13 0.20 1',False)
        # Round bag and protruding front pocket, not a rectangular wall mailbox.
        for name, radii in [('backpack_body', '.16 .11 .22'), ('backpack_pocket', '.12 .045 .09')]:
            geometry = world.find(f"model[@name='{name}']/link/visual/geometry")
            geometry.clear()
            ET.SubElement(ET.SubElement(geometry,'ellipsoid'),'radii').text=radii
        box('backpack_zipper',1.65,y-.16,z-.015,.20,.018,.012,'0.70 0.73 0.75 1',False)
        for dx in [-.18,.18]:
            box(f'backpack_shoulder_{dx}',1.65+dx,y+.015,z+.035,.035,.045,.29,'0.10 0.17 0.25 1',False)
            box(f'backpack_shoulder_top_{dx}',1.65+dx*.78,y+.015,z+.19,.09,.045,.035,'0.10 0.17 0.25 1',False)
        box('backpack_loop_left',1.60,y,z+.23,.025,.035,.10,bag_color,False)
        box('backpack_loop_right',1.70,y,z+.23,.025,.035,.10,bag_color,False)
        box('backpack_loop_top',1.65,y,z+.28,.12,.035,.025,bag_color,False)
    if backpack_state=='occluded':
        box('backpack_occluder',1.65,3.45,.60,.48,.06,.65,'0.58 0.55 0.49 1',False)
    box('fruit_trolley',-1,-2.8,.25,.65,.55,.50,wood)
    if fruit_state in ('empty','absent'):
        for item in list(world.findall('model')):
            if item.get('name','').startswith('fruit_') and item.get('name') not in ('fruit_trolley','fruit_bowl'):
                world.remove(item)
    if fruit_state=='absent':
        world.remove(world.find("model[@name='fruit_bowl']"))
    # Exterior door at the south wall: open leaf has matching axis-aligned collision.
    for x in [.55,1.65]:
        box(f'entry_door_jamb_{x}',x,-3.96,.70,.09,.16,1.4,wood)
    box('entry_door_header',1.1,-3.96,1.43,1.2,.16,.09,wood,False)
    if door_state=='closed':
        box('entry_door_leaf',1.1,-3.98,.68,1.0,.055,1.34,'0.56 0.39 0.25 1')
        box('entry_door_handle',1.49,-3.93,.72,.13,.06,.035,white,False)
    else:
        # 90 degree opening; ajar uses 45 degrees and a conservative AABB in the map.
        if door_state=='open':
            box('entry_door_leaf',.61,-3.48,.68,.055,1.0,1.34,'0.56 0.39 0.25 1')
        else:
            box('entry_door_leaf',.96,-3.63,.68,1.0,.055,1.34,'0.56 0.39 0.25 1')
            world.find("model[@name='entry_door_leaf']/pose").text='.96 -3.63 .68 0 0 .785398'
            obstacles[-1]=(.96,-3.63,.75,.75)
    apply_materials(world, directory)
    # Conservative occupancy from the same axis-aligned collision footprints.
    resolution, width, height = .05, 220, 180
    rows = []
    for row in range(height):
        y = -4.5 + (height - row - .5) * resolution
        pixels = []
        for col in range(width):
            x = -5.5 + (col + .5) * resolution
            occupied = any(abs(x-ox) <= sx/2+.025 and abs(y-oy) <= sy/2+.025
                           for ox, oy, sx, sy in obstacles)
            pixels.append('0' if occupied else ('205' if abs(x)>5 or abs(y)>4 else '254'))
        rows.append(' '.join(pixels))
    directory = Path(directory)
    (directory / 'home.pgm').write_text('P2\n# 用途：家居场景同源几何占据栅格。\n220 180\n255\n' + '\n'.join(rows) + '\n')
    map_path = directory / 'home.yaml'
    map_path.write_text('# 用途：家居场景导航地图参数。\nimage: home.pgm\nresolution: 0.05\norigin: [-5.5, -4.5, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
    return str(map_path)
