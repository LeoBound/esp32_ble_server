import math
import struct
import time
import bluetooth
import machine
from micropython import const

LED_PWM = machine.PWM(machine.Pin(2, machine.Pin.OUT), freq=1000)
LED_PWM.duty(0)


def pulse(pwm, t):
    for i in range(20):
        pwm.duty(int(math.sin(i / 10 * math.pi) * 500 + 500))
        time.sleep(t/1E3)


_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID32_COMPLETE = const(0x5)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_UUID16_MORE = const(0x2)
_ADV_TYPE_UUID32_MORE = const(0x4)
_ADV_TYPE_UUID128_MORE = const(0x6)
_ADV_TYPE_APPEARANCE = const(0x19)

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

# ========================================================================================
# BTLE Config
# ========================================================================================
# A Service is a container for 1 or more characteristics
# Characteristrics can have a descriptor  which say whether they are read/write/notify etc
# All are identified by UUIDs

# Service UUID
_UART_UUID = bluetooth.UUID("7dbea1af-b4ed-4d65-99c9-78b85f2f371f")

# Transmitted characteristic UUID - a sample characteristic that's read-only and notifies
_UART_TX = (
    bluetooth.UUID("bd9945a3-5c60-45b1-9f0e-fd3c5eb163b2"),
    bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY,
)
# Received characteristic UUID - a sample characteristic that's read-write
_UART_RX = (
    bluetooth.UUID("8a1e3d71-7224-4d9d-bf07-cc924abb8db6"),
    bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE,
)

# Construct service from attributes and UUID
_UART_SERVICE = (
    _UART_UUID,
    (_UART_TX, _UART_RX,),
)


# Generate a payload to be passed to gap_advertise(adv_data=...).
def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None, appearance=0):
    payload = bytearray()

    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value

    _append(
        _ADV_TYPE_FLAGS,
        struct.pack("B", (0x01 if limited_disc else 0x02) +
                    (0x18 if br_edr else 0x04)),
    )

    if name:
        _append(_ADV_TYPE_NAME, name)

    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 2:
                _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 4:
                _append(_ADV_TYPE_UUID32_COMPLETE, b)
            elif len(b) == 16:
                _append(_ADV_TYPE_UUID128_COMPLETE, b)

    # See org.bluetooth.characteristic.gap.appearance.xml
    if appearance:
        _append(_ADV_TYPE_APPEARANCE, struct.pack("<h", appearance))

    return payload


class BLESimplePeripheral:
    def __init__(self, ble, name="car-leo"):
        self._ble = ble

        # Turn on bluetooth
        self._ble.active(True)

        # Register callback function so we get notified of connects/disconnects/writes etc
        self._ble.irq(handler=self._irq)

        ((self._handle_tx, self._handle_rx,),
         ) = self._ble.gatts_register_services((_UART_SERVICE,))
        self._connections = set()
        self._write_callback = None
        self._payload = advertising_payload(name=name, services=[_UART_UUID],)

        # Start advertising
        self._advertise()

    # This is essentially a callback function
    def _irq(self, event, data):
        # Track connections so we can send notifications.
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _, = data
            print("New connection", conn_handle)
            self._connections.add(conn_handle)
            LED_PWM.duty(1000)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _, = data
            print("Disconnected", conn_handle)
            self._connections.remove(conn_handle)
            LED_PWM.duty(0)
            # Start advertising again to allow a new connection.
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            value = self._ble.gatts_read(value_handle)
            if value_handle == self._handle_rx and self._write_callback:
                self._write_callback(value)

    def send(self, data):
        for conn_handle in self._connections:
            self._ble.gatts_notify(conn_handle, self._handle_tx, data)

    def is_connected(self):
        return len(self._connections) > 0

    def _advertise(self, interval_us=500000):
        print("Starting advertising")
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

    def on_write(self, callback):
        self._write_callback = callback


def demo(ping_interval=1):
    ble = bluetooth.BLE()
    bleperiph = BLESimplePeripheral(ble)

    def on_receive(v):
        pulse(LED_PWM, 50)
        print("Received:", v)

    bleperiph.on_write(on_receive)

    i = 0
    while True:
        if bleperiph.is_connected():
            # Short burst of queued notifications.
            # data = str(i) + ': This is a big string isn\'t it'
            #print("Transmitting:", data)
            # bleperiph.send(data)
            i += 1
        time.sleep(ping_interval)


if __name__ == "__main__":
    demo()
