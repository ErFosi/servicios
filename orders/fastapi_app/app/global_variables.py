from contextlib import asynccontextmanager
import asyncio
import psutil

rabbitmq_working=False
fastapi_working=False
system_values={"CPU": 0, "Memory": 0}

@asynccontextmanager
async def system_resources(seconds):
    try:
        while True:
            cpu = psutil.cpu_percent(interval=1.0)  # Obtener porcentaje de CPU
            memory = psutil.virtual_memory().percent  # Obtener porcentaje de memoria

            # Actualizar los valores globales
            system_resources["CPU"] = cpu
            system_resources["Memory"] = memory

            # Mostrar los valores de los recursos
            logger.info(f"CPU: {cpu}%, Memory: {memory}%")

            # Dormir antes de la siguiente medición
            await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        logger.info("Monitoreo de recursos cancelado")

def set_rabbitmq_status(status: bool):
    global rabbitmq_working
    rabbitmq_working = status

def get_rabbitmq_status():
    return rabbitmq_working