# LME Spread Trading Platform

A local spread trading platform for LME metals, consisting of four Streamlit applications that communicate through Redis and a SQLite database.

## Overview

This system is designed to facilitate the construction, valuation, and submission of multi-leg carry trades (calendar spreads) for LME metals. It consists of four separate Streamlit applications:

1. **User App** (`user_app.py`): Allows traders to build 2-3 leg spreads, view real-time valuations based on LME forward curve data, and submit their interest.
2. **Market Maker App** (`mm_app.py`): For market makers to view incoming spread requests, evaluate their impact on current positions, and respond with acceptances or counteroffers.
3. **Dashboard App** (`dashboard_app.py`): Provides a comprehensive market overview, visualizes matching opportunities, and displays active market axes.
4. **Order Book App** (`order_book_app.py`): Serves as a centralized repository of all orders, allowing detailed filtering, visualization, and management of trades.

The applications communicate via a local Redis instance and store data in a SQLite database.

## Prerequisites

* Python 3.8+
* Redis server installed and running on localhost:6379
* Required Python libraries (install using `pip install -r requirements.txt`)

## Setup Instructions

1. **Install dependencies**:  
```  
pip install -r requirements.txt  
```

2. **Install and run Redis**:  
   * **Mac**: `brew install redis` and `brew services start redis`  
   * **Linux**: `sudo apt-get install redis-server` and `sudo service redis-server start`  
   * **Windows**: Download and install from Redis for Windows  
   * Alternative: Use Docker with `docker run --name redis -p 6379:6379 -d redis`

3. **Verify Redis is running**:  
```  
redis-cli ping  
```  
It should respond with "PONG".

See detailed Redis setup instructions in [SETUP_REDIS.md](SETUP_REDIS.md).

## Running the Applications

You can run each application individually or use the launcher script to start all applications at once:

### Option 1: Launch All Apps at Once
```
python launch_all.py
```

### Option 2: Run Each App Separately

Run each application in a separate terminal window:

1. **Start the User App**:  
```  
streamlit run user_app.py  
```  
This will typically run on <http://localhost:8501>

2. **Start the Market Maker App**:  
```  
streamlit run mm_app.py  
```  
This will typically run on <http://localhost:8502>

3. **Start the Dashboard App**:  
```  
streamlit run dashboard_app.py  
```  
This will typically run on <http://localhost:8503>

4. **Start the Order Book App**:  
```  
streamlit run order_book_app.py  
```  
This will typically run on <http://localhost:8504>

## Using the System

### User App Workflow

1. **Login**: Select a user from the available options (user1, user2).
2. **Upload Forward Curve**: Use the sidebar to upload an LME PDF file containing forward curve data.
3. **Build Spread**:  
   * Select metal  
   * Configure 2-3 legs with start/end dates, direction (Borrow/Lend), and lots  
   * View real-time valuation of the spread
4. **Submit Interest**:  
   * Choose whether to submit at valuation only or allow a counter within your specified loss threshold  
   * Submit the spread to the market maker
5. **Check History**: View the status and responses for your submitted spreads in the History tab.

### Market Maker App Workflow

1. **Login**: Select the market maker account.
2. **Upload Position Data**: Upload a CSV file with your current positions (format: Metal, Date, Position).
3. **Refresh Interests**: Click the refresh button to load pending spread interests.
4. **View and Respond**:  
   * See overview of position exposure and market interest in the first tab  
   * Review and respond to individual spread requests in the second tab  
   * Accept, counter, or reject each spread based on analysis of its impact on your position

### Dashboard App Workflow

1. **Market Overview**: View a comprehensive heatmap of all market interest across metals and dates.
2. **Matching Opportunities**: Analyze potential matches between different orders that could be combined for efficient execution.
3. **Market Axes**: Identify key dates (axes) with high trading activity to spot market patterns.
4. **Auto-refresh**: Configure the dashboard to automatically refresh at your preferred interval.

### Order Book App Workflow

1. **Order Management**: View, filter, and sort all orders in the system.
2. **Order Details**: Examine comprehensive details of any selected order.
3. **Visualization**: View graphical representations of orders with their legs and timeline.
4. **Statistics**: Monitor key metrics about the overall order book across all metals and users.
5. **Counter Response**: Users can accept or reject counter offers from the market maker.

## Communication Between Apps

The four applications maintain a synchronized view of the market through:

1. **Redis**: Used for real-time communication of new orders, responses, and counters
2. **SQLite**: Provides persistent storage of all trades, user data, and historical information

When a user submits a new spread in the User App, it's immediately visible to the Market Maker and appears in both the Dashboard and Order Book. Similarly, when the Market Maker counters or accepts a trade, this status update is reflected across all applications.

## File Structure

* `user_app.py`: Streamlit application for traders
* `mm_app.py`: Streamlit application for the market maker
* `dashboard_app.py`: Streamlit application for market overview and matching engine
* `order_book_app.py`: Streamlit application for centralized order management
* `src/core_engine.py`: Shared functionality for all apps
* `src/models/`: Contains data models
* `src/utils/`: Utility functions
* `spread_trading.db`: SQLite database (created at runtime)

## Sample Files

* Sample LME PDF files are included in the `data/` directory
* A sample position CSV file is provided (`sample_positions.csv`) with columns:  
   * Metal (e.g., "Zinc")  
   * Date (in DD/MM/YYYY format)  
   * Position (positive for long, negative for short)

## Known Limitations

* The application requires a local Redis server
* PDF parsing may need adjustment for different LME PDF formats
* The position impact calculation is simplified
* No real authentication or security (this is a local simulation)

## Troubleshooting

* **Redis Connection Issues**: Ensure Redis is running on the default port (6379)
* **PDF Parsing Errors**: Check the format of your LME PDFs; they should contain a "Per Day" section
* **Missing Valuation Data**: Upload LME forward curve PDFs for each metal you want to trade
* **Synchronization Issues**: If apps seem out of sync, try refreshing the data manually in each app 