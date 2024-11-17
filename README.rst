owlsensor - Library for OWL CM 160 Energy meter
================================================

This library lets you read sensor data from serial-connected OWL Energy meter.
It current supports the following model:

- CM 160

Usage
=====

* Create a CMDataCollector with port name as first argument, and OWL model as second argument,

```python
cm.CMDataCollector("COM4", cm.SUPPORTED_SENSORS["TheOWL,CM160"])
```

```python
cm.CMDataCollector("/dev/ttyUSB0", cm.SUPPORTED_SENSORS["TheOWL,CM160"])
```

* You can add several devices the same way, on different serial ports.

* Connect will be called automatically by read_data.

```python
await s.connect()
await s.read_data()
```

* read_data returns a dict (CMVALS=[CURRENT]) containing the acquired real-time value. Currently only current in ampere is returned.

```
print(await s.read_data())

{'Current': 4.1}
```

Limitations
===========

* Historical data returned by the device at connection is discarded, only realtime transmissions are available