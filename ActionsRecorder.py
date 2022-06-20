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


def serializeKey(key : keyboard.Key | keyboard.KeyCode) -> str | int:
    if isinstance(key, keyboard.Key):
        return key.name
    else:
        return key.vk

def deserializeKey(key : int | str) -> keyboard.Key | keyboard.KeyCode:
    if isinstance(key, str):
        return keyboard.Key[key]
    else:
        return keyboard.KeyCode.from_vk(key)

def serializeAction(action : Action, timestampOffset : float) -> str:
    r = {
        'type': action.type,
        'ts': int((action.timestamp - timestampOffset) * 1_000_000)
    }
    if action.type in [KEY_PRESS, KEY_RELEASE]:
        r['key'] = serializeKey(action.key)
    elif action.type in [MOUSE_RELEASE, MOUSE_PRESS, MOUSE_MOVE, MOUSE_SCROLL]:
        r['x'] = action.x
        r['y'] = action.y
    if action.type in [MOUSE_RELEASE, MOUSE_PRESS]:
        r['btn'] = action.button.name
    return json.dumps(r)

def deserializeAction(data : dict) -> Action:
    return Action(
        data['ts'] / 1_000_000.,
        data['type'],
        deserializeKey(data['key']) if 'key' in data else None,
        data['x'] if 'x' in data else 0,
        data['y'] if 'y' in data else 0,
        mouse.Button[data['btn']] if 'btn' in data else None)

def serializeActions(actions : list[Action]):
    timestampOffset = actions[0].timestamp
    return '[' + ','.join([serializeAction(a, timestampOffset) for a in actions]) + ']'

def deserializeActions(s : str):
    data = json.loads(s)
    return [deserializeAction(a) for a in data]


# Recorded data
actions : list[Action] = []
recording : bool = False
recorded : bool = False
playing : bool = False
finish : bool = False

endSequence : list[Action] = [
    Action(0, KEY_RELEASE, keyboard.Key.alt),
    Action(0, KEY_RELEASE, keyboard.Key.alt_gr),
    Action(0, KEY_RELEASE, keyboard.Key.cmd),
    Action(0, KEY_RELEASE, keyboard.Key.ctrl)
]


def on_move(x : int, y : int):
    global recording, recorded, playing, finish
    if recording:
        action = Action(time.time(), MOUSE_MOVE)
        action.x = x
        action.y = y
        actions.append(action)

def on_click(x : int, y : int, button : mouse.Button, pressed : bool):
    global recording, recorded, playing, finish
    if recording:
        action = Action(time.time(), MOUSE_PRESS if pressed else MOUSE_RELEASE)
        action.x = x
        action.y = y
        action.button = button
        actions.append(action)

def on_scroll(x : int, y : int, dx : int, dy : int):
    global recording, recorded, playing, finish
    if recording:
        action = Action(time.time(), MOUSE_SCROLL)
        action.x = dx
        action.y = dy
        actions.append(action)

def on_press(key : keyboard.Key | keyboard.KeyCode):
    global recording, recorded, playing, finish
    startHotKey.press(keyboardListener.canonical(key))
    stopHotKey.press(keyboardListener.canonical(key))
    if recording:
        action = Action(time.time(), KEY_PRESS)
        action.key = key
        actions.append(action)

def on_release(key : keyboard.Key):
    global recording, recorded, playing, finish
    startHotKey.release(keyboardListener.canonical(key))
    stopHotKey.release(keyboardListener.canonical(key))
    if recording:
        action = Action(time.time(), KEY_RELEASE)
        action.key = key
        actions.append(action)

def on_start():
    global recording, recorded, playing, finish, actions
    if not recorded:
        if bool(input("Read from file?: ")):
            with open('data.json', 'r') as f:
                actions = deserializeActions(f.read())
            recorded = True
            print("File readed and actions loaded")
        else:
            recording = True
            actions.clear()
            print("Start recording")
    else:
        playing = True
        print("Start playing")

def on_stop():
    global recording, recorded, playing, finish
    if not recorded:
        recording = False
        recorded = True
        actions.extend(endSequence)
        print("Stop recording")
        if bool(input("Write to a file?: ")):
            with open('data.json', 'w') as f:
                f.write(serializeActions(actions))
        print("File writed and actions saved")
    elif playing:
        playing = False
        print("Stop playing")
    else:
        # Stop has been pressed two time so exit
        print("Exit")
        finish = True
        mouseListener.stop()
        keyboardListener.stop()


def playUserAction(action : Action):
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


startHotKey = keyboard.HotKey(keyboard.HotKey.parse(startHotKeyCode), on_start)
stopHotKey  = keyboard.HotKey(keyboard.HotKey.parse(stopHotKeyCode),  on_stop)

mouseListener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
keyboardListener = keyboard.Listener(on_press=on_press, on_release=on_release)

mouseListener.start()
keyboardListener.start()


lastPlaying = False
timeOffset = 0
nextTimestamp = 0
currentEventIndex = 0

while not finish:
    if not lastPlaying and playing:
        # Start playing
        lastPlaying = True
        currentEventIndex = 0
        nextTimestamp = 0
        timeOffset = time.time() - actions[0].timestamp
    
    if playing:
        currentTime = time.time()
        if currentTime > nextTimestamp:
            playUserAction(actions[currentEventIndex])
            currentEventIndex += 1
            if currentEventIndex >= len(actions):
                currentEventIndex = 0
                nextTimestamp = time.time() + 1
                timeOffset = time.time() - actions[0].timestamp
                print("Restart playing")
            else:
                nextTimestamp = actions[currentEventIndex].timestamp + timeOffset

    time.sleep(1. / 10_000)
