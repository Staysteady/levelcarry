#!/usr/bin/env python3
"""
LME Rate Checker Tool

A simple Streamlit tool to check LME rates between two prompt dates.
This shows both the total valuation and per-day values between selected dates.
"""

import streamlit as st
import os
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
import plotly.graph_objects as go
import holidays
import calendar

# Import our custom modules
from utils.extract_lme_perday import extract_lme_perday, get_per_day_value, get_third_wednesday, count_trading_days

# Page config
st.set_page_config(
    page_title="Rate Checker",
    page_icon="📈",
    layout="wide"
)

# Helper functions
def format_date(date):
    """Format date for display."""
    if date:
        return date.strftime('%d-%m-%y')
    return "None"

def get_prompt_dates(year=None, month_range=None):
    """Get 3rd Wednesday prompt dates for a year."""
    if not year:
        year = datetime.now().year
    
    if not month_range:
        month_range = range(1, 13)  # All months
    
    prompt_dates = []
    for month in month_range:
        prompt_date = get_third_wednesday(year, month)
        prompt_dates.append(prompt_date)
    
    return prompt_dates

def load_cached_pdf_data(pdf_path):
    """Load and cache PDF data for reuse."""
    # Check if data is already in session state
    if 'pdf_data' not in st.session_state or st.session_state.pdf_path != pdf_path:
        try:
            data = extract_lme_perday(pdf_path)
            st.session_state.pdf_data = data
            st.session_state.pdf_path = pdf_path
            return data
        except Exception as e:
            st.error(f"Error loading PDF: {str(e)}")
            return None
    
    return st.session_state.pdf_data

def create_rate_chart(per_day_values, start_date=None, end_date=None):
    """Create a chart showing per-day rates."""
    if not per_day_values:
        return None
    
    # Convert to DataFrame for plotting
    data = []
    for entry in per_day_values:
        data.append({
            'start_date': entry['start_date'],
            'end_date': entry['end_date'],
            'per_day': entry['per_day'],
            'value': entry['value'],
            'prompt_name': entry.get('prompt_name', 'Unknown')
        })
    
    df = pd.DataFrame(data)
    
    # Sort by start date
    df = df.sort_values('start_date')
    
    # Create plotly figure
    fig = go.Figure()
    
    # Add per-day values
    fig.add_trace(go.Scatter(
        x=df['start_date'],
        y=df['per_day'],
        mode='lines+markers',
        name='Per Day Value',
        line=dict(color='blue', width=2),
        marker=dict(size=8)
    ))
    
    # Add spans for the sections
    for i, row in df.iterrows():
        # Add light background spans for each section
        fig.add_shape(
            type="rect",
            x0=row['start_date'],
            x1=row['end_date'],
            y0=min(df['per_day']) * 1.1 if min(df['per_day']) < 0 else min(df['per_day']) * 0.9,
            y1=max(df['per_day']) * 1.1 if max(df['per_day']) > 0 else max(df['per_day']) * 0.9,
            line=dict(width=0),
            fillcolor="lightblue",
            opacity=0.3
        )
        
        # Add labels for each section
        fig.add_annotation(
            x=(row['start_date'] + (row['end_date'] - row['start_date'])/2),
            y=row['per_day'],
            text=f"{row['prompt_name']}<br>{row['per_day']}",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1,
            arrowcolor="#636363",
            ax=0,
            ay=-30
        )
    
    # Highlight selected date range if provided
    if start_date and end_date:
        fig.add_shape(
            type="rect",
            x0=start_date,
            x1=end_date,
            y0=min(df['per_day']) * 1.1 if min(df['per_day']) < 0 else min(df['per_day']) * 0.9,
            y1=max(df['per_day']) * 1.1 if max(df['per_day']) > 0 else max(df['per_day']) * 0.9,
            line=dict(width=2, color="red"),
            fillcolor="red",
            opacity=0.1
        )
    
    # Update layout
    fig.update_layout(
        title="Per Day Values by Date Range",
        xaxis_title="Date",
        yaxis_title="Per Day Value",
        legend_title="Legend",
        height=500,
        margin=dict(l=20, r=20, t=40, b=20),
        hovermode="closest"
    )
    
    # Format x-axis as dates
    fig.update_xaxes(
        tickformat="%d-%b-%y",
        tickangle=90
    )
    
    return fig

# Utility function to sum daily curve values for a date range
def sum_daily_curve(daily_curve, start_date, end_date):
    total = 0.0
    date_count = 0
    current_date = start_date
    while current_date < end_date:
        date_key = current_date.strftime('%Y-%m-%d')
        if date_key in daily_curve:
            total += daily_curve[date_key]
            date_count += 1
        current_date += timedelta(days=1)
    return total, date_count

# Utility function to build cumulative valuation for a date range
def build_cumulative_valuation(daily_curve, start_date, end_date):
    cumulative = {}
    running_total = 0.0
    current = start_date
    while current < end_date:
        date_key = current.strftime('%Y-%m-%d')
        daily_value = daily_curve.get(date_key, 0.0)
        running_total += daily_value
        cumulative[date_key] = running_total
        current += timedelta(days=1)
    return cumulative

# Main application
def main():
    st.title("LME Rate Checker")
    
    # Sidebar for PDF upload and configuration
    with st.sidebar:
        st.header("Configuration")
        metals = ["AH", "CA", "NI", "PB", "SN", "ZS"]
        # Multi-upload for PDFs, one per metal
        uploaded_files = st.file_uploader("Upload LME PDFs (one per metal)", type=["pdf"], accept_multiple_files=True)
        if 'pdf_map' not in st.session_state:
            st.session_state.pdf_map = {}
        if uploaded_files:
            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)
            for pdf_file in uploaded_files:
                # Guess metal code from filename (first two letters, uppercase)
                metal_code = pdf_file.name[:2].upper()
                if metal_code in metals:
                    temp_path = temp_dir / pdf_file.name
                    with open(temp_path, "wb") as f:
                        f.write(pdf_file.getbuffer())
                    st.session_state.pdf_map[metal_code] = str(temp_path)
            st.success(f"Loaded PDFs for: {', '.join(st.session_state.pdf_map.keys())}")
        # Dropdown to select metal (only those with loaded PDFs)
        available_metals = list(st.session_state.pdf_map.keys())
        if available_metals:
            # Sort metals alphabetically
            available_metals.sort()
            selected_metal = st.selectbox("Select Metal", available_metals)
            pdf_path = st.session_state.pdf_map[selected_metal]
            st.info(f"Using PDF for metal: {selected_metal}")
        else:
            # Fallback to example PDFs in data directory
            data_dir = Path(__file__).parent / "data"
            pdf_files = list(data_dir.glob("*.pdf"))
            pdf_map = {}
            for f in pdf_files:
                metal_code = f.name[:2].upper()
                if metal_code in metals:
                    pdf_map[metal_code] = str(f)
            if pdf_map:
                available_metals = list(pdf_map.keys())
                # Sort metals alphabetically
                available_metals.sort()
                selected_metal = st.selectbox("Select Metal (example)", available_metals)
                pdf_path = pdf_map[selected_metal]
                st.info(f"Using example PDF for metal: {selected_metal}")
            else:
                st.warning("No PDFs found. Please upload a PDF.")
                pdf_path = None
        # Options
        st.subheader("Options")
        show_section_breakdown = st.checkbox("Show section breakdown", value=True)
        show_chart = st.checkbox("Show rate chart", value=True)
        # --- Cash Date and 3M Date selectors ---
        st.subheader("Key Dates")
        # Use session state to persist user selection
        if 'custom_cash_date' not in st.session_state:
            st.session_state.custom_cash_date = None
        if 'custom_3m_date' not in st.session_state:
            st.session_state.custom_3m_date = None
        cash_date_input = st.date_input(
            "Cash Date",
            value=st.session_state.custom_cash_date or datetime.now().date(),
            key="cash_date_input_box"
        )
        three_m_date_input = st.date_input(
            "3M Date",
            value=st.session_state.custom_3m_date or (datetime.now() + timedelta(days=90)).date(),
            key="three_m_date_input_box"
        )
        st.session_state.custom_cash_date = cash_date_input
        st.session_state.custom_3m_date = three_m_date_input
        # --- True Calendar Grid (like PDF) ---
        st.subheader("Monthly Calendar (Bad Days Highlighted)")
        # Use session state for month/year
        if 'cal_year' not in st.session_state:
            st.session_state.cal_year = datetime.now().year
        if 'cal_month' not in st.session_state:
            st.session_state.cal_month = datetime.now().month
        col_prev, col_label, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("←", key="prev_month"):
                if st.session_state.cal_month == 1:
                    st.session_state.cal_month = 12
                    st.session_state.cal_year -= 1
                else:
                    st.session_state.cal_month -= 1
        with col_next:
            if st.button("→", key="next_month"):
                if st.session_state.cal_month == 12:
                    st.session_state.cal_month = 1
                    st.session_state.cal_year += 1
                else:
                    st.session_state.cal_month += 1
        with col_label:
            st.markdown(f"### {datetime(st.session_state.cal_year, st.session_state.cal_month, 1).strftime('%B %Y')}")
        cal_year = st.session_state.cal_year
        cal_month = st.session_state.cal_month
        uk_holidays = holidays.country_holidays('GB', years=[cal_year])
        cal = calendar.Calendar()
        month_days = cal.monthdayscalendar(cal_year, cal_month)
        week_header = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        # Build HTML table
        html = '<table style="border-collapse:collapse;width:100%;text-align:center;font-size:small;">'
        html += '<tr>' + ''.join(f'<th style="padding:2px;">{d}</th>' for d in week_header) + '</tr>'
        # Find the 3rd Wednesday for the displayed month/year
        third_wed = get_third_wednesday(cal_year, cal_month).day
        for week in month_days:
            html += '<tr>'
            for i, day in enumerate(week):
                if day == 0:
                    html += '<td style="background:#cccccc;padding:2px;"> </td>'
                else:
                    date = datetime(cal_year, cal_month, day)
                    is_weekend = i >= 5
                    is_holiday = date in uk_holidays
                    is_third_wed = (day == third_wed and i == 2)  # Wednesday is index 2
                    style = "padding:2px;"
                    if is_third_wed:
                        style += "background:#ffb347;color:#b36b00;font-weight:bold;"
                    if is_holiday:
                        style += "background:#ffcccc;font-weight:bold;color:#b00;"
                    elif is_weekend:
                        style += "background:#e0e0e0;color:#888;"
                    html += f'<td style="{style}">{day}</td>'
            html += '</tr>'
        html += '</table>'
        st.markdown(html, unsafe_allow_html=True)
        st.caption("Red = UK Bank Holiday, Gray = Weekend")
    
    # Main content
    if pdf_path:
        # Load PDF data
        pdf_data = load_cached_pdf_data(pdf_path)
        
        if pdf_data:
            # Display basic info
            # Section for prompt date selection
            st.subheader("Check Rate Between Dates")
            
            # Initialize start and end dates
            default_start_date = pdf_data['cash_date'] if pdf_data['cash_date'] else datetime.now()
            default_end_date = pdf_data['three_month_date'] if pdf_data['three_month_date'] else (datetime.now() + timedelta(days=90))
            
            # Calendar date picker mode (always use calendar mode)
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input(
                    "Start Date:",
                    value=default_start_date,
                    min_value=default_start_date - timedelta(days=365),
                    max_value=default_end_date
                )
                start_date = datetime.combine(start_date, datetime.min.time())
            with col2:
                end_date = st.date_input(
                    "End Date:",
                    value=default_end_date,
                    min_value=start_date,
                    max_value=default_end_date + timedelta(days=365)
                )
                end_date = datetime.combine(end_date, datetime.min.time())
            
            # Ensure end date is after start date
            if end_date <= start_date:
                st.error("End date must be after start date")
            else:
                # --- First calculate the Day-by-Day Breakdown to get the correct cumulative value ---
                # This is the correct calculation that properly handles backwardation and contango
                breakdown_rows = []
                day_by_day_running_total = 0.0
                total_days = 0
                current = start_date
                
                # Build a list of (start, end, per_day) for lookup, only for detailed splits
                spread_ranges = []
                for entry in pdf_data.get("per_day_values", []):
                    if entry.get("is_summary", False):
                        continue  # Skip summary spreads
                    if entry["value"] is not None and entry["start_date"] and entry["end_date"]:
                        days = (entry["end_date"] - entry["start_date"]).days
                        per_day = entry["value"] / days if days > 0 else 0.0
                        spread_ranges.append((entry["start_date"], entry["end_date"], per_day))
                
                # Calculate day-by-day values and total
                debug_daily_vals = []
                while current < end_date:
                    next_day = current + timedelta(days=1)
                    # Find which spread this day belongs to
                    daily_value = None
                    for s_start, s_end, s_per_day in spread_ranges:
                        if s_start <= current < s_end:
                            daily_value = s_per_day
                            break
                    if daily_value is None:
                        daily_value = 0.0
                    
                    day_by_day_running_total += daily_value
                    debug_daily_vals.append((current.strftime('%Y-%m-%d'), daily_value))
                    total_days += 1
                    current = next_day
                
                print('DEBUG: Daily values summed for Valuation Results:', debug_daily_vals)
                
                # --- Now use the final cumulative total from day-by-day breakdown for the top Valuation Results section ---
                final_total_value = day_by_day_running_total  # This will be -23.38 for Cash-3M period
                per_day_value = final_total_value / total_days if total_days > 0 else 0
                
                # Display results
                st.subheader("Valuation Results")
                col1, col2, col3 = st.columns(3)
                col1.metric("Days", total_days)
                col2.metric("Per Day Value", f"{per_day_value:.2f}")
                col3.metric("Total Value", f"{final_total_value:.2f}")

                # --- Day-by-Day Breakdown Table ---
                st.subheader("Day-by-Day Breakdown")
                with st.expander("Day-by-Day Breakdown Table", expanded=True):
                    breakdown_rows = []
                    running_total = 0.0
                    current = start_date
                    # Build a list of (start, end, per_day) for lookup, only for detailed splits
                    spread_ranges = []
                    for entry in pdf_data.get("per_day_values", []):
                        if entry.get("is_summary", False):
                            continue  # Skip summary spreads
                        if entry["value"] is not None and entry["start_date"] and entry["end_date"]:
                            days = (entry["end_date"] - entry["start_date"]).days
                            per_day = entry["value"] / days if days > 0 else 0.0
                            spread_ranges.append((entry["start_date"], entry["end_date"], per_day))
                    while current < end_date:
                        next_day = current + timedelta(days=1)
                        # Find which spread this day belongs to
                        daily_value = None
                        for s_start, s_end, s_per_day in spread_ranges:
                            if s_start <= current < s_end:
                                daily_value = s_per_day
                                break
                        if daily_value is None:
                            daily_value = 0.0
                        running_total += daily_value
                        breakdown_rows.append({
                            "Leg1": current.strftime('%d/%m/%Y'),
                            "Leg2": next_day.strftime('%d/%m/%Y'),
                            "Daily Valuation": round(daily_value, 6),
                            "Cumulative Valuation": round(running_total, 6)
                        })
                        current = next_day
                    breakdown_df = pd.DataFrame(breakdown_rows)
                    
                    # Prepare CSV and text for copy/download
                    csv_data = breakdown_df.to_csv(index=False)
                    text_data = breakdown_df.to_csv(index=False, sep='\t')
                    
                    # Create charts from the breakdown data
                    if not breakdown_df.empty and show_chart:
                        # --- Day-by-Day Valuation Chart ---
                        st.subheader("Daily Valuation Chart")
                        fig_daily = go.Figure()

                        # To ensure we're showing the full PDF date range, we need a complete dataset
                        # Create a complete dataset from Cash Date to 3M Date from the PDF
                        cash_date = pdf_data['cash_date']
                        three_m_date = pdf_data['three_month_date']

                        if cash_date and three_m_date:
                            # First gather all dates from Cash to 3M to ensure we show the full range
                            all_dates = []
                            all_daily_vals = []
                            all_cum_vals = []
                            
                            running_total = 0.0
                            current_date = cash_date
                            while current_date < three_m_date:
                                next_day = current_date + timedelta(days=1)
                                daily_value = 0.0
                                
                                # Find the correct daily value from the spread ranges
                                for s_start, s_end, s_per_day in spread_ranges:
                                    if s_start <= current_date < s_end:
                                        daily_value = s_per_day
                                        break
                                
                                running_total += daily_value
                                
                                # Store values for plotting
                                all_dates.append(current_date)
                                all_daily_vals.append(daily_value)
                                all_cum_vals.append(running_total)
                                
                                current_date = next_day
                            
                            # Add the trace for complete dataset
                            fig_daily.add_trace(go.Scatter(
                                x=all_dates,
                                y=all_daily_vals,
                                mode='lines+markers',
                                name='Daily Valuation',
                                line=dict(color='royalblue', width=2),
                                marker=dict(size=6)
                            ))
                            
                            # Add red dotted horizontal line at y=0
                            fig_daily.add_shape(
                                type='line',
                                x0=cash_date,
                                x1=three_m_date,
                                y0=0,
                                y1=0,
                                line=dict(color='red', width=2, dash='dot'),
                                xref='x',
                                yref='y'
                            )
                            
                            # Add rectangular highlight for the selected date range
                            start_date_dt = pd.to_datetime(start_date)
                            end_date_dt = pd.to_datetime(end_date)
                            y_min = min(all_daily_vals) - 0.05
                            y_max = max(all_daily_vals) + 0.05
                            
                            fig_daily.add_shape(
                                type='rect',
                                x0=start_date_dt,
                                x1=end_date_dt,
                                y0=y_min,
                                y1=y_max,
                                fillcolor='rgba(135, 206, 250, 0.15)',  # Light blue with low opacity
                                line=dict(color='rgba(0, 100, 255, 0.5)', width=1),
                                layer='below'
                            )
                            
                            # Add vertical orange dotted lines for 3rd Wednesdays in range
                            current = cash_date.replace(day=1)
                            while current <= three_m_date:
                                third_wed = get_third_wednesday(current.year, current.month)
                                if cash_date <= third_wed <= three_m_date:
                                    fig_daily.add_shape(
                                        type='line',
                                        x0=third_wed,
                                        x1=third_wed,
                                        y0=y_min,
                                        y1=y_max,
                                        line=dict(color='orange', width=2, dash='dot'),
                                        xref='x',
                                        yref='y',
                                        layer='below'
                                    )
                                # Move to next month
                                if current.month == 12:
                                    current = current.replace(year=current.year+1, month=1)
                                else:
                                    current = current.replace(month=current.month+1)
                            
                            # Add vertical purple dotted lines for selected Cash Date and 3M Date
                            for special_date in [st.session_state.custom_cash_date, st.session_state.custom_3m_date]:
                                if special_date is not None:
                                    special_date_dt = pd.to_datetime(special_date)
                                    if cash_date <= special_date_dt <= three_m_date:
                                        fig_daily.add_shape(
                                            type='line',
                                            x0=special_date_dt,
                                            x1=special_date_dt,
                                            y0=y_min,
                                            y1=y_max,
                                            line=dict(color='purple', width=2, dash='dot'),
                                            xref='x',
                                            yref='y',
                                            layer='above'
                                        )
                            
                            # Set the x-axis range to always show the full cash to 3M date range
                            # Calculate how many days in the date range
                            days_in_range = (three_m_date - cash_date).days
                            
                            # Determine appropriate tick spacing based on range length
                            if days_in_range > 90:
                                tick_spacing = '7D'  # Weekly ticks for long ranges
                            elif days_in_range > 60:
                                tick_spacing = '5D'  # Every 5 days for medium-long ranges
                            elif days_in_range > 30:
                                tick_spacing = '3D'  # Every 3 days for medium ranges
                            else:
                                tick_spacing = '2D'  # Every 2 days for shorter ranges
                            
                            fig_daily.update_layout(
                                title='Day-by-Day Valuation',
                                xaxis_title='Date',
                                yaxis_title='Daily Valuation',
                                xaxis=dict(
                                    tickmode='linear',  # Linear mode to show all ticks
                                    dtick=tick_spacing,  # Adaptive tick spacing
                                    tickformat='%d-%b-%y',
                                    tickangle=90,  # vertical
                                    range=[cash_date, three_m_date]  # Always show full PDF date range
                                ),
                                yaxis=dict(nticks=20),
                                height=500,
                                margin=dict(l=20, r=20, t=40, b=120),  # increased bottom margin for date labels
                                hovermode='closest'
                            )
                            st.plotly_chart(fig_daily, use_container_width=True)
                        
                        # --- Cumulative Valuation Chart ---
                        st.subheader("Cumulative Valuation Chart")
                        fig_cum = go.Figure()
                        
                        # Add the trace for complete dataset for cumulative values
                        fig_cum.add_trace(go.Scatter(
                            x=all_dates,
                            y=all_cum_vals,
                            mode='lines+markers',
                            name='Cumulative Valuation',
                            line=dict(color='seagreen', width=2),
                            marker=dict(size=6)
                        ))
                        
                        # Add rectangular highlight for the selected date range
                        y_min_cum = min(all_cum_vals) - 0.5
                        y_max_cum = max(all_cum_vals) + 0.5
                        
                        fig_cum.add_shape(
                            type='rect',
                            x0=start_date_dt,
                            x1=end_date_dt,
                            y0=y_min_cum,
                            y1=y_max_cum,
                            fillcolor='rgba(135, 206, 250, 0.15)',  # Light blue with low opacity
                            line=dict(color='rgba(0, 100, 255, 0.5)', width=1),
                            layer='below'
                        )
                        
                        # Add vertical orange dotted lines for 3rd Wednesdays in range
                        current = cash_date.replace(day=1)
                        while current <= three_m_date:
                            third_wed = get_third_wednesday(current.year, current.month)
                            if cash_date <= third_wed <= three_m_date:
                                fig_cum.add_shape(
                                    type='line',
                                    x0=third_wed,
                                    x1=third_wed,
                                    y0=y_min_cum,
                                    y1=y_max_cum,
                                    line=dict(color='orange', width=2, dash='dot'),
                                    xref='x',
                                    yref='y',
                                    layer='below'
                                )
                            # Move to next month
                            if current.month == 12:
                                current = current.replace(year=current.year+1, month=1)
                            else:
                                current = current.replace(month=current.month+1)
                        
                        # Add vertical purple dotted lines for selected Cash Date and 3M Date
                        for special_date in [st.session_state.custom_cash_date, st.session_state.custom_3m_date]:
                            if special_date is not None:
                                special_date_dt = pd.to_datetime(special_date)
                                if cash_date <= special_date_dt <= three_m_date:
                                    fig_cum.add_shape(
                                        type='line',
                                        x0=special_date_dt,
                                        x1=special_date_dt,
                                        y0=y_min_cum,
                                        y1=y_max_cum,
                                        line=dict(color='purple', width=2, dash='dot'),
                                        xref='x',
                                        yref='y',
                                        layer='above'
                                    )
                        
                        # Set the x-axis range to always show the full cash to 3M date range
                        # Use the same tick spacing as determined for the daily chart
                        fig_cum.update_layout(
                            title='Cumulative Valuation',
                            xaxis_title='Date',
                            yaxis_title='Cumulative Valuation',
                            xaxis=dict(
                                tickmode='linear',  # Linear mode to show all ticks
                                dtick=tick_spacing,  # Use same adaptive tick spacing
                                tickformat='%d-%b-%y',
                                tickangle=90,  # vertical
                                range=[cash_date, three_m_date]  # Always show full PDF date range
                            ),
                            yaxis=dict(nticks=20),
                            height=500,
                            margin=dict(l=20, r=20, t=40, b=120),  # increased bottom margin for date labels
                            hovermode='closest'
                        )
                        st.plotly_chart(fig_cum, use_container_width=True)
                    
                    # Now display the table after the charts
                    st.subheader("Day-by-Day Breakdown Table")
                    st.dataframe(breakdown_df, use_container_width=True)
                    st.download_button(
                        label="Download as CSV",
                        data=csv_data,
                        file_name="day_by_day_breakdown.csv",
                        mime="text/csv"
                    )
                    st.text_area("Copy Table (Tab-Delimited)", text_data, height=200)

                # --- C-3M Split Breakdown Table (moved to bottom) ---
                if show_section_breakdown:
                    st.subheader("C-3M Split Breakdown (from PDF)")
                    split_rows = []
                    for entry in pdf_data.get("per_day_values", []):
                        if entry.get("is_summary", False):
                            continue  # Skip summary spreads
                        if entry["value"] is not None and entry["start_date"] and entry["end_date"]:
                            days = (entry["end_date"] - entry["start_date"]).days
                            per_day = entry["value"] / days if days > 0 else 0.0
                            split_rows.append({
                                "Start": entry["start_date"].strftime('%d/%m/%Y'),
                                "End": entry["end_date"].strftime('%d/%m/%Y'),
                                "Value": entry["value"],
                                "Trading Days": days,
                                "Per Day": round(per_day, 6)
                            })
                    split_df = pd.DataFrame(split_rows)
                    st.dataframe(split_df, use_container_width=True)
        else:
            st.error("Failed to extract data from PDF")
    else:
        # Show instructions if no PDF loaded
        st.info("Please upload an LME PDF file or select an example PDF from the sidebar to get started.")
        
        st.markdown("""
        ### Instructions
        
        This tool extracts and analyzes per-day values from LME forward curve PDFs:
        
        1. Upload an LME PDF using the sidebar
        2. Select start and end dates using either:
           - Calendar mode: Pick any dates from the calendar
           - Prompt dates mode: Select from 3rd Wednesday prompt dates
        3. View the calculated per-day and total values
        4. Explore the visualization of per-day values
        
        The tool focuses on the "Per Day" section in the red box of the PDF, with:
        - Cash date (first date in the green box)
        - 3M date (last date in the green box)
        - Per-day values for each date range
        - Section breakdown (Cash-May, May-Jun, etc.)
        """)


if __name__ == "__main__":
    main() 