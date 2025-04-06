import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Fix for the fitz import issue
try:
    import fitz
except ImportError:
    import PyMuPDF as fitz

from src.core_engine import (
    get_pending_interests,
    respond_to_interest,
    price_spread,
    TONS_PER_LOT
)

# Page configuration
st.set_page_config(
    page_title="LME Spread Trading - Market Maker",
    page_icon="📊",
    layout="wide"
)

# Session state initialization
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'position_data' not in st.session_state:
    st.session_state.position_data = None
if 'pending_interests' not in st.session_state:
    st.session_state.pending_interests = []
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = None

# List of available metals
METALS = ["Aluminum", "Copper", "Zinc", "Nickel", "Lead", "Tin"]

def format_date(date_str: str) -> str:
    """Format date string for display."""
    try:
        date = datetime.fromisoformat(date_str)
        return date.strftime('%d-%b-%y')
    except (ValueError, TypeError):
        return date_str

def format_pnl(pnl: float) -> str:
    """Format PnL value with color."""
    color = "green" if pnl > 0 else "red" if pnl < 0 else "gray"
    return f"<span style='color:{color}'>${pnl:.2f}</span>"

def login_screen():
    """Display the login screen for market maker."""
    st.title("LME Spread Trading Platform - Market Maker")
    
    st.header("Market Maker Login")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        user_id = st.selectbox(
            "Select Market Maker ID",
            options=["", "marketmaker"],
            index=0,
            help="Select your market maker ID"
        )
        
        if user_id and st.button("Login"):
            st.session_state.user_id = user_id
            st.success(f"Logged in as {user_id}")
            time.sleep(1)  # Brief pause for UX
            st.rerun()
    
    with col2:
        st.info("This is a simulation of a login. In a real system, this would require authentication.")

def parse_csv_positions(uploaded_file) -> pd.DataFrame:
    """Parse CSV file with position data."""
    try:
        df = pd.read_csv(uploaded_file)
        
        # Validate required columns
        required_columns = ["Metal", "Date", "Position"]
        for col in required_columns:
            if col not in df.columns:
                st.error(f"Missing required column: {col}")
                return None
        
        # Convert date to datetime
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
        
        # Ensure Position is numeric
        df['Position'] = pd.to_numeric(df['Position'], errors='coerce')
        
        # Filter out invalid rows
        df = df.dropna(subset=['Date', 'Position'])
        
        return df
    except Exception as e:
        st.error(f"Error parsing CSV: {str(e)}")
        return None

def display_position_chart(position_data: pd.DataFrame):
    """Display chart of market maker positions by date."""
    if position_data is None or position_data.empty:
        st.warning("No position data available")
        return
    
    # Group by metal and date
    fig = px.bar(
        position_data, 
        x="Date", 
        y="Position",
        color="Metal",
        barmode="group",
        title="Market Maker Position by Date",
        labels={"Position": "Position (Lots)", "Date": "Date"}
    )
    
    # Customize layout
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Position (Lots)",
        legend_title="Metal",
        hovermode="closest"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Also display as a heatmap for a different view
    pivot_df = position_data.pivot_table(
        values="Position", 
        index="Metal", 
        columns="Date", 
        fill_value=0
    )
    
    fig2 = px.imshow(
        pivot_df,
        labels=dict(x="Date", y="Metal", color="Position (Lots)"),
        title="Position Heatmap",
        color_continuous_scale="RdBu_r",  # Blue for positive, red for negative
        aspect="auto"
    )
    
    st.plotly_chart(fig2, use_container_width=True)

def display_interest_heatmap(interests: List[Dict]):
    """Display heatmap of all interests by date range and metal."""
    if not interests:
        st.warning("No interests available")
        return
    
    # Collect all legs from all interests
    all_legs = []
    for interest in interests:
        metal = interest.get('metal', 'Unknown')
        
        for leg in interest.get('legs', []):
            try:
                start_date = datetime.fromisoformat(leg['start_date'])
                end_date = datetime.fromisoformat(leg['end_date'])
                
                all_legs.append({
                    'Metal': metal,
                    'Start': start_date,
                    'End': end_date,
                    'Direction': leg['direction'],
                    'Lots': leg['lots']
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
        title="Market Interest Heatmap",
        color_continuous_scale="RdBu_r",  # Blue for lend interest, red for borrow interest
        aspect="auto"
    )
    
    st.plotly_chart(fig, use_container_width=True)

def calculate_impact(position_data: pd.DataFrame, interest: Dict) -> Tuple[float, pd.DataFrame]:
    """
    Calculate the impact of accepting an interest on the market maker's position.
    Returns (P&L impact, new positions dataframe)
    """
    if position_data is None or position_data.empty:
        return 0.0, None
    
    # Create a copy of position data to modify
    new_positions = position_data.copy()
    
    # Extract interest details
    metal = interest.get('metal', 'Unknown')
    legs = interest.get('legs', [])
    
    # Filter positions for this metal
    metal_positions = new_positions[new_positions['Metal'] == metal].copy()
    
    if metal_positions.empty:
        st.warning(f"No existing positions for {metal}")
        return 0.0, position_data
    
    # Calculate total P&L impact
    total_impact = 0.0
    
    # For each leg, adjust the positions
    for leg in legs:
        try:
            start_date = datetime.fromisoformat(leg['start_date'])
            end_date = datetime.fromisoformat(leg['end_date'])
            lots = leg['lots']
            direction = leg['direction']
            
            # Determine sign - if user wants to borrow, MM lends (positive)
            mm_sign = 1 if direction == 'Borrow' else -1
            mm_lots = lots * mm_sign
            
            # Get all dates in the leg's range that exist in our position data
            dates_in_range = metal_positions[
                (metal_positions['Date'] >= start_date) & 
                (metal_positions['Date'] <= end_date)
            ]['Date'].unique()
            
            # For each date, adjust the position
            for date in dates_in_range:
                # Find the row for this date
                date_mask = (new_positions['Metal'] == metal) & (new_positions['Date'] == date)
                
                if date_mask.any():
                    # Calculate P&L impact - simplified estimation
                    current_pos = new_positions.loc[date_mask, 'Position'].values[0]
                    
                    # If current position and adjustment have opposite signs, this reduces risk
                    if current_pos * mm_lots < 0:
                        # Reduction in risk is positive impact
                        impact = min(abs(current_pos), abs(mm_lots)) * 0.1  # Simplified value
                        total_impact += impact
                    else:
                        # Increase in risk is negative impact
                        impact = -abs(mm_lots) * 0.05  # Simplified value
                        total_impact += impact
                    
                    # Update position
                    new_positions.loc[date_mask, 'Position'] += mm_lots
        
        except (KeyError, ValueError) as e:
            st.error(f"Error processing leg: {str(e)}")
    
    return total_impact, new_positions

def display_interests(interests, tab_name="all"):
    """Display a list of spread interests with expandable details."""
    if not interests:
        st.info("No interests found for this metal.")
        return
    
    # Display each interest in an expander
    for i, interest in enumerate(interests):
        user_id = interest.get('user_id', 'Unknown')
        metal = interest.get('metal', 'Unknown')
        spread_id = interest.get('spread_id', f"unknown_{i}")
        submit_time = interest.get('submit_time', 'Unknown')
        legs = interest.get('legs', [])
        
        # Create a readable title
        if isinstance(submit_time, str):
            try:
                submit_time = datetime.fromisoformat(submit_time).strftime('%d-%b-%y %H:%M')
            except ValueError:
                pass
        
        title = f"#{spread_id}: {user_id} - {metal} - {len(legs)} legs - {submit_time}"
        
        # Create a unique key for this interest that includes tab name and index
        unique_key = f"{tab_name}_{metal}_{spread_id}_{i}"
        
        with st.expander(title):
            col1, col2 = st.columns([3, 2])
            
            with col1:
                st.subheader("Spread Details")
                
                # Build a table of legs
                leg_data = []
                for leg in legs:
                    try:
                        start_date = datetime.fromisoformat(leg['start_date'])
                        end_date = datetime.fromisoformat(leg['end_date'])
                        
                        leg_data.append({
                            "Leg": leg.get('id', '?'),
                            "Direction": leg.get('direction', 'Unknown'),
                            "Start": start_date.strftime('%d-%b-%y'),
                            "End": end_date.strftime('%d-%b-%y'),
                            "Days": (end_date - start_date).days,
                            "Lots": leg.get('lots', 0)
                        })
                    except (KeyError, ValueError) as e:
                        st.error(f"Error parsing leg data: {str(e)}")
                
                if leg_data:
                    st.table(pd.DataFrame(leg_data))
                
                # Valuation and submission options
                valuation_pnl = interest.get('valuation_pnl', 0.0)
                at_val_only = interest.get('at_val_only', False)
                max_loss = interest.get('max_loss', 0.0)
                
                st.write(f"Valuation P&L: {format_pnl(valuation_pnl)}", unsafe_allow_html=True)
                st.write(f"At Valuation Only: {'Yes' if at_val_only else 'No'}")
                
                if not at_val_only:
                    st.write(f"Max Loss Allowed: ${max_loss:.2f}")
            
            with col2:
                st.subheader("Impact Analysis")
                
                if st.session_state.position_data is not None:
                    impact, new_positions = calculate_impact(
                        st.session_state.position_data, interest
                    )
                    
                    impact_color = "green" if impact > 0 else "red" if impact < 0 else "gray"
                    st.markdown(f"**P&L Impact:** <span style='color:{impact_color}'>${impact:.2f}</span>", unsafe_allow_html=True)
                    
                    if impact > 0:
                        st.success("This trade would reduce your risk.")
                    elif impact < 0:
                        st.warning("This trade would increase your risk.")
                    else:
                        st.info("This trade has neutral impact on your position.")
                else:
                    st.warning("Upload position data to see impact analysis.")
                
                # Response form
                st.subheader("Respond to Interest")
                
                response_type = st.radio(
                    "Response Type",
                    options=["Accept", "Counter", "Reject"],
                    horizontal=True,
                    key=f"response_type_{unique_key}"
                )
                
                if response_type == "Counter":
                    # Counter offer form
                    counter_pnl = st.number_input(
                        "Counter P&L ($)",
                        value=float(max(valuation_pnl - 200, -1000)),  # Default to a worse offer
                        step=10.0,
                        key=f"counter_pnl_{unique_key}"
                    )
                    
                    message = st.text_input(
                        "Message (Optional)",
                        value="I can do this trade at a different rate.",
                        key=f"counter_message_{unique_key}"
                    )
                    
                    if st.button("Send Counter", key=f"send_counter_{unique_key}"):
                        response = {
                            "status": "Countered",
                            "counter_pnl": counter_pnl,
                            "message": message
                        }
                        
                        try:
                            success = respond_to_interest(spread_id, response)
                            if success:
                                st.success("Counter offer sent successfully")
                            else:
                                st.error("Failed to send counter offer")
                        except Exception as e:
                            st.error(f"Error sending counter: {str(e)}")
                
                elif response_type == "Accept":
                    if st.button("Accept Interest", key=f"accept_{unique_key}"):
                        response = {
                            "status": "Accepted",
                            "message": "Your spread interest has been accepted at the requested valuation."
                        }
                        
                        try:
                            success = respond_to_interest(spread_id, response)
                            if success:
                                st.success("Interest accepted successfully")
                            else:
                                st.error("Failed to accept interest")
                        except Exception as e:
                            st.error(f"Error accepting interest: {str(e)}")
                
                elif response_type == "Reject":
                    reason = st.text_input(
                        "Rejection Reason (Optional)",
                        value="Unable to accommodate this spread at this time.",
                        key=f"reject_reason_{unique_key}"
                    )
                    
                    if st.button("Reject Interest", key=f"reject_{unique_key}"):
                        response = {
                            "status": "Rejected",
                            "message": reason
                        }
                        
                        try:
                            success = respond_to_interest(spread_id, response)
                            if success:
                                st.success("Interest rejected successfully")
                            else:
                                st.error("Failed to reject interest")
                        except Exception as e:
                            st.error(f"Error rejecting interest: {str(e)}")

def main_app():
    """Main application interface for market maker."""
    st.title(f"LME Spread Trading - Market Maker: {st.session_state.user_id}")
    
    # Sidebar for position data upload
    with st.sidebar:
        st.header("Position Management")
        
        uploaded_file = st.file_uploader("Upload Position Data (CSV)", type="csv")
        if uploaded_file:
            if st.button("Process Position Data"):
                position_data = parse_csv_positions(uploaded_file)
                if position_data is not None:
                    st.session_state.position_data = position_data
                    st.success(f"Loaded position data: {len(position_data)} rows")
        
        # Refresh interests button
        st.header("Spread Interests")
        if st.button("🔄 Refresh Interests"):
            with st.spinner("Loading interests..."):
                st.session_state.pending_interests = get_pending_interests()
                st.session_state.last_refresh = datetime.now()
    
    # Main area - split into tabs for positions and interests
    main_tab1, main_tab2 = st.tabs(["Positions & Market Overview", "Incoming Interests"])
    
    # Tab 1: Positions and Market Overview
    with main_tab1:
        st.header("Market Maker Positions")
        
        if st.session_state.position_data is not None:
            display_position_chart(st.session_state.position_data)
            
            # Show positions table
            st.subheader("Position Details")
            st.dataframe(st.session_state.position_data)
        else:
            st.info("Upload position data to see your current exposures.")
        
        # Show interest heatmap if we have pending interests
        if st.session_state.pending_interests:
            st.header("Market Interest Overview")
            display_interest_heatmap(st.session_state.pending_interests)
    
    # Tab 2: Incoming Interests - organized by metal
    with main_tab2:
        st.header("Incoming Spread Interests")
        
        if st.session_state.last_refresh:
            st.write(f"Last refreshed: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
        
        if not st.session_state.pending_interests:
            st.info("No pending interests found. Click 'Refresh Interests' to check for new requests.")
        else:
            # Group interests by metal
            interests_by_metal = {}
            for interest in st.session_state.pending_interests:
                metal = interest.get('metal', 'Unknown')
                if metal not in interests_by_metal:
                    interests_by_metal[metal] = []
                interests_by_metal[metal].append(interest)
            
            # Create tabs for each metal
            if interests_by_metal:
                # Sort metals to ensure consistent order
                sorted_metals = sorted(interests_by_metal.keys())
                
                # Create a "All Metals" tab first
                tabs = ["All Metals"] + sorted_metals
                metal_tabs = st.tabs(tabs)
                
                # Display all interests in the first tab
                with metal_tabs[0]:
                    display_interests(st.session_state.pending_interests, "all_metals")
                
                # Display interests for each metal in its own tab
                for i, metal in enumerate(sorted_metals):
                    with metal_tabs[i+1]:
                        metal_interests = interests_by_metal[metal]
                        display_interests(metal_interests, f"metal_{metal}")

# Main app flow
def main():
    """Main application flow control."""
    if st.session_state.user_id is None:
        login_screen()
    else:
        main_app()
        
        # Logout option in sidebar
        with st.sidebar:
            if st.button("Logout"):
                st.session_state.user_id = None
                st.rerun()

if __name__ == "__main__":
    main() 