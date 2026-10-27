from ctypes import *

import bacon
from bacon.core import lib
from bacon import native

ControllerProfiles = native.ControllerProfiles
ControllerButtons = native.ControllerButtons
ControllerAxes = native.ControllerAxes

def _get_controller_property_string(controller_index, property):
    buffer = create_string_buffer(256)
    length = c_int(sizeof(buffer))
    try:
        lib.GetControllerPropertyString(controller_index, property, buffer, byref(length))
    except:
        return None
    return buffer.value.decode('utf-8')

def _get_controller_property_int(controller_index, property):
    value = c_int()
    try:
        lib.GetControllerPropertyInt(controller_index, property, byref(value))
    except:
        return None
    return value.value
    
class Controller(object):
    

    def __init__(self, controller_index):
        self._controller_index = controller_index
        
        # Controller state
        self._buttons = 0
        self._axes = {}

        # Controller properties
        self._supported_axes_mask = _get_controller_property_int(controller_index, native.ControllerProperties.supported_axes_mask)
        self._supported_buttons_mask = _get_controller_property_int(controller_index, native.ControllerProperties.supported_buttons_mask)

        for bit in range(16):
            self._axes[1 << bit] = 0.0

        #: A numeric vendor ID that can be used to identify the type of device, when combined with the :attr:`product_id`.
        self.vendor_id = _get_controller_property_int(controller_index, native.ControllerProperties.vendor_id)

        #: A numeric product ID that can be used to identify the type of device, when combined with the :attr:`vendor_id`.
        self.product_id = _get_controller_property_int(controller_index, native.ControllerProperties.product_id)

        #: A human-readable name of the device that can be used to identify it to the user.
        self.name = _get_controller_property_string(controller_index, native.ControllerProperties.name)

        #: The supported profile of the device, a member of the enumeration :class:`GameControllerProfiles`.  Game controllers
        #: with the ``generic`` profile do not provide semantic meanings to any of the buttons or axes, and must usually be configured
        #: by the player unless the device type is known by the game.
        #:
        #: The ``standard`` profile describes a game controller with no analogue sticks or triggers.
        #:
        #: The ``extended`` profile describes a game controller with a layout compatible with an Xbox 360 controller.
        #:
        #: For a game controller to appear in the ``standard`` or ``extended`` profiles, it must have been discovered by a
        #: suitable SDK on the host platform: on Windows, this is XInput, which only supports the Xbox 360 controller.  On
        #: OS X and iOS, this is the GameController SDK, which supports a limited range of new devices.
        self.profile = _get_controller_property_int(controller_index, native.ControllerProperties.profile)

        self.mapping = ControllerMapping.get(self)
        if self.mapping:
            self.profile = self.mapping.profile

    @property
    def controller_index(self):
        
        return self._controller_index

    def has_axis(self, axis):
        
        return (axis & self._supported_axes_mask) != 0

    def get_axis(self, axis):
        
        try:
            return self._axes[axis]
        except KeyError:
            return 0.0

    def has_button(self, button):
        
        return (button & self._supported_buttons_mask) != 0

    def get_button_state(self, button):
        
        return (button & self._buttons) != 0

    @property
    def connected(self):
        
        return self._controller_index is not None

    # Axes

    @property
    def left_thumb_x(self):
        
        return self.get_axis(ControllerAxes.left_thumb_x)

    @property
    def left_thumb_y(self):
        
        return self.get_axis(ControllerAxes.left_thumb_y)

    @property
    def right_thumb_x(self):
        
        return self.get_axis(ControllerAxes.right_thumb_x)

    @property
    def right_thumb_y(self):
        
        return self.get_axis(ControllerAxes.right_thumb_y)

    @property
    def left_trigger(self):
        
        return self.get_axis(ControllerAxes.left_trigger)

    @property
    def right_trigger(self):
        
        return self.get_axis(ControllerAxes.right_trigger)

    # Buttons

    @property
    def start(self):
        
        return self._buttons & ControllerButtons.start

    @property
    def back(self):
        
        return self._buttons & ControllerButtons.back

    @property
    def select(self):
        
        return self._buttons & ControllerButtons.select

    @property
    def action_up(self):
        
        return self._buttons & ControllerButtons.action_up

    @property
    def action_down(self):
        
        return self._buttons & ControllerButtons.action_down

    @property
    def action_left(self):
        
        return self._buttons & ControllerButtons.action_left

    @property
    def action_right(self):
        
        return self._buttons & ControllerButtons.action_right

    @property
    def dpad_up(self):
        
        return self._buttons & ControllerButtons.dpad_up

    @property
    def dpad_down(self):
        
        return self._buttons & ControllerButtons.dpad_down

    @property
    def dpad_left(self):
        
        return self._buttons & ControllerButtons.dpad_left

    @property
    def dpad_right(self):
        
        return self._buttons & ControllerButtons.dpad_right

    @property
    def left_shoulder(self):
        
        return self._buttons & ControllerButtons.left_shoulder

    @property
    def right_shoulder(self):
        
        return self._buttons & ControllerButtons.right_shoulder

    @property
    def left_thumb(self):
        
        return self._buttons & ControllerButtons.left_thumb

    @property
    def right_thumb(self):
        
        return self._buttons & ControllerButtons.right_thumb

class ControllerMapping(object):
    

    # Registry of (vendor_id, product_id) tuples to ControllerMapping
    _registry = {}

    @classmethod
    def register(cls, vendor_id, product_id, mapping):
        
        cls._registry[(vendor_id, product_id)] = mapping

    @classmethod
    def get(cls, controller):
        
        try:
            return cls._registry[(controller.vendor_id, controller.product_id)]
        except KeyError:
            return None

    def __init__(self, buttons={}, axes={}, dead_zones={}, profile=ControllerProfiles.generic):
        self.buttons = {}
        for k, v in buttons.items():
            k = ControllerButtons.parse(k)
            v = ControllerButtons.parse(v)
            self.buttons[k] = v
        self.axes = {}
        for k, v in axes.items():
            k = ControllerAxes.parse(k)
            v = ControllerAxes.parse(v)
            self.axes[k] = v
        self.dead_zones = {}
        for k, v in dead_zones.items():
            k = ControllerAxes.parse(k)
            self.dead_zones[k] = float(v)
        self.profile = ControllerProfiles.parse(profile)

# Map controller index to controller
_controllers = {}

def _controller_connected_event_handler(controller_index, connected):
    # Invalidate any existing controller with the same index
    controller = None
    try:
        controller = _controllers[controller_index]
        controller._controller_index = None
    except KeyError:
        pass

    if connected:
        _controllers[controller_index] = controller = Controller(controller_index)
        bacon._current_game.on_controller_connected(controller)
    else:
        del _controllers[controller_index]
        bacon._current_game.on_controller_disconnected(controller)
        
def _controller_button_event_handler(controller_index, button, pressed):
    try:
        controller = _controllers[controller_index]
    except KeyError:
        return

    if controller.mapping:
        try:
            button = controller.mapping.buttons[button]
        except KeyError:
            pass

    if pressed:
        controller._buttons |= button
    else:
        controller._buttons &= ~button

    bacon._current_game.on_controller_button(controller, button, pressed)

def _controller_axis_event_handler(controller_index, axis, value):    
    try:
        controller = _controllers[controller_index]
    except KeyError:
        return

    if controller.mapping:
        try:
            axis = controller.mapping.axes[axis]
        except KeyError:
            pass

        try:
            dead_zone = controller.mapping.dead_zones[axis]
            if value < -dead_zone:
                value = (value + dead_zone) / (1.0 - dead_zone)
            elif value > dead_zone:
                value = (value - dead_zone) / (1.0 - dead_zone)
            else:
                value = 0.0
            
        except KeyError:
            pass

    if controller._axes[axis] != value:
        controller._axes[axis] = value
        bacon._current_game.on_controller_axis(controller, axis, value)