import aio_pika
from faststream import FastStream
from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue, ExchangeType

from app.config import settings

broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)

payments_exchange = RabbitExchange(
    name="payments",
    type=ExchangeType.TOPIC,
    durable=True,
)

payments_dlq_queue = RabbitQueue(
    name="payments.new.dlq",
    durable=True,
)

payments_new_queue = RabbitQueue(
    name="payments.new",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": "payments.new.dlq",
    },
)

payment_created_publisher = broker.publisher(
    queue=payments_new_queue,
    exchange=payments_exchange,
    routing_key="payment.created",
)


async def setup_rabbitmq_topology() -> None:

    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()

        await channel.declare_queue("payments.new.dlq", durable=True)

        await channel.declare_queue(
            "payments.new",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "payments.new.dlq",
            },
        )

        exchange = await channel.declare_exchange(
            "payments",
            type=aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.get_queue("payments.new")
        await queue.bind(exchange, routing_key="payment.created")
