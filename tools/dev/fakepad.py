#!/usr/bin/env python3
"""A pretend Xbox controller for testing in a VM (not installed on the stick).

Creates a virtual pad and plays commands written to /tmp/fakepad.fifo:
    tap a            press and release a button (a b x y lb rb start select guide l3 r3)
    hold b 800       hold a button for 800 ms
    dpad right       tap a d-pad direction (up down left right)
    dpadhold down 900
    combo guide a    press two buttons together
    stick rx 20000 800   push a stick axis (x y rx ry) that far for 800 ms
    wait 300
"""
import os, time
import evdev
from evdev import UInput, AbsInfo, ecodes as e

BUTTONS = {"a": e.BTN_SOUTH, "b": e.BTN_EAST, "x": e.BTN_NORTH, "y": e.BTN_WEST, "lb": e.BTN_TL, "rb": e.BTN_TR,
           "select": e.BTN_SELECT, "start": e.BTN_START, "guide": e.BTN_MODE, "l3": e.BTN_THUMBL, "r3": e.BTN_THUMBR}
DPAD = {"left": (e.ABS_HAT0X, -1), "right": (e.ABS_HAT0X, 1), "up": (e.ABS_HAT0Y, -1), "down": (e.ABS_HAT0Y, 1)}
caps = {e.EV_KEY: list(BUTTONS.values()),
        e.EV_ABS: [(a, AbsInfo(0, -32768, 32767, 16, 128, 0)) for a in (e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY)]
                  + [(a, AbsInfo(0, 0, 255, 0, 0, 0)) for a in (e.ABS_Z, e.ABS_RZ)]
                  + [(a, AbsInfo(0, -1, 1, 0, 0, 0)) for a in (e.ABS_HAT0X, e.ABS_HAT0Y)]}
pad = UInput(caps, name="Microsoft X-Box 360 pad", vendor=0x045e, product=0x028e, version=0x110, bustype=e.BUS_USB)
fifo = "/tmp/fakepad.fifo"
import stat
if os.path.exists(fifo) and not stat.S_ISFIFO(os.stat(fifo).st_mode):
    os.unlink(fifo)  # a plain file here would be replayed forever
if not os.path.exists(fifo): os.mkfifo(fifo)
def key(code, value): pad.write(e.EV_KEY, code, value); pad.syn()
def axis(code, value): pad.write(e.EV_ABS, code, value); pad.syn()
print("fakepad ready", flush=True)
while True:
    with open(fifo) as f:
        for line in f:
            p = line.split()
            if not p: continue
            if p[0] == "tap": key(BUTTONS[p[1]], 1); time.sleep(0.06); key(BUTTONS[p[1]], 0)
            elif p[0] == "hold": key(BUTTONS[p[1]], 1); time.sleep(int(p[2]) / 1000); key(BUTTONS[p[1]], 0)
            elif p[0] == "dpad": c, v = DPAD[p[1]]; axis(c, v); time.sleep(0.06); axis(c, 0)
            elif p[0] == "dpadhold": c, v = DPAD[p[1]]; axis(c, v); time.sleep(int(p[2]) / 1000); axis(c, 0)
            elif p[0] == "combo":
                for b in p[1:]: key(BUTTONS[b], 1); time.sleep(0.03)
                time.sleep(0.08)
                for b in reversed(p[1:]): key(BUTTONS[b], 0)
            elif p[0] == "stick":   # stick rx 20000 800: push an axis (x y rx ry) that far for that long
                c = {"x": e.ABS_X, "y": e.ABS_Y, "rx": e.ABS_RX, "ry": e.ABS_RY}[p[1]]
                axis(c, int(p[2])); time.sleep(int(p[3]) / 1000); axis(c, 0)
            elif p[0] == "wait": time.sleep(int(p[1]) / 1000)
            time.sleep(0.09)
