import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADC_DIR = (
    ROOT / "hardware" / "24ghz-adf590x-fmcw-rev-c" / "adc-board"
)
CONTRACT_PATH = ADC_DIR / "adc_interface_contract.py"


def load_contract():
    spec = importlib.util.spec_from_file_location("revc_adc_contract", CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rf_cable_is_straight_through_for_all_30_pins():
    contract = load_contract()

    assert contract.rf_cable_pin_map() == {pin: pin for pin in range(1, 31)}
    assert "-R" not in contract.RF_CABLE_MPN
    assert "-RW" not in contract.RF_CABLE_MPN


def test_rf_header_contract_has_no_missing_pins():
    contract = load_contract()

    assert set(contract.RF_J1_PIN_NETS) == set(range(1, 31))
    assert {
        "SPI_SCLK",
        "SPI_SDATA",
        "SPI_SDO",
        "LE_5901",
        "LE_5904",
        "LE_4159",
        "CE_RX",
        "TX_EN",
        "RAMP_SYNC",
    } <= set(contract.RF_J1_PIN_NETS.values())


def test_pi_header_exposes_every_rf_control_and_adc_interface_signal():
    contract = load_contract()
    required = set(contract.PI_J2_REQUIRED_PIN_NETS.values())

    assert set(contract.RF_ENABLE_NETS) <= required
    assert {
        "SPI_SCLK",
        "SPI_SDATA",
        "SPI_SDO",
        "LE_5901",
        "LE_5904",
        "LE_4159",
        "RAMP_SYNC",
        "I2C_SCL",
        "I2C_SDA",
        "I2S_BCLK",
        "I2S_LRCLK",
        "I2S_DIN",
        "ADC_SHDNZ",
    } <= required


def test_production_connectors_and_layer_order_are_locked():
    contract = load_contract()

    assert contract.RF_HEADER_MPN == "FTSH-115-01-L-DV-K"
    assert contract.PI_SOCKET_MPN == "ESQ-120-58-S-D"
    assert contract.PI_SOCKET_SIDE == "Bottom"
    assert contract.COPPER_LAYER_ORDER == ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
