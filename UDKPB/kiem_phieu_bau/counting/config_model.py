"""
Dispatcher cho cac cau hinh kiem phieu.

Moi cau hinh nam trong mot file rieng tai counting/configurations/ de tranh
tron logic cau hinh, validate va tao BallotSelection vao task/view.
"""

from .configurations import config1_resnet18_crossed, config2_resnet18_x, config3_ocr_resnet18_x
from .configurations.base import (
    CONFIG_DEFINITIONS,
    MODEL_RESNET18_CROSSED,
    MODEL_RESNET18_X,
    MODEL_VIETNAMEOCR,
)


CONFIG_MODULES = {
    1: config1_resnet18_crossed,
    2: config2_resnet18_x,
    3: config3_ocr_resnet18_x,
}


def get_supported_config_numbers():
    return sorted(CONFIG_MODULES.keys())


def is_valid_config(config_number):
    return config_number in CONFIG_MODULES


def get_config_definition(config_number):
    return CONFIG_DEFINITIONS.get(config_number, {})


def get_required_services(config_number):
    return get_config_definition(config_number).get('required_services', [])


def apply_config(ai_result, config_number):
    module = CONFIG_MODULES.get(config_number)
    if not module:
        raise ValueError(f'Cau hinh khong hop le: {config_number}')
    return module.apply(ai_result)


def apply_config1(ai_result):
    return apply_config(ai_result, 1)


def apply_config2(ai_result):
    return apply_config(ai_result, 2)


def apply_config3(ai_result):
    return apply_config(ai_result, 3)


def evaluate_ballot_validity(ai_result, config_number):
    module = CONFIG_MODULES.get(config_number)
    if not module:
        raise ValueError(f'Cau hinh khong hop le: {config_number}')
    return module.evaluate_ballot_validity(ai_result)


def create_ballot_selections(ballot, poll, ai_result, config_number):
    module = CONFIG_MODULES.get(config_number)
    if not module:
        raise ValueError(f'Cau hinh khong hop le: {config_number}')
    return module.create_ballot_selections(ballot, poll, ai_result)


def get_config_summary(ai_result):
    rows, cols = ai_result.get_table_dimensions()
    all_models = ai_result.get_all_cell_models()

    models_by_name = {}
    for cell_key, model_name in all_models.items():
        models_by_name.setdefault(model_name, []).append(cell_key)

    return {
        'rows': rows,
        'cols': cols,
        'models_by_name': models_by_name,
        'vietnameocr_cells': models_by_name.get(MODEL_VIETNAMEOCR, []),
        'resnet18_x_cells': models_by_name.get(MODEL_RESNET18_X, []),
        'resnet18_crossed_cells': models_by_name.get(MODEL_RESNET18_CROSSED, []),
        'total_configured': len(all_models)
    }
