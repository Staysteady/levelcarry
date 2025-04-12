#!/usr/bin/env python
"""
Launch script for the LME Spread Trading Platform.
This script launches all four Streamlit apps in separate processes.
"""

import subprocess
import os
import platform
import time
import signal
import sys
import webbrowser

def start_app(script_name, port):
    """Start a Streamlit app at the specified port."""
    cmd = ["streamlit", "run", script_name, "--server.port", str(port)]
    
    # For Windows, we need to set shell=True for the process to run properly
    use_shell = platform.system() == "Windows"
    
    # On Windows, we need 'start' to open a new window, on Unix we can use nohup
    if platform.system() == "Windows":
        cmd = ["start", "cmd", "/k"] + cmd
    
    print(f"Starting {script_name} on port {port}...")
    
    if platform.system() == "Windows":
        # Windows needs shell=True to open new windows
        process = subprocess.Popen(
            " ".join(cmd), 
            shell=True
        )
    else:
        # Create a new process that ignores SIGHUP (so it doesn't close when this script ends)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp
        )
    
    return process

def open_browser(port):
    """Open the browser to the given port."""
    url = f"http://localhost:{port}"
    webbrowser.open(url)
    print(f"Opening browser to {url}")

def main():
    """Launch all four Streamlit apps."""
    # Create process list to track what we've started
    processes = []
    
    try:
        # NOTE: We're skipping Redis check since we're using fakeredis for testing
        print("Using fakeredis for testing - skipping real Redis check.")
        
        # Configure apps and ports
        apps = [
            ("user_app.py", 8501),
            ("mm_app.py", 8502),
            ("dashboard_app.py", 8503),
            ("order_book_app.py", 8504)
        ]
        
        # Start each app
        for script_name, port in apps:
            process = start_app(script_name, port)
            processes.append(process)
            
            # Slight delay to avoid port conflicts during initialization
            time.sleep(2)
        
        print("\nAll applications started:")
        print("User App: http://localhost:8501")
        print("Market Maker App: http://localhost:8502")
        print("Dashboard: http://localhost:8503")
        print("Order Book: http://localhost:8504")
        
        # Give apps time to initialize before opening browsers
        print("\nWaiting for apps to initialize...")
        time.sleep(5)
        
        # Open each app in the browser
        for _, port in apps:
            open_browser(port)
        
        print("\nPress Ctrl+C to shut down all applications...")
        
        # Keep script running until user interrupts
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down applications...")
        
        # Terminate all processes
        for process in processes:
            try:
                if platform.system() != "Windows":
                    process.terminate()
                # Windows processes need to be killed differently
                # but since we launched new cmd windows, they'll need
                # to be closed manually by the user
            except:
                pass
        
        print("Shutdown complete.")

if __name__ == "__main__":
    main() 