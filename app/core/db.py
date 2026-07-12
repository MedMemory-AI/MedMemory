from prisma import Prisma

# Instantiate the globally shared Prisma client instance...
db = Prisma(auto_register=True)

async def connect_db():
    """
    Evaluates connection states. If inactive, establishes an open, active 
    connection pool link to the containerized PostgreSQL database.
    """
    if not db.is_connected():
        await db.connect()

async def disconnect_db():
    if db.is_connected():
        await db.disconnect()
