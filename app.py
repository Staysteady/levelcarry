import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import plotly.graph_objects as go
from typing import Dict, List, Tuple
import sys
import argparse

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description="LME Cash-to-3M Level Carry Tool")
    parser.add_argument("--app_name", type=str, default="Rate Checker", help="Application name")
    # Get only known args, ignore streamlit's own args
    return parser.parse_known_args()[0]

# Get command line arguments
args = parse_args()
app_name = args.app_name

from src.models.trading_card import Position, TradingCard
from src.utils.data_processor import (
    parse_trading_card_csv,
    extract_c3m_rates_from_pdf,
    update_position_rates,
    find_tidy_opportunities
)
from src.utils.extract_pdf_data import (
    extract_spread_data_from_pdf,
    extract_spreads_from_all_pdfs,
    calculate_valuation,
    adjust_spreads_for_dates
)

# Page configuration
st.set_page_config(
    page_title="Rate Checker",
    page_icon="📊",
    layout="wide"
)

# Session state initialization
if 'trading_cards' not in st.session_state:
    st.session_state.trading_cards = []
if 'lme_rates' not in st.session_state:
    st.session_state.lme_rates = {}
if 'spreads_data' not in st.session_state:
    st.session_state.spreads_data = {}

def format_date_uk(date):
    """Format date in UK format (DD/MM/YY)"""
    return date.strftime('%d/%m/%y')

def parse_uk_date(date_str):
    """Parse a date string in UK format (DD/MM/YY or DD/MM/YYYY)"""
    try:
        return datetime.strptime(date_str, '%d/%m/%Y')
    except ValueError:
        try:
            return datetime.strptime(date_str, '%d/%m/%y')
        except ValueError:
            raise ValueError("Date must be in DD/MM/YY or DD/MM/YYYY format")

def display_position_chart(positions):
    """Display a chart of all positions with their durations."""
    if not positions:
        return
    
    # Create data for the chart
    data = []
    all_dates = []
    
    # Get all near and far dates for range calculation
    for pos in positions:
        all_dates.extend([pos.near_date, pos.far_date])
    
    # Calculate date range - use actual position dates, not fixed range
    if all_dates:
        min_date = min(all_dates)
        max_date = max(all_dates)
        # Add small buffer to start and end
        date_range = pd.date_range(
            start=min_date - timedelta(days=5), 
            end=max_date + timedelta(days=5), 
            freq='D'
        )
    else:
        # Fallback if no dates
        date_range = pd.date_range(start='2025-04-01', end='2025-07-31', freq='D')
    
    # Create traces for each position
    for pos in positions:
        color = "blue" if pos.lots > 0 else "red"
        text = (
            f"Owner: {pos.owner if hasattr(pos, 'owner') else 'Unknown'}<br>"
            f"Near: {format_date_uk(pos.near_date)}<br>"
            f"Far: {format_date_uk(pos.far_date)}<br>"
            f"Lots: {abs(pos.lots)}<br>"
            f"Daily Rate: {pos.daily_rate if pos.daily_rate else 'Unknown'}"
        )
        
        # Add the line representing the position duration
        data.append(
            go.Scatter(
                x=[pos.near_date, pos.far_date],
                y=[pos.lots, pos.lots],
                mode='lines+markers',
                line=dict(color=color),
                text=[text, text],
                hoverinfo='text',
                name=f"{abs(pos.lots)} lots ({'Long' if pos.lots > 0 else 'Short'})"
            )
        )
    
    # Create the figure
    fig = go.Figure(data=data)
    
    # Configure the layout
    fig.update_layout(
        title="Position Overview",
        xaxis_title="Date",
        yaxis_title="Position (Lots)",
        hovermode="closest",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Set x-axis range to match the actual position dates
    fig.update_xaxes(range=[min(all_dates) - timedelta(days=5), max(all_dates) + timedelta(days=5)])
    
    return fig

def main():
    st.title("LME Cash-to-3M Level Carry Tool")
    
    # Initialize session state if needed
    if 'trading_cards' not in st.session_state:
        st.session_state.trading_cards = []
    if 'lme_rates' not in st.session_state:
        st.session_state.lme_rates = {}
    if 'spreads_data' not in st.session_state:
        st.session_state.spreads_data = {}
    
    # Main app tabs
    tab1, tab2 = st.tabs(["Trading Analysis", "Spread Data Extraction"])
    
    with tab1:
        # Sidebar for file uploads and controls
        with st.sidebar:
            st.header("Data Input")
            
            # Trading card upload
            st.write("Upload Trading Card (CSV)")
            st.write("Expected format: Date (DD/MM/YY), Short Position, Long Position")
            uploaded_card = st.file_uploader("Choose file", type="csv", key="card_uploader")
            if uploaded_card:
                owner = st.text_input("Card Owner Name")
                if owner and st.button("Process Trading Card"):
                    try:
                        # Save uploaded file temporarily
                        temp_path = Path("temp_card.csv")
                        temp_path.write_bytes(uploaded_card.getvalue())
                        
                        # Parse trading card
                        card = parse_trading_card_csv(str(temp_path), owner)
                        st.session_state.trading_cards.append(card)
                        temp_path.unlink()  # Clean up
                        st.success(f"Added trading card for {owner}")
                    except Exception as e:
                        st.error(f"Error processing file: {str(e)}")
                        if temp_path.exists():
                            temp_path.unlink()
            
            # LME PDF upload
            st.header("Upload LME PDF")
            uploaded_pdf = st.file_uploader("Choose file", type="pdf", key="pdf_uploader")
            if uploaded_pdf:
                # Save uploaded file temporarily
                temp_path = Path("temp_lme.pdf")
                temp_path.write_bytes(uploaded_pdf.getvalue())
                
                # Extract rates
                new_rates = extract_c3m_rates_from_pdf(str(temp_path))
                st.session_state.lme_rates.update(new_rates)
                
                # Also extract spread data
                pdf_data = extract_spread_data_from_pdf(str(temp_path))
                if pdf_data["spreads"]:
                    metal = pdf_data["metal"]
                    st.session_state.spreads_data[metal] = pdf_data["spreads"]
                    st.success(f"Extracted spread data for {metal}")
                
                temp_path.unlink()  # Clean up
                
                # Update all cards with new rates
                for card in st.session_state.trading_cards:
                    update_position_rates(card, st.session_state.lme_rates)
                
                st.success(f"Updated LME rates: {new_rates}")
            
            # Manual trade entry
            st.header("Manual Trade Entry")
            with st.form("manual_trade"):
                owner = st.selectbox(
                    "Select Owner",
                    options=[card.owner for card in st.session_state.trading_cards] if st.session_state.trading_cards else [""]
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    near_date = st.date_input(
                        "Near Date",
                        value=datetime.now(),
                        format="DD/MM/YYYY"
                    )
                with col2:
                    default_far = datetime.now() + timedelta(days=90)
                    far_date = st.date_input(
                        "Far Date",
                        value=default_far,
                        format="DD/MM/YYYY"
                    )
                
                direction = st.selectbox("Direction", ["Long", "Short"])
                lots = st.number_input("Number of Lots", min_value=1)
                daily_rate = st.number_input("Daily Rate (optional)", value=None)
                
                if st.form_submit_button("Add Trade"):
                    if owner:
                        try:
                            # Convert date to datetime
                            near_datetime = datetime.combine(near_date, datetime.min.time())
                            far_datetime = datetime.combine(far_date, datetime.min.time())
                            
                            # Find the relevant trading card
                            for card in st.session_state.trading_cards:
                                if card.owner == owner:
                                    # Create new position
                                    pos = Position(
                                        near_date=near_datetime,
                                        far_date=far_datetime,
                                        lots=lots if direction == "Long" else -lots,
                                        daily_rate=daily_rate if daily_rate else None
                                    )
                                    card.positions.append(pos)
                                    st.success("Trade added successfully")
                                    break
                        except ValueError as e:
                            st.error(f"Error: {str(e)}")
                    else:
                        st.error("Please select an owner")
        
        # Main area
        if st.session_state.trading_cards:
            # Collect all positions from all trading cards
            all_positions = []
            for card in st.session_state.trading_cards:
                for pos in card.positions:
                    # Add owner attribute to position for display
                    pos.owner = card.owner
                    all_positions.append(pos)
            
            # Display position chart
            if all_positions:
                fig = display_position_chart(all_positions)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            
            # Find and display tidy opportunities
            st.header("Tidy Opportunities")
            
            # Filters for tidy opportunities
            col1, col2, col3 = st.columns(3)
            with col1:
                min_lots = st.number_input("Minimum Lots", min_value=0, value=50)
            with col2:
                max_payment = st.number_input("Maximum Payment", min_value=0.0, value=1.0)
            with col3:
                match_type = st.selectbox(
                    "Match Type",
                    options=["All", "Level Carry Only", "Low Payment Only", "Partial Matches Only"]
                )
            
            opportunities = find_tidy_opportunities(st.session_state.trading_cards, min_lots=min_lots, max_payment=max_payment)
            
            # Filter opportunities by match type
            if match_type == "Level Carry Only":
                opportunities = [opp for opp in opportunities if opp["is_level_carry"]]
            elif match_type == "Low Payment Only":
                opportunities = [opp for opp in opportunities if not opp["is_level_carry"] and opp["payment"] is not None and opp["payment"] <= max_payment]
            elif match_type == "Partial Matches Only":
                opportunities = [opp for opp in opportunities if not opp["is_level_carry"]]
            
            if not opportunities:
                st.info("No tidy opportunities found")
            else:
                for i, opp in enumerate(opportunities):
                    with st.expander(f"Opportunity {i+1}: {opp['matchable_lots']} lots - "
                                    f"{format_date_uk(opp['overlap_start'])} to {format_date_uk(opp['overlap_end'])}"):
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.subheader("Short Position")
                            st.write(f"**Owner:** {opp['short_owner']}")
                            st.write(f"**Near Date:** {format_date_uk(opp['short_position'].near_date)}")
                            st.write(f"**Far Date:** {format_date_uk(opp['short_position'].far_date)}")
                            st.write(f"**Lots:** {abs(opp['short_position'].lots)}")
                            st.write(f"**Daily Rate:** {opp['short_position'].daily_rate if opp['short_position'].daily_rate else 'Unknown'}")
                        
                        with col2:
                            st.subheader("Long Position")
                            st.write(f"**Owner:** {opp['long_owner']}")
                            st.write(f"**Near Date:** {format_date_uk(opp['long_position'].near_date)}")
                            st.write(f"**Far Date:** {format_date_uk(opp['long_position'].far_date)}")
                            st.write(f"**Lots:** {abs(opp['long_position'].lots)}")
                            st.write(f"**Daily Rate:** {opp['long_position'].daily_rate if opp['long_position'].daily_rate else 'Unknown'}")
                        
                        st.subheader("Match Details")
                        st.write(f"**Matchable Lots:** {opp['matchable_lots']}")
                        st.write(f"**Match Type:** {'Level Carry' if opp['is_level_carry'] else 'Partial Match'}")
                        
                        if not opp["is_level_carry"]:
                            st.write(f"**Overlap Period:** {format_date_uk(opp['overlap_start'])} to {format_date_uk(opp['overlap_end'])}")
                            st.write(f"**Overlap Days:** {opp['overlap_days']}")
                        
                        if opp["payment"] is not None:
                            st.write(f"**Daily Rate:** {opp['daily_rate']}")
                            st.write(f"**Payment:** {opp['payment']:.2f}")
        else:
            st.info("Upload trading cards to get started")
    
    with tab2:
        st.header("Cash-to-3M Spread Data Extraction")
        
        # Upload PDF files for spread extraction
        uploaded_pdfs = st.file_uploader("Upload LME PDF files", type="pdf", accept_multiple_files=True, key="spreads_pdf_uploader")
        
        if uploaded_pdfs:
            # Create a temporary directory for PDFs if it doesn't exist
            temp_dir = Path("temp_pdfs")
            temp_dir.mkdir(exist_ok=True)
            
            # Save uploaded PDFs temporarily
            for pdf in uploaded_pdfs:
                temp_path = temp_dir / pdf.name
                temp_path.write_bytes(pdf.getvalue())
            
            # Extract spread data from all PDFs
            spreads_data = extract_spreads_from_all_pdfs(str(temp_dir))
            
            # Update session state
            st.session_state.spreads_data.update(spreads_data)
            
            # Clean up temporary files
            for file in temp_dir.glob("*.pdf"):
                file.unlink()
            
            st.success(f"Extracted spread data for {', '.join(spreads_data.keys())}")
        
        # Date selection for Cash-to-3M calculation
        st.subheader("Cash-to-3M Valuation Calculator")
        col1, col2 = st.columns(2)
        
        with col1:
            cash_date = st.date_input(
                "Cash Date",
                value=datetime.now(),
                format="DD/MM/YYYY"
            )
        
        with col2:
            default_three_month = datetime.now() + timedelta(days=90)
            three_month_date = st.date_input(
                "Three Month Date",
                value=default_three_month,
                format="DD/MM/YYYY"
            )
        
        # Convert to datetime objects
        cash_datetime = datetime.combine(cash_date, datetime.min.time())
        three_month_datetime = datetime.combine(three_month_date, datetime.min.time())
        
        # Calculate valuations for all metals
        if st.session_state.spreads_data and st.button("Calculate Valuations"):
            st.subheader("Valuation Results")
            
            results = pd.DataFrame(columns=["Metal", "Valuation", "Per Day"])
            
            for metal, spreads in st.session_state.spreads_data.items():
                valuation = calculate_valuation(spreads, cash_datetime, three_month_datetime)
                
                if valuation is not None:
                    days = (three_month_datetime - cash_datetime).days
                    per_day = valuation / days if days > 0 else 0
                    
                    # Add to results DataFrame
                    results.loc[len(results)] = {
                        "Metal": metal,
                        "Valuation": round(valuation, 2),
                        "Per Day": round(per_day, 2)
                    }
            
            if not results.empty:
                st.dataframe(results)
            else:
                st.warning("No valuations could be calculated with the current data.")
        
        # Display raw spread data for examination
        if st.session_state.spreads_data:
            st.subheader("Raw Spread Data")
            metal = st.selectbox("Select Metal", options=list(st.session_state.spreads_data.keys()))
            
            if metal:
                # Create DataFrame for display
                spreads = st.session_state.spreads_data[metal]
                
                if spreads:
                    # Convert to DataFrame for easier display
                    df = pd.DataFrame([
                        {
                            "Start Date": spread["start_date"].strftime('%d-%m-%y'),
                            "End Date": spread["end_date"].strftime('%d-%m-%y'),
                            "Value": spread["value"],
                            "Per Day": spread["per_day"]
                        }
                        for spread in spreads
                    ])
                    
                    st.dataframe(df)
                else:
                    st.info(f"No spread data available for {metal}")

if __name__ == "__main__":
    main() 