# hardware/

The physical validation record: what was wired, what was measured, and what the
component actually did. One directory per component, each holding the script or
sketch that was run and a Markdown record of the result.

> These are **bench experiments**, not the product. The firmware the field unit
> flashes is [`firmware/fieldsense_unoq/`](../firmware/fieldsense_unoq/). The Python that talks to the
> hardware at runtime is `fieldsense/hardware/`.

| Directory | Component | Contents |
| :--- | :--- | :--- |
| [`soil-probe/`](soil-probe/) | JXBS 7-in-1 probe | Modbus RTU register sweep and the run that mapped the register addresses |
| [`soil-probe-unoq/`](soil-probe-unoq/) | Probe → MAX485 → UNO Q | The integration that verified the probe end-to-end on the board |
| [`rs485/`](rs485/) | MAX485 transceiver | Separate transmit and receive tests across the differential pair |
| [`gps/`](gps/) | NEO-M8N | Standalone NMEA capture on a PC |
| [`gps-unoq/`](gps-unoq/) | NEO-M8N → UNO Q | The UART integration that gave `Serial1` to the GPS |
| [`tft/`](tft/) | 2.8" ST7789V + XPT2046 | Display-only and display-plus-touch bench sketches |
| [`tft-unoq/`](tft-unoq/) | Panel on the UNO Q | Link probe, frame receiver, touch demo, and the display-only dashboard variant |
| [`unoq-bringup/`](unoq-bringup/) | Arduino UNO Q | First-light UART loopback between the QRB2210 and the STM32 |
| [`legacy/`](legacy/) | — | Superseded one-off scripts, kept because production code cites them |

[`HARDWARE_MASTER_AUDIT.md`](HARDWARE_MASTER_AUDIT.md) is the cross-component
audit that found the D7 pin conflict and the `Serial1` contention between the
GPS and the RS485 bus. It is a dated snapshot; the directory names it lists were
changed afterwards and it carries a mapping table.

## How to read a record

Every record classifies its claims — `DATASHEET`, `PHYSICALLY VERIFIED`,
`MEASURED`, `SOFTWARE VERIFIED`, `ASSUMED`, `PENDING` — so a number sourced from
a datasheet is never mistaken for one that was observed on the bench.

Consolidated specifications live in [`docs/HARDWARE.md`](../docs/HARDWARE.md);
step-by-step procedures live in [`docs/TESTING_GUIDE.md`](../docs/TESTING_GUIDE.md).
