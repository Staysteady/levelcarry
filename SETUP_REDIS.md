# Setting Up Redis for LME Spread Trading Platform

Redis is required for communication between the User and Market Maker applications. Below are instructions for installing and running Redis on different operating systems.

## Mac OS X

1. **Install Redis using Homebrew** (recommended):
   ```
   brew install redis
   ```

2. **Start Redis Server**:
   ```
   brew services start redis
   ```
   
   Alternatively, run it in the foreground:
   ```
   redis-server
   ```

3. **Verify Redis is running**:
   ```
   redis-cli ping
   ```
   It should respond with "PONG".

## Linux

1. **Install Redis**:
   ```
   sudo apt-get update
   sudo apt-get install redis-server
   ```

2. **Start Redis Server**:
   ```
   sudo service redis-server start
   ```
   
   Or on systemd-based distributions:
   ```
   sudo systemctl start redis
   ```

3. **Verify Redis is running**:
   ```
   redis-cli ping
   ```

## Windows

1. **Download Redis for Windows**:
   Download from [https://github.com/tporadowski/redis/releases](https://github.com/tporadowski/redis/releases)

2. **Install Redis**:
   Run the downloaded MSI installer and follow the installation wizard.

3. **Start Redis**:
   Redis should start automatically as a Windows service. You can verify in Services.msc.

4. **Verify Redis is running**:
   ```
   redis-cli ping
   ```

## Using Docker (Alternative for any OS)

If you have Docker installed, you can run Redis as a container:

1. **Pull and run the Redis container**:
   ```
   docker run --name redis -p 6379:6379 -d redis
   ```

2. **Verify Redis is running**:
   ```
   docker exec -it redis redis-cli ping
   ```

## Temporary Redis Server for Testing

If you can't install Redis, you can use a Python package called `fakeredis` for local testing:

1. **Install fakeredis**:
   ```
   pip install fakeredis
   ```

2. **Modify the core_engine.py file**:
   Change the Redis client initialization in get_redis_client() to use fakeredis:
   ```python
   def get_redis_client():
       """Get a Redis client connected to the local Redis server."""
       import fakeredis
       return fakeredis.FakeStrictRedis()
   ```

This fakeredis approach is for testing only and won't work for real communication between separate app instances.

## Troubleshooting

- **Port conflicts**: If something else is using port 6379, you can specify a different port in the Redis configuration.
- **Connection refused**: Make sure Redis is actually running.
- **Authentication required**: By default, Redis doesn't require authentication. If your installation does, you'll need to update the connection parameters in the code. 