#!/usr/bin/env python3
"""
Example script demonstrating historical data collection from OWL CM160.

This script shows how to:
1. Connect to a CM160 device
2. Wait for historical data collection to complete
3. Retrieve and display historical data in a format suitable for Home Assistant

The device sends historical data during initial connection, which contains
timestamped current readings that can be processed by Home Assistant.
"""

import asyncio
import owlsensor as cm

async def collect_historical_data(port):
    """Collect and display historical data from CM160 device."""
    print(f"Connecting to CM160 device on {port}...")

    # Use a scan_interval to run data collection in a background task.
    # This allows us to poll the sensor state while it's processing data.
    async with cm.CMDataCollector(
        port, cm.SUPPORTED_SENSORS["CM160"], scan_interval=1) as sensor:
        print("Connected! Waiting for historical data...")

        # Wait for historical data collection to complete
        timeout = 300  # 5 minutes timeout
        start_time = asyncio.get_event_loop().time()

        while not sensor.is_historical_data_complete():
            await asyncio.sleep(1)
            current_time = asyncio.get_event_loop().time()

            # Show progress
            historical_data = sensor.get_historical_data()
            if len(historical_data) > 0:
                print(f"Historical records collected: {len(historical_data)}", end='\r')

            # Check timeout
            if current_time - start_time > timeout:
                print("\nTimeout waiting for historical data completion")
                break

        # Get final historical data
        historical_data = sensor.get_historical_data()

        if not historical_data:
            print("\nNo historical data received")
            return

        print(f"\nHistorical data collection complete! {len(historical_data)} records collected.")

        # Display data in Home Assistant friendly format
        print("\nHistorical data (timestamp, current):")
        print("-" * 50)

        for record in historical_data[-10:]:  # Show last 10 records
            timestamp = record["timestamp"]
            current = record["current"]
            print(f"{timestamp.isoformat()}: {current}A")

        if len(historical_data) > 10:
            print(f"... and {len(historical_data) - 10} more records")

        # Show real-time data
        print("\nWaiting for real-time data...")
        realtime_data = await sensor.read_data()
        if realtime_data:
            print(f"Current real-time reading: {realtime_data['Current']}A")

        # Demonstrate data export for Home Assistant
        print("\nData structure for Home Assistant integration:")
        print("Each record contains:")
        print("- 'timestamp': datetime object")
        print("- 'current': float (amperes)")
        print(f"Sample: {historical_data[0] if historical_data else 'No data'}")

async def main():
    """Main function to run the historical data collection example."""
    # Default port - change this to match your setup
    port = "/dev/ttyUSB0"  # Linux
    # port = "COM4"        # Windows

    try:
        await collect_historical_data(port)
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())