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
ao_channel = "ao0"
ai_channel = "ai0"
sample_rate = 1000
duration = 100
window_size = 5
controller_maxflow = 500
argon_ratio = 1.395 #factor de conversão

# Dynamic variables managed by UI Sliders/Text Boxes
controller_desire = 90
time_open = 15    # seconds valve is OPEN (voltage_max)
time_closed = 2  # seconds valve is CLOSED (0V)

# Initial mathematical scaling
n_ar_ratio = controller_desire / argon_ratio
voltage_max = (5 * n_ar_ratio) / controller_maxflow #regra de conversão linear para 5V
voltage_wave = voltage_max  # Full voltage when open

# --- Buffers ---
max_buffer_points = 2000
time_history = deque(maxlen=max_buffer_points)
feedback_history = deque(maxlen=max_buffer_points)

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
def create_input_group(label_text, min_val, max_val, init_val):
    container = QtWidgets.QVBoxLayout()
    
    # Horizontal layout to keep label and text input on the same line
    header_layout = QtWidgets.QHBoxLayout()
    label = QtWidgets.QLabel(label_text)
    label.setStyleSheet("font-size: 11px; font-weight: bold;")
    
    text_box = QtWidgets.QLineEdit(str(init_val))
    text_box.setFixedWidth(50)
    text_box.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    
    header_layout.addWidget(label)
    header_layout.addWidget(text_box)
    container.addLayout(header_layout)
    
    slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
    slider.setMinimum(min_val)
    slider.setMaximum(max_val)
    slider.setValue(init_val)
    container.addWidget(slider)
    
    controls_panel.addLayout(container)
    
    # Synchronization functions
    def slider_to_text():
        text_box.setText(str(slider.value()))
        
    def text_to_slider():
        try:
            val = int(text_box.text())
            # Constrain typed values to slider limits
            val = max(min_val, min(max_val, val))
            text_box.setText(str(val))
            slider.setValue(val)
        except ValueError:
            text_box.setText(str(slider.value())) # Reset if non-numeric string typed

    slider.valueChanged.connect(slider_to_text)
    text_box.returnPressed.connect(text_to_slider)
    text_box.editingFinished.connect(text_to_slider)
    
    return slider, text_box

# Constructing our UI Controls
desire_slider, desire_box = create_input_group("Flow Setpoint:", 10, 200, controller_desire)
open_slider, open_box = create_input_group("Open Time (s):", 1, 120, time_open)
close_slider, close_box = create_input_group("Closed Time (s):", 1, 10, time_closed)

# Control Action Button Layout
button_layout = QtWidgets.QHBoxLayout()
layout.addLayout(button_layout)

toggle_button = QtWidgets.QPushButton("STOP")
toggle_button.setStyleSheet("background-color: red; color: white; font-size: 14px;")
button_layout.addWidget(toggle_button)

main_widget.setWindowTitle("Live Valve Tracking")
main_widget.resize(1000, 650)
main_widget.show()

# --- Plot ---
plot = plot_widget.addPlot(title=f"Setpoint vs Feedback (Open: {time_open}s / Closed: {time_closed}s)")
plot.setLabel('left', 'Voltage (V)')
plot.setLabel('bottom', 'Time (s)')
plot.setYRange(-5.0 / 10, 1.1 * 5.0) # Fixed viewport range to prevent jumpiness on dynamic edits
plot.showGrid(x=True, y=True)

setpoint_curve = plot.plot(pen=pg.mkPen('b', width=2))
feedback_curve = plot.plot(pen=pg.mkPen('g', width=2))

current_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('r', width=2))
plot.addItem(current_line)

text_item = pg.TextItem(anchor=(0, 0))
plot.addItem(text_item)

# --- NI Tasks ---
write_task = None
read_task = nidaqmx.Task()

read_task.ai_channels.add_ai_voltage_chan(
    f"{device_name}/{ai_channel}", min_val=0.0, max_val=5.0)

# --- Wave ---
def generate_wave():
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    period = time_open + time_closed
    phase = t % period
    wave = np.where(phase < time_open, voltage_wave, 0.0)
    return wave

# --- State ---
running = False
start_time = time.time()

# --- Update ---
def update():
    global running

    if not running:
        return

    try:
        now = time.time() - start_time

        try:
            current_val = read_task.read() + 0.15
        except:
            current_val = 0.0

        time_history.append(now)
        feedback_history.append(current_val)

        period = time_open + time_closed

        t_win = np.linspace(now - window_size, now + window_size, 3000)
        phase_win = t_win % period
        y_win = np.where(phase_win < time_open, voltage_wave, 0.0)

        setpoint_curve.setData(t_win, y_win)
        feedback_curve.setData(list(time_history), list(feedback_history))
        current_line.setPos(now)

        plot.setXRange(now - window_size, now + window_size)

        phase_now = now % period
        current_sp = voltage_wave if (phase_now < time_open) else 0.0
        
        recent_points = list(feedback_history)[-300:]
        historical_avg = np.mean(recent_points) if len(recent_points) > 0 else current_val
        
        if historical_avg > 0.05:
            error = (current_val / historical_avg) * 100
        else:
            error = 0.0

        text_item.setText(
            f"Time: {now:.1f}s\n"
            f"Setpoint: {current_sp:.2f} V\n"
            f"Feedback: {current_val:.2f} V\n"
            f"Error: {error:.1f} %"
        )
        text_item.setPos(now - window_size, voltage_max if voltage_max > 0.1 else 1.0)

    except Exception as e:
        print(f"Update error: {e}")

# --- Timer ---
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(10)

# --- Control Logic ---
def start_ao():
    global write_task, start_time, running, controller_desire, time_open, time_closed, n_ar_ratio, voltage_max, voltage_wave

    try:
        if write_task is not None:
            write_task.close()
    except:
        pass

    # Lock in values from inputs ONLY at the exact moment START is clicked
    controller_desire = desire_slider.value()
    time_open = open_slider.value()
    time_closed = close_slider.value()

    # Recalculate parameters
    n_ar_ratio = controller_desire / argon_ratio
    voltage_max = (5 * n_ar_ratio) / controller_maxflow
    voltage_wave = voltage_max

    # Update dynamic plot title profile string
    plot.setTitle(f"Setpoint vs Feedback (Open: {time_open}s / Closed: {time_closed}s)")

    write_task = nidaqmx.Task()
    write_task.ao_channels.add_ao_voltage_chan(
        f"{device_name}/{ao_channel}", min_val=0.0, max_val=5.0)

    write_task.timing.cfg_samp_clk_timing(
        rate=sample_rate, sample_mode=AcquisitionType.CONTINUOUS)

    write_task.write(generate_wave(), auto_start=True)

    start_time = time.time()
    running = True


def stop_ao():
    global running, write_task

    running = False

    try:
        if write_task is not None:
            write_task.stop()
            write_task.close()
            write_task = None
    except:
        pass

    try:
        with nidaqmx.Task() as zero_task:
            zero_task.ao_channels.add_ao_voltage_chan(
                f"{device_name}/{ao_channel}",
                min_val=0.0,
                max_val=5.0
            )
            zero_task.write(0.0, auto_start=True)
    except Exception as e:
        print(f"Error forcing 0V: {e}")

    # --- Clear History Queues on Stop Sequence ---
    time_history.clear()
    feedback_history.clear()
    
    # Reset UI curves visually so they clear instantly on stop
    setpoint_curve.clear()
    feedback_curve.clear()


def toggle_system():
    if running:
        stop_ao()
        toggle_button.setText("START")
        toggle_button.setStyleSheet("background-color: green; color: white; font-size: 14px;")
    else:
        start_ao()
        toggle_button.setText("STOP")
        toggle_button.setStyleSheet("background-color: red; color: white; font-size: 14px;")


toggle_button.clicked.connect(toggle_system)

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
            reset.ao_channels.add_ao_voltage_chan(f"{device_name}/{ao_channel}")
            reset.write(0.0, auto_start=True)
            print("Safety: Output reset to 0V.")
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