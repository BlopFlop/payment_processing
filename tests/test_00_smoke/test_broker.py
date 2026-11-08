import pytest
import aio_pika

from faststream.rabbit import RabbitBroker

from app.core.config import BrokerSettings


@pytest.mark.parametrize("queue_name", ["payments.new", "payments.dlq", "payments.retry.0", "payments.retry.1"])
async def test_broker_queue(broker: RabbitBroker, broker_settings: BrokerSettings, queue_name: str) -> None:
    connection = await aio_pika.connect(broker_settings.URL.get_secret_value())
    try:
        channel = await connection.channel()
        try:
            await channel.get_queue(queue_name, ensure=True)
        except aio_pika.exceptions.ChannelNotFoundEntity:
            pytest.fail(f"Очередь {queue_name} не объявлена при старте")
    finally:
        await connection.close()


@pytest.mark.parametrize("exchange_name", ["payments", "payments.dlx"])
async def test_broker_exchange(broker: RabbitBroker, broker_settings: BrokerSettings, exchange_name: str) -> None:
    connection = await aio_pika.connect(broker_settings.URL.get_secret_value())
    try:
        channel = await connection.channel()
        try:
            await channel.get_exchange(exchange_name, ensure=True)
        except aio_pika.exceptions.ChannelNotFoundEntity:
            pytest.fail(f"Exchange {exchange_name} не объявлен при старте")
    finally:
        await connection.close()
