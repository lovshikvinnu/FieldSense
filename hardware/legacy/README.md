# hardware/legacy/

Superseded scripts, kept because production code still cites them as the
counter-example that explains why it is written the way it is.

| File | Why it is still here |
| :--- | :--- |
| [`push_frame.py`](push_frame.py) | The original open-loop frame blaster: write `0xAA`, sleep 50 ms, then push 153,600 bytes at the STM32 and hope. It shears the image, because the receiver's buffer is far smaller than the burst. `fieldsense/hardware/display_bridge.py` and `hardware/tft-unoq/frame_receiver/frame_receiver.ino` both refer to it by name when explaining why they wait for an acknowledgement instead. |

Nothing here is wired into the pipeline, the tests, or any deployment path.
