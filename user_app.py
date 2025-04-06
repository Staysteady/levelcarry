import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import json
from pathlib import Path

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
    page_title="LME Spread Trading - User",
    page_icon="📈",
    layout="wide"
)

# Session state initialization
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'rates_loaded' not in st.session_state:
    st.session_state.rates_loaded = False
if 'current_carries' not in st.session_state:
    st.session_state.current_carries = [{"id": 1, "metal": "Aluminum", "legs": [{"id": 1}, {"id": 2}]}]

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
    
    with col1:
        user_id = st.selectbox(
            "Select User",
            options=["", "user1", "user2"],
            index=0,
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
        
        # Initialize collapse state if not exists
        if "collapse_all" not in st.session_state:
            st.session_state.collapse_all = False
        
        # Create a row with left and right buttons
        left_col, spacer, right_col = st.columns([2, 8, 2])
        
        # Add New Carry button with custom styling
        with left_col:
            if st.button("➕ Add New Carry", use_container_width=True):
                if "current_carries" not in st.session_state:
                    st.session_state.current_carries = []
                
                # Add a new carry 
                st.session_state.current_carries.append({
                    "id": len(st.session_state.current_carries) + 1,
                    "metal": "Aluminum",  # Default metal
                    "legs": []  # Will be populated when legs are added
                })
                st.rerun()
        
        # Collapse All button
        with right_col:
            if st.button("Collapse All", use_container_width=True):
                st.session_state.collapse_all = True
                st.rerun()
        
        # Initialize carries if not exist
        if "current_carries" not in st.session_state:
            st.session_state.current_carries = [{"id": 1, "metal": "Aluminum", "legs": []}]
        
        # Loop through each carry
        for carry_idx, carry in enumerate(st.session_state.current_carries):
            with st.expander(f"Carry {carry_idx+1}: {carry['metal']}", expanded=not st.session_state.collapse_all):
                # When expander is opened, reset collapse_all flag
                st.session_state.collapse_all = False
                
                # Metal selection for this carry
                metal = st.selectbox(
                    "Metal",
                    options=METALS,
                    index=METALS.index(carry['metal']) if carry['metal'] in METALS else 0,
                    key=f"metal_{carry_idx}"
                )
                carry['metal'] = metal
                
                # Add/Remove Leg buttons
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("➕ Add Leg", key=f"add_leg_{carry_idx}", 
                                 disabled=len(carry.get('legs', [])) >= 3):
                        if 'legs' not in carry:
                            carry['legs'] = []
                        carry['legs'].append({
                            "id": len(carry['legs']) + 1
                        })
                with col2:
                    if st.button("➖ Remove Leg", key=f"remove_leg_{carry_idx}", 
                                 disabled=len(carry.get('legs', [])) <= 0):
                        if carry['legs']:
                            carry['legs'].pop()
                
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
                    st.subheader(f"Leg {i+1}")
                    
                    # Direction radio buttons moved to the top
                    direction = st.radio(
                        f"Direction (Leg {i+1})",
                        options=["Borrow", "Lend"],
                        horizontal=True,
                        key=f"direction_{carry_idx}_{i}"
                    )
                    
                    # Date selection and lots in columns
                    col1, col2, col3 = st.columns([1, 2, 2])
                    
                    with col1:
                        lots = st.number_input(
                            f"Lots (Leg {i+1})",
                            min_value=1,
                            value=100,
                            step=25,
                            key=f"lots_{carry_idx}_{i}"
                        )
                    
                    with col2:
                        start_date = st.date_input(
                            f"Start Date (Leg {i+1})",
                            value=cash_date if i == 0 else datetime.now() + timedelta(days=i*30),
                            key=f"start_date_{carry_idx}_{i}"
                        )
                    
                    with col3:
                        end_date = st.date_input(
                            f"End Date (Leg {i+1})",
                            value=three_m_date if i == 0 else datetime.now() + timedelta(days=(i+1)*30),
                            key=f"end_date_{carry_idx}_{i}"
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
                        "lots": lots
                    }
                    legs_data.append(leg_data)
                
                # Calculate valuation immediately (outside of form)
                if legs_data:
                    try:
                        total_pnl, leg_details = price_spread(legs_data)
                        
                        # Show valuation details
                        st.subheader("Spread Valuation")
                        
                        # Leg details table
                        leg_data_table = []
                        for leg, pnl, rate in leg_details:
                            leg_days = (leg['end_date'] - leg['start_date']).days
                            
                            leg_data_table.append({
                                "Leg": leg['id'],
                                "Direction": leg['direction'],
                                "Start": format_date(leg['start_date']),
                                "End": format_date(leg['end_date']),
                                "Days": leg_days,
                                "Lots": leg['lots'],
                                "Daily Rate": f"${rate:.2f}/ton/day" if rate is not None else "Unknown",
                                "P&L": f"${pnl:.2f}" if pnl is not None else "$0.00 (unknown)"
                            })
                        
                        leg_df = pd.DataFrame(leg_data_table)
                        st.table(leg_df)
                        
                        # P&L at Valuation
                        st.subheader("P&L at Valuation")
                        # Apply color directly based on P&L value
                        pnl_color = "green" if total_pnl > 0 else "red" if total_pnl < 0 else "gray"
                        st.markdown(f"### <span style='color:{pnl_color}'>${total_pnl:.2f}</span>", unsafe_allow_html=True)
                        
                        # Ensure total_pnl is a valid number 
                        safe_total_pnl = 0.0 if total_pnl is None else float(total_pnl)
                        
                        # Acceptable Cost vs Valuation with sliding scale
                        st.subheader("Acceptable Cost vs Valuation")
                        
                        # Set a range of +/- $50,000 with 0 as the center point (neutral)
                        # But flip the scale: negative (left) = user pays, positive (right) = user receives
                        slider_min = -50000.0  # User pays money (negative value = payment from user)
                        slider_max = 50000.0   # User receives money (positive value = payment to user)
                        
                        # Add increment markers only (no colored bar background)
                        st.markdown("""
                        <div style="display: flex; justify-content: space-between; margin-bottom: -15px;">
                            <span style="color: red;">-$50,000<br/>(Pay)</span>
                            <span style="color: gray;">-$25,000</span>
                            <span style="color: gray;">$0</span>
                            <span style="color: gray;">+$25,000</span>
                            <span style="color: green;">+$50,000<br/>(Receive)</span>
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
                                f"### {direction}: <span style='color:{adjustment_color}'>${abs(acceptable_cost_adjustment):.2f}</span>", 
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown("### No adjustment to valuation", unsafe_allow_html=True)
                        
                        # Calculate the net (P&L at valuation + adjustment)
                        # FLIPPED: positive adjustment (receiving) increases net, negative (paying) decreases net
                        net_amount = safe_total_pnl + acceptable_cost_adjustment
                        
                        # Display the Net
                        st.subheader("Net")
                        net_color = "green" if net_amount > 0 else "red" if net_amount < 0 else "gray"
                        st.markdown(
                            f"### <span style='color:{net_color}'>${net_amount:.2f}</span>", 
                            unsafe_allow_html=True
                        )
                        
                        # Put only the submit button in the form for final submission
                        with st.form(key=f"spread_form_{carry_idx}"):
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
                                                "lots": leg["lots"]
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
                                leg_rows.append({
                                    "Leg": leg['id'],
                                    "Direction": leg['direction'],
                                    "Start": format_date(start_date),
                                    "End": format_date(end_date),
                                    "Lots": leg['lots']
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