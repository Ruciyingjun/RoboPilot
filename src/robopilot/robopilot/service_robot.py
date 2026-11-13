"""用途：在差速底盘上添加酒店服务机器人外壳、头部相机及一致的 RViz/TF 描述。"""

import xml.etree.ElementTree as ET


def configure_robot(robot, urdf, service=True):
    """Return robot_description; locomotion remains differential drive, service shell fixed."""
    base = robot.find("model/link[@name='base_link']")
    description = ET.fromstring(urdf)
    urdf_base = description.find("link[@name='base_link']")
    if service:
        for parent in (base, urdf_base):
            for visual in list(parent.findall('visual')):
                parent.remove(visual)
        # All shell parts fit inside a 0.40 m diameter navigation envelope.
        parts = [
            ('lower_shell', (0,0,.24), 'cylinder', (.19,.16), '.86 .89 .90 1'),
            ('waist', (0,0,.48), 'cylinder', (.135,.36), '.88 .91 .92 1'),
            ('upper_body', (0,0,.73), 'cylinder', (.16,.20), '.88 .91 .92 1'),
            ('shoulder_cap', (0,0,.83), 'sphere', (.16,), '.88 .91 .92 1'),
            ('neck', (0,0,.93), 'cylinder', (.065,.14), '.22 .28 .32 1'),
            ('head', (0,0,1.055), 'sphere', (.14,), '.88 .91 .92 1'),
            ('screen_bezel', (.157,0,.76), 'box', (.025,.22,.17), '.08 .14 .19 1'),
            ('screen', (.174,0,.76), 'box', (.008,.195,.145), '.12 .36 .46 1'),
            ('screen_welcome', (.18,0,.79), 'box', (.005,.12,.014), '.56 .86 .90 1'),
            ('screen_button', (.18,0,.72), 'box', (.005,.07,.018), '.30 .68 .71 1'),
            ('camera_panel', (.131,0,1.065), 'box', (.022,.105,.065), '.07 .13 .17 1'),
            ('camera_lens', (.146,0,1.075), 'sphere', (.018,), '.12 .35 .43 1'),
        ]
        def shape(parent, kind, size, sdf):
            if sdf:
                node = ET.SubElement(parent,kind)
                if kind == 'box':
                    ET.SubElement(node,'size').text=' '.join(map(str,size))
                else:
                    ET.SubElement(node,'radius').text=str(size[0])
                    if kind == 'cylinder':
                        ET.SubElement(node,'length').text=str(size[1])
            else:
                attrs = {'size':' '.join(map(str,size))} if kind == 'box' else {'radius':str(size[0])}
                if kind == 'cylinder':
                    attrs['length']=str(size[1])
                ET.SubElement(parent,kind,**attrs)
        for name,xyz,kind,size,color in parts:
            visual=ET.SubElement(base,'visual',name='service_'+name)
            ET.SubElement(visual,'pose').text=' '.join(map(str,(*xyz,0,0,0)))
            shape(ET.SubElement(visual,'geometry'),kind,size,True)
            material=ET.SubElement(visual,'material')
            ET.SubElement(material,'ambient').text=color
            ET.SubElement(material,'diffuse').text=color
            rv=ET.SubElement(urdf_base,'visual',name='service_'+name)
            ET.SubElement(rv,'origin',xyz=' '.join(map(str,xyz)),rpy='0 0 0')
            shape(ET.SubElement(rv,'geometry'),kind,size,False)
            ET.SubElement(ET.SubElement(rv,'material',name='service_'+name),'color',rgba=color)
        collision=ET.SubElement(base,'collision',name='service_shell')
        ET.SubElement(collision,'pose').text='0 0 .69 0 0 0'
        shape(ET.SubElement(collision,'geometry'),'cylinder',(.195,1.02),True)
    camera_xyz = '.17 0 1.075' if service else '.1 0 .22'
    pitch = '.55' if service else '0'
    sensor = ET.SubElement(base,'sensor',name='robopilot_rgb',type='camera')
    ET.SubElement(sensor,'pose').text=f'{camera_xyz} 0 {pitch} 0'
    ET.SubElement(sensor,'always_on').text='true'
    ET.SubElement(sensor,'update_rate').text='2'
    ET.SubElement(sensor,'topic').text='/robopilot/camera/image_raw'
    ET.SubElement(sensor,'gz_frame_id').text='robopilot_camera_optical_frame'
    camera = ET.SubElement(sensor,'camera')
    ET.SubElement(camera,'horizontal_fov').text='1.047'
    image=ET.SubElement(camera,'image')
    for tag,value in [('width','320'),('height','240'),('format','R8G8B8')]:
        ET.SubElement(image,tag).text=value
    clip=ET.SubElement(camera,'clip')
    ET.SubElement(clip,'near').text='.05'
    ET.SubElement(clip,'far').text='10'
    for name,parent,xyz,rpy in [
        ('robopilot_camera_link','base_link',camera_xyz,f'0 {pitch} 0'),
        ('robopilot_camera_optical_frame','robopilot_camera_link','0 0 0','-1.57079632679 0 -1.57079632679'),
    ]:
        ET.SubElement(description,'link',name=name)
        joint=ET.SubElement(description,'joint',name=name+'_joint',type='fixed')
        ET.SubElement(joint,'parent',link=parent)
        ET.SubElement(joint,'child',link=name)
        ET.SubElement(joint,'origin',xyz=xyz,rpy=rpy)
    return ET.tostring(description,encoding='unicode')
