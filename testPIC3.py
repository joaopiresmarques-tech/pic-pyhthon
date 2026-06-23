# -*- coding: utf-8 -*-
"""
Created on Sun May  3 19:22:42 2026

@author: joao.marques
"""

import nidaqmx
from nidaqmx.constants import AcquisitionType
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
import time
from collections import deque

# --- Configuration ---
device_name = "Dev2"

# Hard Reset Device on Launch to instantly clear background allocations
try:
    nidaqmx.system.Device(device_name).reset_device()
    print(f"Successfully reset {device_name} hardware channels.")
except Exception as e:
    print(f"Hardware reset warning (Device may not be connected yet): {e}")

ao_channel_1 = "ao0"
ao_channel_2 = "ao1"
ai_channel_1 = "ai0"      
ai_channel_2 = "ai1"      
sample_rate = 1000
duration = 6000          # Extended baseline to cover longer run profiles in minutes
window_size_min = 0.1    # Viewport window size in minutes (e.g., 0.1 min = 6 seconds)
argon_ratio = 1.395     # factor de conversão

# Controller 1 Hardware Constants (500 sccm)
controller_maxflow_1 = 500

# Controller 2 Hardware Constants (5 SLM = 5000 sccm)
controller_maxflow_2 = 5000

# Dynamic variables managed by UI Sliders/Text Boxes (Input in seconds)
controller_desire_1 = 90
time_open_1 = 15        
time_closed_1 = 2       

controller_desire_2 = 1500  
time_open_2 = 10        
time_closed_2 = 5       

# Dynamic Mathematical Scales (Instantiated global fallbacks)
voltage_max_1 = (5 * (controller_desire_1 / argon_ratio)) / controller_maxflow_1
voltage_max_2 = (5 * (controller_desire_2 / argon_ratio)) / controller_maxflow_2

# --- Buffers ---
max_buffer_points = 5000
time_history = deque(maxlen=max_buffer_points)
feedback_history_1 = deque(maxlen=max_buffer_points)
feedback_history_2 = deque(maxlen=max_buffer_points)

# --- Qt Application ---
app = QtWidgets.QApplication([])

main_widget = QtWidgets.QWidget()
layout = QtWidgets.QVBoxLayout(main_widget)

plot_widget = pg.GraphicsLayoutWidget()
layout.addWidget(plot_widget)

# --- Dynamic Controls UI Panel ---
controls_panel = QtWidgets.QHBoxLayout()
layout.addLayout(controls_panel)

# Function helper to create interactive input groups (Slider + Editable Text Box)
def create_input_group(parent_layout, label_text, min_val, max_val, init_val):
    container = QtWidgets.QVBoxLayout()
    
    header_layout = QtWidgets.QHBoxLayout()
    label = QtWidgets.QLabel(label_text)
    label.setStyleSheet("font-size: 11px; font-weight: bold;")
    
    text_box = QtWidgets.QLineEdit(str(init_val))
    text_box.setFixedWidth(60)
    text_box.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    
    header_layout.addWidget(label)
    header_layout.addWidget(text_box)
    container.addLayout(header_layout)
    
    slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
    slider.setMinimum(min_val)
    slider.setMaximum(max_val)
    slider.setValue(init_val)
    container.addWidget(slider)
    
    parent_layout.addLayout(container)
    
    def slider_to_text():
        text_box.setText(str(slider.value()))
        
    def text_to_slider():
        try:
            val = int(text_box.text())
            val = max(min_val, min(max_val, val))
            text_box.setText(str(val))
            slider.setValue(val)
        except ValueError:
            text_box.setText(str(slider.value()))

    slider.valueChanged.connect(slider_to_text)
    text_box.returnPressed.connect(text_to_slider)
    text_box.editingFinished.connect(text_to_slider)
    
    return slider, text_box

# --- UI Grouping for Controller 1 (500 sccm) ---
group_box_1 = QtWidgets.QGroupBox("Controller 1 (500 sccm)")
group_layout_1 = QtWidgets.QVBoxLayout(group_box_1)
desire_slider_1, desire_box_1 = create_input_group(group_layout_1, "Flow Setpoint:", 10, 200, controller_desire_1)
open_slider_1, open_box_1 = create_input_group(group_layout_1, "Open Time (s):", 1, 120, time_open_1)
close_slider_1, close_box_1 = create_input_group(group_layout_1, "Closed Time (s):", 1, 10, time_closed_1)
controls_panel.addWidget(group_box_1)

# --- UI Grouping for Controller 2 (5 SLM / 5000 sccm) ---
group_box_2 = QtWidgets.QGroupBox("Controller 2 (5 SLM)")
group_layout_2 = QtWidgets.QVBoxLayout(group_box_2)
desire_slider_2, desire_box_2 = create_input_group(group_layout_2, "Flow Setpoint (sccm):", 100, 4500, controller_desire_2)
open_slider_2, open_box_2 = create_input_group(group_layout_2, "Open Time (s):", 1, 120, time_open_2)
close_slider_2, close_box_2 = create_input_group(group_layout_2, "Closed Time (s):", 1, 10, time_closed_2)
controls_panel.addWidget(group_box_2)

# Control Action Button Layout (Split Control)
button_layout = QtWidgets.QHBoxLayout()
layout.addLayout(button_layout)

toggle_button_1 = QtWidgets.QPushButton("STOP 1")
toggle_button_1.setStyleSheet("background-color: red; color: white; font-size: 14px; font-weight: bold;")
button_layout.addWidget(toggle_button_1)

toggle_button_2 = QtWidgets.QPushButton("STOP 2")
toggle_button_2.setStyleSheet("background-color: red; color: white; font-size: 14px; font-weight: bold;")
button_layout.addWidget(toggle_button_2)

main_widget.setWindowTitle("Dual Valve Live Tracking System")
main_widget.resize(1200, 600)
main_widget.show()

# --- Plot 1 Setup (Controller 1) ---
plot1 = plot_widget.addPlot(title="Controller 1 (500 sccm)")
plot1.setLabel('left', 'Voltage (V)')
plot1.setLabel('bottom', 'Time (min)')
plot1.setYRange(-5.0 / 10, 1.1 * 5.0)
plot1.showGrid(x=True, y=True)

setpoint_curve_1 = plot1.plot(pen=pg.mkPen('b', width=2))
feedback_curve_1 = plot1.plot(pen=pg.mkPen('g', width=2))

current_line_1 = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('r', width=1.5))
plot1.addItem(current_line_1)

# Top Left Caption Text Object for Plot 1
text_item_1 = pg.TextItem(anchor=(0, 0), color=(255, 255, 255))
plot1.addItem(text_item_1)

# --- Plot 2 Setup (Controller 2) ---
plot2 = plot_widget.addPlot(title="Controller 2 (5 SLM)")
plot2.setLabel('left', 'Voltage (V)')
plot2.setLabel('bottom', 'Time (min)')
plot2.setYRange(-5.0 / 10, 1.1 * 5.0)
plot2.showGrid(x=True, y=True)

setpoint_curve_2 = plot2.plot(pen=pg.mkPen('c', width=2))
feedback_curve_2 = plot2.plot(pen=pg.mkPen('m', width=2))

current_line_2 = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('r', width=1.5))
plot2.addItem(current_line_2)

# Top Left Caption Text Object for Plot 2
text_item_2 = pg.TextItem(anchor=(0, 0), color=(255, 255, 255))
plot2.addItem(text_item_2)

# --- NI Tasks ---
write_task = None  
read_task = nidaqmx.Task()

read_task.ai_channels.add_ai_voltage_chan(f"{device_name}/{ai_channel_1}", min_val=0.0, max_val=5.0)
read_task.ai_channels.add_ai_voltage_chan(f"{device_name}/{ai_channel_2}", min_val=0.0, max_val=5.0)

# --- State ---
running_chan_1 = True
running_chan_2 = True
start_time = time.time()

# --- Waveform Generators ---
def generate_combined_wave():
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Calculate wave 1 if active, else assign clean zero line
    if running_chan_1:
        period_1 = time_open_1 + time_closed_1
        phase_1 = t % period_1
        wave_1 = np.where(phase_1 < time_open_1, voltage_max_1, 0.0)
    else:
        wave_1 = np.zeros_like(t)
        
    # Calculate wave 2 if active, else assign clean zero line
    if running_chan_2:
        period_2 = time_open_2 + time_closed_2
        phase_2 = t % period_2
        wave_2 = np.where(phase_2 < time_open_2, voltage_max_2, 0.0)
    else:
        wave_2 = np.zeros_like(t)
    
    return np.vstack((wave_1, wave_2))

# --- Update Loop ---
def update():
    if not running_chan_1 and not running_chan_2:
        return

    try:
        # Time processing converted cleanly into minutes for UI graphing
        now_seconds = time.time() - start_time
        now_minutes = now_seconds / 60.0

        try:
            ai_data = read_task.read()
            current_val_1 = ai_data[0] + 0.15
            current_val_2 = ai_data[1] + 0.15
        except:
            current_val_1 = 0.0
            current_val_2 = 0.0

        time_history.append(now_minutes)
        feedback_history_1.append(current_val_1)
        feedback_history_2.append(current_val_2)

        # Build UI viewport tracking frame 
        t_win_min = np.linspace(now_minutes - window_size_min, now_minutes + window_size_min, 3000)
        t_win_sec = t_win_min * 60.0 
        
        # Eval Setpoint Profile 1
        period_1 = time_open_1 + time_closed_1
        phase_win_1 = t_win_sec % period_1
        y_win_1 = np.where(phase_win_1 < time_open_1, voltage_max_1, 0.0) if running_chan_1 else np.zeros_like(t_win_sec)

        # Eval Setpoint Profile 2
        period_2 = time_open_2 + time_closed_2
        phase_win_2 = t_win_sec % period_2
        y_win_2 = np.where(phase_win_2 < time_open_2, voltage_max_2, 0.0) if running_chan_2 else np.zeros_like(t_win_sec)

        # Update Graph 1 arrays
        setpoint_curve_1.setData(t_win_min, y_win_1)
        feedback_curve_1.setData(list(time_history), list(feedback_history_1))
        current_line_1.setPos(now_minutes)
        plot1.setXRange(now_minutes - window_size_min, now_minutes + window_size_min)

        # Update Graph 2 arrays
        setpoint_curve_2.setData(t_win_min, y_win_2)
        feedback_curve_2.setData(list(time_history), list(feedback_history_2))
        current_line_2.setPos(now_minutes)
        plot2.setXRange(now_minutes - window_size_min, now_minutes + window_size_min)

        # Live Caption variables for Graph 1
        current_sp_1 = 0.0
        if running_chan_1:
            phase_now_1 = now_seconds % period_1
            current_sp_1 = voltage_max_1 if (phase_now_1 < time_open_1) else 0.0
        recent_points_1 = list(feedback_history_1)[-300:]
        historical_avg_1 = np.mean(recent_points_1) if len(recent_points_1) > 0 else current_val_1
        error_1 = (current_val_1 / historical_avg_1) * 100 if historical_avg_1 > 0.05 else 0.0

        text_item_1.setText(
            f"Time: {now_minutes:.1f} min\n"
            f"Setpoint 1: {current_sp_1:.2f} V\n"
            f"Feedback: {current_val_1:.2f} V\n"
            f"Error Group: {error_1:.1f} %"
        )
        text_item_1.setPos(now_minutes - window_size_min + (window_size_min * 0.05), 3.8)

        # Live Caption variables for Graph 2
        current_sp_2 = 0.0
        if running_chan_2:
            phase_now_2 = now_seconds % period_2
            current_sp_2 = voltage_max_2 if (phase_now_2 < time_open_2) else 0.0
        recent_points_2 = list(feedback_history_2)[-300:]
        historical_avg_2 = np.mean(recent_points_2) if len(recent_points_2) > 0 else current_val_2
        error_2 = (current_val_2 / historical_avg_2) * 100 if historical_avg_2 > 0.05 else 0.0

        text_item_2.setText(
            f"Time: {now_minutes:.1f} min\n"
            f"Setpoint 2: {current_sp_2:.2f} V\n"
            f"Feedback: {current_val_2:.2f} V\n"
            f"Error Group: {error_2:.1f} %"
        )
        text_item_2.setPos(now_minutes - window_size_min + (window_size_min * 0.05), 3.8)

    except Exception as e:
        print(f"Update error: {e}")

# --- Timer ---
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(10)

# --- Control Logic ---
def update_hardware_waveforms():
    """Reads latest GUI inputs, recalculates scales, and pushes new parameter limits dynamically to NI hardware."""
    global write_task
    global controller_desire_1, time_open_1, time_closed_1, voltage_max_1
    global controller_desire_2, time_open_2, time_closed_2, voltage_max_2

    # CRITICAL FIX: Pull latest state variables directly from UI inputs before calculations
    controller_desire_1 = desire_slider_1.value()
    time_open_1 = open_slider_1.value()
    time_closed_1 = close_slider_1.value()

    controller_desire_2 = desire_slider_2.value()
    time_open_2 = open_slider_2.value()
    time_closed_2 = close_slider_2.value()

    # Dynamic math updates inside context thread loop
    voltage_max_1 = (5 * (controller_desire_1 / argon_ratio)) / controller_maxflow_1
    voltage_max_2 = (5 * (controller_desire_2 / argon_ratio)) / controller_maxflow_2

    plot1.setTitle(f"Ctrl 1 (Open: {time_open_1}s / Closed: {time_closed_1}s)")
    plot2.setTitle(f"Ctrl 2 (Open: {time_open_2}s / Closed: {time_closed_2}s)")

    try:
        if write_task is not None:
            write_task.stop()
            write_task.close()
    except:
        pass

    write_task = nidaqmx.Task()
    write_task.ao_channels.add_ao_voltage_chan(f"{device_name}/{ao_channel_1}", min_val=0.0, max_val=5.0)
    write_task.ao_channels.add_ao_voltage_chan(f"{device_name}/{ao_channel_2}", min_val=0.0, max_val=5.0)
    write_task.timing.cfg_samp_clk_timing(rate=sample_rate, sample_mode=AcquisitionType.CONTINUOUS)
    write_task.write(generate_combined_wave(), auto_start=True)


def start_ao():
    global running_chan_1, running_chan_2, start_time
    
    running_chan_1 = True
    running_chan_2 = True
    
    update_hardware_waveforms()
    start_time = time.time()


def toggle_channel_1():
    global running_chan_1
    if running_chan_1:
        running_chan_1 = False
        toggle_button_1.setText("START 1")
        toggle_button_1.setStyleSheet("background-color: green; color: white; font-size: 14px; font-weight: bold;")
    else:
        running_chan_1 = True
        toggle_button_1.setText("STOP 1")
        toggle_button_1.setStyleSheet("background-color: red; color: white; font-size: 14px; font-weight: bold;")
    
    update_hardware_waveforms()


def toggle_channel_2():
    global running_chan_2
    if running_chan_2:
        running_chan_2 = False
        toggle_button_2.setText("START 2")
        toggle_button_2.setStyleSheet("background-color: green; color: white; font-size: 14px; font-weight: bold;")
    else:
        running_chan_2 = True
        toggle_button_2.setText("STOP 2")
        toggle_button_2.setStyleSheet("background-color: red; color: white; font-size: 14px; font-weight: bold;")
        
    update_hardware_waveforms()


toggle_button_1.clicked.connect(toggle_channel_1)
toggle_button_2.clicked.connect(toggle_channel_2)

# --- Cleanup ---
def cleanup():
    print("Shutting down...")
    timer.stop()

    try:
        if write_task is not None:
            write_task.stop()
            write_task.close()
    except:
        pass

    try:
        read_task.stop()
        read_task.close()
    except:
        pass

    try:
        with nidaqmx.Task() as reset:
            reset.ao_channels.add_ao_voltage_chan(f"{device_name}/{ao_channel_1}")
            reset.ao_channels.add_ao_voltage_chan(f"{device_name}/{ao_channel_2}")
            reset.write([0.0, 0.0], auto_start=True)
            print("Safety: Outputs reset to 0V.")
    except:
        pass

    QtWidgets.QApplication.quit()


def close_event(event):
    cleanup()
    event.accept()


main_widget.closeEvent = close_event

# --- Auto-start ---
start_ao()

# --- Run ---
QtWidgets.QApplication.instance().exec()