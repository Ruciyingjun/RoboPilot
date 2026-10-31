"""用途：列出已支持的家居检查，将有限中文或编号选择完整解析为可预览的静态任务。"""

import re

from .schemas import ValidationError, parse_plan

# Explicit full-clause patterns: never collect a few keywords and drop the rest.
CATALOG = (
    ('toolbox', 'living_room', '客厅工具箱是否存在', r'(?:客厅(?:的)?)?工具箱(?:是否(?:存在|还在|在客厅)|在不在|还在不在)?'),
    ('backpack_hanging', 'backpack_check', '卧室背包是否挂在墙钩上', r'(?:卧室(?:的)?)?背包(?:是否|是不是)?(?:在墙上挂着|挂在墙上|挂在墙钩上|挂墙|挂着)'),
    ('door_closed', 'door_check', '指定外门是否关闭', r'(?:指定(?:的)?外门|外门|门)(?:是否|是不是)?(?:关闭|关好|关着|已关闭)'),
    ('fruit_bowl', 'fruit_check', '厨房果盘中是否有水果', r'(?:厨房(?:的)?)?果盘(?:是否在厨房|是否有水果|中是否有水果|里是否有水果|有水果)?'),
    ('red_marker', 'living_room', '客厅是否有红色标记（本地颜色检测）', r'(?:客厅(?:是否有|的)?)?红色标记(?:是否存在|是否还在|在不在)?'),
)


def catalog_text():
    return '\n'.join(f'{i}. {label} → {place}' for i, (_,place,label,_) in enumerate(CATALOG,1))


def select_tasks(text):
    if not isinstance(text,str) or not 1 <= len(text.strip()) <= 500:
        raise ValidationError('请输入1–500字的任务或编号')
    text=text.strip()
    text=re.sub(r'[。.!！]+$','',text)
    text=re.sub(r'(?:[，,、；;]?\s*(?:最后|并)?(?:返回|回到)起点)$','',text)
    parts=re.split(r'\s*(?:[、，,；;]?\s*(?:然后|接着|并且|以及)|[、，,；;]|和)\s*',text)
    selected=[]
    for part in parts:
        if not part.strip():raise ValidationError('任务中有空项目，请重新输入')
        part=re.sub(r'^(?:请)?(?:帮我)?(?:先|再)?(?:检查一下|检查|看看|确认)?\s*','',part.strip())
        if part.isdigit() and 1<=int(part)<=len(CATALOG):
            index=int(part)-1
        else:
            matches=[i for i,(_,_,_,pattern) in enumerate(CATALOG) if re.fullmatch(pattern,part)]
            if len(matches)!=1:
                raise ValidationError(f'不能完整理解「{part}」；请使用清单编号或列出的检查说法，不支持的部分不会被省略')
            index=matches[0]
        if index in selected:raise ValidationError('任务重复，请每项只选一次')
        selected.append(index)
    return selected


def catalog_plan(text,places):
    selected=select_tasks(text)
    steps=[]
    for index in selected:
        target,place,_,_=CATALOG[index]
        nav=f'go_{index+1}'
        steps += [{'id':nav,'action':'navigate','place':place,'timeout_s':180},
                  {'id':f'inspect_{index+1}','action':'inspect','place':place,'target':target,
                   'depends_on':[nav],'timeout_s':60 if target!='red_marker' else 15}]
    steps.append({'id':'return','action':'return_to_start','timeout_s':180})
    return parse_plan({'version':1,'name':'user_selected_inspection','steps':steps},places), selected


def run_interactive(args):
    """Preview and explicit confirmation precede backend or paid service setup."""
    from .schemas import load_inputs
    print('当前可执行任务（指定观察点，不包含抓取、开门或自动搜索其他物品）：')
    print(catalog_text())
    print('示例：2,3,4；或：检查背包是否挂在墙上、门是否关闭、果盘是否在厨房。')
    print('所有任务完成后返回本次起点；语义检查会上传相机图片并产生API用量。')
    if args.list_only:return 0
    backend=store=None
    try:
        text=args.instruction if args.instruction is not None else input('请输入要检查的任务（输入q退出）：').strip()
        if text.lower() in ('q','quit','退出'):return 0
        places,_=load_inputs(args.places)
        plan,selected=catalog_plan(text,places)
        print('\n执行前预览：')
        for order,index in enumerate(selected,1):
            _,place,label,_=CATALOG[index]
            print(f'{order}. 前往 {place} → 检查：{label}')
        print(f'{len(selected)+1}. 返回本次任务起点')
        print('注意：果盘任务要求盘中有水果；任务执行成功不表示检查条件都满足。')
        if args.preview:return 0
        if input('是否开始执行？输入 y/是 确认：').strip().lower() not in ('y','yes','是'):
            print('已取消，未发送机器人目标。');return 0
        from .llm_config import load_llm_config
        if any(CATALOG[i][0]!='red_marker' for i in selected):load_llm_config()
        from .backends import MockBackend
        from .storage import MissionStore
        from .executor import MissionExecutor
        if args.backend=='ros':
            from .ros_adapter import RosNavigationBackend
            backend=RosNavigationBackend()
        else:backend=MockBackend()
        store=MissionStore(args.output)
        mission=MissionExecutor(backend,store,90,print).run(plan,places,
            {'planner':'catalog_rules','instruction':text})
        print(f"任务状态：{mission['status']}")
        print(f"报告：{(args.output/mission['id']/'report.md').resolve()}")
        if mission['status']!='SUCCEEDED':
            for step in mission['steps']:
                if step['status'] not in ('SUCCEEDED','SKIPPED'):
                    codes=[a.get('result',{}).get('code','') for a in step['attempts']]
                    print(f"未完成步骤：{step['id']} / {step['status']} / {','.join(codes)} / {step['message']}")
        if mission['error']:print(mission['error'])
        return 0 if mission['status']=='SUCCEEDED' else 1
    except (EOFError,KeyboardInterrupt):
        print('输入已取消。');return 130
    except Exception as exc:
        print(f'未能执行：{exc}');return 2
    finally:
        if backend:backend.close()
        if store:store.close()
