# Universal-Audio-Bridge

A small Windows tool that takes audio from a microphone or audio interface (ASIO, WASAPI or MME) and sends it to [VB-CABLE](https://vb-audio.com/Cable/), a virtual audio device. This lets applications that don't support ASIO, such as Counter-Strike, use your interface's microphone as a regular input device.

## Features

- Works with any input device Windows exposes: ASIO, WASAPI, DirectSound and MME
- Channel selection for interfaces with multiple inputs
- Automatic sample rate matching (48 kHz or 44.1 kHz) between the microphone and VB-CABLE
- Adjustable volume with a percentage display
- Segmented level meter (green, yellow, red)
- Resizable window with a dark interface

## Requirements

- Windows 10 or 11
- [VB-CABLE](https://vb-audio.com/Cable/) (free virtual audio driver)
- The ASIO driver of your interface, if you want to use ASIO

## Installation

### Run the EXE

1. Install VB-CABLE and restart Windows.
2. Download `uab.exe` and start it.

## Usage

1. Start the program.
2. Select your microphone or interface under **Input device**.
3. Enter the **Channel** your microphone is connected to. Use `1` for a single-input device.
4. Leave **Output** set to `CABLE Input (VB-Audio Virtual Cable)`.
5. Adjust **Volume** if needed. Keep the level meter in the green area, and avoid the red zone.
6. Click **Start**.
7. In the game, open the audio settings and select **CABLE Output (VB-Audio Virtual Cable)** as the microphone.

In Windows, open the recording settings for **CABLE Output**, go to **Listen**, and make sure **Listen to this device** is turned off. Otherwise you will hear yourself with a delay.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| VB-CABLE not found | Install VB-CABLE and restart Windows. |
| My interface is not listed | Check Device Manager for warnings. Install the manufacturer's driver, or use its WASAPI or MME entry. |
| No common sample rate found | Set the interface and CABLE Output to 48000 Hz in the Windows sound settings. |
| Crackling or dropouts | Close other audio software (DAWs, Discord, OBS) that may use the same device. The program uses a 60 ms prefill buffer for stability. |
| Sound is distorted | Lower the input level on your interface. The meter should stay below the red zone. |
| Game does not show CABLE Output | Restart the game after starting the bridge. |
| Icon does not update in Explorer | Rename the EXE, or restart Windows Explorer. |

## Notes

- Only one application can use an ASIO device at a time. Close your DAW before starting the bridge.
- The bridge adds a small amount of latency, which is normally not noticeable for voice chat.
- Some antivirus programs flag PyInstaller executables as suspicious. If this happens, add an exception for the file.
