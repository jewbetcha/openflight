"""Production interface contract for the Rev C ADC/Raspberry Pi board."""

from __future__ import annotations

RF_HEADER_MPN = "FTSH-115-01-L-DV-K"
RF_CABLE_MPN = "FFSD-15-D-03.00-01-N"
PI_SOCKET_MPN = "ESQ-120-58-S-D"
PI_SOCKET_SIDE = "Bottom"

COPPER_LAYER_ORDER = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")

RF_J1_PIN_NETS = {
    1: "+5V",
    2: "+5V",
    3: "GND",
    4: "GND",
    5: "BB1_P",
    6: "BB1_N",
    7: "GND",
    8: "GND",
    9: "BB2_P",
    10: "BB2_N",
    11: "GND",
    12: "GND",
    13: "BB3_P",
    14: "BB3_N",
    15: "GND",
    16: "GND",
    17: "BB4_P",
    18: "BB4_N",
    19: "GND",
    20: "GND",
    21: "SPI_SCLK",
    22: "SPI_SDATA",
    23: "SPI_SDO",
    24: "GND",
    25: "LE_5901",
    26: "LE_5904",
    27: "LE_4159",
    28: "CE_RX",
    29: "TX_EN",
    30: "RAMP_SYNC",
}

PI_J2_REQUIRED_PIN_NETS = {
    1: "+3V3",
    2: "+5V",
    3: "I2C_SDA",
    4: "+5V",
    5: "I2C_SCL",
    6: "GND",
    9: "GND",
    12: "I2S_BCLK",
    14: "GND",
    16: "ADC_SHDNZ",
    17: "+3V3",
    18: "RAMP_SYNC",
    19: "SPI_SDATA",
    20: "GND",
    21: "SPI_SDO",
    22: "CE_RX",
    23: "SPI_SCLK",
    24: "LE_5901",
    25: "GND",
    26: "LE_5904",
    29: "LE_4159",
    30: "GND",
    34: "GND",
    35: "I2S_LRCLK",
    37: "TX_EN",
    38: "I2S_DIN",
    39: "GND",
}

RF_ENABLE_NETS = ("CE_RX", "TX_EN")
DNP_REFERENCES = {
    "CCP1",
    "CCP2",
    "CCP3",
    "CCP4",
    "CCN1",
    "CCN2",
    "CCN3",
    "CCN4",
    "R5",
}


def rf_cable_pin_map() -> dict[int, int]:
    """Return the only supported straight-through RF cable mapping."""

    return {pin: pin for pin in range(1, 31)}
