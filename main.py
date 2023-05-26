#!/usr/bin/python3

from pynput import mouse, keyboard
import json
import time

# Fix some problems with high DPI screen
import ctypes
PROCESS_PER_MONITOR_DPI_AWARE = 2
ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)


keyboardController = keyboard.Controller()
mouseController = mouse.Controller()

startHotKeyCode = "<ctrl>+<alt>+b"
stopHotKeyCode  = "<ctrl>+<alt>+h"



KEY_PRESS = 0
KEY_RELEASE = 1
MOUSE_MOVE = 2
MOUSE_PRESS = 3
MOUSE_RELEASE = 4
MOUSE_SCROLL = 5


class Action:
    def __init__(self, timestamp : int, type : int, key : keyboard.Key | keyboard.KeyCode = None, x = 0, y = 0, btn : mouse.Button = None) -> None:
        self.type : int = type
        self.key : keyboard.Key | keyboard.KeyCode = key
        self.x : int = x
        self.y : int = y
        self.button : mouse.Button = btn
        self.timestamp : float = timestamp


def serialize_key(key : keyboard.Key | keyboard.KeyCode) -> str | int:
    if isinstance(key, keyboard.Key):
        return key.name
    else:
        return key.vk

def deserialize_key(key : int | str) -> keyboard.Key | keyboard.KeyCode:
    if isinstance(key, str):
        return keyboard.Key[key]
    else:
        return keyboard.KeyCode.from_vk(key)

def serialize_action(action : Action, timestampOffset : float) -> str:
    r = {
        'type': action.type,
        'ts': int((action.timestamp - timestampOffset) * 1_000_000)
    }
    if action.type in [KEY_PRESS, KEY_RELEASE]:
        r['key'] = serialize_key(action.key)
    elif action.type in [MOUSE_RELEASE, MOUSE_PRESS, MOUSE_MOVE, MOUSE_SCROLL]:
        r['x'] = action.x
        r['y'] = action.y
    if action.type in [MOUSE_RELEASE, MOUSE_PRESS]:
        r['btn'] = action.button.name
    return json.dumps(r)

def deserialize_action(data : dict) -> Action:
    return Action(
        data['ts'] / 1_000_000.,
        data['type'],
        deserialize_key(data['key']) if 'key' in data else None,
        data['x'] if 'x' in data else 0,
        data['y'] if 'y' in data else 0,
        mouse.Button[data['btn']] if 'btn' in data else None)

def serialize_actions(actions : list[Action]):
    timestampOffset = actions[0].timestamp
    return '[' + ','.join([serialize_action(a, timestampOffset) for a in actions]) + ']'

def deserialize_actions(s : str):
    data = json.loads(s)
    return [deserialize_action(a) for a in data]


MODE_UNKNOWN = 0
MODE_RECORD = 1
MODE_PLAY = 2


actions : list[Action] = []
recording : bool = False
playing : bool = False
mode : int = MODE_UNKNOWN

nextTimestamp = 0
timeOffset = 0


endSequence : list[Action] = [
    Action(0, KEY_RELEASE, keyboard.Key.alt),
    Action(0, KEY_RELEASE, keyboard.Key.alt_gr),
    Action(0, KEY_RELEASE, keyboard.Key.cmd),
    Action(0, KEY_RELEASE, keyboard.Key.ctrl)
]


def on_move(x : int, y : int):
    global actions
    if recording:
        action = Action(time.time(), MOUSE_MOVE)
        action.x = x
        action.y = y
        actions.append(action)

def on_click(x : int, y : int, button : mouse.Button, pressed : bool):
    global actions
    if recording:
        action = Action(time.time(), MOUSE_PRESS if pressed else MOUSE_RELEASE)
        action.x = x
        action.y = y
        action.button = button
        actions.append(action)

def on_scroll(x : int, y : int, dx : int, dy : int):
    global actions
    if recording:
        action = Action(time.time(), MOUSE_SCROLL)
        action.x = dx
        action.y = dy
        actions.append(action)

def on_press(key : keyboard.Key | keyboard.KeyCode):
    global actions
    startHotKey.press(keyboardListener.canonical(key))
    stopHotKey.press(keyboardListener.canonical(key))
    if recording:
        action = Action(time.time(), KEY_PRESS)
        action.key = key
        actions.append(action)

def on_release(key : keyboard.Key):
    global actions
    startHotKey.release(keyboardListener.canonical(key))
    stopHotKey.release(keyboardListener.canonical(key))
    if recording:
        action = Action(time.time(), KEY_RELEASE)
        action.key = key
        actions.append(action)


def input_bool(q):
    return input(q).lower()[:1] not in ['n', '0', 'f']

def input_int(q):
    while True:
        try:
            return int(input(q))
        except ValueError:
            print("Invalid integer")


def on_start():
    global recording, playing, actions, nextTimestamp, timeOffset
    if mode == MODE_RECORD:
        print("Start recording")
        recording = True
        actions.clear()
    else:
        if actions is not None and len(actions) > 0:
            print("Start playing")
            nextTimestamp = time.time()
            timeOffset = nextTimestamp - actions[0].timestamp
            playing = True



def on_stop():
    global recording, playing, mode

    if mode == MODE_RECORD:
        print("Stop recording")
        recording = False
        actions.extend(endSequence)
        if input_bool("Save this record?: "):
            with open('data.json', 'w') as f:
                f.write(serialize_actions(actions))
            print("Record saved")

    elif mode == MODE_PLAY:
        print("Stop playing")
        playing = False

    mode = MODE_UNKNOWN


def play_user_action(action : Action):
    if action.type == MOUSE_MOVE:
        mouseController.move(action.x - mouseController.position[0], action.y - mouseController.position[1])
    elif action.type == MOUSE_PRESS:
        mouseController.move(action.x - mouseController.position[0], action.y - mouseController.position[1])
        mouseController.press(action.button)
    elif action.type == MOUSE_RELEASE:
        mouseController.move(action.x - mouseController.position[0], action.y - mouseController.position[1])
        mouseController.release(action.button)
    elif action.type == MOUSE_SCROLL:
        mouseController.scroll(action.x, action.y)
    elif action.type == KEY_PRESS:
        keyboardController.press(action.key)
    elif action.type == KEY_RELEASE:
        keyboardController.release(action.key)
    else:
        raise Exception("Unknow action type : " + action.type)


def play_loop():
    global mode, actions, nextTimestamp, timeOffset, playing
    mode = MODE_PLAY

    with open('data.json', 'r') as f:
        actions = deserialize_actions(f.read())
    if len(actions) == 0:
        print("Can't load empty record")
        return
    print("Record loaded")

    currentEventIndex = 0
    playEndTime = time.time() + (60 * 60 * 7) # 7 hour max

    while mode == MODE_PLAY and time.time() < playEndTime:
        if playing:
            currentTime = time.time()
            while nextTimestamp < currentTime:
                play_user_action(actions[currentEventIndex])
                currentEventIndex += 1
                if currentEventIndex >= len(actions):
                    currentEventIndex = 0
                    nextTimestamp = time.time() + 1
                    timeOffset = nextTimestamp - actions[0].timestamp
                    print("Restart playing")
                    break
                else:
                    nextTimestamp = actions[currentEventIndex].timestamp + timeOffset
                currentTime = time.time()
            time.sleep(min(1 / 500, nextTimestamp - currentTime))
        else:
            time.sleep(1 / 500)

    mode = MODE_UNKNOWN
    playing = False


def record_loop():
    global mode, recording
    mode = MODE_RECORD

    while mode == MODE_RECORD:
        time.sleep(1 / 500)

    mode = MODE_UNKNOWN
    recording = False


startHotKey = keyboard.HotKey(keyboard.HotKey.parse(startHotKeyCode), on_start)
stopHotKey  = keyboard.HotKey(keyboard.HotKey.parse(stopHotKeyCode),  on_stop)

mouseListener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
keyboardListener = keyboard.Listener(on_press=on_press, on_release=on_release)


if __name__ == "__main__":
    mouseListener.start()
    keyboardListener.start()

    while True:
        print()
        print("What do you want to do ?")
        print("  1 : Play a record")
        print("  2 : Create a new record")
        print("  3 : Quit")
        r = int(input("> "))

        if r == 2:
            print("Press %s to start and %s to stop recoring" % (startHotKeyCode, stopHotKeyCode))
            record_loop()

        elif r == 1:
            print("Press %s to start and %s to stop playing" % (startHotKeyCode, stopHotKeyCode))
            play_loop()

        elif r == 3:
            print("Good by!")
            break

        else:
            print("Invalid response")
