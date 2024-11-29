from contextlib import asynccontextmanager
import asyncio
import psutil

rabbitmq_working=False
fastapi_working=False
system_values={"CPU": 0, "Memory": 0}


async def update_system_resources_periodically(interval: int):
    """Update system resources (CPU and Memory usage) in the global variable."""
    while True:
        try:
            # Get current CPU usage as percentage
            system_values["CPU"] = psutil.cpu_percent(interval=1)

            # Get current Memory usage as percentage
            memory = psutil.virtual_memory()
            system_values["Memory"] = memory.percent

            logger.info(f"Updated system resources: {system_values}")
        except Exception as e:
            logger.error(f"Error updating system resources: {e}")

        # Sleep for a given interval before updating again
        await asyncio.sleep(10)


def set_rabbitmq_status(status: bool):
    global rabbitmq_working
    rabbitmq_working = status

def get_rabbitmq_status():
    return rabbitmq_working