import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import plotly.graph_objects as go
from typing import Dict, List, Tuple

from src.models.trading_card import Position, TradingCard
from src.utils.data_processor import (
    parse_trading_card_csv,
    extract_c3m_rates_from_pdf,
    update_position_rates,
    find_tidy_opportunities
)

# Page configuration
st.set_page_config(
    page_title="LME C-3M Level Carry Tool",
    page_icon="📊",
    layout="wide"
)

# Session state initialization
if 'trading_cards' not in st.session_state:
    st.session_state.trading_cards = []
if 'lme_rates' not in st.session_state:
    st.session_state.lme_rates = {}

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

if __name__ == "__main__":
    main() 