import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np
import base64
import io
import sys
import argparse
import sqlite3

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description="LME Spread Trading Dashboard App")
    parser.add_argument("--app_name", type=str, default="Dashboard", help="Application name")
    # Get only known args, ignore streamlit's own args
    return parser.parse_known_args()[0]

# Get command line arguments
args = parse_args()
app_name = args.app_name

# Fix for the fitz import issue
try:
    import fitz
except ImportError:
    import PyMuPDF as fitz
    
from src.core_engine import (
    get_pending_interests,
    get_user_spread_history,
    price_spread,
    get_latest_curve,
    get_redis_client,
    TONS_PER_LOT
)

# Page configuration
st.set_page_config(
    page_title=f"Dashboard",
    page_icon="📊",
    layout="wide"
)

def init_session_state():
    """Initialize session state variables."""
    if 'pending_interests' not in st.session_state:
        st.session_state.pending_interests = []
    
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = None
    
    if 'refresh_interval' not in st.session_state:
        st.session_state.refresh_interval = 60
    
    if 'auto_refresh' not in st.session_state:
        st.session_state.auto_refresh = True
    
    if 'current_view' not in st.session_state:
        st.session_state.current_view = "timeline"
        
    # Always use dark mode
    st.session_state.dark_mode = True

# List of available metals
METALS = ["Aluminum", "Copper", "Zinc", "Nickel", "Lead", "Tin"]

def apply_theme():
    """Apply theme for the entire application."""
    st.markdown("""
    <style>
    /* Main app background and text */
    .stApp {
        background-color: #ffffff;
        color: #262730;
    }
    
    /* Sidebar and widgets background */
    div[data-testid="stSidebar"] {
        background-color: #f0f2f6;
        color: #262730;
    }
    
    /* Elements inside sidebar - make them consistent with sidebar */
    div[data-testid="stSidebar"] .st-cb, div[data-testid="stSidebar"] .st-d9, 
    div[data-testid="stSidebar"] .st-da, div[data-testid="stSidebar"] .st-db, 
    div[data-testid="stSidebar"] .st-dc, div[data-testid="stSidebar"] .st-dd, 
    div[data-testid="stSidebar"] .st-de, 
    div[data-testid="stSidebar"] .css-1aumxhk, 
    div[data-testid="stSidebar"] .css-182u55c, 
    div[data-testid="stSidebar"] .css-1x8cf1d,
    div[data-testid="stSidebar"] div[data-testid="stExpander"] {
        background-color: #f0f2f6 !important;
        color: #262730 !important;
    }
    
    /* Make radio buttons and other controls in sidebar match sidebar background */
    div[data-testid="stSidebar"] .st-bq,
    div[data-testid="stSidebar"] div[role="radiogroup"],
    div[data-testid="stSidebar"] label,
    div[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    div[data-testid="stSidebar"] .stRadio,
    div[data-testid="stSidebar"] .stSlider {
        background-color: #f0f2f6 !important;
    }
    
    /* Form inputs and interactive elements */
    .stTextInput, .stSelectbox, .stDateInput, .stNumberInput,
    input, select, textarea, .stSlider, [data-baseweb="select"] {
        background-color: #fff !important;
        color: #262730 !important;
        border-color: #ccc !important;
    }
    
    /* Buttons - update to match the light theme buttons in other apps */
    .stButton>button {
        background-color: #f0f2f6 !important;
        color: #262730 !important;
        border: 1px solid #ccc !important;
        border-radius: 4px !important;
        padding: 0.375rem 0.75rem !important;
        font-size: 1rem !important;
        line-height: 1.5 !important;
        text-align: center !important;
        text-decoration: none !important;
        cursor: pointer !important;
    }
    
    .stButton>button:hover {
        background-color: #e9ecef !important;
        color: #dc3545 !important; /* Red color on hover, matching other apps */
        border-color: #dc3545 !important;
    }
    
    /* Sidebar specific button styles */
    div[data-testid="stSidebar"] .stButton>button {
        background-color: #f0f2f6 !important;
        color: #262730 !important;
        border: 1px solid #ccc !important;
    }
    
    div[data-testid="stSidebar"] .stButton>button:hover {
        background-color: #e9ecef !important;
        color: #dc3545 !important;
        border-color: #dc3545 !important;
    }
    
    /* Tabs styling to match the other app */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #f8f9fa;
        border-radius: 4px;
        overflow: hidden;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        border-radius: 0 !important;
        padding: 10px 16px;
        color: #262730;
        background-color: #f8f9fa;
        border: none !important;
        border-right: 1px solid #dee2e6 !important;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        color: #dc3545 !important; /* Red on hover */
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #f8f9fa !important;
        color: #dc3545 !important; /* Red for selected tab */
        border-bottom: 2px solid #dc3545 !important; /* Red underline for selected tab */
    }
    
    /* Metal tabs styling for User Timeline */
    .stTabs [role="tablist"] button {
        background-color: #f8f9fa;
        color: #262730;
        border-radius: 0;
        border: none;
        border-right: 1px solid #dee2e6;
        height: 40px;
        padding: 10px 16px;
    }
    
    .stTabs [role="tablist"] button:hover {
        color: #dc3545 !important; /* Red on hover */
    }
    
    .stTabs [role="tablist"] [aria-selected="true"] {
        background-color: #f8f9fa !important;
        color: #dc3545 !important; /* Red for selected tab */
        border-bottom: 2px solid #dc3545 !important; /* Red underline for selected tab */
        font-weight: 500;
    }
    
    /* Plotly charts */
    .stPlotlyChart {
        background-color: #ffffff;
    }
    
    /* Data frames and tables */
    .stDataFrame, div[data-testid="stTable"] {
        background-color: #fff;
    }
    
    .dataframe {
        color: #262730 !important;
    }
    
    .dataframe th {
        background-color: #f0f2f6 !important;
        color: #262730 !important;
    }
    
    .dataframe td {
        color: #262730 !important;
    }
    
    /* Expanders and containers - those in main content area should be white */
    .main .streamlit-expanderHeader {
        background-color: #ffffff !important;
        color: #262730 !important;
    }
    
    div[data-testid="stExpander"] {
        background-color: #ffffff !important;
        color: #262730 !important;
    }
    
    /* Legend container */
    .legend-container {
        display: flex;
        flex-wrap: wrap;
        gap: 15px;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 5px;
        background-color: #ffffff;
        margin-top: 10px;
        color: #262730;
    }
    
    /* Metric widgets */
    div[data-testid="stMetricValue"] {
        color: #262730 !important;
    }
    
    /* Info, warning, error boxes */
    div[data-testid="stInfoBox"] {
        background-color: #e1f5fe !important;
        color: #0277bd !important;
    }
    
    div[data-testid="stWarningBox"] {
        background-color: #fff8e1 !important;
        color: #ff8f00 !important;
    }
    
    div[data-testid="stErrorBox"] {
        background-color: #ffebee !important;
        color: #c62828 !important;
    }
    
    /* Hover labels */
    div[data-baseweb="tooltip"], div[data-baseweb="popover"] {
        background-color: #ffffff !important;
        color: #262730 !important;
    }
    </style>
    """, unsafe_allow_html=True)

def format_date(date_str: str) -> str:
    """Format date string for display."""
    try:
        date = datetime.fromisoformat(date_str)
        return date.strftime('%d-%b-%y')
    except (ValueError, TypeError):
        return date_str

def format_pnl(pnl: float, for_hover: bool = False) -> str:
    """Format PnL value with color.
    
    Args:
        pnl: The PnL value to format
        for_hover: If True, return plain text format for hover tooltips
    """
    if for_hover:
        return f"${pnl:.2f}"
    
    color = "green" if pnl > 0 else "red" if pnl < 0 else "gray"
    return f"<span style='color:{color}'>${pnl:.2f}</span>"

def get_all_orders() -> List[Dict]:
    """Get combined list of all orders and active interests."""
    # Get pending interests from Redis/DB
    interests = get_pending_interests()
    
    # Get user history for completed trades (we'll filter for responses)
    user_history = []
    for user_id in ["Bushy", "Josh", "Dorans", "Jimmy", "Paddy"]:  # Capitalized user names
        # Convert to lowercase for database lookup
        db_user_id = user_id.lower()
        history = get_user_spread_history(db_user_id)
        
        # Set the user_id to the capitalized version for display
        for trade in history:
            trade['user_id'] = user_id
            
        user_history.extend(history)
    
    # Filter for accepted trades or countered trades
    active_trades = [
        trade for trade in user_history 
        if 'response' in trade and 
        trade['response'].get('status') in ['Accepted', 'Countered']
    ]
    
    # Ensure all user IDs are capitalized in the interests list too
    for interest in interests:
        if 'user_id' in interest and interest['user_id']:
            user_id = interest['user_id']
            interest['user_id'] = user_id[0].upper() + user_id[1:] if user_id else user_id
    
    # Combine and return all
    return interests + active_trades

def display_market_heatmap(interests: List[Dict], chart_template=None):
    """Display heatmap of all interests by date range and metal."""
    if not interests:
        st.warning("No interests or orders available")
        return
    
    # Collect all legs from all interests
    all_legs = []
    for interest in interests:
        metal = interest.get('metal', 'Unknown')
        # Include status and counter value if available
        status = interest.get('status', 'Pending')
        counter_pnl = None
        
        if 'response' in interest and interest['response'].get('status') == 'Countered':
            counter_pnl = interest['response'].get('counter_pnl')
            status = 'Countered'
        
        for leg in interest.get('legs', []):
            try:
                start_date = datetime.fromisoformat(leg['start_date'])
                end_date = datetime.fromisoformat(leg['end_date'])
                
                all_legs.append({
                    'Metal': metal,
                    'Start': start_date,
                    'End': end_date,
                    'Direction': leg['direction'],
                    'Lots': leg['lots'],
                    'Status': status,
                    'CounterPnL': counter_pnl
                })
            except (KeyError, ValueError):
                continue
    
    if not all_legs:
        st.warning("No valid legs found in interests")
        return
    
    # Create a dataframe of all legs
    legs_df = pd.DataFrame(all_legs)
    
    # Create a date range covering all legs
    min_date = legs_df['Start'].min()
    max_date = legs_df['End'].max()
    date_range = pd.date_range(start=min_date, end=max_date, freq='D')
    
    # Initialize a dictionary to hold interest by date and metal
    interest_by_date_metal = {}
    
    # For each leg, add its lots to all dates in its range
    for _, leg in legs_df.iterrows():
        metal = leg['Metal']
        start = leg['Start']
        end = leg['End']
        lots = leg['Lots']
        if leg['Direction'] == 'Borrow':
            lots = -lots  # Negative for borrow
        
        leg_dates = pd.date_range(start=start, end=end, freq='D')
        
        for date in leg_dates:
            date_str = date.strftime('%Y-%m-%d')
            key = (metal, date_str)
            
            if key in interest_by_date_metal:
                interest_by_date_metal[key] += lots
            else:
                interest_by_date_metal[key] = lots
    
    # Convert to dataframe for plotting
    heatmap_data = []
    for (metal, date_str), lots in interest_by_date_metal.items():
        heatmap_data.append({
            'Metal': metal,
            'Date': date_str,
            'Lots': lots
        })
    
    heatmap_df = pd.DataFrame(heatmap_data)
    
    # Create pivot table for heatmap
    pivot_df = heatmap_df.pivot_table(
        values="Lots", 
        index="Metal", 
        columns="Date", 
        fill_value=0
    )
    
    # Plot heatmap
    fig = px.imshow(
        pivot_df,
        labels=dict(x="Date", y="Metal", color="Net Interest (Lots)"),
        title="Market Heatmap - Net Interest by Date & Metal",
        color_continuous_scale="RdBu_r",  # Red for lend interest, blue for borrow interest
        aspect="auto"
    )
    
    # Apply theme template if provided
    if chart_template:
        fig.update_layout(template=chart_template)
    
    # Add more detailed hover info
    fig.update_traces(
        hovertemplate="Metal: %{y}<br>Date: %{x}<br>Net Lots: %{z}<extra></extra>"
    )
    
    # Improve layout
    fig.update_layout(
        height=400,
        margin=dict(l=40, r=40, t=40, b=40),
        coloraxis_colorbar=dict(
            title="Lots",
            tickvals=[-500, -250, 0, 250, 500],
            ticktext=["-500 (Borrow)", "-250", "0", "250", "500 (Lend)"],
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)

def find_matching_opportunities(interests: List[Dict]) -> List[Dict]:
    """
    Find potential matching opportunities between different spread interests.
    Returns a list of dictionaries with matched orders and their compatibility score.
    """
    if not interests:
        return []
    
    opportunities = []
    
    # Compare each pair of interests
    for i, interest1 in enumerate(interests):
        for j, interest2 in enumerate(interests[i+1:], i+1):
            # Skip if same user or different metals
            if (interest1.get('user_id') == interest2.get('user_id') or 
                interest1.get('metal') != interest2.get('metal')):
                continue
            
            metal = interest1.get('metal')
            
            # Check for opposite directions in legs
            match_score = 0
            overlap_days = 0
            matching_legs = []
            
            for leg1 in interest1.get('legs', []):
                for leg2 in interest2.get('legs', []):
                    # Skip if same direction
                    if leg1.get('direction') == leg2.get('direction'):
                        continue
                    
                    # Calculate date overlap
                    try:
                        start1 = datetime.fromisoformat(leg1.get('start_date'))
                        end1 = datetime.fromisoformat(leg1.get('end_date'))
                        start2 = datetime.fromisoformat(leg2.get('start_date'))
                        end2 = datetime.fromisoformat(leg2.get('end_date'))
                        
                        # Check for date overlap
                        overlap_start = max(start1, start2)
                        overlap_end = min(end1, end2)
                        
                        if overlap_start <= overlap_end:
                            days_overlap = (overlap_end - overlap_start).days + 1
                            lots_match = min(leg1.get('lots', 0), leg2.get('lots', 0))
                            
                            # Update match score based on overlap and lots
                            leg_score = days_overlap * lots_match / 100
                            match_score += leg_score
                            overlap_days += days_overlap
                            
                            matching_legs.append({
                                'leg1': leg1,
                                'leg2': leg2,
                                'overlap_start': overlap_start.isoformat(),
                                'overlap_end': overlap_end.isoformat(),
                                'days_overlap': days_overlap,
                                'lots_match': lots_match
                            })
                    except (ValueError, TypeError):
                        continue
            
            # If we found matches, add to opportunities
            if match_score > 0:
                opportunities.append({
                    'order1': interest1,
                    'order2': interest2,
                    'metal': metal,
                    'match_score': match_score,
                    'overlap_days': overlap_days,
                    'matching_legs': matching_legs
                })
    
    # Sort opportunities by match score (descending)
    opportunities.sort(key=lambda x: x['match_score'], reverse=True)
    
    return opportunities

def display_matching_opportunities(opportunities):
    """Display potential matching opportunities between orders."""
    if not opportunities:
        st.info("No matching opportunities found.")
        return
    
    # Display in a table
    data = []
    for opp in opportunities:
        # Get the first matching leg from the opportunity
        matching_legs = opp.get('matching_legs', [])
        if not matching_legs:
            continue
            
        # Get order details
        order1 = opp.get('order1', {})
        order2 = opp.get('order2', {})
        
        # Get the first matching leg pair
        first_match = matching_legs[0]
        leg1 = first_match.get('leg1', {})
        leg2 = first_match.get('leg2', {})
        
        data.append({
            'Match Score': f"{opp['match_score']:.0f}",
            'Metal': opp.get('metal', 'Unknown'),
            'User 1': order1.get('user_id', 'Unknown'),
            'User 2': order2.get('user_id', 'Unknown'),
            'Direction 1': leg1.get('direction', 'Unknown'),
            'Direction 2': leg2.get('direction', 'Unknown'),
            'Overlap Days': opp.get('overlap_days', 0),
            'Matched Lots': first_match.get('lots_match', 0)
        })
    
    # Convert to DataFrame and display
    df = pd.DataFrame(data)
    
    # Use dataframe to make it more interactive
    st.dataframe(df, use_container_width=True)
    
    # Display first few matches as cards
    st.subheader("Top Matching Opportunities")
    
    for i, opp in enumerate(opportunities[:3]):
        # Skip if there are no matching legs
        matching_legs = opp.get('matching_legs', [])
        if not matching_legs:
            continue
            
        # Get order details
        order1 = opp.get('order1', {})
        order2 = opp.get('order2', {})
        
        # Get the first matching leg pair
        first_match = matching_legs[0]
        leg1 = first_match.get('leg1', {})
        leg2 = first_match.get('leg2', {})
        
        with st.container(border=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader(f"Match Score: {opp['match_score']:.0f}")
                st.write(f"Metal: {opp.get('metal', 'Unknown')}")
                st.write(f"Overlap Days: {opp.get('overlap_days', 0)}")
                st.write(f"Matched Lots: {first_match.get('lots_match', 0)}")
                
            with col2:
                user1 = order1.get('user_id', 'Unknown')
                user2 = order2.get('user_id', 'Unknown')
                
                st.write(f"User 1: {user1} ({leg1.get('direction', 'Unknown')} {leg1.get('lots', 0)} lots)")
                start1 = leg1.get('start_date', '')
                end1 = leg1.get('end_date', '')
                st.write(f"From {format_date(start1)} to {format_date(end1)}")
                
                st.write(f"User 2: {user2} ({leg2.get('direction', 'Unknown')} {leg2.get('lots', 0)} lots)")
                start2 = leg2.get('start_date', '')
                end2 = leg2.get('end_date', '')
                st.write(f"From {format_date(start2)} to {format_date(end2)}")

def display_market_axes(interests, chart_template=None):
    """Display axes (time periods) with significant activity."""
    if not interests:
        return
    
    # Extract all date ranges and count activity
    date_ranges = []
    
    for interest in interests:
        for leg in interest.get('legs', []):
            try:
                start_date = datetime.fromisoformat(leg['start_date'])
                end_date = datetime.fromisoformat(leg['end_date'])
                metal = interest.get('metal', 'Unknown')
                
                date_ranges.append({
                    'start': start_date,
                    'end': end_date,
                    'metal': metal,
                    'direction': leg['direction'],
                    'lots': leg['lots']
                })
            except (KeyError, ValueError):
                continue
    
    if not date_ranges:
        return
    
    # Create a DataFrame
    df = pd.DataFrame(date_ranges)
    
    # Find common axes by looking at frequency of start and end dates
    start_counts = df['start'].value_counts().reset_index()
    start_counts.columns = ['Date', 'Frequency']
    start_counts['Type'] = 'Start'
    
    end_counts = df['end'].value_counts().reset_index()
    end_counts.columns = ['Date', 'Frequency']
    end_counts['Type'] = 'End'
    
    # Combine
    axes_df = pd.concat([start_counts, end_counts])
    axes_df = axes_df.sort_values('Frequency', ascending=False).head(10)
    
    # Display the most active axes
    st.subheader("Active Market Axes")
    
    # Plot as a horizontal bar chart
    fig = px.bar(
        axes_df,
        x='Frequency',
        y='Date',
        color='Type',
        orientation='h',
        labels={'Frequency': 'Number of Orders', 'Date': 'Date', 'Type': 'Date Type'},
        title='Most Active Market Axes',
        color_discrete_map={'Start': 'blue', 'End': 'red'}
    )
    
    # Apply theme template if provided
    if chart_template:
        fig.update_layout(template=chart_template)
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Also display as a timeline to show stretches of time
    date_extent = [df['start'].min(), df['end'].max()]
    
    # Create activity count per day
    all_days = pd.date_range(start=date_extent[0], end=date_extent[1])
    day_counts = {day: 0 for day in all_days}
    
    for _, row in df.iterrows():
        dates = pd.date_range(start=row['start'], end=row['end'])
        for date in dates:
            day_counts[date] += 1
    
    # Convert to DataFrame for plotting
    activity_df = pd.DataFrame([
        {'Date': date, 'Active Orders': count} 
        for date, count in day_counts.items()
    ])
    
    # Plot activity timeline
    fig2 = px.line(
        activity_df,
        x='Date',
        y='Active Orders',
        title='Daily Market Activity',
        labels={'Date': 'Date', 'Active Orders': 'Number of Active Orders'}
    )
    
    # Apply theme template if provided
    if chart_template:
        fig2.update_layout(template=chart_template)
    
    # Add a threshold line for high activity
    threshold = activity_df['Active Orders'].quantile(0.75)
    fig2.add_hline(
        y=threshold,
        line_dash="dash",
        line_color="red",
        annotation_text="High Activity Threshold",
        annotation_position="bottom right"
    )
    
    # Highlight high activity periods
    high_activity = activity_df[activity_df['Active Orders'] >= threshold]
    
    fig2.add_trace(
        go.Scatter(
            x=high_activity['Date'],
            y=high_activity['Active Orders'],
            mode='markers',
            marker=dict(color='red', size=8),
            name='High Activity'
        )
    )
    
    st.plotly_chart(fig2, use_container_width=True)

def auto_refresh():
    """Automatically refresh the data based on the interval."""
    if st.session_state.auto_refresh:
        if st.session_state.last_refresh is None:
            st.session_state.pending_interests = get_pending_interests()
            st.session_state.last_refresh = datetime.now()
        else:
            elapsed = (datetime.now() - st.session_state.last_refresh).total_seconds()
            if elapsed >= st.session_state.refresh_interval:
                st.session_state.pending_interests = get_pending_interests()
                st.session_state.last_refresh = datetime.now()
                st.rerun()

def display_user_timeline(interests: List[Dict], chart_template=None):
    """
    Display a timeline of trades by user as horizontal lines.
    Each user is shown on a separate row with their activities color-coded:
    - Red for lending periods
    - Green for borrowing periods
    - White/empty for inactive periods
    Includes tabs to filter by metal type.
    
    Args:
        interests: List of spread interests to display
        chart_template: Optional chart template for styling
    """
    if not interests:
        st.warning("No interests or orders available")
        return
    
    # Get available metals from the data
    all_metals = set()
    for interest in interests:
        metal = interest.get('metal', 'Unknown')
        if metal != 'Unknown':
            all_metals.add(metal)
    
    # Make sure we include all standard metals even if there's no data yet
    standard_metals = ["Aluminum", "Copper", "Zinc", "Nickel", "Lead", "Tin"]
    for metal in standard_metals:
        all_metals.add(metal)
    
    # Sort metals
    all_metals = sorted(list(all_metals))
    
    # Create custom CSS for better tab styling to match the light theme in other apps
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"] button[role="tab"] {
        background-color: #f8f9fa;
        color: #262730;
        border-radius: 0;
        border: none;
        border-right: 1px solid #dee2e6;
        border-bottom: 1px solid #dee2e6;
        height: 40px;
        padding: 10px 16px;
    }
    
    div[data-testid="stHorizontalBlock"] button[role="tab"]:hover {
        color: #dc3545 !important; /* Red on hover */
    }
    
    div[data-testid="stHorizontalBlock"] button[role="tab"][aria-selected="true"] {
        background-color: #f8f9fa !important;
        color: #dc3545 !important; /* Red for selected tab */
        border-bottom: 2px solid #dc3545 !important; /* Red underline for selected tab */
        font-weight: 500;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Create tabs for each metal (no "All Metals" tab)
    metal_tabs = st.tabs(all_metals)
    
    # Determine global date range from all interests (across all metals)
    # This ensures consistent x-axis across all tabs
    all_global_dates = []
    for interest in interests:
        for leg in interest.get('legs', []):
            try:
                start_date = datetime.fromisoformat(leg['start_date'])
                end_date = datetime.fromisoformat(leg['end_date'])
                all_global_dates.extend([start_date, end_date])
            except (KeyError, ValueError):
                continue
    
    if all_global_dates:
        global_min_date = min(all_global_dates)
        global_max_date = max(all_global_dates)
    else:
        # If no data, use today and 3 months from today
        global_min_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        global_max_date = global_min_date + timedelta(days=90)
    
    # Calculate Cash Date and 3M Date consistently
    cash_date = global_min_date
    three_m_date = cash_date + timedelta(days=90)
    
    # Ensure global date range includes 3M date
    if three_m_date > global_max_date:
        global_max_date = three_m_date
    
    # Add padding to global range
    global_date_range_start = global_min_date - timedelta(days=5)
    global_date_range_end = global_max_date + timedelta(days=10)  # Extra padding for 3M date
    
    # Calculate all third Wednesdays in advance (used in all tabs)
    third_wednesdays = []
    
    # Function to get the third Wednesday of a given month/year
    def get_third_wednesday(year, month):
        # Start with the first day of the month
        day = 1
        date = datetime(year, month, day)
        
        # Find the first Wednesday (weekday=2)
        while date.weekday() != 2:
            day += 1
            date = datetime(year, month, day)
        
        # Add 14 days to get to the third Wednesday
        third_wednesday = date + timedelta(days=14)
        return third_wednesday
    
    # Get all months between cash_date and three_m_date
    current_date = cash_date.replace(day=1)
    while current_date <= three_m_date + timedelta(days=31):  # Add extra month to ensure we get the 3M date
        # Get the third Wednesday for this month
        third_wednesday = get_third_wednesday(current_date.year, current_date.month)
        
        # If this third Wednesday is within our range, add it
        if cash_date <= third_wednesday <= three_m_date + timedelta(days=31):
            third_wednesdays.append({
                'date': third_wednesday,
                'label': f"3rd Wed ({third_wednesday.strftime('%b')})"
            })
        
        # Move to the next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)
    
    # Loop through each tab and display the filtered visualization
    for i, tab in enumerate(metal_tabs):
        with tab:
            selected_metal = all_metals[i]
            
            # Filter interests by selected metal
            filtered_interests = [
                interest for interest in interests
                if interest.get('metal') == selected_metal
            ]
            tab_title = f"{selected_metal} Trading Timeline"
            
            st.subheader(tab_title)
            
            # Collect all legs from filtered interests and organize by user
            user_legs = {}
            
            # Track which legs belong to which spread for hover information
            spread_details = {}
            
            # Create a map of spread_id to interest for accessing original data
            interests_map = {interest.get('spread_id', 'unknown'): interest for interest in filtered_interests}
            
            for interest in filtered_interests:
                spread_id = interest.get('spread_id', 'unknown')
                user_id = interest.get('user_id', 'Unknown')
                metal = interest.get('metal', 'Unknown')
                status = interest.get('status', 'Pending')
                pnl = interest.get('pnl', 0)
                
                # Initialize user in dict if not exists
                if user_id not in user_legs:
                    user_legs[user_id] = []
                
                # Gather all legs for this spread
                all_legs_in_spread = []
                total_valuation = 0
                for i, leg in enumerate(interest.get('legs', [])):
                    try:
                        leg_start = datetime.fromisoformat(leg['start_date'])
                        leg_end = datetime.fromisoformat(leg['end_date'])
                        leg_direction = leg['direction']
                        leg_lots = leg['lots']
                        leg_valuation = leg.get('valuation', 0)
                        
                        # Add leg valuation to total
                        total_valuation += leg_valuation
                        
                        all_legs_in_spread.append({
                            'leg_number': i+1,
                            'start': leg_start.strftime('%d-%b-%Y'),
                            'end': leg_end.strftime('%d-%b-%Y'),
                            'direction': leg_direction,
                            'lots': leg_lots,
                            'valuation': leg_valuation
                        })
                    except (KeyError, ValueError):
                        continue
                
                # Get acceptable cost information
                acceptable_cost_adjustment = interest.get('acceptable_cost_adjustment', 0)
                acceptable_cost = total_valuation + acceptable_cost_adjustment
                
                # Get valuation constraints
                at_valuation_only = interest.get('at_valuation_only', False) or interest.get('at_val_only', False)
                max_loss_allowed = interest.get('max_loss_allowed', 0) or interest.get('max_loss', 0)
                
                # Ensure max_loss_allowed is negative for display consistency
                if max_loss_allowed > 0:
                    max_loss_allowed = -max_loss_allowed
                
                # Store the spread details
                spread_details[spread_id] = {
                    'status': status,
                    'user': user_id,
                    'metal': metal,
                    'pnl': pnl,
                    'legs': all_legs_in_spread,
                    'valuation': total_valuation,
                    'acceptable_cost_adjustment': acceptable_cost_adjustment,
                    'acceptable_cost': acceptable_cost,
                    'at_valuation_only': at_valuation_only,
                    'max_loss_allowed': max_loss_allowed
                }
                
                # Process each leg for timeline display
                for leg in interest.get('legs', []):
                    try:
                        start_date = datetime.fromisoformat(leg['start_date'])
                        end_date = datetime.fromisoformat(leg['end_date'])
                        
                        user_legs[user_id].append({
                            'start': start_date,
                            'end': end_date,
                            'direction': leg['direction'],
                            'lots': leg['lots'],
                            'metal': metal,
                            'spread_id': spread_id  # Link to the spread details
                        })
                    except (KeyError, ValueError):
                        continue
            
            # Create a figure with one trace per leg per user
            fig = go.Figure()
            
            # Create a list of all users to ensure consistent ordering
            users = sorted(user_legs.keys())
            
            # Use the consistent global date range for x-axis
            date_range_start = global_date_range_start
            date_range_end = global_date_range_end
            
            # For each user, add their legs as separate traces
            for user in users:
                # Skip users with no legs
                if not user_legs[user]:
                    continue
                
                # Capitalize the first letter of each user name for display
                display_user = user[0].upper() + user[1:] if user else user
                
                # Add each leg as a separate segment
                for leg in sorted(user_legs[user], key=lambda x: x['start']):
                    # Determine color based on direction
                    color = "blue" if leg['direction'] == 'Borrow' else "red"
                    
                    # Get the full spread details for this leg
                    spread_id = leg.get('spread_id', 'unknown')
                    spread_info = spread_details.get(spread_id, {})
                    
                    # Format spread valuation and cost information
                    total_valuation = spread_info.get('valuation', 0)
                    
                    # Format PnL with color
                    pnl_value = spread_info.get('pnl', 0)
                    formatted_pnl = format_pnl(pnl_value, for_hover=True)
                    
                    # Create detailed spread summary for hover text - initialized here to avoid NameError
                    legs_text = ""
                    for i, spread_leg in enumerate(spread_info.get('legs', [])):
                        leg_dir = spread_leg['direction']
                        leg_color = "blue" if leg_dir == 'Borrow' else "red"
                        leg_val = spread_leg.get('valuation', 0)
                        leg_val_color = "green" if leg_val > 0 else "red" if leg_val < 0 else "gray"
                        
                        # Check if this is the current leg being hovered
                        is_current_leg = (spread_leg['start'] == leg['start'].strftime('%d-%b-%Y') and 
                                          spread_leg['end'] == leg['end'].strftime('%d-%b-%Y') and
                                          spread_leg['direction'] == leg['direction'] and
                                          spread_leg['lots'] == leg['lots'])
                        
                        # Add arrow marker if it's the current leg, without using HTML tags
                        leg_prefix = "→ " if is_current_leg else ""
                        
                        legs_text += f"<br>{leg_prefix}Leg {spread_leg['leg_number']}: {leg_dir} {spread_leg['lots']} lots ({spread_leg['start']} to {spread_leg['end']}) - Val: ${leg_val:.2f}"
                    
                    # Format adjustment and acceptable cost
                    adjustment = spread_info.get('acceptable_cost_adjustment', 0)
                    adjustment_text = ""
                    user_constraints = ""
                    
                    # Check valuation constraints from spread details
                    at_valuation_only = spread_info.get('at_valuation_only', False)
                    max_loss_allowed = spread_info.get('max_loss_allowed', 0)
                    
                    # Safety check for max_loss_allowed
                    if max_loss_allowed > 0:
                        max_loss_allowed = -max_loss_allowed
                    
                    if at_valuation_only:
                        user_constraints = "<br>At Valuation Only: Yes"
                    elif max_loss_allowed < 0:
                        user_constraints = f"<br>Max Loss Allowed: ${max_loss_allowed:.2f}"
                    
                    if adjustment != 0:
                        direction = "Receiving" if adjustment > 0 else "Paying"
                        adjustment_text = f"<br>User {direction}: ${abs(adjustment):.2f}"
                    
                    acceptable_cost = spread_info.get('acceptable_cost', 0)
                    
                    # Create hover text with full spread information
                    hover_text = f"{display_user}'s {leg['metal']} Spread<br>" \
                                f"Status: {spread_info.get('status', 'Unknown')}<br>" \
                                f"Spread ID: {spread_id}<br>" \
                                f"P&L: {formatted_pnl}" \
                                f"{user_constraints}<br>" \
                                f"Valuation: ${total_valuation:.2f}" \
                                f"{adjustment_text}<br>" \
                                f"Final Cost: ${acceptable_cost:.2f}"
                                
                    # Add spread summary with proper line breaks
                    hover_text += f"<br><br>Spread Summary:{legs_text}"
                    
                    # Add segment as a line with markers at start and end
                    fig.add_trace(go.Scatter(
                        x=[leg['start'], leg['end']],
                        y=[display_user, display_user],  # Use capitalized user name
                        mode='lines',
                        line=dict(color=color, width=10),  # Thicker line for visibility
                        hoverinfo='text',
                        hovertext=hover_text,
                        showlegend=False
                    ))
            
            # If no users with legs, show a message but still display the date range
            if not users or all(not user_legs.get(user, []) for user in users):
                st.info(f"No trading data available for {selected_metal}")
                # Add a dummy invisible trace to maintain figure dimensions
                fig.add_trace(go.Scatter(
                    x=[date_range_start, date_range_end],
                    y=[0, 0],
                    mode='lines',
                    line=dict(color='rgba(0,0,0,0)'),  # Transparent
                    showlegend=False
                ))
            
            # Configure layout with chart template
            layout_updates = {
                'xaxis': dict(
                    title="Date",
                    range=[date_range_start, date_range_end],  # Consistent range across all tabs
                    tickformat="%d-%b",  # Day-Month format
                    tickangle=90,  # Make dates completely vertical
                    tickmode="array",  # Use custom tick values for more granularity
                    # Create ticks for every day
                    tickvals=[date_range_start + timedelta(days=i) for i in range(0, (date_range_end - date_range_start).days + 1, 1)],
                    ticktext=[(date_range_start + timedelta(days=i)).strftime("%d/%m") 
                             for i in range(0, (date_range_end - date_range_start).days + 1, 1)],
                    tickfont=dict(
                        size=12,  # Increased font size for dates
                        family="Arial",
                        color="black", # This will be overridden by dark theme template if needed
                    ),
                ),
                'yaxis': dict(
                    title="User",
                    categoryorder="array",
                    # Use capitalized user names for the y-axis
                    categoryarray=[user[0].upper() + user[1:] if user else user for user in users] if users else ["No Data"],
                    tickfont=dict(
                        size=18,  # Large font for user names
                        family="Arial",
                        color="black",
                        weight="bold",  # Bold text for better visibility
                    ),
                ),
                'height': max(400, 400 + (len(users) * 40)),  # Dynamic height based on user count
                'margin': dict(l=40, r=20, t=40, b=140),  # Very large bottom margin for larger font date labels
                'hoverlabel': dict(
                    bgcolor="white",
                    font_size=14,  # Larger hover text
                    font_family="Arial"
                ),
                'hovermode': "closest"
            }
            
            # Apply base layout
            fig.update_layout(**layout_updates)
            
            # Apply theme template if provided
            if chart_template:
                fig.update_layout(template=chart_template)
                
                # Fix plot background color to match white theme
                fig.update_layout(
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#ffffff",
                    font=dict(color="#262730"),
                    yaxis=dict(
                        tickfont=dict(color="#262730", size=18, family="Arial", weight="bold")
                    ),
                    xaxis=dict(
                        tickfont=dict(color="#262730", size=12)
                    ),
                    hoverlabel=dict(
                        bgcolor="#ffffff",
                        font_color="#262730"
                    )
                )
            
            # Add weekend and UK bank holiday highlighting
            all_dates = pd.date_range(start=date_range_start, end=date_range_end, freq='D')
            
            # Highlight weekends
            for date in all_dates:
                if date.weekday() >= 5:  # Saturday (5) or Sunday (6)
                    fig.add_shape(
                        type="rect",
                        xref="x",
                        yref="paper",
                        x0=date - timedelta(hours=12),  # Start slightly before the date
                        x1=date + timedelta(hours=12),  # End slightly after the date
                        y0=0,
                        y1=1,
                        fillcolor="lightgrey",
                        opacity=0.2,
                        layer="below",
                        line_width=0,
                    )
            
            # UK Bank Holidays for 2025 (add or adjust as needed)
            uk_bank_holidays_2025 = [
                datetime(2025, 1, 1),   # New Year's Day
                datetime(2025, 4, 18),  # Good Friday
                datetime(2025, 4, 21),  # Easter Monday
                datetime(2025, 5, 5),   # Early May Bank Holiday
                datetime(2025, 5, 26),  # Spring Bank Holiday
                datetime(2025, 8, 25),  # Summer Bank Holiday
                datetime(2025, 12, 25), # Christmas Day
                datetime(2025, 12, 26), # Boxing Day
            ]
            
            # Add bank holiday highlighting and annotations
            for holiday_date in uk_bank_holidays_2025:
                if date_range_start <= holiday_date <= date_range_end:
                    # Add holiday background
                    fig.add_shape(
                        type="rect",
                        xref="x",
                        yref="paper",
                        x0=holiday_date - timedelta(hours=12),
                        x1=holiday_date + timedelta(hours=12),
                        y0=0,
                        y1=1,
                        fillcolor="lightyellow",
                        opacity=0.4,
                        layer="below",
                        line_width=0,
                    )
            
            # Add Cash Date vertical line - use simple label
            fig.add_shape(
                type="line",
                x0=cash_date,
                x1=cash_date,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(color="blue", width=2, dash="dash"),
            )
            
            # Add annotation for Cash Date - simpler label
            fig.add_annotation(
                x=cash_date,
                y=1.05,
                yref="paper",
                text="C",
                showarrow=False,
                font=dict(color="blue", size=16, family="Arial Black")
            )
            
            # Add 3M Date vertical line - ensure visibility
            fig.add_shape(
                type="line",
                x0=three_m_date,
                x1=three_m_date,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(color="purple", width=3, dash="dash"),
            )
            
            # Add annotation for 3M Date - simpler label
            fig.add_annotation(
                x=three_m_date,
                y=1.05,
                yref="paper",
                text="3M",
                showarrow=False,
                font=dict(color="purple", size=16, family="Arial Black")
            )
            
            # Add all the third Wednesdays
            for wednesday in third_wednesdays:
                # Add Third Wednesday vertical line
                fig.add_shape(
                    type="line",
                    x0=wednesday['date'],
                    x1=wednesday['date'],
                    y0=0,
                    y1=1,
                    yref="paper",
                    line=dict(color="orange", width=1.5, dash="dot"),
                )
                
                # Add annotation for Third Wednesday - just month name
                fig.add_annotation(
                    x=wednesday['date'],
                    y=1.05,
                    yref="paper",
                    text=wednesday['date'].strftime('%b'),  # Use the date's month directly
                    showarrow=False,
                    font=dict(color="orange", size=14)
                )
            
            # Use a unique key for each metal tab's chart to prevent StreamlitDuplicateElementId errors
            st.plotly_chart(fig, use_container_width=True, key=f"timeline_{selected_metal}_{i}")
            
            # Add legend/key for the chart markers below the chart
            st.markdown("""
            <style>
            .legend-item {
                display: flex;
                align-items: center;
                margin-bottom: 8px;
            }
            .legend-color {
                display: inline-block;
                width: 20px;
                height: 20px;
                margin-right: 8px;
            }
            .legend-line {
                display: inline-block;
                width: 30px;
                height: 3px;
                margin-right: 8px;
            }
            .legend-dash {
                border-top: 3px dashed;
                width: 30px;
                height: 1px;
                display: inline-block;
                margin-right: 8px;
            }
            .legend-dot {
                border-top: 3px dotted;
                width: 30px;
                height: 1px;
                display: inline-block;
                margin-right: 8px;
            }
            .legend-container {
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: #ffffff;
                margin-top: 10px;
                color: #262730;
            }
            </style>
            
            <div class="legend-container">
                <div class="legend-item">
                    <div class="legend-line" style="background-color: blue;"></div>
                    <span>Borrowing</span>
                </div>
                <div class="legend-item">
                    <div class="legend-line" style="background-color: red;"></div>
                    <span>Lending</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: lightgrey; opacity: 0.4;"></div>
                    <span>Weekend</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: lightyellow; opacity: 0.6;"></div>
                    <span>UK Bank Holiday</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dash" style="border-color: blue;"></div>
                    <span>Cash Date (C)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dash" style="border-color: purple;"></div>
                    <span>3-Month Date (3M)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-dot" style="border-color: orange;"></div>
                    <span>3rd Wednesday (Month)</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # Add explanation below the tabs - simplified since we now have a proper legend
    st.info("""
    This timeline shows trading activity by user. Each row represents a different user.
    Hover over segments to see details, and use tabs above to filter by metal.
    """)

# Helper function to display a tooltip
def tooltip(text, help_text):
    """Display text with a tooltip."""
    return f"{text} " + f'<span data-toggle="tooltip" title="{help_text}">ℹ️</span>'

def create_chart_template():
    """Create chart templates for better contrast."""
    template = {
        'layout': {
            'paper_bgcolor': '#ffffff',
            'plot_bgcolor': '#ffffff',
            'font': {'color': '#262730'},
            'title': {'font': {'color': '#262730'}},
            'legend': {'font': {'color': '#262730'}},
            'xaxis': {
                'gridcolor': '#e6e6e6',
                'zerolinecolor': '#999999',
                'title': {'font': {'color': '#262730'}},
                'tickfont': {'color': '#262730', 'size': 12}
            },
            'yaxis': {
                'gridcolor': '#e6e6e6',
                'zerolinecolor': '#999999',
                'title': {'font': {'color': '#262730'}},
                'tickfont': {'color': '#262730'}
            }
        }
    }
    return template

def main():
    """Main dashboard application."""
    # Initialize session state
    init_session_state()
    
    # Apply theme based on dark/light mode preference
    apply_theme()
    
    # Create chart template based on theme
    chart_template = create_chart_template()
    
    # Title and header
    st.title("LME Spread Trading Dashboard")
    
    # Auto-refresh the dashboard
    auto_refresh()
    
    # Sidebar with controls
    with st.sidebar:
        st.header("Dashboard Controls")
        
        # Ensure dark mode is always on
        st.session_state.dark_mode = True
            
        st.divider()
        
        # Allow changing refresh interval
        st.session_state.refresh_interval = st.slider(
            "Refresh Interval (seconds)",
            min_value=10,
            max_value=300,
            value=st.session_state.refresh_interval,
            step=10
        )
        
        # Toggle auto-refresh
        st.session_state.auto_refresh = st.toggle(
            "Auto-refresh",
            value=st.session_state.auto_refresh
        )
        
        # Manual refresh button
        if st.button("🔄 Refresh Data Now"):
            with st.spinner("Refreshing data..."):
                st.session_state.pending_interests = get_pending_interests()
                st.session_state.last_refresh = datetime.now()
                st.rerun()
        
        if st.session_state.last_refresh:
            st.write(f"Last refreshed: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
        
        # View selector
        st.subheader("View Selection")
        view_options = {
            "overview": "Market Overview",
            "matches": "Matching Opportunities",
            "axes": "Market Axes",
            "risk": "Risk Analysis",
            "timeline": "User Timeline"
        }
        
        selected_view = st.radio(
            "Select Dashboard View:",
            options=list(view_options.keys()),
            format_func=lambda x: view_options[x],
            index=list(view_options.keys()).index(st.session_state.current_view)
        )
        
        if selected_view != st.session_state.current_view:
            st.session_state.current_view = selected_view
            st.rerun()
    
    # Main content based on selected view
    if st.session_state.current_view == "overview":
        # Get all orders
        with st.spinner("Loading market data..."):
            all_orders = get_all_orders()
        
        # Add export functionality
        col1, col2, col3, export_col = st.columns([1, 1, 1, 1])
        with export_col:
            export_df = export_orders_to_csv(all_orders)
            st.markdown(
                get_csv_download_link(export_df, "market_overview.csv", "📥 Export Data"),
                unsafe_allow_html=True
            )
        
        # Display market overview
        st.header("Market Overview")
        display_market_heatmap(all_orders, chart_template)
        
        # Display summary statistics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Active Orders",
                len(all_orders),
                delta=None
            )
        
        # Count total lots involved
        total_lots = 0
        for order in all_orders:
            for leg in order.get('legs', []):
                total_lots += leg.get('lots', 0)
        
        with col2:
            st.metric(
                "Total Lots",
                total_lots,
                delta=None
            )
        
        # Count unique users
        unique_users = set()
        for order in all_orders:
            unique_users.add(order.get('user_id', 'unknown'))
        
        with col3:
            st.metric(
                "Active Users",
                len(unique_users),
                delta=None
            )
    
    elif st.session_state.current_view == "matches":
        # Get all interests
        with st.spinner("Loading matching opportunities..."):
            all_orders = get_all_orders()
            # Find and display matching opportunities
            opportunities = find_matching_opportunities(all_orders)
        
        # Add export functionality
        col1, export_col = st.columns([3, 1])
        with export_col:
            # Create a DataFrame from opportunities
            if opportunities:
                opp_data = []
                for opp in opportunities:
                    opp_data.append({
                        'order1_id': opp.get('order1', {}).get('spread_id', 'unknown'),
                        'order2_id': opp.get('order2', {}).get('spread_id', 'unknown'),
                        'metal': opp.get('metal', 'unknown'),
                        'user1': opp.get('order1', {}).get('user_id', 'unknown'),
                        'user2': opp.get('order2', {}).get('user_id', 'unknown'),
                        'match_score': opp.get('match_score', 0),
                        'overlap_days': opp.get('overlap_days', 0),
                    })
                opp_df = pd.DataFrame(opp_data)
                st.markdown(
                    get_csv_download_link(opp_df, "matching_opportunities.csv", "📥 Export Matches"),
                    unsafe_allow_html=True
                )
        
        st.header("Matching Opportunities")
        display_matching_opportunities(opportunities)
    
    elif st.session_state.current_view == "axes":
        # Get all interests
        with st.spinner("Loading market axes data..."):
            all_orders = get_all_orders()
        
        # Add export functionality
        col1, export_col = st.columns([3, 1])
        with export_col:
            export_df = export_orders_to_csv(all_orders)
            st.markdown(
                get_csv_download_link(export_df, "market_axes.csv", "📥 Export Data"),
                unsafe_allow_html=True
            )
        
        # Display market axes
        st.header("Market Axes Analysis")
        display_market_axes(all_orders, chart_template)
    
    elif st.session_state.current_view == "risk":
        # Get all interests
        with st.spinner("Loading risk analysis data..."):
            all_orders = get_all_orders()
        
        # Add export functionality
        col1, export_col = st.columns([3, 1])
        with export_col:
            export_df = export_orders_to_csv(all_orders)
            st.markdown(
                get_csv_download_link(export_df, "risk_analysis.csv", "📥 Export Risk Data"),
                unsafe_allow_html=True
            )
        
        # Display risk analysis
        st.header("Risk Analysis")
        display_risk_analysis(all_orders, chart_template)
    
    elif st.session_state.current_view == "timeline":
        # Get all interests
        with st.spinner("Loading timeline data..."):
            all_orders = get_all_orders()
        
        # Add export functionality
        col1, export_col = st.columns([3, 1])
        with export_col:
            export_df = export_orders_to_csv(all_orders)
            st.markdown(
                get_csv_download_link(export_df, "user_timeline.csv", "📥 Export Timeline"),
                unsafe_allow_html=True
            )
        
        # Display user timeline
        st.header("User Trading Timeline")
        display_user_timeline(all_orders, chart_template)

# Helper function to generate a download link for a dataframe
def get_csv_download_link(df, filename, text):
    """Generate a link to download the dataframe as a CSV file."""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()  # Encode to base64
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{text}</a>'
    return href

# Helper function to export orders data to CSV
def export_orders_to_csv(orders):
    """Export orders data to CSV format."""
    # Create a list to store flattened order data
    flat_orders = []
    
    for order in orders:
        spread_id = order.get('spread_id', 'unknown')
        user_id = order.get('user_id', 'unknown')
        metal = order.get('metal', 'unknown')
        status = order.get('status', 'unknown')
        submit_time = order.get('submit_time', '')
        pnl = order.get('pnl', 0)
        
        # For each leg in the order, create a row
        for i, leg in enumerate(order.get('legs', [])):
            try:
                start_date = leg.get('start_date', '')
                end_date = leg.get('end_date', '')
                direction = leg.get('direction', '')
                lots = leg.get('lots', 0)
                
                flat_orders.append({
                    'spread_id': spread_id,
                    'user_id': user_id,
                    'metal': metal,
                    'status': status,
                    'submit_time': submit_time,
                    'pnl': pnl,
                    'leg_number': i+1,
                    'start_date': start_date,
                    'end_date': end_date,
                    'direction': direction,
                    'lots': lots
                })
            except Exception as e:
                print(f"Error processing leg: {str(e)}")
    
    return pd.DataFrame(flat_orders)

def analyze_risk_exposure(orders: List[Dict]) -> Dict:
    """
    Analyze risk exposure across metals and dates.
    Returns metrics including net position by date, VaR, and exposure concentration.
    """
    if not orders:
        return {}
    
    # Create a date range covering all orders
    all_dates = []
    for order in orders:
        for leg in order.get('legs', []):
            try:
                start_date = datetime.fromisoformat(leg['start_date'])
                end_date = datetime.fromisoformat(leg['end_date'])
                all_dates.extend([start_date, end_date])
            except (ValueError, KeyError):
                continue
    
    if not all_dates:
        return {}
    
    min_date = min(all_dates)
    max_date = max(all_dates)
    date_range = pd.date_range(start=min_date, end=max_date, freq='D')
    
    # Initialize metrics
    net_position_by_date = {metal: {date: 0 for date in date_range} for metal in METALS}
    risk_metrics = {
        'var_95': 0,
        'max_exposure': 0,
        'concentration_index': 0
    }
    
    # Calculate net position for each metal and date
    for order in orders:
        metal = order.get('metal', 'Unknown')
        if metal not in METALS:
            continue
        
        for leg in order.get('legs', []):
            try:
                start_date = datetime.fromisoformat(leg['start_date'])
                end_date = datetime.fromisoformat(leg['end_date'])
                direction = leg['direction']
                lots = leg['lots']
                
                # Determine sign - borrowing is positive, lending is negative
                sign = 1 if direction == 'Borrow' else -1
                position = lots * sign
                
                # Add position to each date in the leg's range
                leg_dates = pd.date_range(start=start_date, end=end_date, freq='D')
                for date in leg_dates:
                    if date in date_range:
                        net_position_by_date[metal][date] += position
            except (ValueError, KeyError):
                continue
    
    # Convert to DataFrame for easier analysis
    position_data = []
    for metal, positions in net_position_by_date.items():
        for date, position in positions.items():
            if position != 0:  # Only include non-zero positions
                position_data.append({
                    'Metal': metal,
                    'Date': date,
                    'Position': position
                })
    
    position_df = pd.DataFrame(position_data)
    
    # If no positions, return empty metrics
    if position_df.empty:
        return {
            'net_position_by_date': net_position_by_date,
            'metrics': risk_metrics,
            'position_df': pd.DataFrame()
        }
    
    # Calculate risk metrics
    # VaR - Simplified calculation (95th percentile of positions)
    all_positions = np.abs(position_df['Position'].values)
    if len(all_positions) > 0:
        risk_metrics['var_95'] = np.percentile(all_positions, 95)
        risk_metrics['max_exposure'] = np.max(all_positions)
        
        # Concentration index - Herfindahl-Hirschman Index (HHI)
        # Higher value means more concentration in specific metals/dates
        total_exposure = np.sum(all_positions)
        if total_exposure > 0:
            metal_exposure = position_df.groupby('Metal')['Position'].apply(lambda x: np.sum(np.abs(x))).reset_index()
            metal_shares = metal_exposure['Position'] / total_exposure
            risk_metrics['concentration_index'] = np.sum(metal_shares ** 2) * 100  # Scale to 0-100
    
    return {
        'net_position_by_date': net_position_by_date,
        'metrics': risk_metrics,
        'position_df': position_df
    }

def display_risk_analysis(orders: List[Dict], chart_template=None):
    """Display risk analysis dashboard."""
    st.subheader("Risk Analysis Dashboard")
    
    # Run risk analysis
    with st.spinner("Analyzing risk exposure..."):
        risk_data = analyze_risk_exposure(orders)
    
    if not risk_data or risk_data.get('position_df') is None or risk_data.get('position_df').empty:
        st.warning("No position data available for risk analysis")
        return
    
    # Display risk metrics
    metrics = risk_data.get('metrics', {})
    position_df = risk_data.get('position_df', pd.DataFrame())
    
    # Risk metrics cards
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Value at Risk (95%)",
            f"{metrics.get('var_95', 0):.0f} lots",
            delta=None
        )
    
    with col2:
        st.metric(
            "Maximum Exposure",
            f"{metrics.get('max_exposure', 0):.0f} lots",
            delta=None
        )
    
    with col3:
        concentration = metrics.get('concentration_index', 0)
        level = "Low" if concentration < 25 else "Medium" if concentration < 50 else "High"
        st.metric(
            "Concentration Risk",
            f"{concentration:.1f} ({level})",
            delta=None
        )
    
    # Plot net position by metal and date
    st.subheader("Net Position Heat Map")
    
    try:
        # Pivot data for heatmap
        pivot_df = position_df.pivot_table(
            values="Position", 
            index="Metal", 
            columns="Date", 
            fill_value=0
        )
        
        if not pivot_df.empty:
            # Create heatmap
            fig = px.imshow(
                pivot_df,
                labels=dict(x="Date", y="Metal", color="Net Position (Lots)"),
                color_continuous_scale="RdBu_r",  # Red for negative, blue for positive
                aspect="auto"
            )
            
            # Apply theme template if provided
            if chart_template:
                fig.update_layout(template=chart_template)
                
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No position data available for heatmap visualization")
    except Exception as e:
        st.error(f"Error creating heatmap: {str(e)}")
    
    # Plot exposure by metal
    st.subheader("Exposure by Metal")
    
    try:
        if not position_df.empty and 'Metal' in position_df.columns and 'Position' in position_df.columns:
            metal_exposure = position_df.groupby('Metal')['Position'].agg(['sum', 'min', 'max']).reset_index()
            metal_exposure['abs_sum'] = metal_exposure['sum'].abs()
            metal_exposure = metal_exposure.sort_values('abs_sum', ascending=False)
            
            fig2 = px.bar(
                metal_exposure,
                x="Metal",
                y="sum",
                color="sum",
                color_continuous_scale="RdBu_r",  # Red for negative, blue for positive
                labels={"sum": "Net Position (Lots)", "Metal": "Metal"},
                title="Net Position by Metal"
            )
            
            # Apply theme template if provided
            if chart_template:
                fig2.update_layout(template=chart_template)
            
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Insufficient data for exposure analysis")
    except Exception as e:
        st.error(f"Error creating exposure chart: {str(e)}")

if __name__ == "__main__":
    main() 