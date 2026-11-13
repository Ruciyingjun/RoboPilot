"""用途：集中定义可检查目标、状态命题、视觉证据与适用地点，供执行和评测共用。"""

VISUAL_TARGETS = {
    'toolbox': None,  # Existing calibrated toolbox prompt remains unchanged.
    'backpack_hanging': {
        'label': '背包是否挂在墙上', 'place': 'backpack_check',
        'question': 'Is a BACKPACK visibly hanging from a WALL HOOK? Require backpack features (straps/pockets) and a visible top loop/hook connection to a wall mount, with clearance below the bag. A backpack on the floor or shelf does NOT satisfy hanging. Mere proximity to a wall is insufficient.',
        'cues': ('backpack', 'straps', 'wall_hook', 'suspended'),
        'required': ('backpack', 'wall_hook', 'suspended'),
    },
    'door_closed': {
        'label': '指定门是否关闭', 'place': 'door_check',
        'question': 'Is the designated exterior DOOR CLOSED? Inspect the door frame and leaf: require leaf aligned with the frame and filling the doorway, with no substantial opening. A visible open or partly open leaf means the condition is false. Do not infer closed from a wall/cabinet or absence of a visible opening alone.',
        'cues': ('door_leaf', 'door_frame', 'aligned', 'no_open_gap'),
        'required': ('door_leaf', 'door_frame', 'aligned', 'no_open_gap'),
    },
    'fruit_bowl': {
        'label': '厨房是否有装水果的果盘', 'place': 'fruit_check',
        'question': 'Is a FRUIT BOWL containing visible fruit present on the designated kitchen inspection table? Require both a bowl/plate and identifiable fruit inside it. An empty bowl or a ball outside a bowl does not satisfy this condition. Kitchen location is established by the configured checkpoint, never infer a room solely from pixels.',
        'cues': ('bowl', 'fruit', 'fruit_inside_bowl'),
        'required': ('bowl', 'fruit', 'fruit_inside_bowl'),
    },
}
TARGETS = ('red_marker', *VISUAL_TARGETS)
