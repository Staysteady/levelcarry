# LME Spread Trading Platform

A local spread trading platform for LME metals, consisting of two Streamlit applications that communicate through Redis and a SQLite database.

## Overview

This system is designed to facilitate the construction, valuation, and submission of multi-leg carry trades (calendar spreads) for LME metals. It consists of two separate Streamlit applications:

1. **User App** (`user_app.py`): Allows traders to build 2-3 leg spreads, view real-time valuations based on LME forward curve data, and submit their interest.
2. **Market Maker App** (`mm_app.py`): For market makers to view incoming spread requests, evaluate their impact on current positions, and respond with acceptances or counteroffers.

The applications communicate via a local Redis instance and store data in a SQLite database.

## Prerequisites

- Python 3.8+
- Redis server installed and running on localhost:6379
- Required Python libraries (install using `pip install -r requirements.txt`)

## Setup Instructions

1. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

2. **Install and run Redis**:
   - **Mac**: `brew install redis` and `brew services start redis`
   - **Linux**: `sudo apt-get install redis-server` and `sudo service redis-server start`
   - **Windows**: Download and install from [Redis for Windows](https://github.com/tporadowski/redis/releases)
   - Alternative: Use Docker with `docker run --name redis -p 6379:6379 -d redis`
   
3. **Verify Redis is running**:
   ```
   redis-cli ping
   ```
   It should respond with "PONG".

## Running the Applications

Run both applications in separate terminal windows:

1. **Start the User App**:
   ```
   streamlit run user_app.py
   ```
   This will typically run on http://localhost:8501

2. **Start the Market Maker App**:
   ```
   streamlit run mm_app.py
   ```
   This will typically run on http://localhost:8502

## Using the System

### User App Workflow

1. **Login**: Select a user from the available options (user1, user2).
2. **Upload Forward Curve**: Use the sidebar to upload an LME PDF file containing forward curve data.
3. **Build Spread**:
   - Select metal
   - Configure 2-3 legs with start/end dates, direction (Borrow/Lend), and lots
   - View real-time valuation of the spread
4. **Submit Interest**:
   - Choose whether to submit at valuation only or allow a counter within your specified loss threshold
   - Submit the spread to the market maker
5. **Check History**: View the status and responses for your submitted spreads in the History tab.

### Market Maker App Workflow

1. **Login**: Select the market maker account.
2. **Upload Position Data**: Upload a CSV file with your current positions (format: Metal, Date, Position).
3. **Refresh Interests**: Click the refresh button to load pending spread interests.
4. **View and Respond**:
   - See overview of position exposure and market interest in the first tab
   - Review and respond to individual spread requests in the second tab
   - Accept, counter, or reject each spread based on analysis of its impact on your position

## File Structure

- `user_app.py`: Streamlit application for traders
- `mm_app.py`: Streamlit application for the market maker
- `src/core_engine.py`: Shared functionality for both apps
- `src/models/`: Contains data models
- `src/utils/`: Utility functions
- `spread_trading.db`: SQLite database (created at runtime)

## Sample Files

- Create a `data/` directory and add sample LME PDF files
- Create sample position CSV files with columns:
  - Metal (e.g., "Zinc")
  - Date (in DD/MM/YYYY format)
  - Position (positive for long, negative for short)

## Known Limitations

- The application requires a local Redis server
- PDF parsing may need adjustment for different LME PDF formats
- The position impact calculation is simplified
- No real authentication or security (this is a local simulation)

## Troubleshooting

- **Redis Connection Issues**: Ensure Redis is running on the default port (6379)
- **PDF Parsing Errors**: Check the format of your LME PDFs; they should contain a "Per Day" section
- **Missing Valuation Data**: Upload LME forward curve PDFs for each metal you want to trade 