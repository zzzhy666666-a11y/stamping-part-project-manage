from flask import Flask, request, jsonify, send_from_directory
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='.')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_FILE = os.path.join(BASE_DIR, 'projects.json')

def load_store():
    try:
        with open(PROJECTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            data.setdefault('projects', [])
            data.setdefault('collections', [])
            return data
    except Exception as e:
        print(f"读取数据失败: {e}")
        return {'projects': [], 'collections': []}

# 读取项目数据
def load_projects():
    return load_store().get('projects', [])

def load_collections():
    return load_store().get('collections', [])

# 保存项目数据
def save_projects(projects):
    try:
        data = load_store()
        data['projects'] = projects
        with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存数据失败: {e}")
        return False

def save_collections(collections, projects=None):
    try:
        data = load_store()
        data['collections'] = collections
        if projects is not None:
            data['projects'] = projects
        with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存项目集失败: {e}")
        return False

# 生成新ID
def generate_id(projects):
    if not projects:
        return 1
    return max(p['id'] for p in projects) + 1

# 生成任务ID
def generate_task_id():
    import uuid
    return f"task-{uuid.uuid4().hex[:8]}"

def generate_issue_id():
    import uuid
    return f"issue-{uuid.uuid4().hex[:8]}"

ISSUE_STATUSES = ('待处理', '处理中', '已解决', '已关闭')
ISSUE_RISK_LEVELS = ('高', '中', '低')
ISSUE_FIELDS = ('customerName', 'description', 'department', 'status', 'riskLevel',
                'nextAction', 'deadline', 'notes')

def ensure_issue_lists(projects):
    changed = False
    for project in projects:
        if not isinstance(project.get('issues'), list):
            project['issues'] = []
            changed = True
    return changed

def normalize_issue(data, issue_id=None, existing=None):
    issue = dict(existing or {})
    for field in ISSUE_FIELDS:
        if field in data:
            issue[field] = str(data.get(field, '')).strip()
        else:
            issue.setdefault(field, '')
    if not issue.get('description'):
        return None
    if issue.get('status') not in ISSUE_STATUSES:
        issue['status'] = '待处理'
    if issue.get('riskLevel') not in ISSUE_RISK_LEVELS:
        issue['riskLevel'] = '中'
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    issue['id'] = issue_id or issue.get('id') or generate_issue_id()
    issue.setdefault('createdAt', now)
    issue['updatedAt'] = now
    return issue

def issue_snapshot(project, issue):
    return {
        'id': issue.get('id'),
        'projectId': project.get('id'),
        'projectName': project.get('name', ''),
        'customerName': issue.get('customerName') or project.get('customer', ''),
        'description': issue.get('description', ''),
        'department': issue.get('department', ''),
        'status': issue.get('status', '待处理'),
        'riskLevel': issue.get('riskLevel', '中'),
        'nextAction': issue.get('nextAction', ''),
        'deadline': issue.get('deadline', ''),
        'notes': issue.get('notes', ''),
        'createdAt': issue.get('createdAt', ''),
        'updatedAt': issue.get('updatedAt', '')
    }

def flatten_issues(projects):
    return [
        issue_snapshot(project, issue)
        for project in projects
        for issue in project.get('issues', [])
    ]

def make_task(phase, name, start_date, end_date, description='', parent_task=None,
              is_parent=False, extra=None):
    task = {
        'id': generate_task_id(),
        'phase': phase,
        'name': name,
        'startDate': start_date,
        'endDate': end_date,
        'status': '未开始',
        'description': description
    }
    if parent_task:
        task['parentTask'] = parent_task
    if is_parent:
        task['isParent'] = True
    if extra:
        task.update(extra)
    return task

def add_days(date_str, days):
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        return (date + timedelta(days=days)).strftime('%Y-%m-%d')
    except Exception:
        return date_str

def to_int(value):
    try:
        return int(value)
    except Exception:
        return 0

def to_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0

def normalize_process_mode(value):
    if value in ('预镀', '预度'):
        return '预镀'
    if value == '料带镀':
        return '料带镀'
    return '后镀'

def use_strip_plating(process_mode, product_quantity=None, mold_quantity=None):
    product_count = to_int(product_quantity)
    mold_count = to_int(mold_quantity)
    return process_mode == '料带镀' or (product_count > 0 and mold_count == product_count * 2)

def calculate_material_weight(task):
    width = to_float(task.get('materialWidth'))
    thickness = to_float(task.get('materialThickness'))
    pitch = to_float(task.get('materialPitch'))
    density = to_float(task.get('materialDensity'))
    annual_quantity = to_float(task.get('annualQuantity'))
    # mm * mm * mm = mm3; /1000 -> cm3, * g/cm3 -> g, /1000 -> kg.
    weight = width * thickness * pitch * density * annual_quantity * (3 / 12) / 1000000
    return round(weight, 3)

def make_material_purchase_task(index, start_date=''):
    return make_task(
        '第二阶段：设计与制作',
        f'买材料数量 - 产品{index}',
        '',
        '',
        '填写材料参数后自动计算3个月采购重量',
        parent_task='原材料采购',
        extra={
            'noSchedule': True,
            'generatedMaterialTask': True,
            'materialIndex': index,
            'materialGrade': '',
            'materialWidth': '',
            'materialPitch': '',
            'materialThickness': '',
            'materialDensity': '',
            'annualQuantity': '',
            'materialWeight': 0
        }
    )

def ensure_material_purchase_tasks(project):
    tasks = project.setdefault('tasks', [])
    product_count = max(to_int(project.get('productQuantity')), 1)
    existing = [
        task for task in tasks
        if task.get('parentTask') == '原材料采购' and task.get('generatedMaterialTask')
    ]
    changed = False
    for task in existing:
        weight = calculate_material_weight(task)
        if task.get('materialWeight') != weight:
            task['materialWeight'] = weight
            changed = True
        if not task.get('noSchedule'):
            task['noSchedule'] = True
            changed = True
    existing_indexes = {to_int(task.get('materialIndex')) for task in existing}
    for index in range(1, product_count + 1):
        if index in existing_indexes:
            continue
        tasks.append(make_material_purchase_task(index, project.get('startDate', '')))
        changed = True
    return changed

def descendant_tasks(project, parent_task):
    descendants = []
    pending = [parent_task]
    while pending:
        current_parent = pending.pop()
        for task in project.get('tasks', []):
            if task.get('parentTask') == current_parent:
                descendants.append(task)
                pending.append(task.get('name'))
    return descendants

def sync_completed_parent_descendants(project):
    changed = False
    for task in project.get('tasks', []):
        if task.get('status') != '已完成':
            continue
        for child in descendant_tasks(project, task.get('name')):
            if child.get('status') == '已完成':
                continue
            child['status'] = '已完成'
            child.pop('autoOverdue', None)
            child['manualStatusOverride'] = True
            changed = True
    return changed

DESIGN_DAYS = 5
SECOND_PUNCH_DESIGN_DAYS = 7
MOLD_PROCESSING_DAYS = 12
MOLD_ASSEMBLY_DAYS = 4
PLATING_DAYS = 7

def end_after_days(start_date, duration):
    return add_days(start_date, max(duration - 1, 0))

def process_phase2_tasks(start_date, t0_date, process_mode):
    if process_mode != '预镀':
        return []
    plating_start = add_days(t0_date or start_date, -PLATING_DAYS)
    plating_end = add_days(t0_date or start_date, -1)
    return [
        make_task('第二阶段：设计与制作', '原材料送电镀', plating_start, plating_end,
                  '原材料到货后送外协电镀，按7天周期安排', parent_task='原材料采购'),
        make_task('第二阶段：设计与制作', '电镀材料回厂', plating_end, plating_end,
                  '预镀材料回厂并确认可投入T0试模', parent_task='原材料采购')
    ]

def stagger_offset(index):
    """One mold occupies one full trial day."""
    return index

def make_mold_trial_task(name, mold_number, base_date, offset, description, order):
    trial_date = add_days(base_date, offset)
    return make_task(
        '第三阶段：T0/T1试模',
        f'{name} - {mold_number}号模具',
        trial_date,
        trial_date,
        description,
        parent_task='T0试模',
        extra={
            'moldNumber': mold_number,
            'generatedMoldTask': True,
            'displayOrder': order
        }
    )

def t0_mold_plan_tasks(start_date, t0_date, process_mode='后镀',
                       product_quantity=None, mold_quantity=None):
    base_date = t0_date or start_date
    mold_count = max(to_int(mold_quantity), 1)
    children = []
    final_offset = 0

    if use_strip_plating(process_mode, product_quantity, mold_quantity):
        first_count = max(1, (mold_count + 1) // 2)
        first_numbers = list(range(1, first_count + 1))
        second_numbers = list(range(first_count + 1, mold_count + 1)) or first_numbers
        first_offsets = [stagger_offset(index) for index in range(len(first_numbers))]
        for index, mold_number in enumerate(first_numbers):
            children.append(make_mold_trial_task(
                '一冲T0试模',
                mold_number,
                base_date,
                first_offsets[index],
                f'{mold_number}号一冲模具试模，打出待电镀料带',
                510 + index
            ))

        plating_start_offset = max(first_offsets) + 1
        plating_end_offset = plating_start_offset + PLATING_DAYS - 1
        first_label = '、'.join(str(number) for number in first_numbers)
        children.append(make_task(
            '第三阶段：T0/T1试模',
            '料带电镀回厂',
            add_days(base_date, plating_start_offset),
            add_days(base_date, plating_end_offset),
            f'承接{first_label}号一冲模具试出的料带，按7天周期送电镀并回厂',
            parent_task='T0试模',
            extra={'generatedMoldTask': True, 'displayOrder': 520}
        ))

        second_start_offset = plating_end_offset + 1
        second_offsets = [
            second_start_offset + stagger_offset(index)
            for index in range(len(second_numbers))
        ]
        for index, mold_number in enumerate(second_numbers):
            children.append(make_mold_trial_task(
                '二冲T0试模',
                mold_number,
                base_date,
                second_offsets[index],
                f'{mold_number}号二冲模具使用回厂电镀料带试模',
                530 + index
            ))
        final_offset = max(second_offsets)
        summary_description = f'料带镀工艺，{first_label}号一冲后电镀，再进入二冲试模'
    elif process_mode == '后镀':
        trial_offsets = [stagger_offset(index) for index in range(mold_count)]
        for index, mold_number in enumerate(range(1, mold_count + 1)):
            children.append(make_mold_trial_task(
                'T0试模执行',
                mold_number,
                base_date,
                trial_offsets[index],
                f'{mold_number}号模具试模并取得待后镀试模件',
                510 + index
            ))
        plating_offset = max(trial_offsets) + 1
        plating_end_offset = plating_offset + PLATING_DAYS - 1
        children.append(make_task(
            '第三阶段：T0/T1试模',
            '试模件后镀',
            add_days(base_date, plating_offset),
            add_days(base_date, plating_end_offset),
            '各套模具试模件集中送电镀，按7天周期安排',
            parent_task='T0试模',
            extra={'generatedMoldTask': True, 'displayOrder': 520}
        ))
        final_offset = plating_end_offset
        summary_description = f'后镀工艺，按{mold_count}套模具分别试模后送电镀'
    else:
        trial_offsets = [stagger_offset(index) for index in range(mold_count)]
        for index, mold_number in enumerate(range(1, mold_count + 1)):
            children.append(make_mold_trial_task(
                '预镀材料T0试模',
                mold_number,
                base_date,
                trial_offsets[index],
                f'{mold_number}号模具使用预镀材料开展T0试模验证',
                510 + index
            ))
        final_offset = max(trial_offsets)
        summary_description = f'预镀工艺，按{mold_count}套模具分别开展T0试模'

    result_date = add_days(base_date, final_offset)
    children.extend([
        make_task(
            '第三阶段：T0/T1试模',
            '尺寸报告',
            result_date,
            result_date,
            '全部T0试模完成后的样件尺寸检测报告',
            parent_task='T0试模',
            extra={'generatedMoldTask': True, 'displayOrder': 540}
        ),
        make_task(
            '第三阶段：T0/T1试模',
            '问题点清单',
            result_date,
            result_date,
            '汇总各套T0试模问题点和责任闭环',
            parent_task='T0试模',
            extra={'generatedMoldTask': True, 'displayOrder': 550}
        )
    ])
    return [
        make_task(
            '第三阶段：T0/T1试模',
            'T0试模',
            base_date,
            result_date,
            summary_description,
            is_parent=True,
            extra={'generatedMoldTask': True, 'displayOrder': 500}
        ),
        *children
    ], final_offset

def standard_followup_tasks(start_date, t0_date, ppap_date, process_mode='后镀',
                            product_quantity=None, mold_quantity=None):
    t0_tasks, t0_last_offset = t0_mold_plan_tasks(
        start_date,
        t0_date,
        process_mode,
        product_quantity,
        mold_quantity
    )
    t1_date = add_days(t0_date or start_date, t0_last_offset + 7)
    ost_date = add_days(t1_date, 7)
    transfer_date = add_days(ppap_date or ost_date, 7)

    return [
        *t0_tasks,
        make_task('第三阶段：T0/T1试模', 'T1试模', t1_date, t1_date, '开展T1试模验证', is_parent=True),
        make_task('第三阶段：T0/T1试模', '尺寸报告', t1_date, t1_date, 'T1样件尺寸检测报告', parent_task='T1试模'),
        make_task('第三阶段：T0/T1试模', '问题清单更新', t1_date, t1_date, '更新并关闭T0/T1遗留问题', parent_task='T1试模'),
        make_task('第三阶段：T0/T1试模', '正式BOM更新', t1_date, t1_date, '根据试模结果更新正式BOM', is_parent=True,
                  extra={'moldCode': '', 'materialCode': ''}),
        make_task('第三阶段：T0/T1试模', '包装方案', t1_date, ost_date, '确认包装方式、标签和周转方案', is_parent=True),
        make_task('第三阶段：T0/T1试模', 'OST交样', ost_date, ost_date, '提交OST样件和相关记录', is_parent=True),
        make_task('第四阶段：正式PPAP', '正式PPAP资料提交', ppap_date, ppap_date, '更新并提交正式PPAP资料', is_parent=True),
        make_task('第五阶段：量产转移', '量产转移', ppap_date, transfer_date, '移交量产资料、工艺和质量控制要求', is_parent=True)
    ]

def update_task_dates(project, name, start_date, end_date, parent_task=None):
    changed = False
    for task in project.get('tasks', []):
        if task.get('name') != name or task.get('parentTask') != parent_task:
            continue
        if task.get('startDate') != start_date or task.get('endDate') != end_date:
            task['startDate'] = start_date
            task['endDate'] = end_date
            changed = True
    return changed

def apply_preparation_schedule(project):
    start_date = project.get('startDate')
    t0_date = project.get('t0Date') or start_date
    second_punch = use_strip_plating(
        normalize_process_mode(project.get('processMode')),
        project.get('productQuantity'),
        project.get('moldQuantity')
    )
    design_days = SECOND_PUNCH_DESIGN_DAYS if second_punch else DESIGN_DAYS
    design_end = end_after_days(start_date, design_days)
    processing_start = add_days(design_end, 1)
    processing_end = end_after_days(processing_start, MOLD_PROCESSING_DAYS)
    assembly_start = add_days(processing_end, 1)
    assembly_end = end_after_days(assembly_start, MOLD_ASSEMBLY_DAYS)
    material_arrival = add_days(t0_date, -PLATING_DAYS) if project.get('processMode') == '预镀' else assembly_end

    spans = [
        ('项目启动会议', start_date, start_date, None),
        ('获得客户图纸和标准', start_date, start_date, None),
        ('模具的设计与制作', start_date, assembly_end, None),
        ('料带图确认', start_date, design_end, '模具的设计与制作'),
        ('模具图纸外发', design_end, design_end, '模具的设计与制作'),
        ('模具加工', processing_start, processing_end, '模具的设计与制作'),
        ('模具组装', assembly_start, assembly_end, '模具的设计与制作'),
        ('工装检具的设计制作', start_date, design_end, None),
        ('检具设计', start_date, design_end, '工装检具的设计制作'),
        ('检具外发', design_end, design_end, '工装检具的设计制作'),
        ('生产工序图', start_date, design_end, '工装检具的设计制作'),
        ('料带图', start_date, design_end, '生产工序图'),
        ('材料图', start_date, design_end, '生产工序图'),
        ('电镀图', start_date, design_end, '生产工序图'),
        ('产品图', start_date, design_end, '生产工序图'),
        ('初始BOM', design_end, design_end, '工装检具的设计制作'),
        ('原材料采购', design_end, material_arrival, None),
        ('原材料请购', design_end, design_end, '原材料采购'),
        ('原材料到货', material_arrival, material_arrival, '原材料采购'),
        ('初始PPAP', start_date, design_end, None),
    ]
    for name, task_start, task_end, parent_task in spans:
        update_task_dates(project, name, task_start, task_end, parent_task)
    return assembly_end

def update_followup_schedule(project):
    t0_parent = next((
        task for task in project.get('tasks', [])
        if task.get('name') == 'T0试模' and not task.get('parentTask')
    ), None)
    t0_result_date = t0_parent.get('endDate') if t0_parent else project.get('t0Date')
    t1_date = add_days(t0_result_date, 7)
    ost_date = add_days(t1_date, 7)
    ppap_date = project.get('ppapDate') or ost_date
    transfer_date = add_days(ppap_date, 7)
    for name, start_date, end_date, parent_task in [
        ('T1试模', t1_date, t1_date, None),
        ('尺寸报告', t1_date, t1_date, 'T1试模'),
        ('问题清单更新', t1_date, t1_date, 'T1试模'),
        ('正式BOM更新', t1_date, t1_date, None),
        ('包装方案', t1_date, ost_date, None),
        ('OST交样', ost_date, ost_date, None),
        ('正式PPAP资料提交', ppap_date, ppap_date, None),
        ('量产转移', ppap_date, transfer_date, None),
    ]:
        update_task_dates(project, name, start_date, end_date, parent_task)

def preparation_warning(project, assembly_end):
    warnings = []
    try:
        ready_date = datetime.strptime(assembly_end, '%Y-%m-%d').date()
        t0_date = datetime.strptime(project.get('t0Date', ''), '%Y-%m-%d').date()
    except Exception:
        ready_date = None
        t0_date = None
    if ready_date and t0_date:
        late_days = (ready_date - t0_date).days
        if late_days > 0:
            warnings.append(f'按标准周期，模具组装将在T0后{late_days}天完成，请调整T0或提前启动。')

    ost_task = next((
        task for task in project.get('tasks', [])
        if task.get('name') == 'OST交样' and not task.get('parentTask')
    ), None)
    try:
        ost_date = datetime.strptime(ost_task.get('endDate', ''), '%Y-%m-%d').date()
        ppap_date = datetime.strptime(project.get('ppapDate', ''), '%Y-%m-%d').date()
    except Exception:
        ost_date = None
        ppap_date = None
    if ost_date and ppap_date and ost_date > ppap_date:
        warnings.append(f'预计OST交样晚于PPAP {(ost_date - ppap_date).days} 天，请调整PPAP节点。')
    return ' '.join(warnings)

STANDARD_TASK_ORDER = {
    '项目启动会议': 10,
    '获得客户图纸和标准': 20,
    '模具的设计与制作': 100,
    '料带图确认': 110,
    '模具图纸外发': 120,
    '模具加工': 130,
    '模具组装': 140,
    '工装检具的设计制作': 200,
    '检具设计': 210,
    '检具外发': 220,
    '生产工序图': 230,
    '料带图': 231,
    '材料图': 232,
    '电镀图': 233,
    '产品图': 234,
    '初始BOM': 240,
    '原材料采购': 300,
    '原材料请购': 310,
    '买材料数量': 315,
    '原材料到货': 320,
    '原材料送电镀': 330,
    '电镀材料回厂': 340,
    '初始PPAP': 400,
    'T0试模': 500,
    '预镀材料T0试模': 510,
    'T0试模执行': 510,
    '一冲T0试模': 510,
    '试模件后镀': 520,
    '料带电镀': 520,
    '料带电镀回厂': 520,
    '二冲试模': 530,
    '问题点清单': 550,
    'T1试模': 600,
    '问题清单更新': 630,
    '正式BOM更新': 700,
    '包装方案': 710,
    'OST交样': 720,
    '正式PPAP资料提交': 800,
    '量产转移': 900
}

def default_task_order(task):
    name = task.get('name', '')
    if name == '尺寸报告':
        return 620 if task.get('parentTask') == 'T1试模' else 540
    if name.startswith('买材料数量 - 产品'):
        return 315 + to_int(task.get('materialIndex'))
    for mold_task_name, base_order in (
        ('预镀材料T0试模 - ', 510),
        ('T0试模执行 - ', 510),
        ('一冲T0试模 - ', 510),
        ('二冲T0试模 - ', 530),
    ):
        if name.startswith(mold_task_name):
            return base_order + to_int(task.get('moldNumber'))
    return STANDARD_TASK_ORDER.get(name, 999)

def sibling_key(task):
    return task.get('phase', ''), task.get('parentTask', '')

def ensure_task_display_orders(project):
    tasks = project.setdefault('tasks', [])
    task_indices = {task.get('id'): index for index, task in enumerate(tasks)}
    sibling_groups = {}
    changed = False
    for task in tasks:
        sibling_groups.setdefault(sibling_key(task), []).append(task)
    for siblings in sibling_groups.values():
        siblings.sort(key=lambda task: (
            task.get('displayOrder', default_task_order(task)),
            task_indices.get(task.get('id'), 0)
        ))
        for index, task in enumerate(siblings, 1):
            display_order = index * 10
            if task.get('displayOrder') != display_order:
                task['displayOrder'] = display_order
                changed = True
    return changed

def ensure_generated_t0_before_t1(project):
    phase = '第三阶段：T0/T1试模'
    roots = [
        task for task in project.get('tasks', [])
        if task.get('phase') == phase and not task.get('parentTask')
    ]
    t0_task = next((
        task for task in roots
        if task.get('name') == 'T0试模' and task.get('generatedMoldTask')
    ), None)
    t1_task = next((task for task in roots if task.get('name') == 'T1试模'), None)
    if not t0_task or not t1_task:
        return False
    t0_order = t0_task.get('displayOrder', default_task_order(t0_task))
    t1_order = t1_task.get('displayOrder', default_task_order(t1_task))
    if t0_order < t1_order:
        return False
    t0_task['displayOrder'] = t1_order - 1
    return True

def ensure_standard_tasks(project):
    tasks = project.setdefault('tasks', [])
    changed = False
    if project.get('processMode') == '预度':
        project['processMode'] = '预镀'
        changed = True
    project.setdefault('processMode', '后镀')
    project.setdefault('productQuantity', '')
    project.setdefault('moldQuantity', '')
    changed = ensure_material_purchase_tasks(project) or changed
    for task in tasks:
        if task.get('name') in ('初始BOM', '正式BOM更新'):
            if 'moldCode' not in task:
                task['moldCode'] = ''
                changed = True
            if 'materialCode' not in task:
                task['materialCode'] = ''
                changed = True
    corrected_trial_order = ensure_generated_t0_before_t1(project)
    # Once a plan has been manually adjusted, deleted or renamed tasks must stay deleted/renamed.
    if project.get('taskPlanCustomized'):
        return ensure_task_display_orders(project) or corrected_trial_order or changed
    existing_keys = {
        (task.get('phase'), task.get('name'), task.get('parentTask', ''))
        for task in tasks
    }
    for task in process_phase2_tasks(
        project.get('startDate'),
        project.get('t0Date'),
        normalize_process_mode(project.get('processMode'))
    ):
        key = (task.get('phase'), task.get('name'), task.get('parentTask', ''))
        if key not in existing_keys:
            tasks.append(task)
            existing_keys.add(key)
            changed = True
    for task in standard_followup_tasks(
        project.get('startDate'),
        project.get('t0Date'),
        project.get('ppapDate'),
        normalize_process_mode(project.get('processMode')),
        project.get('productQuantity'),
        project.get('moldQuantity')
    ):
        key = (task.get('phase'), task.get('name'), task.get('parentTask', ''))
        if key not in existing_keys:
            tasks.append(task)
            existing_keys.add(key)
            changed = True
    return ensure_task_display_orders(project) or corrected_trial_order or changed

def rebuild_t0_mold_plan(project):
    tasks = project.setdefault('tasks', [])
    t0_phase = '第三阶段：T0/T1试模'
    names_to_remove = {'T0试模'}
    removed_ids = set()
    while True:
        found_child = False
        for task in tasks:
            if task.get('phase') != t0_phase or task.get('id') in removed_ids:
                continue
            if task.get('name') in names_to_remove or task.get('parentTask') in names_to_remove:
                removed_ids.add(task.get('id'))
                names_to_remove.add(task.get('name'))
                found_child = True
        if not found_child:
            break
    new_t0_tasks, _ = t0_mold_plan_tasks(
        project.get('startDate'),
        project.get('t0Date'),
        normalize_process_mode(project.get('processMode')),
        project.get('productQuantity'),
        project.get('moldQuantity')
    )
    project['tasks'] = [
        task for task in tasks
        if task.get('id') not in removed_ids
    ] + new_t0_tasks
    project['taskPlanCustomized'] = True
    ensure_generated_t0_before_t1(project)
    ensure_task_display_orders(project)
    return len(removed_ids), new_t0_tasks

# 计算项目进度（基于时间节点）
def calculate_progress(project):
    today = datetime.now().date()
    
    try:
        start_date = datetime.strptime(project['startDate'], '%Y-%m-%d').date()
        t0_date = datetime.strptime(project['t0Date'], '%Y-%m-%d').date()
        ppap_date = datetime.strptime(project['ppapDate'], '%Y-%m-%d').date()
        
        total_days = (ppap_date - start_date).days
        elapsed_days = (today - start_date).days
        
        if elapsed_days <= 0:
            return 0
        elif elapsed_days >= total_days:
            return 100
        else:
            progress = int((elapsed_days / total_days) * 100)
            return min(progress, 100)
    except:
        return project.get('progress', 0)

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return None

def status_from_dates(start_date, end_date):
    today = datetime.now().date()
    start = parse_date(start_date)
    end = parse_date(end_date)
    if start and today < start:
        return '未开始'
    if end and today > end:
        return '已延期'
    if start and end and start <= today <= end:
        return '进行中'
    return '未开始'

def refresh_overdue_statuses(project):
    today = datetime.now().date()
    changed = False
    project_overdue = False

    for task in project.get('tasks', []):
        if task.get('noSchedule'):
            continue
        end_date = parse_date(task.get('endDate'))
        if task.get('manualStatusOverride'):
            continue
        is_overdue = bool(end_date and end_date < today and task.get('status') != '已完成')
        if is_overdue:
            project_overdue = True
            if task.get('status') != '已延期':
                task['status'] = '已延期'
                task['autoOverdue'] = True
                changed = True
        elif task.get('autoOverdue') and task.get('status') == '已延期':
            task['status'] = status_from_dates(task.get('startDate'), task.get('endDate'))
            task.pop('autoOverdue', None)
            changed = True

    t0_date = parse_date(project.get('t0Date'))
    ppap_date = parse_date(project.get('ppapDate'))
    if t0_date and t0_date < today and not is_task_completed(project, {'T0试模'}):
        project_overdue = True
    if ppap_date and ppap_date < today and not is_task_completed(project, {'正式PPAP资料提交'}):
        project_overdue = True

    if project.pop('autoOverdue', None):
        if project.get('status') == '已延期':
            project['status'] = status_from_dates(project.get('startDate'), project.get('ppapDate'))
        changed = True
    project['isOverdue'] = project_overdue

    return changed

# 检查T0节点风险
def is_project_completed(project):
    return project.get('status') == '已完成'

def is_task_completed(project, task_names):
    return any(
        task.get('name') in task_names and task.get('status') == '已完成'
        for task in project.get('tasks', [])
    )

def check_t0_risk(project):
    alerts = []
    today = datetime.now().date()

    if is_project_completed(project) or is_task_completed(project, {'T0试模'}):
        return alerts
    
    if project.get('t0Date'):
        try:
            t0_date = datetime.strptime(project['t0Date'], '%Y-%m-%d').date()
            days_to_t0 = (t0_date - today).days
            
            if days_to_t0 < 0:
                alerts.append({
                    'type': 'error',
                    'message': f'T0已延期 {-days_to_t0} 天',
                    'date': project['t0Date']
                })
            elif days_to_t0 <= 7:
                alerts.append({
                    'type': 'warning',
                    'message': f'T0将在 {days_to_t0} 天后到期',
                    'date': project['t0Date']
                })
        except:
            pass
    
    return alerts

# 检查PPAP节点风险
def check_ppap_risk(project):
    alerts = []
    today = datetime.now().date()

    if is_project_completed(project) or is_task_completed(project, {'正式PPAP资料提交'}):
        return alerts
    
    if project.get('ppapDate'):
        try:
            ppap_date = datetime.strptime(project['ppapDate'], '%Y-%m-%d').date()
            days_to_ppap = (ppap_date - today).days
            
            if days_to_ppap < 0:
                alerts.append({
                    'type': 'error',
                    'message': f'PPAP已延期 {-days_to_ppap} 天',
                    'date': project['ppapDate']
                })
            elif days_to_ppap <= 14:
                alerts.append({
                    'type': 'warning',
                    'message': f'PPAP将在 {days_to_ppap} 天后到期',
                    'date': project['ppapDate']
                })
        except:
            pass
    
    return alerts

# 首页路由
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/collections', methods=['GET'])
def get_collections():
    return jsonify({
        'success': True,
        'data': load_collections()
    })

@app.route('/api/collections', methods=['POST'])
def create_collection():
    import uuid
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'message': '项目集名称不能为空'}), 400
    collections = load_collections()
    if any(item.get('name') == name for item in collections):
        return jsonify({'success': False, 'message': '项目集名称已存在'}), 400
    collection = {
        'id': f"collection-{uuid.uuid4().hex[:8]}",
        'name': name,
        'createdAt': datetime.now().strftime('%Y-%m-%d')
    }
    collections.append(collection)
    if save_collections(collections):
        return jsonify({'success': True, 'data': collection, 'message': '项目集创建成功'}), 201
    return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/collections/<collection_id>', methods=['PUT'])
def update_collection(collection_id):
    data = request.get_json(silent=True) or {}
    collections = load_collections()
    collection = next((item for item in collections if item.get('id') == collection_id), None)
    if not collection:
        return jsonify({'success': False, 'message': '项目集不存在'}), 404
    name = str(data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'message': '项目集名称不能为空'}), 400
    if any(item.get('id') != collection_id and item.get('name') == name for item in collections):
        return jsonify({'success': False, 'message': '项目集名称已存在'}), 400
    collection['name'] = name
    if save_collections(collections):
        return jsonify({'success': True, 'data': collection, 'message': '项目集已更新'})
    return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/collections/<collection_id>', methods=['DELETE'])
def delete_collection(collection_id):
    collections = load_collections()
    if not any(item.get('id') == collection_id for item in collections):
        return jsonify({'success': False, 'message': '项目集不存在'}), 404
    projects = load_projects()
    for project in projects:
        if project.get('collectionId') == collection_id:
            project['collectionId'] = ''
    collections = [item for item in collections if item.get('id') != collection_id]
    if save_collections(collections, projects):
        return jsonify({'success': True, 'message': '项目集已删除，项目已移至未分类'})
    return jsonify({'success': False, 'message': '删除失败'}), 500

# 获取所有项目
@app.route('/api/projects', methods=['GET'])
def get_projects():
    projects = load_projects()
    data_changed = ensure_issue_lists(projects)
    
    # 计算每个项目的进度和风险
    for project in projects:
        data_changed = ensure_standard_tasks(project) or data_changed
        data_changed = sync_completed_parent_descendants(project) or data_changed
        data_changed = refresh_overdue_statuses(project) or data_changed
        # 重新计算进度
        project['progress'] = calculate_progress(project)
        
        # 检查风险
        project['t0Risk'] = check_t0_risk(project)
        project['ppapRisk'] = check_ppap_risk(project)
        
        # 合并所有风险
        all_risks = project['t0Risk'] + project['ppapRisk']
        project['hasError'] = any(r['type'] == 'error' for r in all_risks)
        project['hasWarning'] = any(r['type'] == 'warning' for r in all_risks)
    if data_changed:
        save_projects(projects)
    
    return jsonify({
        'success': True,
        'data': projects,
        'total': len(projects)
    })

# 根据ID获取单个项目
@app.route('/api/projects/<int:project_id>', methods=['GET'])
def get_project(project_id):
    projects = load_projects()
    issues_changed = ensure_issue_lists(projects)
    project = next((p for p in projects if p['id'] == project_id), None)
    
    if project:
        data_changed = ensure_standard_tasks(project) or issues_changed
        data_changed = sync_completed_parent_descendants(project) or data_changed
        data_changed = refresh_overdue_statuses(project) or data_changed
        if data_changed:
            save_projects(projects)
        project['progress'] = calculate_progress(project)
        project['t0Risk'] = check_t0_risk(project)
        project['ppapRisk'] = check_ppap_risk(project)
        
        return jsonify({
            'success': True,
            'data': project
        })
    else:
        return jsonify({
            'success': False,
            'message': '项目不存在'
        }), 404

# 创建新项目
@app.route('/api/projects', methods=['POST'])
def create_project():
    data = request.json
    projects = load_projects()
    
    # 生成所有阶段的任务
    start_date = data.get('startDate')
    t0_date = data.get('t0Date')
    ppap_date = data.get('ppapDate')
    process_mode = normalize_process_mode(data.get('processMode'))
    product_quantity = data.get('productQuantity', '')
    mold_quantity = data.get('moldQuantity', '')
    
    tasks = []
    
    # ========== 第一阶段：立项 ==========
    tasks.extend([
        {
            'id': generate_task_id(),
            'phase': '第一阶段：立项',
            'name': '项目启动会议',
            'startDate': start_date,
            'endDate': start_date,
            'status': '未开始',
            'description': '召开项目启动会议，明确项目目标和范围',
            'isParent': True  # 标记为主任务
        },
        {
            'id': generate_task_id(),
            'phase': '第一阶段：立项',
            'name': '获得客户图纸和标准',
            'startDate': start_date,
            'endDate': start_date,
            'status': '未开始',
            'description': '获取客户发布的正式图纸和技术标准文档',
            'isParent': True  # 标记为主任务
        }
    ])
    
    # ========== 第二阶段：设计与制作 ==========
    
    # 主任务1：模具的设计与制作
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '模具的设计与制作',
        'startDate': start_date,
        'endDate': t0_date,
        'status': '未开始',
        'description': '模具整体设计与制造流程',
        'isParent': True  # 标记为主任务
    })
    
    # 子任务1.1：料带图确认
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '料带图确认',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '确认产品料带设计方案',
        'parentTask': '模具的设计与制作'
    })
    
    # 子任务1.2：模具图纸外发
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '模具图纸外发',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '将模具设计图纸外发给供应商',
        'parentTask': '模具的设计与制作'
    })
    
    # 子任务1.3：模具加工
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '模具加工',
        'startDate': start_date,
        'endDate': t0_date,
        'status': '未开始',
        'description': '模具零部件加工制造',
        'parentTask': '模具的设计与制作'
    })
    
    # 子任务1.4：模具组装
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '模具组装',
        'startDate': start_date,
        'endDate': t0_date,
        'status': '未开始',
        'description': '模具组装调试',
        'parentTask': '模具的设计与制作'
    })
    
    # 主任务2：工装检具的设计制作
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '工装检具的设计制作',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '工装和检具的设计与制作',
        'isParent': True
    })
    
    # 子任务2.1：检具设计
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '检具设计',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '检具方案设计',
        'parentTask': '工装检具的设计制作'
    })
    
    # 子任务2.2：检具外发
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '检具外发',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '检具制作外发',
        'parentTask': '工装检具的设计制作'
    })
    
    # 子任务2.3：生产工序图
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '生产工序图',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '编制生产工序流程图',
        'parentTask': '工装检具的设计制作'
    })
    
    # 子任务2.3.1：料带图
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '料带图',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '料带设计图纸',
        'parentTask': '生产工序图'
    })
    
    # 子任务2.3.2：材料图
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '材料图',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '材料图纸确认',
        'parentTask': '生产工序图'
    })
    
    # 子任务2.3.3：电镀图
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '电镀图',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '电镀工艺图纸',
        'parentTask': '生产工序图'
    })
    
    # 子任务2.3.4：产品图
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '产品图',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '产品最终图纸',
        'parentTask': '生产工序图'
    })
    
    # 子任务2.4：初始BOM（包含模具代码和材料代码）
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '初始BOM',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '编制初始物料清单',
        'parentTask': '工装检具的设计制作',
        'moldCode': '',  # 模具代码
        'materialCode': ''  # 材料代码
    })
    
    # 主任务3：原材料采购
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '原材料采购',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '原材料采购流程',
        'isParent': True
    })
    
    # 子任务3.1：原材料请购
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '原材料请购',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '提交原材料采购申请',
        'parentTask': '原材料采购'
    })
    
    # 子任务3.2：原材料到货
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '原材料到货',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '原材料验收入库',
        'parentTask': '原材料采购'
    })
    for index in range(1, max(to_int(product_quantity), 1) + 1):
        tasks.append(make_material_purchase_task(index, start_date))
    tasks.extend(process_phase2_tasks(start_date, t0_date, process_mode))
    
    # 主任务4：初始PPAP（原特殊特性及其控制方法）
    tasks.append({
        'id': generate_task_id(),
        'phase': '第二阶段：设计与制作',
        'name': '初始PPAP',
        'startDate': start_date,
        'endDate': start_date,
        'status': '未开始',
        'description': '确定产品特殊特性及控制方法',
        'isParent': True
    })

    tasks.extend(standard_followup_tasks(
        start_date,
        t0_date,
        ppap_date,
        process_mode,
        product_quantity,
        mold_quantity
    ))
    
    new_project = {
        'id': generate_id(projects),
        'name': data.get('name'),
        'startDate': start_date,
        't0Date': t0_date,
        'ppapDate': ppap_date,
        'productQuantity': product_quantity,
        'processMode': process_mode,
        'moldQuantity': mold_quantity,
        'customer': data.get('customer', ''),
        'partName': data.get('partName', ''),
        'drawingNumber': data.get('drawingNumber', ''),
        'manager': data.get('manager', ''),
        'collectionId': data.get('collectionId', ''),
        'status': '未开始',
        'progress': 0,
        'createdAt': datetime.now().strftime('%Y-%m-%d'),
        'remarks': data.get('remarks', ''),
        'tasks': tasks,
        'issues': []
    }
    ready_date = apply_preparation_schedule(new_project)
    schedule_warning = preparation_warning(new_project, ready_date)
    
    projects.append(new_project)
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '项目创建成功',
            'data': new_project,
            'scheduleWarning': schedule_warning
        }), 201
    else:
        return jsonify({
            'success': False,
            'message': '保存失败'
        }), 500

# 更新项目
@app.route('/api/projects/<int:project_id>', methods=['PUT'])
def update_project(project_id):
    data = request.json
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)
    
    if not project:
        return jsonify({
            'success': False,
            'message': '项目不存在'
        }), 404
    
    # 记录旧的启动时间
    old_start_date = project.get('startDate')
    new_start_date = data.get('startDate', old_start_date)
    
    # 更新字段
    updatable_fields = ['name', 'startDate', 't0Date', 'ppapDate',
                       'productQuantity', 'processMode', 'moldQuantity',
                       'customer', 'partName', 'drawingNumber', 
                       'manager', 'status', 'remarks', 'collectionId']
    for field in updatable_fields:
        if field in data:
            project[field] = normalize_process_mode(data[field]) if field == 'processMode' else data[field]
    if 'status' in data:
        project.pop('autoOverdue', None)
    ensure_standard_tasks(project)
    refresh_overdue_statuses(project)
    
    # 如果启动时间改变了，同步更新阶段一任务的日期
    if old_start_date != new_start_date and new_start_date:
        tasks = project.get('tasks', [])
        for task in tasks:
            # 只更新阶段一的任务（立项阶段）
            if task.get('phase') == '立项':
                task['startDate'] = new_start_date
                task['endDate'] = new_start_date
    
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '项目更新成功',
            'data': project
        })
    else:
        return jsonify({
            'success': False,
            'message': '保存失败'
        }), 500

@app.route('/api/projects/<int:project_id>/t0-plan/regenerate', methods=['POST'])
def regenerate_t0_plan(project_id):
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)

    if not project:
        return jsonify({
            'success': False,
            'message': '项目不存在'
        }), 404

    removed_count, new_tasks = rebuild_t0_mold_plan(project)
    update_followup_schedule(project)
    project['progress'] = calculate_progress(project)
    project['t0Risk'] = check_t0_risk(project)
    project['ppapRisk'] = check_ppap_risk(project)
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': 'T0试模已按模具数量重新生成',
            'removedCount': removed_count,
            'generatedCount': len(new_tasks),
            'data': project
        })
    return jsonify({
        'success': False,
        'message': '保存失败'
    }), 500

@app.route('/api/projects/<int:project_id>/schedule/regenerate', methods=['POST'])
def regenerate_project_schedule(project_id):
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)

    if not project:
        return jsonify({
            'success': False,
            'message': '项目不存在'
        }), 404

    ready_date = apply_preparation_schedule(project)
    removed_count, new_tasks = rebuild_t0_mold_plan(project)
    update_followup_schedule(project)
    project['progress'] = calculate_progress(project)
    project['t0Risk'] = check_t0_risk(project)
    project['ppapRisk'] = check_ppap_risk(project)
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '已按标准周期重新生成项目计划',
            'removedCount': removed_count,
            'generatedCount': len(new_tasks),
            'scheduleWarning': preparation_warning(project, ready_date),
            'data': project
        })
    return jsonify({
        'success': False,
        'message': '保存失败'
    }), 500

@app.route('/api/issues', methods=['GET'])
def get_issues():
    projects = load_projects()
    if ensure_issue_lists(projects):
        save_projects(projects)
    issues = flatten_issues(projects)
    return jsonify({
        'success': True,
        'data': issues,
        'total': len(issues)
    })

@app.route('/api/projects/<int:project_id>/issues', methods=['POST'])
def create_issue(project_id):
    data = request.get_json(silent=True) or {}
    projects = load_projects()
    ensure_issue_lists(projects)
    project = next((p for p in projects if p['id'] == project_id), None)
    if not project:
        return jsonify({'success': False, 'message': '项目不存在'}), 404
    issue = normalize_issue(data)
    if not issue:
        return jsonify({'success': False, 'message': '问题点描述不能为空'}), 400
    project['issues'].append(issue)
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '问题已新增',
            'data': issue_snapshot(project, issue)
        }), 201
    return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/projects/<int:project_id>/issues/<issue_id>', methods=['PUT'])
def update_issue(project_id, issue_id):
    data = request.get_json(silent=True) or {}
    projects = load_projects()
    ensure_issue_lists(projects)
    project = next((p for p in projects if p['id'] == project_id), None)
    if not project:
        return jsonify({'success': False, 'message': '项目不存在'}), 404
    target = next((item for item in project['issues'] if item.get('id') == issue_id), None)
    if not target:
        return jsonify({'success': False, 'message': '问题不存在'}), 404
    issue = normalize_issue(data, issue_id=issue_id, existing=target)
    if not issue:
        return jsonify({'success': False, 'message': '问题点描述不能为空'}), 400
    project['issues'][project['issues'].index(target)] = issue
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '问题已更新',
            'data': issue_snapshot(project, issue)
        })
    return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/projects/<int:project_id>/issues/<issue_id>', methods=['DELETE'])
def delete_issue(project_id, issue_id):
    projects = load_projects()
    ensure_issue_lists(projects)
    project = next((p for p in projects if p['id'] == project_id), None)
    if not project:
        return jsonify({'success': False, 'message': '项目不存在'}), 404
    original_count = len(project['issues'])
    project['issues'] = [issue for issue in project['issues'] if issue.get('id') != issue_id]
    if len(project['issues']) == original_count:
        return jsonify({'success': False, 'message': '问题不存在'}), 404
    if save_projects(projects):
        return jsonify({'success': True, 'message': '问题已删除'})
    return jsonify({'success': False, 'message': '保存失败'}), 500

@app.route('/api/issues/import', methods=['POST'])
def import_issues():
    data = request.get_json(silent=True) or {}
    imported_rows = data if isinstance(data, list) else data.get('issues')
    if not isinstance(imported_rows, list):
        return jsonify({'success': False, 'message': '导入文件中未找到问题列表'}), 400
    projects = load_projects()
    ensure_issue_lists(projects)
    projects_by_id = {project.get('id'): project for project in projects}
    projects_by_name = {project.get('name'): project for project in projects}
    for project in projects:
        project['issues'] = []
    imported_count = 0
    skipped_count = 0
    used_ids = set()
    for row in imported_rows:
        if not isinstance(row, dict):
            skipped_count += 1
            continue
        project = projects_by_id.get(to_int(row.get('projectId'))) or projects_by_name.get(row.get('projectName'))
        preferred_id = str(row.get('id', '')).strip() or generate_issue_id()
        if preferred_id in used_ids:
            preferred_id = generate_issue_id()
        issue = normalize_issue(row, issue_id=preferred_id)
        if not project or not issue:
            skipped_count += 1
            continue
        used_ids.add(issue['id'])
        project['issues'].append(issue)
        imported_count += 1
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '问题清单导入完成',
            'importedCount': imported_count,
            'skippedCount': skipped_count,
            'data': flatten_issues(projects)
        })
    return jsonify({'success': False, 'message': '保存失败'}), 500

# 删除项目
@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)
    
    if not project:
        return jsonify({
            'success': False,
            'message': '项目不存在'
        }), 404
    
    projects = [p for p in projects if p['id'] != project_id]
    
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '项目删除成功'
        })
    else:
        return jsonify({
            'success': False,
            'message': '删除失败'
        }), 500

# 更新任务状态
@app.route('/api/projects/<int:project_id>/tasks', methods=['POST'])
def create_task(project_id):
    data = request.get_json(silent=True) or {}
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)

    if not project:
        return jsonify({
            'success': False,
            'message': '项目不存在'
        }), 404

    name = str(data.get('name', '')).strip()
    phase = str(data.get('phase', '')).strip()
    start_date = str(data.get('startDate', '')).strip()
    end_date = str(data.get('endDate', '')).strip()
    parent_task = str(data.get('parentTask', '')).strip() or None
    is_material_task = bool(data.get('generatedMaterialTask')) or parent_task == '原材料采购' and name.startswith('买材料数量')
    if not name or not phase or (not is_material_task and (not start_date or not end_date)):
        return jsonify({
            'success': False,
            'message': '任务名称、阶段和日期不能为空'
        }), 400

    if parent_task and not any(
        t.get('name') == parent_task and t.get('phase') == phase
        for t in project.get('tasks', [])
    ):
        return jsonify({
            'success': False,
            'message': '未找到所选父任务'
        }), 400

    if is_material_task:
        material_index = max([
            to_int(task.get('materialIndex'))
            for task in project.get('tasks', [])
            if task.get('parentTask') == '原材料采购' and task.get('generatedMaterialTask')
        ] or [0]) + 1
        task = make_material_purchase_task(material_index, project.get('startDate', ''))
        task['name'] = name or f'买材料数量 - 产品{material_index}'
        task['customTask'] = True
    else:
        task = make_task(
            phase,
            name,
            start_date,
            end_date,
            str(data.get('description', '')).strip(),
            parent_task=parent_task,
            is_parent=bool(data.get('isParent')) and not parent_task,
            extra={'customTask': True}
        )
    status = data.get('status', '未开始')
    if status in ('未开始', '进行中', '已完成', '已延期'):
        task['status'] = status
    ensure_task_display_orders(project)
    tasks = project.setdefault('tasks', [])
    siblings = sorted(
        (candidate for candidate in tasks if sibling_key(candidate) == sibling_key(task)),
        key=lambda candidate: candidate.get('displayOrder', default_task_order(candidate))
    )
    insert_after_id = data.get('insertAfterTaskId', '__end__')
    if insert_after_id == '__end__':
        insert_index = len(siblings)
    elif not insert_after_id:
        insert_index = 0
    else:
        matching_index = next(
            (index for index, candidate in enumerate(siblings) if candidate.get('id') == insert_after_id),
            None
        )
        if matching_index is None:
            return jsonify({
                'success': False,
                'message': '插入位置已不存在，请重新选择'
            }), 400
        insert_index = matching_index + 1
    siblings.insert(insert_index, task)
    for index, sibling in enumerate(siblings, 1):
        sibling['displayOrder'] = index * 10
    tasks.append(task)
    project['taskPlanCustomized'] = True

    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '任务新增成功',
            'data': task
        }), 201
    return jsonify({
        'success': False,
        'message': '保存失败'
    }), 500

@app.route('/api/projects/<int:project_id>/tasks/<task_id>', methods=['PUT'])
def update_task(project_id, task_id):
    data = request.get_json(silent=True) or {}
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)
    
    if not project:
        return jsonify({
            'success': False,
            'message': '项目不存在'
        }), 404
    
    task = next((t for t in project.get('tasks', []) if t['id'] == task_id), None)
    if not task:
        return jsonify({
            'success': False,
            'message': '任务不存在'
        }), 404
    
    old_name = task.get('name')
    # 更新任务字段（支持所有字段）
    updatable_fields = [
        'name', 'description', 'startDate', 'endDate', 'status', 'moldCode', 'materialCode',
        'materialGrade', 'materialWidth', 'materialPitch', 'materialThickness',
        'materialDensity', 'annualQuantity'
    ]
    for field in updatable_fields:
        if field in data:
            task[field] = data[field]
    if task.get('generatedMaterialTask'):
        task['materialWeight'] = calculate_material_weight(task)
    if 'status' in data:
        task.pop('autoOverdue', None)
        task['manualStatusOverride'] = True
        if data.get('status') == '已完成':
            for child in descendant_tasks(project, task.get('name')):
                if child.get('status') != '已完成':
                    child['status'] = '已完成'
                    child.pop('autoOverdue', None)
                    child['manualStatusOverride'] = True
    if 'startDate' in data or 'endDate' in data:
        task.pop('manualStatusOverride', None)
    if task.get('name') != old_name:
        for child in project.get('tasks', []):
            if child.get('phase') == task.get('phase') and child.get('parentTask') == old_name:
                child['parentTask'] = task['name']
    project['taskPlanCustomized'] = True
    
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '任务更新成功',
            'data': task
        })
    else:
        return jsonify({
            'success': False,
            'message': '保存失败'
        }), 500

@app.route('/api/projects/<int:project_id>/tasks/<task_id>', methods=['DELETE'])
def delete_task(project_id, task_id):
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)

    if not project:
        return jsonify({
            'success': False,
            'message': '项目不存在'
        }), 404

    tasks = project.get('tasks', [])
    target = next((t for t in tasks if t.get('id') == task_id), None)
    if not target:
        return jsonify({
            'success': False,
            'message': '任务不存在'
        }), 404

    removed_ids = {task_id}
    parents_to_remove = [(target.get('phase'), target.get('name'))]
    while parents_to_remove:
        parent_phase, parent_name = parents_to_remove.pop()
        for task in tasks:
            if (
                task.get('id') not in removed_ids
                and task.get('phase') == parent_phase
                and task.get('parentTask') == parent_name
            ):
                removed_ids.add(task['id'])
                parents_to_remove.append((task.get('phase'), task.get('name')))

    project['tasks'] = [task for task in tasks if task.get('id') not in removed_ids]
    project['taskPlanCustomized'] = True
    ensure_task_display_orders(project)
    if save_projects(projects):
        return jsonify({
            'success': True,
            'message': '任务删除成功',
            'removedCount': len(removed_ids)
        })
    return jsonify({
        'success': False,
        'message': '删除失败'
    }), 500

if __name__ == '__main__':
    print("=" * 50)
    print("五金件模具排期管理系统启动中...")
    print("访问地址: http://localhost:8000")
    print("=" * 50)
    app.run(debug=False, port=8000, use_reloader=False)
