"""Build MuJoCo scenes and maps from the existing home geometry source."""
import copy
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from .home_scene import build_home
from .mujoco_bridge import default_model


def build_scene(directory, scene='home'):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    root = ET.parse(default_model()).getroot()
    worldbody = root.find('worldbody')
    if scene == 'home':
        sdf_world = ET.Element('world')
        map_path = Path(build_home(sdf_world, directory))
        robot = copy.deepcopy(worldbody.find("body[@name='base_link']"))
        for child in list(worldbody):
            worldbody.remove(child)
        ET.SubElement(worldbody, 'light', pos='0 0 5', directional='true', diffuse='.8 .8 .8')
        asset = ET.SubElement(root, 'asset')
        textures = {}
        for model in sdf_world.findall('model'):
            body = ET.SubElement(worldbody, 'body', name=model.get('name'),
                                 pos=' '.join(model.findtext('pose').split()[:3]),
                                 euler=' '.join(model.findtext('pose').split()[3:]))
            for kind in ('collision', 'visual'):
                for index, element in enumerate(model.findall(f'link/{kind}')):
                    shape = element.find('geometry')[0]
                    attrs = {'name': f'{model.get("name")}_{kind}_{index}'}
                    values = lambda tag: [float(v) for v in shape.findtext(tag).split()]
                    if shape.tag == 'box':
                        attrs.update(type='box', size=' '.join(str(v/2) for v in values('size')))
                    elif shape.tag == 'sphere':
                        attrs.update(type='sphere', size=shape.findtext('radius'))
                    elif shape.tag == 'cylinder':
                        attrs.update(type='cylinder', size=f'{shape.findtext("radius")} {float(shape.findtext("length"))/2}')
                    elif shape.tag == 'ellipsoid':
                        attrs.update(type='ellipsoid', size=shape.findtext('radii'))
                    else:
                        raise ValueError(f'Unsupported home geometry: {shape.tag}')
                    pose = element.findtext('pose', '0 0 0 0 0 0').split()
                    attrs.update(pos=' '.join(pose[:3]), euler=' '.join(pose[3:]))
                    if kind == 'collision':
                        # mj_ray skips alpha=0 geoms. Keep collision envelopes
                        # almost invisible while retaining physical lidar hits.
                        attrs.update(group='0', rgba='0 0 0 .001')
                    else:
                        attrs.update(group='2', contype='0', conaffinity='0',
                                     rgba=element.findtext('material/diffuse', '.7 .7 .7 1'))
                        texture = element.findtext('material/pbr/metal/albedo_map')
                        if texture:
                            if texture not in textures:
                                key = 'texture_' + str(len(textures))
                                textures[texture] = key
                                ET.SubElement(asset, 'texture', name=key, type='2d', file=texture)
                                ET.SubElement(asset, 'material', name=key, texture=key, texrepeat='2 2')
                            attrs['material'] = textures[texture]
                    ET.SubElement(body, 'geom', **attrs)
        # Same observation height, pitch and horizontal FOV as the original service robot.
        camera = robot.find('camera')
        pitch = .55
        camera.set('pos', '.17 0 .915')
        camera.set('xyaxes', f'0 -1 0 {math.sin(pitch)} 0 {math.cos(pitch)}')
        camera.set('fovy', str(math.degrees(2*math.atan(.75*math.tan(1.047/2)))))
        ET.SubElement(robot, 'geom', name='mast', group='1', contype='0', conaffinity='0',
                      type='cylinder', pos='0 0 .40', size='.045 .35', mass='.2', rgba='.2 .3 .4 1')
        worldbody.append(robot)
        start = (2.7, -2.1, math.pi/2)
    elif scene == 'demo':
        # Rasterize actual static box collision footprints of the bridge demo.
        resolution, width = .05, 140
        rectangles = []
        for geom in worldbody.findall('geom'):
            if geom.get('type') == 'box':
                x, y, _ = map(float, geom.get('pos').split())
                sx, sy, _ = map(float, geom.get('size').split())
                rectangles.append((x, y, sx, sy))
        pixels = bytearray()
        for row in range(width):
            y = -3.5+(width-row-.5)*resolution
            for col in range(width):
                x = -3.5+(col+.5)*resolution
                occupied = any(abs(x-ox)<=sx+.025 and abs(y-oy)<=sy+.025 for ox,oy,sx,sy in rectangles)
                pixels.append(0 if occupied else 254 if abs(x)<3 and abs(y)<3 else 205)
        (directory/'demo.pgm').write_bytes(b'P5\n140 140\n255\n'+pixels)
        map_path = directory/'demo.yaml'
        map_path.write_text('image: demo.pgm\nresolution: 0.05\norigin: [-3.5, -3.5, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
        start = (0., 0., 0.)
    else:
        raise ValueError('scene must be home or demo')
    model_path = directory/'scene.xml'
    ET.ElementTree(root).write(model_path, encoding='unicode')
    return model_path, map_path, start
