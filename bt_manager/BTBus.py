from __future__ import unicode_literals

import dbus
import dbus.service
import types
import pprint


def translate_to_dbus_type(typeof, value):
    """Helper function to map values from their native Python types
    to Dbus types"""
    if ((isinstance(value, types.UnicodeType) or
         isinstance(value, str)) and typeof is not dbus.String):
        # FIXME: This is potentially dangerous since it evaluates
        # a string in-situ
        return typeof(eval(value))
    else:
        return typeof(value)


class BTRejectedException(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class BTSignalNameNotRecognisedException:
    """Exception raised for when a signal name is not recognized.
    Check the originating class for a list of supported signal names"""
    pass


class BTDeviceNotSpecifiedException:
    """Exception raised for when a device is not specified"""
    pass


class Signal():
    def __init__(self, signal, user_callback, user_arg):
        self.signal = signal
        self.user_callback = user_callback
        self.user_arg = user_arg

    def signal_handler(self, *args):
        self.user_callback(self.signal, self.user_arg, *args)


class BTInterface:
    """Wrapper around DBus to encapsulated a BT interface
    entry point e.g., an adapter, a device, etc"""

    SIGNAL_PROPERTY_CHANGED = 'PropertyChanged'

    def __init__(self, path, addr):
        self._dbus_addr = addr
        self._signals = {}
        self._signal_names = []
        self._bus = dbus.SystemBus()
        self._object = self._bus.get_object('org.bluez', path)
        self._interface = dbus.Interface(self._object, addr)
        self._properties = self._interface.GetProperties().keys()
        self._register_signal_name(BTInterface.SIGNAL_PROPERTY_CHANGED)

    def _register_signal_name(self, name):
        self._signal_names.append(name)

    def add_signal_receiver(self, callback_fn, signal, user_arg):
        """Add a signal receiver callback with user argument"""
        if (signal in self._signal_names):
            s = Signal(signal, callback_fn, user_arg)
            self._signals[signal] = s
            self._bus.add_signal_receiver(s.signal_handler,
                                          signal,
                                          dbus_interface=self._dbus_addr)
        else:
            raise BTSignalNameNotRecognisedException

    def remove_signal_receiver(self, signal):
        """Remove an installed signal receiver by signal name"""
        if (signal in self._signal_names):
            s = self._signals.get(signal)
            if (s):
                self._bus.remove_signal_receiver(s.signal_handler,
                                                 signal,
                                                 dbus_interface=self._dbus_addr)  # noqa
                self._signals.pop(signal)
        else:
            raise BTSignalNameNotRecognisedException

    def get_property(self, name):
        """Helper to get a property value by name"""
        return self._interface.GetProperties()[name]

    def set_property(self, name, value):
        """Helper to set a property value by name, translating to correct
        DBus type"""
        typeof = type(self.get_property(name))
        self._interface.SetProperty(name,
                                    translate_to_dbus_type(typeof, value))

    def __getattr__(self, name):
        """Override default getattr behaviours to allow DBus object
        properties to be exposed in the class for getting"""
        if name in self.__dict__:
            return self.__dict__[name]
        elif '_properties' in self.__dict__ and name in self._properties:
            return self.get_property(name)

    def __setattr__(self, name, value):
        """Override default setattr behaviours to allow DBus object
        properties to be exposed in the class for setting"""
        if '_properties' in self.__dict__ and name not in self.__dict__:
            self.set_property(name, value)
        else:
            self.__dict__[name] = value

    def __repr__(self):
        """Stringify the Dbus interface properties as raw"""
        return pprint.pformat(self._interface.GetProperties())

    def __str__(self):
        """Stringify the Dbus interface properties in a nice format"""
        return pprint.pformat(self._interface.GetProperties())


class BTManager(BTInterface):
    """Wrapper around Dbus to encapsulate the BT manager entity"""

    SIGNAL_ADAPTER_ADDED = 'AdapterAdded'
    SIGNAL_ADAPTER_REMOVED = 'AdapterRemoved'
    SIGNAL_DEFAULT_ADAPTER_CHANGED = 'DefaultAdapterChanged'

    def __init__(self):
        BTInterface.__init__(self, '/', 'org.bluez.Manager')
        self._register_signal_name(BTManager.SIGNAL_ADAPTER_ADDED)
        self._register_signal_name(BTManager.SIGNAL_ADAPTER_REMOVED)
        self._register_signal_name(BTManager.SIGNAL_DEFAULT_ADAPTER_CHANGED)

    def default_adapter(self):
        """Obtain the default BT adapter object path"""
        return self._interface.DefaultAdapter()

    def find_adapter(self, dev_id):
        """Find a BT adapter by its MAC address e.g., 11:22:33:44:55:66"""
        return self._interface.FindAdapter(dev_id)

    def list_adapters(self):
        """List all attached BT adapters"""
        return self._interface.ListAdapters()


class BTAdapter(BTInterface):
    """Wrapper around Dbus to encapsulate the BT adapter entity"""

    SIGNAL_DEVICE_FOUND = 'DeviceFound'
    SIGNAL_DEVICE_REMOVED = 'DeviceRemoved'
    SIGNAL_DEVICE_CREATED = 'DeviceCreated'
    SIGNAL_DEVICE_DISAPPEARED = 'DeviceDisappeared'

    def __init__(self, adapter_id=None):
        manager = BTManager()
        if (adapter_id is None):
            adapter_path = manager.default_adapter()
        else:
            adapter_path = manager.find_adapter(adapter_id)
        BTInterface.__init__(self, adapter_path, 'org.bluez.Adapter')
        self._register_signal_name(BTAdapter.SIGNAL_DEVICE_FOUND)
        self._register_signal_name(BTAdapter.SIGNAL_DEVICE_REMOVED)
        self._register_signal_name(BTAdapter.SIGNAL_DEVICE_CREATED)
        self._register_signal_name(BTAdapter.SIGNAL_DEVICE_DISAPPEARED)
        self._register_signal_name(BTAdapter.SIGNAL_PROPERTY_CHANGED)

    def start_discovery(self):
        """Start device discovery which will signal
        events on installed notifiers"""
        return self._interface.StartDiscovery()

    def stop_discovery(self):
        """Stop a previously started device discovery"""
        return self._interface.StopDiscovery()

    def find_device(self, dev_id):
        """Find a device by its MAC address e.g., 11:22:33:44:55:66"""
        return self._interface.FindDevice(dev_id)

    def list_devices(self):
        """List all registered BT devices by their DBus object path"""
        return self._interface.ListDevices()

    def create_paired_device(self, dev_id, agent_path,
                             caps, cb_notify_device, cb_notify_error):
        """Create a new paired device entry for this adapter by
        device MAC address using the provided agent path"""
        return self._interface.CreatePairedDevice(dev_id,
                                                  agent_path,
                                                  caps,
                                                  reply_handler=cb_notify_device,  # noqa
                                                  error_handler=cb_notify_error)   # noqa

    def remove_device(self, dev_path):
        """Remove an existing paired device entry on this adapter
        by device path"""
        self._interface.RemoveDevice(dev_path)

    def register_agent(self, path, caps):
        """Register a pairing agent on this adapter"""
        self._interface.RegisterAgent(path, caps)

    def unregister_agent(self, path):
        """Unregister a pairing agent on this adapter"""
        self._interface.UnregisterAgent(path)


class BTGenericDevice(BTInterface):
    """Generic BT device which has its own interface bus address but is
    associated with a BT adapter"""
    def __init__(self, addr, adapter_id=None, dev_path=None, dev_id=None):
        if (dev_path):
            path = dev_path
        elif (dev_id):
            if (adapter_id):
                adapter = BTAdapter(adapter_id)
            else:
                adapter = BTAdapter()
            path = adapter.find_device(dev_id)
        else:
            raise BTDeviceNotSpecifiedException
        BTInterface.__init__(self, path, addr)


class BTDevice(BTGenericDevice):
    """Wrapper around Dbus to encapsulate the BT device entity"""

    SIGNAL_DISCONNECT_REQUESTED = 'DisconnectRequested'

    def __init__(self, *args, **kwargs):
        BTGenericDevice.__init__(self, addr='org.bluez.Device',
                                 *args, **kwargs)
        self._register_signal_name(BTDevice.SIGNAL_DISCONNECT_REQUESTED)

    def discover_services(self, pattern=''):
        return self._interface.DiscoverServices(pattern)

    def disconnect(self):
        self._interface.Disconnect()


class BTAudioSink(BTGenericDevice):
    """Wrapper around Dbus to encapsulate the BT audio sink entity"""

    SIGNAL_CONNECTED = 'Connected'
    SIGNAL_DISCONNECTED = 'Disconnected'
    SIGNAL_PLAYING = 'Playing'
    SIGNAL_STOPPED = 'Stopped'

    def __init__(self, *args, **kwargs):
        BTGenericDevice.__init__(self, addr='org.bluez.AudioSink',
                                 *args, **kwargs)
        self._register_signal_name(BTAudioSink.SIGNAL_CONNECTED)
        self._register_signal_name(BTAudioSink.SIGNAL_DISCONNECTED)
        self._register_signal_name(BTAudioSink.SIGNAL_PLAYING)
        self._register_signal_name(BTAudioSink.SIGNAL_STOPPED)

    def connect(self):
        self._interface.Connect()

    def is_connected(self):
        return self._interface.IsConnected()

    def disconnect(self):
        self._interface.Disconnect()


class BTControl(BTGenericDevice):
    """Wrapper around Dbus to encapsulate the BT control entity"""

    SIGNAL_CONNECTED = 'Connected'
    SIGNAL_DISCONNECTED = 'Disconnected'

    def __init__(self, *args, **kwargs):
        BTGenericDevice.__init__(self, addr='org.bluez.Control',
                                 *args, **kwargs)
        self._register_signal_name(BTControl.SIGNAL_CONNECTED)
        self._register_signal_name(BTControl.SIGNAL_DISCONNECTED)

    def is_connected(self):
        return self._interface.IsConnected()

    def volume_up(self):
        self._interface.VolumeUp()

    def volume_down(self):
        self._interface.VolumeDown()


class BTAgent(dbus.service.Object):
    """Simple BT device pairing agent"""

    NOTIFY_ON_RELEASE = 'Release'
    NOTIFY_ON_AUTHORIZE = 'Authorize'
    NOTIFY_ON_REQUEST_PIN_CODE = 'RequestPinCode'
    NOTIFY_ON_REQUEST_PASS_KEY = 'RequestPasskey'
    NOTIFY_ON_DISPLAY_PASS_KEY = 'DisplayPasskey'
    NOTIFY_ON_REQUEST_CONFIRMATION = 'RequestConfirmation'
    NOTIFY_ON_CONFIRM_MODE_CHANGE = 'ConfirmModeChange'
    NOTIFY_ON_CANCEL = 'Cancel'

    def __init__(self,
                 path='/test/agent',
                 auto_authorize_connections=True,
                 default_pin_code='0000',
                 default_pass_key=0,   # Range: 0-999999
                 cb_notify_on_release=None,
                 cb_notify_on_authorize=None,
                 cb_notify_on_request_pin_code=None,
                 cb_notify_on_request_pass_key=None,
                 cb_notify_on_display_pass_key=None,
                 cb_notify_on_request_confirmation=None,
                 cb_notify_on_confirm_mode_change=None,
                 cb_notify_on_cancel=None):

        self.auto_authorize_connections = auto_authorize_connections
        self.default_pin_code = default_pin_code
        self.default_pass_key = default_pass_key
        self.cb_notify_on_release = cb_notify_on_release
        self.cb_notify_on_authorize = cb_notify_on_authorize
        self.cb_notify_on_request_pin_code = cb_notify_on_request_pin_code
        self.cb_notify_on_request_pass_key = cb_notify_on_request_pass_key
        self.cb_notify_on_display_pass_key = cb_notify_on_display_pass_key
        self.cb_notify_on_request_confirmation = \
            cb_notify_on_request_confirmation
        self.cb_notify_on_confirm_mode_change = \
            cb_notify_on_confirm_mode_change
        self.cb_notify_on_cancel = cb_notify_on_cancel
        bus = dbus.SystemBus()
        super(BTAgent, self).__init__(bus, path)

    @dbus.service.method("org.bluez.Agent", in_signature="", out_signature="")
    def Release(self):
        if (self.cb_notify_on_release):
            self.cb_notify_on_release(BTAgent.NOTIFY_ON_RELEASE)

    @dbus.service.method("org.bluez.Agent", in_signature="os",
                         out_signature="")
    def Authorize(self, device, uuid):
        if (self.cb_notify_on_authorize):
            if (not self.cb_notify_on_authorize(BTAgent.NOTIFY_ON_AUTHORIZE,
                                                device,
                                                uuid)):
                raise BTRejectedException('Connection not authorized by user')
        elif (not self.auto_authorize_connections):
            raise BTRejectedException('Auto authorize is off')

    @dbus.service.method("org.bluez.Agent", in_signature="o",
                         out_signature="s")
    def RequestPinCode(self, device):
        if (self.cb_notify_on_request_pin_code):
            pin_code = self.cb_notify_on_request_pin_code(BTAgent.NOTIFY_ON_REQUEST_PIN_CODE,  # noqa
                                                          device)
            if (pin_code is None):
                raise BTRejectedException('User did not provide PIN code')
        elif (self.default_pin_code is None):
            raise BTRejectedException('No default PIN code set')
        else:
            pin_code = self.default_pin_code
        return dbus.String(pin_code)

    @dbus.service.method("org.bluez.Agent", in_signature="o",
                         out_signature="s")
    def RequestPasskey(self, device):
        if (self.cb_notify_on_request_pass_key):
            pass_key = self.cb_notify_on_request_pass_key(BTAgent.NOTIFY_ON_REQUEST_PASS_KEY,  # noqa
                                                          device)
            if (pass_key is None):
                raise BTRejectedException('User did not provide pass key')
        elif (self.default_pass_key is None):
            raise BTRejectedException('No default pass key set')
        else:
            pass_key = self.default_pass_key
        return dbus.UInt32(pass_key)

    @dbus.service.method("org.bluez.Agent", in_signature="ou",
                         out_signature="")
    def DisplayPasskey(self, device, pass_key):
        if (self.cb_notify_on_display_pass_key):
            self.cb_notify_on_display_pass_key(BTAgent.NOTIFY_ON_DISPLAY_PASS_KEY,  # noqa
                                               device, pass_key)

    @dbus.service.method("org.bluez.Agent", in_signature="ou",
                         out_signature="")
    def RequestConfirmation(self, device, pass_key):
        if (self.cb_notify_on_request_confirmation):
            if (not self.cb_notify_on_request_confirmation(BTAgent.NOTIFY_ON_REQUEST_CONFIRMATION,  # noqa
                                                           device, pass_key)):
                raise \
                    BTRejectedException('User confirmation of pass key negative')  # noqa

    @dbus.service.method("org.bluez.Agent", in_signature="s", out_signature="")
    def ConfirmModeChange(self, mode):
        if (self.cb_notify_on_confirm_mode_change):
            if (not self.cb_notify_on_confirm_mode_change(BTAgent.NOTIFY_ON_CONFIRM_MODE_CHANGE,  # noqa
                                                          mode)):
                raise \
                    BTRejectedException('User mode change confirmation negative')  # noqa

    @dbus.service.method("org.bluez.Agent", in_signature="", out_signature="")
    def Cancel(self):
        if (self.cb_notify_on_cancel):
            self.cb_notify_on_cancel(BTAgent.NOTIFY_ON_CANCEL)
