import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import json
from pathlib import Path
import sqlite3
import sys
import argparse

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description="LME Spread Trading User App")
    parser.add_argument("--app_name", type=str, default="User App", help="Application name")
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
    submit_spread_interest,
    price_spread,
    get_user_spread_history,
    extract_c3m_rates_from_pdf,
    TONS_PER_LOT
)

# Page configuration
st.set_page_config(
    page_title=f"User",
    page_icon="📈",
    layout="wide"
)

# Add custom CSS to reduce white space and padding
st.markdown("""
<style>
    /* Reduce padding in the main content area */
    .main .block-container {
        padding-top: 1rem;
        padding-right: 1rem;
        padding-left: 1rem;
        padding-bottom: 1rem;
    }
    
    /* Reduce padding around tables */
    [data-testid="stTable"] {
        margin-top: 0.5rem;
        margin-bottom: 0.5rem;
    }
    
    /* Reduce margins around headers */
    h1, h2, h3, h4, h5, h6 {
        margin-top: 0.5rem;
        margin-bottom: 0.5rem;
    }
    
    /* Make expanders more compact */
    .streamlit-expanderHeader {
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
    }
    
    /* Make form elements more compact */
    .stButton, .stSelectbox, .stDateInput, .stNumberInput {
        margin-bottom: 0.5rem;
    }
    
    /* Reduce spacing around containers */
    .stContainer {
        padding-top: 0.25rem;
        padding-bottom: 0.25rem;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'rates_loaded' not in st.session_state:
    st.session_state.rates_loaded = False
if 'current_carries' not in st.session_state:
    st.session_state.current_carries = [{"id": 1, "metal": "Aluminum", "legs": [{"id": 1}, {"id": 2}]}]
if "expander_states" not in st.session_state:
    st.session_state.expander_states = {}

# List of available metals
METALS = ["Aluminum", "Copper", "Lead", "Nickel", "Tin", "Zinc"]

def format_date(date):
    """Format date in DD-MMM-YY format for display."""
    return date.strftime('%d-%b-%y')

def format_pnl(pnl):
    """Format PnL value with color."""
    if pnl is None:
        return "<span style='color:gray'>$0.00 (unknown)</span>"
    
    color = "green" if pnl > 0 else "red" if pnl < 0 else "gray"
    return f"<span style='color:{color}'>${pnl:.2f}</span>"

def login_screen():
    """Display the login screen to select a user."""
    st.title("LME Spread Trading Platform")
    
    st.header("User Login")
    
    col1, col2 = st.columns([2, 1])
    
    # Get all available users from the database
    conn = sqlite3.connect("spread_trading.db")
    cursor = conn.cursor()
    
    # Get all users
    cursor.execute("SELECT user_id, name, affiliation FROM users ORDER BY user_id")
    user_data = cursor.fetchall()
    conn.close()
    
    # Create a list of user_ids
    user_ids = [""] + [user[0] for user in user_data]
    
    # Create a mapping of user_id to display text with affiliation
    user_display = {user[0]: f"{user[0]} ({user[2]})" if user[2] else user[0] for user in user_data}
    
    with col1:
        user_id = st.selectbox(
            "Select User",
            options=user_ids,
            index=0,
            format_func=lambda x: user_display.get(x, x),
            help="Select your user ID"
        )
        
        if user_id and st.button("Login"):
            st.session_state.user_id = user_id
            st.success(f"Logged in as {user_id}")
            time.sleep(1)  # Brief pause for UX
            st.rerun()
    
    with col2:
        st.info("This is a simulation of a login. In a real system, this would require authentication.")

def main_app():
    """Main application interface for spread building and submission."""
    st.title(f"LME Spread Builder - User: {st.session_state.user_id}")
    
    # Sidebar for PDF uploads
    with st.sidebar:
        st.header("LME Forward Curve Data")
        st.write("Upload LME forward curve PDF(s) to get the latest rates.")
        
        uploaded_pdfs = st.file_uploader("Upload LME PDFs", type="pdf", accept_multiple_files=True)
        
        if uploaded_pdfs:
            # Store temporary files and metals in a list to process together
            temp_files_and_metals = []
            
            for uploaded_pdf in uploaded_pdfs:
                # Save uploaded file temporarily
                temp_path = Path(f"temp_{uploaded_pdf.name}")
                temp_path.write_bytes(uploaded_pdf.getvalue())
                
                # Determine metal from filename prefix (first 2 letters)
                prefix = uploaded_pdf.name[:2].lower()
                metal_map = {
                    "al": "Aluminum", 
                    "ah": "Aluminum",  # Additional code for Aluminum
                    "cu": "Copper", 
                    "zn": "Zinc",
                    "zs": "Zinc",      # Additional code for Zinc
                    "ni": "Nickel", 
                    "pb": "Lead", 
                    "sn": "Tin"
                }
                
                metal = metal_map.get(prefix)
                if not metal:
                    valid_prefixes = ", ".join(f"{k} ({v})" for k, v in metal_map.items())
                    st.warning(f"Could not determine metal for file: {uploaded_pdf.name}. Valid prefixes are: {valid_prefixes}")
                    continue
                    
                # Add to the list to process later
                temp_files_and_metals.append((temp_path, metal, uploaded_pdf.name))
            
            # Single button to process all PDFs at once
            if st.button("Process All PDFs"):
                for temp_path, metal, filename in temp_files_and_metals:
                    with st.spinner(f"Processing {metal} PDF ({filename})..."):
                        try:
                            # Extract rates
                            rates = extract_c3m_rates_from_pdf(str(temp_path), metal)
                            
                            if rates:
                                num_rates = len(rates)
                                st.success(f"Successfully extracted {num_rates} rate entries for {metal}")
                                st.session_state.rates_loaded = True
                            else:
                                st.error(f"Failed to extract rates from {metal} PDF. Please check the file format.")
                            
                            # Clean up
                            temp_path.unlink()
                        except Exception as e:
                            st.error(f"Error processing {metal} PDF: {str(e)}")
                            if temp_path.exists():
                                temp_path.unlink()

        # Add a separator
        st.markdown("---")
        
        # Cash-to-3M date specification in sidebar
        st.header("Cash and 3M Dates")
        cash_date = st.date_input(
            "Cash Date",
            value=datetime.now() + timedelta(days=2), # Cash date is typically T+2
            help="Enter the Cash date (usually T+2)"
        )
        
        three_m_date = st.date_input(
            "3M Date",
            value=datetime.now() + timedelta(days=90), # 3M date is typically T+90
            help="Enter the 3M date (usually T+90)"
        )
        
        # Logout option in sidebar
        if st.button("Logout"):
            st.session_state.user_id = None
            st.rerun()

    # Main area - split into two tabs
    tab1, tab2 = st.tabs(["Build Spread", "History"])
    
    # Tab 1: Spread Builder
    with tab1:
        st.header("Build Your Spread")
        
        # Create a row with left and right buttons
        left_col, spacer, right_col = st.columns([2, 8, 2])
        
        # Add New Carry button with custom styling
        with left_col:
            if st.button("➕ Add New Carry", use_container_width=True):
                if "current_carries" not in st.session_state:
                    st.session_state.current_carries = []
                
                # Add a new carry - initialize with TWO legs right away
                st.session_state.current_carries.append({
                    "id": len(st.session_state.current_carries) + 1,
                    "metal": "Aluminum",  # Default metal
                    "legs": [{"id": 1}, {"id": 2}]  # Initialize with 2 legs
                })
                # Initialize new expander state to be open
                carry_idx = len(st.session_state.current_carries) - 1
                st.session_state.expander_states[f"carry_{carry_idx}"] = True
                st.rerun()
        
        # Collapse All button
        with right_col:
            if st.button("Collapse All", use_container_width=True):
                # Set all known expanders to collapsed state
                for i in range(len(st.session_state.current_carries)):
                    key = f"carry_{i}"
                    st.session_state.expander_states[key] = False
                st.rerun()
        
        # Initialize carries if not exist
        if "current_carries" not in st.session_state:
            st.session_state.current_carries = [{"id": 1, "metal": "Aluminum", "legs": []}]
        
        # Loop through each carry
        for carry_idx, carry in enumerate(st.session_state.current_carries):
            # Initialize this expander's state if it doesn't exist yet
            expander_key = f"carry_{carry_idx}"
            if expander_key not in st.session_state.expander_states:
                st.session_state.expander_states[expander_key] = True
                
            # Create the expander without the problematic parameters
            with st.expander(
                f"Carry {carry_idx+1}: {carry['metal']}", 
                expanded=not st.session_state.force_collapse if "force_collapse" in st.session_state and st.session_state.force_collapse else st.session_state.expander_states[expander_key]):
                
                # Update state tracking to indicate this expander is open
                st.session_state.expander_states[expander_key] = True
                
                # Single metal selector for the entire carry (for all legs)
                # Create a narrow column for it
                metal_col, _ = st.columns([1, 3])
                with metal_col:
                    metal = st.selectbox(
                        "Metal",
                        options=METALS,
                        index=METALS.index(carry['metal']) if carry['metal'] in METALS else 0,
                        key=f"metal_{carry_idx}",
                    )
                    carry['metal'] = metal
                
                # Initialize with two legs if none exist
                if 'legs' not in carry or not carry['legs']:
                    carry['legs'] = [{"id": 1}, {"id": 2}]
                
                # Convert to datetime objects
                cash_datetime = datetime.combine(cash_date, datetime.min.time())
                three_m_datetime = datetime.combine(three_m_date, datetime.min.time())
                
                # Define legs and collect leg data
                legs_data = []
                
                # Build leg data outside of form to allow live updates
                for i, leg in enumerate(carry['legs']):
                    # Store the leg name as a variable but don't create an input field
                    leg_name = f"Leg {i+1}"
                    
                    # Direction radio buttons back on the left
                    direction = st.radio(
                        "Direction",  # Provide a label
                        options=["Borrow", "Lend"],
                        horizontal=True,
                        key=f"direction_{carry_idx}_{i}",
                        label_visibility="collapsed"  # Hide the label while keeping it accessible
                    )
                    
                    # Create columns with reduced spacing between them for the input fields
                    # All inputs on the same row with equal sizing
                    c1, s1, c2, s2, c3, _ = st.columns([1, 0.2, 1, 0.2, 1, 1])
                    
                    with c1:
                        lots = st.number_input(
                            f"Lots ({leg_name})",  # Include leg name in the label
                            min_value=1,
                            value=100,
                            step=25,
                            key=f"lots_{carry_idx}_{i}"
                        )
                    
                    with c2:
                        # Put the start date input at the top
                        start_date = st.date_input(
                            f"Start Date ({leg_name})",  # Include leg name in the label
                            value=cash_date if i == 0 else datetime.now() + timedelta(days=i*30),
                            key=f"start_date_{carry_idx}_{i}",
                            format="DD/MM/YYYY"  # UK date format
                        )
                    
                    with c3:
                        end_date = st.date_input(
                            f"End Date ({leg_name})",  # Include leg name in the label
                            value=three_m_date if i == 0 else datetime.now() + timedelta(days=(i+1)*30),
                            key=f"end_date_{carry_idx}_{i}",
                            format="DD/MM/YYYY"  # UK date format
                        )
                    
                    # Convert dates to datetime for processing
                    start_datetime = datetime.combine(start_date, datetime.min.time())
                    end_datetime = datetime.combine(end_date, datetime.min.time())
                    
                    # Add leg to list
                    leg_data = {
                        "id": i+1,
                        "metal": metal,
                        "direction": direction,
                        "start_date": start_datetime,
                        "end_date": end_datetime,
                        "lots": lots,
                        "name": leg_name  # Store the custom name in leg data
                    }
                    legs_data.append(leg_data)
                
                # Add Leg and Remove Leg buttons side by side right before the summary section
                st.write("")  # Add a small spacer
                
                # Use the same column structure as the inputs to match widths but reduce right space
                c1, s1, c2, s2, c3, _ = st.columns([1, 0.2, 1, 0.2, 1, 1])
                
                with c1:
                    # Use container width to ensure consistent width with lots input
                    if st.button("➕ Add Leg", key=f"add_leg_{carry_idx}", 
                                disabled=len(carry.get('legs', [])) >= 3,
                                use_container_width=True):
                        if 'legs' not in carry:
                            carry['legs'] = []
                        carry['legs'].append({
                            "id": len(carry['legs']) + 1
                        })
                        st.rerun()  # Add rerun to refresh the UI
                
                with c2:
                    # Remove Leg button in the next column
                    if st.button("➖ Remove Leg", key=f"remove_leg_{carry_idx}", 
                                disabled=len(carry.get('legs', [])) <= 1,  # Changed from 0 to 1 to prevent removing all legs
                                use_container_width=True):
                        if carry['legs'] and len(carry['legs']) > 1:  # Additional check to ensure we keep at least 1 leg
                            carry['legs'].pop()
                            st.rerun()  # Add rerun to refresh the UI
                
                # Calculate valuation immediately (outside of form)
                if legs_data:
                    try:
                        total_pnl, leg_details = price_spread(legs_data)
                        
                        # Show valuation details
                        st.subheader(f"{metal} Spread Summary")
                        
                        # Leg details table - add compact display for tables
                        leg_data_table = []
                        for leg, pnl, rate in leg_details:
                            leg_days = (leg['end_date'] - leg['start_date']).days
                            
                            # Use the custom leg name if available, otherwise use regular ID
                            display_leg_name = leg.get('name', f"Leg {leg['id']}")
                            
                            # Calculate the total valuation for this leg
                            total_valuation = None
                            if rate is not None:
                                total_valuation = rate * leg_days * leg['lots']
                            
                            # Format the rate as dollar amount with 2 decimal places
                            formatted_rate = None
                            if rate is not None:
                                formatted_rate = rate
                            
                            leg_data_table.append({
                                "Metal": metal,  # Put Metal first
                                "Leg": display_leg_name,
                                "Direction": leg['direction'],
                                "Start": format_date(leg['start_date']),
                                "End": format_date(leg['end_date']),
                                "Days": leg_days,
                                "Lots": leg['lots'],
                                "Valuation": f"{total_valuation:.2f}" if total_valuation is not None else "Unknown",
                                "Daily Rate": f"{formatted_rate:.2f}" if formatted_rate is not None else "Unknown",
                                "P&L": f"${pnl:.2f}" if pnl is not None else "$0.00 (unknown)"
                            })
                        
                        leg_df = pd.DataFrame(leg_data_table)
                        # Use a smaller table with less padding
                        st.table(leg_df)
                        
                        # Make the valuation sections more compact
                        col1, col2 = st.columns(2)
                        
                        # Ensure total_pnl is a valid number 
                        safe_total_pnl = 0.0 if total_pnl is None else float(total_pnl)
                        
                        # Calculate the net amount before using it
                        # Set initial net amount to P&L
                        net_amount = safe_total_pnl
                        
                        with col1:
                            # P&L at Valuation
                            st.subheader("P&L at Valuation")
                            # Apply color directly based on P&L value
                            pnl_color = "green" if total_pnl > 0 else "red" if total_pnl < 0 else "gray"
                            st.markdown(f"### <span style='color:{pnl_color}'>${total_pnl:.2f}</span>", unsafe_allow_html=True)
                            
                            # We'll display the Net after the slider calculation is done below
                            # Creating a placeholder for Net that will be filled later
                            net_placeholder = st.empty()
                        
                        with col2:
                            # Acceptable Cost vs Valuation with sliding scale
                            st.subheader("Acceptable Cost vs Valuation")
                            
                            # Set a range of +/- $50,000 with 0 as the center point (neutral)
                            # But flip the scale: negative (left) = user pays, positive (right) = user receives
                            slider_min = -50000.0  # User pays money (negative value = payment from user)
                            slider_max = 50000.0   # User receives money (positive value = payment to user)
                            
                            # Add increment markers only (no colored bar background)
                            st.markdown("""
                            <div style="display: flex; justify-content: space-between; margin-bottom: -15px;">
                                <span style="color: red;">-$50k</span>
                                <span style="color: gray;">-$25k</span>
                                <span style="color: gray;">$0</span>
                                <span style="color: gray;">+$25k</span>
                                <span style="color: green;">+$50k</span>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Set slider with 0 as the default value (no adjustment)
                            acceptable_cost_adjustment = st.slider(
                                "Sliding Scale ($)",
                                min_value=slider_min,
                                max_value=slider_max,
                                value=0.0,  # Start at zero (neutral position)
                                step=250.0,
                                key=f"pnl_slider_{carry_idx}",
                                label_visibility="collapsed"  # Hide the label since we have the markers
                            )

                            # Now add custom CSS to style the slider track
                            if acceptable_cost_adjustment < 0:
                                # When slider is negative (paying), color the track red
                                st.markdown("""
                                <style>
                                /* Main track */
                                [data-testid="stSlider"] > div > div > div > div {
                                    background-color: red !important;
                                }
                                </style>
                                """, unsafe_allow_html=True)
                            elif acceptable_cost_adjustment > 0:
                                # When slider is positive (receiving), color the track green
                                st.markdown("""
                                <style>
                                /* Main track */
                                [data-testid="stSlider"] > div > div > div > div {
                                    background-color: green !important;
                                }
                                </style>
                                """, unsafe_allow_html=True)
                            else:
                                # When slider is at zero, keep track neutral gray
                                st.markdown("""
                                <style>
                                /* Main track */
                                [data-testid="stSlider"] > div > div > div > div {
                                    background-color: #e0e0e0 !important;
                                }
                                </style>
                                """, unsafe_allow_html=True)
                            
                            # Display the adjustment amount with appropriate color
                            # Color coding: green for receiving money (positive values), red for paying money (negative values)
                            adjustment_color = "green" if acceptable_cost_adjustment > 0 else "red" if acceptable_cost_adjustment < 0 else "gray"
                            if acceptable_cost_adjustment != 0:
                                direction = "Receiving" if acceptable_cost_adjustment > 0 else "Paying"
                                st.markdown(
                                    f"<span style='color:{adjustment_color}; font-size:18px'>{direction}: ${abs(acceptable_cost_adjustment):.2f}</span>", 
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown("<span style='color:gray; font-size:16px'>No adjustment to valuation</span>", unsafe_allow_html=True)
                                
                            # Calculate the net (P&L at valuation + adjustment)
                            # FLIPPED: positive adjustment (receiving) increases net, negative (paying) decreases net
                            net_amount = safe_total_pnl + acceptable_cost_adjustment
                        
                        # Now fill the Net placeholder with the updated value
                        with net_placeholder.container():
                            st.subheader("Net")
                            net_color = "green" if net_amount > 0 else "red" if net_amount < 0 else "gray"
                            st.markdown(
                                f"### <span style='color:{net_color}'>${net_amount:.2f}</span>", 
                                unsafe_allow_html=True
                            )
                            
                        # Put only the submit button in the form for final submission - full width
                        with st.form(key=f"spread_form_{carry_idx}"):
                            col1, col2, col3 = st.columns([1, 1, 1])
                            with col2:
                                submit_button = st.form_submit_button("Submit Spread")
                            
                            if submit_button:
                                if not st.session_state.rates_loaded:
                                    st.warning("Please load LME rates by uploading PDFs first.")
                                else:
                                    # Prepare the spread data for submission
                                    spread_data = {
                                        "metal": metal,
                                        "legs": [
                                            {
                                                "id": leg["id"],
                                                "direction": leg["direction"],
                                                "start_date": leg["start_date"].isoformat(),
                                                "end_date": leg["end_date"].isoformat(),
                                                "lots": leg["lots"],
                                                "name": leg.get("name", f"Leg {leg['id']}")  # Include the leg name
                                            }
                                            for leg in legs_data
                                        ],
                                        "valuation_pnl": total_pnl,
                                        "at_val_only": False,  # No longer using this option
                                        "max_loss": net_amount  # Use the net amount
                                    }
                                    
                                    try:
                                        spread_id = submit_spread_interest(st.session_state.user_id, spread_data)
                                        st.success(f"Spread submitted successfully with ID: {spread_id}")
                                    except Exception as e:
                                        st.error(f"Error submitting spread: {str(e)}")
                    
                    except Exception as e:
                        st.error(f"Error calculating valuation: {str(e)}")
        
    # Tab 2: History
    with tab2:
        st.header("Spread History")
        
        # Refresh button
        if st.button("🔄 Refresh History"):
            st.rerun()
        
        # Get user history
        history = get_user_spread_history(st.session_state.user_id)
        
        if not history:
            st.info("No spread history found. Submit a spread to see it here.")
        else:
            for spread in history:
                # Create an expander for each spread
                with st.expander(f"Spread #{spread['id']} - {spread['status']} - {spread['metal']} - {spread.get('submit_time', 'Unknown')}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("Spread Details")
                        st.write(f"Metal: {spread['metal']}")
                        st.write(f"Valuation P&L: {format_pnl(spread['valuation_pnl'])}", unsafe_allow_html=True)
                        st.write(f"At Valuation Only: {'Yes' if spread['at_val_only'] else 'No'}")
                        if not spread['at_val_only']:
                            st.write(f"Acceptable P&L Range: ${spread['max_loss']:.2f}")
                        st.write(f"Status: {spread['status']}")
                        st.write(f"Submitted: {spread.get('submit_time', 'Unknown')}")
                    
                    with col2:
                        st.subheader("Response")
                        if spread['status'] == 'Pending':
                            st.info("Waiting for Market Maker response...")
                        elif 'response' in spread and spread['response']:
                            response = spread['response']
                            st.write(f"Response Type: {response.get('status', 'Unknown')}")
                            
                            if response.get('status') == 'Accepted':
                                st.success("Your spread was accepted at the requested valuation.")
                            elif response.get('status') == 'Countered':
                                st.warning("Market Maker has countered your request.")
                                if 'counter_pnl' in response:
                                    st.write(f"Counter P&L: {format_pnl(response['counter_pnl'])}", unsafe_allow_html=True)
                                if 'message' in response:
                                    st.write(f"Message: {response['message']}")
                            elif response.get('status') == 'Rejected':
                                st.error("Your spread was rejected.")
                                if 'message' in response:
                                    st.write(f"Reason: {response['message']}")
                    
                    # Leg details
                    st.subheader("Legs")
                    if 'legs' in spread:
                        leg_rows = []
                        for leg in spread['legs']:
                            try:
                                start_date = datetime.fromisoformat(leg['start_date'])
                                end_date = datetime.fromisoformat(leg['end_date'])
                                
                                # Calculate days for this leg
                                leg_days = (end_date - start_date).days
                                
                                # We don't have the rate directly in history, so we'll try to derive it if available
                                rate = None
                                valuation = None
                                
                                # If the leg has a 'rate' field, use it
                                if 'rate' in leg:
                                    rate = leg['rate']
                                    valuation = rate * leg_days * leg['lots']
                                    
                                    # Format rate as dollar amount with 2 decimal places
                                    formatted_rate = rate
                                else:
                                    formatted_rate = None
                                
                                leg_rows.append({
                                    "Metal": spread['metal'],  # Put Metal first
                                    "Leg": leg.get('name', f"Leg {leg['id']}"),  # Use custom name if available
                                    "Direction": leg['direction'],
                                    "Start": format_date(start_date),
                                    "End": format_date(end_date),
                                    "Days": leg_days,
                                    "Lots": leg['lots'],
                                    "Daily Rate": f"{formatted_rate:.2f}" if formatted_rate is not None else "N/A",
                                    "Valuation": f"{valuation:.2f}" if valuation is not None else "N/A"
                                })
                            except (KeyError, ValueError) as e:
                                st.error(f"Error parsing leg data: {str(e)}")
                        
                        if leg_rows:
                            st.table(pd.DataFrame(leg_rows))
                    else:
                        st.write("No leg details available.")

# Main app flow
def main():
    """Main application flow control."""
    if st.session_state.user_id is None:
        login_screen()
    else:
        main_app()
        
        # Logout option was moved directly to the sidebar in main_app()

if __name__ == "__main__":
    main() 