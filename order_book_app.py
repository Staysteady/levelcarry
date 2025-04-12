import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    get_pending_interests,
    respond_to_interest,
    get_user_spread_history,
    price_spread,
    get_redis_client,
    TONS_PER_LOT
)

# Page configuration
st.set_page_config(
    page_title="LME Spread Trading - Order Book",
    page_icon="📖",
    layout="wide"
)

# Session state initialization
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = None
if 'orders' not in st.session_state:
    st.session_state.orders = []
if 'display_mode' not in st.session_state:
    st.session_state.display_mode = 'all'  # Default view all orders
if 'filter_metal' not in st.session_state:
    st.session_state.filter_metal = 'All'
if 'filter_status' not in st.session_state:
    st.session_state.filter_status = 'All'
if 'user_filter' not in st.session_state:
    st.session_state.user_filter = 'All'
if 'sort_by' not in st.session_state:
    st.session_state.sort_by = 'Time'
if 'selected_order' not in st.session_state:
    st.session_state.selected_order = None
if 'refresh_interval' not in st.session_state:
    st.session_state.refresh_interval = 60  # Default to 60 seconds
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False

# List of available metals
METALS = ["Aluminum", "Copper", "Zinc", "Nickel", "Lead", "Tin"]

def format_date(date_str: str) -> str:
    """Format date string for display."""
    try:
        date = datetime.fromisoformat(date_str)
        return date.strftime('%d-%b-%y')
    except (ValueError, TypeError):
        return date_str

def format_pnl(pnl) -> str:
    """Format PnL value with color."""
    if pnl is None:
        return "<span style='color:gray'>$0.00</span>"
    
    color = "green" if pnl > 0 else "red" if pnl < 0 else "gray"
    return f"<span style='color:{color}'>${pnl:.2f}</span>"

def get_all_orders() -> list:
    """Get a complete list of all orders in the system."""
    # Get pending interests from Redis/DB
    pending = get_pending_interests()
    
    # Get user history for all users
    user_history = []
    for user_id in ["user1", "user2"]:
        user_history.extend(get_user_spread_history(user_id))
    
    # Combine all orders 
    all_orders = pending + user_history
    
    # Sort by submission time (newest first)
    all_orders.sort(key=lambda x: x.get('submit_time', ''), reverse=True)
    
    return all_orders

def get_filtered_orders(orders, filter_metal='All', filter_status='All', user_filter='All', sort_by='Time'):
    """Apply filters to the order list."""
    if not orders:
        return []
    
    # Apply metal filter
    if filter_metal != 'All':
        orders = [o for o in orders if o.get('metal') == filter_metal]
    
    # Apply status filter
    if filter_status != 'All':
        orders = [o for o in orders if o.get('status') == filter_status]
    
    # Apply user filter
    if user_filter != 'All':
        orders = [o for o in orders if o.get('user_id') == user_filter]
    
    # Apply sorting
    if sort_by == 'Time':
        orders.sort(key=lambda x: x.get('submit_time', ''), reverse=True)
    elif sort_by == 'Metal':
        orders.sort(key=lambda x: x.get('metal', ''))
    elif sort_by == 'Value':
        orders.sort(key=lambda x: x.get('valuation_pnl', 0), reverse=True)
    elif sort_by == 'Lots':
        # Sort by total lots across all legs
        orders.sort(key=lambda x: sum(leg.get('lots', 0) for leg in x.get('legs', [])), reverse=True)
    
    return orders

def auto_refresh():
    """Automatically refresh the data based on the interval."""
    if st.session_state.auto_refresh:
        if st.session_state.last_refresh is None:
            st.session_state.orders = get_all_orders()
            st.session_state.last_refresh = datetime.now()
        else:
            elapsed = (datetime.now() - st.session_state.last_refresh).total_seconds()
            if elapsed >= st.session_state.refresh_interval:
                st.session_state.orders = get_all_orders()
                st.session_state.last_refresh = datetime.now()
                st.rerun()

def display_order_summary(orders):
    """Display a summary table of all orders."""
    if not orders:
        st.info("No orders found with current filters.")
        return
    
    # Prepare data for table
    table_data = []
    for order in orders:
        # Get basic order info
        order_id = order.get('spread_id', 'unknown')
        user_id = order.get('user_id', 'unknown')
        metal = order.get('metal', 'Unknown')
        status = order.get('status', 'Unknown')
        
        # Parse submit time
        submit_time = order.get('submit_time', '')
        if submit_time:
            try:
                submit_time = datetime.fromisoformat(submit_time).strftime('%d-%b-%y %H:%M')
            except ValueError:
                pass
        
        # Get valuation
        valuation_pnl = order.get('valuation_pnl', 0)
        
        # Count legs and calculate total lots
        legs = order.get('legs', [])
        leg_count = len(legs)
        total_lots = sum(leg.get('lots', 0) for leg in legs)
        
        # Get date range (across all legs)
        start_dates = []
        end_dates = []
        
        for leg in legs:
            try:
                start_dates.append(datetime.fromisoformat(leg['start_date']))
                end_dates.append(datetime.fromisoformat(leg['end_date']))
            except (KeyError, ValueError):
                continue
        
        date_range = ""
        if start_dates and end_dates:
            min_start = min(start_dates)
            max_end = max(end_dates)
            date_range = f"{min_start.strftime('%d-%b')} to {max_end.strftime('%d-%b')}"
        
        # Get response info if available
        response_status = None
        if 'response' in order:
            response_status = order['response'].get('status')
            
            # For countered responses, include counter value
            if response_status == 'Countered':
                counter_pnl = order['response'].get('counter_pnl')
                if counter_pnl is not None:
                    response_status = f"Countered (${counter_pnl:.2f})"
        
        # Add to table data
        table_data.append({
            'ID': order_id,
            'User': user_id,
            'Metal': metal,
            'Date Range': date_range,
            'Legs': leg_count,
            'Total Lots': total_lots,
            'Valuation': f"${valuation_pnl:.2f}" if valuation_pnl is not None else "N/A",
            'Time': submit_time,
            'Status': status,
            'Response': response_status
        })
    
    # Create DataFrame
    df = pd.DataFrame(table_data)
    
    # Display interactive table
    st.dataframe(
        df,
        column_config={
            'ID': st.column_config.TextColumn('ID'),
            'User': st.column_config.TextColumn('User'),
            'Metal': st.column_config.TextColumn('Metal'),
            'Date Range': st.column_config.TextColumn('Date Range'),
            'Legs': st.column_config.NumberColumn('Legs'),
            'Total Lots': st.column_config.NumberColumn('Total Lots'),
            'Valuation': st.column_config.TextColumn('Valuation'),
            'Time': st.column_config.TextColumn('Submitted'),
            'Status': st.column_config.TextColumn('Status'),
            'Response': st.column_config.TextColumn('Response')
        },
        hide_index=True,
        use_container_width=True
    )

def display_order_details(order):
    """Display detailed information for a selected order."""
    if not order:
        st.info("Select an order to view details.")
        return
    
    # Create tabs for different views
    tab1, tab2 = st.tabs(["Order Details", "Visualize"])
    
    with tab1:
        # Top section: Order header info
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader(f"Order #{order.get('spread_id', 'unknown')}")
            st.write(f"User: {order.get('user_id', 'unknown')}")
            st.write(f"Metal: {order.get('metal', 'Unknown')}")
        
        with col2:
            submit_time = order.get('submit_time', '')
            if submit_time:
                try:
                    submit_time = datetime.fromisoformat(submit_time).strftime('%d-%b-%y %H:%M')
                except ValueError:
                    pass
                
            st.write(f"Submitted: {submit_time}")
            st.write(f"Status: {order.get('status', 'Unknown')}")
            
            if 'response' in order and order['response']:
                response_status = order['response'].get('status', 'Unknown')
                st.write(f"Response: {response_status}")
        
        with col3:
            valuation_pnl = order.get('valuation_pnl', 0)
            st.write(f"Valuation: {format_pnl(valuation_pnl)}", unsafe_allow_html=True)
            
            if 'at_val_only' in order:
                st.write(f"At Valuation Only: {'Yes' if order['at_val_only'] else 'No'}")
            
            if 'max_loss' in order and not order.get('at_val_only', False):
                st.write(f"Max Loss: ${order['max_loss']:.2f}")
        
        # Divider
        st.markdown("---")
        
        # Leg details table
        st.subheader("Leg Details")
        
        legs = order.get('legs', [])
        if legs:
            leg_data = []
            
            for leg in legs:
                try:
                    # Parse dates
                    start_date = datetime.fromisoformat(leg['start_date'])
                    end_date = datetime.fromisoformat(leg['end_date'])
                    days = (end_date - start_date).days
                    
                    # Get other details
                    direction = leg.get('direction', 'Unknown')
                    lots = leg.get('lots', 0)
                    name = leg.get('name', f"Leg {leg.get('id', '?')}")
                    
                    leg_data.append({
                        'Name': name,
                        'Direction': direction,
                        'Start': start_date.strftime('%d-%b-%y'),
                        'End': end_date.strftime('%d-%b-%y'),
                        'Days': days,
                        'Lots': lots
                    })
                    
                except (KeyError, ValueError) as e:
                    st.error(f"Error parsing leg data: {e}")
            
            if leg_data:
                st.table(pd.DataFrame(leg_data))
        else:
            st.info("No leg details available.")
        
        # Response section
        if 'response' in order and order['response']:
            st.subheader("Market Maker Response")
            
            response = order['response']
            status = response.get('status', 'Unknown')
            
            if status == 'Accepted':
                st.success("This order has been accepted by the market maker.")
                
            elif status == 'Countered':
                st.warning("The market maker has countered this order.")
                
                counter_pnl = response.get('counter_pnl')
                if counter_pnl is not None:
                    st.write(f"Counter P&L: {format_pnl(counter_pnl)}", unsafe_allow_html=True)
                
                # Show comparison to original valuation
                original_pnl = order.get('valuation_pnl', 0)
                if original_pnl is not None and counter_pnl is not None:
                    difference = counter_pnl - original_pnl
                    diff_text = f"Difference from original: {format_pnl(difference)}"
                    st.write(diff_text, unsafe_allow_html=True)
                
                # Show message if available
                if 'message' in response:
                    st.write(f"Message: {response['message']}")
                
                # Add accept/reject counter buttons for user
                user_id = order.get('user_id', '')
                if user_id.startswith('user'):
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Accept Counter Offer", key=f"accept_counter_{order.get('spread_id')}"):
                            st.success("Counter offer accepted successfully.")
                            # In a real implementation, this would update the order status
                    
                    with col2:
                        if st.button("Reject Counter Offer", key=f"reject_counter_{order.get('spread_id')}"):
                            st.error("Counter offer rejected.")
                            # In a real implementation, this would update the order status
            
            elif status == 'Rejected':
                st.error("This order has been rejected by the market maker.")
                
                if 'message' in response:
                    st.write(f"Reason: {response['message']}")
    
    with tab2:
        # Visualization tab
        st.subheader("Order Visualization")
        
        # Create a timeline visualization of the legs
        legs = order.get('legs', [])
        if legs:
            # Prepare data for Gantt chart
            gantt_data = []
            
            for i, leg in enumerate(legs):
                try:
                    start_date = datetime.fromisoformat(leg['start_date'])
                    end_date = datetime.fromisoformat(leg['end_date'])
                    direction = leg.get('direction', 'Unknown')
                    lots = leg.get('lots', 0)
                    name = leg.get('name', f"Leg {leg.get('id', '?')}")
                    
                    gantt_data.append({
                        'Leg': name,
                        'Start': start_date,
                        'End': end_date + timedelta(days=1),  # Add a day to make end inclusive
                        'Direction': direction,
                        'Lots': lots
                    })
                except (KeyError, ValueError):
                    continue
            
            if gantt_data:
                df = pd.DataFrame(gantt_data)
                
                # Create Gantt chart
                fig = px.timeline(
                    df, 
                    x_start="Start", 
                    x_end="End", 
                    y="Leg",
                    color="Direction",
                    color_discrete_map={"Borrow": "blue", "Lend": "red"},
                    hover_data=["Lots"]
                )
                
                # Customize layout
                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Leg",
                    title="Order Timeline",
                    height=300,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Also display a pie chart of direction distribution
                direction_counts = df.groupby('Direction')['Lots'].sum().reset_index()
                
                fig2 = px.pie(
                    direction_counts,
                    values='Lots',
                    names='Direction',
                    title='Direction Distribution (Lots)',
                    color='Direction',
                    color_discrete_map={"Borrow": "blue", "Lend": "red"}
                )
                
                fig2.update_layout(
                    height=300,
                    margin=dict(l=20, r=20, t=40, b=20),
                )
                
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No leg details available for visualization.")

def main():
    """Main application function."""
    st.title("LME Spread Trading Order Book")
    
    # Auto-refresh the data
    auto_refresh()
    
    # Sidebar with controls
    with st.sidebar:
        st.header("Order Book Controls")
        
        # Refresh controls
        st.subheader("Refresh Settings")
        
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
        if st.button("🔄 Refresh Orders"):
            st.session_state.orders = get_all_orders()
            st.session_state.last_refresh = datetime.now()
            st.rerun()
        
        if st.session_state.last_refresh:
            st.write(f"Last refreshed: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
        
        # Filtering controls
        st.subheader("Filter Orders")
        
        # Metal filter
        st.session_state.filter_metal = st.selectbox(
            "Metal",
            options=['All'] + METALS,
            index=0
        )
        
        # Status filter
        st.session_state.filter_status = st.selectbox(
            "Status",
            options=['All', 'Pending', 'Accepted', 'Countered', 'Rejected'],
            index=0
        )
        
        # User filter
        st.session_state.user_filter = st.selectbox(
            "User",
            options=['All', 'user1', 'user2', 'marketmaker'],
            index=0
        )
        
        # Sorting options
        st.session_state.sort_by = st.selectbox(
            "Sort By",
            options=['Time', 'Metal', 'Value', 'Lots'],
            index=0
        )
    
    # Main content - split into two areas
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.subheader("All Orders")
        
        # Get and filter orders
        if not st.session_state.orders or st.session_state.last_refresh is None:
            st.session_state.orders = get_all_orders()
            st.session_state.last_refresh = datetime.now()
        
        filtered_orders = get_filtered_orders(
            st.session_state.orders,
            st.session_state.filter_metal,
            st.session_state.filter_status,
            st.session_state.user_filter,
            st.session_state.sort_by
        )
        
        # Display order summary
        display_order_summary(filtered_orders)
        
        # Order selection
        st.subheader("Select Order")
        
        # Create a selection component
        order_options = [f"#{o.get('spread_id', 'unknown')} - {o.get('user_id', 'unknown')} - {o.get('metal', 'Unknown')}" 
                         for o in filtered_orders]
        
        if order_options:
            selected_idx = 0
            if st.session_state.selected_order is not None:
                # Try to find the current selection in the filtered list
                selected_id = st.session_state.selected_order.get('spread_id')
                for i, o in enumerate(filtered_orders):
                    if o.get('spread_id') == selected_id:
                        selected_idx = i
                        break
            
            selected_option = st.selectbox(
                "Select an order to view details",
                options=order_options,
                index=min(selected_idx, len(order_options)-1) if order_options else 0
            )
            
            # Find the selected order
            selected_idx = order_options.index(selected_option)
            st.session_state.selected_order = filtered_orders[selected_idx]
        else:
            st.info("No orders available with current filters.")
            st.session_state.selected_order = None
    
    with col2:
        st.subheader("Order Details")
        
        # Display selected order details
        display_order_details(st.session_state.selected_order)
    
    # Bottom section - order statistics
    st.markdown("---")
    st.subheader("Order Book Statistics")
    
    # Create metrics in a row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_orders = len(st.session_state.orders)
        st.metric("Total Orders", total_orders)
    
    with col2:
        pending_orders = len([o for o in st.session_state.orders if o.get('status') == 'Pending'])
        st.metric("Pending Orders", pending_orders)
    
    with col3:
        completed_orders = len([o for o in st.session_state.orders 
                               if o.get('status') == 'Accepted' or 
                               (o.get('response', {}).get('status') == 'Accepted')])
        st.metric("Completed Orders", completed_orders)
    
    with col4:
        total_lots = sum([
            sum(leg.get('lots', 0) for leg in o.get('legs', []))
            for o in st.session_state.orders
        ])
        st.metric("Total Lots", total_lots)
    
    # Display a small heatmap of orders by metal and status
    if st.session_state.orders:
        # Prepare data for heatmap
        status_counts = {}
        for order in st.session_state.orders:
            metal = order.get('metal', 'Unknown')
            
            # Get effective status
            if 'response' in order and order['response']:
                status = order['response'].get('status', order.get('status', 'Unknown'))
            else:
                status = order.get('status', 'Unknown')
            
            key = (metal, status)
            status_counts[key] = status_counts.get(key, 0) + 1
        
        # Create DataFrame
        heatmap_data = []
        for (metal, status), count in status_counts.items():
            heatmap_data.append({
                'Metal': metal,
                'Status': status,
                'Count': count
            })
        
        df = pd.DataFrame(heatmap_data)
        
        # Create pivot table
        if not df.empty:
            pivot_df = df.pivot_table(
                values="Count", 
                index="Metal", 
                columns="Status", 
                fill_value=0
            )
            
            # Plot heatmap
            fig = px.imshow(
                pivot_df,
                text_auto=True,
                labels=dict(x="Status", y="Metal", color="Count"),
                title="Orders by Metal and Status",
                height=300
            )
            
            st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main() 