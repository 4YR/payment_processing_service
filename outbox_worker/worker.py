import asyncio


async def main():
    print("Outbox worker started")

    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())