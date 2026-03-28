# Robot Bridge

This document explains how to connect Aiya to a future physical body without rewriting Aiya core.

## Goal

Keep Aiya as the high-level brain on the PC/server side, and keep the robot/body firmware or controller app as a separate low-level execution layer.

That split lets you:

- change hardware later without breaking the assistant logic
- test with a gamepad, simulator, or desktop mock first
- add camera, IMU, lidar, servos, docking logic, and telemetry gradually

## Recommended Architecture

1. Aiya Core decides what should happen next.
2. Your body-controller program sends sensor/state updates to Aiya.
3. Aiya writes high-level commands into the robot command queue.
4. Your body-controller polls the queue, executes commands, and reports completion.

The body-controller can be:

- a Python desktop app
- a small gateway service on the PC
- a microcontroller companion paired with a PC-side bridge
- a simulator used during development

## Stable API Endpoints

Use these endpoints from your future body program:

- `GET /robot/capabilities`
- `GET /robot/state`
- `PATCH /robot/state`
- `POST /robot/sensors`
- `GET /robot/sensors/recent`
- `POST /robot/commands`
- `GET /robot/commands/next?target=<module>`
- `POST /robot/commands/{id}/complete`

These endpoints are implemented in `main.py`.

## Integration Pattern

### 1. Publish current body state

Use `PATCH /robot/state` for slow-changing shared state, for example:

- current mode
- battery level
- dock status
- active profile
- safety lock

Example:

```json
{
  "profile_name": "fairy-mk1",
  "body_mode": "walking",
  "notes": "Indoor test profile",
  "state_payload": {
    "battery_pct": 82,
    "dock_connected": false,
    "controller_online": true
  }
}
```

### 2. Push sensor snapshots

Use `POST /robot/sensors` for camera summaries, IMU packets, lidar summaries, button states, or telemetry frames.

Example:

```json
{
  "source": "imu_main",
  "sensor_type": "imu",
  "payload": {
    "roll": 0.02,
    "pitch": -0.01,
    "yaw": 1.45,
    "accel": [0.1, 0.0, 9.7]
  }
}
```

For camera input, send metadata or your own perception output first. You do not need raw video transport inside this API unless you want it later.

### 3. Poll commands by module

Split the body into clear targets such as:

- `locomotion`
- `flight`
- `camera_head`
- `left_arm`
- `right_arm`
- `voice`
- `dock`
- `safety`

Then your controller can poll:

`GET /robot/commands/next?target=locomotion`

Example response:

```json
{
  "id": 12,
  "target": "locomotion",
  "command_type": "move",
  "payload": {
    "direction": "forward",
    "speed": 0.25,
    "duration_ms": 800
  }
}
```

### 4. Report completion

After execution, mark the command done:

```json
{
  "status": "completed",
  "result_payload": {
    "distance_cm": 18,
    "safety_stop": false
  }
}
```

Send that to:

`POST /robot/commands/{id}/complete`

## How To Grow This Safely

Start simple:

1. mock controller on the PC
2. gamepad-assisted movement
3. walking only
4. camera summaries
5. IMU + stabilization loop
6. docking and charging logic
7. optional flight mode

## What Should Stay Outside Aiya Core

Do not put these low-level loops directly into Aiya core:

- motor PID
- servo stabilization
- flight control
- sensor fusion
- emergency stop firmware
- battery charging control

Those must stay in the body-controller or embedded firmware. Aiya should send intentions and receive state, not replace the real-time controller.

## Suggested First External Program

For the first version, build a tiny companion app that:

1. reads camera/gamepad/sensor inputs
2. posts summaries to `/robot/sensors`
3. polls `/robot/commands/next`
4. executes mock actions or gamepad output
5. reports `/robot/commands/{id}/complete`

That lets you prototype the future body before buying or wiring all hardware.

## Notes For Future Hardware

- keep transport encrypted if you move beyond localhost
- use a dedicated low-level safety controller
- keep an emergency-stop path outside the LLM
- treat docking, charging, and flight as safety-critical subsystems
- prefer module targets over one giant command endpoint

## Related Files

- `main.py`
- `database.py`
- `init.sql`
- `README.md`
