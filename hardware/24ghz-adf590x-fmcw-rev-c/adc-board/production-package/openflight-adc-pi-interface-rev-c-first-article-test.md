# Rev C ADC First-Article Test

Do this before powering the assembled RF board or ordering a larger run.

1. Inspect J1, bottom-side J2, U1, and all DNP locations against the drawings.
2. With power off, verify no short from 5 V to GND or 3.3 V to GND.
3. Verify R6 and R7 each measure about 10 kohm from `CE_RX`/`TX_EN` to GND.
4. Power from a current-limited 5 V bench supply at the Pi 5 V/GND pins with
   the RF cable disconnected. Start at a 100 mA current limit.
5. Confirm 3.3 V at J2 pins 1/17 and the expected ADC internal regulator rails.
6. Connect a Raspberry Pi with RF still disconnected. Confirm U1 responds on
   I2C and `CE_RX`/`TX_EN` remain low during boot.
7. Configure four-channel TDM/I2S and confirm all four ADC channels capture
   injected low-frequency test signals without channel swaps.
8. Power down, connect the specified straight-through RF cable, and continuity
   check every J1 control and baseband pin end to end.
9. Power with TX disabled. Program the RF devices, verify ramp sync, then enable
   RX and TX in controlled steps while monitoring current and rail temperature.

Passing CAD checks does not replace this first-article hardware validation.
